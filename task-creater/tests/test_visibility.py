"""Разделение видимости: студент не должен видеть скрытую рубрику и эталон."""

from __future__ import annotations

from app.render import public_criteria, reviewer_md, student_brief_md, student_dict
from app.schemas import Criterion, RubricLevel, TaskDraftData

TASK = TaskDraftData(
    title="Кейс по монетизации",
    summary="Разобрать кейс и предложить план.",
    context_md="Вы — аналитик монетизации. Take-rate ниже конкурентов.",
    statement_md="Можем ли улучшить take-rate?",
    deliverables=["Валидация проблемы", "Гипотезы", "Метрики"],
    submission_format="Документ PDF/DOCX.",
    public_rubric_note="Максимум 10 баллов по этапам.",
    learning_objectives=["Работать с юнит-экономикой"],
    criteria=[
        Criterion(
            key="problem-validation",
            title="Валидация проблемы",
            student_hint="Как убедиться, что проблема реальна",
            description="Студент проверяет take-rate по сегментам и подтверждает разрыв данными.",
            check_kind="subjective",
            evidence_hint="Раздел про валидацию",
            expected_signals=["Сравнение take-rate по сегментам", "Ссылка на бенчмарк конкурентов"],
            rubric_levels=[
                RubricLevel(points=0, label="нет", descriptor="take-rate по сегментам не считался"),
                RubricLevel(points=1, label="слабо", descriptor="счёт есть, сравнения с бенчмарком нет"),
                RubricLevel(points=2, label="средне", descriptor="разрыв подтверждён данными"),
                RubricLevel(points=3, label="хорошо", descriptor="разрыв подтверждён и локализован по сегменту"),
                RubricLevel(points=4, label="полно", descriptor="разрыв подтверждён, локализован и оценён в деньгах"),
            ],
            max_points=4,
        ),
        Criterion(
            key="hypotheses",
            title="Гипотезы",
            student_hint="Полнота и приоритизация гипотез",
            description="6–8 приоритизированных гипотез про монетизацию.",
            check_kind="subjective",
            evidence_hint="Список гипотез",
            expected_signals=["Гипотезы про продвижение и тарифы", "Явная приоритизация"],
            max_points=6,
        ),
    ],
    reference_solution_md="СЕКРЕТ: эталонный разбор кейса.",
    common_mistakes=["СЕКРЕТ: типичная ошибка"],
    reviewer_notes="СЕКРЕТ: калибровочные заметки",
)

_HIDDEN_MARKERS = [
    "СЕКРЕТ",
    "Сравнение take-rate по сегментам",
    "Ссылка на бенчмарк",
    "разрыв подтверждён данными",
    "6–8 приоритизированных гипотез",
    "Раздел про валидацию",
]


def test_student_brief_hides_rubric_internals():
    md = student_brief_md(TASK)
    assert "Валидация проблемы" in md  # имя критерия — видно
    assert "0–4" in md and "0–6" in md  # веса — видно
    assert "Как убедиться, что проблема реальна" in md  # student_hint — видно
    for marker in _HIDDEN_MARKERS:
        assert marker not in md, f"скрытое просочилось в бриф студента: {marker!r}"


def test_reviewer_md_contains_everything():
    md = reviewer_md(TASK)
    for marker in _HIDDEN_MARKERS + ["эталонный разбор", "калибровочные заметки"]:
        assert marker in md


def test_public_criteria_projection_drops_hidden_fields():
    for row in public_criteria(TASK.criteria):
        assert set(row) == {"key", "title", "max_points", "student_hint", "check_kind"}


def test_student_dict_has_no_hidden_keys():
    d = student_dict(TASK)
    assert "reference_solution_md" not in d
    assert "common_mistakes" not in d
    assert "reviewer_notes" not in d
    assert d["criteria"][0].get("description") is None
    assert d["criteria"][0].get("expected_signals") is None
