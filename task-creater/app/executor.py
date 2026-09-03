"""Точка расширения: реальное исполнение решений в песочнице.

В MVP решатели и грейдер работают только на LLM-рассуждении. Интерфейс заложен,
чтобы позже подключить sandbox (напр. Go/Python в контейнере с лимитами CPU/mem,
без сети): грейдер тогда получает ExecutionReport и опирается на факт компиляции
и прогона тестов, а не только на чтение кода.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from app.schemas import SolverOutput


class ExecutionReport(BaseModel):
    supported: bool = False
    compiled: bool | None = None
    tests_total: int | None = None
    tests_passed: int | None = None
    stdout_tail: str | None = None
    notes: str = "исполнение не выполнялось (LLM-only режим MVP)"


class SolutionExecutor(Protocol):
    async def run(self, solution: SolverOutput, *, language: str) -> ExecutionReport: ...


class NoopExecutor:
    """Ничего не запускает. Дефолт для MVP."""

    async def run(self, solution: SolverOutput, *, language: str) -> ExecutionReport:  # noqa: ARG002
        return ExecutionReport(supported=False)


def get_executor() -> SolutionExecutor:
    return NoopExecutor()
