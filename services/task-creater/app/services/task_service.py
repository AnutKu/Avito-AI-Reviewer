"""Работа с идеями и черновиками заданий: генерация, версионирование, ручные правки,
применение решений ревьюера по правкам критериев.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import roles
from app.db import CourseIdea, EditDecision, TaskDraft, ValidationRun
from app.llm import LLMClient
from app.pipeline import apply_edits
from app.schemas import (
    CourseIdeaIn,
    Criterion,
    CriterionEdit,
    DecisionsIn,
    TaskDraftData,
    TaskDraftOut,
    TaskPatchIn,
    ValidationResult,
)


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


def to_out(row: TaskDraft) -> TaskDraftOut:
    data = TaskDraftData(**row.data)
    created = row.created_at or datetime.now(UTC)
    return TaskDraftOut(
        id=row.id,
        root_id=row.root_id,
        version=row.version,
        source=row.source,  # type: ignore[arg-type]
        idea_id=row.idea_id,
        created_at=created,
        data=data,
        total_points=data.total_points,
        changelog=row.changelog or [],
    )


# --------------------------------------------------------------------------- #
#  Идеи
# --------------------------------------------------------------------------- #


async def create_idea(session: AsyncSession, idea: CourseIdeaIn) -> CourseIdea:
    row = CourseIdea(payload=idea.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_idea(session: AsyncSession, idea_id: str) -> CourseIdea | None:
    return await session.get(CourseIdea, idea_id)


# --------------------------------------------------------------------------- #
#  Черновики заданий
# --------------------------------------------------------------------------- #


async def generate_task(
    session: AsyncSession,
    *,
    idea_id: str | None = None,
    idea: CourseIdeaIn | None = None,
) -> TaskDraft:
    if idea_id:
        idea_row = await get_idea(session, idea_id)
        if not idea_row:
            raise NotFoundError(f"идея {idea_id} не найдена")
        idea_obj = CourseIdeaIn(**idea_row.payload)
    elif idea:
        idea_row = await create_idea(session, idea)
        idea_obj = idea
        idea_id = idea_row.id
    else:
        raise ValueError("нужен idea_id или idea")

    llm = LLMClient()
    data: TaskDraftData = await asyncio.to_thread(roles.generate_task, llm, idea_obj)

    new_id = uuid.uuid4().hex
    row = TaskDraft(
        id=new_id,
        root_id=new_id,
        source="generated",
        version=1,
        idea_id=idea_id,
        data=data.model_dump(),
        changelog=[],
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_task(session: AsyncSession, task_id: str) -> TaskDraft | None:
    return await session.get(TaskDraft, task_id)


async def latest_task(session: AsyncSession, root_id: str) -> TaskDraft | None:
    res = await session.execute(
        select(TaskDraft).where(TaskDraft.root_id == root_id).order_by(TaskDraft.version.desc())
    )
    return res.scalars().first()


async def get_task_version(session: AsyncSession, root_id: str, version: int) -> TaskDraft | None:
    res = await session.execute(
        select(TaskDraft).where(TaskDraft.root_id == root_id, TaskDraft.version == version)
    )
    return res.scalars().first()


async def list_versions(session: AsyncSession, root_id: str) -> list[TaskDraft]:
    res = await session.execute(
        select(TaskDraft).where(TaskDraft.root_id == root_id).order_by(TaskDraft.version.asc())
    )
    return list(res.scalars().all())


async def _next_version_row(
    session: AsyncSession,
    base: TaskDraft,
    *,
    data: TaskDraftData,
    source: str,
    change: dict,
) -> TaskDraft:
    latest = await latest_task(session, base.root_id)
    next_version = (latest.version if latest else base.version) + 1
    changelog = list(base.changelog or []) + [{**change, "version": next_version}]
    row = TaskDraft(
        root_id=base.root_id,
        version=next_version,
        source=source,
        idea_id=base.idea_id,
        parent_id=base.id,
        data=data.model_dump(),
        changelog=changelog,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def patch_task(session: AsyncSession, task_id: str, patch: TaskPatchIn) -> TaskDraft:
    base = await get_task(session, task_id)
    if not base:
        raise NotFoundError(f"черновик {task_id} не найден")
    data = TaskDraftData(**base.data)
    fields = patch.model_dump(exclude_none=True)
    updated = data.model_copy(update=fields)
    change = {
        "at": datetime.now(UTC).isoformat(),
        "kind": "manual_edit",
        "fields": sorted(fields.keys()),
    }
    return await _next_version_row(session, base, data=updated, source="edited", change=change)


async def apply_decisions(session: AsyncSession, run_id: str, decisions: DecisionsIn) -> TaskDraft:
    run = await session.get(ValidationRun, run_id)
    if not run:
        raise NotFoundError(f"прогон {run_id} не найден")
    if run.status != "succeeded" or not run.result:
        raise ConflictError("прогон ещё не завершён успешно — нечего применять")
    base = await get_task(session, run.task_draft_id)
    if not base:
        raise NotFoundError(f"черновик {run.task_draft_id} не найден")

    result = ValidationResult(**run.result)
    edits: list[CriterionEdit] = result.proposed_edits
    edit_ids = {e.id for e in edits}
    accepted = {d.edit_id for d in decisions.decisions if d.accept}
    unknown = (accepted | {d.edit_id for d in decisions.decisions}) - edit_ids
    if unknown:
        raise ConflictError(f"неизвестные id правок: {sorted(unknown)}")

    data = TaskDraftData(**base.data)
    new_criteria: list[Criterion] = apply_edits(data.criteria, edits, accepted_ids=accepted)
    if not new_criteria:
        raise ConflictError("после применения правок не осталось ни одного критерия")
    updated = data.model_copy(update={"criteria": new_criteria})

    change = {
        "at": datetime.now(UTC).isoformat(),
        "kind": "criteria_revision",
        "validation_run_id": run_id,
        "author": decisions.author,
        "decisions": [d.model_dump() for d in decisions.decisions],
        "applied_edit_ids": sorted(accepted),
    }
    new_row = await _next_version_row(session, base, data=updated, source="revised", change=change)

    session.add(
        EditDecision(
            validation_run_id=run_id,
            resulting_task_draft_id=new_row.id,
            payload=change,
        )
    )
    await session.commit()
    return new_row
