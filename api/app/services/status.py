"""Переходы автомата работы. Всё пишется в status_history — отдельного учёта нет."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status as http
from sqlalchemy.orm import Session

from ..models import SUBMISSION_FLOW, StatusHistory, Submission, SubmissionStatus, User


def transition(
    db: Session,
    submission: Submission,
    to_status: SubmissionStatus,
    actor: User | None = None,
    comment: str = "",
) -> Submission:
    allowed = SUBMISSION_FLOW.get(submission.status, [])
    if to_status not in allowed:
        raise HTTPException(
            http.HTTP_409_CONFLICT,
            f"Переход {submission.status} → {to_status} не разрешён автоматом",
        )

    db.add(
        StatusHistory(
            submission_id=submission.id,
            from_status=submission.status,
            to_status=to_status,
            actor_id=actor.id if actor else None,
            comment=comment,
        )
    )
    submission.status = to_status
    return submission


def record_initial(db: Session, submission: Submission, actor: User | None = None) -> None:
    db.add(
        StatusHistory(
            submission_id=submission.id,
            from_status=None,
            to_status=submission.status,
            actor_id=actor.id if actor else None,
        )
    )


def overdue_risk(submission: Submission) -> bool:
    """Работа, не начатая за 24 часа до дедлайна, — риск просрочки."""

    deadline = submission.assignment.deadline_at if submission.assignment else None
    if deadline is None or submission.status in (SubmissionStatus.COMPLETED,):
        return False
    if submission.status not in (SubmissionStatus.ASSIGNED, SubmissionStatus.PROPOSED):
        return False
    return datetime.now(UTC) + timedelta(hours=24) >= deadline
