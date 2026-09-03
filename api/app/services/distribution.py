from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ReviewAssignment, Role, Submission, SubmissionStatus, User


ACTIVE_STATUSES = {
    SubmissionStatus.ASSIGNED,
    SubmissionStatus.IN_REVIEW,
    SubmissionStatus.BLITZ_SENT,
    SubmissionStatus.BLITZ_ANSWERED,
}


def proposals(db: Session) -> list[dict]:
    """Simple, explainable load-based distribution from the project decision."""

    reviewers = list(
        db.scalars(
            select(User)
            .where(User.role == Role.REVIEWER, User.is_available.is_(True))
            .order_by(User.full_name)
        )
    )
    load: dict = defaultdict(float)
    active = db.scalars(
        select(ReviewAssignment).join(Submission).where(
            ReviewAssignment.is_active.is_(True), Submission.status.in_(ACTIVE_STATUSES)
        )
    )
    for assignment in active:
        load[assignment.reviewer_id] += 1

    waiting = db.scalars(
        select(Submission)
        .where(Submission.status.in_([SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED]))
        .order_by(Submission.submitted_at)
    )
    result = []
    for submission in waiting:
        candidates = [
            reviewer
            for reviewer in reviewers
            if reviewer.specialization in (None, submission.assignment.course.specialization)
            and load[reviewer.id] < submission.assignment.course.reviewer_capacity
        ]
        if not candidates:
            result.append({"submission": submission, "reviewer": None, "explanation": "Нет доступных ревьюеров"})
            continue
        chosen = min(candidates, key=lambda user: (load[user.id], user.full_name))
        explanation = (
            f"Специализация совпадает · загрузка {int(load[chosen.id])} работ · "
            f"рассмотрено кандидатов: {len(candidates)}"
        )
        result.append({"submission": submission, "reviewer": chosen, "explanation": explanation})
        load[chosen.id] += submission.assignment.effort_weight
    return result
