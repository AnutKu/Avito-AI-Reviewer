"""Образовательный долг курса: где он теряет качество.

Идея простая: у каждого потока накапливаются места, которые «пока работают», но
уже подтачивают результат — тема, которую стабильно не понимают; задание, на
котором все спотыкаются об одно и то же; критерий, который ревьюеры каждый раз
переписывают руками. Поодиночке это шум, вместе — долг, который заплатит
следующий поток.

**Главное правило модуля: не говорить того, чего не видно в данных.** Каждый
вывод считается по живым записям и снабжён порогом наблюдений; там, где
наблюдений мало, вывод не делается вовсе — вместо него честная строка «данных
пока мало». Низкий процент по двум работам и низкий процент по тридцати
выглядят одинаково, и показать первый как второй значит соврать.

Два пункта из продуктовой формулировки названы здесь иначе, чем в брифе, — и
это осознанно:

* «материалы, после которых растут вопросы» — учебных материалов кабинет не
  хранит и о лекциях ничего не знает. Зато он знает, после каких заданий
  ревьюер чаще всего вынужден переспрашивать студента (блиц) и где AI отмечает
  риск непонимания. Это и есть измеримая часть того же сигнала;
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
    AiSignal,
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

SEVERITY_ORDER = {"critical": 0, "important": 1, "watch": 2}


@dataclass(frozen=True)
class TaskFact:
    """Задание глазами долга: не «сколько сдали», а «что с ним не так»."""

    id: UUID
    title: str
    topic: str
    published_at: datetime | None
    rubric_updated_at: datetime | None
    works: int = 0
    questioned: int = 0        # работ, по которым пришлось задать доп. вопросы
    risk_flagged: int = 0      # работ, где AI отметил риск непонимания
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
    severity: str,
    metric: float | None = None,
    target: dict | None = None,
) -> dict:
    return {
        "kind": kind,
        "title": title,
        "detail": detail,
        "evidence": evidence,
        "action": action,
        "severity": severity,
        "metric": metric,
        "target": target or {},
    }


# --------------------------------------------------------------------------- #
#  Сигналы
# --------------------------------------------------------------------------- #


def topic_gaps(works: list[WorkFact], tasks: dict[UUID, TaskFact]) -> tuple[list[dict], list[str]]:
    """Темы, которые массово не понимают.

    Считается по доле незачётов среди ПРОВЕРЕННЫХ работ темы: незавершённая
    работа ничего не говорит о понимании. Тема без указанной темы в задании в
    расчёт не идёт — иначе всё сваливается в одну кучу «без темы».
    """

    graded: dict[str, list[WorkFact]] = defaultdict(list)
    untagged = 0
    for work in works:
        if work.passed is None:
            continue
        task = tasks.get(work.assignment_id)
        topic = (task.topic if task else "").strip()
        if not topic:
            untagged += 1
            continue
        graded[topic].append(work)

    rows, notes = [], []
    if untagged:
        notes.append(
            f"У {untagged} проверенных работ не указана тема задания — они в разбор по темам не вошли."
        )
    for topic, items in sorted(graded.items()):
        if len(items) < MIN_WORKS_PER_TOPIC:
            notes.append(f"«{topic}»: проверенных работ {len(items)} — для вывода о теме мало.")
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
                severity="critical" if share >= 60 else "important",
                metric=round(share),
                target={"topic": topic},
            )
        )
    return rows, notes


def repeated_errors(
    items: list[ItemFact], tasks: dict[UUID, TaskFact]
) -> tuple[list[dict], list[str]]:
    """Задания, на которых все спотыкаются об одно и то же.

    «Одинаковая ошибка» здесь — один и тот же критерий, проваленный многими.
    Провал считается по итоговой оценке ревьюера (а не AI) и по половине
    максимума: ноль ставят редко, а «меньше половины» — это уже не придирка.
    """

    buckets: dict[tuple[UUID, str], list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.assignment_id and item.final_score is not None:
            buckets[(item.assignment_id, item.criterion_key)].append(item)

    rows, notes = [], []
    thin = 0
    for (assignment_id, key), group in buckets.items():
        if len(group) < MIN_REVIEWS_PER_CRITERION:
            thin += 1
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
                severity="critical" if share >= 70 else "important",
                metric=round(share),
                target={"assignment_id": str(assignment_id), "criterion_key": key},
            )
        )
    if thin:
        notes.append(
            f"Ещё {thin} критериев проверены меньше {MIN_REVIEWS_PER_CRITERION} раз — их не считали."
        )
    return rows, notes


def manual_corrections(
    items: list[ItemFact], tasks: dict[UUID, TaskFact]
) -> tuple[list[dict], list[str]]:
    """Критерии, которые ревьюер каждый раз переписывает руками.

    Высокая доля правок — не про плохой AI, а про формулировку, по которой два
    человека не сходятся. Это и есть кандидат на уточнение.
    """

    buckets: dict[tuple[UUID, str], list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.assignment_id and item.action in DECIDED_ACTIONS:
            buckets[(item.assignment_id, item.criterion_key)].append(item)

    rows, notes = [], []
    thin = 0
    for (assignment_id, key), group in buckets.items():
        if len(group) < MIN_REVIEWS_PER_CRITERION:
            thin += 1
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
                severity="important" if share >= 60 else "watch",
                metric=round(share),
                target={"assignment_id": str(assignment_id), "criterion_key": key},
            )
        )
    if thin:
        notes.append(
            f"Ещё {thin} критериев решены меньше {MIN_REVIEWS_PER_CRITERION} раз — их не считали."
        )
    return rows, notes


def question_hotspots(tasks: dict[UUID, TaskFact]) -> tuple[list[dict], list[str]]:
    """Задания, после которых чаще всего приходится переспрашивать.

    Ближайшее, что кабинет знает о «материалах, после которых растут вопросы»:
    доля работ, по которым ревьюер отправлял дополнительные вопросы или AI
    отмечал риск непонимания. Учебных материалов система не хранит, и делать
    вид, что она их анализирует, — значит выдумывать.
    """

    rows, notes = [], []
    thin = 0
    for task in tasks.values():
        if task.works < MIN_WORKS_PER_TOPIC:
            thin += 1
            continue
        flagged = max(task.questioned, task.risk_flagged)
        share = _pct(flagged, task.works)
        if share < QUESTION_SHARE:
            continue
        parts = []
        if task.questioned:
            parts.append(f"доп. вопросы по {task.questioned} работам")
        if task.risk_flagged:
            parts.append(f"риск непонимания у {task.risk_flagged}")
        rows.append(
            _item(
                "questions",
                title=f"«{task.title}» вызывает вопросы",
                detail=f"По {round(share)}% работ пришлось уточнять, понял ли студент задание.",
                evidence="; ".join(parts) + f" из {task.works} работ.",
                action="Проверьте, что материалы перед этим заданием закрывают то, "
                "что оно требует, и что условие не оставляет догадок.",
                severity="important" if share >= 50 else "watch",
                metric=round(share),
                target={"assignment_id": str(task.id)},
            )
        )
    if thin:
        notes.append(f"Ещё {thin} заданий собрали меньше {MIN_WORKS_PER_TOPIC} работ — их не считали.")
    return rows, notes


def stale_tasks(
    tasks: dict[UUID, TaskFact], items: list[ItemFact], now: datetime | None = None
) -> tuple[list[dict], list[str]]:
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

    rows, notes = [], []
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
                severity="important" if len(reasons) > 1 else "watch",
                metric=len(reasons),
                target={"assignment_id": str(task.id)},
            )
        )
    return rows, notes


def build_debt(
    works: list[WorkFact], items: list[ItemFact], tasks: dict[UUID, TaskFact], now: datetime | None = None
) -> dict:
    """Все сигналы разом: список долгов и честный список того, что не считали."""

    rows, notes = [], []
    for signal in (
        topic_gaps(works, tasks),
        repeated_errors(items, tasks),
        manual_corrections(items, tasks),
        question_hotspots(tasks),
        stale_tasks(tasks, items, now),
    ):
        rows.extend(signal[0])
        notes.extend(signal[1])

    rows.sort(key=lambda row: (SEVERITY_ORDER.get(row["severity"], 9), -(row["metric"] or 0)))
    counts = {"critical": 0, "important": 0, "watch": 0}
    for row in rows:
        counts[row["severity"]] = counts.get(row["severity"], 0) + 1
    graded = [work for work in works if work.passed is not None]
    return {
        "items": rows,
        "counts": counts,
        "notes": notes,
        "coverage": {
            "works": len(works),
            "graded": len(graded),
            "tasks": len(tasks),
            # Без проверенных работ считать нечего, и это надо сказать прямо, а
            # не показывать пустой экран как «долга нет».
            "enough": len(graded) >= MIN_WORKS_PER_TOPIC,
        },
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
    risky = dict(
        db.execute(
            select(Submission.assignment_id, func.count(func.distinct(Submission.id)))
            .join(Review, Review.submission_id == Submission.id)
            .join(AiSignal, AiSignal.review_id == Review.id)
            .where(
                Submission.assignment_id.in_(ids),
                AiSignal.kind == "understanding_risk",
                AiSignal.level.in_(("high", "medium")),
            )
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
            risk_flagged=risky.get(assignment.id, 0),
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
