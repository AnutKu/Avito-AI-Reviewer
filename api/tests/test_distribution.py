"""Юнит-тесты ядра балансировщика — чистой функции `plan_distribution`.

БД не нужна: работаем на простых структурах `ReviewerState` / `Work`.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.services.distribution import (
    ReviewerState,
    Work,
    plan_distribution,
)

BASE = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def reviewer(
    name: str,
    *,
    spec: str | None = "data_science",
    available: bool = True,
    load: float = 0.0,
    count: int = 0,
    capacity: float = 12.0,
    last: datetime | None = None,
    rid: UUID | None = None,
) -> ReviewerState:
    return ReviewerState(
        id=rid or uuid4(),
        name=name,
        specialization=spec,
        is_available=available,
        base_load=load,
        active_count=count,
        capacity=capacity,
        last_assigned_at=last,
    )


def work(
    i: int,
    *,
    spec: str = "data_science",
    weight: float = 1.0,
    capacity: float = 12.0,
    minutes: int = 0,
    current: UUID | None = None,
) -> Work:
    return Work(
        submission_id=uuid4(),
        student_name=f"Студент {i}",
        assignment_title="ДЗ",
        specialization=spec,
        effort_weight=weight,
        submitted_at=BASE + timedelta(minutes=minutes),
        capacity=capacity,
        current_reviewer_id=current,
    )


def test_even_split_between_equal_reviewers():
    a = reviewer("A", rid=uuid4())
    b = reviewer("B", rid=uuid4())
    works = [work(i, minutes=i) for i in range(6)]

    plan = plan_distribution([a, b], works)

    assert all(p.reviewer_id is not None for p in plan)
    counts = {a.id: 0, b.id: 0}
    for p in plan:
        counts[p.reviewer_id] += 1
    assert counts[a.id] == 3
    assert counts[b.id] == 3


def test_round_robin_alternates_on_a_tie():
    a = reviewer("A", rid=uuid4())
    b = reviewer("B", rid=uuid4())
    plan = plan_distribution([a, b], [work(i, minutes=i) for i in range(4)])
    seq = [p.reviewer_id for p in plan]
    # Строгое чередование: никто не получает две подряд при полном паритете.
    assert seq[0] != seq[1]
    assert seq[1] != seq[2]
    assert seq[2] != seq[3]


def test_effort_weight_counts_more_than_work_count():
    light = reviewer("Лёгкий", load=0.0, rid=uuid4())
    plan = plan_distribution(
        [light],
        [work(0, weight=3.0, minutes=0), work(1, weight=1.0, minutes=1)],
    )
    assert [p.reviewer_id for p in plan] == [light.id, light.id]

    # Два ревьюера: тяжёлая работа (вес 3) уходит одному, дальше баланс
    # выравнивается лёгкими, а не по числу работ.
    a = reviewer("A", rid=uuid4())
    b = reviewer("B", rid=uuid4())
    works = [work(0, weight=3.0, minutes=0)] + [work(i, weight=1.0, minutes=i) for i in range(1, 4)]
    plan = plan_distribution([a, b], works)
    got = {a.id: 0.0, b.id: 0.0}
    for p, w in zip(plan, works, strict=True):
        got[p.reviewer_id] += w.effort_weight
    # Идеальный баланс по весу — 3 и 3.
    assert set(got.values()) == {3.0}


def test_specialization_filter_excludes_mismatch():
    ds = reviewer("DS", spec="data_science", rid=uuid4())
    go = reviewer("Go", spec="backend_go", rid=uuid4())
    plan = plan_distribution([ds, go], [work(0, spec="data_science")])
    assert plan[0].reviewer_id == ds.id
    assert "data_science" in plan[0].explanation


def test_universal_reviewer_matches_any_specialization():
    universal = reviewer("Универсал", spec=None, rid=uuid4())
    plan = plan_distribution([universal], [work(0, spec="whatever")])
    assert plan[0].reviewer_id == universal.id


def test_unavailable_reviewer_is_skipped():
    on = reviewer("Доступен", rid=uuid4())
    off = reviewer("Недоступен", available=False, load=0.0, rid=uuid4())
    plan = plan_distribution([on, off], [work(0), work(1, minutes=1)])
    assert {p.reviewer_id for p in plan} == {on.id}


def test_no_candidate_returns_none_with_reason():
    go = reviewer("Go", spec="backend_go", rid=uuid4())
    plan = plan_distribution([go], [work(0, spec="data_science")])
    assert plan[0].reviewer_id is None
    assert "Нет доступного ревьюера" in plan[0].explanation


def test_hard_cap_is_respected_until_everyone_is_full():
    small = reviewer("A", capacity=2.0, rid=uuid4())
    big = reviewer("B", capacity=2.0, rid=uuid4())
    # 4 работы веса 1 → ровно по 2 каждому, всё в пределах капа.
    plan = plan_distribution([small, big], [work(i, capacity=2.0, minutes=i) for i in range(4)])
    assert all(not p.over_capacity for p in plan)
    per = {small.id: 0, big.id: 0}
    for p in plan:
        per[p.reviewer_id] += 1
    assert per == {small.id: 2, big.id: 2}


def test_over_capacity_is_flagged_not_dropped():
    solo = reviewer("Единственный", capacity=1.0, rid=uuid4())
    plan = plan_distribution(
        [solo], [work(0, capacity=1.0, minutes=0), work(1, capacity=1.0, minutes=1)]
    )
    assert plan[0].reviewer_id == solo.id and plan[0].over_capacity is False
    assert plan[1].reviewer_id == solo.id and plan[1].over_capacity is True
    assert "сверх лимита" in plan[1].explanation


def test_existing_base_load_pulls_work_to_the_lighter_reviewer():
    busy = reviewer("Загружен", load=5.0, count=5, rid=uuid4())
    free = reviewer("Свободен", load=0.0, rid=uuid4())
    plan = plan_distribution([busy, free], [work(0)])
    assert plan[0].reviewer_id == free.id


def test_least_recently_assigned_wins_the_first_tie():
    old = reviewer("Давно", last=BASE - timedelta(days=3), rid=uuid4())
    recent = reviewer("Недавно", last=BASE - timedelta(hours=1), rid=uuid4())
    plan = plan_distribution([old, recent], [work(0)])
    assert plan[0].reviewer_id == old.id


def test_exclude_current_keeps_work_off_its_present_reviewer():
    a = reviewer("A", rid=uuid4())
    b = reviewer("B", rid=uuid4())
    w = work(0, current=a.id)
    plan = plan_distribution([a, b], [w], exclude_current=True)
    assert plan[0].reviewer_id == b.id


def test_exclude_current_with_no_alternative_returns_none():
    a = reviewer("A", rid=uuid4())
    w = work(0, current=a.id)
    plan = plan_distribution([a], [w], exclude_current=True)
    assert plan[0].reviewer_id is None


def test_plan_is_deterministic_regardless_of_input_order():
    ids = [uuid4() for _ in range(3)]
    revs = [reviewer(n, rid=i) for n, i in zip("ABC", ids, strict=True)]
    works_a = [work(i, minutes=i) for i in range(9)]
    works_b = list(reversed(works_a))

    plan_a = plan_distribution(revs, works_a)
    plan_b = plan_distribution(list(reversed(revs)), works_b)

    map_a = {p.submission_id: p.reviewer_id for p in plan_a}
    map_b = {p.submission_id: p.reviewer_id for p in plan_b}
    assert map_a == map_b


def test_explanation_reports_candidate_count():
    revs = [reviewer(n, rid=uuid4()) for n in "ABC"]
    plan = plan_distribution(revs, [work(0)])
    assert "кандидатов рассмотрено: 3" in plan[0].explanation


if __name__ == "__main__":  # запуск без pytest: `python tests/test_distribution.py`
    raise SystemExit(pytest.main([__file__, "-q"]))
