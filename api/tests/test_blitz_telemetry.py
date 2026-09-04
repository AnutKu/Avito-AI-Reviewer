"""Сведение поведенческих событий блиц-опроса.

Что здесь проверяется и чего здесь нет. Проверяется арифметика: как считаются
отлучки, набранное и вставленное и при каких значениях зажигаются пометки.

Не проверяется — и не может быть проверено тестом — верна ли сама пометка. Все
события приходят из браузера студента, подделываются открытой консолью и
описывают поведение, у которого всегда есть невинное объяснение. Пороги здесь
подобраны, а не выведены; тест фиксирует, что мы считаем именно то, что
собирались, а не то, что мы правы.
"""

import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services import blitz_telemetry as telemetry


def event(kind: str, offset_ms: int, question_id: str | None = None, size: int = 0):
    return SimpleNamespace(kind=kind, offset_ms=offset_ms, question_id=question_id, size=size)


def answers(**texts) -> list[dict]:
    return [{"question_id": key, "text": value} for key, value in texts.items()]


def answering(question: str, start: int, end: int) -> list:
    return [
        event("question_focus", start, question),
        event("question_blur", end, question),
    ]


class AwayTest(unittest.TestCase):
    def test_blur_and_hidden_describe_one_departure(self):
        # Alt-Tab в другое приложение даёт blur, переключение вкладки —
        # visibilitychange, а браузер нередко шлёт оба. Считать это двумя
        # уходами значило бы удваивать наблюдение на ровном месте.
        result = telemetry.aggregate(
            events=[
                *answering("q1", 0, 60_000),
                event("blur", 10_000),
                event("hidden", 10_050),
                event("visible", 40_000),
                event("focus", 40_050),
            ],
            answers=answers(q1="ответ"),
        )

        self.assertEqual(result["away_count"], 1)
        self.assertEqual(result["questions"][0]["away_count"], 1)

    def test_departure_without_return_lasts_until_the_form_is_sent(self):
        # Вкладку могли не вернуть: ответ отправлен, а focus так и не пришёл.
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 90_000), event("blur", 30_000)],
            answers=answers(q1="ответ"),
        )

        self.assertEqual(result["questions"][0]["longest_away_ms"], 60_000)

    def test_time_away_is_not_counted_as_time_spent_answering(self):
        result = telemetry.aggregate(
            events=[
                *answering("q1", 0, 100_000),
                event("blur", 20_000),
                event("focus", 70_000),
            ],
            answers=answers(q1="ответ"),
        )

        self.assertEqual(result["questions"][0]["active_ms"], 50_000)

    def test_departure_outside_the_question_does_not_count_against_it(self):
        # Ушёл до того, как открыл вопрос: к этому ответу это отношения не имеет.
        result = telemetry.aggregate(
            events=[
                event("blur", 0),
                event("focus", 60_000),
                *answering("q1", 70_000, 90_000),
            ],
            answers=answers(q1="ответ"),
        )

        self.assertEqual(result["questions"][0]["away_ms"], 0)
        self.assertEqual(result["questions"][0]["flags"], [])


class FlagTest(unittest.TestCase):
    def test_pasted_answer_is_marked(self):
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 5_000), event("paste", 1_000, "q1", 200)],
            answers=answers(q1="x" * 200),
        )

        self.assertIn("paste_dominant", result["questions"][0]["flags"])

    def test_typed_answer_is_not_marked(self):
        result = telemetry.aggregate(
            events=[
                *answering("q1", 0, 120_000),
                event("input_batch", 30_000, "q1", 100),
                event("input_batch", 60_000, "q1", 100),
            ],
            answers=answers(q1="x" * 200),
        )

        self.assertEqual(result["questions"][0]["flags"], [])

    def test_text_that_appeared_without_keystrokes_or_paste_is_marked(self):
        # Ни одного нажатия, ни одной вставки — а текст есть. Программная
        # подстановка, автозаполнение или отключённый сбор: смотреть глазами.
        result = telemetry.aggregate(
            events=answering("q1", 0, 3_000),
            answers=answers(q1="x" * 300),
        )

        self.assertIn("phantom_insert", result["questions"][0]["flags"])

    def test_short_answer_is_not_marked_on_rounding(self):
        # Батч ввода округляет: на коротком ответе десяток знаков разницы —
        # это округление, а не подстановка.
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 20_000), event("input_batch", 5_000, "q1", 25)],
            answers=answers(q1="x" * 40),
        )

        self.assertNotIn("phantom_insert", result["questions"][0]["flags"])

    def test_long_departure_mid_answer_is_marked(self):
        result = telemetry.aggregate(
            events=[
                *answering("q1", 0, 120_000),
                event("input_batch", 5_000, "q1", 200),
                event("blur", 10_000),
                event("focus", 100_000),
            ],
            answers=answers(q1="x" * 200),
        )

        self.assertIn("left_mid_answer", result["questions"][0]["flags"])

    def test_brief_switch_is_ordinary_behaviour(self):
        result = telemetry.aggregate(
            events=[
                *answering("q1", 0, 60_000),
                event("input_batch", 5_000, "q1", 200),
                event("blur", 10_000),
                event("focus", 15_000),
            ],
            answers=answers(q1="x" * 200),
        )

        self.assertNotIn("left_mid_answer", result["questions"][0]["flags"])

    def test_speed_beyond_human_typing_is_marked(self):
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 4_000), event("input_batch", 3_000, "q1", 300)],
            answers=answers(q1="x" * 300),
        )

        self.assertIn("implausible_speed", result["questions"][0]["flags"])


class IntegrityTest(unittest.TestCase):
    def test_client_timeline_longer_than_the_server_window_is_marked(self):
        # Клиент утверждает, что отвечал два часа, а опрос отправлен десять
        # минут назад. Одно из двух неверно, и оба варианта стоит посмотреть.
        sent = datetime.now(UTC)
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 7_200_000)],
            answers=answers(q1="ответ"),
            sent_at=sent,
            answered_at=sent + timedelta(minutes=10),
        )

        self.assertIn("timeline_implausible", result["flags"])

    def test_ordinary_session_passes_the_server_check(self):
        sent = datetime.now(UTC)
        result = telemetry.aggregate(
            events=[*answering("q1", 0, 300_000)],
            answers=answers(q1="ответ"),
            sent_at=sent,
            answered_at=sent + timedelta(minutes=6),
        )

        self.assertEqual(result["flags"], [])

    def test_absence_of_events_is_not_an_observation(self):
        # Скрипт отключён, JS недоступен, события не дошли. Длинный ответ без
        # единого события выглядит как подстановка, но это отсутствие данных,
        # а не наблюдение о студенте, и пометок здесь быть не должно.
        result = telemetry.aggregate(events=[], answers=answers(q1="x" * 500))

        self.assertFalse(result["collected"])
        self.assertEqual(result["questions"][0]["flags"], [])
