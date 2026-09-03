from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    Assignment,
    Course,
    Notification,
    Review,
    ReviewAssignment,
    ReviewItem,
    Role,
    RubricVersion,
    Submission,
    SubmissionStatus,
    User,
)
from ..security import require
from ..serializers import assignment_data, iso, submission_data
from ..services.distribution import proposals
from ..services.status import transition

router = APIRouter(prefix="/methodist", tags=["methodist"])
methodist_guard = require(Role.METHODIST)


class DistributionItem(BaseModel):
    submission_id: UUID
    reviewer_id: UUID
    explanation: str = "Назначено методистом"


class DistributionApply(BaseModel):
    assignments: list[DistributionItem]


class ReassignPayload(BaseModel):
    reviewer_id: UUID


class CourseUpdate(BaseModel):
    reviewer_capacity: int = Field(ge=1, le=100)
    tone_of_voice: dict


class RubricCreate(BaseModel):
    criteria: list[dict]
    pass_score: float = Field(ge=0)
    note: str = ""


def feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(404, "Раздел выключен фиче-флагом")


@router.get("/dashboard")
def dashboard(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> dict:
    del user
    submissions = list(db.scalars(select(Submission)))
    counts = Counter(item.status for item in submissions)
    active_assignments = list(
        db.scalars(select(ReviewAssignment).where(ReviewAssignment.is_active.is_(True)))
    )
    reviewer_counts = Counter(item.reviewer_id for item in active_assignments)
    reviewers = list(db.scalars(select(User).where(User.role == Role.REVIEWER)))
    completed = [item for item in submissions if item.status == SubmissionStatus.COMPLETED]
    return {
        "demo_data": True,
        "metrics": {
            "total": 40,
            "completed": 27,
            "overdue": 3,
            "average_hours": 18.4,
        },
        "funnel": [
            {"status": status, "count": counts.get(status, 0)}
            for status in SubmissionStatus
        ],
        "reviewers": [
            {
                "id": str(reviewer.id),
                "name": reviewer.full_name,
                "active": reviewer_counts[reviewer.id],
                "capacity": 12,
                "available": reviewer.is_available,
            }
            for reviewer in reviewers
        ],
        "live_records": len(submissions),
        "live_completed": len(completed),
    }


@router.get("/distribution")
def distribution(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    del user
    feature(settings.feature_distribution)
    result = []
    for proposal in proposals(db):
        submission = proposal["submission"]
        reviewer = proposal["reviewer"]
        result.append(
            {
                "submission": submission_data(submission),
                "reviewer": {
                    "id": str(reviewer.id), "name": reviewer.full_name
                } if reviewer else None,
                "explanation": proposal["explanation"],
            }
        )
    return result


def assign_one(db: Session, item: DistributionItem, actor: User) -> None:
    submission = db.get(Submission, item.submission_id)
    reviewer = db.get(User, item.reviewer_id)
    if not submission or not reviewer or reviewer.role != Role.REVIEWER:
        raise HTTPException(422, "Работа или ревьюер не найдены")
    if submission.status == SubmissionStatus.COMPLETED:
        raise HTTPException(409, "Завершённую работу нельзя переназначить")
    if not reviewer.is_available:
        raise HTTPException(409, f"Ревьюер {reviewer.full_name} недоступен")
    old = list(
        db.scalars(
            select(ReviewAssignment).where(
                ReviewAssignment.submission_id == submission.id,
                ReviewAssignment.is_active.is_(True),
            )
        )
    )
    for row in old:
        row.is_active = False
    db.add(
        ReviewAssignment(
            submission_id=submission.id,
            reviewer_id=reviewer.id,
            proposed_by="system",
            explanation=item.explanation,
            approved_by=actor.id,
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


@router.post("/distribution/apply")
def apply_distribution(
    payload: DistributionApply,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_distribution)
    for item in payload.assignments:
        assign_one(db, item, user)
    db.commit()
    return {"ok": True, "assigned": len(payload.assignments)}


@router.get("/reviewers")
def reviewers(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    del user
    rows = db.scalars(select(User).where(User.role == Role.REVIEWER).order_by(User.full_name))
    return [
        {
            "id": str(row.id),
            "name": row.full_name,
            "specialization": row.specialization,
            "available": row.is_available,
        }
        for row in rows
    ]


@router.get("/submissions")
def registry(
    status: str | None = Query(default=None),
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> list[dict]:
    del user
    statement = select(Submission).order_by(Submission.submitted_at.desc())
    if status:
        statement = statement.where(Submission.status == status)
    rows = list(db.scalars(statement))
    result = []
    for row in rows:
        assignment = db.scalar(
            select(ReviewAssignment).where(
                ReviewAssignment.submission_id == row.id,
                ReviewAssignment.is_active.is_(True),
            )
        )
        data = submission_data(row, assignment.reviewer.full_name if assignment else None)
        review = db.scalar(select(Review).where(Review.submission_id == row.id))
        data["ai_status"] = review.ai_status if review else "pending"
        result.append(data)
    return result


@router.patch("/submissions/{submission_id}/reviewer")
def reassign(
    submission_id: UUID,
    payload: ReassignPayload,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    assign_one(
        db,
        DistributionItem(
            submission_id=submission_id,
            reviewer_id=payload.reviewer_id,
            explanation="Переназначено методистом вручную",
        ),
        user,
    )
    db.commit()
    return {"ok": True}


@router.get("/assignments")
def assignments(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    del user
    rows = db.scalars(select(Assignment).order_by(Assignment.created_at.desc()))
    result = []
    for row in rows:
        rubric = db.get(RubricVersion, row.current_rubric_version_id)
        data = assignment_data(row, rubric)
        data["rubric_version"] = rubric.version if rubric else None
        data["rubric_note"] = rubric.note if rubric else ""
        result.append(data)
    return result


@router.post("/assignments/{assignment_id}/rubrics", status_code=201)
def publish_rubric(
    assignment_id: UUID,
    payload: RubricCreate,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    current_version = db.scalar(
        select(func.max(RubricVersion.version)).where(RubricVersion.assignment_id == assignment.id)
    ) or 0
    max_score = sum(float(item.get("max_score", 0)) for item in payload.criteria)
    if payload.pass_score > max_score:
        raise HTTPException(422, "Проходной балл превышает максимум")
    rubric = RubricVersion(
        assignment_id=assignment.id,
        version=current_version + 1,
        criteria=payload.criteria,
        max_score=max_score,
        pass_score=payload.pass_score,
        author_id=user.id,
        note=payload.note,
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id
    db.commit()
    return {"id": str(rubric.id), "version": rubric.version, "max_score": rubric.max_score}


@router.get("/analytics")
def analytics(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> dict:
    del user
    feature(settings.feature_analytics)
    live = db.execute(
        select(ReviewItem.criterion_title, ReviewItem.reviewer_action, func.count())
        .group_by(ReviewItem.criterion_title, ReviewItem.reviewer_action)
    ).all()
    return {
        "demo_data": True,
        "criteria": [
            {"title": "Регистрация лучшей модели", "correction_rate": 38, "reviews": 40},
            {"title": "Выводы по экспериментам", "correction_rate": 31, "reviews": 40},
            {"title": "Воспроизводимость", "correction_rate": 18, "reviews": 40},
            {"title": "Трекинг экспериментов", "correction_rate": 7, "reviews": 40},
        ],
        "weekly": [
            {"week": "11 авг", "ai_agreement": 71, "review_time": 27},
            {"week": "18 авг", "ai_agreement": 76, "review_time": 23},
            {"week": "25 авг", "ai_agreement": 82, "review_time": 18},
            {"week": "1 сен", "ai_agreement": 84, "review_time": 16},
        ],
        "live_actions": [
            {"criterion": title, "action": action, "count": count}
            for title, action, count in live
        ],
    }


@router.get("/course")
def get_course(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> dict:
    del user
    course = db.scalar(select(Course).order_by(Course.created_at))
    if not course:
        raise HTTPException(404, "Курс не найден")
    return {
        "id": str(course.id),
        "title": course.title,
        "reviewer_capacity": course.reviewer_capacity,
        "tone_of_voice": course.tone_of_voice,
    }


@router.patch("/course")
def update_course(
    payload: CourseUpdate,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    del user
    course = db.scalar(select(Course).order_by(Course.created_at))
    if not course:
        raise HTTPException(404, "Курс не найден")
    course.reviewer_capacity = payload.reviewer_capacity
    course.tone_of_voice = payload.tone_of_voice
    db.commit()
    return {"ok": True, "updated_at": iso(datetime.now(UTC))}
