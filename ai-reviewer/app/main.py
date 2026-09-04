from fastapi import FastAPI, HTTPException

from .config import settings
from .contracts import (
    DetectionRequest,
    DetectionResponse,
    FeedbackRequest,
    FeedbackResponse,
    ReviewRequest,
    ReviewResponse,
)
from .reviewer import ZaiInvalidResponse, ZaiNotConfigured, ZaiReviewer


app = FastAPI(
    title="Avito AI Reviewer Service",
    version="0.1.0",
    description="Isolated Z.AI GLM-5.3-Flash review and feedback service.",
)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "ai-reviewer",
        "provider": "z.ai",
        "model": settings.zai_model,
        "configured": bool(settings.zai_api_key),
    }


@app.post("/v1/reviews", response_model=ReviewResponse, tags=["review"])
def create_review(payload: ReviewRequest) -> ReviewResponse:
    try:
        return ZaiReviewer().review(payload)
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc


@app.post("/v1/ai-detection", response_model=DetectionResponse, tags=["detection"])
def detect(payload: DetectionRequest) -> DetectionResponse:
    try:
        return ZaiReviewer().detect(payload)
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc


@app.post("/v1/feedback/rewrite", response_model=FeedbackResponse, tags=["feedback"])
def rewrite_feedback(payload: FeedbackRequest) -> FeedbackResponse:
    try:
        return ZaiReviewer().rewrite_feedback(payload)
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc
