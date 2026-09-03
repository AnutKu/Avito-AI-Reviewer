"""Прогоны валидации критериев: постановка, фоновое выполнение, чтение статуса."""

from __future__ import annotations

import asyncio
import logging
import traceback
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, TaskDraft, ValidationRun
from app.pipeline import run_validation
from app.schemas import TaskDraftData, ValidationConfigIn

log = logging.getLogger("taskcreater.validation")

# держим ссылки на фоновые задачи, чтобы их не собрал GC
_BG_TASKS: set[asyncio.Task] = set()


async def create_run(session: AsyncSession, task_draft_id: str, cfg: ValidationConfigIn) -> ValidationRun:
    task = await session.get(TaskDraft, task_draft_id)
    if not task:
        raise LookupError(f"черновик {task_draft_id} не найден")
    run = ValidationRun(
        task_draft_id=task_draft_id,
        status="pending",
        progress="поставлен в очередь",
        config=cfg.model_dump(),
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


async def get_run(session: AsyncSession, run_id: str) -> ValidationRun | None:
    return await session.get(ValidationRun, run_id)


def launch(run_id: str) -> None:
    task = asyncio.create_task(_execute(run_id))
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)


async def _set(run_id: str, **fields) -> None:
    if isinstance(fields.get("progress"), str) and len(fields["progress"]) > 500:
        fields["progress"] = fields["progress"][:497] + "…"
    async with SessionLocal() as s:
        run = await s.get(ValidationRun, run_id)
        if not run:
            return
        for k, v in fields.items():
            setattr(run, k, v)
        run.updated_at = datetime.now(UTC)
        await s.commit()


async def _execute(run_id: str) -> None:
    async with SessionLocal() as s:
        run = await s.get(ValidationRun, run_id)
        if not run:
            return
        cfg = ValidationConfigIn(**run.config)
        task = await s.get(TaskDraft, run.task_draft_id)
        data = TaskDraftData(**task.data)

    await _set(run_id, status="running", progress="старт")

    async def progress(msg: str) -> None:
        log.info("run %s: %s", run_id, msg)
        await _set(run_id, progress=msg)

    try:
        result = await run_validation(task=data, cfg=cfg, progress=progress)
        await _set(
            run_id,
            status="succeeded",
            progress=result.summary,
            result=result.model_dump(),
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 — фон, ошибку кладём в запись
        log.exception("run %s упал", run_id)
        await _set(
            run_id,
            status="failed",
            progress="ошибка",
            error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}",
        )
