from datetime import datetime
from typing import Any

from .models import AiSignal, Assignment, Review, ReviewItem, Submission


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def assignment_data(assignment: Assignment, rubric: Any = None) -> dict:
    return {
        "id": str(assignment.id),
        "title": assignment.title,
        "statement": assignment.statement,
        "deadline_at": iso(assignment.deadline_at),
        "effort_weight": assignment.effort_weight,
        "submission_channel": assignment.submission_channel,
        "course": assignment.course.title,
        "course_id": str(assignment.course_id),
        "published": assignment.published_at is not None,
        "published_at": iso(assignment.published_at),
        "rubric": rubric.criteria if rubric else [],
        "max_score": rubric.max_score if rubric else None,
        "pass_score": rubric.pass_score if rubric else None,
    }


def submission_data(submission: Submission, reviewer: str | None = None) -> dict:
    return {
        "id": str(submission.id),
        "assignment_id": str(submission.assignment_id),
        "assignment": submission.assignment.title,
        "student": submission.student.full_name,
        "student_id": str(submission.student_id),
        "source_url": submission.source_url,
        "submitted_at": iso(submission.submitted_at),
        "deadline_at": iso(submission.assignment.deadline_at),
        "status": submission.status,
        "is_overdue": submission.is_overdue,
        "reviewer": reviewer,
    }


def item_data(item: ReviewItem) -> dict:
    return {
        "id": str(item.id),
        "criterion_key": item.criterion_key,
        "criterion_title": item.criterion_title,
        "max_score": item.max_score,
        "ai_score": item.ai_score,
        "verdict": item.verdict,
        "confidence": item.confidence,
        "evidence": item.evidence,
        "recommendation": item.recommendation,
        "reviewer_action": item.reviewer_action,
        "final_score": item.final_score,
        "reviewer_comment": item.reviewer_comment,
    }


def signal_data(signal: AiSignal) -> dict:
    return {
        "id": str(signal.id),
        "kind": signal.kind,
        "level": signal.level,
        "summary": signal.summary,
        "grounds": signal.grounds,
        "limitations": signal.limitations,
        "reviewer_decision": signal.reviewer_decision,
    }


def review_data(review: Review, include_internal: bool = True) -> dict:
    data = {
        "id": str(review.id),
        "submission_id": str(review.submission_id),
        "ai_status": review.ai_status,
        "final_score": review.final_score,
        "final_feedback": review.final_feedback,
        "completed_at": iso(review.completed_at),
    }
    if include_internal:
        data.update(
            {
                "model": review.model,
                "ai_error": review.ai_error,
                "summary": review.raw_result.get("summary", ""),
                "draft_feedback": review.draft_feedback,
                "is_demo": bool(review.raw_result.get("demo_data", False)),
                "items": [item_data(item) for item in review.items],
                "signals": [signal_data(signal) for signal in review.signals],
            }
        )
    return data
