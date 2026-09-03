"""Тестовое окружение: оффлайн-LLM + файловый SQLite (виден фоновым задачам)."""

from __future__ import annotations

import os
import pathlib

os.environ.setdefault("TASKCREATER_LLM_FAKE", "1")
_DB_FILE = pathlib.Path(__file__).parent / ".pytest-taskcreater.db"
os.environ.setdefault("TASKCREATER_DATABASE_URL", f"sqlite+aiosqlite:///{_DB_FILE}")

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import validation_service as _vs  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    for t in list(_vs._BG_TASKS):
        t.cancel()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
    _DB_FILE.unlink(missing_ok=True)
