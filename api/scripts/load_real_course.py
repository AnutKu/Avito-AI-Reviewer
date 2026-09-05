"""Наполнить кабинет настоящим курсом: реальные ДЗ, критерии и решения.

    python -m scripts.load_real_course --wipe            # загрузить, без оценок
    python -m scripts.load_real_course --wipe --review   # и прогнать AI-проверку
    python -m scripts.load_real_course --review-only     # догнать непроверенное

Задания и критерии берутся из `app/real_course.py`, тексты условий и решений —
из `data/real_course/` (их кладёт туда `scripts/extract_homework.py`). Ничего не
генерируется: и формулировка задания, и работа студента — это то, что реально
писали люди на курсах Авито.

`--review` вызывает ту же самую функцию, что и кабинет, когда ревьюеру
назначают работу: `review_pipeline.run_review`. Никакого отдельного «режима
демонстрации» здесь нет — если модель недоступна, работа останется без разбора
и это будет видно, а не заменится фикстурой.

`--wipe` сносит всё содержимое базы. Отдельным флагом и без значения по
умолчанию: перепутать эту команду с обычным запуском не должно быть возможности.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AiStatus,
    Assignment,
    Base,
    Course,
    Enrollment,
    Review,
    ReviewAssignment,
    ReviewerAction,
    Role,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
    User,
)
from app.real_course import TASKS  # noqa: E402
from app.services.level_agreement import LEVEL_NAMES, Work, by_task, overall  # noqa: E402
from app.services.review_pipeline import run_review  # noqa: E402

DATA = ROOT / "data" / "real_course"

# Сколько отказов подряд считать признаком недоступного сервиса, а не плохих работ.
MAX_FAILURES_IN_A_ROW = 3
RETRY_PAUSE_SECONDS = 10

COURSE = "Авито Академия: разбор реальных ДЗ"

METHODIST = ("methodist@demo.local", "Анна Воронова")
REVIEWERS = (
    ("reviewer@demo.local", "Максим Орлов"),
    ("reviewer2@demo.local", "Елена Соколова"),
    ("reviewer3@demo.local", "Игорь Ефремов"),
)

# Студенты сгруппированы по уровню работ, которые за ними закреплены. Это не
# украшение: в исходных материалах у каждого решения есть метка кейсодателя
# «слабое / среднее / хорошее», и сохранённая связь «уровень → студент» — это
# то, что позволяет потом сравнить оценку модели с этой меткой.
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


def load(db, *, now: datetime) -> int:
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
        opened = now - timedelta(days=45 - index * 3)
        deadline = opened + timedelta(days=14)
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
            submitted_at = deadline - timedelta(hours=30 + order * 7)
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
    for title in refreshed:
        print(f"  условие обновлено из файла: {title}")
    return created


def review_all(db) -> None:
    pending = list(
        db.scalars(
            select(Review.id)
            .join(Submission, Submission.id == Review.submission_id)
            .where(Review.ai_status.in_([AiStatus.PENDING, AiStatus.FAILED]))
            .order_by(Submission.submitted_at)
        )
    )
    print(f"К проверке работ: {len(pending)}")
    ok = failed = streak = 0
    for number, review_id in enumerate(pending, 1):
        # Подряд идущие отказы означают не плохие работы, а недоступный сервис
        # (так и вышло: контейнеры перезапустились посреди прогона). Продолжать
        # — значит за полминуты пометить все оставшиеся работы как «ошибка
        # проверки» и потерять понимание, какие из них вообще пробовали.
        if streak >= MAX_FAILURES_IN_A_ROW:
            left = len(pending) - number + 1
            print(
                f"\n  Прервано: {streak} отказа подряд — похоже, сервис проверки недоступен."
                f"\n  Не тронуто работ: {left}. Повторите ту же команду, когда сервис поднимется."
            )
            break
        started = time.monotonic()
        run_review(review_id)
        with SessionLocal() as fresh:
            review = fresh.get(Review, review_id)
            submission = fresh.get(Submission, review.submission_id)
            title = submission.assignment.title[:44]
            level = (
                fresh.scalar(select(Snapshot).where(Snapshot.submission_id == submission.id))
                .parsed_facts.get("expert_level")
            )
            if review.ai_status == AiStatus.READY:
                score = sum(item.ai_score or 0 for item in review.items)
                total = review.rubric_version.max_score
                ok += 1
                mark = f"{score:>5.1f} / {total:<4.0f}"
            else:
                failed += 1
                streak += 1
                mark = f"  ошибка: {(review.ai_error or '')[:40]}"
            if review.ai_status == AiStatus.READY:
                streak = 0
        print(
            f"  [{number:>2}/{len(pending)}] {time.monotonic() - started:5.1f}с "
            f"{LEVEL_NAMES.get(level, level):<8} {mark}  {title}",
            flush=True,
        )
        if streak:
            # Дать сервису шанс подняться, прежде чем списывать следующую работу.
            time.sleep(RETRY_PAUSE_SECONDS)
    print(f"\nПроверено: {ok}. С ошибкой: {failed}.")


def report(db) -> None:
    """Сравнить баллы модели с разметкой кейсодателя."""

    rows = db.execute(
        select(
            Assignment.title,
            Snapshot.parsed_facts,
            RubricVersion.max_score,
            Review.id,
        )
        .join(Submission, Submission.assignment_id == Assignment.id)
        .join(Snapshot, Snapshot.submission_id == Submission.id)
        .join(Review, Review.submission_id == Submission.id)
        .join(RubricVersion, RubricVersion.id == Review.rubric_version_id)
        .where(Review.ai_status == AiStatus.READY)
    ).all()

    works: list[Work] = []
    # У одного задания может быть два решения одного уровня (в «лабе 1» два
    # слабых). В таблице показывается среднее по ним, а в подсчёте пар каждое
    # участвует отдельно — иначе одно из них просто исчезло бы из отчёта.
    scores: dict[tuple[str, str], list[float]] = {}
    for title, facts, max_score, review_id in rows:
        review = db.get(Review, review_id)
        if not review.items or not max_score:
            continue
        percent = 100 * sum(item.ai_score or 0 for item in review.items) / max_score
        level = (facts or {}).get("expert_level", "")
        works.append(Work(task=title, level=level, percent=percent))
        scores.setdefault((title, level), []).append(percent)

    print("\nОценка модели против разметки кейсодателя\n")
    print(f"  {'задание':<44}{'слабое':>9}{'среднее':>9}{'хорошее':>9}   порядок")
    for title, agreement in sorted(by_task(works).items()):
        cells = "".join(
            f"{sum(scores[(title, level)]) / len(scores[(title, level)]):>8.0f}%"
            if (title, level) in scores
            else f"{'—':>9}"
            for level in ("weak", "medium", "strong")
        )
        verdict = "—" if agreement.share is None else f"{agreement.share:.0f}%"
        print(f"  {title[:43]:<44}{cells}   {verdict}")

    total = overall(works)
    print(
        f"\n  Пар сравнено: {total.compared}. Порядок сохранён: {total.concordant}, "
        f"нарушен: {total.discordant}, одинаковый балл: {total.ties}."
    )
    if total.share is not None:
        print(f"  Доля согласованных пар: {total.share}%.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe", action="store_true", help="снести всё содержимое базы")
    parser.add_argument("--review", action="store_true", help="прогнать AI-проверку после загрузки")
    parser.add_argument("--review-only", action="store_true", help="только догнать непроверенное")
    parser.add_argument(
        "--rerun", metavar="SLUG", help="сбросить разбор задания и проверить заново"
    )
    parser.add_argument("--report", action="store_true", help="сравнить баллы с разметкой")
    args = parser.parse_args()

    if not DATA.exists():
        print("Нет текстов ДЗ. Сначала: python -m scripts.extract_homework")
        return 1

    with SessionLocal() as db:
        if args.wipe:
            Base.metadata.create_all(bind=engine)
            wipe(db)
            print("База очищена.")
        if not args.review_only and not args.report:
            created = load(db, now=datetime.now(UTC))
            print(f"Загружено: заданий {len(TASKS)}, новых работ {created}.")
        if args.rerun:
            task = next((item for item in TASKS if item.slug == args.rerun), None)
            if task is None:
                print(f"Нет такого задания: {args.rerun}")
                return 1
            reviews = db.scalars(
                select(Review)
                .join(Submission, Submission.id == Review.submission_id)
                .join(Assignment, Assignment.id == Submission.assignment_id)
                .where(Assignment.title == task.title)
            )
            count = 0
            for review in reviews:
                review.ai_status = AiStatus.PENDING
                count += 1
            db.commit()
            print(f"Сброшено разборов: {count} по заданию «{task.title}».")
        if args.review or args.review_only or args.rerun:
            review_all(db)
        if args.report or args.review or args.review_only:
            report(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
