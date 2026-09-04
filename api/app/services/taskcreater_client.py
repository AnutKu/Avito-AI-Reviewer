"""HTTP-клиент к движку конструктора заданий (микросервис task-creater).

Движок — счётная машина: генерирует блоки и гоняет AI-персон. Задание хранит
кабинет, поэтому в движок ходит только сервер, а браузер — никогда: иначе
появилось бы второе хранилище заданий и два разных ответа на вопрос «а какая
версия настоящая».
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from ..config import settings


class TaskCreaterError(RuntimeError):
    """Движок ответил, но ответ непригоден."""


class TaskCreaterUnavailable(TaskCreaterError):
    """Сеть, таймаут, сервис не поднят. Повтор имеет смысл."""


class TaskCreaterClient:
    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.taskcreater_url).rstrip("/")
        self.timeout = timeout or settings.taskcreater_timeout_seconds

    def _request(
        self, method: str, path: str, payload: dict | None = None, timeout: float | None = None
    ) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", "User-Agent": "avito-core-api/0.1"},
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode()).get("detail", f"HTTP {exc.code}")
            except (UnicodeDecodeError, json.JSONDecodeError):
                detail = f"HTTP {exc.code}"
            if isinstance(detail, list):  # 422 от FastAPI приходит списком ошибок
                detail = "; ".join(str(item.get("msg", item)) for item in detail)
            raise TaskCreaterError(str(detail)) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise TaskCreaterUnavailable("Конструктор заданий недоступен") from exc

    # -- помощь по одному блоку ------------------------------------------
    def assist_field(
        self, *, field: str, mode: str, current: str = "", instruction: str = "", context: dict | None = None
    ) -> dict:
        return self._request(
            "POST",
            "/assist/field",
            {
                "field": field,
                "mode": mode,
                "current": current,
                "instruction": instruction,
                "context": context or {},
            },
        )

    def assist_criterion(self, *, title: str, max_points: float, student_hint: str = "",
                         description: str = "", task_context: dict | None = None) -> dict:
        return self._request(
            "POST",
            "/assist/criterion",
            {
                "title": title,
                "max_points": max_points,
                "student_hint": student_hint,
                "description": description,
                "task_context": task_context or {},
            },
        )

    # -- черновик из идеи -------------------------------------------------
    def generate_task(self, idea: dict) -> dict:
        """Ставит генерацию в очередь движка и сразу возвращает заготовку с id.

        Синхронно ждать нельзя: сборка задания с критериями и эталоном идёт
        одну-две минуты, а держать всё это время открытым HTTP-запрос — значит
        упереться в таймаут любого прокси между браузером и сервисом.
        """

        return self._request("POST", "/tasks/generate", {"background": True, "idea": idea})

    def get_task(self, task_id: str) -> dict:
        return self._request("GET", f"/tasks/{urllib.parse.quote(task_id)}")

    # -- прогон AI-персон -------------------------------------------------
    def import_task(self, payload: dict) -> dict:
        return self._request("POST", "/tasks/import", payload)

    def start_validation(
        self, task_id: str, *, persona_type: str, max_rounds: int = 1, samples: int = 1
    ) -> dict:
        return self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(task_id)}/validate",
            {"persona_type": persona_type, "max_rounds": max_rounds, "grader_samples": samples},
        )

    def get_run(self, run_id: str) -> dict:
        return self._request("GET", f"/validation-runs/{urllib.parse.quote(run_id)}")
