import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock, patch

from app.models import AiStatus, Review
from app.services.ai_reviewer_client import (
    AiReviewerError,
    AiReviewerNotConfigured,
    AiReviewerUnavailable,
)
from app.services.review_pipeline import (
    _review_with_retries,
    blitz_questions_with_retries,
    is_stale,
    running_since,
)


def running(started_ago_seconds: float | None) -> Review:
    review = Review(ai_status=AiStatus.RUNNING, raw_result={})
    review.created_at = datetime.now(UTC)
    if started_ago_seconds is not None:
        started = datetime.now(UTC) - timedelta(seconds=started_ago_seconds)
        review.raw_result = {"started_at": started.isoformat()}
    return review


class RunningSinceTest(unittest.TestCase):
    def test_reads_start_time_from_raw_result(self):
        review = running(120)

        self.assertAlmostEqual(
            (datetime.now(UTC) - running_since(review)).total_seconds(), 120, delta=5
        )

    def test_falls_back_to_created_at_without_marker(self):
        review = running(None)

        self.assertEqual(running_since(review), review.created_at)

    def test_falls_back_to_created_at_on_broken_marker(self):
        review = running(None)
        review.raw_result = {"started_at": "не дата"}

        self.assertEqual(running_since(review), review.created_at)


class IsStaleTest(unittest.TestCase):
    def test_fresh_run_is_not_stale(self):
        with patch("app.services.review_pipeline.settings.ai_review_stale_after_seconds", 600):
            self.assertFalse(is_stale(running(30)))

    def test_run_past_the_deadline_is_stale(self):
        with patch("app.services.review_pipeline.settings.ai_review_stale_after_seconds", 600):
            self.assertTrue(is_stale(running(900)))

    def test_only_running_reviews_can_be_stale(self):
        review = running(900)
        review.ai_status = AiStatus.READY

        with patch("app.services.review_pipeline.settings.ai_review_stale_after_seconds", 600):
            self.assertFalse(is_stale(review))


class ReviewRetryTest(unittest.TestCase):
    def setUp(self):
        self.kwargs = {"assignment": Mock(), "rubric": Mock(), "snapshot": Mock()}
        delay = patch("app.services.review_pipeline.settings.ai_review_retry_delay_seconds", 0)
        delay.start()
        self.addCleanup(delay.stop)

    def run_with(self, side_effect, attempts=2):
        client = Mock()
        client.review = Mock(side_effect=side_effect)
        with (
            patch("app.services.review_pipeline.AiReviewerClient", return_value=client),
            patch("app.services.review_pipeline.settings.ai_review_max_attempts", attempts),
        ):
            try:
                return client, _review_with_retries(**self.kwargs)
            finally:
                self.attempts_made = client.review.call_count

    def test_transient_failure_is_retried_and_succeeds(self):
        client, result = self.run_with([AiReviewerUnavailable("сеть"), "ok"])

        self.assertEqual(result, "ok")
        self.assertEqual(client.review.call_count, 2)

    def test_invalid_provider_response_is_retried(self):
        client, result = self.run_with([AiReviewerError("контракт"), "ok"])

        self.assertEqual(result, "ok")
        self.assertEqual(client.review.call_count, 2)

    def test_missing_api_key_is_not_retried(self):
        with self.assertRaises(AiReviewerNotConfigured):
            self.run_with(AiReviewerNotConfigured("ZAI_API_KEY не настроен"))

        self.assertEqual(self.attempts_made, 1)

    def test_attempts_are_bounded(self):
        with self.assertRaises(AiReviewerUnavailable):
            self.run_with(AiReviewerUnavailable("сеть"), attempts=3)

        self.assertEqual(self.attempts_made, 3)


class BlitzQuestionsRetryTest(unittest.TestCase):
    """Генерация вопросов идёт синхронно из роутера и раньше повторов не имела.

    Первый же живой прогон это и поймал: модель отдала два вопроса правильной
    формы и один — нет, а ревьюер увидел красную ошибку вместо черновика.
    """

    def setUp(self):
        self.kwargs = {"assignment": Mock(), "snapshot": Mock(), "count": 3, "focus": []}
        delay = patch("app.services.review_pipeline.settings.ai_review_retry_delay_seconds", 0)
        delay.start()
        self.addCleanup(delay.stop)

    def run_with(self, side_effect, attempts=2):
        client = Mock()
        client.blitz_questions = Mock(side_effect=side_effect)
        with (
            patch("app.services.review_pipeline.AiReviewerClient", return_value=client),
            patch("app.services.review_pipeline.settings.ai_review_max_attempts", attempts),
        ):
            try:
                return client, blitz_questions_with_retries(**self.kwargs)
            finally:
                self.attempts_made = client.blitz_questions.call_count

    def test_response_off_contract_is_retried(self):
        client, result = self.run_with(
            [AiReviewerError("Ответ Z.AI не соответствует контракту"), "ok"]
        )

        self.assertEqual(result, "ok")
        self.assertEqual(client.blitz_questions.call_count, 2)

    def test_missing_api_key_is_not_retried(self):
        with self.assertRaises(AiReviewerNotConfigured):
            self.run_with(AiReviewerNotConfigured("ZAI_API_KEY не настроен"))

        self.assertEqual(self.attempts_made, 1)

    def test_the_reviewer_still_sees_a_failure_that_keeps_repeating(self):
        # Повтор прячет промах выборки, а не сломанного провайдера.
        with self.assertRaises(AiReviewerError):
            self.run_with(AiReviewerError("контракт"))


if __name__ == "__main__":
    unittest.main()
