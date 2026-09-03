"""Пер-ранный контекст, который нельзя (и не нужно) класть в состояние графа.

LLM-клиент и счётчик расхода живут здесь, в реестре по `run_id`; в состоянии графа
только сериализуемые данные. Узлы достают контекст через `ctx(run_id)`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.config import settings
from app.llm import LLMClient, UsageAccumulator


@dataclass
class RunContext:
    llm: LLMClient
    usage: UsageAccumulator
    sem: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(settings.solver_concurrency))


_REGISTRY: dict[str, RunContext] = {}


def open_run(run_id: str, *, model_fast: str | None = None, model_smart: str | None = None) -> RunContext:
    usage = UsageAccumulator()
    llm = LLMClient(usage=usage)
    llm.set_models(model_fast, model_smart)
    ctx_obj = RunContext(llm=llm, usage=usage)
    _REGISTRY[run_id] = ctx_obj
    return ctx_obj


def ctx(run_id: str) -> RunContext:
    return _REGISTRY[run_id]


def close_run(run_id: str) -> RunContext | None:
    return _REGISTRY.pop(run_id, None)
