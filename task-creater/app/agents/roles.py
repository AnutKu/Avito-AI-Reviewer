"""Агенты как функции: собирают промпт → один структурированный вызов LLM.

Все вызовы синхронные (instructor поверх litellm); параллелизм обеспечивает
оркестратор через asyncio.to_thread.

Разделение видимости: `solve` получает только студенческий бриф, `grade`/`critique`
— полную (скрытую) рубрику.
"""

from __future__ import annotations

from app.agents.personas import Persona
from app.llm import LLMClient
from app.llm import prompts as P
from app.schemas import (
    CourseIdeaIn,
    Criterion,
    CriterionAssistIn,
    CriticOutput,
    FieldAssistIn,
    FieldAssistOut,
    GeneratedTask,
    GraderOutput,
    SolverOutput,
    TaskDraftData,
)

_LANG = {"ru": "русский", "en": "английский"}


def generate_task(llm: LLMClient, idea: CourseIdeaIn) -> TaskDraftData:
    out = llm.structured(
        system=P.GENERATOR_SYSTEM.format(
            language=_LANG.get(idea.language, "русский"),
            format_hint=P._FORMAT_HINT.get(idea.task_format, "определи сам"),
        ),
        user=P.generator_user(idea),
        schema=GeneratedTask,
        tier="smart",
        temperature=0.5,
        max_tokens=9000,
    )
    return _normalize_points(TaskDraftData(**out.model_dump()), idea.total_points)


def solve(
    llm: LLMClient,
    task: TaskDraftData,
    criteria: list[Criterion],
    persona: Persona,
    temperature: float,
) -> SolverOutput:
    out = llm.structured(
        system=P.SOLVER_SYSTEM.format(
            persona_key=persona.key,
            persona_title=persona.title,
            persona_instructions=persona.instructions,
        ),
        user=P.solver_user(task, criteria, persona.key),
        schema=SolverOutput,
        tier="fast",
        temperature=temperature,
        max_tokens=7000,
    )
    out.persona = persona.key
    return out


def grade(
    llm: LLMClient,
    task: TaskDraftData,
    criteria: list[Criterion],
    solution: SolverOutput,
) -> GraderOutput:
    out = llm.structured(
        system=P.GRADER_SYSTEM,
        user=P.grader_user(task, criteria, solution),
        schema=GraderOutput,
        tier="fast",
        temperature=0.1,
        max_tokens=6000,
    )
    out.persona = solution.persona
    return out


def critique(
    llm: LLMClient,
    task: TaskDraftData,
    criteria: list[Criterion],
    gradings: list[GraderOutput],
    solvers: list[SolverOutput],
    persona_type: str = "reviewer",
) -> CriticOutput:
    return llm.structured(
        system=P.CRITIC_SYSTEM,
        user=P.critic_user(task, criteria, gradings, solvers, P.CRITIC_FOCUS.get(persona_type, "")),
        schema=CriticOutput,
        tier="smart",
        temperature=0.3,
        max_tokens=8000,
    )


def assist_criterion(llm: LLMClient, body: CriterionAssistIn) -> Criterion:
    """Достраивает критерий до применимого: признаки и уровни с порогами.

    Именно их отсутствие AI-ревьюеры возвращают замечанием чаще всего — дешевле
    попросить агента сразу, чем чинить это потом правкой по итогам прогона.
    """

    out = llm.structured(
        system=P.CRITERION_SYSTEM,
        user=P.criterion_user(
            body.title, body.max_points, body.student_hint, body.description, body.task_context
        ),
        schema=Criterion,
        tier="smart",
        temperature=0.3,
        max_tokens=3000,
    )
    return out.model_copy(update={"title": body.title, "max_points": body.max_points})


def assist_field(llm: LLMClient, body: FieldAssistIn) -> FieldAssistOut:
    """Предложение по одному блоку. Ничего не сохраняет — решает человек."""

    out = llm.structured(
        system=P.ASSIST_SYSTEM,
        user=P.assist_user(body.field, body.mode, body.current, body.instruction, body.context),
        schema=FieldAssistOut,
        tier="smart",
        temperature=0.4,
        max_tokens=3000,
    )
    return out.model_copy(update={"field": body.field})


def _normalize_points(task: TaskDraftData, target_total: float) -> TaskDraftData:
    """Приводит сумму весов критериев к заданной разбалловке (модель иногда мажет)."""
    current = sum(c.max_points for c in task.criteria)
    if current <= 0 or not task.criteria:
        return task
    if abs(current - target_total) < 1e-6:
        return task
    factor = target_total / current
    for c in task.criteria:
        c.max_points = round(c.max_points * factor, 2)
        for lvl in c.rubric_levels:
            lvl.points = round(lvl.points * factor, 2)
    drift = round(target_total - sum(c.max_points for c in task.criteria), 2)
    if drift and task.criteria:
        task.criteria[0].max_points = round(task.criteria[0].max_points + drift, 2)
        # Верхний уровень градации — это и есть «полный балл»: остатком его
        # сдвигает вместе с максимумом, иначе лестница перестаёт доходить
        # до верха и по ней нельзя поставить максимум.
        if task.criteria[0].rubric_levels:
            task.criteria[0].rubric_levels[-1].points = task.criteria[0].max_points
    return task
