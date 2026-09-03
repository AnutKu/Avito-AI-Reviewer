"""Точка входа в мультиагентную валидацию критериев.

Оркестрация вынесена в граф LangGraph (`app.graph`). Здесь — драйвер: запуск
графа стримом, трансляция прогресса и сборка `ValidationResult` из финального
состояния. Чистые операции над критериями ре-экспортируются для обратной
совместимости (сервисы и тесты импортируют их отсюда).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from app.agents.personas import resolve_personas
from app.graph import build_validation_graph
from app.graph.ops import apply_edits, build_score_matrix, consolidate_edits
from app.graph.runtime import RunContext, close_run, open_run
from app.graph.state import GraphState
from app.schemas import (
    CourseIdeaIn,
    Criterion,
    Finding,
    RoundArtifact,
    RunMetrics,
    TaskDraftData,
    ValidationConfigIn,
    ValidationResult,
)

__all__ = [
    "run_validation",
    "apply_edits",
    "consolidate_edits",
    "build_score_matrix",
]

ProgressCB = Callable[[str], Awaitable[None]]


async def _noop(_: str) -> None:
    return None


async def run_validation(
    *,
    cfg: ValidationConfigIn,
    task: TaskDraftData | None = None,
    statement_md: str | None = None,
    criteria: list[Criterion] | None = None,
    idea: CourseIdeaIn | None = None,
    language: str = "ru",
    progress: ProgressCB = _noop,
    run_id: str | None = None,
) -> ValidationResult:
    """Прогоняет граф валидации. Один из: `task` (TaskDraftData), `criteria`
    (+`statement_md`), либо `idea` (тогда сработает узел generate)."""
    if task is None and criteria is None and idea is None:
        raise ValueError("нужны task, criteria или idea")

    run_id = run_id or uuid.uuid4().hex
    personas = resolve_personas(cfg.personas)  # ранняя валидация: бросит ValueError
    rctx = open_run(run_id, model_fast=cfg.model_fast, model_smart=cfg.model_smart)
    t0 = time.perf_counter()

    if task is None and criteria is not None:
        task = TaskDraftData(
            title="(без названия)",
            summary="",
            statement_md=statement_md or "",
            criteria=criteria,
            reference_solution_md="",
            common_mistakes=[],
        )

    init: GraphState = {
        "run_id": run_id,
        "config": cfg.model_dump(),
        "personas": [p.key for p in personas],
        "language": language,
    }
    if task is not None:
        init["task_data"] = task
        init["original_criteria"] = [c.model_copy(deep=True) for c in task.criteria]
        init["working_criteria"] = [c.model_copy(deep=True) for c in task.criteria]
    if idea is not None:
        init["idea"] = idea.model_dump()

    graph = build_validation_graph()
    graph_cfg = {"recursion_limit": 80}

    final_state: GraphState | None = None
    last_msg: str | None = None
    try:
        async for state in graph.astream(init, graph_cfg, stream_mode="values"):
            final_state = state  # type: ignore[assignment]
            msg = _derive_progress(state)
            if msg and msg != last_msg:
                last_msg = msg
                await progress(msg)
        if final_state is None:  # pragma: no cover
            raise RuntimeError("граф не вернул состояния")
        return _assemble_result(final_state, rctx, t0)
    finally:
        close_run(run_id)


# --------------------------------------------------------------------------- #


def _derive_progress(state: GraphState) -> str:
    r = state.get("round_no", 0)
    if r == 0:
        return "задание сгенерировано, старт валидации" if state.get("generated") else "инициализация графа"
    mx = state.get("config", {}).get("max_rounds", "?")
    done = len(state.get("rounds", []))
    if done >= r:
        return f"раунд {r}/{mx}: критик завершил (готово раундов: {done})"
    n_grade = len(state.get("gradings") or [])
    n_solve = len(state.get("solutions") or [])
    if n_grade:
        return f"раунд {r}/{mx}: предварительное ревью решений ({n_grade})"
    if n_solve:
        return f"раунд {r}/{mx}: решают профили ({n_solve})"
    return f"раунд {r}/{mx}: подготовка"


def _assemble_result(state: GraphState, rctx: RunContext, t0: float) -> ValidationResult:
    rounds: list[RoundArtifact] = list(state.get("rounds", []))
    if not rounds:
        raise RuntimeError("граф не произвёл ни одного раунда валидации")

    original = state.get("original_criteria") or rounds[0].criteria_snapshot
    last = rounds[-1]
    recommended = apply_edits(last.criteria_snapshot, last.proposed_edits)
    consolidated = consolidate_edits(original, recommended, rounds)

    converged = bool(state.get("converged"))
    stop_reason = state.get("stop_reason") or ""
    open_findings: list[Finding] = (
        [] if converged else [f for rd in rounds for f in rd.findings if f.severity in ("medium", "high")]
    )

    usage = rctx.usage
    dt = round(time.perf_counter() - t0, 2)
    metrics = RunMetrics(
        llm_calls=usage.llm_calls,
        prompt_tokens=usage.prompt_tokens,
        completion_tokens=usage.completion_tokens,
        total_tokens=usage.total_tokens,
        cost_usd=round(usage.cost_usd, 5),
        cost_rub=usage.cost_rub,
        duration_s=dt,
        model_fast=rctx.llm.model_for("fast"),
        model_smart=rctx.llm.model_for("smart"),
    )
    summary = (
        f"{len(rounds)} раунд(ов); предложено правок: {len(consolidated)}; "
        f"{'рубрика сошлась' if converged else 'нужно решение человека'} ({stop_reason}). "
        f"Расход: {usage.total_tokens} токенов ≈ {usage.cost_rub} ₽ за {dt} c."
    )

    return ValidationResult(
        rounds=rounds,
        recommended_criteria=recommended,
        open_findings=open_findings,
        proposed_edits=consolidated,
        converged=converged,
        summary=summary,
        metrics=metrics,
    )
