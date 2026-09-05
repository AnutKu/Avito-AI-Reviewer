"""Каталог реального курса.

Критерии сюда переписаны из условий руками, а рука ошибается: пропущенный балл
или задвоенный ключ дают рубрику, по которой нельзя честно оценить работу.
Здесь проверяется то, что можно проверить машинно, — согласованность каталога
с самим собой и с извлечёнными текстами.

БД и модель не нужны.
"""

import re
from pathlib import Path

import pytest

from app.real_course import HOMEWORK_ROOT, TASKS

DATA = Path(__file__).resolve().parent.parent / "data" / "real_course"
SOURCE = Path(__file__).resolve().parent.parent.parent / HOMEWORK_ROOT

TASK_IDS = [task.slug for task in TASKS]

# Тот же признак заголовка, что и у скрипта извлечения: «Критерии оценивания»
# в одних условиях и «Критерии оценки» в других.
CRITERIA_HEADING = re.compile(r"критери\w*\s+оцен", re.I)


def test_catalogue_is_not_empty_and_covers_several_tracks():
    assert len(TASKS) >= 8
    assert len({task.track for task in TASKS}) >= 3


def test_slugs_are_unique():
    assert len(TASK_IDS) == len(set(TASK_IDS))


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_criteria_are_well_formed(task):
    keys = [item["key"] for item in task.criteria]
    assert keys, f"{task.slug}: рубрика без критериев"
    assert len(keys) == len(set(keys)), f"{task.slug}: повторяющийся ключ критерия"
    for item in task.criteria:
        assert item["title"].strip(), f"{task.slug}: критерий без названия"
        assert item["max_score"] > 0, f"{task.slug}: критерий с нулевым максимумом"


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_levels_do_not_exceed_the_criterion(task):
    """Градация не может обещать больше баллов, чем стоит у критерия."""

    for item in task.criteria:
        levels = item.get("levels")
        if not levels:
            continue
        points = [level["points"] for level in levels]
        assert points == sorted(points), f"{task.slug}/{item['key']}: уровни не по возрастанию"
        assert max(points) == item["max_score"], (
            f"{task.slug}/{item['key']}: верхний уровень {max(points)} "
            f"не совпадает с максимумом {item['max_score']}"
        )
        assert min(points) == 0, f"{task.slug}/{item['key']}: нет уровня «ноль баллов»"
        for level in levels:
            assert level["descriptor"].strip(), f"{task.slug}/{item['key']}: уровень без описания"


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_pass_score_fits_the_scale(task):
    if task.pass_score is None:
        return
    assert 0 < task.pass_score < task.max_score, (
        f"{task.slug}: зачёт {task.pass_score} вне шкалы 0..{task.max_score}"
    )


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_every_task_has_solutions_of_different_levels(task):
    levels = [solution.level for solution in task.solutions]
    assert len(levels) >= 2, f"{task.slug}: меньше двух решений"
    assert set(levels) <= {"weak", "medium", "strong"}, f"{task.slug}: неизвестный уровень"
    assert len(set(levels)) >= 2, f"{task.slug}: все решения одного уровня — сравнивать нечего"


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_source_files_are_in_place(task):
    if not SOURCE.exists():
        pytest.skip("материалы кейсодателя недоступны")
    assert (SOURCE / task.statement_path).exists(), f"{task.slug}: нет файла условия"
    for solution in task.solutions:
        assert (SOURCE / solution.path).exists(), f"{task.slug}: нет файла решения {solution.path}"


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_extracted_texts_are_present_and_substantial(task):
    if not DATA.exists():
        pytest.skip("тексты не извлечены: python -m scripts.extract_homework")
    statement = DATA / task.slug / "statement.md"
    assert statement.exists(), f"{task.slug}: не извлечено условие"
    assert len(statement.read_text("utf-8")) > 400, f"{task.slug}: условие подозрительно короткое"

    for solution in task.solutions:
        name = f"{solution.level}-{Path(solution.path).stem}.md"
        path = DATA / task.slug / "solutions" / name
        assert path.exists(), f"{task.slug}: не извлечено решение {name}"
        assert len(path.read_text("utf-8")) > 400, f"{task.slug}/{name}: пустое решение"


@pytest.mark.parametrize("task", TASKS, ids=TASK_IDS)
def test_criteria_are_not_duplicated_inside_the_statement(task):
    """Шкала живёт в рубрике. Второй её экземпляр внутри условия со временем разойдётся."""

    if not DATA.exists():
        pytest.skip("тексты не извлечены")
    # Ровно тот текст, который загрузчик кладёт в задание: служебная шапка о
    # происхождении файла в условие не идёт и сама содержит слово «критерии».
    body = "\n".join(
        line
        for line in (DATA / task.slug / "statement.md").read_text("utf-8").splitlines()
        if not line.startswith("<!--")
    ).lower()
    assert not CRITERIA_HEADING.search(body), f"{task.slug}: критерии остались в тексте условия"
