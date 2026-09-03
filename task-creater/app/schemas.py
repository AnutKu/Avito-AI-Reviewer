"""Контракты данных: структурированные выходы агентов (LLM) и API-модели.

Схемы агентов переиспользуются в API — задание, критерий и предложенная правка
имеют одну и ту же форму на всех слоях, что упрощает `apply` правок и экспорт.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
#  Базовые сущности задания и критериев
# --------------------------------------------------------------------------- #

CheckKind = Literal["objective", "subjective"]
Severity = Literal["low", "medium", "high"]
AudienceLevel = Literal["novice", "intermediate", "advanced"]
DeliveryChannel = Literal["github", "stepik", "gdocs", "other"]
Language = Literal["ru", "en"]
TaskFormat = Literal["auto", "case_study", "metrics_design", "coding", "open"]


class RubricLevel(BaseModel):
    """Уровень выполнения критерия и сколько баллов за него дают."""

    points: float
    label: str = Field(description="Короткая метка уровня, напр. 'частично'")
    descriptor: str = Field(description="Наблюдаемый признак: по чему видно, что решение на этом уровне")


class Criterion(BaseModel):
    """Один критерий оценки.

    Разделён на то, что видит студент, и то, что видит только ревьюер. Студенту
    показываются `title`, `max_points`, `student_hint` — этого хватает понять, что
    делать, но не хватает «подогнать» решение под грейдинг. Всё остальное скрыто.
    """

    key: str = Field(description="слаг латиницей, kebab-case, стабильный идентификатор")
    title: str = Field(description="ВИДНО СТУДЕНТУ: короткое имя критерия/этапа")
    max_points: float = Field(gt=0, description="ВИДНО СТУДЕНТУ: вес критерия")
    student_hint: str = Field(
        default="",
        description="ВИДНО СТУДЕНТУ: одна фраза, ЧТО оценивается. Без перечисления "
        "конкретных ожидаемых ответов, метрик, гипотез — иначе студент просто спишет.",
    )
    description: str = Field(
        description="СКРЫТО: что именно проверяет ревьюер, наблюдаемый признак, а не субъективное понятие."
    )
    check_kind: CheckKind = Field(
        description="objective — проверяется однозначно; subjective — требует суждения ревьюера"
    )
    evidence_hint: str = Field(description="СКРЫТО: куда смотреть в решении, чтобы оценить критерий")
    expected_signals: list[str] = Field(
        default_factory=list,
        description="СКРЫТО: признаки сильного ответа по этому критерию (что именно должно "
        "быть в решении). Это и есть то, что нельзя показывать студенту.",
    )
    rubric_levels: list[RubricLevel] = Field(
        default_factory=list, description="СКРЫТО: детальные уровни выполнения с порогами баллов"
    )


class TaskDraftData(BaseModel):
    """Полное тело черновика задания (хранится в JSONB, версионируется).

    Поля с пометкой ВИДНО — часть студенческого брифа; остальные видит только ревьюер.
    """

    title: str = Field(description="ВИДНО")
    summary: str = Field(description="ВИДНО: 1–2 предложения, что студент должен сделать и зачем")
    context_md: str = Field(
        default="",
        description="ВИДНО: роль, бизнес-контекст, вводные данные и цифры (для кейсов). "
        "Может быть пустым для простых заданий.",
    )
    statement_md: str = Field(description="ВИДНО: что нужно сделать (постановка задачи), Markdown")
    deliverables: list[str] = Field(
        default_factory=list,
        description="ВИДНО: конкретные пункты/вопросы, которые студент должен раскрыть в сдаче",
    )
    submission_format: str = Field(
        default="", description="ВИДНО: формат сдачи (тип документа, обязательны ли скриншоты и т.п.)"
    )
    public_rubric_note: str = Field(
        default="",
        description="ВИДНО: как считаются баллы, ОБОБЩЁННО. Напр. «5 пунктов × 0–2 балла: "
        "2 — верно и аргументировано, 1 — верно, но слабо, 0 — неверно/нет». Без деталей "
        "того, что конкретно ожидается по каждому пункту.",
    )
    learning_objectives: list[str] = Field(default_factory=list, description="ВИДНО")
    criteria: list[Criterion]
    reference_solution_md: str = Field(description="СКРЫТО: эталонное решение / разбор, Markdown")
    common_mistakes: list[str] = Field(description="СКРЫТО: типичные ошибки и анти-паттерны")
    reviewer_notes: str = Field(
        default="", description="СКРЫТО: калибровочные заметки для ревьюеров (на что смотреть, спорные места)"
    )

    @property
    def total_points(self) -> float:
        return round(sum(c.max_points for c in self.criteria), 3)


# --------------------------------------------------------------------------- #
#  Выход агента-генератора
# --------------------------------------------------------------------------- #


class GeneratedTask(TaskDraftData):
    """Схема, которую возвращает агент-генератор (совпадает с телом черновика)."""


# --------------------------------------------------------------------------- #
#  Выход агентов-решателей
# --------------------------------------------------------------------------- #


class SelfCriterionScore(BaseModel):
    criterion_key: str
    expected_points: float
    reasoning: str


class SolverOutput(BaseModel):
    """Решение задания «глазами» одного профиля студента.

    Решатель видит ТОЛЬКО студенческий бриф (условие + пункты сдачи + обобщённая
    разбалловка), но не скрытую рубрику — как настоящий студент.
    """

    persona: str
    approach_notes: str = Field(description="Как студент понял задание и как шёл к решению — своими словами")
    solution_md: str = Field(description="Само решение (текст/код/разбор) в Markdown")
    self_assessment: list[SelfCriterionScore]
    exploited_ambiguities: list[str] = Field(
        default_factory=list,
        description="Места, где брифа не хватило и пришлось догадываться / где формулировку "
        "можно прочитать двояко — и как именно она прочитана в этом решении",
    )


# --------------------------------------------------------------------------- #
#  Выход агента-грейдера
# --------------------------------------------------------------------------- #


class GradedCriterion(BaseModel):
    criterion_key: str
    points: float
    max_points: float
    rationale: str
    evidence_quote: str = Field(description="Дословная цитата из решения — основание оценки")
    confidence: float = Field(ge=0, le=1, description="Насколько уверенно критерий применяется")
    decidable: bool = Field(description="Хватило ли формулировки критерия, чтобы оценить однозначно")
    ambiguity_note: str | None = Field(default=None, description="Если decidable=false — что именно помешало")


class GraderOutput(BaseModel):
    persona: str
    scores: list[GradedCriterion]
    total_points: float
    overall_comment: str


# --------------------------------------------------------------------------- #
#  Выход агента-критика (ревизора рубрики)
# --------------------------------------------------------------------------- #

FindingKind = Literal[
    "ambiguous",  # допускает разные трактовки
    "underspecified",  # не хватает деталей, чтобы применить
    "gameable",  # можно формально выполнить, нарушив смысл
    "overlapping",  # пересекается с другим критерием, двойной счёт
    "unmeasurable",  # субъективное понятие без формализации
    "missing_criterion",  # важный аспект задания не покрыт ни одним критерием
    "inconsistent_scoring",  # разные решения получают одинаковый балл (или наоборот)
    "weight_imbalance",  # вес критерия не соответствует его важности
    "scope_creep",  # критерий требует того, чего нет в условии
    "unfair_hidden",  # скрытое ожидание нельзя вывести из того, что видит студент
    "leaky_public",  # публичная часть раскрывает грейдинг — решение можно списать/подогнать
]

FindingTarget = Literal["rubric", "brief"]


class Finding(BaseModel):
    id: str = Field(description="короткий стабильный id, напр. 'F1'")
    criterion_key: str | None = Field(
        default=None, description="ключ критерия или null для проблемы уровня задания"
    )
    kind: FindingKind
    severity: Severity
    target: FindingTarget = Field(
        default="rubric",
        description="rubric — чинится правкой критерия; brief — чинится правкой того, что "
        "видит студент (условие/пункты сдачи/публичная разбалловка)",
    )
    explanation: str
    fix_suggestion: str = Field(default="", description="Конкретное предложение: что и как поменять")
    evidence: str = Field(description="На чём основан вывод: какие профили/оценки/цитаты разошлись и как")


class CriterionEdit(BaseModel):
    id: str = Field(description="короткий стабильный id, напр. 'E1'")
    operation: Literal["modify", "add", "remove"]
    criterion_key: str = Field(description="для modify/remove — существующий ключ; для add — новый")
    proposed_criterion: Criterion | None = Field(
        default=None, description="новая версия критерия (для modify и add); null для remove"
    )
    before_snapshot: str | None = Field(default=None, description="текущая формулировка критерия до правки")
    rationale: str
    addresses: list[str] = Field(description="id находок (Finding), которые закрывает правка")
    severity: Severity


class CriticOutput(BaseModel):
    findings: list[Finding]
    proposed_edits: list[CriterionEdit]
    converged: bool = Field(description="true, если находок severity>=medium не осталось")
    convergence_reason: str


# --------------------------------------------------------------------------- #
#  Артефакты прогона валидации (то, что кладётся в validation_runs.result)
# --------------------------------------------------------------------------- #


class RoundArtifact(BaseModel):
    round_no: int
    criteria_snapshot: list[Criterion]
    solutions: list[SolverOutput]
    gradings: list[GraderOutput]
    findings: list[Finding]
    proposed_edits: list[CriterionEdit]
    score_matrix: dict[str, dict[str, float]] = Field(
        description="{criterion_key: {persona: points}} — для наглядного показа расхождений"
    )
    converged: bool
    convergence_reason: str


class RunMetrics(BaseModel):
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    cost_rub: float = 0.0
    duration_s: float = 0.0
    model_fast: str = ""
    model_smart: str = ""


class ValidationResult(BaseModel):
    rounds: list[RoundArtifact]
    recommended_criteria: list[Criterion] = Field(
        description="Критерии после применения всех правок последнего раунда — предпросмотр, "
        "не сохраняется без решения человека"
    )
    open_findings: list[Finding]
    proposed_edits: list[CriterionEdit]
    converged: bool
    summary: str
    metrics: RunMetrics


# --------------------------------------------------------------------------- #
#  API: запросы
# --------------------------------------------------------------------------- #


class CourseIdeaIn(BaseModel):
    idea: str = Field(min_length=10, description="Идея задания/курса своими словами")
    track: str = Field(description="Направление, напр. 'Аналитика данных' или 'Backend / Go'")
    audience_level: AudienceLevel = "intermediate"
    task_format: TaskFormat = Field(
        default="auto",
        description="Формат задания: case_study — бизнес-кейс с ролью и данными; "
        "metrics_design — «выбери продукт, подбери метрики»; coding — задача с кодом; "
        "open — свободный. auto — определить по идее и направлению.",
    )
    target_effort_hours: float | None = Field(default=None, gt=0)
    delivery_channel: DeliveryChannel = "github"
    language: Language = "ru"
    total_points: float = Field(default=10, gt=0, description="Желаемая сумма баллов (разбалловка)")
    constraints: str | None = Field(
        default=None,
        description="Доп. требования: правило штрафа за просрочку, обязательные технологии, "
        "формат сдачи, что должно и не должно проверяться",
    )


class GenerateTaskIn(BaseModel):
    idea_id: str | None = None
    idea: CourseIdeaIn | None = None
    background: bool = Field(
        default=False,
        description="true — вернуть черновик сразу (статус generating), генерировать в фоне",
    )


class ImportTaskIn(BaseModel):
    """Добавить УЖЕ существующее задание (не сгенерированное сервисом) и проверить его."""

    title: str
    track: str = "General"
    context_md: str = ""
    statement_md: str
    deliverables: list[str] = Field(default_factory=list)
    submission_format: str = ""
    public_rubric_note: str = ""
    learning_objectives: list[str] = Field(default_factory=list)
    criteria: list[Criterion]
    reference_solution_md: str = ""
    common_mistakes: list[str] = Field(default_factory=list)
    reviewer_notes: str = ""
    total_points: float | None = Field(default=None, description="если задано — веса нормируются к нему")


class GradeSolutionIn(BaseModel):
    """Демо-проверка: предварительное ревью одного решения по текущей рубрике задания."""

    solution_md: str = Field(min_length=1, description="текст решения студента (или эталон)")
    approach_notes: str = Field(default="", description="как студент шёл к решению (опционально)")
    persona: str | None = Field(default=None, description="метка профиля для отчёта")


class ValidationConfigIn(BaseModel):
    personas: list[str] | None = Field(
        default=None, description="ключи профилей решателей; null — набор по умолчанию"
    )
    max_rounds: int = Field(default=2, ge=1, le=4)
    token_budget: int = Field(default=200_000, ge=10_000)
    model_fast: str | None = None
    model_smart: str | None = None
    solver_temperature: float = Field(default=0.7, ge=0, le=2)


class EditDecisionIn(BaseModel):
    edit_id: str
    accept: bool
    note: str | None = None


class DecisionsIn(BaseModel):
    decisions: list[EditDecisionIn]
    author: str | None = Field(default=None, description="кто принял решение (для истории)")


class TaskPatchIn(BaseModel):
    """Ручная правка черновика лектором (создаёт новую версию, source=edited)."""

    title: str | None = None
    summary: str | None = None
    context_md: str | None = None
    statement_md: str | None = None
    deliverables: list[str] | None = None
    submission_format: str | None = None
    public_rubric_note: str | None = None
    learning_objectives: list[str] | None = None
    criteria: list[Criterion] | None = None
    reference_solution_md: str | None = None
    common_mistakes: list[str] | None = None
    reviewer_notes: str | None = None


# --------------------------------------------------------------------------- #
#  API: ответы
# --------------------------------------------------------------------------- #


class TaskDraftOut(BaseModel):
    id: str
    root_id: str
    version: int
    source: Literal["generated", "edited", "revised"]
    gen_status: Literal["generating", "ready", "generation_failed"] = "ready"
    gen_error: str | None = None
    idea_id: str | None
    created_at: datetime
    data: TaskDraftData
    total_points: float
    changelog: list[dict] = Field(default_factory=list)


class ValidationRunOut(BaseModel):
    id: str
    task_draft_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    config: ValidationConfigIn
    created_at: datetime
    updated_at: datetime
    progress: str
    result: ValidationResult | None = None
    error: str | None = None


class PersonaOut(BaseModel):
    key: str
    title: str
    description: str


# --------------------------------------------------------------------------- #
#  Менеджер задач: список и статусы
# --------------------------------------------------------------------------- #

TaskStatus = Literal[
    "generating",  # задание генерируется в фоне
    "generation_failed",  # генерация упала
    "draft",  # сгенерировано/импортировано, валидация ещё не запускалась
    "validating",  # идёт прогон валидации
    "needs_review",  # прогон завершён, есть открытые находки/правки — ждёт решения человека
    "checked",  # прогон завершён, рубрика сошлась без правок
    "revised",  # правки применены — есть версия revised
    "failed",  # последний прогон упал
]


class RunBrief(BaseModel):
    id: str
    task_draft_id: str
    status: Literal["pending", "running", "succeeded", "failed"]
    progress: str
    converged: bool | None = None
    open_findings: int = 0
    proposed_edits: int = 0
    rounds: int = 0
    cost_rub: float = 0.0
    created_at: datetime
    updated_at: datetime


class TaskListItem(BaseModel):
    root_id: str
    id: str  # последняя версия
    title: str
    track: str | None = None
    task_format: str | None = None
    version: int
    source: Literal["generated", "edited", "revised"]
    total_points: float
    criteria_count: int
    status: TaskStatus
    created_at: datetime
    updated_at: datetime
    last_run: RunBrief | None = None
