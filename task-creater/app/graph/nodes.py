"""Узлы графа. Тело каждого узла — тонкая обёртка над агентом из `app.agents.roles`.

Синхронные вызовы агентов (instructor поверх litellm) выполняются в пуле потоков,
семафор ограничивает параллелизм внутри раунда.

Разделение видимости: `solve_one` даёт решателю только студенческий бриф;
`grade_one` и `critic` получают полную (скрытую) рубрику через `task_data`.
"""

from __future__ import annotations

import asyncio

from langgraph.graph import END
from langgraph.types import Send

from app.agents import roles
from app.agents.personas import PERSONAS
from app.graph.ops import apply_edits, build_score_matrix, build_score_samples
from app.graph.runtime import ctx
from app.graph.state import GraphState
from app.schemas import CourseIdeaIn, RoundArtifact

# --------------------------------------------------------------------------- #
#  Точка входа: генерировать задание или сразу валидировать переданные критерии
# --------------------------------------------------------------------------- #


def entry(state: GraphState) -> str:
    return "prepare_round" if state.get("working_criteria") else "generate"


async def generate(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    idea = CourseIdeaIn(**state["idea"])
    data = await asyncio.to_thread(roles.generate_task, c.llm, idea)
    return {
        "task_data": data,
        "generated": True,
        "language": idea.language,
        "original_criteria": [x.model_copy(deep=True) for x in data.criteria],
        "working_criteria": [x.model_copy(deep=True) for x in data.criteria],
    }


# --------------------------------------------------------------------------- #
#  Раунд валидации
# --------------------------------------------------------------------------- #


async def prepare_round(state: GraphState) -> dict:
    """Инкремент номера раунда и сброс пер-раундовых аккумуляторов."""
    return {"round_no": state.get("round_no", 0) + 1, "solutions": None, "gradings": None}


def fan_solvers(state: GraphState) -> list[Send]:
    cfg = state["config"]
    return [
        Send(
            "solve_one",
            {
                "run_id": state["run_id"],
                "persona": key,
                "task_data": state["task_data"],
                "working_criteria": state["working_criteria"],
                "solver_temperature": cfg["solver_temperature"],
            },
        )
        for key in state["personas"]
    ]


async def solve_one(payload: dict) -> dict:
    c = ctx(payload["run_id"])
    persona = PERSONAS[payload["persona"]]
    async with c.sem:
        out = await asyncio.to_thread(
            roles.solve,
            c.llm,
            payload["task_data"],
            payload["working_criteria"],
            persona,
            payload["solver_temperature"],
        )
    return {"solutions": [out]}


async def dispatch_grade(_: GraphState) -> dict:
    """Барьер fan-in: выполняется один раз после всех solve_one."""
    return {}


def fan_graders(state: GraphState) -> list[Send]:
    """По `grader_samples` оценок на каждое решение.

    Повторная оценка одного и того же решения по одной и той же рубрике — это
    замер стохастики самой модели: если баллы гуляют, дело не в решении, а в
    формулировке критерия.
    """

    samples = max(1, int(state["config"].get("grader_samples", 1)))
    return [
        Send(
            "grade_one",
            {
                "run_id": state["run_id"],
                "task_data": state["task_data"],
                "working_criteria": state["working_criteria"],
                "solution": sol,
            },
        )
        for sol in state["solutions"]
        for _ in range(samples)
    ]


async def grade_one(payload: dict) -> dict:
    c = ctx(payload["run_id"])
    async with c.sem:
        out = await asyncio.to_thread(
            roles.grade,
            c.llm,
            payload["task_data"],
            payload["working_criteria"],
            payload["solution"],
        )
    return {"gradings": [out]}


async def critic(state: GraphState) -> dict:
    c = ctx(state["run_id"])
    cfg = state["config"]
    working = state["working_criteria"]
    solutions = list(state["solutions"])
    gradings = list(state["gradings"])

    out = await asyncio.to_thread(
        roles.critique,
        c.llm,
        state["task_data"],
        working,
        gradings,
        solutions,
        cfg.get("persona_type", "reviewer"),
    )

    artifact = RoundArtifact(
        round_no=state["round_no"],
        criteria_snapshot=[x.model_copy(deep=True) for x in working],
        solutions=solutions,
        gradings=gradings,
        findings=out.findings,
        proposed_edits=out.proposed_edits,
        score_matrix=build_score_matrix(working, gradings),
        score_samples=build_score_samples(working, gradings),
        converged=out.converged,
        convergence_reason=out.convergence_reason,
    )

    if out.converged or not out.proposed_edits:
        converged, stop_reason = out.converged, (out.convergence_reason or "критик не предложил правок")
    elif state["round_no"] >= cfg["max_rounds"]:
        converged, stop_reason = False, "исчерпан лимит раундов"
    elif c.usage.over_budget(cfg["token_budget"]):
        converged, stop_reason = False, f"достигнут лимит токенов ({cfg['token_budget']})"
    else:
        converged, stop_reason = False, ""

    return {"rounds": [artifact], "converged": converged, "stop_reason": stop_reason}


def route_after_critic(state: GraphState) -> str:
    """Единственная точка решения «ещё раунд или выход»."""
    last = state["rounds"][-1]
    if last.converged or not last.proposed_edits:
        return END
    if state["round_no"] >= state["config"]["max_rounds"]:
        return END
    if ctx(state["run_id"]).usage.over_budget(state["config"]["token_budget"]):
        return END
    return "apply_edits"


async def apply_edits_node(state: GraphState) -> dict:
    """Теневое применение правок критика к копии критериев перед следующим раундом."""
    last = state["rounds"][-1]
    return {"working_criteria": apply_edits(last.criteria_snapshot, last.proposed_edits)}
