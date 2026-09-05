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
    # Этот текст читает студент, и приходил он сплошным абзацем: ревьюер либо
    # разбивал его руками, либо публиковал стену текста. Структура описана в
    # контракте, а не только в промпте, — тогда она часть формы ответа.
    draft_feedback: str = Field(
        min_length=1,
        max_length=12000,
        description=(
            "Готовый текст для студента с абзацами через пустую строку: короткий "
            "абзац о том, что получилось; затем список '- ' с тем, что доработать, "
            "по пункту на замечание; в конце абзац о следующем шаге. Без "
            "заголовков, без баллов и без упоминаний AI."
        ),
    )
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


DetectionVerdict = Literal["human", "human_ai_assisted", "ai"]

# Определения уходят в промпт дословно: вердикт выносит модель, и три слова без
# описания она трактует каждый прогон по-своему — тогда голосование считает
# разброс формулировок, а не разброс мнений о решении.
VERDICT_DEFINITIONS: dict[str, str] = {
    "human": "решение написано человеком, следов генерации не наблюдается",
    "human_ai_assisted": (
        "человек писал сам, но пользовался AI как инструментом: подсказки, "
        "отдельные куски кода, формулировки в тексте"
    ),
    "ai": "решение целиком или почти целиком сгенерировано",
}

# Порядок «строгости» вывода. Нужен ровно для одного: разрешать ничью серединой,
# а не алфавитом — см. _majority_verdict в reviewer.py.
VERDICT_SEVERITY: dict[str, int] = {"human": 0, "human_ai_assisted": 1, "ai": 2}

assert set(VERDICT_DEFINITIONS) == set(DetectionVerdict.__args__)
assert set(VERDICT_SEVERITY) == set(DetectionVerdict.__args__)


class DetectionRequest(StrictModel):
    assignment: AssignmentInput
    snapshot: SnapshotInput


class DetectionIndicator(StrictModel):
    key: DetectionIndicatorKey
    evidence: list[EvidenceResult] = Field(min_length=1, max_length=3)
    note: str = Field(min_length=1, max_length=600)


class DetectionResult(StrictModel):
    """Итог ОДНОГО прогона детектора: наблюдаемые признаки и один вердикт.

    Ни score, ни probability, ни percent: число считает core api. У модели нет
    внутренней шкалы, на которой 73 и 68 отличались бы, поэтому её просят
    перечислить наблюдаемое и назвать одну из трёх категорий, а не оценить
    вероятность.
    """

    indicators: list[DetectionIndicator] = Field(default_factory=list, max_length=11)
    verdict: DetectionVerdict
    summary: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def unique_keys(self) -> "DetectionResult":
        keys = [item.key for item in self.indicators]
        if len(keys) != len(set(keys)):
            raise ValueError("indicator key must be unique")
        return self


class DetectionVote(StrictModel):
    """Как разошлись прогоны. Модель и промпт у всех голосов одни и те же.

    Разные модели дали бы разброс их характеров; одна и та же модель на одном и
    том же промпте даёт разброс собственной выборки — а он и есть то, что нас
    интересует: устойчив ли вывод об этой конкретной работе. Поэтому
    `agreement` отдаётся наружу вместе с вердиктом: 3 из 3 и 2 из 3 — разные
    основания смотреть работу, и решать это ревьюеру, а не нам.
    """

    verdict: DetectionVerdict
    # По голосу на прогон, в порядке вызовов. Короче запрошенного, если часть
    # прогонов не дошла: голосование по двум голосам лучше, чем отказ целиком.
    votes: list[DetectionVerdict] = Field(min_length=1)
    agreement: int = Field(ge=1)

    @model_validator(mode="after")
    def agreement_matches_votes(self) -> "DetectionVote":
        if self.agreement != self.votes.count(self.verdict):
            raise ValueError("agreement must count the votes for the winning verdict")
        return self


class DetectionResponse(StrictModel):
    """`result` — отчёт того прогона, который голосовал как большинство.

    Не склейка трёх: признаки, summary и вердикт внутри одного прогона
    согласованы между собой, а у смеси трёх отчётов эта связь теряется —
    ревьюер читал бы обоснование от одного рассуждения под выводом от другого.
    """

    result: DetectionResult
    vote: DetectionVote
    metadata: ProviderMetadata


BlitzQuestionType = Literal[
    "explain_choice",
    "what_if",
    "change_solution",
    "trace_output",
]

BLITZ_QUESTION_TYPES: dict[str, str] = {
    "explain_choice": "почему выбрано именно это решение, а не очевидная альтернатива",
    "what_if": "что изменится в результате, если поменять одно условие",
    "change_solution": "как доработать решение под новое требование",
    "trace_output": "что окажется в переменной или выводе на конкретном шаге",
}

assert set(BLITZ_QUESTION_TYPES) == set(BlitzQuestionType.__args__)


class BlitzQuestionsRequest(StrictModel):
    assignment: AssignmentInput
    snapshot: SnapshotInput
    count: int = Field(default=5, ge=1, le=8)
    # Ключи признаков из детекции: вопросы имеет смысл целить в те места решения,
    # где что-то наблюдалось. Пустой список — нормальный вход.
    focus: list[str] = Field(default_factory=list, max_length=11)


class BlitzQuestion(StrictModel):
    """`expected_points` — материал ревьюера, студенту он не показывается.

    Проекцию делает core api (routers/student.py), но подпись стоит и здесь:
    поле выглядит безобидно ровно до того момента, когда его отдадут вместе с
    вопросом, и опрос превратится в тест с ответами на обороте.
    """

    id: str = Field(min_length=1, max_length=16)
    type: BlitzQuestionType
    text: str = Field(min_length=10, max_length=600)
    anchor: str = Field(min_length=1, max_length=255)
    expected_points: list[str] = Field(min_length=1, max_length=4)


class BlitzQuestionsResult(StrictModel):
    questions: list[BlitzQuestion] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_ids(self) -> "BlitzQuestionsResult":
        ids = [item.id for item in self.questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question id must be unique")
        return self


class BlitzQuestionsResponse(StrictModel):
    result: BlitzQuestionsResult
    metadata: ProviderMetadata


class AnswerInput(StrictModel):
    question_id: str = Field(min_length=1, max_length=16)
    text: str = Field(default="", max_length=20_000)


class BlitzAnalysisRequest(StrictModel):
    """Телеметрии здесь нет намеренно.

    Поведение за клавиатурой и содержание ответа — разные свидетельства, и
    смешивать их в одном промпте значит позволить одному подкрасить другое.
    Телеметрию ревьюер видит отдельно и взвешивает сам.
    """

    assignment: AssignmentInput
    questions: list[BlitzQuestion] = Field(min_length=1, max_length=8)
    answers: list[AnswerInput] = Field(min_length=1, max_length=8)


class AnswerAssessment(StrictModel):
    question_id: str = Field(min_length=1, max_length=16)
    verdict: Literal["consistent", "partial", "inconsistent", "empty"]
    # Дословные фрагменты ответа студента. Непроверяемое основание отбрасывается.
    grounds: list[str] = Field(default_factory=list, max_length=3)
    note: str = Field(min_length=1, max_length=1500)


class BlitzAnalysisResult(StrictModel):
    assessments: list[AnswerAssessment] = Field(min_length=1, max_length=8)
    summary: str = Field(min_length=1, max_length=2000)
    limitations: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def unique_ids(self) -> "BlitzAnalysisResult":
        ids = [item.question_id for item in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("question_id must be unique")
        return self


class BlitzAnalysisResponse(StrictModel):
    result: BlitzAnalysisResult
    metadata: ProviderMetadata


class FeedbackRequest(StrictModel):
    text: str = Field(min_length=3, max_length=12000)
    tone_of_voice: dict = Field(default_factory=dict)
    decisions: list[dict] = Field(default_factory=list, max_length=100)


class FeedbackResponse(StrictModel):
    suggestion: str
    metadata: ProviderMetadata
