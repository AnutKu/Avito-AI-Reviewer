"""Мультиагентная валидация критериев как граф LangGraph.

Узлы = агенты (генератор, решатель, грейдер, критик) + служебные шаги
(подготовка раунда, теневое применение правок). Рёбра = поток управления:
fan-out по профилям и решениям через `Send`, условная маршрутизация цикла раундов.
"""

from app.graph.build import build_validation_graph
from app.graph.ops import apply_edits, build_score_matrix, consolidate_edits
from app.graph.runtime import close_run, ctx, open_run
from app.graph.state import GraphState

__all__ = [
    "build_validation_graph",
    "GraphState",
    "open_run",
    "close_run",
    "ctx",
    "apply_edits",
    "consolidate_edits",
    "build_score_matrix",
]
