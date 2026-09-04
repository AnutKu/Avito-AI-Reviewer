"""Core-side orchestration and persistence for asynchronous AI review.

Прогон живёт в `BackgroundTasks` того же процесса uvicorn — очереди в MVP нет.
Из этого следуют три вещи, реализованные здесь, а не оставленные на удачу:

* транзиентный отказ провайдера повторяется (`ai_review_max_attempts`);
* запись, оставшаяся в `running` дольше `ai_review_stale_after_seconds`,
  считается мёртвой и переводится в `failed` (`fail_stale_reviews`);
* при старте процесса все `running` осиротели по определению — прогон умер
  вместе с предыдущим процессом (`recover_orphaned_reviews`).

Здесь же живёт вторая стадия — `run_detection`. Она ставится следующей задачей
после ревью и наследует всю ту же защиту: свои повторы, свой sweep зависших, своё
восстановление осиротевших. Прогоны независимы: падение одного не уносит второй.
"""

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import (
    AiDetection,
    AiSignal,
    AiStatus,
    Assignment,
    DetectionCategory,
    LlmCall,
    Review,
    ReviewerAction,
    ReviewItem,
    RubricVersion,
    SignalDecision,
    SignalKind,
    Snapshot,
    Submission,
)
from . import detection_scale
from .ai_reviewer_client import (
    AiReviewerClient,
    AiReviewerError,
    AiReviewerNotConfigured,
    DetectionResponse,
    ProviderMetadata,
    ReviewResponse,
)

ORPHANED_ERROR = (
    "Прогон прерван: процесс, выполнявший AI-ревью, был остановлен. "
    "Запустите проверку заново."
)
STALE_ERROR = (
    "Прогон не завершился за отведённое время и признан зависшим. "
    "Запустите проверку заново."
)


def _record_call(db: Session, review_id: UUID, stage: str, metadata: ProviderMetadata) -> None:
    cost = (
        metadata.prompt_tokens * settings.zai_input_cost_per_million
        + metadata.completion_tokens * settings.zai_output_cost_per_million
    ) / 1_000_000
    db.add(
        LlmCall(
            review_id=review_id,
            stage=stage,
            model=metadata.model,
            prompt_hash=metadata.prompt_hash,
            tokens_in=metadata.prompt_tokens,
            tokens_out=metadata.completion_tokens,
            cost_usd=cost,
            cache_hit=False,
        )
    )


def persist_call(db: Session, review_id: UUID, stage: str, metadata: ProviderMetadata) -> None:
    _record_call(db, review_id, stage, metadata)


def running_since(row: Review | AiDetection) -> datetime:
    """Момент старта прогона. Пишется в raw_result, чтобы не заводить миграцию схемы."""

    started = (row.raw_result or {}).get("started_at")
    if isinstance(started, str):
        try:
            return datetime.fromisoformat(started)
        except ValueError:
            pass
    return row.created_at or datetime.now(UTC)


def _stale(row: Review | AiDetection, status: str) -> bool:
    if status != AiStatus.RUNNING:
        return False
    deadline = datetime.now(UTC) - timedelta(seconds=settings.ai_review_stale_after_seconds)
    return running_since(row) < deadline


def is_stale(review: Review) -> bool:
    return _stale(review, review.ai_status)


def is_stale_detection(detection: AiDetection) -> bool:
    return _stale(detection, detection.status)


def _mark_failed(review: Review, message: str) -> None:
    review.ai_status = AiStatus.FAILED
    review.ai_error = message


def fail_stale_reviews(db: Session) -> int:
    """Переводит зависшие прогоны в failed. Дёргается из чтения очереди — планировщика нет."""

    stale = [
        review
        for review in db.scalars(select(Review).where(Review.ai_status == AiStatus.RUNNING))
        if is_stale(review)
    ]
    for review in stale:
        _mark_failed(review, STALE_ERROR)
    if stale:
        db.commit()
    return len(stale)


def fail_stale_detections(db: Session) -> int:
    """То же для прогонов детектора: они живут в тех же BackgroundTasks."""

    stale = [
        detection
        for detection in db.scalars(select(AiDetection).where(AiDetection.status == AiStatus.RUNNING))
        if is_stale_detection(detection)
    ]
    for detection in stale:
        detection.status = AiStatus.FAILED
        detection.error = STALE_ERROR
    if stale:
        db.commit()
    return len(stale)


def recover_orphaned_detections() -> int:
    """Вызывается на старте приложения — по той же причине, что и для ревью."""

    with SessionLocal() as db:
        orphaned = list(
            db.scalars(select(AiDetection).where(AiDetection.status == AiStatus.RUNNING))
        )
        for detection in orphaned:
            detection.status = AiStatus.FAILED
            detection.error = ORPHANED_ERROR
        if orphaned:
            db.commit()
        return len(orphaned)


def recover_orphaned_reviews() -> int:
    """Вызывается на старте приложения.

    BackgroundTasks не переживают перезапуск процесса, поэтому любой `running`
    на старте — осиротевшая запись, а не выполняющийся прогон.

    Верно ровно до тех пор, пока api поднят одним процессом (текущий CMD без
    --workers). Появятся воркеры — старт одного будет ронять прогоны соседей,
    и это место должно уехать во внешнюю очередь.
    """

    with SessionLocal() as db:
        orphaned = list(db.scalars(select(Review).where(Review.ai_status == AiStatus.RUNNING)))
        for review in orphaned:
            _mark_failed(review, ORPHANED_ERROR)
        if orphaned:
            db.commit()
        return len(orphaned)


def _with_retries(call):
    """Повтор транзиентного отказа. Отсутствие ключа детерминировано — не повторяем."""

    attempts = max(1, settings.ai_review_max_attempts)
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except AiReviewerNotConfigured:
            raise
        except AiReviewerError:
            if attempt == attempts:
                raise
            time.sleep(settings.ai_review_retry_delay_seconds * attempt)
    raise AssertionError("недостижимо: цикл повторов всегда возвращает или бросает")


def _review_with_retries(
    *,
    assignment: Assignment,
    rubric: RubricVersion,
    snapshot: Snapshot,
) -> ReviewResponse:
    return _with_retries(
        lambda: AiReviewerClient().review(
            assignment=assignment,
            rubric=rubric,
            snapshot=snapshot,
        )
    )


def _detection_with_retries(*, assignment: Assignment, snapshot: Snapshot) -> DetectionResponse:
    return _with_retries(
        lambda: AiReviewerClient().detect(assignment=assignment, snapshot=snapshot)
    )


SIGNAL_LEVEL_BY_CATEGORY = {
    DetectionCategory.LIKELY_GENERATED: "high",
    DetectionCategory.TOOL_ASSISTED: "medium",
    DetectionCategory.NO_SIGNS: "low",
}


def _sync_ai_signal(
    db: Session,
    review: Review,
    detection: AiDetection,
    score: detection_scale.DetectionScore,
) -> None:
    """Единственное место, где рождается сигнал ai_use.

    Раньше его порождало и общее ревью, и детектор; на экране это давало два
    разных ответа об одной работе. Теперь ревью отвечает только за
    understanding_risk, а этот сигнал — производная от прогона детектора.
    """

    for signal in list(review.signals):
        if signal.kind == SignalKind.AI_USE:
            db.delete(signal)
    if not score.is_reportable:
        return
    grounds = [
        f"{item.title} — подтверждённых мест: {len(item.evidence)}"
        if item.evidence
        else item.title
        for item in score.contributions
        if item.direction > 0
    ]
    grounds.append(f"Индекс признаков: {score.score} из 100 (шкала описана рядом с числом)")
    db.add(
        AiSignal(
            review_id=review.id,
            kind=SignalKind.AI_USE,
            level=SIGNAL_LEVEL_BY_CATEGORY.get(score.category, "low"),
            summary=detection.summary,
            grounds=grounds,
            limitations=detection.limitations,
            reviewer_decision=SignalDecision.PENDING,
        )
    )


def run_detection(review_id: UUID) -> None:
    """Background task entry point. Ставится следующей задачей после run_review.

    Отдельный прогон, а не два поля в ревью: у детекции другой вход, другой промпт
    и другая цена перезапуска — смешать их значило бы переоценивать всю рубрику
    ради повторной проверки одного сигнала.
    """

    if not settings.feature_ai_detection:
        return
    with SessionLocal() as db:
        review = db.get(Review, review_id)
        if not review:
            return
        detection = AiDetection(
            review_id=review.id,
            status=AiStatus.RUNNING,
            model=settings.ai_reviewer_model,
            raw_result={"started_at": datetime.now(UTC).isoformat()},
        )
        db.add(detection)
        db.commit()
        detection_id = detection.id

        try:
            submission = db.get(Submission, review.submission_id)
            snapshot = db.query(Snapshot).filter(Snapshot.submission_id == submission.id).one()
            assignment = db.get(Assignment, submission.assignment_id)
            response = _detection_with_retries(assignment=assignment, snapshot=snapshot)
            score = detection_scale.compute(
                parsed_facts=snapshot.parsed_facts,
                snapshot_content=snapshot.content,
                indicators=[item.model_dump() for item in response.result.indicators],
            )
            detection.score = score.score
            detection.coverage = score.coverage
            detection.confidence = score.confidence
            detection.category = score.category
            detection.contributions = [item.as_dict() for item in score.contributions]
            detection.summary = response.result.summary
            detection.limitations = response.result.limitations
            detection.model = response.metadata.model
            detection.status = AiStatus.READY
            detection.raw_result = {
                **(detection.raw_result or {}),
                "provider": response.metadata.provider,
                "request_id": response.metadata.request_id,
            }
            _record_call(db, review.id, "ai_detection", response.metadata)
            _sync_ai_signal(db, review, detection, score)
            db.commit()
        except Exception as exc:
            db.rollback()
            detection = db.get(AiDetection, detection_id)
            if detection:
                detection.status = AiStatus.FAILED
                detection.error = str(exc)[:2000]
                db.commit()


def run_review(review_id: UUID) -> None:
    """Background task entry point. Provider failures never create fallback results."""

    with SessionLocal() as db:
        review = db.get(Review, review_id)
        if not review:
            return
        review.ai_status = AiStatus.RUNNING
        review.ai_error = None
        review.model = settings.ai_reviewer_model
        review.raw_result = {"started_at": datetime.now(UTC).isoformat()}
        review.draft_feedback = ""
        for item in list(review.items):
            db.delete(item)
        for signal in list(review.signals):
            db.delete(signal)
        db.commit()

        try:
            submission = db.get(Submission, review.submission_id)
            snapshot = db.query(Snapshot).filter(Snapshot.submission_id == submission.id).one()
            assignment = db.get(Assignment, submission.assignment_id)
            rubric = db.get(RubricVersion, review.rubric_version_id)
            response = _review_with_retries(
                assignment=assignment,
                rubric=rubric,
                snapshot=snapshot,
            )
            result = response.result
            metadata = response.metadata
            rubric_by_key = {item["key"]: item for item in rubric.criteria}
            for position, item in enumerate(result.criteria):
                criterion = rubric_by_key[item.criterion_key]
                db.add(
                    ReviewItem(
                        review_id=review.id,
                        position=position,
                        criterion_key=item.criterion_key,
                        criterion_title=criterion["title"],
                        max_score=float(criterion["max_score"]),
                        ai_score=item.score,
                        verdict=item.verdict,
                        confidence=item.confidence,
                        evidence=[evidence.model_dump() for evidence in item.evidence],
                        recommendation=item.recommendation,
                        reviewer_action=ReviewerAction.PENDING,
                    )
                )
            for signal in result.signals:
                db.add(
                    AiSignal(
                        review_id=review.id,
                        kind=signal.kind,
                        level=signal.level,
                        summary=signal.summary,
                        grounds=signal.grounds,
                        limitations=signal.limitations,
                        reviewer_decision=SignalDecision.PENDING,
                    )
                )
            review.model = metadata.model
            review.ai_status = AiStatus.READY
            review.raw_result = {
                **result.model_dump(mode="json"),
                "provider": metadata.provider,
                "request_id": metadata.request_id,
                "demo_data": False,
            }
            review.draft_feedback = result.draft_feedback
            _record_call(db, review.id, "review", metadata)
            db.commit()
        except Exception as exc:
            db.rollback()
            review = db.get(Review, review_id)
            if review:
                _mark_failed(review, str(exc)[:2000])
                db.commit()
