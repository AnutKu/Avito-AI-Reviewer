"""Градация внутри критерия: за что ставится каждый балл.

Раньше критерий доезжал до ревьюера как «название + максимум»: сколько снимать
за пропущенный крайний случай — оставалось на глаз, и два ревьюера ставили за
одну работу разное. Здесь проверяется, что генератор без градации не проходит,
что лестница остаётся лестницей после всех преобразований рубрики и что
уточнение формулировки её не стирает.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.roles import _normalize_points, generate_task
from app.llm import LLMClient
from app.pipeline import apply_edits
from app.schemas import (
    CourseIdeaIn,
    Criterion,
    CriterionEdit,
    GeneratedTask,
    RubricLevel,
    TaskDraftData,
    grading_gap,
)


def _levels(*points: float) -> list[RubricLevel]:
    return [
        RubricLevel(points=p, label=f"уровень {p}", descriptor=f"наблюдаемый признак на {p}")
        for p in points
    ]


def _crit(key: str, pts: float, levels: list[RubricLevel] | None = None) -> Criterion:
    return Criterion(
        key=key,
        title=key.title(),
        description="что именно проверяется",
        max_points=pts,
        check_kind="objective",
        evidence_hint="куда смотреть",
        rubric_levels=levels or [],
    )


def _task(criteria: list[Criterion]) -> dict:
    return dict(
        title="Задание",
        summary="Что сделать и зачем",
        statement_md="Постановка",
        criteria=criteria,
        reference_solution_md="эталон",
        common_mistakes=["ошибка"],
    )


# --- лестница как шкала критерия ------------------------------------------


def test_levels_are_sorted_even_if_the_model_returned_them_upside_down():
    crit = _crit("a", 2, _levels(2, 0, 1))

    assert [level.points for level in crit.rubric_levels] == [0, 1, 2]


def test_levels_must_reach_the_maximum():
    # Иначе максимум критерия недостижим по его же градации.
    with pytest.raises(ValidationError, match="доходить до"):
        _crit("a", 3, _levels(0, 1, 2))


def test_levels_must_start_at_zero():
    with pytest.raises(ValidationError, match="начинаться с 0"):
        _crit("a", 2, _levels(1, 2))


def test_two_levels_on_the_same_score_are_a_contradiction():
    with pytest.raises(ValidationError, match="один и тот же балл"):
        Criterion(
            key="a",
            title="A",
            description="описание",
            max_points=2,
            check_kind="objective",
            evidence_hint="куда смотреть",
            rubric_levels=[
                RubricLevel(points=0, label="нет", descriptor="ничего"),
                RubricLevel(points=2, label="да", descriptor="одно"),
                RubricLevel(points=2, label="да", descriptor="другое"),
            ],
        )


def test_a_hand_made_criterion_may_have_no_levels_at_all():
    # Рубрику заводят и руками, в кабинете; отсутствие градации — не ошибка.
    assert _crit("a", 2).rubric_levels == []


# --- у сгенерированного критерия градация обязательна ----------------------


def test_generation_without_levels_is_rejected():
    with pytest.raises(ValidationError, match="нет градации"):
        GeneratedTask(**_task([_crit("a", 3)]))


def test_generation_with_a_hole_in_the_ladder_is_rejected():
    # 0 и 3 есть, а за что ставится 1 и 2 — не сказано.
    with pytest.raises(ValidationError, match=r"не описаны баллы \[1, 2\]"):
        GeneratedTask(**_task([_crit("a", 3, _levels(0, 3))]))


def test_generation_with_a_level_per_point_passes():
    task = GeneratedTask(**_task([_crit("a", 3, _levels(0, 1, 2, 3))]))

    assert grading_gap(task.criteria[0]) is None


def test_a_heavy_criterion_needs_three_levels_but_not_nine():
    # На критерии в 8 баллов требование «уровень на каждый балл» превращается
    # в формальность: хватает 0, середины и максимума.
    assert grading_gap(_crit("a", 8, _levels(0, 4, 8))) is None
    assert "не меньше трёх" in grading_gap(_crit("a", 8, _levels(0, 8)))


# --- лестница переживает преобразования рубрики ----------------------------


def test_normalizing_weights_keeps_the_top_level_equal_to_the_maximum():
    # Остаток разбалловки досыпается первому критерию: если не сдвинуть верхний
    # уровень вместе с максимумом, полный балл станет недостижим.
    # Три равных веса на десять баллов не делятся нацело — остаток будет.
    task = TaskDraftData(**_task([_crit(key, 1, _levels(0, 1)) for key in "abc"]))

    _normalize_points(task, 10)

    top = task.criteria[0]
    assert top.max_points != task.criteria[1].max_points, "иначе остаток не досыпался и тест пуст"
    assert top.rubric_levels[-1].points == top.max_points
    assert sum(c.max_points for c in task.criteria) == 10


def test_refining_the_wording_does_not_erase_the_gradation():
    base = [_crit("a", 2, _levels(0, 1, 2))]
    edit = CriterionEdit(
        id="E1",
        operation="modify",
        criterion_key="a",
        proposed_criterion=_crit("a", 2),  # критик прислал критерий без уровней
        rationale="уточнили формулировку",
        addresses=[],
        severity="medium",
    )

    out = apply_edits(base, [edit])

    assert [level.points for level in out[0].rubric_levels] == [0, 1, 2]


def test_a_changed_weight_drops_the_old_gradation_instead_of_lying():
    # Лестница до 2 баллов на критерии в 4 балла — не «сохранённая градация»,
    # а неверная: пусть лучше её не будет.
    base = [_crit("a", 2, _levels(0, 1, 2))]
    edit = CriterionEdit(
        id="E1",
        operation="modify",
        criterion_key="a",
        proposed_criterion=_crit("a", 4),
        rationale="переоценили вес",
        addresses=[],
        severity="medium",
    )

    out = apply_edits(base, [edit])

    assert out[0].rubric_levels == []


# --- оффлайн-режим ---------------------------------------------------------


def test_offline_generation_grades_every_criterion():
    # Оффлайн-ответ обязан быть валиден ровно как настоящий: иначе демо-сценарий
    # перестаёт быть репетицией и первым же реальным прогоном всплывает то,
    # что здесь должно было упасть.
    task = generate_task(LLMClient(), CourseIdeaIn(idea="Учебное задание про метрики", track="Аналитика"))

    for criterion in task.criteria:
        assert criterion.rubric_levels, criterion.key
        assert criterion.rubric_levels[0].points == 0
        assert criterion.rubric_levels[-1].points == criterion.max_points
