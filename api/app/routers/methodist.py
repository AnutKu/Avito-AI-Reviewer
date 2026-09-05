import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import (
    AiRecommendation,
    AiRun,
    Assignment,
    Course,
    Enrollment,
    Review,
    ReviewAssignment,
    Role,
    RubricVersion,
    Submission,
    SubmissionStatus,
    User,
)
from ..security import require
from ..serializers import (
    ai_run_data,
    assignment_data,
    iso,
    recommendation_data,
    submission_data,
)
from ..services import task_ai
from ..services.analytics import course_report, performance_report
from ..services.course_debt import debt_report
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
from ..services.review_pipeline import start_pending_scoring
from ..services.taskcreater_client import TaskCreaterError, TaskCreaterUnavailable

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


class LevelIn(BaseModel):
    """Один уровень градации: сколько баллов и за что именно."""

    points: float = Field(ge=0, le=100)
    label: str = ""
    descriptor: str = ""


class CriterionIn(BaseModel):
    key: str = ""
    title: str = Field(min_length=1)
    max_score: float = Field(gt=0, le=100)
    student_hint: str = ""
    # Скрытая от студента часть критерия. Кабинет её не показывает студенту, но
    # хранит: по ней работают AI-ревьюеры и ей же оперируют правки от прогона.
    description: str = ""
    check_kind: str = ""
    evidence_hint: str = ""
    expected_signals: list[str] = Field(default_factory=list)
    # Градация внутри критерия. Приходит из конструктора заданий, вручную
    # заводить её не обязательно: у рубрики без градации критерий по-прежнему
    # оценивается «сколько-то из максимума».
    levels: list[LevelIn] = Field(default_factory=list)


class AssignmentIn(BaseModel):
    course_id: UUID | None = None
    title: str = Field(min_length=1)
    statement: str = ""
    deadline_at: datetime | None = None
    effort_weight: float = Field(default=1.0, gt=0, le=10)
    submission_channel: str = "github"
    criteria: list[CriterionIn] = Field(min_length=1)
    pass_score: float = Field(default=0, ge=0)
    authoring: dict = Field(default_factory=dict)
    publish: bool = False  # сразу опубликовать (по умолчанию создаётся черновик)


class AssignmentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    statement: str | None = None
    deadline_at: datetime | None = None
    effort_weight: float | None = Field(default=None, gt=0, le=10)
    submission_channel: str | None = None
    authoring: dict | None = None


class PublishPayload(BaseModel):
    published: bool = True


class AiFillPayload(BaseModel):
    """Заполнить или улучшить один блок. Ответ — предложение, не запись."""

    field: str = Field(min_length=1)
    mode: str = "fill"
    current: str = ""
    instruction: str = ""
    context: dict = Field(
        default_factory=dict, description="уже заполненные блоки — как они выглядят в редакторе"
    )


class DraftFromIdeaPayload(BaseModel):
    idea: str = Field(min_length=10)
    track: str = "General"
    task_format: str = "auto"
    total_points: float = Field(default=10, gt=0)
    constraints: str = ""


class AiRunPayload(BaseModel):
    persona_type: str = Field(
        description="student — проверить постановку; reviewer — критерии; both — и то и другое"
    )
    samples: int = Field(
        default=1, ge=1, le=5,
        description="Сколько раз оценить каждое решение — чтобы увидеть разброс самой модели",
    )
    idempotency_key: str | None = Field(default=None, max_length=64)


class CriterionAssistPayload(BaseModel):
    """Достроить критерий до применимого. Ответ — предложение, не запись.

    Пустое название допустимо: тогда агент сам предлагает, что стоит оценивать
    в этом задании, глядя на уже заведённые критерии.
    """

    title: str = ""
    max_score: float = Field(gt=0, le=100)
    student_hint: str = ""
    description: str = ""
    context: dict = Field(default_factory=dict)
    existing: list[str] = Field(default_factory=list)


class RecommendationDecision(BaseModel):
    expected_revision: int | None = None
    value: str = ""  # для «Редактировать»: текст, который подтвердил человек
    reason: str = ""  # для «Отклонить»


def feature(enabled: bool) -> None:
    if not enabled:
        raise HTTPException(404, "Раздел выключен фиче-флагом")


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
    background_tasks: BackgroundTasks,
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
    scoring = start_pending_scoring(db, background_tasks)
    return {
        "ok": True,
        "auto_assign": course.auto_assign,
        "assigned": assigned,
        "scoring_started": len(scoring),
    }


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
    background_tasks: BackgroundTasks,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_distribution)
    for item in payload.assignments:
        assign_one(db, item, user)
    db.commit()
    # У работы появился ревьюер — значит, есть ради кого считать.
    scoring = start_pending_scoring(db, background_tasks)
    return {
        "ok": True,
        "assigned": len(payload.assignments),
        "scoring_started": len(scoring),
    }


@router.get("/reviewers")
def reviewers(user: User = Depends(methodist_guard), db: Session = Depends(get_db)) -> list[dict]:
    del user
    return reviewer_loads(db)


@router.patch("/reviewers/{reviewer_id}")
def set_availability(
    reviewer_id: UUID,
    payload: AvailabilityPayload,
    background_tasks: BackgroundTasks,
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
    start_pending_scoring(db, background_tasks)
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
    background_tasks: BackgroundTasks,
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
    # Работа могла прийти сюда неразобранной — например, её передали раньше,
    # чем прогон успел стартовать. Готовый разбор свип не трогает.
    start_pending_scoring(db, background_tasks)
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
        data = assignment_data(row, rubric, full=True, authoring=True)
        data["rubric_version"] = rubric.version if rubric else None
        data["rubric_note"] = rubric.note if rubric else ""
        data["rubric_versions"] = db.scalar(
            select(func.count())
            .select_from(RubricVersion)
            .where(RubricVersion.assignment_id == row.id)
        ) or 0
        # Сколько работ уйдёт вместе с заданием, если его удалить.
        data["submissions"] = db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(Submission.assignment_id == row.id)
        ) or 0
        last_run = db.scalars(
            select(AiRun).where(AiRun.assignment_id == row.id).order_by(AiRun.created_at.desc())
        ).first()
        data["last_run"] = ai_run_data(last_run) if last_run else None
        result.append(data)
    return result


def _assignment_snapshot(assignment: Assignment) -> dict:
    """Редактируемые поля задания — их версионируем вместе с критериями,
    чтобы «Вернуть» откатывал задание целиком."""

    return {
        "title": assignment.title,
        "statement": assignment.statement,
        "deadline_at": iso(assignment.deadline_at),
        "effort_weight": assignment.effort_weight,
        "submission_channel": assignment.submission_channel,
        "authoring": assignment.authoring or {},
    }


def _criterion_dict(criterion: CriterionIn, seen: set[str]) -> dict:
    slug = re.sub(r"[^a-zа-яё0-9]+", "_", criterion.title.lower(), flags=re.IGNORECASE)
    key = criterion.key.strip() or slug.strip("_")[:40] or "criterion"
    base, n = key, 2
    while key in seen:
        key, n = f"{base}_{n}", n + 1
    seen.add(key)
    # Уровни идут по возрастанию балла: на экране ревьюера это лестница снизу
    # вверх, и порядок из ответа модели на неё полагаться не даёт.
    levels = sorted(criterion.levels, key=lambda level: level.points)
    over = [level.points for level in levels if level.points > criterion.max_score]
    if over:
        raise HTTPException(
            422, f"Критерий «{criterion.title.strip()}»: уровень {over[0]} больше максимума"
        )
    row = {
        "key": key,
        "title": criterion.title.strip(),
        "max_score": float(criterion.max_score),
        "student_hint": criterion.student_hint.strip(),
        "levels": [level.model_dump() for level in levels],
    }
    # Скрытые поля кладём только заполненными: пустой ключ в рубрике ничего не
    # значит, а версии критериев сравниваются по равенству словарей.
    for field in ("description", "check_kind", "evidence_hint", "expected_signals"):
        value = getattr(criterion, field)
        if value:
            row[field] = value.strip() if isinstance(value, str) else value
    return row


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
        authoring=payload.authoring or {},
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
        assignment_snapshot=_assignment_snapshot(assignment),
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


@router.delete("/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: UUID,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Полное удаление задания: версии рубрики, сданные работы и их оценки.

    Разрешено только для неопубликованного задания — публикация и есть тот
    рубеж, за которым удаление становится осознанным: студенты его больше не
    видят, и методист сам решил, что задание в потоке не нужно. Снятые с
    публикации работы удаляются вместе с заданием, вместе с оценками."""

    del user
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    if assignment.published_at is not None:
        raise HTTPException(
            409, "Нельзя удалить опубликованное задание. Сначала снимите его с публикации."
        )

    # Порядок важен: `reviews.rubric_version_id` без ON DELETE, поэтому версии
    # рубрики можно убирать только после того, как ушли ревью вместе с работами.
    submission_ids = list(
        db.scalars(select(Submission.id).where(Submission.assignment_id == assignment_id))
    )
    if submission_ids:
        db.execute(delete(Submission).where(Submission.id.in_(submission_ids)))
        db.flush()
    db.execute(delete(RubricVersion).where(RubricVersion.assignment_id == assignment_id))
    db.delete(assignment)
    db.commit()
    return {"ok": True, "deleted": str(assignment_id), "submissions": len(submission_ids)}


@router.patch("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: UUID,
    payload: AssignmentPatch,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value.strip() if isinstance(value, str) else value)
    db.flush()

    # Правка задания версионируется так же, как правка критериев, — но только
    # если что-то реально изменилось относительно текущей версии рубрики.
    current = db.get(RubricVersion, assignment.current_rubric_version_id)
    snapshot = _assignment_snapshot(assignment)
    bumped = None
    if current and current.assignment_snapshot != snapshot:
        latest = db.scalar(
            select(func.max(RubricVersion.version)).where(
                RubricVersion.assignment_id == assignment.id
            )
        ) or 0
        bumped = RubricVersion(
            assignment_id=assignment.id,
            version=latest + 1,
            criteria=current.criteria,
            max_score=current.max_score,
            pass_score=current.pass_score,
            author_id=user.id,
            note="Правка задания",
            assignment_snapshot=snapshot,
        )
        db.add(bumped)
        db.flush()
        assignment.current_rubric_version_id = bumped.id
    db.commit()
    version = bumped.version if bumped else (current.version if current else None)
    return {"ok": True, "rubric_version": version, "versioned": bumped is not None}


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
        note=payload.note or "Правка критериев",
        assignment_snapshot=_assignment_snapshot(assignment),
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id
    db.commit()
    return {"id": str(rubric.id), "version": rubric.version, "max_score": rubric.max_score}


def _rubric_row(rubric: RubricVersion, current_id: UUID | None, author: str | None) -> dict:
    return {
        "id": str(rubric.id),
        "version": rubric.version,
        "criteria": rubric.criteria,
        "max_score": rubric.max_score,
        "pass_score": rubric.pass_score,
        "note": rubric.note,
        "published_at": iso(rubric.published_at),
        "author": author,
        "is_current": rubric.id == current_id,
        "assignment_snapshot": rubric.assignment_snapshot or {},
    }


@router.get("/assignments/{assignment_id}/rubrics")
def rubric_versions(
    assignment_id: UUID,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> list[dict]:
    """История версий рубрики, новые сверху — для отката «как в гите»."""

    del user
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    rows = list(
        db.scalars(
            select(RubricVersion)
            .where(RubricVersion.assignment_id == assignment_id)
            .order_by(RubricVersion.version.desc())
        )
    )
    author_ids = {row.author_id for row in rows if row.author_id}
    authors = (
        dict(
            db.execute(
                select(User.id, User.full_name).where(User.id.in_(author_ids))
            ).all()
        )
        if author_ids
        else {}
    )
    return [
        _rubric_row(row, assignment.current_rubric_version_id, authors.get(row.author_id))
        for row in rows
    ]


@router.post("/assignments/{assignment_id}/rubrics/{version}/restore")
def restore_rubric(
    assignment_id: UUID,
    version: int,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Откат к прошлой версии рубрики — как `git revert`: содержимое старой
    версии переносится в НОВУЮ. Номера версий только растут, история цела,
    уже выставленные по старым версиям оценки не трогаются."""

    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    target = db.scalar(
        select(RubricVersion).where(
            RubricVersion.assignment_id == assignment_id,
            RubricVersion.version == version,
        )
    )
    if not target:
        raise HTTPException(404, "Версия рубрики не найдена")
    if target.id == assignment.current_rubric_version_id:
        raise HTTPException(409, "Эта версия уже активна")
    latest = db.scalar(
        select(func.max(RubricVersion.version)).where(
            RubricVersion.assignment_id == assignment_id
        )
    ) or 0
    # Откат задания целиком: возвращаем и условие/срок из снимка той версии.
    snap = target.assignment_snapshot or {}
    if snap.get("title"):
        assignment.title = snap["title"]
        assignment.statement = snap.get("statement", assignment.statement)
        assignment.effort_weight = snap.get("effort_weight", assignment.effort_weight)
        assignment.submission_channel = snap.get(
            "submission_channel", assignment.submission_channel
        )
        assignment.authoring = snap.get("authoring", assignment.authoring)
        raw_deadline = snap.get("deadline_at")
        assignment.deadline_at = (
            datetime.fromisoformat(raw_deadline) if raw_deadline else None
        )
        db.flush()
    restored = RubricVersion(
        assignment_id=assignment_id,
        version=latest + 1,
        criteria=target.criteria,
        max_score=target.max_score,
        pass_score=target.pass_score,
        author_id=user.id,
        note=f"Откат к версии v{version}",
        assignment_snapshot=_assignment_snapshot(assignment),
    )
    db.add(restored)
    db.flush()
    assignment.current_rubric_version_id = restored.id
    db.commit()
    return {"id": str(restored.id), "version": restored.version, "restored_from": version}


@router.get("/analytics")
def analytics(
    course_id: UUID | None = None,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Аналитика курса: обзор потока, качество проверки и образовательный долг.

    Всё считается по живым записям. Блок `quality` приезжает только когда
    включён фиче-флаг аналитики, `debt` — свой флаг: разбор долга опирается на
    накопленную статистику, и на пустом курсе его лучше не показывать вовсе."""

    del user
    report = course_report(db, course_id, with_quality=settings.feature_analytics)
    if settings.feature_course_debt:
        report["debt"] = debt_report(db, course_id)
    return report


@router.get("/performance")
def performance(
    course_id: UUID | None = None,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Успеваемость: матрица «студент × опубликованное задание»."""

    del user
    return performance_report(db, course_id)


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


# --------------------------------------------------------------------------- #
#  AI-инструменты внутри работы над заданием
#
#  Помощь по блоку и проверка на персонах — не отдельный раздел и не отдельное
#  хранилище: задание всё время лежит здесь, движок только считает. Поэтому в
#  task-creater ходит сервер, а не браузер, и ни один ответ агента не попадает
#  в задание без явного решения человека.
# --------------------------------------------------------------------------- #


def _bump_rubric(
    db: Session,
    assignment: Assignment,
    *,
    criteria: list[dict],
    pass_score: float,
    author_id: UUID | None,
    note: str,
) -> RubricVersion:
    """Новая версия рубрики. Опубликованная версия не правится никогда."""

    latest = db.scalar(
        select(func.max(RubricVersion.version)).where(RubricVersion.assignment_id == assignment.id)
    ) or 0
    rubric = RubricVersion(
        assignment_id=assignment.id,
        version=latest + 1,
        criteria=criteria,
        max_score=sum(float(item.get("max_score", 0)) for item in criteria),
        pass_score=pass_score,
        author_id=author_id,
        note=note,
        assignment_snapshot=_assignment_snapshot(assignment),
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id
    return rubric


def _assignment_or_404(db: Session, assignment_id: UUID) -> Assignment:
    feature(settings.feature_rubric_builder)
    assignment = db.get(Assignment, assignment_id)
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    return assignment


def _engine_call(action, *args, **kwargs):
    """Единая трансляция отказов движка в 503: конструктор — внешний сервис."""

    try:
        return action(*args, **kwargs)
    except TaskCreaterUnavailable as exc:
        raise HTTPException(503, "Конструктор заданий недоступен. Черновик сохранён.") from exc
    except TaskCreaterError as exc:
        raise HTTPException(502, f"Конструктор заданий ответил ошибкой: {exc}") from exc


@router.post("/ai-fill")
def ai_fill(payload: AiFillPayload, user: User = Depends(methodist_guard)) -> dict:
    """Предложение по одному блоку. Ничего не сохраняет — вставляет человек.

    Контекст приходит от редактора, а не из базы, и это важно: помощник должен
    видеть то, что методист набрал прямо сейчас, включая несохранённое. Поэтому
    же ручка не привязана к заданию — она работает и для ещё не созданного.
    """

    del user
    feature(settings.feature_rubric_builder)
    context = {k: v for k, v in payload.context.items() if isinstance(v, str) and v}
    context.pop(payload.field, None)
    out = _engine_call(
        task_ai.client().assist_field,
        field=task_ai.FIELD_TITLES.get(payload.field, payload.field),
        mode="improve" if payload.mode == "improve" else "fill",
        current=payload.current,
        instruction=payload.instruction,
        context=context,
    )
    return {"field": payload.field, "proposed": out.get("proposed", ""), "note": out.get("note", "")}


@router.post("/ai-criterion")
def ai_criterion(payload: CriterionAssistPayload, user: User = Depends(methodist_guard)) -> dict:
    """Достроить критерий: признаки сильного ответа и уровни с порогами.

    Без них ревьюер не может поставить балл однозначно — и прогон валидации
    возвращает это замечанием чаще всего остального. Дешевле попросить агента
    сразу, чем чинить потом правкой по итогам прогона.
    """

    del user
    feature(settings.feature_rubric_builder)
    out = _engine_call(
        task_ai.client().assist_criterion,
        title=payload.title,
        max_points=payload.max_score,
        student_hint=payload.student_hint,
        description=payload.description,
        task_context={k: v for k, v in payload.context.items() if isinstance(v, str) and v},
        existing=[name for name in payload.existing if name],
    )
    return task_ai.from_engine_criterion(out)


@router.post("/assignments/draft-from-idea", status_code=202)
def draft_from_idea(payload: DraftFromIdeaPayload, user: User = Depends(methodist_guard)) -> dict:
    """Ставит сборку черновика в очередь и сразу отдаёт номер задачи.

    Синхронного ответа здесь быть не может: задание с критериями и эталоном
    собирается одну-две минуты, и запрос успевал упереться в таймаут прокси
    (кабинет показывал 504 вместо результата). Готовность спрашивают отдельной
    ручкой — страницу при этом можно закрыть, сборка идёт на сервере.

    В кабинете при этом ничего не создаётся: результат — предпросмотр, который
    методист правит и сохраняет сам. Иначе кнопка «Сформировать» плодила бы
    мусорные задания на каждый эксперимент.
    """

    del user
    feature(settings.feature_rubric_builder)
    out = _engine_call(
        task_ai.client().generate_task,
        {
            "idea": payload.idea,
            "track": payload.track,
            "task_format": payload.task_format,
            "total_points": payload.total_points,
            "constraints": payload.constraints or None,
            "language": "ru",
        },
    )
    return {"job_id": out["id"], "status": "generating", "track": payload.track}


@router.get("/assignments/draft-from-idea/{job_id}")
def draft_from_idea_status(
    job_id: str,
    track: str = "",
    total_points: float = 10,
    user: User = Depends(methodist_guard),
) -> dict:
    """Готовность черновика. `ready` — в ответе лежит предпросмотр."""

    del user
    feature(settings.feature_rubric_builder)
    out = _engine_call(task_ai.client().get_task, job_id)
    state = out.get("gen_status")
    if state == "generating":
        return {"status": "generating"}
    if state == "generation_failed":
        return {"status": "failed", "error": out.get("gen_error") or "Сборка черновика не удалась"}
    draft = task_ai.draft_from_engine_task(out, track=track, total_points=total_points)
    return {"status": "ready", "draft": draft}


@router.post("/assignments/{assignment_id}/ai-runs", status_code=202)
def start_ai_run(
    assignment_id: UUID,
    payload: AiRunPayload,
    background_tasks: BackgroundTasks,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Запуск проверки на персонах ОДНОГО типа.

    Второй тип запускается отдельно и после — по актуальной на тот момент
    ревизии. Сам по себе прогон ничего не публикует и ничего не переписывает.
    """

    assignment = _assignment_or_404(db, assignment_id)
    if payload.persona_type not in task_ai.PERSONA_TYPES:
        raise HTTPException(422, "Тип персон: student или reviewer")
    rubric = db.get(RubricVersion, assignment.current_rubric_version_id)
    if not rubric or not rubric.criteria:
        raise HTTPException(422, "Нужен хотя бы один критерий — иначе проверять нечего")

    existing = task_ai.reusable_run(db, assignment.id, payload.idempotency_key)
    if existing and (payload.idempotency_key or existing.status in task_ai.OPEN_STATUSES):
        return ai_run_data(existing)

    run = task_ai.create_run(
        db,
        assignment,
        persona_type=payload.persona_type,
        idempotency_key=payload.idempotency_key,
        created_by=user.id,
        samples=payload.samples,
    )
    task_ai.start(db, run, background_tasks)
    return ai_run_data(run)


@router.get("/assignments/{assignment_id}/ai-runs")
def ai_runs(
    assignment_id: UUID,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> list[dict]:
    """История прогонов задания, новые сверху."""

    del user
    _assignment_or_404(db, assignment_id)
    rows = db.scalars(
        select(AiRun).where(AiRun.assignment_id == assignment_id).order_by(AiRun.created_at.desc())
    )
    return [ai_run_data(row) for row in rows]


@router.get("/ai-runs/{run_id}")
def ai_run(
    run_id: UUID,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Один прогон с рекомендациями. Отсюда же экран берёт прогресс."""

    del user
    feature(settings.feature_rubric_builder)
    run = db.get(AiRun, run_id)
    if not run:
        raise HTTPException(404, "Прогон не найден")
    assignment = db.get(Assignment, run.assignment_id)
    data = ai_run_data(run, run.recommendations)
    # Результат всегда относится к своей ревизии: если задание правили после
    # прогона, экран обязан это сказать, а не выдавать разбор за актуальный.
    data["assignment_revision"] = task_ai.current_revision(db, assignment) if assignment else None
    data["stale"] = data["assignment_revision"] not in (None, run.revision)
    return data


def _decision(db: Session, recommendation_id: UUID, expected_revision: int | None):
    feature(settings.feature_rubric_builder)
    row = db.get(AiRecommendation, recommendation_id)
    if not row:
        raise HTTPException(404, "Рекомендация не найдена")
    run = db.get(AiRun, row.run_id)
    assignment = db.get(Assignment, run.assignment_id) if run else None
    if not assignment:
        raise HTTPException(404, "Задание не найдено")
    if row.status != "new":
        raise HTTPException(409, "По этой рекомендации решение уже принято")
    # Защита от гонки: пока прогон обсуждали, поле могли поменять в другой
    # вкладке. Тихо перезаписать чужую правку хуже, чем показать расхождение.
    revision = task_ai.current_revision(db, assignment)
    if expected_revision is not None and expected_revision != revision:
        raise HTTPException(
            409,
            f"Задание изменилось с момента прогона (ревизия {revision}). "
            "Откройте сравнение и примените правку вручную.",
        )
    return row, assignment


def _apply_recommendation(
    db: Session, row: AiRecommendation, assignment: Assignment, value: str, author_id: UUID
) -> None:
    rubric = db.get(RubricVersion, assignment.current_rubric_version_id)
    if row.target_type == "criterion" and (row.payload or {}).get("operation"):
        criteria = task_ai.criteria_after(rubric.criteria if rubric else [], row.payload, value)
        _bump_rubric(
            db,
            assignment,
            criteria=criteria,
            pass_score=rubric.pass_score if rubric else 0,
            author_id=author_id,
            note=f"Правка по рекомендации AI ({row.target_id or 'критерий'})",
        )
        return
    if row.target_type == "criterion":  # подсказка студенту у конкретного критерия
        criteria = [dict(item) for item in (rubric.criteria if rubric else [])]
        for item in criteria:
            if item.get("key") == row.target_id:
                item[row.target_field or "student_hint"] = value
        _bump_rubric(
            db,
            assignment,
            criteria=criteria,
            pass_score=rubric.pass_score if rubric else 0,
            author_id=author_id,
            note="Правка критерия по рекомендации AI",
        )
        return

    field = row.target_field or "statement"
    if field == "statement":
        assignment.statement = value
    else:
        assignment.authoring = {**(assignment.authoring or {}), field: value}
    db.flush()
    _bump_rubric(
        db,
        assignment,
        criteria=rubric.criteria if rubric else [],
        pass_score=rubric.pass_score if rubric else 0,
        author_id=author_id,
        note="Правка задания по рекомендации AI",
    )


@router.post("/ai-recommendations/{recommendation_id}/apply")
def apply_recommendation(
    recommendation_id: UUID,
    payload: RecommendationDecision,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Принять предложение агента как есть."""

    row, assignment = _decision(db, recommendation_id, payload.expected_revision)
    if not row.proposed_value:
        raise HTTPException(422, "У этой рекомендации нет готового текста — отредактируйте вручную")
    _apply_recommendation(db, row, assignment, row.proposed_value, user.id)
    row.status = "applied"
    row.final_value = row.proposed_value
    row.decided_at = datetime.now(UTC)
    db.commit()
    return recommendation_data(row)


@router.post("/ai-recommendations/{recommendation_id}/edit")
def edit_recommendation(
    recommendation_id: UUID,
    payload: RecommendationDecision,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Принять свой вариант вместо предложенного.

    Исходное предложение остаётся в `proposed_value`: разница между тем, что
    предложил агент, и тем, что оставил человек, — единственный честный
    материал для оценки качества самих рекомендаций.
    """

    if not payload.value.strip():
        raise HTTPException(422, "Пустой текст правки")
    row, assignment = _decision(db, recommendation_id, payload.expected_revision)
    _apply_recommendation(db, row, assignment, payload.value, user.id)
    row.status = "edited"
    row.final_value = payload.value
    row.decided_at = datetime.now(UTC)
    db.commit()
    return recommendation_data(row)


@router.post("/ai-recommendations/{recommendation_id}/reject")
def reject_recommendation(
    recommendation_id: UUID,
    payload: RecommendationDecision,
    user: User = Depends(methodist_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Отклонить. Задание не меняется, рекомендация остаётся видимой."""

    del user
    row, _ = _decision(db, recommendation_id, None)
    row.status = "rejected"
    row.rejection_reason = payload.reason or None
    row.decided_at = datetime.now(UTC)
    db.commit()
    return recommendation_data(row)
