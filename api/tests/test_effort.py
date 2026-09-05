"""Счёт экономии времени и денег.

Эти цифры пойдут в разговор про экономический эффект, поэтому здесь
проверяется не арифметика ради арифметики, а три обещания: время человека
после машины не забыто, ориентир «как было» не появляется без источника, а
ставка часа не подставляется за заказчика.
"""

import pytest

from app.services.effort import (
    BASELINE_BY_OPERATION,
    BASELINES,
    cost_usd,
    payback_ratio,
    saved_minutes,
)


def test_time_the_human_still_spends_is_subtracted():
    """Машина посчитала 40 секунд — это не значит, что работа проверена."""

    naive = 60 - 40 / 60
    honest = saved_minutes(manual_minutes=60, machine_seconds=40, human_minutes=12.5)
    assert honest == pytest.approx(46.83, abs=0.01)
    assert honest < naive - 12, "время ревьюера после разбора не вычтено"


def test_no_human_time_left_means_full_saving():
    assert saved_minutes(30, 60, 0) == 29.0


def test_automation_can_come_out_worse_and_the_number_says_so():
    """Если после машины остаётся больше работы, чем было, экономия отрицательная."""

    assert saved_minutes(manual_minutes=5, machine_seconds=120, human_minutes=10) < 0


def test_every_baseline_names_its_source():
    assert BASELINES, "ориентиров нет вовсе"
    for baseline in BASELINES:
        assert baseline.source.strip(), f"{baseline.operation}: ориентир без источника"
        assert baseline.minutes > 0
        assert baseline.note.strip(), f"{baseline.operation}: не сказано, что именно измерялось"


def test_manual_review_baseline_matches_the_interview():
    """Час на работу — прямая цитата из интервью с ревьюером, не наша оценка."""

    assert BASELINE_BY_OPERATION["review"].minutes == 60.0
    assert "нтервью" in BASELINE_BY_OPERATION["review"].source


def test_cost_follows_the_tariff():
    assert cost_usd(1_000_000, 0, price_in=0.075, price_out=0.25) == 0.075
    assert cost_usd(0, 1_000_000, price_in=0.075, price_out=0.25) == 0.25
    assert cost_usd(28_000, 2_400, price_in=0.075, price_out=0.25) == pytest.approx(0.0027, abs=1e-4)


def test_free_call_costs_nothing():
    assert cost_usd(0, 0, price_in=0.075, price_out=0.25) == 0.0


def test_payback_is_not_computed_without_an_hourly_rate():
    """Своих ставок Авито не раскрывал. Подставить «примерно рыночную» нельзя."""

    assert payback_ratio(46.8, 0.0027, 0) is None
    assert payback_ratio(46.8, 0.0, 30) is None


def test_payback_ratio_is_a_multiple_of_the_spend():
    ratio = payback_ratio(saved_minutes_value=60, cost=0.01, hourly_rate=30)
    assert ratio == pytest.approx(3000.0, rel=0.01)
