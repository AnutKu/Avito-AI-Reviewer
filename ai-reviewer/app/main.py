from fastapi import FastAPI, HTTPException

from .config import settings
from .contracts import (
    BlitzAnalysisRequest,
    BlitzAnalysisResponse,
    BlitzQuestionsRequest,
    BlitzQuestionsResponse,
    DetectionRequest,
    DetectionResponse,
    FeedbackRequest,
    FeedbackResponse,
    ReviewRequest,
    ReviewResponse,
)
from .masking import MaskingUnavailable, status as masking_status
from .reviewer import ZaiInvalidResponse, ZaiNotConfigured, ZaiReviewer


app = FastAPI(
    title="Avito AI Reviewer Service",
    version="0.1.0",
    description="Isolated Z.AI GLM-5.3-Flash review and feedback service.",
)

# MaskingUnavailable отдаётся как 503, а не как 502 «ошибка провайдера»: с
# провайдером всё в порядке, это у нас не поднялось маскирование. Разница не
# косметическая — core api считает 503 детерминированным отказом и не повторяет
# запрос, а повторять тут нечего: бандл модели от второй попытки не появится.


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "ai-reviewer",
        "provider": "z.ai",
        "model": settings.zai_model,
        "configured": bool(settings.zai_api_key),
        # Видно снаружи намеренно: «маскирование включено» — это то, что
        # обещано пользователю, и проверять это по логам не должно быть нужно.
        "masking": masking_status(),
    }


@app.post("/v1/reviews", response_model=ReviewResponse, tags=["review"])
def create_review(payload: ReviewRequest) -> ReviewResponse:
    try:
        return ZaiReviewer().review(payload)
    except MaskingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
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
    except MaskingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc


@app.post("/v1/blitz/questions", response_model=BlitzQuestionsResponse, tags=["blitz"])
def blitz_questions(payload: BlitzQuestionsRequest) -> BlitzQuestionsResponse:
    try:
        return ZaiReviewer().blitz_questions(payload)
    except MaskingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc


@app.post("/v1/blitz/analysis", response_model=BlitzAnalysisResponse, tags=["blitz"])
def blitz_analysis(payload: BlitzAnalysisRequest) -> BlitzAnalysisResponse:
    try:
        return ZaiReviewer().blitz_analysis(payload)
    except MaskingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
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
    except MaskingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiNotConfigured as exc:
        raise HTTPException(503, str(exc)) from exc
    except ZaiInvalidResponse as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ошибка провайдера Z.AI: {exc}") from exc
