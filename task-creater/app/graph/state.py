"""Состояние графа валидации.

Аккумуляторы `solutions` / `gradings` собираются fan-in'ом внутри раунда и
СБРАСЫВАЮТСЯ в начале следующего: узел `prepare_round` пишет туда `None`,
редьюсер `add_or_reset` трактует это как «очистить».
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from app.schemas import Criterion, GraderOutput, RoundArtifact, SolverOutput, TaskDraftData


def add_or_reset(current: list[Any] | None, update: list[Any] | None) -> list[Any]:
    if update is None:
        return []
    return (current or []) + list(update)


class GraphState(TypedDict, total=False):
    run_id: str

    # --- вход ---
    idea: dict | None  # CourseIdeaIn.model_dump() — если валидируем прямо из идеи
    language: str
    task_data: TaskDraftData  # канонический бриф + рубрика (из узла generate либо из аргументов)
    generated: bool  # прошёл ли узел generate
    original_criteria: list[Criterion]
    config: dict  # ValidationConfigIn.model_dump()
    personas: list[str]  # уже провалидированные ключи профилей

    # --- рабочее ---
    working_criteria: list[Criterion]
    round_no: int
    solutions: Annotated[list[SolverOutput], add_or_reset]
    gradings: Annotated[list[GraderOutput], add_or_reset]

    # --- выход ---
    rounds: Annotated[list[RoundArtifact], operator.add]
    converged: bool
    stop_reason: str
