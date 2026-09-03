from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    AiSignal,
    BlitzSession,
    BlitzStatus,
    Notification,
    Review,
    ReviewAssignment,
    ReviewerAction,
    ReviewItem,
    Role,
    SignalDecision,
    Snapshot,
    Submission,
    SubmissionStatus,
    User,
)
from ..security import require
from ..serializers import iso, review_data, submission_data
from ..services.mock_review import blitz_questions
from ..services.status import overdue_risk, transition
from ..services.ai_reviewer_client import (
    AiReviewerClient,
    AiReviewerError,
    AiReviewerUnavailable,
)
from ..services.review_pipeline import persist_call, run_review

router = APIRouter(prefix="/reviewer", tags=["reviewer"])
reviewer_guard = require(Role.REVIEWER)


class ItemDecision(BaseModel):
    action: Literal["accepted", "changed", "rejected"]
    final_score: float | None = Field(default=None, ge=0)
    comment: str = ""


class SignalDecisionPayload(BaseModel):
    decision: Literal["confirmed", "dismissed"]


class BlitzCreate(BaseModel):
    questions: list[dict]


class CompleteReview(BaseModel):
    feedback: str = Field(min_length=10)


class RewriteFeedback(BaseModel):
    text: str = Field(min_length=3)


def review_context(db: Session, submission_id: UUID, reviewer: User) -> tuple[Submission, Review]:
    assignment = db.scalar(
        select(ReviewAssignment).where(
            ReviewAssignment.submission_id == submission_id,
            ReviewAssignment.reviewer_id == reviewer.id,
            ReviewAssignment.is_active.is_(True),
            ReviewAssignment.approved_at.is_not(None),
        )
    )
    if not assignment:
        raise HTTPException(404, "Работа не найдена в вашей очереди")
    submission = db.get(Submission, submission_id)
    review = db.scalar(select(Review).where(Review.submission_id == submission_id))
    if not submission or not review:
        raise HTTPException(404, "Ревью не найдено")
    return submission, review


@router.get("/queue")
def queue(user: User = Depends(reviewer_guard), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        select(Submission, ReviewAssignment)
        .join(ReviewAssignment, ReviewAssignment.submission_id == Submission.id)
        .where(
            ReviewAssignment.reviewer_id == user.id,
            ReviewAssignment.is_active.is_(True),
            ReviewAssignment.approved_at.is_not(None),
            Submission.status != SubmissionStatus.COMPLETED,
        )
        .order_by(Submission.is_overdue.desc(), Submission.submitted_at)
    ).all()
    result = []
    for submission, assignment in rows:
        data = submission_data(submission, user.full_name)
        data["deadline_risk"] = overdue_risk(submission) or submission.is_overdue
        data["explanation"] = assignment.explanation
        review = db.scalar(select(Review).where(Review.submission_id == submission.id))
        data["ai_status"] = review.ai_status if review else "failed"
        result.append(data)
    return result


@router.get("/submissions/{submission_id}/review")
def review_screen(
    submission_id: UUID,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    submission, review = review_context(db, submission_id, user)
    if submission.status == SubmissionStatus.ASSIGNED:
        transition(db, submission, SubmissionStatus.IN_REVIEW, user, "Ревьюер открыл работу")
        db.commit()
    snapshot = db.scalar(select(Snapshot).where(Snapshot.submission_id == submission.id))
    blitz = db.scalar(
        select(BlitzSession).where(BlitzSession.review_id == review.id).order_by(BlitzSession.created_at.desc())
    )
    return {
        "submission": submission_data(submission, user.full_name),
        "snapshot": {
            "content": snapshot.content if snapshot else "",
            "parsed_facts": snapshot.parsed_facts if snapshot else {},
            "fetched_at": iso(snapshot.fetched_at) if snapshot else None,
        },
        "review": review_data(review),
        "blitz": {
            "id": str(blitz.id),
            "status": blitz.status,
            "questions": blitz.questions,
            "answers": blitz.answers,
            "ai_analysis": blitz.ai_analysis,
            "due_at": iso(blitz.due_at),
        } if blitz else None,
        "suggested_questions": blitz_questions() if settings.feature_blitz else [],
    }


@router.patch("/review-items/{item_id}")
def decide_item(
    item_id: UUID,
    payload: ItemDecision,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    item = db.get(ReviewItem, item_id)
    review = db.get(Review, item.review_id) if item else None
    if not review:
        raise HTTPException(404, "Критерий не найден")
    review_context(db, review.submission_id, user)
    if payload.action == ReviewerAction.CHANGED and payload.final_score is None:
        raise HTTPException(422, "Для изменённого вывода укажите итоговый балл")
    if payload.final_score is not None and payload.final_score > item.max_score:
        raise HTTPException(422, "Баллы превышают максимум критерия")
    item.reviewer_action = payload.action
    item.final_score = {
        ReviewerAction.ACCEPTED: item.ai_score,
        ReviewerAction.REJECTED: 0,
    }.get(payload.action, payload.final_score)
    item.reviewer_comment = payload.comment
    db.commit()
    return {"ok": True, "item_id": str(item.id), "action": item.reviewer_action}


@router.patch("/signals/{signal_id}")
def decide_signal(
    signal_id: UUID,
    payload: SignalDecisionPayload,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    signal = db.get(AiSignal, signal_id)
    review = db.get(Review, signal.review_id) if signal else None
    if not review:
        raise HTTPException(404, "Сигнал не найден")
    review_context(db, review.submission_id, user)
    signal.reviewer_decision = payload.decision
    signal.decided_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}


@router.post("/reviews/{review_id}/blitz", status_code=201)
def send_blitz(
    review_id: UUID,
    payload: BlitzCreate,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.feature_blitz:
        raise HTTPException(404, "Раздел выключен")
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, _ = review_context(db, review.submission_id, user)
    if submission.status != SubmissionStatus.IN_REVIEW:
        raise HTTPException(409, "Дополнительные вопросы можно отправить только во время ревью")
    selected = [question for question in payload.questions if question.get("selected", True)]
    if not selected:
        raise HTTPException(422, "Выберите хотя бы один вопрос")
    session = BlitzSession(
        review_id=review.id,
        status=BlitzStatus.SENT,
        questions=selected,
        sent_at=datetime.now(UTC),
        due_at=datetime.now(UTC) + timedelta(hours=48),
    )
    db.add(session)
    transition(db, submission, SubmissionStatus.BLITZ_SENT, user, "Ревьюер отправил дополнительные вопросы")
    db.add(
        Notification(
            recipient_id=submission.student_id,
            kind="blitz",
            title="Дополнительные вопросы по вашей работе",
            body="Ответьте на вопросы в течение 48 часов",
            payload={"route": "/student/blitz"},
        )
    )
    for signal in review.signals:
        if signal.reviewer_decision == SignalDecision.PENDING:
            signal.reviewer_decision = SignalDecision.BLITZ
            signal.decided_at = datetime.now(UTC)
    db.commit()
    return {"id": str(session.id), "status": session.status}


@router.post("/reviews/{review_id}/rewrite-feedback")
def rewrite_feedback(
    review_id: UUID,
    payload: RewriteFeedback,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, review = review_context(db, review.submission_id, user)
    decisions = [
        {
            "criterion": item.criterion_title,
            "score": item.final_score if item.final_score is not None else item.ai_score,
            "max_score": item.max_score,
            "action": item.reviewer_action,
            "comment": item.reviewer_comment or item.recommendation,
        }
        for item in review.items
        if item.reviewer_action != ReviewerAction.REJECTED
    ]
    try:
        response = AiReviewerClient().rewrite_feedback(
            text=payload.text,
            tone_of_voice=submission.assignment.course.tone_of_voice,
            decisions=decisions,
        )
        suggestion = response.suggestion
        metadata = response.metadata
    except AiReviewerUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AiReviewerError as exc:
        raise HTTPException(502, f"AI reviewer не смог переформулировать feedback: {exc}") from exc
    persist_call(db, review.id, "feedback_copilot", metadata)
    db.commit()
    return {
        "original": payload.text,
        "suggestion": suggestion,
        "provider": "z.ai",
        "model": metadata.model,
    }


@router.post("/reviews/{review_id}/rerun", status_code=202)
def rerun_review(
    review_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, review = review_context(db, review.submission_id, user)
    if submission.status == SubmissionStatus.COMPLETED:
        raise HTTPException(409, "Завершённое ревью нельзя перезапустить")
    if any(item.reviewer_action != ReviewerAction.PENDING for item in review.items):
        raise HTTPException(409, "Ревью с решениями человека нельзя перезапустить")
    if review.ai_status == "running":
        raise HTTPException(409, "AI-ревью уже выполняется")
    review.ai_status = "pending"
    review.ai_error = None
    db.commit()
    background_tasks.add_task(run_review, review.id)
    return {"review_id": str(review.id), "ai_status": review.ai_status}


@router.post("/reviews/{review_id}/complete")
def complete(
    review_id: UUID,
    payload: CompleteReview,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, review = review_context(db, review.submission_id, user)
    unresolved = [item for item in review.items if item.reviewer_action == ReviewerAction.PENDING]
    if unresolved:
        raise HTTPException(409, f"Примите решение по всем критериям: осталось {len(unresolved)}")
    if submission.status not in (SubmissionStatus.IN_REVIEW, SubmissionStatus.BLITZ_ANSWERED):
        raise HTTPException(409, "Работа пока не готова к завершению")
    review.final_score = sum(item.final_score or 0 for item in review.items)
    review.final_feedback = payload.feedback
    review.completed_by = user.id
    review.completed_at = datetime.now(UTC)
    transition(db, submission, SubmissionStatus.COMPLETED, user, "Ревью подтверждено человеком")
    db.add(
        Notification(
            recipient_id=submission.student_id,
            kind="review_completed",
            title="Работа проверена",
            body="Опубликованы оценка и обратная связь",
            payload={"submission_id": str(submission.id)},
        )
    )
    db.commit()
    return {"ok": True, "score": review.final_score, "status": submission.status}
