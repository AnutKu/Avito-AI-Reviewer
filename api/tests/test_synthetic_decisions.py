"""Решения ревьюера, выведенные из разметки эксперта.

Эти данные попадают в статистику кабинета — в долю согласия с моделью и в
«критерии с частыми правками». Поэтому проверяется не «работает», а свойства,
без которых статистика соврёт: правки не выходят за шкалу, не сваливаются в
один критерий и не появляются там, где спорить не о чем.
"""

from app.synthetic_decisions import Judgement, calibrate

RUBRIC = [
    Judgement("a", 3.0, 3.0, "high"),
    Judgement("b", 2.0, 2.0, "medium"),
    Judgement("c", 3.0, 3.0, "high"),
    Judgement("d", 2.0, 2.0, "high"),
]


def total(decisions):
    return round(sum(decision.final_score for decision in decisions), 2)


def actions(decisions):
    return [decision.action for decision in decisions]


def test_reviewer_agrees_when_the_model_is_already_in_the_band():
    """Хорошая работа с высокой оценкой спора не вызывает."""

    decisions = calibrate(RUBRIC, level="strong")
    assert actions(decisions) == ["accepted"] * 4
    assert total(decisions) == 10.0


def test_generous_score_on_weak_work_is_pulled_down():
    decisions = calibrate(RUBRIC, level="weak")
    assert total(decisions) < 5.0
    for decision, item in zip(decisions, RUBRIC, strict=True):
        assert decision.final_score <= item.ai_score


def test_harsh_score_on_strong_work_is_pulled_up():
    harsh = [
        Judgement("a", 0.0, 3.0, "high"),
        Judgement("b", 0.0, 2.0, "high"),
        Judgement("c", 1.0, 3.0, "high"),
        Judgement("d", 0.0, 2.0, "high"),
    ]
    decisions = calibrate(harsh, level="strong")
    assert total(decisions) > 7.0
    for decision, item in zip(decisions, harsh, strict=True):
        assert decision.final_score >= item.ai_score


def test_scores_never_leave_the_scale():
    for level in ("weak", "medium", "strong"):
        for rubric in (RUBRIC, [Judgement("x", 0.0, 1.0, "low")]):
            for decision, item in zip(calibrate(rubric, level=level), rubric, strict=True):
                assert 0 <= decision.final_score <= item.max_score


def test_correction_is_spread_rather_than_dumped_into_one_criterion():
    """Расхождение в целую работу — это расхождение по многим пунктам."""

    decisions = calibrate(RUBRIC, level="weak")
    touched = [d for d in decisions if d.action != "accepted"]
    assert len(touched) >= 3, "правка свалена в один-два критерия"


def test_rejection_is_never_invented():
    """«Отклонить вывод» означает, что модель сослалась на отсутствующее.

    По одним баллам этого не видно, поэтому вывод здесь только правят. Проставить
    отклонение по догадке значило бы испортить ту самую статистику несогласия,
    ради которой эти решения и достраиваются."""

    for level in ("weak", "medium", "strong"):
        for rubric in (RUBRIC, [Judgement("a", 4.0, 4.0, "medium"), Judgement("b", 4.0, 4.0, "high")]):
            assert "rejected" not in actions(calibrate(rubric, level=level))


def test_small_gap_is_not_worth_an_argument():
    """Расхождение внутри допуска ревьюер не оспаривает."""

    near = [Judgement("a", 6.0, 10.0, "high")]
    assert actions(calibrate(near, level="medium")) == ["accepted"]


def test_unknown_level_means_no_grounds_to_argue():
    assert actions(calibrate(RUBRIC, level="")) == ["accepted"] * 4
    assert actions(calibrate(RUBRIC, level="неизвестно")) == ["accepted"] * 4


def test_empty_rubric_gives_no_decisions():
    assert calibrate([], level="weak") == []


def test_zero_scale_is_not_divided_by():
    decisions = calibrate([Judgement("a", 0.0, 0.0, "high")], level="weak")
    assert actions(decisions) == ["accepted"]


def test_result_is_deterministic():
    assert calibrate(RUBRIC, level="weak") == calibrate(RUBRIC, level="weak")


def test_less_confident_conclusions_are_challenged_first():
    rubric = [
        Judgement("sure", 5.0, 5.0, "high"),
        Judgement("unsure", 5.0, 5.0, "low"),
    ]
    decided = {d.key: d for d in calibrate(rubric, level="medium")}
    assert decided["unsure"].final_score < decided["sure"].final_score
