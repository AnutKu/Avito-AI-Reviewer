"""Сборка графа валидации критериев.

START ─(есть критерии?)─────────────► prepare_round ◄──────────────┐
  └─(только идея)─► generate ─────────────┘                        │
                                         │ Send × профили         │
                                         ▼                        │
                                     solve_one   (параллельно)    │
                                         ▼                        │
                                    dispatch_grade                │
                                         │ Send × решения         │
                                         ▼                        │
                                     grade_one   (параллельно)    │
                                         ▼                        │
                                      critic ──► record round     │
                                         │                        │
                        ┌────────────────┴───────────────┐        │
                 сошлось / лимит                    ещё раунд      │
                        ▼                                ▼         │
                       END                         apply_edits ───┘
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph import nodes
from app.graph.state import GraphState

RECURSION_LIMIT = 80  # ~6 супершагов на раунд × до 4 раундов + генерация, с запасом


def build_validation_graph(checkpointer=None):
    """Компилирует граф. `checkpointer` (напр. AsyncPostgresSaver) — опционально,
    для durable / возобновляемых прогонов; по умолчанию прогон живёт одним вызовом.
    """
    g = StateGraph(GraphState)

    g.add_node("generate", nodes.generate)
    g.add_node("prepare_round", nodes.prepare_round)
    g.add_node("solve_one", nodes.solve_one)
    g.add_node("dispatch_grade", nodes.dispatch_grade)
    g.add_node("grade_one", nodes.grade_one)
    g.add_node("critic", nodes.critic)
    g.add_node("apply_edits", nodes.apply_edits_node)

    g.add_conditional_edges(START, nodes.entry, ["generate", "prepare_round"])
    g.add_edge("generate", "prepare_round")
    g.add_conditional_edges("prepare_round", nodes.fan_solvers, ["solve_one"])
    g.add_edge("solve_one", "dispatch_grade")
    g.add_conditional_edges("dispatch_grade", nodes.fan_graders, ["grade_one"])
    g.add_edge("grade_one", "critic")
    g.add_conditional_edges("critic", nodes.route_after_critic, ["apply_edits", END])
    g.add_edge("apply_edits", "prepare_round")

    return g.compile(checkpointer=checkpointer)
