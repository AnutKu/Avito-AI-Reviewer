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
    RunBrief,
    TaskDraftData,
    TaskDraftOut,
    TaskListItem,
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


# --------------------------------------------------------------------------- #
#  Менеджер задач: список со статусами и история прогонов
# --------------------------------------------------------------------------- #


def _run_brief(run: ValidationRun) -> RunBrief:
    res = ValidationResult(**run.result) if run.result else None
    return RunBrief(
        id=run.id,
        task_draft_id=run.task_draft_id,
        status=run.status,  # type: ignore[arg-type]
        progress=run.progress,
        converged=res.converged if res else None,
        open_findings=len(res.open_findings) if res else 0,
        proposed_edits=len(res.proposed_edits) if res else 0,
        rounds=len(res.rounds) if res else 0,
        cost_rub=res.metrics.cost_rub if res else 0.0,
        created_at=run.created_at or datetime.now(UTC),
        updated_at=run.updated_at or run.created_at or datetime.now(UTC),
    )


def _derive_status(latest: TaskDraft, run: RunBrief | None) -> str:
    if run is None:
        return "revised" if latest.source == "revised" else "draft"
    if run.status in ("pending", "running"):
        return "validating"
    if run.status == "failed":
        return "failed"
    # succeeded
    if latest.source == "revised":
        return "revised"
    if run.proposed_edits or run.open_findings:
        return "needs_review"
    return "checked"


async def list_tasks(
    session: AsyncSession, *, status: str | None = None, q: str | None = None
) -> list[TaskListItem]:
    """Одна строка на root_id — последняя версия + последний прогон валидации."""
    drafts = list(
        (await session.execute(select(TaskDraft).order_by(TaskDraft.version.desc()))).scalars().all()
    )
    latest_by_root: dict[str, TaskDraft] = {}
    root_of_draft: dict[str, str] = {}
    for d in drafts:
        root_of_draft[d.id] = d.root_id
        latest_by_root.setdefault(d.root_id, d)  # первая при version desc = максимальная

    runs = list(
        (await session.execute(select(ValidationRun).order_by(ValidationRun.created_at.desc())))
        .scalars()
        .all()
    )
    latest_run_by_root: dict[str, ValidationRun] = {}
    for r in runs:
        root = root_of_draft.get(r.task_draft_id)
        if root and root not in latest_run_by_root:
            latest_run_by_root[root] = r

    ideas = {i.id: i.payload for i in (await session.execute(select(CourseIdea))).scalars().all()}

    items: list[TaskListItem] = []
    for root, latest in latest_by_root.items():
        data = TaskDraftData(**latest.data)
        brief = _run_brief(latest_run_by_root[root]) if root in latest_run_by_root else None
        st = _derive_status(latest, brief)
        if status and st != status:
            continue
        if q and q.lower() not in data.title.lower():
            continue
        idea = ideas.get(latest.idea_id) or {}
        items.append(
            TaskListItem(
                root_id=root,
                id=latest.id,
                title=data.title,
                track=idea.get("track"),
                task_format=idea.get("task_format"),
                version=latest.version,
                source=latest.source,  # type: ignore[arg-type]
                total_points=data.total_points,
                criteria_count=len(data.criteria),
                status=st,  # type: ignore[arg-type]
                created_at=latest.created_at or datetime.now(UTC),
                updated_at=(brief.updated_at if brief else latest.created_at) or datetime.now(UTC),
                last_run=brief,
            )
        )
    items.sort(key=lambda x: x.updated_at, reverse=True)
    return items


async def list_runs(session: AsyncSession, root_id: str) -> list[RunBrief]:
    """Все прогоны валидации по любой версии задания, новые сверху."""
    versions = await list_versions(session, root_id)
    ids = [v.id for v in versions]
    if not ids:
        return []
    runs = (
        (
            await session.execute(
                select(ValidationRun)
                .where(ValidationRun.task_draft_id.in_(ids))
                .order_by(ValidationRun.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_run_brief(r) for r in runs]


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
