"""Typed HTTP client for the isolated ai-reviewer microservice."""

import json
import urllib.error
import urllib.request
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..config import settings
from ..models import Assignment, RubricVersion, Snapshot


class AiReviewerError(RuntimeError):
    """Провайдер ответил, но ответ непригоден. Повтор имеет смысл: ответ не детерминирован."""


class AiReviewerUnavailable(AiReviewerError):
    """Сервис недоступен: сеть, таймаут, не поднят. Повтор имеет смысл."""


class AiReviewerNotConfigured(AiReviewerUnavailable):
    """Нет ZAI_API_KEY. Детерминированный отказ — повторять нечего.

    Наследуется от AiReviewerUnavailable, чтобы вызовы, отдающие наружу 503,
    продолжали работать без изменений.
    """


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceResult(ContractModel):
    quote: str
    anchor: str


class CriterionResult(ContractModel):
    criterion_key: str
    score: float
    verdict: Literal["passed", "partial", "failed"]
    confidence: Literal["high", "medium", "low"]
    evidence: list[EvidenceResult]
    recommendation: str


class SignalResult(ContractModel):
    kind: Literal["ai_use", "understanding_risk"]
    level: Literal["high", "medium", "low"]
    summary: str
    grounds: list[str]
    limitations: str


class ReviewResult(ContractModel):
    summary: str
    criteria: list[CriterionResult]
    draft_feedback: str
    signals: list[SignalResult] = Field(default_factory=list)


class ProviderMetadata(ContractModel):
    provider: Literal["z.ai"]
    model: str
    prompt_hash: str
    prompt_tokens: int
    completion_tokens: int
    request_id: str | None = None


class ReviewResponse(ContractModel):
    result: ReviewResult
    metadata: ProviderMetadata


class FeedbackResponse(ContractModel):
    suggestion: str
    metadata: ProviderMetadata


class AiReviewerClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.ai_reviewer_url).rstrip("/")
        self.timeout = timeout or settings.ai_reviewer_timeout_seconds

    def _request(self, path: str, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "avito-core-api/0.1"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                body = json.loads(exc.read().decode())
                detail = body.get("detail", f"HTTP {exc.code}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = f"HTTP {exc.code}"
            if exc.code == 503:
                raise AiReviewerNotConfigured(detail) from exc
            raise AiReviewerError(detail) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise AiReviewerUnavailable("Сервис ai-reviewer недоступен") from exc

    def review(
        self,
        *,
        assignment: Assignment,
        rubric: RubricVersion,
        snapshot: Snapshot,
    ) -> ReviewResponse:
        payload = {
            "assignment": {
                "title": assignment.title,
                "statement": assignment.statement,
                "tone_of_voice": assignment.course.tone_of_voice,
            },
            "rubric": {
                "criteria": rubric.criteria,
                "max_score": rubric.max_score,
            },
            "snapshot": {
                "content": snapshot.content,
                "parsed_facts": snapshot.parsed_facts,
            },
        }
        return ReviewResponse.model_validate(self._request("/v1/reviews", payload))

    def rewrite_feedback(
        self,
        *,
        text: str,
        tone_of_voice: dict,
        decisions: list[dict],
    ) -> FeedbackResponse:
        payload = {
            "text": text,
            "tone_of_voice": tone_of_voice,
            "decisions": decisions,
        }
        return FeedbackResponse.model_validate(
            self._request("/v1/feedback/rewrite", payload)
        )

    def health(self) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/health",
            headers={"User-Agent": "avito-core-api/0.1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return {**json.load(response), "available": True}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return {
                "service": "ai-reviewer",
                "model": settings.ai_reviewer_model,
                "configured": False,
                "available": False,
            }
