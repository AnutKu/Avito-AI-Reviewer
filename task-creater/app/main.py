"""Точка входа FastAPI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api import router
from app.config import settings
from app.db import init_models
from app.llm import LLMError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DESCRIPTION = """
AI-помощник лектора Авито Образование.

* **Генератор задания** — из идеи курса собирает домашнее задание с рубрикой:
  условие, критерии с весами, эталон, типичные ошибки.
* **Валидация критериев агентами** — несколько профилей студентов решают задание,
  агент-грейдер проводит предварительное ревью по рубрике, агент-критик находит
  слабые места формулировок и предлагает точечные правки. Итог применяет человек.
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_models()
    logging.getLogger("taskcreater").info(
        "старт: llm_fake=%s model_fast=%s model_smart=%s",
        settings.llm_fake,
        settings.model_fast,
        settings.model_smart,
    )
    yield


app = FastAPI(
    title="task-creater — AI-помощник лектора",
    version=__version__,
    description=DESCRIPTION,
    lifespan=lifespan,
    root_path=settings.root_path,
)
app.include_router(router)


@app.exception_handler(LLMError)
async def _llm_error_handler(_: Request, exc: LLMError) -> JSONResponse:
    """Ошибка провайдера/шлюза → 502 с понятным телом вместо голого 500."""
    return JSONResponse(status_code=502, content={"detail": f"LLM недоступен: {exc}"})


@app.get("/", tags=["meta"])
async def root() -> dict:
    return {
        "service": "task-creater",
        "version": __version__,
        "docs": "/docs",
        "llm_fake": settings.llm_fake,
    }
