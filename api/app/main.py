from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import SessionLocal, engine
from .models import Base
from .routers import auth, common, methodist, reviewer, student
from .seed import seed_demo

# Точечные ALTER для колонок, добавленных после первого релиза, — чтобы
# существующий demo-volume поднялся без пересоздания (Alembic в MVP нет).
_COLUMN_MIGRATIONS = (
    "ALTER TABLE courses ADD COLUMN IF NOT EXISTS auto_assign BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS published_at TIMESTAMPTZ",
    # Задания, у которых уже есть сданные работы, — это точно не черновики:
    # публикуем их один раз (на черновик без работ условие не сработает).
    "UPDATE assignments a SET published_at = a.created_at "
    "WHERE a.published_at IS NULL "
    "AND EXISTS (SELECT 1 FROM submissions s WHERE s.assignment_id = a.id)",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for statement in _COLUMN_MIGRATIONS:
            connection.execute(text(statement))
    if settings.seed_on_start:
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(
    title="Avito AI Reviewer Core API",
    version="0.1.0",
    description="Core domain and mocked feature contracts for the unified cabinet.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router, prefix="/api")
app.include_router(common.router, prefix="/api")
app.include_router(student.router, prefix="/api")
app.include_router(reviewer.router, prefix="/api")
app.include_router(methodist.router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": "core-api", "mock_mode": True}
