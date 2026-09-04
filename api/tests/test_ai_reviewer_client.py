import unittest
from unittest.mock import Mock

from app.models import Assignment, Course, RubricVersion, Snapshot
from app.services.ai_reviewer_client import AiReviewerClient


class AiReviewerClientTest(unittest.TestCase):
    def test_review_contract_is_parsed(self):
        course = Course(title="Курс", tone_of_voice={"style": "предметный"})
        assignment = Assignment(title="MLflow", statement="Условие")
        assignment.course = course
        rubric = RubricVersion(
            version=1,
            criteria=[{"key": "runs", "title": "Запуски", "max_score": 2}],
            max_score=2,
            pass_score=1,
        )
        snapshot = Snapshot(content="solution", content_hash="hash", parsed_facts={})
        client = AiReviewerClient(base_url="http://ai-reviewer")
        client._request = Mock(
            return_value={
                "result": {
                    "summary": "Готово",
                    "criteria": [
                        {
                            "criterion_key": "runs",
                            "score": 2,
                            "verdict": "passed",
                            "confidence": "high",
                            "evidence": [{"quote": "solution", "anchor": "main.py"}],
                            "recommendation": "Нет замечаний",
                        }
                    ],
                    "draft_feedback": "Хорошая работа",
                    "signals": [],
                },
                "metadata": {
                    "provider": "z.ai",
                    "model": "glm-5.3-flash",
                    "prompt_hash": "hash",
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "request_id": "request-test",
                },
            }
        )

        response = client.review(assignment=assignment, rubric=rubric, snapshot=snapshot)

        self.assertEqual(response.metadata.model, "glm-5.3-flash")
        self.assertEqual(response.result.criteria[0].score, 2)
        client._request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
