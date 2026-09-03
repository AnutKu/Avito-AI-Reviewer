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
    kind: Literal["ai_use", "understanding_risk"]
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


class FeedbackRequest(StrictModel):
    text: str = Field(min_length=3, max_length=12000)
    tone_of_voice: dict = Field(default_factory=dict)
    decisions: list[dict] = Field(default_factory=list, max_length=100)


class FeedbackResponse(StrictModel):
    suggestion: str
    metadata: ProviderMetadata
