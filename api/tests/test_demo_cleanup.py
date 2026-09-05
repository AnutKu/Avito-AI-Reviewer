"""Уборка накликанных при отладке заданий.

Проверяется одно свойство и оно же главное: под удаление не может попасть
задание, по которому кто-то сдавал работу. Всё остальное — вопрос удобства,
а это — вопрос сохранности чужого труда.

БД не нужна: решение принимает чистая функция над списком.
"""

from datetime import UTC, datetime, timedelta

from app.services.demo_cleanup import TaskRow, kept, reason, removable

NOW = datetime(2026, 9, 5, tzinfo=UTC)
CATALOGUE = {"Разведочный анализ данных", "Трекинг экспериментов в MLflow"}


def task(title, *, submissions=0, days_ago=0, published=True, runs=0):
    return TaskRow(
        id=title,
        title=title,
        created_at=NOW - timedelta(days=days_ago),
        published=published,
        submissions=submissions,
        runs=runs,
    )


def test_task_with_submissions_is_never_removed_however_it_is_named():
    junk = task("тест тест 123", submissions=1)
    assert removable([junk], CATALOGUE) == []
    assert kept([junk], CATALOGUE) == [junk]


def test_demo_catalogue_survives_even_while_empty():
    fresh = task("Трекинг экспериментов в MLflow")
    assert removable([fresh], CATALOGUE) == []
    assert reason(fresh, CATALOGUE) == "задание демо-курса"


def test_empty_task_outside_the_catalogue_is_offered_for_removal():
    junk = task("Анализ рынка недвижимости (копия)", runs=2)
    assert removable([junk], CATALOGUE) == [junk]
    assert reason(junk, CATALOGUE) == "нет работ и нет в демо-каталоге"


def test_draft_is_removable_on_the_same_terms_as_published():
    draft = task("Черновик", published=False)
    assert removable([draft], CATALOGUE) == [draft]


def test_list_reads_as_a_history_of_debugging_oldest_first():
    rows = [task("новое", days_ago=1), task("старое", days_ago=30), task("среднее", days_ago=10)]
    assert [row.title for row in removable(rows, CATALOGUE)] == ["старое", "среднее", "новое"]


def test_unknown_creation_date_does_not_break_the_order():
    undated = TaskRow(id="x", title="без даты", created_at=None, published=True, submissions=0, runs=0)
    rows = [undated, task("с датой", days_ago=3)]
    assert [row.title for row in removable(rows, CATALOGUE)] == ["с датой", "без даты"]


def test_title_is_matched_without_stray_spaces():
    assert reason(task("  Разведочный анализ данных  "), CATALOGUE) == "задание демо-курса"
