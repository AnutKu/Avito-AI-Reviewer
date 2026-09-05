"""Аналитика кабинета методиста.

Все цифры считаются по живым записям (`submissions`, `reviews`, `review_items`,
`review_assignments`) — фикстур в расчётах нет. Ядро — чистые функции над
плоскими фактами `WorkFact` / `ItemFact`: формулы покрыты юнит-тестами без БД.
Ниже — тонкие адаптеры, которые собирают факты запросами и отдают готовые
структуры роутеру.

Источники метрик:
* время до проверки — `submissions.submitted_at → reviews.completed_at`;
* время самой проверки — `review_assignments.approved_at → reviews.completed_at`;
* согласие AI и ревьюера — `review_items.reviewer_action` (единственный
  источник данных о правках, см. `ReviewerAction`);
* зачёт — `reviews.final_score >= rubric_versions.pass_score` той версии
  рубрики, по которой работа реально проверялась.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from ..models import (
    Assignment,
    Course,
    Enrollment,
    Review,
    ReviewAssignment,
    ReviewerAction,
    ReviewItem,
    Role,
    RubricVersion,
    Submission,
    SubmissionStatus,
    User,
)
from ..serializers import iso
from .distribution import reviewer_loads

# Ревьюер принял решение по критерию — только такие строки идут в статистику правок.
DECIDED_ACTIONS = frozenset(
    {ReviewerAction.ACCEPTED, ReviewerAction.CHANGED, ReviewerAction.REJECTED}
)
# Решение разошлось с AI.
CORRECTED_ACTIONS = frozenset({ReviewerAction.CHANGED, ReviewerAction.REJECTED})
# Работа сдана, но ещё не дошла до ревьюера.
WAITING_STATUSES = frozenset({SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED})

DEFAULT_WEEKS = 6


# --------------------------------------------------------------------------- #
# Факты
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class WorkFact:
    """Одна сданная работа со всем, что нужно аналитике."""

    submission_id: UUID
    assignment_id: UUID
    student_id: UUID
    status: str
    is_overdue: bool
    submitted_at: datetime
    assigned_at: datetime | None
    completed_at: datetime | None
    final_score: float | None
    max_score: float
    pass_score: float
    ai_status: str
    reviewer_id: UUID | None = None      # активное назначение
    completed_by: UUID | None = None     # кто фактически завершил
    reviewer_name: str | None = None
    is_demo: bool = False

    @property
    def owner_id(self) -> UUID | None:
        """Кому засчитывается работа: завершивший важнее назначенного."""

        return self.completed_by or self.reviewer_id

    @property
    def is_completed(self) -> bool:
        return self.status == SubmissionStatus.COMPLETED

    @property
    def lead_hours(self) -> float | None:
        """От сдачи студентом до готового результата."""

        return _hours(self.submitted_at, self.completed_at)

    @property
    def review_hours(self) -> float | None:
        """От назначения ревьюеру до завершения — время самой проверки."""

        return _hours(self.assigned_at, self.completed_at)

    @property
    def percent(self) -> float | None:
        if self.final_score is None or not self.max_score:
            return None
        return round(self.final_score / self.max_score * 100, 1)

    @property
    def passed(self) -> bool | None:
        if self.final_score is None:
            return None
        return self.final_score >= self.pass_score


@dataclass(frozen=True)
class ItemFact:
    """Строка рубрики после решения ревьюера."""

    criterion_key: str
    criterion_title: str
    max_score: float
    ai_score: float
    final_score: float | None
    action: str
    reviewer_id: UUID | None = None
    completed_at: datetime | None = None
    # Нужен разбору образовательного долга: там вопрос не «как критерий ведёт
    # себя на курсе», а «что происходит с ним внутри конкретного задания».
    assignment_id: UUID | None = None


@dataclass(frozen=True)
class StudentRef:
    id: UUID
    name: str


@dataclass(frozen=True)
class AssignmentRef:
    id: UUID
    title: str
    max_score: float
    pass_score: float
    deadline_at: datetime | None


# --------------------------------------------------------------------------- #
# Мелкие помощники
# --------------------------------------------------------------------------- #


def _hours(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    delta = (end - start).total_seconds() / 3600
    return round(delta, 1) if delta >= 0 else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[mid], 1)
    return round((ordered[mid - 1] + ordered[mid]) / 2, 1)


def share(part: float, whole: float) -> float:
    """Доля в процентах. Ноль знаменателя — это 0%, а не деление на ноль."""

    return round(part / whole * 100, 1) if whole else 0.0


def _delta_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def week_start(moment: datetime) -> datetime:
    """Понедельник недели, к которой относится момент (UTC)."""

    day = moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


# --------------------------------------------------------------------------- #
# Чистое ядро
# --------------------------------------------------------------------------- #


def agreement(items: list[ItemFact]) -> dict:
    """Насколько ревьюеры соглашаются с оценкой AI по критериям."""

    decided = [item for item in items if item.action in DECIDED_ACTIONS]
    accepted = sum(1 for item in decided if item.action == ReviewerAction.ACCEPTED)
    changed = sum(1 for item in decided if item.action == ReviewerAction.CHANGED)
    rejected = sum(1 for item in decided if item.action == ReviewerAction.REJECTED)
    scored = [
        (item.ai_score, item.final_score)
        for item in decided
        if item.final_score is not None
    ]
    avg_ai = _mean([ai for ai, _ in scored])
    avg_final = _mean([final for _, final in scored])
    return {
        "decided": len(decided),
        "accepted": accepted,
        "changed": changed,
        "rejected": rejected,
        "rate": share(accepted, len(decided)),
        "avg_ai": avg_ai,
        "avg_final": avg_final,
        # >0 — ревьюеры в среднем добавляют баллы, <0 — AI завышает.
        "delta": None if avg_ai is None else round(avg_final - avg_ai, 1),
    }


def overview(
    works: list[WorkFact],
    items: list[ItemFact],
    *,
    expected: int,
    students: int,
    assignments: int,
    now: datetime,
) -> dict:
    """Верхние метрики потока: объём, сроки, качество."""

    completed = [work for work in works if work.is_completed]
    lead = [work.lead_hours for work in works if work.lead_hours is not None]
    review = [work.review_hours for work in works if work.review_hours is not None]
    scores = [work.final_score for work in completed if work.final_score is not None]
    percents = [work.percent for work in completed if work.percent is not None]
    verdicts = [work.passed for work in completed if work.passed is not None]

    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)
    recent = [w for w in completed if w.completed_at and w.completed_at >= week_ago]
    previous = [
        w
        for w in completed
        if w.completed_at and two_weeks_ago <= w.completed_at < week_ago
    ]
    lead_recent = _mean([w.lead_hours for w in recent if w.lead_hours is not None])
    lead_previous = _mean([w.lead_hours for w in previous if w.lead_hours is not None])

    return {
        "students": students,
        "assignments": assignments,
        "expected": expected,
        "submitted": len(works),
        "submission_rate": share(len(works), expected),
        "completed": len(completed),
        "in_progress": sum(
            1
            for work in works
            if not work.is_completed and work.status not in WAITING_STATUSES
        ),
        "waiting": sum(1 for work in works if work.status in WAITING_STATUSES),
        "not_submitted": max(0, expected - len(works)),
        "overdue": sum(1 for work in works if work.is_overdue),
        "avg_lead_hours": _mean(lead),
        "median_lead_hours": _median(lead),
        "avg_review_hours": _mean(review),
        "avg_score": _mean(scores),
        "avg_percent": _mean(percents),
        "pass_rate": share(sum(verdicts), len(verdicts)),
        "ai_agreement": agreement(items)["rate"],
        "completed_7d": len(recent),
        "completed_prev_7d": len(previous),
        "completed_delta": len(recent) - len(previous),
        "lead_7d": lead_recent,
        "lead_prev_7d": lead_previous,
        "lead_delta_pct": _delta_pct(lead_recent, lead_previous),
        "ai_failed": sum(1 for work in works if work.ai_status == "failed"),
    }


def funnel(works: list[WorkFact]) -> list[dict]:
    """Воронка по статусам — в порядке автомата, включая нулевые ступени."""

    counts: dict[str, int] = defaultdict(int)
    for work in works:
        counts[work.status] += 1
    total = len(works)
    return [
        {"status": status, "count": counts.get(status, 0), "share": share(counts.get(status, 0), total)}
        for status in SubmissionStatus
    ]


def weekly(
    works: list[WorkFact],
    items: list[ItemFact],
    *,
    now: datetime,
    weeks: int = DEFAULT_WEEKS,
) -> list[dict]:
    """Динамика по неделям. Пустые недели остаются в ряду — иначе график врёт."""

    first = week_start(now) - timedelta(weeks=weeks - 1)
    keys = [first + timedelta(weeks=index) for index in range(weeks)]
    known = set(keys)
    submitted: dict[datetime, int] = defaultdict(int)
    completed: dict[datetime, int] = defaultdict(int)
    lead: dict[datetime, list[float]] = defaultdict(list)
    decided: dict[datetime, int] = defaultdict(int)
    accepted: dict[datetime, int] = defaultdict(int)

    for work in works:
        bucket = week_start(work.submitted_at)
        if bucket in known:
            submitted[bucket] += 1
        if work.completed_at:
            bucket = week_start(work.completed_at)
            if bucket in known:
                completed[bucket] += 1
                if work.lead_hours is not None:
                    lead[bucket].append(work.lead_hours)

    for item in items:
        if item.action not in DECIDED_ACTIONS or not item.completed_at:
            continue
        bucket = week_start(item.completed_at)
        if bucket not in known:
            continue
        decided[bucket] += 1
        accepted[bucket] += item.action == ReviewerAction.ACCEPTED

    return [
        {
            "week_start": iso(key),
            "submitted": submitted[key],
            "completed": completed[key],
            "avg_lead_hours": _mean(lead[key]),
            "decided": decided[key],
            "agreement": share(accepted[key], decided[key]) if decided[key] else None,
        }
        for key in keys
    ]


def criteria_report(items: list[ItemFact]) -> list[dict]:
    """Критерии, которые ревьюеры правят чаще всего, — кандидаты на переформулировку."""

    groups: dict[str, list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.action in DECIDED_ACTIONS:
            groups[item.criterion_key or item.criterion_title].append(item)

    rows = []
    for key, group in groups.items():
        changed = sum(1 for item in group if item.action in CORRECTED_ACTIONS)
        finals = [item.final_score for item in group if item.final_score is not None]
        ai_scores = [item.ai_score for item in group if item.final_score is not None]
        avg_final, avg_ai = _mean(finals), _mean(ai_scores)
        max_score = max(item.max_score for item in group)
        rows.append(
            {
                "key": key,
                "title": group[0].criterion_title,
                "reviews": len(group),
                "changed": sum(1 for item in group if item.action == ReviewerAction.CHANGED),
                "rejected": sum(1 for item in group if item.action == ReviewerAction.REJECTED),
                "correction_rate": share(changed, len(group)),
                "max_score": max_score,
                "avg_ai": avg_ai,
                "avg_final": avg_final,
                "delta": None if avg_ai is None else round(avg_final - avg_ai, 1),
                "avg_percent": None if avg_final is None else share(avg_final, max_score),
            }
        )
    rows.sort(key=lambda row: (-row["correction_rate"], -row["reviews"], row["title"]))
    return rows


def reviewer_report(
    works: list[WorkFact], items: list[ItemFact], loads: list[dict]
) -> list[dict]:
    """Производительность ревьюеров поверх их текущей нагрузки."""

    done: dict[str, list[WorkFact]] = defaultdict(list)
    for work in works:
        if work.is_completed and work.owner_id:
            done[str(work.owner_id)].append(work)
    by_reviewer: dict[str, list[ItemFact]] = defaultdict(list)
    for item in items:
        if item.reviewer_id:
            by_reviewer[str(item.reviewer_id)].append(item)

    rows = []
    for load in loads:
        mine = done.get(load["id"], [])
        rows.append(
            {
                **load,
                "completed": len(mine),
                "avg_review_hours": _mean(
                    [work.review_hours for work in mine if work.review_hours is not None]
                ),
                "avg_percent": _mean(
                    [work.percent for work in mine if work.percent is not None]
                ),
                "agreement": agreement(by_reviewer.get(load["id"], []))["rate"],
                "decided": len(
                    [
                        item
                        for item in by_reviewer.get(load["id"], [])
                        if item.action in DECIDED_ACTIONS
                    ]
                ),
            }
        )
    rows.sort(key=lambda row: (-row["completed"], row["name"]))
    return rows


def _cell(work: WorkFact | None, ref: AssignmentRef) -> dict:
    if work is None:
        return {
            "assignment_id": str(ref.id),
            "status": "not_submitted",
            "score": None,
            "max_score": ref.max_score,
            "percent": None,
            "passed": None,
            "is_overdue": False,
            "submitted_at": None,
            "reviewer": None,
        }
    return {
        "assignment_id": str(ref.id),
        "status": work.status,
        "score": work.final_score,
        "max_score": work.max_score or ref.max_score,
        "percent": work.percent,
        "passed": work.passed,
        "is_overdue": work.is_overdue,
        "submitted_at": iso(work.submitted_at),
        "reviewer": work.reviewer_name,
    }


def performance(
    students: list[StudentRef],
    assignments: list[AssignmentRef],
    works: list[WorkFact],
) -> dict:
    """Матрица «студент × задание»: балл в ячейке, итог по студенту справа."""

    by_pair = {(work.student_id, work.assignment_id): work for work in works}
    rows = []
    for student in students:
        cells = [_cell(by_pair.get((student.id, ref.id)), ref) for ref in assignments]
        mine = [cell for cell in cells if cell["status"] != "not_submitted"]
        percents = [cell["percent"] for cell in mine if cell["percent"] is not None]
        scores = [cell["score"] for cell in mine if cell["score"] is not None]
        verdicts = [cell["passed"] for cell in mine if cell["passed"] is not None]
        rows.append(
            {
                "student_id": str(student.id),
                "student": student.name,
                "cells": cells,
                "totals": {
                    "expected": len(assignments),
                    "submitted": len(mine),
                    "completed": sum(1 for cell in mine if cell["status"] == "completed"),
                    "in_progress": sum(
                        1 for cell in mine if cell["status"] != "completed"
                    ),
                    "avg_score": _mean(scores),
                    "avg_percent": _mean(percents),
                    "passed": sum(verdicts),
                    "failed": len(verdicts) - sum(verdicts),
                    "overdue": sum(1 for cell in mine if cell["is_overdue"]),
                },
            }
        )
    rows.sort(key=lambda row: row["student"])

    columns = []
    for index, ref in enumerate(assignments):
        column = [row["cells"][index] for row in rows]
        submitted = [cell for cell in column if cell["status"] != "not_submitted"]
        percents = [cell["percent"] for cell in submitted if cell["percent"] is not None]
        verdicts = [cell["passed"] for cell in submitted if cell["passed"] is not None]
        columns.append(
            {
                "id": str(ref.id),
                "title": ref.title,
                "max_score": ref.max_score,
                "pass_score": ref.pass_score,
                "deadline_at": iso(ref.deadline_at),
                "stats": {
                    "expected": len(students),
                    "submitted": len(submitted),
                    "completed": sum(
                        1 for cell in submitted if cell["status"] == "completed"
                    ),
                    "avg_percent": _mean(percents),
                    "pass_rate": share(sum(verdicts), len(verdicts)),
                    "overdue": sum(1 for cell in submitted if cell["is_overdue"]),
                },
            }
        )

    all_percents = [
        cell["percent"]
        for row in rows
        for cell in row["cells"]
        if cell["percent"] is not None
    ]
    all_verdicts = [
        cell["passed"]
        for row in rows
        for cell in row["cells"]
        if cell["passed"] is not None
    ]
    expected = len(students) * len(assignments)
    submitted = sum(row["totals"]["submitted"] for row in rows)
    return {
        "assignments": columns,
        "rows": rows,
        "summary": {
            "students": len(students),
            "assignments": len(assignments),
            "expected": expected,
            "submitted": submitted,
            "not_submitted": expected - submitted,
            "submission_rate": share(submitted, expected),
            "avg_percent": _mean(all_percents),
            "pass_rate": share(sum(all_verdicts), len(all_verdicts)),
            "at_risk": sum(
                1
                for row in rows
                if row["totals"]["avg_percent"] is not None
                and row["totals"]["avg_percent"] < 60
            ),
        },
    }


# --------------------------------------------------------------------------- #
# Адаптеры к БД
# --------------------------------------------------------------------------- #


def _course(db: Session, course_id: UUID | None) -> Course | None:
    if course_id:
        return db.get(Course, course_id)
    return db.scalar(select(Course).order_by(Course.created_at))


def published_assignments(db: Session, course_id: UUID | None) -> list[Assignment]:
    query = select(Assignment).where(Assignment.published_at.is_not(None))
    if course_id:
        query = query.where(Assignment.course_id == course_id)
    return list(db.scalars(query.order_by(Assignment.created_at)))


def _rubrics(db: Session, assignments: list[Assignment]) -> dict[UUID, RubricVersion]:
    ids = [a.current_rubric_version_id for a in assignments if a.current_rubric_version_id]
    if not ids:
        return {}
    return {
        rubric.id: rubric
        for rubric in db.scalars(select(RubricVersion).where(RubricVersion.id.in_(ids)))
    }


def collect_works(db: Session, assignments: list[Assignment]) -> list[WorkFact]:
    """Один запрос на все сданные работы по опубликованным заданиям."""

    if not assignments:
        return []
    ids = [assignment.id for assignment in assignments]
    current = _rubrics(db, assignments)
    fallback = {
        assignment.id: current.get(assignment.current_rubric_version_id)
        for assignment in assignments
    }

    rows = db.execute(
        select(Submission, Review, RubricVersion, ReviewAssignment, User)
        .outerjoin(Review, Review.submission_id == Submission.id)
        .outerjoin(RubricVersion, RubricVersion.id == Review.rubric_version_id)
        .outerjoin(
            ReviewAssignment,
            and_(
                ReviewAssignment.submission_id == Submission.id,
                ReviewAssignment.is_active.is_(True),
            ),
        )
        .outerjoin(User, User.id == ReviewAssignment.reviewer_id)
        .where(Submission.assignment_id.in_(ids))
        .order_by(Submission.submitted_at)
    ).all()

    # Активное назначение по инварианту одно, но исторические данные могли
    # оставить второе — на работу всё равно должна приходиться одна строка.
    facts: dict[UUID, WorkFact] = {}
    for submission, review, rubric, assigned, reviewer in rows:
        if submission.id in facts:
            continue
        scale = rubric or fallback.get(submission.assignment_id)
        facts[submission.id] = (
            WorkFact(
                submission_id=submission.id,
                assignment_id=submission.assignment_id,
                student_id=submission.student_id,
                status=submission.status,
                is_overdue=bool(submission.is_overdue),
                submitted_at=submission.submitted_at,
                assigned_at=assigned.approved_at if assigned else None,
                completed_at=review.completed_at if review else None,
                final_score=review.final_score if review else None,
                max_score=float(scale.max_score) if scale else 0.0,
                pass_score=float(scale.pass_score) if scale else 0.0,
                ai_status=review.ai_status if review else "pending",
                reviewer_id=assigned.reviewer_id if assigned else None,
                completed_by=review.completed_by if review else None,
                reviewer_name=reviewer.full_name if reviewer else None,
                is_demo=bool(review.raw_result.get("demo_data")) if review else False,
            )
        )
    return list(facts.values())


# Ниже какого числа решений доля согласия ничего не значит: одно принятое
# решение — это «100%», и показать его рядом с сотней настоящих значит соврать.
MIN_DECIDED_FOR_AGREEMENT = 3


def agreement_by_assignment(db: Session, assignments: list[Assignment]) -> dict[UUID, dict]:
    """Доля согласия ревьюеров с AI — по каждому заданию отдельно.

    Возвращает и долю, и число решений, на которых она посчитана: без второго
    первое невозможно взвесить. Пока решений мало, доля не считается вовсе —
    вместо неё едет None, и экран говорит «мало данных», а не показывает 100%.
    """

    if not assignments:
        return {}
    rows = db.execute(
        select(
            Submission.assignment_id,
            func.count(),
            func.count(ReviewItem.id).filter(ReviewItem.reviewer_action == ReviewerAction.ACCEPTED),
        )
        .join(Review, Review.id == ReviewItem.review_id)
        .join(Submission, Submission.id == Review.submission_id)
        .where(
            Submission.assignment_id.in_([item.id for item in assignments]),
            ReviewItem.reviewer_action.in_(tuple(DECIDED_ACTIONS)),
        )
        .group_by(Submission.assignment_id)
    ).all()
    return {
        assignment_id: {
            "decided": decided,
            "accepted": accepted,
            "rate": share(accepted, decided) if decided >= MIN_DECIDED_FOR_AGREEMENT else None,
        }
        for assignment_id, decided, accepted in rows
    }


def collect_items(db: Session, assignments: list[Assignment]) -> list[ItemFact]:
    if not assignments:
        return []
    ids = [assignment.id for assignment in assignments]
    rows = db.execute(
        select(ReviewItem, Review.completed_by, Review.completed_at, Submission.assignment_id)
        .join(Review, Review.id == ReviewItem.review_id)
        .join(Submission, Submission.id == Review.submission_id)
        .where(Submission.assignment_id.in_(ids))
    ).all()
    return [
        ItemFact(
            criterion_key=item.criterion_key,
            criterion_title=item.criterion_title,
            max_score=float(item.max_score or 0.0),
            ai_score=float(item.ai_score or 0.0),
            final_score=item.final_score,
            action=item.reviewer_action,
            reviewer_id=completed_by,
            completed_at=completed_at,
            assignment_id=assignment_id,
        )
        for item, completed_by, completed_at, assignment_id in rows
    ]


def _students(db: Session, course_ids: set[UUID]) -> list[StudentRef]:
    if not course_ids:
        return []
    rows = db.scalars(
        select(User)
        .join(Enrollment, Enrollment.user_id == User.id)
        .where(Enrollment.course_id.in_(course_ids), User.role == Role.STUDENT)
        .order_by(User.full_name)
        .distinct()
    )
    return [StudentRef(id=row.id, name=row.full_name) for row in rows]


def _expected(db: Session, assignments: list[Assignment]) -> int:
    """Сколько работ вообще ожидается: студенты курса × его опубликованные задания."""

    if not assignments:
        return 0
    counts = dict(
        db.execute(
            select(Enrollment.course_id, func.count())
            .join(User, User.id == Enrollment.user_id)
            .where(User.role == Role.STUDENT)
            .group_by(Enrollment.course_id)
        ).all()
    )
    return sum(counts.get(assignment.course_id, 0) for assignment in assignments)


def course_report(
    db: Session, course_id: UUID | None = None, *, with_quality: bool = True
) -> dict:
    """Данные объединённого экрана «Дашборд курса»."""

    now = datetime.now(UTC)
    course = _course(db, course_id)
    assignments = published_assignments(db, course.id if course else None)
    works = collect_works(db, assignments)
    items = collect_items(db, assignments)
    students = _students(db, {assignment.course_id for assignment in assignments})
    loads = reviewer_loads(db)

    report = {
        "generated_at": iso(now),
        "course": (
            {"id": str(course.id), "title": course.title, "auto_assign": course.auto_assign}
            if course
            else None
        ),
        "overview": overview(
            works,
            items,
            expected=_expected(db, assignments),
            students=len(students),
            assignments=len(assignments),
            now=now,
        ),
        "funnel": funnel(works),
        "reviewers": reviewer_report(works, items, loads),
        "demo_reviews": sum(1 for work in works if work.is_demo),
        "live_records": len(works),
        "quality": None,
    }
    if with_quality:
        report["quality"] = {
            "agreement": agreement(items),
            "weekly": weekly(works, items, now=now),
            "criteria": criteria_report(items),
            "ai_runs": _ai_runs(works),
        }
    return report


def _ai_runs(works: list[WorkFact]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    for work in works:
        counts[work.ai_status] += 1
    total = len(works)
    return {
        "total": total,
        "ready": counts.get("ready", 0),
        "failed": counts.get("failed", 0),
        "pending": counts.get("pending", 0) + counts.get("running", 0),
        "ready_rate": share(counts.get("ready", 0), total),
    }


def performance_report(db: Session, course_id: UUID | None = None) -> dict:
    """Данные экрана «Успеваемость студентов»."""

    course = _course(db, course_id)
    assignments = published_assignments(db, course.id if course else None)
    rubrics = _rubrics(db, assignments)
    refs = [
        AssignmentRef(
            id=assignment.id,
            title=assignment.title,
            max_score=float(
                rubrics[assignment.current_rubric_version_id].max_score
                if assignment.current_rubric_version_id in rubrics
                else 0.0
            ),
            pass_score=float(
                rubrics[assignment.current_rubric_version_id].pass_score
                if assignment.current_rubric_version_id in rubrics
                else 0.0
            ),
            deadline_at=assignment.deadline_at,
        )
        for assignment in assignments
    ]
    students = _students(db, {assignment.course_id for assignment in assignments})
    works = collect_works(db, assignments)
    report = performance(students, refs, works)
    report["course"] = (
        {"id": str(course.id), "title": course.title} if course else None
    )
    return report
