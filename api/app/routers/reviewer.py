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
    AiDetection,
    AiSignal,
    AiStatus,
    BlitzEvent,
    BlitzSession,
    BlitzStatus,
    FraudDecision,
    FraudVerdict,
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
from ..serializers import blitz_data, detection_data, iso, review_data, submission_data
from ..services import blitz_telemetry
from ..services.status import overdue_risk, transition
from ..services.ai_reviewer_client import (
    AiReviewerClient,
    AiReviewerError,
    AiReviewerUnavailable,
)
from ..services.review_pipeline import (
    expire_blitz_sessions,
    fail_stale_detections,
    fail_stale_reviews,
    is_stale,
    is_stale_detection,
    persist_call,
    run_detection,
    run_review,
)

router = APIRouter(prefix="/reviewer", tags=["reviewer"])
reviewer_guard = require(Role.REVIEWER)


class ItemDecision(BaseModel):
    action: Literal["accepted", "changed", "rejected"]
    final_score: float | None = Field(default=None, ge=0)
    comment: str = ""


class SignalDecisionPayload(BaseModel):
    decision: Literal["confirmed", "dismissed"]


class BlitzSuggest(BaseModel):
    count: int = Field(default=5, ge=1, le=8)


class BlitzCreate(BaseModel):
    """Отправляются идентификаторы, а не тексты.

    Раньше сюда приходил список вопросов целиком, и то, что увидит студент,
    определял клиент. Теперь клиент выбирает из черновика, а формулировку берём
    из базы: отправить можно только то, что было сгенерировано и сохранено.
    """

    session_id: UUID
    question_ids: list[str] = Field(min_length=1, max_length=8)


class FraudDecisionPayload(BaseModel):
    verdict: Literal["no_signs", "tool_assisted", "misconduct", "inconclusive"]
    # Обоснование обязательно: решение о недобросовестности человек принимает
    # сам и объясняет сам. Пустое поле здесь превратило бы вердикт в кнопку.
    rationale: str = Field(min_length=20)
    blitz_id: UUID | None = None


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
    # Планировщика нет: зависшие прогоны подметаются при чтении очереди, чтобы
    # ревьюер видел failed с понятной причиной, а не вечное «Проверка выполняется…».
    fail_stale_reviews(db)
    fail_stale_detections(db)
    # По той же причине: опрос, переживший свой срок, иначе держит работу в
    # «ожидает ответа» до конца времён и не даёт её завершить.
    expire_blitz_sessions(db)
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
        data["is_demo"] = bool(review and review.raw_result.get("demo_data", False))
        data["model"] = review.model if review else None
        result.append(data)
    return result


@router.get("/submissions/{submission_id}/review")
def review_screen(
    submission_id: UUID,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    submission, review = review_context(db, submission_id, user)
    # То же, что в очереди: иначе зависшая запись оставит экран в состоянии
    # «Проверка выполняется…» с заблокированным перезапуском.
    fail_stale_reviews(db)
    fail_stale_detections(db)
    expire_blitz_sessions(db)
    if submission.status == SubmissionStatus.ASSIGNED:
        transition(db, submission, SubmissionStatus.IN_REVIEW, user, "Ревьюер открыл работу")
        db.commit()
    snapshot = db.scalar(select(Snapshot).where(Snapshot.submission_id == submission.id))
    sessions = list(
        db.scalars(
            select(BlitzSession)
            .where(BlitzSession.review_id == review.id)
            .order_by(BlitzSession.created_at.desc())
        )
    )
    # Черновик и отправленный опрос — разные вещи на экране: из первого ревьюер
    # выбирает, второй уже живёт своей жизнью у студента.
    draft = next((item for item in sessions if item.status == BlitzStatus.DRAFT), None)
    active = next((item for item in sessions if item.status != BlitzStatus.DRAFT), None)
    detection = db.scalar(
        select(AiDetection)
        .where(AiDetection.review_id == review.id)
        .order_by(AiDetection.created_at.desc())
    ) if settings.feature_ai_detection else None
    return {
        "submission": submission_data(submission, user.full_name),
        "detection": detection_data(detection),
        "snapshot": {
            "content": snapshot.content if snapshot else "",
            "parsed_facts": snapshot.parsed_facts if snapshot else {},
            "fetched_at": iso(snapshot.fetched_at) if snapshot else None,
        },
        "review": review_data(review),
        "blitz": blitz_data(active, session_telemetry(db, active)),
        "blitz_draft": blitz_data(draft) if settings.feature_blitz else None,
        "fraud_decisions": [
            {
                "verdict": row.verdict,
                "rationale": row.rationale,
                "decided_at": iso(row.decided_at),
            }
            for row in db.scalars(
                select(FraudDecision)
                .where(FraudDecision.review_id == review.id)
                .order_by(FraudDecision.decided_at.desc())
            )
        ],
    }


def session_telemetry(db: Session, session: BlitzSession | None) -> dict | None:
    """Считается на чтении из событий, а не хранится сведённой.

    Событие — факт, сводка — интерпретация: пороги мы наверняка ещё подвинем, и
    подвинуть их на исторических сессиях можно, только если сводку не заморозили.
    """

    if not session or session.status == BlitzStatus.DRAFT:
        return None
    events = list(
        db.scalars(select(BlitzEvent).where(BlitzEvent.session_id == session.id))
    )
    return blitz_telemetry.aggregate(
        events=events,
        answers=session.answers or [],
        sent_at=session.sent_at,
        answered_at=session.answered_at,
    )


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


@router.post("/reviews/{review_id}/blitz/suggest", status_code=201)
def suggest_blitz(
    review_id: UUID,
    payload: BlitzSuggest,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Генерирует черновик вопросов. Студент их пока не видит.

    Синхронно, а не фоновой задачей: ревьюер нажал и ждёт результата на экране,
    и отдавать ему «поставлено в очередь» здесь было бы хуже, чем подождать.
    """

    if not settings.feature_blitz:
        raise HTTPException(404, "Раздел выключен")
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, review = review_context(db, review.submission_id, user)
    if submission.status != SubmissionStatus.IN_REVIEW:
        raise HTTPException(409, "Вопросы можно подготовить только во время ревью")
    snapshot = db.scalar(select(Snapshot).where(Snapshot.submission_id == submission.id))
    if not snapshot:
        raise HTTPException(409, "Снапшот решения не сохранён")
    # Признаки из детекции — прицел, а не обвинение: вопрос по месту, где что-то
    # наблюдалось, проверяет понимание лучше, чем вопрос по случайной ячейке.
    detection = db.scalar(
        select(AiDetection)
        .where(AiDetection.review_id == review.id, AiDetection.status == AiStatus.READY)
        .order_by(AiDetection.created_at.desc())
    )
    focus = [
        item["key"]
        for item in (detection.contributions if detection else [])
        if item.get("direction", 0) > 0
    ]
    try:
        response = AiReviewerClient().blitz_questions(
            assignment=submission.assignment,
            snapshot=snapshot,
            count=payload.count,
            focus=focus,
        )
    except AiReviewerUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AiReviewerError as exc:
        raise HTTPException(502, f"AI reviewer не смог составить вопросы: {exc}") from exc

    for stale in db.scalars(
        select(BlitzSession).where(
            BlitzSession.review_id == review.id, BlitzSession.status == BlitzStatus.DRAFT
        )
    ):
        db.delete(stale)
    session = BlitzSession(
        review_id=review.id,
        status=BlitzStatus.DRAFT,
        questions=[question.model_dump() for question in response.result.questions],
    )
    db.add(session)
    persist_call(db, review.id, "blitz_questions", response.metadata)
    db.commit()
    return {"id": str(session.id), "status": session.status, "questions": session.questions}


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
    session = db.get(BlitzSession, payload.session_id)
    if not session or session.review_id != review.id or session.status != BlitzStatus.DRAFT:
        raise HTTPException(404, "Черновик вопросов не найден")
    by_id = {question["id"]: question for question in session.questions}
    unknown = [key for key in payload.question_ids if key not in by_id]
    if unknown:
        raise HTTPException(422, f"Вопросы отсутствуют в черновике: {', '.join(unknown)}")
    # Черновик становится отправленным опросом, а не порождает второй: у события
    # «эти вопросы задали студенту» должна быть одна запись.
    session.questions = [by_id[key] for key in payload.question_ids]
    session.status = BlitzStatus.SENT
    session.sent_at = datetime.now(UTC)
    session.due_at = session.sent_at + timedelta(hours=48)
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


@router.post("/reviews/{review_id}/fraud-decision", status_code=201)
def fraud_decision(
    review_id: UUID,
    payload: FraudDecisionPayload,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Финальное решение человека о недобросовестности.

    Балл не трогает — ни при каком вердикте. Оценка складывается из решений по
    критериям, и `misconduct` здесь не должен уметь её изменить: иначе сигнал,
    который «на балл не влияет», начинает влиять через заднюю дверь.
    Пересмотр добавляет строку, а не переписывает старую.
    """

    if not settings.feature_ai_detection:
        raise HTTPException(404, "Раздел выключен")
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    review_context(db, review.submission_id, user)
    blitz = db.get(BlitzSession, payload.blitz_id) if payload.blitz_id else None
    if payload.blitz_id and (not blitz or blitz.review_id != review.id):
        raise HTTPException(404, "Опрос не найден")
    detection = db.scalar(
        select(AiDetection)
        .where(AiDetection.review_id == review.id, AiDetection.status == AiStatus.READY)
        .order_by(AiDetection.created_at.desc())
    )
    decision = FraudDecision(
        review_id=review.id,
        detection_id=detection.id if detection else None,
        blitz_id=blitz.id if blitz else None,
        verdict=FraudVerdict(payload.verdict),
        rationale=payload.rationale,
        decided_by=user.id,
    )
    db.add(decision)
    # Сигнал закрывается решением человека: держать его «на рассмотрении» после
    # вынесенного вердикта незачем.
    for signal in review.signals:
        if signal.kind == "ai_use" and signal.reviewer_decision in (
            SignalDecision.PENDING,
            SignalDecision.BLITZ,
        ):
            signal.reviewer_decision = (
                SignalDecision.CONFIRMED
                if payload.verdict == FraudVerdict.MISCONDUCT
                else SignalDecision.DISMISSED
            )
            signal.decided_at = datetime.now(UTC)
    db.commit()
    return {"id": str(decision.id), "verdict": decision.verdict, "decided_at": iso(decision.decided_at)}


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
    # Зависший прогон перезапустить можно: процесс, который его вёл, уже мёртв.
    if review.ai_status == "running" and not is_stale(review):
        raise HTTPException(409, "AI-ревью уже выполняется")
    review.ai_status = "pending"
    review.ai_error = None
    db.commit()
    background_tasks.add_task(run_review, review.id)
    # Детекция ставится следующей задачей, а не внутри run_review: прогоны
    # независимы, и падение одного не должно уносить второй.
    background_tasks.add_task(run_detection, review.id)
    return {"review_id": str(review.id), "ai_status": review.ai_status}


@router.post("/reviews/{review_id}/detect", status_code=202)
def rerun_detection(
    review_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(reviewer_guard),
    db: Session = Depends(get_db),
) -> dict:
    """Перезапуск только детекции — рубрика при этом не переоценивается."""

    if not settings.feature_ai_detection:
        raise HTTPException(404, "Раздел выключен")
    review = db.get(Review, review_id)
    if not review:
        raise HTTPException(404, "Ревью не найдено")
    submission, review = review_context(db, review.submission_id, user)
    if submission.status == SubmissionStatus.COMPLETED:
        raise HTTPException(409, "Завершённое ревью нельзя перезапустить")
    running = db.scalar(
        select(AiDetection)
        .where(AiDetection.review_id == review.id, AiDetection.status == "running")
        .order_by(AiDetection.created_at.desc())
    )
    # Зависший прогон перезапустить можно: процесс, который его вёл, уже мёртв.
    if running and not is_stale_detection(running):
        raise HTTPException(409, "Проверка на признаки AI уже выполняется")
    background_tasks.add_task(run_detection, review.id)
    return {"review_id": str(review.id), "status": "running"}


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
