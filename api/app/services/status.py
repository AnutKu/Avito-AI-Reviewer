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


def deadline_state(submission: Submission) -> str | None:
    """Состояние срока: `overdue` — срок прошёл, `risk` — меньше суток, иначе None.

    Срок один на всё задание, поэтому и признак зависит только от него и от
    того, закрыта ли работа. Раньше сюда примешивался статус (риск считался
    только для `assigned`/`proposed`), и работа с тем же дедлайном переставала
    быть красной, стоило ревьюеру её открыть, — одинаковый срок, разный цвет.
    """

    deadline = submission.assignment.deadline_at if submission.assignment else None
    if deadline is None or submission.status == SubmissionStatus.COMPLETED:
        return None
    now = datetime.now(UTC)
    if now >= deadline:
        return "overdue"
    if now + timedelta(hours=24) >= deadline:
        return "risk"
    return None
