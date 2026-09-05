"""Сохранённые ответы модели, из которых кабинет поднимается на новой машине.

Файл `data/real_course/ai_results.json` — единственная причина, по которой
развёртывание не требует ключа к модели и получаса прогона. Он же тихо
устаревает: стоит добавить задание в каталог или переименовать критерий, и
восстановленный кабинет окажется наполовину пустым, причём без единой ошибки.
Эти проверки ловят расхождение до того, как оно доедет до чужой машины.
"""

import json
from pathlib import Path

import pytest

from app.real_course import TASKS
from app.real_course_loader import RESULTS, saved_results

pytestmark = pytest.mark.skipif(
    not RESULTS.exists(),
    reason="ответы модели не выгружены: python -m scripts.load_real_course --export",
)

EXPECTED = {solution.path: task for task in TASKS for solution in task.solutions}


def payload():
    return json.loads(Path(RESULTS).read_text("utf-8"))


def test_every_solution_has_a_saved_review():
    missing = sorted(set(EXPECTED) - set(saved_results()))
    assert not missing, "нет сохранённого разбора: " + "; ".join(missing)


def test_saved_reviews_do_not_outlive_the_catalogue():
    """Решение убрали из каталога — его разбор больше не нужен."""

    extra = sorted(set(saved_results()) - set(EXPECTED))
    assert not extra, "разбор есть, а решения в каталоге нет: " + "; ".join(extra)


def test_saved_scores_match_the_current_rubric():
    """Ключи и максимумы критериев должны совпадать с рубрикой.

    Иначе восстановленный разбор ставит баллы по шкале, которой уже нет."""

    for source, record in saved_results().items():
        task = EXPECTED[source]
        rubric = {item["key"]: item["max_score"] for item in task.criteria}
        for item in record["items"]:
            key = item["criterion_key"]
            assert key in rubric, f"{task.slug}: критерия «{key}» нет в рубрике"
            assert item["max_score"] == rubric[key], (
                f"{task.slug}/{key}: сохранён максимум {item['max_score']}, "
                f"в рубрике {rubric[key]}"
            )
            assert 0 <= item["ai_score"] <= rubric[key], (
                f"{task.slug}/{key}: балл {item['ai_score']} вне шкалы"
            )


def test_every_saved_review_is_a_finished_one():
    for source, record in saved_results().items():
        assert record["ai_status"] == "ready", f"{source}: сохранён незаконченный разбор"
        assert record["items"], f"{source}: разбор без оценок по критериям"
        assert record["draft_feedback"].strip(), f"{source}: разбор без обратной связи"


def test_provenance_is_recorded():
    """По файлу должно быть видно, чем и когда он снят."""

    data = payload()
    assert data.get("generated_at")
    assert "--review" in data.get("note", ""), "в файле нет следа, каким прогоном он получен"
    assert {record["model"] for record in data["reviews"]} != {""}


def test_blitz_questions_belong_to_a_saved_review():
    for source, record in saved_results().items():
        blitz = record.get("blitz")
        if blitz is None:
            continue
        assert blitz["questions"], f"{source}: пустой список вопросов"
        for question in blitz["questions"]:
            assert question.get("text", "").strip(), f"{source}: вопрос без текста"
