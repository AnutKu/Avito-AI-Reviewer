"""Core-side orchestration and persistence for asynchronous AI review."""

from uuid import UUID

from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..models import (
    AiSignal,
    AiStatus,
    Assignment,
    LlmCall,
    Review,
    ReviewerAction,
    ReviewItem,
    RubricVersion,
    SignalDecision,
    Snapshot,
    Submission,
)
from .ai_reviewer_client import AiReviewerClient, ProviderMetadata


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


def run_review(review_id: UUID) -> None:
    """Background task entry point. Provider failures never create fallback results."""

    with SessionLocal() as db:
        review = db.get(Review, review_id)
        if not review:
            return
        review.ai_status = AiStatus.RUNNING
        review.ai_error = None
        review.model = settings.ai_reviewer_model
        review.raw_result = {}
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
            response = AiReviewerClient().review(
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
                review.ai_status = AiStatus.FAILED
                review.ai_error = str(exc)[:2000]
                db.commit()
