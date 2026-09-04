from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssignmentInput(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    statement: str = Field(min_length=1, max_length=50_000)
    tone_of_voice: dict = Field(default_factory=dict)


class RubricInput(StrictModel):
    criteria: list[dict] = Field(min_length=1, max_length=100)
    max_score: float = Field(gt=0)


class SnapshotInput(StrictModel):
    content: str = Field(min_length=1)
    parsed_facts: dict = Field(default_factory=dict)


class ReviewRequest(StrictModel):
    assignment: AssignmentInput
    rubric: RubricInput
    snapshot: SnapshotInput


class EvidenceResult(StrictModel):
    quote: str = Field(min_length=1, max_length=1000)
    anchor: str = Field(min_length=1, max_length=255)


class CriterionResult(StrictModel):
    criterion_key: str = Field(min_length=1, max_length=64)
    score: float = Field(ge=0)
    verdict: Literal["passed", "partial", "failed"]
    confidence: Literal["high", "medium", "low"]
    evidence: list[EvidenceResult] = Field(min_length=1)
    recommendation: str = Field(min_length=1, max_length=4000)


class SignalResult(StrictModel):
    # ai_use здесь больше не порождается: этот сигнал целиком принадлежит
    # детектору (/v1/ai-detection). Два источника одного вывода давали на экране
    # ревьюера два разных ответа об одной работе.
    kind: Literal["understanding_risk"]
    level: Literal["high", "medium", "low"]
    summary: str = Field(min_length=1, max_length=2000)
    grounds: list[str]
    limitations: str = Field(min_length=1, max_length=3000)


class ReviewResult(StrictModel):
    summary: str = Field(min_length=1, max_length=4000)
    criteria: list[CriterionResult] = Field(min_length=1)
    draft_feedback: str = Field(min_length=1, max_length=12000)
    signals: list[SignalResult] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def unique_keys(self) -> "ReviewResult":
        criterion_keys = [item.criterion_key for item in self.criteria]
        if len(criterion_keys) != len(set(criterion_keys)):
            raise ValueError("criterion_key must be unique")
        signal_kinds = [item.kind for item in self.signals]
        if len(signal_kinds) != len(set(signal_kinds)):
            raise ValueError("signal kind must be unique")
        return self


class ProviderMetadata(StrictModel):
    provider: Literal["z.ai"] = "z.ai"
    model: str
    prompt_hash: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    request_id: str | None = None


class ReviewResponse(StrictModel):
    result: ReviewResult
    metadata: ProviderMetadata


DetectionIndicatorKey = Literal[
    "task_mismatch",
    "internal_contradiction",
    "unused_scaffolding",
    "explains_the_obvious",
    "tutorial_shape",
    "verbose_uniform_markdown",
    "generic_naming",
    "style_uniformity",
    "debug_leftovers",
    "domain_naming",
    "text_inconsistency",
]

# Описания уходят в промпт. Признаки процесса (execution_disorder, failed_cells,
# unrun_cells) здесь отсутствуют намеренно: их величину считает core api из
# parsed_facts, и спрашивать о них модель незачем.
DETECTION_INDICATORS: dict[str, str] = {
    "task_mismatch": "решение отвечает не на поставленную задачу или опирается на данные не из задания",
    "internal_contradiction": "утверждение в тексте противоречит собственному коду или выводу ячейки",
    "unused_scaffolding": "импорты, функции или переменные, которые нигде дальше не используются",
    "explains_the_obvious": "комментарии объясняют тривиальные строки и молчат о сложных",
    "tutorial_shape": "структура повторяет учебный пример, а не решение поставленной задачи",
    "verbose_uniform_markdown": "объяснения обильные, ровные по длине и тону, без следов правки",
    "generic_naming": "имена вида df, data, model без привязки к предметной области задания",
    "style_uniformity": "единый стиль на всём объёме: одинаковые отступы, кавычки, формат строк",
    "debug_leftovers": "закомментированный код, отладочные print, брошенные черновые эксперименты",
    "domain_naming": "имена и комментарии привязаны к предметной области, есть личные пометки",
    "text_inconsistency": "опечатки, смена тона, непоследовательность изложения",
}

assert set(DETECTION_INDICATORS) == set(DetectionIndicatorKey.__args__)


class DetectionRequest(StrictModel):
    assignment: AssignmentInput
    snapshot: SnapshotInput


class DetectionIndicator(StrictModel):
    key: DetectionIndicatorKey
    evidence: list[EvidenceResult] = Field(min_length=1, max_length=3)
    note: str = Field(min_length=1, max_length=600)


class DetectionResult(StrictModel):
    """Ни score, ни probability, ни percent: число считает core api.

    У модели нет внутренней шкалы, на которой 73 и 68 отличались бы, поэтому
    её просят перечислить наблюдаемое, а не оценить вероятность.
    """

    indicators: list[DetectionIndicator] = Field(default_factory=list, max_length=11)
    summary: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def unique_keys(self) -> "DetectionResult":
        keys = [item.key for item in self.indicators]
        if len(keys) != len(set(keys)):
            raise ValueError("indicator key must be unique")
        return self


class DetectionResponse(StrictModel):
    result: DetectionResult
    metadata: ProviderMetadata


class FeedbackRequest(StrictModel):
    text: str = Field(min_length=3, max_length=12000)
    tone_of_voice: dict = Field(default_factory=dict)
    decisions: list[dict] = Field(default_factory=list, max_length=100)


class FeedbackResponse(StrictModel):
    suggestion: str
    metadata: ProviderMetadata
