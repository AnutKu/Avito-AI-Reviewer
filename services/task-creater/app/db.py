"""Async SQLAlchemy: движок, сессия, ORM-модели.

Схема намеренно JSONB-центрична: тело задания, конфиг и результат прогона лежат
как документы. Новые типы курсов/критериев/находок не требуют миграций —
это часть аргумента о масштабируемости.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    # JSON работает и в Postgres (как JSONB через dialect), и в SQLite — удобно для тестов.
    type_annotation_map = {dict: JSON, list: JSON}


class CourseIdea(Base):
    __tablename__ = "course_ideas"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON)


class TaskDraft(Base):
    __tablename__ = "task_drafts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    root_id: Mapped[str] = mapped_column(String(32), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    source: Mapped[str] = mapped_column(String(16), default="generated")
    idea_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("course_ideas.id"), nullable=True)
    parent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    data: Mapped[dict] = mapped_column(JSON)
    changelog: Mapped[list] = mapped_column(JSON, default=list)


class ValidationRun(Base):
    __tablename__ = "validation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    task_draft_id: Mapped[str] = mapped_column(String(32), ForeignKey("task_drafts.id"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    progress: Mapped[str] = mapped_column(Text, default="создан")
    config: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )


class EditDecision(Base):
    __tablename__ = "edit_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    validation_run_id: Mapped[str] = mapped_column(String(32), ForeignKey("validation_runs.id"))
    resulting_task_draft_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    payload: Mapped[dict] = mapped_column(JSON)


async def init_models() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Лёгкая миграция для БД, созданных до расширения колонки (без Alembic).
        if engine.url.get_backend_name().startswith("postgresql"):
            from sqlalchemy import text

            try:
                await conn.execute(text("ALTER TABLE validation_runs ALTER COLUMN progress TYPE TEXT"))
            except Exception:  # noqa: BLE001 — колонка уже TEXT или прав нет
                pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
