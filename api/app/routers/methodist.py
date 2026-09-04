import re
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    Assignment,
    Course,
    Enrollment,
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
from ..services.assignment import (
    assign_submission,
    auto_assign_enabled,
    auto_distribute,
    auto_reassign_from,
)
from ..services.distribution import (
    proposals,
    rebalance,
    reviewer_headroom,
    reviewer_loads,
)

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
    force: bool = False  # назначить, даже если у ревьюера исчерпан кап


class RebalancePayload(BaseModel):
    reviewer_ids: list[UUID] = Field(min_length=1)
    set_unavailable: bool = False  # заодно снять этих ревьюеров с распределения


class AvailabilityPayload(BaseModel):
    is_available: bool


class AutoAssignPayload(BaseModel):
    enabled: bool


class CourseUpdate(BaseModel):
    reviewer_capacity: int = Field(ge=1, le=100)
    tone_of_voice: dict


class RubricCreate(BaseModel):
    criteria: list[dict]
    pass_score: float = Field(ge=0)
    note: str = ""


class CriterionIn(BaseModel):
    key: str = ""
    title: str = Field(min_length=1)
    max_score: float = Field(gt=0, le=100)
    student_hint: str = ""


class AssignmentIn(BaseModel):
    course_id: UUID | None = None
    title: str = Field(min_length=1)
    statement: str = ""
    deadline_at: datetime | None = None
    effort_weight: float = Field(default=1.0, gt=0, le=10)
    submission_channel: str = "github"
    criteria: list[CriterionIn] = Field(min_length=1)
    pass_score: float = Field(default=0, ge=0)
    publish: bool = False  # сразу опубликовать (по умолчанию создаётся черновик)


class AssignmentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    statement: str | None = None
    deadline_at: datetime | None = None
    effort_weight: float | None = Field(default=None, gt=0, le=10)
    submission_channel: str | None = None


class PublishPayload(BaseModel):
    published: bool = True


def feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(404, "Раздел выключен фиче-флагом")


@router.get("/dashboard")
def dashboard(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> dict:
    del user
    submissions = list(db.scalars(select(Submission)))
    counts = Counter(item.status for item in submissions)
    loads = reviewer_loads(db)
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
                "id": row["id"],
                "name": row["name"],
                "active": row["load"],
                "capacity": row["capacity"],
                "available": row["available"],
            }
            for row in loads
        ],
        "live_records": len(submissions),
        "live_completed": len(completed),
    }


def _proposal_row(proposal: dict) -> dict:
    reviewer = proposal["reviewer"]
    return {
        "submission": submission_data(proposal["submission"]),
        "reviewer": {"id": str(reviewer.id), "name": reviewer.full_name} if reviewer else None,
        "explanation": proposal["explanation"],
        "over_capacity": proposal.get("over_capacity", False),
    }


_ASSIGNED_ON_SCREEN = (SubmissionStatus.ASSIGNED, SubmissionStatus.IN_REVIEW)


def _assigned_rows(db: Session) -> list[dict]:
    """Уже распределённые работы — их можно передать другому ревьюеру."""

    rows = db.execute(
        select(Submission, ReviewAssignment)
        .join(ReviewAssignment, ReviewAssignment.submission_id == Submission.id)
        .where(
            ReviewAssignment.is_active.is_(True),
            ReviewAssignment.approved_at.is_not(None),
            Submission.status.in_(_ASSIGNED_ON_SCREEN),
        )
        .order_by(Submission.submitted_at)
    ).all()
    return [
        {
            "submission": submission_data(submission, assignment.reviewer.full_name),
            "reviewer": {
                "id": str(assignment.reviewer_id),
                "name": assignment.reviewer.full_name,
            },
            "explanation": assignment.explanation,
            "status": submission.status,
        }
        for submission, assignment in rows
    ]


@router.get("/distribution")
def distribution(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> dict:
    del user
    feature(settings.feature_distribution)
    return {
        "auto_assign": auto_assign_enabled(db),
        "reviewers": reviewer_loads(db),
        "waiting": [_proposal_row(proposal) for proposal in proposals(db)],
        "assigned": _assigned_rows(db),
    }


@router.post("/distribution/auto")
def set_auto_assign(
    payload: AutoAssignPayload,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_distribution)
    course = db.scalar(select(Course).order_by(Course.created_at))
    if not course:
        raise HTTPException(404, "Курс не найден")
    course.auto_assign = payload.enabled
    assigned = auto_distribute(db, actor_id=user.id) if payload.enabled else 0
    db.commit()
    return {"ok": True, "auto_assign": course.auto_assign, "assigned": assigned}


@router.post("/distribution/rebalance")
def rebalance_distribution(
    payload: RebalancePayload,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> list[dict]:
    del user
    feature(settings.feature_distribution)
    rows = rebalance(db, payload.reviewer_ids, set_unavailable=payload.set_unavailable)
    if payload.set_unavailable:
        db.commit()
    return [_proposal_row(row) for row in rows]


def assign_one(
    db: Session, item: DistributionItem, actor: User, *, enforce_capacity: bool = False
) -> None:
    submission = db.get(Submission, item.submission_id)
    reviewer = db.get(User, item.reviewer_id)
    if not submission or not reviewer or reviewer.role != Role.REVIEWER:
        raise HTTPException(422, "Работа или ревьюер не найдены")
    if submission.status == SubmissionStatus.COMPLETED:
        raise HTTPException(409, "Завершённую работу нельзя переназначить")
    if not reviewer.is_available:
        raise HTTPException(409, f"Ревьюер {reviewer.full_name} недоступен")
    if enforce_capacity:
        already_here = db.scalar(
            select(ReviewAssignment.id).where(
                ReviewAssignment.submission_id == submission.id,
                ReviewAssignment.reviewer_id == reviewer.id,
                ReviewAssignment.is_active.is_(True),
            )
        )
        headroom = reviewer_headroom(
            db, reviewer.id, float(submission.assignment.effort_weight or 1.0)
        )
        if headroom and not headroom["fits"] and not already_here:
            raise HTTPException(
                409,
                f"У ревьюера {reviewer.full_name} нет свободного лимита "
                f"({headroom['load']:.1f}/{headroom['capacity']:.0f}). "
                "Поставьте флаг «всё равно назначить», чтобы превысить кап.",
            )
    assign_submission(
        db, submission, reviewer, explanation=item.explanation, actor_id=actor.id
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
    return reviewer_loads(db)


@router.patch("/reviewers/{reviewer_id}")
def set_availability(
    reviewer_id: UUID,
    payload: AvailabilityPayload,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    reviewer = db.get(User, reviewer_id)
    if not reviewer or reviewer.role != Role.REVIEWER:
        raise HTTPException(404, "Ревьюер не найден")
    reviewer.is_available = payload.is_available
    result: dict = {"ok": True, "id": str(reviewer.id), "available": reviewer.is_available}
    if not payload.is_available:
        # работы снятого ревьюера не должны зависнуть на нём
        if auto_assign_enabled(db):
            result["reassigned"] = auto_reassign_from(db, [reviewer_id], actor_id=user.id)
        else:
            result["proposals"] = [_proposal_row(row) for row in rebalance(db, [reviewer_id])]
    db.commit()
    return result


@router.get("/submissions")
def registry(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    """Реестр работ, сгруппированный по опубликованным заданиям.

    В каждой группе — строка на КАЖДОГО студента курса, включая тех, кто ещё
    не сдал (`status = "not_submitted"`)."""

    del user
    published = list(
        db.scalars(
            select(Assignment)
            .where(Assignment.published_at.is_not(None))
            .order_by(Assignment.created_at.desc())
        )
    )
    groups = []
    for assignment in published:
        students = list(
            db.scalars(
                select(User)
                .join(Enrollment, Enrollment.user_id == User.id)
                .where(Enrollment.course_id == assignment.course_id, User.role == Role.STUDENT)
                .order_by(User.full_name)
            )
        )
        subs = {
            sub.student_id: sub
            for sub in db.scalars(
                select(Submission).where(Submission.assignment_id == assignment.id)
            )
        }
        rows, submitted, completed, overdue = [], 0, 0, 0
        for student in students:
            sub = subs.get(student.id)
            if sub is None:
                rows.append(
                    {
                        "student": student.full_name,
                        "student_id": str(student.id),
                        "status": "not_submitted",
                        "submission_id": None,
                        "reviewer": None,
                        "submitted_at": None,
                        "is_overdue": False,
                        "ai_status": None,
                    }
                )
                continue
            submitted += 1
            completed += sub.status == SubmissionStatus.COMPLETED
            overdue += bool(sub.is_overdue)
            active = db.scalar(
                select(ReviewAssignment).where(
                    ReviewAssignment.submission_id == sub.id,
                    ReviewAssignment.is_active.is_(True),
                )
            )
            review = db.scalar(select(Review).where(Review.submission_id == sub.id))
            rows.append(
                {
                    "student": student.full_name,
                    "student_id": str(student.id),
                    "status": sub.status,
                    "submission_id": str(sub.id),
                    "reviewer": active.reviewer.full_name if active else None,
                    "submitted_at": iso(sub.submitted_at),
                    "is_overdue": sub.is_overdue,
                    "ai_status": review.ai_status if review else "pending",
                }
            )
        groups.append(
            {
                "assignment": {
                    "id": str(assignment.id),
                    "title": assignment.title,
                    "course": assignment.course.title,
                    "deadline_at": iso(assignment.deadline_at),
                    "published_at": iso(assignment.published_at),
                },
                "stats": {
                    "students": len(students),
                    "submitted": submitted,
                    "completed": completed,
                    "not_submitted": len(students) - submitted,
                    "overdue": overdue,
                },
                "rows": rows,
            }
        )
    return groups


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
        enforce_capacity=not payload.force,
    )
    db.commit()
    return {"ok": True}


@router.get("/courses")
def courses(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    del user
    return [
        {"id": str(row.id), "title": row.title, "specialization": row.specialization}
        for row in db.scalars(select(Course).order_by(Course.created_at))
    ]


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


def _criterion_dict(criterion: CriterionIn, seen: set[str]) -> dict:
    slug = re.sub(r"[^a-zа-яё0-9]+", "_", criterion.title.lower(), flags=re.IGNORECASE)
    key = criterion.key.strip() or slug.strip("_")[:40] or "criterion"
    base, n = key, 2
    while key in seen:
        key, n = f"{base}_{n}", n + 1
    seen.add(key)
    return {
        "key": key,
        "title": criterion.title.strip(),
        "max_score": float(criterion.max_score),
        "student_hint": criterion.student_hint.strip(),
    }


@router.post("/assignments", status_code=201)
def create_assignment(
    payload: AssignmentIn,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_rubric_builder)
    course = (
        db.get(Course, payload.course_id)
        if payload.course_id
        else db.scalar(select(Course).order_by(Course.created_at))
    )
    if not course:
        raise HTTPException(404, "Курс не найден")
    seen: set[str] = set()
    criteria = [_criterion_dict(item, seen) for item in payload.criteria]
    max_score = sum(item["max_score"] for item in criteria)
    if payload.pass_score > max_score:
        raise HTTPException(422, "Проходной балл превышает максимум")

    assignment = Assignment(
        course_id=course.id,
        title=payload.title.strip(),
        statement=payload.statement,
        deadline_at=payload.deadline_at,
        effort_weight=payload.effort_weight,
        submission_channel=payload.submission_channel,
        published_at=datetime.now(UTC) if payload.publish else None,
    )
    db.add(assignment)
    db.flush()
    rubric = RubricVersion(
        assignment_id=assignment.id,
        version=1,
        criteria=criteria,
        max_score=max_score,
        pass_score=payload.pass_score,
        author_id=user.id,
        note="Первая версия",
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id
    db.commit()
    return {
        "id": str(assignment.id),
        "rubric_version": 1,
        "max_score": max_score,
        "published": assignment.published_at is not None,
    }


@router.post("/assignments/{assignment_id}/publish")
def publish_assignment(
    assignment_id: UUID,
    payload: PublishPayload,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    del user
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    if payload.published and not assignment.current_rubric_version_id:
        raise HTTPException(422, "Нельзя опубликовать задание без рубрики")
    assignment.published_at = datetime.now(UTC) if payload.published else None
    db.commit()
    return {"ok": True, "published": assignment.published_at is not None}


@router.patch("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: UUID,
    payload: AssignmentPatch,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    del user
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return {"ok": True}


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
        "auto_assign": course.auto_assign,
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
