import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .config import settings
from .db import SessionLocal, engine
from .models import Base
from .routers import auth, common, methodist, reviewer, student
from .real_course_loader import prepare as prepare_cabinet
from .seed import seed_demo
from .services.review_pipeline import recover_orphaned_detections, recover_orphaned_reviews
from .services.task_ai import recover_orphaned_runs

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
    "ALTER TABLE rubric_versions ADD COLUMN IF NOT EXISTS assignment_snapshot JSONB "
    "NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS authoring JSONB "
    "NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE ai_task_runs ADD COLUMN IF NOT EXISTS samples INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS late_penalty DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS late_penalty_note TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS duration_ms INTEGER NOT NULL DEFAULT 0",
    # Градация внутри критерия какое-то время называлась `rubric_levels` — так её
    # звали в движке. В кабинете она `levels`, и по этому имени её читает экран
    # ревьюера. Переименовываем ключ в уже сохранённых рубриках, иначе заведённая
    # раньше градация просто перестанет находиться.
    """UPDATE rubric_versions SET criteria = (
        SELECT jsonb_agg(
            CASE WHEN item ? 'rubric_levels'
                 THEN (item - 'rubric_levels') || jsonb_build_object('levels', item -> 'rubric_levels')
                 ELSE item END
            ORDER BY ordinality
        )
        FROM jsonb_array_elements(criteria) WITH ORDINALITY AS t(item, ordinality)
    ) WHERE criteria::text LIKE '%rubric_levels%'""",
)


def _fill_empty_cabinet(db) -> None:
    """Чем наполнить кабинет на старте — и почему именно этим.

    По умолчанию настоящим курсом: задания, критерии, работы студентов и
    дословные ответы модели лежат в репозитории (`api/data/real_course`), так
    что на новой машине достаточно поднять контейнеры. Ключ к модели не нужен —
    разборы не пересчитываются, а читаются из файла.

    Решение всегда пишется в лог. «Ничего не изменилось после обновления» —
    самый частый вопрос про этот кусок запуска, и отвечать на него, читая код
    по серверам, не должно быть нужно.
    """

    log = logging.getLogger("uvicorn.error")
    outcome = prepare_cabinet(db, enabled=settings.real_course_on_start)
    if outcome["action"] == "loaded":
        log.info(
            "курс из репозитория (%s): работ %s, разборов %s, закрыто %s",
            outcome["reason"], outcome["works"], outcome["reviews"], outcome["closed"],
        )
        return
    log.info("курс из репозитория не загружен: %s", outcome["reason"])
    # Демонстрационный сев остаётся запасным вариантом — он и сам не тронет
    # базу, в которой уже есть чужой курс.
    seed_demo(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        for statement in _COLUMN_MIGRATIONS:
            connection.execute(text(statement))
    if settings.seed_on_start:
        with SessionLocal() as db:
            _fill_empty_cabinet(db)
    # AI-ревью выполняется в BackgroundTasks этого же процесса, поэтому всё, что
    # осталось в running, умерло вместе с предыдущим процессом. Без этого запись
    # висит в running навсегда и её нельзя ни перезапустить, ни завершить.
    recover_orphaned_reviews()
    recover_orphaned_detections()
    recover_orphaned_runs()
    # Выключенный флагом раздел просто исчезает с экрана — в этом и смысл, но
    # тогда «раздела нет» и «раздел не выкатили» выглядят одинаково. Строка в
    # логе отвечает на этот вопрос за две секунды, без чтения .env по серверам.
    flags = settings.feature_flags()
    # Логгер uvicorn, а не свой: корневой остаётся на WARNING, и строка на
    # INFO в него просто не дошла бы — а нужна она ровно в потоке старта.
    logging.getLogger("uvicorn.error").info(
        "фиче-флаги: включены [%s] · выключены [%s]",
        ", ".join(sorted(k for k, v in flags.items() if v)) or "—",
        ", ".join(sorted(k for k, v in flags.items() if not v)) or "—",
    )
    yield


app = FastAPI(
    title="Avito AI Reviewer Core API",
    version="0.1.0",
    description="Core domain integrated with the isolated AI reviewer service.",
    lifespan=lifespan,
)
# "*" со списком origin'ов несовместимо с credentials, поэтому режим "любой
# источник" отдаём регуляркой — она отражает конкретный Origin обратно.
_cors_origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
_cors_rule = (
    {"allow_origin_regex": ".*"} if "*" in _cors_origins else {"allow_origins": _cors_origins}
)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    **_cors_rule,
)
app.include_router(auth.router, prefix="/api")
app.include_router(common.router, prefix="/api")
app.include_router(student.router, prefix="/api")
app.include_router(reviewer.router, prefix="/api")
app.include_router(methodist.router, prefix="/api")


@app.get("/health", tags=["system"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "core-api",
        "ai_reviewer_url": settings.ai_reviewer_url,
        "ai_model": settings.ai_reviewer_model,
    }
