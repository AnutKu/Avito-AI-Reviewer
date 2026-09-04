from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    zai_api_key: str | None = None
    zai_model: str = "glm-5.3-flash"
    zai_reasoning_effort: Literal["low", "medium", "high", "max"] = "low"
    zai_timeout_seconds: float = 120.0
    # Один и тот же MAX_SNAPSHOT_CHARS читают core api (режет при сборке снапшота)
    # и этот сервис (страховка перед отправкой в модель). Значения обязаны совпадать,
    # иначе часть снапшота молча не доедет до модели.
    max_snapshot_chars: int = 120_000


settings = Settings()
