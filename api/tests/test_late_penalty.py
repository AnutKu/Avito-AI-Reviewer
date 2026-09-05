"""Штраф за просрочку: арифметика и, главное, границы.

Это код, который меняет оценку живого человека, поэтому тесты здесь в основном
про то, где он обязан НЕ срабатывать: нет правила, нет просрочки, кривая
настройка. Ошибка в любую сторону — несправедливый балл, и заметят её не сразу.
"""

from datetime import UTC, datetime, timedelta

from app.services.late_penalty import (
    Rule,
    describe,
    explain,
    late_days,
    parse_rule,
    penalty,
)

DEADLINE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
POINTS = Rule(per_day=1, unit="points", max_penalty=3)
PERCENT = Rule(per_day=10, unit="percent", max_penalty=30)


# --- когда штрафа нет ------------------------------------------------------


def test_no_rule_means_the_score_is_untouched():
    """Большинство заданий штрафа не предусматривает — это норма, не край."""

    assert penalty(None, days=5, score=8, max_score=10) == 0.0


def test_in_time_work_is_never_penalised():
    assert late_days(DEADLINE, DEADLINE) == 0
    assert late_days(DEADLINE, DEADLINE - timedelta(hours=1)) == 0
    assert penalty(POINTS, 0, score=8, max_score=10) == 0.0


def test_a_missing_deadline_cannot_be_missed():
    assert late_days(None, DEADLINE + timedelta(days=5)) == 0
    assert late_days(DEADLINE, None) == 0


def test_a_zero_score_has_nothing_to_take_away():
    assert penalty(POINTS, 3, score=0, max_score=10) == 0.0


# --- сутки -----------------------------------------------------------------


def test_a_started_day_counts_as_a_whole_one():
    """Опоздание на час и на двадцать три — одинаково «первые сутки»."""

    assert late_days(DEADLINE, DEADLINE + timedelta(hours=1)) == 1
    assert late_days(DEADLINE, DEADLINE + timedelta(hours=23)) == 1
    assert late_days(DEADLINE, DEADLINE + timedelta(hours=25)) == 2
    assert late_days(DEADLINE, DEADLINE + timedelta(days=3)) == 3


# --- арифметика ------------------------------------------------------------


def test_points_rule_takes_a_point_per_day():
    assert penalty(POINTS, 2, score=8, max_score=10) == 2.0


def test_the_cap_holds():
    assert penalty(POINTS, 10, score=9, max_score=10) == 3.0


def test_percent_rule_counts_from_the_maximum_not_from_the_score():
    # 10% в сутки от максимума 10 — это ровно 1 балл в сутки, сколько бы студент
    # ни набрал: иначе слабая работа штрафовалась бы мягче сильной.
    assert penalty(PERCENT, 2, score=4, max_score=10) == 2.0
    assert penalty(PERCENT, 2, score=9, max_score=10) == 2.0


def test_percent_cap_is_also_a_percent():
    assert penalty(PERCENT, 10, score=10, max_score=10) == 3.0


def test_the_penalty_never_exceeds_what_was_earned():
    """Штраф — вычет из заработанного, а не долг: ниже нуля работа не уходит."""

    assert penalty(Rule(per_day=5, unit="points"), 4, score=3, max_score=10) == 3.0


def test_a_rule_without_a_cap_still_stops_at_the_score():
    assert penalty(Rule(per_day=2, unit="points"), 100, score=7, max_score=10) == 7.0


# --- разбор настройки ------------------------------------------------------


def test_a_rule_is_read_from_the_task_settings():
    rule = parse_rule({"per_day": 1.5, "unit": "points", "max_penalty": 3})
    assert rule and rule.per_day == 1.5 and rule.max_penalty == 3


def test_no_settings_no_rule():
    for raw in (None, {}, "штраф -1 в день", []):
        assert parse_rule(raw) is None


def test_broken_settings_are_ignored_rather_than_thrown():
    """У ревьюера в момент оценки нет полномочий чинить настройку задания."""

    assert parse_rule({"per_day": "много"}) is None
    assert parse_rule({"per_day": 0}) is None
    assert parse_rule({"per_day": -1}) is None
    assert parse_rule({"per_day": 1, "unit": "бананов"}) is None


def test_a_rule_without_a_cap_is_valid():
    rule = parse_rule({"per_day": 1, "unit": "points"})
    assert rule and rule.max_penalty is None


# --- объяснение ------------------------------------------------------------


def test_the_rule_reads_as_a_sentence():
    assert describe(POINTS) == "−1 б. за каждые начатые сутки просрочки, но не больше −3 б."
    assert describe(Rule(per_day=10, unit="percent")) == "−10% за каждые начатые сутки просрочки"
    assert describe(None) == ""


def test_the_arithmetic_is_shown_not_just_the_result():
    text = explain(POINTS, 2, 2.0)
    assert "2 сут." in text and "−2" in text
    assert explain(POINTS, 0, 0.0) == "", "нечего объяснять, когда ничего не сняли"
