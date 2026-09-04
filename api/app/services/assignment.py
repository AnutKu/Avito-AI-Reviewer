"""Применение раскладки: превратить предложение балансировщика в назначение.

Домейн без HTTP-слоя — переиспользуется роутером методиста (ручное подтверждение),
студенческим submit (авто-режим) и переносом работ при снятии ревьюера.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Course,
    Notification,
    ReviewAssignment,
    Submission,
    SubmissionStatus,
    User,
)
from ..services.distribution import proposals, rebalance
from ..services.status import transition


def auto_assign_enabled(db: Session) -> bool:
    course = db.scalar(select(Course).order_by(Course.created_at))
    return bool(course and course.auto_assign)


def assign_submission(
    db: Session,
    submission: Submission,
    reviewer: User,
    *,
    explanation: str,
    actor_id: UUID | None,
) -> None:
    """Снять прежнее активное назначение, поставить новое, двинуть статус, уведомить.

    Валидацию (роль, доступность, кап) делает вызывающий код."""

    actor = db.get(User, actor_id) if actor_id else None
    active = db.scalars(
        select(ReviewAssignment).where(
            ReviewAssignment.submission_id == submission.id,
            ReviewAssignment.is_active.is_(True),
        )
    )
    for row in active:
        row.is_active = False

    db.add(
        ReviewAssignment(
            submission_id=submission.id,
            reviewer_id=reviewer.id,
            proposed_by="auto" if actor_id is None else "system",
            explanation=explanation,
            approved_by=actor_id,
            approved_at=datetime.now(UTC),
        )
    )

    if submission.status == SubmissionStatus.SUBMITTED:
        transition(db, submission, SubmissionStatus.PROPOSED, actor, "Сформировано предложение")
    if submission.status == SubmissionStatus.PROPOSED:
        transition(db, submission, SubmissionStatus.ASSIGNED, actor, "Распределение подтверждено")
    elif submission.status == SubmissionStatus.IN_REVIEW:
        transition(db, submission, SubmissionStatus.ASSIGNED, actor, "Работа переназначена")

    db.add(
        Notification(
            recipient_id=reviewer.id,
            kind="assignment",
            title="Назначена новая работа",
            body=f"{submission.assignment.title} · {submission.student.full_name}",
            payload={"submission_id": str(submission.id)},
        )
    )


def auto_distribute(db: Session, *, actor_id: UUID | None = None) -> int:
    """Разложить все ожидающие работы по балансировщику и сразу применить."""

    applied = 0
    for row in proposals(db):
        if row["reviewer"] is None:
            continue
        assign_submission(
            db,
            row["submission"],
            row["reviewer"],
            explanation=row["explanation"],
            actor_id=actor_id,
        )
        applied += 1
    return applied


def auto_reassign_from(db: Session, reviewer_ids: list[UUID], *, actor_id: UUID | None = None) -> int:
    """Перекинуть ещё не начатые работы указанных ревьюеров на других и применить."""

    applied = 0
    for row in rebalance(db, reviewer_ids):
        if row["reviewer"] is None:
            continue
        assign_submission(
            db,
            row["submission"],
            row["reviewer"],
            explanation=row["explanation"],
            actor_id=actor_id,
        )
        applied += 1
    return applied
