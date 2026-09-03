"""Тонкая обёртка над litellm + instructor: структурированный вывод по Pydantic-схеме,
ретраи, учёт токенов и стоимости, опциональный Langfuse и оффлайн-режим (fake).

Провайдер-агностик: тот же код работает с OpenAI-совместимым шлюзом (llm_api_base +
llm_api_key) и с родными провайдерами (ключи в окружении). Выбор модели — на уровне
вызова: "fast" для решателей/грейдера, "smart" для генератора/критика.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel

from app.config import settings
from app.llm.fakes import fake_structured

log = logging.getLogger("taskcreater.llm")

T = TypeVar("T", bound=BaseModel)

Tier = str  # "fast" | "smart"


class LLMError(RuntimeError):
    """Провайдер/шлюз вернул ошибку или недоступен. Мапится в HTTP 502."""


# Прайс шлюза vsellm.ru (RUB за 1M токенов) — не в справочнике litellm, т.к. это
# идентификаторы шлюза, а не апстрим-имена. Правьте цифры при изменении тарифа.
_GATEWAY_PRICING_RUB_PER_1M: dict[str, dict[str, float]] = {
    "google/gemini-3.5-flash-lite": {"input": 33, "output": 276},
    "google/gemini-3.5-flash": {"input": 100, "output": 500},
    "google/gemini-3.6-flash": {"input": 166, "output": 829},
    "google/gemini-3-flash-preview": {"input": 166, "output": 829},
    "google/gemini-2.5-flash": {"input": 166, "output": 829},
}


@dataclass
class UsageAccumulator:
    """Копит расход по всем вызовам одного прогона валидации."""

    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    _rub_per_usd: float = field(default_factory=lambda: settings.rub_per_usd)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, prompt: int, completion: int, cost_usd: float) -> None:
        with self._lock:
            self.llm_calls += 1
            self.prompt_tokens += prompt
            self.completion_tokens += completion
            self.cost_usd += cost_usd

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_rub(self) -> float:
        return round(self.cost_usd * self._rub_per_usd, 2)

    def over_budget(self, token_budget: int) -> bool:
        return self.total_tokens >= token_budget


def _register_gateway_pricing() -> None:
    if not settings.llm_api_base:
        return
    try:
        import litellm

        litellm.register_model(
            {
                model: {
                    "input_cost_per_token": p["input"] / settings.rub_per_usd / 1_000_000,
                    "output_cost_per_token": p["output"] / settings.rub_per_usd / 1_000_000,
                    "litellm_provider": "openai",
                    "mode": "chat",
                }
                for model, p in _GATEWAY_PRICING_RUB_PER_1M.items()
            }
        )
    except Exception as exc:  # noqa: BLE001 — прайсинг не критичен
        log.warning("не удалось зарегистрировать прайс шлюза: %s", exc)


class LLMClient:
    def __init__(self, usage: UsageAccumulator | None = None) -> None:
        self.usage = usage or UsageAccumulator()
        self._model = {"fast": settings.model_fast, "smart": settings.model_smart}
        self._instructor = None
        if not settings.llm_fake:
            self._setup_real()

    # -- настройка реального клиента ------------------------------------
    def _setup_real(self) -> None:
        import instructor
        import litellm

        litellm.drop_params = True
        litellm.suppress_debug_info = True
        _register_gateway_pricing()
        if settings.langfuse_enabled:
            litellm.success_callback = ["langfuse"]
            litellm.failure_callback = ["langfuse"]
        self._litellm = litellm
        self._instructor = instructor.from_litellm(litellm.completion)

    def set_models(self, fast: str | None, smart: str | None) -> None:
        if fast:
            self._model["fast"] = fast
        if smart:
            self._model["smart"] = smart

    def model_for(self, tier: Tier) -> str:
        return self._model.get(tier, self._model["fast"])

    # -- основной метод ------------------------------------------------
    _TRUNCATION_MARKS = ("max_tokens", "incomplete", "length limit", "finish_reason")
    _MAX_TOKENS_CAP = 16000

    def structured(
        self,
        *,
        system: str,
        user: str,
        schema: type[T],
        tier: Tier = "fast",
        temperature: float = 0.4,
        max_tokens: int | None = 6000,
    ) -> T:
        """Один вызов LLM с ответом, провалидированным по `schema`.

        При обрыве по длине автоматически повторяет один раз с удвоенным `max_tokens`.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        if settings.llm_fake:
            approx_prompt = (len(system) + len(user)) // 4
            obj = fake_structured(schema, system=system, user=user)
            approx_completion = len(json.dumps(obj.model_dump(), ensure_ascii=False)) // 4
            self.usage.add(approx_prompt, approx_completion, 0.0)
            return obj

        model = self.model_for(tier)
        cur = max_tokens or 6000
        for attempt in (1, 2):
            try:
                return self._call_once(model, messages, schema, temperature, cur)
            except Exception as exc:  # noqa: BLE001 — единая точка
                msg = str(exc).splitlines()[0][:300]
                truncated = any(m in str(exc).lower() for m in self._TRUNCATION_MARKS)
                if attempt == 1 and truncated and cur < self._MAX_TOKENS_CAP:
                    cur = min(cur * 2, self._MAX_TOKENS_CAP)
                    log.warning(
                        "llm.structured обрыв по длине model=%s schema=%s → повтор с max_tokens=%d",
                        model,
                        schema.__name__,
                        cur,
                    )
                    continue
                log.warning("llm.structured FAILED model=%s schema=%s: %s", model, schema.__name__, msg)
                raise LLMError(f"модель '{model}': {msg}") from exc
        raise AssertionError("unreachable")  # pragma: no cover

    def _call_once(
        self, model: str, messages: list[dict], schema: type[T], temperature: float, max_tokens: int
    ) -> T:
        params: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "num_retries": settings.llm_max_retries,
            "timeout": settings.llm_timeout_s,
            "response_model": schema,
        }
        if settings.llm_api_base:
            params["api_base"] = settings.llm_api_base
            params["custom_llm_provider"] = "openai"
        if settings.llm_api_key:
            params["api_key"] = settings.llm_api_key

        t0 = time.perf_counter()
        result, raw = self._instructor.chat.completions.create_with_completion(**params)
        dt = time.perf_counter() - t0

        prompt_tok, completion_tok, cost = self._account(raw)
        self.usage.add(prompt_tok, completion_tok, cost)
        log.info(
            "llm.structured model=%s schema=%s tokens=%d+%d cost_usd=%.5f %.1fs",
            model,
            schema.__name__,
            prompt_tok,
            completion_tok,
            cost,
            dt,
        )
        return result

    def _account(self, raw: Any) -> tuple[int, int, float]:
        usage = getattr(raw, "usage", None)
        prompt_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tok = int(getattr(usage, "completion_tokens", 0) or 0)
        cost = 0.0
        try:
            cost = float(self._litellm.completion_cost(completion_response=raw) or 0.0)
        except Exception:  # noqa: BLE001
            pass
        return prompt_tok, completion_tok, cost
