"""Конфигурация сервиса. Всё читается из окружения / .env, секреты в логи не попадают."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Единый .env — в корне репозитория; локальный (если создан) переопределяет.
        # В контейнере обоих файлов нет, конфиг приходит из docker-compose environment.
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_prefix="TASKCREATER_",
        extra="ignore",
    )

    # --- Хранилище -----------------------------------------------------------
    # В интегрированном стеке — общий контейнер postgres, своя база `taskcreater`
    # (см. docker-compose.yml в корне). Для тестов подменяется на sqlite.
    database_url: str = "postgresql+asyncpg://avito:avito@postgres:5432/taskcreater"

    # --- LLM-шлюз ----------------------------------------------------------
    # Провайдер-агностик через litellm. Задайте llm_api_base + llm_api_key для
    # OpenAI-совместимого шлюза (напр. vsellm.ru), либо родные ключи провайдера
    # (OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY — без префикса).
    llm_api_base: str | None = None
    llm_api_key: str | None = None
    model_fast: str = Field(default="gpt-4o-mini")
    model_smart: str = Field(default="gpt-4o")

    # Оффлайн-режим: детерминированные ответы вместо реальных вызовов LLM.
    # Нужен для тестов и для демо без доступа к шлюзу.
    llm_fake: bool = False

    # Курс валют для перевода стоимости шлюза (RUB/1M токенов) в отчётность.
    rub_per_usd: float = 90.0

    # --- Бюджеты и лимиты валидации ---------------------------------------
    default_max_rounds: int = 2
    default_token_budget: int = 200_000
    llm_max_retries: int = 2
    llm_timeout_s: float = 60.0
    solver_concurrency: int = 4

    # Префикс, под которым сервис проксируется снаружи (напр. "/task-creater" в
    # nginx единого кабинета) — чтобы Swagger/OpenAPI отдавали правильные пути.
    root_path: str = ""

    # --- Наблюдаемость (опционально) ------------------------------------
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "http://localhost:3000"

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
