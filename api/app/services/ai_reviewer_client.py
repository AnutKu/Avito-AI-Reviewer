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
    # ai_use сюда больше не приходит: сигнал целиком принадлежит детектору.
    kind: Literal["understanding_risk"]
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


class DetectionIndicator(ContractModel):
    key: str
    evidence: list[EvidenceResult]
    note: str


DetectionVerdict = Literal["human", "human_ai_assisted", "ai"]


class DetectionResult(ContractModel):
    """Ни score, ни probability: индекс считает services/detection_scale.py.

    `verdict` — категория, а не число: её модель назвать может, шкалу — нет.
    """

    indicators: list[DetectionIndicator] = Field(default_factory=list)
    verdict: DetectionVerdict
    summary: str
    limitations: str


class DetectionVote(ContractModel):
    """Голосование нескольких одинаковых прогонов детектора.

    `agreement` — сколько голосов из `votes` пришлось на победивший вердикт.
    Число едет до ревьюера: 3 из 3 и 2 из 3 — разные основания смотреть работу.
    """

    verdict: DetectionVerdict
    votes: list[DetectionVerdict]
    agreement: int


class DetectionResponse(ContractModel):
    result: DetectionResult
    vote: DetectionVote
    metadata: ProviderMetadata


class BlitzQuestion(ContractModel):
    """`expected_points` не покидает контур ревьюера — см. student.py."""

    id: str
    type: str
    text: str
    anchor: str
    expected_points: list[str]


class BlitzQuestionsResult(ContractModel):
    questions: list[BlitzQuestion]


class BlitzQuestionsResponse(ContractModel):
    result: BlitzQuestionsResult
    metadata: ProviderMetadata


class AnswerAssessment(ContractModel):
    question_id: str
    verdict: Literal["consistent", "partial", "inconsistent", "empty"]
    grounds: list[str] = Field(default_factory=list)
    note: str


class BlitzAnalysisResult(ContractModel):
    assessments: list[AnswerAssessment]
    summary: str
    limitations: str


class BlitzAnalysisResponse(ContractModel):
    result: BlitzAnalysisResult
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

    def detect(self, *, assignment: Assignment, snapshot: Snapshot) -> DetectionResponse:
        payload = {
            "assignment": {
                "title": assignment.title,
                "statement": assignment.statement,
                "tone_of_voice": assignment.course.tone_of_voice,
            },
            "snapshot": {
                "content": snapshot.content,
                "parsed_facts": snapshot.parsed_facts,
            },
        }
        return DetectionResponse.model_validate(self._request("/v1/ai-detection", payload))

    def blitz_questions(
        self,
        *,
        assignment: Assignment,
        snapshot: Snapshot,
        count: int,
        focus: list[str],
    ) -> BlitzQuestionsResponse:
        payload = {
            "assignment": {
                "title": assignment.title,
                "statement": assignment.statement,
                "tone_of_voice": assignment.course.tone_of_voice,
            },
            "snapshot": {
                "content": snapshot.content,
                "parsed_facts": snapshot.parsed_facts,
            },
            "count": count,
            "focus": focus,
        }
        return BlitzQuestionsResponse.model_validate(
            self._request("/v1/blitz/questions", payload)
        )

    def blitz_analysis(
        self,
        *,
        assignment: Assignment,
        questions: list[dict],
        answers: list[dict],
    ) -> BlitzAnalysisResponse:
        payload = {
            "assignment": {
                "title": assignment.title,
                "statement": assignment.statement,
                "tone_of_voice": assignment.course.tone_of_voice,
            },
            "questions": questions,
            "answers": answers,
        }
        return BlitzAnalysisResponse.model_validate(
            self._request("/v1/blitz/analysis", payload)
        )

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
