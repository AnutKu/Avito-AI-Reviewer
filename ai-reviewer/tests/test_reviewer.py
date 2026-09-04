import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import Settings
from app.contracts import AssignmentInput, ReviewRequest, RubricInput, SnapshotInput
from app.reviewer import ZaiInvalidResponse, ZaiNotConfigured, ZaiReviewer


class FakeCompletions:
    """Список ответов — по одному на вызов; последний повторяется.

    Вызовов стало больше одного: ответ не по контракту модель чинит следующим
    сообщением. `kwargs` остаётся последним вызовом, `calls` хранит все.
    """

    def __init__(self, content):
        self.contents = [content] if isinstance(content, str) else list(content)
        self.calls = []

    @property
    def content(self):
        return self.contents[min(len(self.calls) - 1, len(self.contents) - 1)]

    @property
    def kwargs(self):
        return self.calls[-1] if self.calls else None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            model="glm-5.3-flash",
            request_id=f"request-test-{len(self.calls)}",
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


class FakeClient:
    def __init__(self, content):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))


def request():
    return ReviewRequest(
        assignment=AssignmentInput(
            title="MLflow",
            statement="Проведите эксперименты",
            tone_of_voice={"style": "предметный"},
        ),
        rubric=RubricInput(
            criteria=[{"key": "runs", "title": "Запуски", "max_score": 2}],
            max_score=2,
        ),
        snapshot=SnapshotInput(
            content="mlflow.start_run()",
            parsed_facts={"runs": 1},
        ),
    )


def response(score=2):
    return json.dumps(
        {
            "summary": "Требование выполнено.",
            "criteria": [
                {
                    "criterion_key": "runs",
                    "score": score,
                    "verdict": "passed",
                    "confidence": "high",
                    "evidence": [{"quote": "mlflow.start_run()", "anchor": "Файл: main.py"}],
                    "recommendation": "Замечаний нет.",
                }
            ],
            "draft_feedback": "Работа выполнена корректно.",
            "signals": [],
        },
        ensure_ascii=False,
    )


class ZaiReviewerTest(unittest.TestCase):
    def test_medium_reasoning_effort_is_valid_configuration(self):
        with patch.dict("os.environ", {"ZAI_REASONING_EFFORT": "medium"}):
            configured = Settings(_env_file=None)

        self.assertEqual(configured.zai_reasoning_effort, "medium")

    def test_missing_api_key_fails_explicitly(self):
        with self.assertRaises(ZaiNotConfigured):
            ZaiReviewer()

    def test_review_uses_flash_json_mode_and_validates_result(self):
        fake = FakeClient(response())
        result = ZaiReviewer(client=fake).review(request())

        self.assertEqual(result.result.criteria[0].score, 2)
        self.assertEqual(result.metadata.prompt_tokens, 100)
        self.assertEqual(fake.chat.completions.kwargs["model"], "glm-5.3-flash")
        self.assertEqual(fake.chat.completions.kwargs["response_format"], {"type": "json_object"})
        self.assertEqual(fake.chat.completions.kwargs["reasoning_effort"], "low")

    def test_score_above_rubric_maximum_is_rejected(self):
        with self.assertRaises(ZaiInvalidResponse):
            ZaiReviewer(client=FakeClient(response(score=3))).review(request())


if __name__ == "__main__":
    unittest.main()
