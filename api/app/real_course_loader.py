"""Наполнение кабинета настоящим курсом — та часть, которой не нужна модель.

Здесь всё, что воспроизводится из репозитория: задания и критерии из
`real_course.py`, тексты условий и решений из `data/real_course/`, сохранённые
разборы модели из `data/real_course/ai_results.json` и выведенные из разметки
решения ревьюера.

Разделение с `scripts/load_real_course.py` проходит ровно по одной линии: там
живут команды, которые ходят в модель (прогнать проверку, составить вопросы,
выгрузить результат), здесь — те, что не ходят никуда. Поэтому этот модуль
можно вызывать на старте контейнера: чтобы поднять кабинет с теми же данными,
ключ к модели не нужен, интернет не нужен, и результат не зависит от того, что
модель ответит сегодня.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AiSignal,
    AiStatus,
    Assignment,
    Base,
    BlitzSession,
    BlitzStatus,
    Course,
    Enrollment,
    Review,
    ReviewAssignment,
    ReviewerAction,
    ReviewItem,
    Role,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
    User,
)
from .real_course import TASKS
from .synthetic_decisions import Judgement, calibrate

DATA = Path(__file__).resolve().parent.parent / "data" / "real_course"

# Сохранённые ответы модели. Файл лежит в репозитории, поэтому кабинет
# поднимается одинаково на любой машине — и без обращения к провайдеру.
RESULTS = DATA / "ai_results.json"

COURSE = "Авито Академия: разбор реальных ДЗ"


METHODIST = ("methodist@demo.local", "Анна Воронова")


REVIEWERS = (
    ("reviewer@demo.local", "Максим Орлов"),
    ("reviewer2@demo.local", "Елена Соколова"),
    ("reviewer3@demo.local", "Игорь Ефремов"),
)


STUDENTS = {
    "weak": (
        ("student@demo.local", "Дмитрий Волков"),
        ("student2@demo.local", "Артём Ковалёв"),
        ("student3@demo.local", "Ксения Романова"),
    ),
    "medium": (
        ("student4@demo.local", "Мария Иванова"),
        ("student5@demo.local", "Кирилл Попов"),
        ("student6@demo.local", "Егор Никитин"),
    ),
    "strong": (
        ("student7@demo.local", "Алексей Смирнов"),
        ("student8@demo.local", "Алина Морозова"),
        ("student9@demo.local", "Варвара Гусева"),
    ),
}


def schedule(index: int, now: datetime) -> tuple[datetime, datetime]:
    """Когда задание выдали и когда срок. Один источник дат на загрузку и сдвиг.

    Курс укладывается в последние полтора месяца и доходит до сегодня: иначе вся
    активность оказывается старше недели, и недельные срезы дашборда показывают
    ноль — кабинет выглядит заброшенным, хотя данные в нём есть."""

    opened = now - timedelta(days=38 - index * 3)
    return opened, opened + timedelta(days=14)


def sent_at(deadline: datetime, now: datetime, order: int) -> datetime:
    """Когда студент сдал. Не позже, чем сейчас: работ из будущего не бывает."""

    return min(deadline, now - timedelta(hours=6)) - timedelta(hours=30 + order * 7)


def wipe(db) -> None:
    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def people(db) -> tuple[User, list[User], dict[str, list[User]]]:
    def add(email, name, role, specialization=None):
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=name, role=role, specialization=specialization)
            db.add(user)
        return user

    methodist = add(*METHODIST, Role.METHODIST, "education")
    reviewers = [add(email, name, Role.REVIEWER, "education") for email, name in REVIEWERS]
    students = {
        level: [add(email, name, Role.STUDENT) for email, name in group]
        for level, group in STUDENTS.items()
    }
    db.flush()
    return methodist, reviewers, students


def statement_of(slug: str) -> str:
    path = DATA / slug / "statement.md"
    text = path.read_text("utf-8")
    # Служебный комментарий о происхождении файла в условие задания не идёт.
    return "\n".join(line for line in text.splitlines() if not line.startswith("<!--")).strip()


def solution_text(slug: str, level: str, source: str) -> str:
    name = f"{level}-{Path(source).stem}.md"
    path = DATA / slug / "solutions" / name
    text = path.read_text("utf-8")
    return "\n".join(line for line in text.splitlines() if not line.startswith("<!--")).strip()


def load(db, *, now: datetime) -> dict:
    course = db.scalar(select(Course).where(Course.title == COURSE))
    if course is None:
        course = Course(
            title=COURSE,
            specialization="education",
            reviewer_capacity=20,
            tone_of_voice={
                "style": "доброжелательный и предметный",
                "address": "на вы",
                "rules": ["Начинать с сильных сторон", "Замечания подкреплять цитатой из работы"],
            },
        )
        db.add(course)
        db.flush()

    methodist, reviewers, students = people(db)
    for group in students.values():
        for student in group:
            if not db.scalar(
                select(Enrollment.id).where(
                    Enrollment.course_id == course.id, Enrollment.user_id == student.id
                )
            ):
                db.add(Enrollment(course_id=course.id, user_id=student.id))
    db.flush()

    created = 0
    refreshed: list[str] = []
    for index, task in enumerate(TASKS):
        opened, deadline = schedule(index, now)
        assignment = db.scalar(
            select(Assignment).where(
                Assignment.course_id == course.id, Assignment.title == task.title
            )
        )
        if assignment is None:
            assignment = Assignment(
                course_id=course.id,
                title=task.title,
                statement=statement_of(task.slug),
                deadline_at=deadline,
                effort_weight=task.effort_weight,
                submission_channel="github",
                authoring={
                    "topic": task.topic,
                    "track": task.track,
                    "source": task.statement_path,
                },
                published_at=opened,
                created_at=opened,
            )
            db.add(assignment)
            db.flush()
            rubric = RubricVersion(
                assignment_id=assignment.id,
                version=1,
                criteria=[dict(item) for item in task.criteria],
                max_score=task.max_score,
                pass_score=task.pass_score
                if task.pass_score is not None
                else round(task.max_score * 0.6),
                author_id=methodist.id,
                published_at=opened,
                note=f"Критерии из условия: {task.statement_path}",
            )
            db.add(rubric)
            db.flush()
            assignment.current_rubric_version_id = rubric.id
        else:
            rubric = db.get(RubricVersion, assignment.current_rubric_version_id)
            # Текст условия — производная от файла, а не отдельная правда.
            # Если извлечение стало точнее, задание обязано это подхватить:
            # иначе в базе навсегда остаётся версия с мусором, а откуда она
            # взялась — уже не проследить.
            fresh_statement = statement_of(task.slug)
            if assignment.statement != fresh_statement:
                assignment.statement = fresh_statement
                refreshed.append(task.title)

        for order, solution in enumerate(task.solutions):
            pool = students[solution.level]
            student = pool[(index + order) % len(pool)]
            if db.scalar(
                select(Submission.id).where(
                    Submission.assignment_id == assignment.id,
                    Submission.student_id == student.id,
                )
            ):
                continue
            submitted_at = sent_at(deadline, now, order)
            submission = Submission(
                assignment_id=assignment.id,
                student_id=student.id,
                source_url=f"https://github.com/avito-academy/{task.slug}-{solution.level}",
                submitted_at=submitted_at,
                status=SubmissionStatus.IN_REVIEW,
                is_overdue=False,
            )
            db.add(submission)
            db.flush()
            db.add(
                Snapshot(
                    submission_id=submission.id,
                    content=solution_text(task.slug, solution.level, solution.path),
                    content_hash=f"real-{task.slug}-{solution.level}",
                    fetched_at=submitted_at,
                    # Метка кейсодателя. Она не участвует в оценке — её смысл в
                    # том, чтобы потом было с чем сравнить то, что поставит
                    # модель, и увидеть, различает ли она уровни работ.
                    parsed_facts={
                        "source": solution.path,
                        "expert_level": solution.level,
                        "expert_label": solution.label,
                    },
                )
            )
            reviewer = reviewers[(index + order) % len(reviewers)]
            db.add(
                ReviewAssignment(
                    submission_id=submission.id,
                    reviewer_id=reviewer.id,
                    explanation="Специализация совпадает · минимальная загрузка на момент назначения",
                    approved_by=methodist.id,
                    approved_at=submitted_at + timedelta(hours=3),
                    created_at=submitted_at + timedelta(minutes=10),
                )
            )
            db.add(Review(submission_id=submission.id, rubric_version_id=rubric.id))
            db.add(
                StatusHistory(
                    submission_id=submission.id,
                    from_status=None,
                    to_status=SubmissionStatus.SUBMITTED,
                    actor_id=student.id,
                    comment="Работа сдана",
                    created_at=submitted_at,
                )
            )
            created += 1
    db.commit()
    return {"created": created, "refreshed": refreshed}


def reschedule(db, *, now: datetime) -> int:
    """Пересчитать все даты курса от сегодняшнего дня.

    Загруженный однажды курс со временем «уезжает в прошлое»: недельные срезы
    пустеют, и дашборд выглядит так, будто на курсе ничего не происходит.
    Пересчёт идёт по той же формуле, что и загрузка, поэтому его можно
    запускать сколько угодно раз — результат зависит только от даты."""

    moved = 0
    for index, task in enumerate(TASKS):
        assignment = db.scalar(select(Assignment).where(Assignment.title == task.title))
        if assignment is None:
            continue
        opened, deadline = schedule(index, now)
        assignment.published_at = opened
        assignment.created_at = opened
        assignment.deadline_at = deadline
        for rubric in db.scalars(
            select(RubricVersion).where(RubricVersion.assignment_id == assignment.id)
        ):
            rubric.published_at = opened

        submissions = list(
            db.scalars(
                select(Submission)
                .where(Submission.assignment_id == assignment.id)
                .order_by(Submission.submitted_at)
            )
        )
        for order, submission in enumerate(submissions):
            submitted = sent_at(deadline, now, order)
            submission.submitted_at = submitted
            submission.is_overdue = submitted > deadline
            snapshot = db.scalar(
                select(Snapshot).where(Snapshot.submission_id == submission.id)
            )
            if snapshot:
                snapshot.fetched_at = submitted
            for handover in db.scalars(
                select(ReviewAssignment).where(
                    ReviewAssignment.submission_id == submission.id
                )
            ):
                handover.created_at = submitted + timedelta(minutes=10)
                if handover.approved_at is not None:
                    handover.approved_at = submitted + timedelta(hours=3)
            review = db.scalar(select(Review).where(Review.submission_id == submission.id))
            if review:
                review.created_at = submitted + timedelta(minutes=2)
                if review.completed_at is not None:
                    review.completed_at = submitted + timedelta(hours=18 + (order % 7) * 4)
            for row in db.scalars(
                select(StatusHistory).where(StatusHistory.submission_id == submission.id)
            ):
                row.created_at = (
                    submitted
                    if row.to_status == SubmissionStatus.SUBMITTED
                    else (review.completed_at if review and review.completed_at else submitted)
                )
            moved += 1
    db.commit()
    return moved


def complete(db, *, keep_open: int) -> dict:
    """Закрыть проверку по старым заданиям: ревьюер принял решение по критериям.

    Решения выводятся из разметки кейсодателя (см. `app/synthetic_decisions`), а
    не выдумываются: иначе «доля согласия с AI» и «критерии с частыми правками»
    показывали бы ровный шум. `keep_open` последних заданий остаются в работе —
    без них пустеет очередь ревьюера, а это половина кабинета.
    """

    titles = [task.title for task in TASKS]
    closing = set(titles[: max(len(titles) - keep_open, 0)])

    rows = db.execute(
        select(Review, Submission, Snapshot, Assignment)
        .join(Submission, Submission.id == Review.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
        .where(Review.ai_status == AiStatus.READY)
        .order_by(Submission.submitted_at)
    ).all()

    closed = changed = accepted = 0
    for order, (review, submission, snapshot, assignment) in enumerate(rows):
        if assignment.title not in closing or submission.status == SubmissionStatus.COMPLETED:
            continue
        level = (snapshot.parsed_facts or {}).get("expert_level", "")
        items = {item.criterion_key: item for item in review.items}
        decisions = calibrate(
            [
                Judgement(
                    key=item.criterion_key,
                    ai_score=item.ai_score or 0.0,
                    max_score=item.max_score,
                    confidence=item.confidence or "medium",
                )
                for item in review.items
            ],
            level=level,
        )
        if not decisions:
            continue
        for decision in decisions:
            item = items[decision.key]
            item.reviewer_action = (
                ReviewerAction.ACCEPTED
                if decision.action == "accepted"
                else ReviewerAction.CHANGED
            )
            item.final_score = decision.final_score
            item.reviewer_comment = decision.comment
            if decision.action == "accepted":
                accepted += 1
            else:
                changed += 1

        assignment_row = db.scalar(
            select(ReviewAssignment).where(
                ReviewAssignment.submission_id == submission.id,
                ReviewAssignment.is_active.is_(True),
            )
        )
        review.final_score = round(sum(d.final_score for d in decisions), 2)
        review.final_feedback = review.draft_feedback
        review.completed_by = assignment_row.reviewer_id if assignment_row else None
        review.completed_at = submission.submitted_at + timedelta(hours=18 + (order % 7) * 4)
        # Пометка в разборе: решения по этой работе достроены, а не приняты
        # живым ревьюером. Без неё демонстрационные данные со временем
        # становятся неотличимы от настоящих.
        review.raw_result = {**(review.raw_result or {}), "reviewer_decisions": "derived"}
        submission.status = SubmissionStatus.COMPLETED
        db.add(
            StatusHistory(
                submission_id=submission.id,
                from_status=SubmissionStatus.IN_REVIEW,
                to_status=SubmissionStatus.COMPLETED,
                actor_id=review.completed_by,
                comment="Проверка завершена",
                created_at=review.completed_at,
            )
        )
        closed += 1
    db.commit()
    return {"closed": closed, "accepted": accepted, "changed": changed}


# --------------------------------------------------------------------------- #
#  Сохранённые ответы модели
# --------------------------------------------------------------------------- #


def _work_key(source: str) -> str:
    """Чем опознаётся работа в сохранённых результатах.

    Путь к файлу решения, а не пара «задание + уровень»: у одного задания бывает
    два решения одного уровня, и по уровню они неразличимы."""

    return source


def saved_results() -> dict[str, dict]:
    if not RESULTS.exists():
        return {}
    payload = json.loads(RESULTS.read_text("utf-8"))
    return {_work_key(row["source"]): row for row in payload.get("reviews", [])}


def replay(db: Session) -> int:
    """Проставить разборы из сохранённого файла вместо обращения к модели.

    Это не «фиктивный разбор»: в файле лежат дословные ответы модели на эти же
    работы, снятые прогоном `--review` и записанные вместе с идентификатором
    запроса. Отличие от повторного прогона только одно — результат не зависит
    от того, что модель ответит сегодня, и одинаков на любой машине.
    """

    saved = saved_results()
    if not saved:
        return 0

    applied = 0
    rows = db.execute(
        select(Review, Submission, Snapshot)
        .join(Submission, Submission.id == Review.submission_id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
    ).all()
    for review, submission, snapshot in rows:
        record = saved.get(_work_key((snapshot.parsed_facts or {}).get("source", "")))
        if record is None or review.ai_status == AiStatus.READY:
            continue
        for item in list(review.items):
            db.delete(item)
        for signal in list(review.signals):
            db.delete(signal)

        review.model = record["model"]
        review.ai_status = record["ai_status"]
        review.raw_result = record["raw_result"]
        review.draft_feedback = record["draft_feedback"]
        for position, item in enumerate(record["items"]):
            db.add(
                ReviewItem(
                    review_id=review.id,
                    position=position,
                    criterion_key=item["criterion_key"],
                    criterion_title=item["criterion_title"],
                    max_score=item["max_score"],
                    ai_score=item["ai_score"],
                    verdict=item["verdict"],
                    confidence=item["confidence"],
                    evidence=item["evidence"],
                    recommendation=item["recommendation"],
                    reviewer_action=ReviewerAction.PENDING,
                )
            )
        for signal in record["signals"]:
            db.add(AiSignal(review_id=review.id, **signal))

        if record.get("blitz"):
            sent = submission.submitted_at + timedelta(hours=20)
            db.add(
                BlitzSession(
                    review_id=review.id,
                    status=BlitzStatus.SENT,
                    questions=record["blitz"]["questions"],
                    sent_at=sent,
                    due_at=sent + timedelta(hours=48),
                )
            )
            submission.status = SubmissionStatus.BLITZ_SENT
            db.add(
                StatusHistory(
                    submission_id=submission.id,
                    from_status=SubmissionStatus.IN_REVIEW,
                    to_status=SubmissionStatus.BLITZ_SENT,
                    comment="Отправлены дополнительные вопросы",
                    created_at=sent,
                )
            )
        applied += 1
    db.commit()
    return applied


def restore(db: Session, *, keep_open: int = 3, now: datetime | None = None) -> dict:
    """Собрать кабинет целиком из того, что лежит в репозитории.

    Одна операция вместо пяти команд: загрузить задания и работы, проставить
    сохранённые разборы, достроить решения ревьюера, подтянуть даты к сегодня.
    Каждый шаг идемпотентен, поэтому повторный вызов ничего не ломает."""

    now = now or datetime.now(UTC)
    loaded = load(db, now=now)
    applied = replay(db)
    decisions = complete(db, keep_open=keep_open)
    reschedule(db, now=now)
    return {"works": loaded["created"], "reviews": applied, **decisions}


def is_loaded(db: Session) -> bool:
    return db.scalar(select(Course.id).where(Course.title == COURSE)) is not None


def _demo_titles() -> set[str]:
    from .seed import HISTORY_ASSIGNMENTS, LIVE_ASSIGNMENTS

    return {spec["title"] for spec in (*HISTORY_ASSIGNMENTS, *LIVE_ASSIGNMENTS)}


def demo_is_untouched(db: Session) -> bool:
    """В базе только демо-курс и ничего, кроме им же созданных заданий.

    Такой курс — целиком продукт сева, и заменить его настоящим можно без
    потерь. Стоит методисту завести там своё задание, и это уже чужая работа:
    вопрос о её судьбе решает человек, а не старт контейнера."""

    from .seed import COURSE_TITLE

    courses = list(db.scalars(select(Course)))
    if len(courses) != 1 or courses[0].title != COURSE_TITLE:
        return False
    titles = set(db.scalars(select(Assignment.title).where(Assignment.course_id == courses[0].id)))
    return titles <= _demo_titles()


def prepare(db: Session, *, enabled: bool = True) -> dict:
    """Что сделать с базой на старте. Решение возвращается, а не печатается.

    Наполнение — та часть запуска, про которую сложнее всего понять, почему
    «ничего не изменилось». Поэтому здесь не булев результат, а причина: её
    печатает вызывающий, и по логу видно, что именно произошло и что делать
    дальше."""

    if not enabled:
        return {"action": "skipped", "reason": "наполнение настоящим курсом выключено флагом"}
    if not RESULTS.exists():
        return {
            "action": "skipped",
            "reason": f"нет файла с разборами ({RESULTS}) — он не попал в образ?",
        }
    if is_loaded(db):
        return {"action": "kept", "reason": "настоящий курс уже загружен"}

    empty = db.scalar(select(Course.id).limit(1)) is None
    if not empty and not demo_is_untouched(db):
        return {
            "action": "kept",
            "reason": (
                "в базе есть свой курс или задания, заведённые вручную — старт их не трогает. "
                "Заменить настоящим курсом: "
                "docker compose exec api python -m scripts.load_real_course --wipe --restore"
            ),
        }
    if not empty:
        # Демо-курс целиком создан севом: заменить его — не потеря данных.
        wipe(db)
    summary = restore(db)
    return {
        "action": "loaded",
        "reason": "с нуля" if empty else "демонстрационный курс заменён настоящим",
        **summary,
    }
