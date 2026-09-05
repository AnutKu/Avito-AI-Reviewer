"""Образовательный долг курса: где он теряет качество.

Идея простая: у каждого потока накапливаются места, которые «пока работают», но
уже подтачивают результат — тема, которую стабильно не понимают; задание, на
котором все спотыкаются об одно и то же; критерий, который ревьюеры каждый раз
переписывают руками. Поодиночке это шум, вместе — долг, который заплатит
следующий поток.

**Главное правило модуля: не говорить того, чего не видно в данных.** Каждый
вывод считается по живым записям и снабжён порогом наблюдений; там, где
наблюдений мало, вывод не делается вовсе. Низкий процент по двум работам и
низкий процент по тридцати выглядят одинаково, и показать первый как второй
значит соврать.

Градаций важности здесь нет намеренно. Если признак прошёл порог и попал в
список — им уже стоит заняться; делить попавшее на «важно» и «присмотреться»
значит давать повод отложить половину. Порядок задаёт сам вид признака: сначала
то, что бьёт по обучению, потом то, что бьёт по оценке.

Два пункта из продуктовой формулировки названы здесь иначе, чем в брифе, — и
это осознанно:

* «материалы, после которых растут вопросы» — учебных материалов кабинет не
  хранит и о лекциях ничего не знает. Зато он знает, после каких заданий
  ревьюер реально отправлял студенту дополнительные вопросы. Это измеримая
  часть того же сигнала — и только она: сигнал `understanding_risk` из AI-ревью
  сюда НЕ входит, хотя соблазн был. Он говорит «похоже, студент не понимает,
  что сдал» — это суждение о конкретной работе, а не о ясности задания, и
  смешивать их значит выдавать за «пришлось уточнять» то, чего никто не делал;
* «задания, не соответствующие программе» — программы у системы нет. Есть
  признаки того, что задание перестало работать: рубрику давно не трогали,
  прогон агентов оставил незакрытые критичные замечания, критерий перестал
  различать сильных и слабых. Об этом и говорим, не выдавая догадку за знание.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    AiRecommendation,
    AiRun,
    Assignment,
    BlitzSession,
    Review,
    RubricVersion,
    Submission,
)
from .analytics import (
    CORRECTED_ACTIONS,
    DECIDED_ACTIONS,
    ItemFact,
    WorkFact,
    collect_items,
    collect_works,
    published_assignments,
    share,
)

# Пороги. Вынесены наверх, потому что это не детали реализации, а решение о
# том, с какого объёма наблюдений мы вообще имеем право делать вывод.
MIN_WORKS_PER_TOPIC = 5      # тема: меньше — это не «массово», а совпадение
MIN_REVIEWS_PER_CRITERION = 4  # критерий: на трёх работах доля ничего не значит
FAIL_SHARE = 40              # % работ ниже половины балла — «спотыкаются все»
CORRECTION_SHARE = 40        # % решений, где ревьюер переписал оценку AI
QUESTION_SHARE = 30          # % работ, после которых пришлось переспрашивать
STALE_DAYS = 120             # рубрику не трогали столько дней, а работы идут
SPREAD_EPSILON = 0.01        # балл по критерию одинаков у всех — не различает

# Порядок показа. Сначала то, что мешает студенту учиться, потом то, что мешает
# честно оценить, и только потом состояние самого задания.
KIND_ORDER = ("topic", "repeated_error", "questions", "criterion_corrections", "stale_task")


@dataclass(frozen=True)
class TaskFact:
    """Задание глазами долга: не «сколько сдали», а «что с ним не так»."""

    id: UUID
    title: str
    topic: str
    published_at: datetime | None
    rubric_updated_at: datetime | None
    works: int = 0
    questioned: int = 0        # работ, по которым ревьюер отправил доп. вопросы
    open_findings: int = 0     # незакрытые критичные рекомендации AI-прогона
    last_run_at: datetime | None = None
    criteria: list = field(default_factory=list)


def _pct(part: float, whole: float) -> float:
    return share(part, whole) or 0.0


def _item(
    kind: str,
    *,
    title: str,
    detail: str,
    evidence: str,
    action: str,
    metric: float | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "kind": kind,
        "title": title,
        "detail": detail,
        "evidence": evidence,
        "action": action,
        "metric": metric,
        # Куда идти чинить. Экран делает из этого кнопку — как из рекомендации
        # AI-прогона: вывод без пути к правке заставляет искать задание руками.
        "target": target or {},
    }


# --------------------------------------------------------------------------- #
#  Сигналы
# --------------------------------------------------------------------------- #


def topic_gaps(works: list[WorkFact], tasks: dict[UUID, TaskFact]) -> list[dict]:
    """Темы, которые массово не понимают.

    Считается по доле незачётов среди ПРОВЕРЕННЫХ работ темы: незавершённая
    работа ничего не говорит о понимании. Тема без указанной темы в задании в
    расчёт не идёт — иначе всё сваливается в одну кучу «без темы».
    """

    graded: dict[str, list[WorkFact]] = defaultdict(list)
    for work in works:
        if work.passed is None:
            continue
        task = tasks.get(work.assignment_id)
        topic = (task.topic if task else "").strip()
        # Задание без темы в разбор по темам не попадает: иначе всё сваливается
        # в одну кучу «без темы», и вывод получается ни о чём.
        if topic:
            graded[topic].append(work)

    rows = []
    for topic, items in sorted(graded.items()):
        if len(items) < MIN_WORKS_PER_TOPIC:
            continue
        failed = [work for work in items if work.passed is False]
        share = _pct(len(failed), len(items))
        if share < FAIL_SHARE:
            continue
        rows.append(
            _item(
                "topic",
                title=f"Тема «{topic}» не усваивается",
                detail=f"Не получают зачёт {round(share)}% проверенных работ по теме.",
                evidence=f"{len(failed)} из {len(items)} работ ниже проходного балла.",
                action="Посмотрите, чего не хватает в объяснении темы до выдачи задания.",
                metric=round(share),
                target={"topic": topic},
            )
        )
    return rows


def repeated_errors(
    items: list[ItemFact], tasks: dict[UUID, TaskFact]
) -> list[dict]:
    """Задания, на которых все спотыкаются об одно и то же.

    «Одинаковая ошибка» здесь — один и тот же критерий, проваленный многими.
    Провал считается по итоговой оценке ревьюера (а не AI) и по половине
    максимума: ноль ставят редко, а «меньше половины» — это уже не придирка.
    """

    buckets: dict[tuple[UUID, str], list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.assignment_id and item.final_score is not None:
            buckets[(item.assignment_id, item.criterion_key)].append(item)

    rows = []
    for (assignment_id, key), group in buckets.items():
        if len(group) < MIN_REVIEWS_PER_CRITERION:
            continue
        failed = [x for x in group if x.max_score and x.final_score < x.max_score / 2]
        share = _pct(len(failed), len(group))
        if share < FAIL_SHARE:
            continue
        task = tasks.get(assignment_id)
        title = group[0].criterion_title or key
        rows.append(
            _item(
                "repeated_error",
                title=f"«{title}» проваливают почти все",
                detail=f"{round(share)}% работ по заданию «{task.title if task else '—'}» "
                "получают меньше половины балла по этому критерию.",
                evidence=f"{len(failed)} из {len(group)} проверенных работ.",
                action="Либо это пробел в обучении, либо требование не объяснено в условии — "
                "проверьте задание на AI-студентах.",
                metric=round(share),
                target={"assignment_id": str(assignment_id), "criterion_key": key},
            )
        )
    return rows


def manual_corrections(
    items: list[ItemFact], tasks: dict[UUID, TaskFact]
) -> list[dict]:
    """Критерии, которые ревьюер каждый раз переписывает руками.

    Высокая доля правок — не про плохой AI, а про формулировку, по которой два
    человека не сходятся. Это и есть кандидат на уточнение.
    """

    buckets: dict[tuple[UUID, str], list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.assignment_id and item.action in DECIDED_ACTIONS:
            buckets[(item.assignment_id, item.criterion_key)].append(item)

    rows = []
    for (assignment_id, key), group in buckets.items():
        if len(group) < MIN_REVIEWS_PER_CRITERION:
            continue
        corrected = [x for x in group if x.action in CORRECTED_ACTIONS]
        share = _pct(len(corrected), len(group))
        if share < CORRECTION_SHARE:
            continue
        task = tasks.get(assignment_id)
        title = group[0].criterion_title or key
        rows.append(
            _item(
                "criterion_corrections",
                title=f"«{title}» ревьюеры переписывают",
                detail=f"В {round(share)}% решений оценка AI по этому критерию исправлена вручную "
                f"(задание «{task.title if task else '—'}»).",
                evidence=f"{len(corrected)} правок из {len(group)} решений.",
                action="Уточните формулировку и пороги критерия — по ней не сходятся даже двое.",
                metric=round(share),
                target={"assignment_id": str(assignment_id), "criterion_key": key},
            )
        )
    return rows


def question_hotspots(tasks: dict[UUID, TaskFact]) -> list[dict]:
    """Задания, после которых ревьюер вынужден переспрашивать студента.

    Считается по одному факту: отправленному блиц-опросу. Это действие живого
    человека, и только оно даёт право написать «пришлось уточнять». Учебных
    материалов система не хранит и анализировать их не может; это ближайшее,
    что она о них знает.
    """

    rows = []
    for task in tasks.values():
        if task.works < MIN_WORKS_PER_TOPIC or not task.questioned:
            continue
        share = _pct(task.questioned, task.works)
        if share < QUESTION_SHARE:
            continue
        rows.append(
            _item(
                "questions",
                title=f"«{task.title}»: студентов приходится переспрашивать",
                detail=f"По {round(share)}% работ ревьюер отправлял студенту дополнительные "
                "вопросы — обычно так делают, когда по решению неясно, понял ли студент задание.",
                evidence=f"Дополнительные вопросы отправлены по {task.questioned} из {task.works} работ.",
                action="Проверьте, что материалы перед этим заданием закрывают то, "
                "что оно требует, и что условие не оставляет догадок.",
                metric=round(share),
                target={"assignment_id": str(task.id)},
            )
        )
    return rows


def stale_tasks(
    tasks: dict[UUID, TaskFact], items: list[ItemFact], now: datetime | None = None
) -> list[dict]:
    """Задания, которые пора пересмотреть.

    Соответствие программе система проверить не может — программы у неё нет.
    Зато видно три признака того, что задание перестало работать: рубрику давно
    не трогали, прогон агентов оставил незакрытые критичные замечания, критерий
    перестал различать сильных и слабых. Каждый признак назван явно, чтобы
    методист решал сам, а не верил ярлыку «устарело».
    """

    now = now or datetime.now(UTC)
    # Критерий, по которому все получили одинаковый балл, ничего не измеряет.
    scores: dict[tuple[UUID, str], set[float]] = defaultdict(set)
    titles: dict[tuple[UUID, str], str] = {}
    for item in items:
        if item.assignment_id and item.final_score is not None:
            scores[(item.assignment_id, item.criterion_key)].add(round(item.final_score, 2))
            titles[(item.assignment_id, item.criterion_key)] = item.criterion_title or item.criterion_key
    flat: dict[UUID, list[str]] = defaultdict(list)
    counts: dict[tuple[UUID, str], int] = defaultdict(int)
    for item in items:
        if item.assignment_id and item.final_score is not None:
            counts[(item.assignment_id, item.criterion_key)] += 1
    for key, values in scores.items():
        if len(values) == 1 and counts[key] >= MIN_REVIEWS_PER_CRITERION:
            flat[key[0]].append(titles[key])

    rows = []
    for task in tasks.values():
        reasons = []
        stamp = task.rubric_updated_at or task.published_at
        age = (now - stamp).days if stamp else None
        if age is not None and age >= STALE_DAYS and task.works:
            reasons.append(f"рубрику не меняли {age} дней, а работы по заданию идут")
        if task.open_findings:
            reasons.append(f"незакрытых критичных замечаний прогона: {task.open_findings}")
        if flat.get(task.id):
            listed = ", ".join(f"«{name}»" for name in sorted(flat[task.id])[:3])
            reasons.append(f"критерии не различают работы: {listed}")
        if not reasons:
            continue
        rows.append(
            _item(
                "stale_task",
                title=f"«{task.title}» пора пересмотреть",
                detail="; ".join(reasons).capitalize() + ".",
                evidence=f"Работ по заданию: {task.works}."
                + (f" Последний прогон агентов: {task.last_run_at:%d.%m.%Y}." if task.last_run_at else ""),
                action="Откройте задание в банке и прогоните его на AI-персонах — "
                "разбор скажет, что именно перестало работать.",
                metric=len(reasons),
                target={"assignment_id": str(task.id)},
            )
        )
    return rows


def build_debt(
    works: list[WorkFact], items: list[ItemFact], tasks: dict[UUID, TaskFact], now: datetime | None = None
) -> dict:
    """Все сигналы разом, в порядке от «мешает учиться» к «мешает оценивать»."""

    now = now or datetime.now(UTC)
    rows = []
    for signal in (
        topic_gaps(works, tasks),
        repeated_errors(items, tasks),
        manual_corrections(items, tasks),
        question_hotspots(tasks),
        stale_tasks(tasks, items, now),
    ):
        rows.extend(signal)

    order = {kind: index for index, kind in enumerate(KIND_ORDER)}
    rows.sort(key=lambda row: (order.get(row["kind"], 99), -(row["metric"] or 0)))
    graded = [work for work in works if work.passed is not None]
    return {
        "items": rows,
        "coverage": {
            "works": len(works),
            "graded": len(graded),
            "tasks": len(tasks),
            # Без проверенных работ считать нечего, и это надо сказать прямо, а
            # не показывать пустой экран как «долга нет».
            "enough": len(graded) >= MIN_WORKS_PER_TOPIC,
        },
        # Кэша нет: цифры пересчитываются на каждый запрос экрана. Методист
        # должен знать, на какой момент он смотрит, — иначе непонятно, отражает
        # ли список работу, проверенную минуту назад.
        "computed_at": now.isoformat(),
    }


# --------------------------------------------------------------------------- #
#  Адаптер: сбор фактов из базы
# --------------------------------------------------------------------------- #


def collect_tasks(db: Session, assignments: list[Assignment]) -> dict[UUID, TaskFact]:
    if not assignments:
        return {}
    ids = [assignment.id for assignment in assignments]

    works = dict(
        db.execute(
            select(Submission.assignment_id, func.count())
            .where(Submission.assignment_id.in_(ids))
            .group_by(Submission.assignment_id)
        ).all()
    )
    questioned = dict(
        db.execute(
            select(Submission.assignment_id, func.count(func.distinct(Submission.id)))
            .join(Review, Review.submission_id == Submission.id)
            .join(BlitzSession, BlitzSession.review_id == Review.id)
            .where(Submission.assignment_id.in_(ids), BlitzSession.sent_at.is_not(None))
            .group_by(Submission.assignment_id)
        ).all()
    )
    findings = dict(
        db.execute(
            select(AiRun.assignment_id, func.count())
            .join(AiRecommendation, AiRecommendation.run_id == AiRun.id)
            .where(
                AiRun.assignment_id.in_(ids),
                AiRecommendation.status == "new",
                AiRecommendation.severity == "critical",
            )
            .group_by(AiRun.assignment_id)
        ).all()
    )
    last_run = dict(
        db.execute(
            select(AiRun.assignment_id, func.max(AiRun.completed_at))
            .where(AiRun.assignment_id.in_(ids))
            .group_by(AiRun.assignment_id)
        ).all()
    )
    rubric_at = dict(
        db.execute(
            select(RubricVersion.assignment_id, func.max(RubricVersion.published_at))
            .where(RubricVersion.assignment_id.in_(ids))
            .group_by(RubricVersion.assignment_id)
        ).all()
    )

    return {
        assignment.id: TaskFact(
            id=assignment.id,
            title=assignment.title,
            topic=str((assignment.authoring or {}).get("topic") or "").strip(),
            published_at=assignment.published_at,
            rubric_updated_at=rubric_at.get(assignment.id),
            works=works.get(assignment.id, 0),
            questioned=questioned.get(assignment.id, 0),
            open_findings=findings.get(assignment.id, 0),
            last_run_at=last_run.get(assignment.id),
        )
        for assignment in assignments
    }


def debt_report(db: Session, course_id: UUID | None = None) -> dict:
    assignments = published_assignments(db, course_id)
    return build_debt(
        collect_works(db, assignments),
        collect_items(db, assignments),
        collect_tasks(db, assignments),
    )
