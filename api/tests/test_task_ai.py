"""Разбор результата AI-прогона: что становится рекомендацией и что — нет.

Чистые функции, БД и движок не нужны. Проверяется ровно то, ради чего фича и
писалась: один прогон отвечает на один вопрос, ни одна правка не применяется
сама, а результат навсегда привязан к той ревизии, которую проверяли.
"""

from app.services.task_ai import (
    criteria_after,
    engine_payload,
    from_engine_criterion,
    persona_cards,
    recommendations_from_result,
    run_summary,
    score_spread,
    to_engine_criterion,
)

CRITERIA = [
    {"key": "hypotheses", "title": "Гипотезы", "max_score": 4, "student_hint": "полнота"},
    {"key": "metrics", "title": "Метрики", "max_score": 6},
]

EDIT = {
    "id": "E1",
    "operation": "modify",
    "criterion_key": "metrics",
    "severity": "high",
    "rationale": "«Хорошо подобраны» — не проверяется.",
    "addresses": ["F1"],
    "before_snapshot": "Метрики хорошо подобраны",
    "proposed_criterion": {
        "key": "metrics",
        "title": "Метрики",
        "max_points": 6,
        "student_hint": "как измеряем результат",
        "description": "Названы 2+ метрики с формулой и обоснованием выбора.",
        "check_kind": "objective",
        "evidence_hint": "раздел «Метрики»",
        "expected_signals": ["есть формула", "есть базовое значение"],
        "rubric_levels": [{"points": 6, "label": "полно", "descriptor": "обе метрики"}],
    },
}

BRIEF_FINDING = {
    "id": "F2",
    "criterion_key": None,
    "kind": "unfair_hidden",
    "severity": "medium",
    "target": "brief",
    "explanation": "Из условия не следует, что нужен расчёт в деньгах.",
    "fix_suggestion": "Добавьте в условие требование оценить эффект в рублях.",
    "evidence": "Двое из трёх решателей денег не посчитали.",
}

RUBRIC_FINDING = {
    "id": "F1",
    "criterion_key": "metrics",
    "kind": "unmeasurable",
    "severity": "high",
    "target": "rubric",
    "explanation": "Критерий субъективен.",
    "fix_suggestion": "Задайте порог.",
    "evidence": "Разброс оценок 4 балла.",
}

RESULT = {
    "proposed_edits": [EDIT],
    "open_findings": [RUBRIC_FINDING, BRIEF_FINDING],
    "converged": False,
    "summary": "Рубрика требует уточнения.",
    "metrics": {"cost_rub": 1.5},
    "rounds": [
        {
            "round_no": 1,
            "solutions": [
                {"persona": "diligent_strong", "approach_notes": "по пунктам", "exploited_ambiguities": []},
                {
                    "persona": "minimalist_weak",
                    "approach_notes": "по минимуму",
                    "exploited_ambiguities": ["непонятно, нужен ли расчёт в деньгах"],
                },
            ],
            "gradings": [
                {
                    "persona": "diligent_strong",
                    "total_points": 9,
                    "overall_comment": "полно",
                    "scores": [{"criterion_key": "metrics", "decidable": True}],
                },
                {
                    "persona": "minimalist_weak",
                    "total_points": 4,
                    "overall_comment": "поверхностно",
                    "scores": [{"criterion_key": "metrics", "decidable": False}],
                },
            ],
            "score_matrix": {
                "hypotheses": {"diligent_strong": 4, "minimalist_weak": 3.5},
                "metrics": {"diligent_strong": 6, "minimalist_weak": 2},
            },
        }
    ],
}


# --- перевод критериев -----------------------------------------------------


def test_engine_criterion_roundtrip_keeps_the_score():
    back = from_engine_criterion(to_engine_criterion(CRITERIA[0]))
    assert back["max_score"] == 4, "балл кабинета не должен потеряться в max_points движка"
    assert back["key"] == "hypotheses"


def test_half_filled_criterion_still_reaches_the_engine():
    """Методист заводит название и вес; движок требует описание — подставляем название."""

    payload = to_engine_criterion({"key": "metrics", "title": "Метрики", "max_score": 6})
    assert payload["description"] == "Метрики"
    assert payload["evidence_hint"]


def test_engine_payload_is_a_snapshot_of_what_is_checked():
    payload = engine_payload(
        title="Кейс по оттоку",
        statement="Условие",
        authoring={"topic": "Аналитика", "context": "Роль аналитика", "reference_solution": "эталон"},
        criteria=CRITERIA,
    )
    assert payload["statement_md"] == "Условие"
    assert payload["track"] == "Аналитика"
    assert payload["reference_solution_md"] == "эталон"
    assert len(payload["criteria"]) == 2


# --- разбор результата -----------------------------------------------------


def test_reviewer_run_proposes_criterion_edits():
    rows = recommendations_from_result(RESULT, "reviewer", criteria=CRITERIA)
    edits = [r for r in rows if r["target_type"] == "criterion"]
    assert len(edits) == 1
    row = edits[0]
    assert row["target_id"] == "metrics"
    assert row["severity"] == "critical", "high у агента — это «критично» для методиста"
    assert "формул" in row["proposed_value"]
    assert row["original_value"] == "Метрики хорошо подобраны"


def test_reviewer_run_does_not_repeat_a_finding_already_covered_by_an_edit():
    rows = recommendations_from_result(RESULT, "reviewer", criteria=CRITERIA)
    assert len(rows) == 1, "находка F1 закрыта правкой E1 — второй раз её показывать незачем"


def test_student_run_is_about_the_brief_only():
    rows = recommendations_from_result(RESULT, "student", criteria=CRITERIA)
    assert len(rows) == 1
    row = rows[0]
    assert row["target_type"] == "task_field" and row["target_field"] == "statement"
    assert row["proposed_value"] == "", "текст замены дописывается отдельным шагом"
    assert row["expected_effect"].startswith("Добавьте")


def test_student_run_never_touches_criteria():
    rows = recommendations_from_result(RESULT, "student", criteria=CRITERIA)
    assert not [r for r in rows if r["payload"].get("operation")]


def test_leaky_hint_is_fixed_on_the_criterion_not_the_statement():
    leaky = {**BRIEF_FINDING, "id": "F3", "kind": "leaky_public", "criterion_key": "metrics"}
    rows = recommendations_from_result(
        {"proposed_edits": [], "open_findings": [leaky]}, "student", criteria=CRITERIA
    )
    assert rows[0]["target_type"] == "criterion"
    assert rows[0]["target_field"] == "student_hint"
    assert rows[0]["target_id"] == "metrics"


def test_recommendations_keep_their_order():
    rows = recommendations_from_result(RESULT, "reviewer", criteria=CRITERIA)
    assert [row["position"] for row in rows] == list(range(len(rows)))


def test_empty_result_yields_no_recommendations():
    assert recommendations_from_result({}, "reviewer", criteria=CRITERIA) == []
    assert recommendations_from_result({}, "student", criteria=CRITERIA) == []


# --- сводка и персоны ------------------------------------------------------


def test_summary_counts_severity_and_stays_explainable():
    rows = recommendations_from_result(RESULT, "reviewer", criteria=CRITERIA)
    summary = run_summary(RESULT, "reviewer", rows)
    assert summary["verdict"] == "attention"
    assert summary["counts"]["critical"] == 1
    assert summary["good"], "«что прошло хорошо» показывается всегда, а не только при успехе"
    assert "балл качества" not in summary["headline"]


def test_clean_run_reads_as_ok():
    clean = {"rounds": RESULT["rounds"], "converged": True, "open_findings": [], "proposed_edits": []}
    summary = run_summary(clean, "reviewer", [])
    assert summary["verdict"] == "ok" and summary["recommendations"] == 0


def test_persona_cards_follow_the_run_type():
    student = persona_cards(RESULT, "student")
    assert [card["understood"] for card in student] == [True, False]
    reviewer = persona_cards(RESULT, "reviewer")
    assert reviewer[1]["undecidable"] == ["metrics"]


def test_persona_cards_are_not_pinned_to_four_profiles():
    one = {"rounds": [{"solutions": [{"persona": "solo", "exploited_ambiguities": []}], "gradings": []}]}
    assert len(persona_cards(one, "student")) == 1


def test_score_spread_puts_the_worst_criterion_first():
    rows = score_spread(RESULT)
    assert rows[0]["criterion_key"] == "metrics" and rows[0]["spread"] == 4


# --- применение правки -----------------------------------------------------


def test_applying_an_edit_replaces_one_criterion_in_place():
    updated = criteria_after(CRITERIA, EDIT, EDIT["proposed_criterion"]["description"])
    assert [c["key"] for c in updated] == ["hypotheses", "metrics"]
    assert updated[1]["description"].startswith("Названы 2+")
    assert updated[1]["max_score"] == 6


def test_human_text_wins_over_the_agents_wording():
    updated = criteria_after(CRITERIA, EDIT, "Мой вариант формулировки")
    assert updated[1]["description"] == "Мой вариант формулировки"


def test_remove_drops_the_criterion():
    updated = criteria_after(CRITERIA, {"operation": "remove", "criterion_key": "metrics"}, "")
    assert [c["key"] for c in updated] == ["hypotheses"]


def test_add_appends_a_new_criterion():
    add = {"operation": "add", "criterion_key": "risks", "proposed_criterion": {
        "key": "risks", "title": "Риски", "max_points": 2, "description": "Названы риски"}}
    updated = criteria_after(CRITERIA, add, "")
    assert [c["key"] for c in updated] == ["hypotheses", "metrics", "risks"]


def test_applying_does_not_mutate_the_original_criteria():
    criteria_after(CRITERIA, EDIT, "прочее")
    assert CRITERIA[1] == {"key": "metrics", "title": "Метрики", "max_score": 6}
