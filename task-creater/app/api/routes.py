"""HTTP API сервиса task-creater."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.personas import PERSONAS
from app.config import settings
from app.db import SessionLocal, get_session
from app.schemas import (
    CourseIdeaIn,
    DecisionsIn,
    GenerateTaskIn,
    PersonaOut,
    RunBrief,
    TaskDraftOut,
    TaskListItem,
    TaskPatchIn,
    ValidationConfigIn,
    ValidationResult,
    ValidationRunOut,
)
from app.services import task_service as tasks
from app.services import validation_service as validations
from app.services.export import to_dict, to_markdown

router = APIRouter()


# --------------------------------------------------------------------------- #
#  Служебное
# --------------------------------------------------------------------------- #


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"status": "ok", "llm_fake": settings.llm_fake, "time": datetime.now(UTC).isoformat()}


@router.get("/personas", response_model=list[PersonaOut], tags=["meta"])
async def list_personas() -> list[PersonaOut]:
    return [PersonaOut(key=p.key, title=p.title, description=p.description) for p in PERSONAS.values()]


# --------------------------------------------------------------------------- #
#  Идеи
# --------------------------------------------------------------------------- #


@router.post("/ideas", tags=["ideas"], status_code=201)
async def create_idea(idea: CourseIdeaIn, session: AsyncSession = Depends(get_session)) -> dict:
    row = await tasks.create_idea(session, idea)
    return {"id": row.id, "payload": row.payload}


@router.get("/ideas/{idea_id}", tags=["ideas"])
async def get_idea(idea_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    row = await tasks.get_idea(session, idea_id)
    if not row:
        raise HTTPException(404, "идея не найдена")
    return {"id": row.id, "payload": row.payload}


# --------------------------------------------------------------------------- #
#  Черновики заданий
# --------------------------------------------------------------------------- #


@router.get("/tasks", response_model=list[TaskListItem], tags=["tasks"])
async def list_tasks(
    status: str | None = Query(None, description="фильтр по статусу"),
    q: str | None = Query(None, description="поиск по заголовку"),
    session: AsyncSession = Depends(get_session),
) -> list[TaskListItem]:
    """Менеджер задач: по строке на задание (последняя версия + последний прогон)."""
    return await tasks.list_tasks(session, status=status, q=q)


@router.post("/tasks/generate", response_model=TaskDraftOut, tags=["tasks"], status_code=201)
async def generate_task(body: GenerateTaskIn, session: AsyncSession = Depends(get_session)) -> TaskDraftOut:
    if not body.idea_id and not body.idea:
        raise HTTPException(422, "нужен idea_id или idea")
    try:
        row = await tasks.generate_task(session, idea_id=body.idea_id, idea=body.idea)
    except tasks.NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return tasks.to_out(row)


@router.get("/tasks/{task_id}", response_model=TaskDraftOut, tags=["tasks"])
async def get_task(task_id: str, session: AsyncSession = Depends(get_session)) -> TaskDraftOut:
    row = await tasks.get_task(session, task_id)
    if not row:
        raise HTTPException(404, "черновик не найден")
    return tasks.to_out(row)


@router.get("/tasks/{root_id}/versions", response_model=list[TaskDraftOut], tags=["tasks"])
async def list_task_versions(
    root_id: str, session: AsyncSession = Depends(get_session)
) -> list[TaskDraftOut]:
    rows = await tasks.list_versions(session, root_id)
    if not rows:
        raise HTTPException(404, "версии не найдены")
    return [tasks.to_out(r) for r in rows]


@router.get("/tasks/{root_id}/versions/{version}", response_model=TaskDraftOut, tags=["tasks"])
async def get_task_version(
    root_id: str, version: int, session: AsyncSession = Depends(get_session)
) -> TaskDraftOut:
    row = await tasks.get_task_version(session, root_id, version)
    if not row:
        raise HTTPException(404, "версия не найдена")
    return tasks.to_out(row)


@router.get("/tasks/{root_id}/runs", response_model=list[RunBrief], tags=["tasks"])
async def list_task_runs(root_id: str, session: AsyncSession = Depends(get_session)) -> list[RunBrief]:
    """История прогонов валидации по всем версиям задания, новые сверху."""
    return await tasks.list_runs(session, root_id)


@router.patch("/tasks/{task_id}", response_model=TaskDraftOut, tags=["tasks"])
async def patch_task(
    task_id: str, patch: TaskPatchIn, session: AsyncSession = Depends(get_session)
) -> TaskDraftOut:
    try:
        row = await tasks.patch_task(session, task_id, patch)
    except tasks.NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    return tasks.to_out(row)


@router.get("/tasks/{task_id}/export", tags=["tasks"])
async def export_task(
    task_id: str,
    fmt: Literal["markdown", "json"] = Query("markdown", alias="format"),
    view: Literal["student", "reviewer"] = Query("reviewer"),
    session: AsyncSession = Depends(get_session),
):
    """view=student — бриф без скрытой рубрики и эталона; view=reviewer — всё."""
    row = await tasks.get_task(session, task_id)
    if not row:
        raise HTTPException(404, "черновик не найден")
    data = tasks.to_out(row).data
    if fmt == "json":
        return to_dict(data, view)
    return PlainTextResponse(to_markdown(data, view), media_type="text/markdown; charset=utf-8")


# --------------------------------------------------------------------------- #
#  Валидация критериев
# --------------------------------------------------------------------------- #


def _run_to_out(run) -> ValidationRunOut:
    return ValidationRunOut(
        id=run.id,
        task_draft_id=run.task_draft_id,
        status=run.status,
        config=ValidationConfigIn(**run.config),
        created_at=run.created_at or datetime.now(UTC),
        updated_at=run.updated_at or datetime.now(UTC),
        progress=run.progress,
        result=ValidationResult(**run.result) if run.result else None,
        error=run.error,
    )


@router.post(
    "/tasks/{task_id}/validate",
    response_model=ValidationRunOut,
    tags=["validation"],
    status_code=202,
)
async def start_validation(
    task_id: str,
    cfg: ValidationConfigIn = Body(default_factory=ValidationConfigIn),
    session: AsyncSession = Depends(get_session),
) -> ValidationRunOut:
    try:
        run = await validations.create_run(session, task_id, cfg)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    validations.launch(run.id)
    return _run_to_out(run)


@router.get("/validation-runs/{run_id}", response_model=ValidationRunOut, tags=["validation"])
async def get_validation_run(run_id: str, session: AsyncSession = Depends(get_session)) -> ValidationRunOut:
    run = await validations.get_run(session, run_id)
    if not run:
        raise HTTPException(404, "прогон не найден")
    return _run_to_out(run)


@router.get("/validation-runs/{run_id}/events", tags=["validation"])
async def validation_events(run_id: str):
    """SSE-поток статуса прогона — для показа прозрачности процесса в демо."""

    async def gen():
        last = None
        for _ in range(900):  # ~15 минут максимум
            async with SessionLocal() as s:
                run = await validations.get_run(s, run_id)
            if not run:
                yield "event: error\ndata: run not found\n\n"
                return
            payload = {"status": run.status, "progress": run.progress}
            if payload != last:
                yield f"event: progress\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                last = payload
            if run.status in ("succeeded", "failed"):
                yield f"event: done\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                return
            await asyncio.sleep(1.0)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/validation-runs/{run_id}/decisions", response_model=TaskDraftOut, tags=["validation"])
async def apply_decisions(
    run_id: str, decisions: DecisionsIn, session: AsyncSession = Depends(get_session)
) -> TaskDraftOut:
    try:
        row = await tasks.apply_decisions(session, run_id, decisions)
    except tasks.NotFoundError as e:
        raise HTTPException(404, str(e)) from e
    except tasks.ConflictError as e:
        raise HTTPException(409, str(e)) from e
    return tasks.to_out(row)
