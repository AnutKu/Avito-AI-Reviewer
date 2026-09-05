"""Согласие оценки модели с разметкой кейсодателя.

Проверяется главное свойство: ничья — это не согласие. Модель, поставившая
слабой и хорошей работе поровну, ничего не различила, и записывать это в её
пользу значило бы отчитаться об успехе там, где его нет.
"""

from app.services.level_agreement import Work, by_task, compare, overall


def work(level, percent, task="Задание"):
    return Work(task=task, level=level, percent=percent)


def test_correct_order_counts_as_agreement():
    result = compare([work("weak", 30), work("medium", 60), work("strong", 90)])
    assert (result.concordant, result.discordant, result.ties) == (3, 0, 0)
    assert result.share == 100.0


def test_reversed_order_counts_against():
    result = compare([work("weak", 90), work("strong", 30)])
    assert (result.concordant, result.discordant) == (0, 1)
    assert result.share == 0.0


def test_equal_scores_are_ties_not_agreement():
    result = compare([work("weak", 70), work("strong", 70)])
    assert (result.concordant, result.discordant, result.ties) == (0, 0, 1)
    assert result.share == 0.0


def test_two_works_of_the_same_level_are_not_compared():
    result = compare([work("weak", 20), work("weak", 80)])
    assert result.compared == 0
    assert result.share is None


def test_unknown_level_is_skipped_rather_than_guessed():
    result = compare([work("strong", 90), work("неизвестно", 10)])
    assert result.compared == 0


def test_tasks_are_compared_separately():
    works = [
        work("weak", 10, "А"), work("strong", 90, "А"),
        work("weak", 90, "Б"), work("strong", 10, "Б"),
    ]
    per_task = by_task(works)
    assert per_task["А"].share == 100.0
    assert per_task["Б"].share == 0.0
    assert overall(works).share == 50.0


def test_nothing_to_compare_gives_no_number_rather_than_zero():
    assert overall([]).share is None
