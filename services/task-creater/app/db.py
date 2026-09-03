"""Async SQLAlchemy: движок, сессия, ORM-модели.

Схема намеренно JSONB-центрична: тело задания, конфиг и результат прогона лежат
как документы. Новые типы курсов/критериев/находок не требуют миграций —
это часть аргумента о масштабируемости.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON

from app.config import settings

log = logging.getLogger("taskcreater.db")

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


async def _ensure_database() -> None:
    """Создаёт целевую БД на общем сервере Postgres, если её ещё нет.

    Позволяет ходить в тот же контейнер postgres, что и остальной стек, без
    отдельного контейнера БД под этот сервис. Своя БД (а не общая) — чтобы схема
    не пересекалась с core api. Идемпотентно, переживает уже существующий volume.
    """
    url = engine.url
    if not url.get_backend_name().startswith("postgresql"):
        return
    dbname = (url.database or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_]+", dbname):
        return

    admin_url = url.set(drivername="postgresql+asyncpg", database="postgres")
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": dbname}
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
                log.info("создана БД %s на общем сервере postgres", dbname)
    except Exception as exc:  # noqa: BLE001 — сервер не готов / нет прав / гонка старта
        log.warning("не удалось подготовить БД %s (%s); полагаемся, что она уже есть", dbname, exc)
    finally:
        await admin_engine.dispose()


async def init_models() -> None:
    await _ensure_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Лёгкая миграция для БД, созданных до расширения колонки (без Alembic).
        if engine.url.get_backend_name().startswith("postgresql"):
            try:
                await conn.execute(text("ALTER TABLE validation_runs ALTER COLUMN progress TYPE TEXT"))
            except Exception:  # noqa: BLE001 — колонка уже TEXT или прав нет
                pass


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
