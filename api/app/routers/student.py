from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Assignment,
    BlitzSession,
    BlitzStatus,
    Enrollment,
    Notification,
    Review,
    ReviewAssignment,
    Role,
    RubricVersion,
    Snapshot,
    Submission,
    SubmissionStatus,
    User,
)
from ..security import require
from ..serializers import assignment_data, iso, review_data, submission_data
from ..services.github import GithubSnapshotError, fetch_github_snapshot
from ..services.status import record_initial, transition
from ..services.review_pipeline import run_detection, run_review

router = APIRouter(
    prefix="/student",
    tags=["student"],
    dependencies=[],
)
student_guard = require(Role.STUDENT)


class SubmissionCreate(BaseModel):
    source_url: HttpUrl


class BlitzAnswers(BaseModel):
    answers: list[dict]


@router.get("/assignments")
def assignments(user: User = Depends(student_guard), db: Session = Depends(get_db)) -> list[dict]:
    course_ids = select(Enrollment.course_id).where(Enrollment.user_id == user.id)
    rows = db.scalars(select(Assignment).where(Assignment.course_id.in_(course_ids)).order_by(Assignment.deadline_at))
    result = []
    for assignment in rows:
        submission = db.scalar(
            select(Submission).where(
                Submission.assignment_id == assignment.id, Submission.student_id == user.id
            )
        )
        data = assignment_data(assignment)
        data["submission"] = submission_data(submission) if submission else None
        if submission and submission.status == SubmissionStatus.COMPLETED:
            review = db.scalar(select(Review).where(Review.submission_id == submission.id))
            data["score"] = review.final_score if review else None
        else:
            data["score"] = None
        result.append(data)
    return result


@router.get("/assignments/{assignment_id}")
def assignment(
    assignment_id: UUID,
    user: User = Depends(student_guard),
    db: Session = Depends(get_db),
) -> dict:
    row = db.get(Assignment, assignment_id)
    enrolled = db.scalar(
        select(Enrollment.id).where(Enrollment.course_id == row.course_id, Enrollment.user_id == user.id)
    ) if row else None
    if not row or not enrolled:
        raise HTTPException(404, "Задание не найдено")
    rubric = db.get(RubricVersion, row.current_rubric_version_id)
    data = assignment_data(row, rubric)
    submission = db.scalar(
        select(Submission).where(Submission.assignment_id == row.id, Submission.student_id == user.id)
    )
    data["submission"] = submission_data(submission) if submission else None
    return data


@router.post("/assignments/{assignment_id}/submissions", status_code=202)
def submit(
    assignment_id: UUID,
    payload: SubmissionCreate,
    background_tasks: BackgroundTasks,
    user: User = Depends(student_guard),
    db: Session = Depends(get_db),
) -> dict:
    assignment = db.get(Assignment, assignment_id)
    enrolled = db.scalar(
        select(Enrollment.id).where(
            Enrollment.course_id == assignment.course_id, Enrollment.user_id == user.id
        )
    ) if assignment else None
    if not assignment or not enrolled:
        raise HTTPException(404, "Задание не найдено")
    existing = db.scalar(
        select(Submission).where(
            Submission.assignment_id == assignment.id, Submission.student_id == user.id
        )
    )
    if existing:
        raise HTTPException(409, "Работа по этому заданию уже принята")
    source_url = str(payload.source_url)
    try:
        github_snapshot = fetch_github_snapshot(source_url)
    except GithubSnapshotError as exc:
        raise HTTPException(422, str(exc)) from exc
    submission = Submission(
        assignment_id=assignment.id,
        student_id=user.id,
        source_url=source_url,
        status=SubmissionStatus.SUBMITTED,
        is_overdue=bool(assignment.deadline_at and datetime.now(UTC) > assignment.deadline_at),
    )
    db.add(submission)
    db.flush()
    record_initial(db, submission, user)
    db.add(
        Snapshot(
            submission_id=submission.id,
            content=github_snapshot.content,
            content_hash=github_snapshot.content_hash,
            parsed_facts=github_snapshot.parsed_facts,
        )
    )
    review = Review(
        submission_id=submission.id,
        rubric_version_id=assignment.current_rubric_version_id,
    )
    db.add(review)
    db.flush()
    transition(db, submission, SubmissionStatus.PROPOSED, comment="AI-ревью поставлено в очередь")
    db.commit()
    background_tasks.add_task(run_review, review.id)
    background_tasks.add_task(run_detection, review.id)
    data = submission_data(submission)
    data["review"] = {"id": str(review.id), "ai_status": review.ai_status}
    return data


def own_submission(db: Session, submission_id: UUID, user: User) -> Submission:
    submission = db.get(Submission, submission_id)
    if not submission or submission.student_id != user.id:
        raise HTTPException(404, "Работа не найдена")
    return submission


@router.get("/submissions/{submission_id}/result")
def result(
    submission_id: UUID,
    user: User = Depends(student_guard),
    db: Session = Depends(get_db),
) -> dict:
    submission = own_submission(db, submission_id, user)
    review = db.scalar(select(Review).where(Review.submission_id == submission.id))
    data = {"submission": submission_data(submission), "review": None}
    if submission.status == SubmissionStatus.COMPLETED and review:
        data["review"] = review_data(review, include_internal=False)
        data["criteria"] = [
            {
                "title": item.criterion_title,
                "score": item.final_score,
                "max_score": item.max_score,
                "comment": item.reviewer_comment or item.recommendation,
            }
            for item in review.items
            if item.reviewer_action != "rejected"
        ]
    return data


@router.get("/blitz")
def blitz(user: User = Depends(student_guard), db: Session = Depends(get_db)) -> list[dict]:
    sessions = db.execute(
        select(BlitzSession, Submission)
        .join(Review, Review.id == BlitzSession.review_id)
        .join(Submission, Submission.id == Review.submission_id)
        .where(Submission.student_id == user.id, BlitzSession.status == BlitzStatus.SENT)
    ).all()
    return [
        {
            "id": str(session.id),
            "assignment": submission.assignment.title,
            "questions": session.questions,
            "sent_at": iso(session.sent_at),
            "due_at": iso(session.due_at),
        }
        for session, submission in sessions
    ]


@router.post("/blitz/{session_id}/answer")
def answer_blitz(
    session_id: UUID,
    payload: BlitzAnswers,
    user: User = Depends(student_guard),
    db: Session = Depends(get_db),
) -> dict:
    session = db.get(BlitzSession, session_id)
    review = db.get(Review, session.review_id) if session else None
    submission = db.get(Submission, review.submission_id) if review else None
    if not session or not submission or submission.student_id != user.id:
        raise HTTPException(404, "Опрос не найден")
    if session.status != BlitzStatus.SENT:
        raise HTTPException(409, "Ответ на этот опрос уже принят")
    session.answers = payload.answers
    session.status = BlitzStatus.ANSWERED
    session.answered_at = datetime.now(UTC)
    session.ai_analysis = {
        "summary": "Ответ показывает понимание выбора модели; итоговое решение остаётся за ревьюером.",
        "confidence": "medium",
        "mock": True,
    }
    transition(db, submission, SubmissionStatus.BLITZ_ANSWERED, user, "Студент ответил на блиц")
    assignment = db.scalar(
        select(ReviewAssignment).where(
            ReviewAssignment.submission_id == submission.id, ReviewAssignment.is_active.is_(True)
        )
    )
    if assignment:
        db.add(
            Notification(
                recipient_id=assignment.reviewer_id,
                kind="blitz_answered",
                title="Получен ответ на дополнительные вопросы",
                body=f"{user.full_name} ответил на блиц-опрос",
                payload={"submission_id": str(submission.id)},
            )
        )
    db.commit()
    return {"ok": True, "status": session.status}
