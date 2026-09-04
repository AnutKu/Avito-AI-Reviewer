"""Балансировщик ревьюеров.

Правило простое и объяснимое (проектное решение §8):

1. фильтр по специализации;
2. среди доступных — минимальная текущая нагрузка
   (сумма весов трудоёмкости активных работ, а не просто их число);
3. при равенстве нагрузки — round-robin: работа уходит тому, кто дольше всех
   не получал новых назначений;
4. жёсткий кап работ на ревьюера — параметр курса (`courses.reviewer_capacity`).

Ядро (`plan_distribution`) — чистая детерминированная функция над простыми
структурами, без ORM и без обращения к времени: её покрывают юнит-тесты.
Функции `proposals` / `rebalance` / `reviewer_loads` — тонкие адаптеры к БД,
сохраняющие прежние контракты роутера методиста.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Assignment,
    Course,
    ReviewAssignment,
    Role,
    Submission,
    SubmissionStatus,
    User,
)

# Работы, которые уже «висят» на ревьюере и создают нагрузку.
ACTIVE_STATUSES = {
    SubmissionStatus.ASSIGNED,
    SubmissionStatus.IN_REVIEW,
    SubmissionStatus.BLITZ_SENT,
    SubmissionStatus.BLITZ_ANSWERED,
}
# Работы, ожидающие распределения.
WAITING_STATUSES = {SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED}
# Работу, которую ревьюер уже открыл, при ребалансе не трогаем —
# переносим только назначенные, но ещё не начатые.
MOVABLE_STATUSES = {SubmissionStatus.PROPOSED, SubmissionStatus.ASSIGNED}

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
DEFAULT_CAPACITY = 12.0


@dataclass(frozen=True)
class ReviewerState:
    """Снимок ревьюера для планировщика."""

    id: UUID
    name: str
    specialization: str | None
    is_available: bool
    base_load: float           # сумма весов трудоёмкости активных работ
    active_count: int          # число активных работ (для UI)
    capacity: float            # кап курса
    last_assigned_at: datetime | None


@dataclass(frozen=True)
class Work:
    """Работа, которую нужно кому-то назначить."""

    submission_id: UUID
    student_name: str
    assignment_title: str
    specialization: str
    effort_weight: float
    submitted_at: datetime
    capacity: float                     # кап курса, к которому относится работа
    current_reviewer_id: UUID | None = None


@dataclass(frozen=True)
class Proposal:
    submission_id: UUID
    reviewer_id: UUID | None
    explanation: str
    over_capacity: bool = False


def _spec_ok(reviewer: ReviewerState, work: Work) -> bool:
    # None-специализация = «универсал», подходит под любую работу.
    return reviewer.specialization is None or reviewer.specialization == work.specialization


def _explain(
    reviewer: ReviewerState,
    load_after: float,
    capacity: float,
    considered: int,
    *,
    round_robin: bool,
    over: bool,
) -> str:
    parts = [
        f"специализация «{reviewer.specialization or 'любая'}»",
        f"нагрузка {load_after:.1f}/{capacity:.0f}",
        f"кандидатов рассмотрено: {considered}",
    ]
    if round_robin:
        parts.append("дольше всех без новых работ")
    if over:
        parts.append(f"⚠ сверх лимита ({load_after:.1f}/{capacity:.0f})")
    text = " · ".join(parts)
    return text[0].upper() + text[1:]


def plan_distribution(
    reviewers: list[ReviewerState],
    works: list[Work],
    *,
    exclude_current: bool = False,
) -> list[Proposal]:
    """Разложить `works` по `reviewers`. Чистая функция, без побочных эффектов.

    Батч раскладывается последовательно: после каждого назначения нагрузка
    выбранного ревьюера растёт, поэтому работы внутри одного вызова тоже
    выравниваются между собой, а не только относительно стартовой нагрузки.
    """

    load: dict[UUID, float] = {r.id: r.base_load for r in reviewers}
    # Сколько раз ревьюер уже выбран в этом батче — вращает round-robin,
    # когда исторических данных не хватает.
    picks: dict[UUID, int] = {r.id: 0 for r in reviewers}
    hist: dict[UUID, datetime] = {r.id: (r.last_assigned_at or _EPOCH) for r in reviewers}
    out: list[Proposal] = []

    for work in sorted(works, key=lambda w: (w.submitted_at, str(w.submission_id))):
        pool = [
            r
            for r in reviewers
            if r.is_available
            and _spec_ok(r, work)
            and not (exclude_current and r.id == work.current_reviewer_id)
        ]
        fitting = [r for r in pool if load[r.id] + work.effort_weight <= work.capacity + 1e-9]
        candidates = fitting or pool
        if not candidates:
            out.append(
                Proposal(
                    work.submission_id,
                    None,
                    "Нет доступного ревьюера с подходящей специализацией",
                )
            )
            continue

        ranked = sorted(
            candidates,
            key=lambda r: (round(load[r.id], 6), picks[r.id], hist[r.id], r.name),
        )
        best = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        # Round-robin реально сработал, только если по нагрузке был паритет.
        round_robin = runner_up is not None and round(load[runner_up.id], 6) == round(
            load[best.id], 6
        )
        over = best not in fitting

        load[best.id] += work.effort_weight
        picks[best.id] += 1
        out.append(
            Proposal(
                work.submission_id,
                best.id,
                _explain(
                    best,
                    load[best.id],
                    work.capacity,
                    len(candidates),
                    round_robin=round_robin,
                    over=over,
                ),
                over_capacity=over,
            )
        )
    return out


# --------------------------------------------------------------------------- #
# Адаптеры к БД
# --------------------------------------------------------------------------- #


def _course_capacity(db: Session) -> float:
    """Кап на ревьюера. Курс в MVP один; берём самый строгий, если их несколько."""

    value = db.scalar(select(func.min(Course.reviewer_capacity)))
    return float(value) if value else DEFAULT_CAPACITY


def _reviewer_states(db: Session) -> tuple[list[ReviewerState], dict[UUID, User]]:
    capacity = _course_capacity(db)
    reviewers = list(
        db.scalars(
            select(User).where(User.role == Role.REVIEWER).order_by(User.full_name)
        )
    )

    load_rows = db.execute(
        select(
            ReviewAssignment.reviewer_id,
            func.coalesce(func.sum(Assignment.effort_weight), 0.0),
            func.count(),
        )
        .join(Submission, Submission.id == ReviewAssignment.submission_id)
        .join(Assignment, Assignment.id == Submission.assignment_id)
        .where(
            ReviewAssignment.is_active.is_(True),
            Submission.status.in_(ACTIVE_STATUSES),
        )
        .group_by(ReviewAssignment.reviewer_id)
    ).all()
    load_by_id = {rid: (float(weight), int(count)) for rid, weight, count in load_rows}

    last_rows = db.execute(
        select(
            ReviewAssignment.reviewer_id,
            func.max(
                func.coalesce(ReviewAssignment.approved_at, ReviewAssignment.created_at)
            ),
        ).group_by(ReviewAssignment.reviewer_id)
    ).all()
    last_by_id = {rid: ts for rid, ts in last_rows}

    states = [
        ReviewerState(
            id=reviewer.id,
            name=reviewer.full_name,
            specialization=reviewer.specialization,
            is_available=reviewer.is_available,
            base_load=load_by_id.get(reviewer.id, (0.0, 0))[0],
            active_count=load_by_id.get(reviewer.id, (0.0, 0))[1],
            capacity=capacity,
            last_assigned_at=last_by_id.get(reviewer.id),
        )
        for reviewer in reviewers
    ]
    return states, {reviewer.id: reviewer for reviewer in reviewers}


def _work_of(
    db: Session, submission: Submission, *, current_reviewer_id: UUID | None = None
) -> Work:
    assignment = submission.assignment
    course = assignment.course
    return Work(
        submission_id=submission.id,
        student_name=submission.student.full_name,
        assignment_title=assignment.title,
        specialization=course.specialization,
        effort_weight=float(assignment.effort_weight or 1.0),
        submitted_at=submission.submitted_at,
        capacity=float(course.reviewer_capacity or DEFAULT_CAPACITY),
        current_reviewer_id=current_reviewer_id,
    )


def _rows(
    plan: list[Proposal],
    subs: dict[UUID, Submission],
    orm: dict[UUID, User],
    *,
    prefix: str = "",
) -> list[dict]:
    rows = []
    for item in plan:
        reviewer = orm.get(item.reviewer_id)
        explanation = item.explanation
        if prefix and reviewer is not None:
            explanation = f"{prefix}{explanation}"
        rows.append(
            {
                "submission": subs[item.submission_id],
                "reviewer": reviewer,
                "explanation": explanation,
                "over_capacity": item.over_capacity,
            }
        )
    return rows


def proposals(db: Session) -> list[dict]:
    """Раскладка для экрана «Распределение». Рекомендация, не действие."""

    states, orm = _reviewer_states(db)
    waiting = list(
        db.scalars(
            select(Submission)
            .where(Submission.status.in_(WAITING_STATUSES))
            .order_by(Submission.submitted_at)
        )
    )
    works = [_work_of(db, submission) for submission in waiting]
    plan = plan_distribution(states, works)
    return _rows(plan, {s.id: s for s in waiting}, orm)


def reviewer_loads(db: Session) -> list[dict]:
    """Нагрузка и свободный лимит по каждому ревьюеру — для переназначения «по возможностям»."""

    states, _ = _reviewer_states(db)
    return [
        {
            "id": str(state.id),
            "name": state.name,
            "specialization": state.specialization,
            "available": state.is_available,
            "load": round(state.base_load, 1),
            "active_count": state.active_count,
            "capacity": round(state.capacity, 1),
            "slots_left": round(state.capacity - state.base_load, 1),
        }
        for state in states
    ]


def reviewer_headroom(db: Session, reviewer_id: UUID, extra_weight: float) -> dict | None:
    """Хватит ли у ревьюера лимита ещё на одну работу веса `extra_weight`."""

    for row in reviewer_loads(db):
        if row["id"] == str(reviewer_id):
            return {**row, "fits": row["load"] + extra_weight <= row["capacity"] + 1e-9}
    return None


def rebalance(
    db: Session, reviewer_ids: list[UUID], *, set_unavailable: bool = False
) -> list[dict]:
    """Снять активные, ещё не начатые работы с указанных ревьюеров и предложить,
    кому их передать. Ничего не применяет — методист подтверждает раскладку сам."""

    off = {UUID(str(rid)) for rid in reviewer_ids}
    rows = list(
        db.execute(
            select(Submission, ReviewAssignment)
            .join(ReviewAssignment, ReviewAssignment.submission_id == Submission.id)
            .where(
                ReviewAssignment.is_active.is_(True),
                ReviewAssignment.reviewer_id.in_(off),
                Submission.status.in_(MOVABLE_STATUSES),
            )
            .order_by(Submission.submitted_at)
        ).all()
    )

    if set_unavailable:
        for reviewer in db.scalars(select(User).where(User.id.in_(off))):
            reviewer.is_available = False
        db.flush()

    states, orm = _reviewer_states(db)
    moved_weight: dict[UUID, float] = defaultdict(float)
    for submission, assignment in rows:
        moved_weight[assignment.reviewer_id] += float(
            submission.assignment.effort_weight or 1.0
        )

    # Получатели — все, кроме разгружаемых; их стартовая нагрузка уменьшена
    # на вес работ, которые мы как раз снимаем.
    receivers = [
        replace(state, base_load=max(0.0, state.base_load - moved_weight.get(state.id, 0.0)))
        for state in states
        if state.id not in off
    ]
    works = [
        _work_of(db, submission, current_reviewer_id=assignment.reviewer_id)
        for submission, assignment in rows
    ]
    plan = plan_distribution(receivers, works, exclude_current=True)
    subs = {submission.id: submission for submission, _ in rows}
    return _rows(plan, subs, orm, prefix="Переназначение · ")
