"""Разбор результата AI-прогона: что становится рекомендацией и что — нет.

Чистые функции, БД и движок не нужны. Проверяется ровно то, ради чего фича и
писалась: один прогон отвечает на один вопрос, ни одна правка не применяется
сама, а результат навсегда привязан к той ревизии, которую проверяли.
"""

from app.services.task_ai import (
    criteria_after,
    draft_from_engine_task,
    engine_payload,
    from_engine_criterion,
    persona_cards,
    recommendations_from_result,
    run_summary,
    sampling_spread,
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


# --- режим «и то, и другое» ------------------------------------------------


def test_both_covers_the_brief_and_the_criteria_at_once():
    rows = recommendations_from_result(RESULT, "both", criteria=CRITERIA)
    targets = {row["target_type"] for row in rows}
    assert targets == {"criterion", "task_field"}, "разбираются оба слоя"


def test_both_still_does_not_repeat_a_covered_finding():
    rows = recommendations_from_result(RESULT, "both", criteria=CRITERIA)
    assert len(rows) == 2, "F1 закрыта правкой E1, отдельной рекомендацией не едет"


def test_both_shows_one_card_per_persona():
    """Иначе одна и та же персона выглядела бы двумя разными участниками."""

    cards = persona_cards(RESULT, "both")
    assert [c["key"] for c in cards] == ["diligent_strong", "minimalist_weak"]
    assert cards[0]["understood"] is True and cards[0]["total_points"] == 9


def test_each_run_type_shows_only_what_it_checked():
    student = persona_cards(RESULT, "student")[0]
    reviewer = persona_cards(RESULT, "reviewer")[0]
    assert "total_points" not in student and "understood" in student
    assert "understood" not in reviewer and "total_points" in reviewer


def test_both_summary_speaks_about_both_layers():
    rows = recommendations_from_result(RESULT, "both", criteria=CRITERIA)
    summary = run_summary(RESULT, "both", rows)
    assert "Постановку поняли" in summary["good"] and "разбросом" in summary["good"]


# --- разброс при повторной оценке ------------------------------------------

SAMPLED = {
    **RESULT,
    "rounds": [
        {
            **RESULT["rounds"][0],
            "score_samples": {
                "metrics": {"diligent_strong": [6, 6, 6], "minimalist_weak": [2, 4, 3]},
                "hypotheses": {"diligent_strong": [4, 4, 4], "minimalist_weak": [3.5, 3.5, 3.5]},
            },
        }
    ],
}


def test_sampling_spread_finds_the_unstable_criterion():
    rows = sampling_spread(SAMPLED)
    assert rows[0]["criterion_key"] == "metrics"
    assert rows[0]["worst"] == 2 and rows[0]["samples"] == 3
    assert rows[0]["stable"] is False


def test_a_criterion_scored_the_same_every_time_is_stable():
    rows = sampling_spread(SAMPLED)
    steady = next(r for r in rows if r["criterion_key"] == "hypotheses")
    assert steady["worst"] == 0 and steady["stable"] is True


def test_a_single_sample_says_nothing_about_stochasticity():
    """Один замер разброса не даёт — показывать «стабильно» было бы враньём."""

    single = {"rounds": [{"score_samples": {"metrics": {"diligent_strong": [6]}}}]}
    assert sampling_spread(single) == []


def test_summary_counts_unstable_criteria():
    summary = run_summary(SAMPLED, "reviewer", [])
    assert summary["unstable"] == 1
    assert summary["sampling"][0]["criterion_key"] == "metrics"


def test_persona_card_averages_repeated_gradings():
    doubled = {
        "rounds": [
            {
                "solutions": [],
                "gradings": [
                    {"persona": "p", "total_points": 4, "scores": [], "overall_comment": "раз"},
                    {"persona": "p", "total_points": 6, "scores": [], "overall_comment": "два"},
                ],
            }
        ]
    }
    card = persona_cards(doubled, "reviewer")[0]
    assert card["total_points"] == 5 and card["samples"] == 2


# --- эталон пишет лектор ----------------------------------------------------


def test_the_reference_solution_is_never_generated():
    """Эталон — это ответ, с которым сверяют студентов. Его пишет человек."""

    task = {
        "total_points": 10,
        "data": {
            "title": "Кейс", "statement_md": "условие", "context_md": "контекст",
            "reference_solution_md": "решение, придуманное моделью",
            "criteria": [{"key": "c1", "title": "Крит", "max_points": 10}],
        },
    }
    draft = draft_from_engine_task(task, track="Аналитика")
    assert "reference_solution" not in draft["authoring"]
    assert "модель" not in str(draft["authoring"])


# --- что делают агенты, по шагам -------------------------------------------

from app.services.task_ai import run_stages  # noqa: E402


def states(rows):
    return {row["key"]: row["state"] for row in rows}


def test_stages_mark_where_the_run_is_now():
    # Двое из четырёх — решатели ещё работают.
    rows = run_stages(
        status="running", progress="раунд 1/1: решают профили (2)", persona_type="reviewer"
    )
    assert states(rows) == {
        "snapshot": "done", "solving": "active",
        "grading": "pending", "critique": "pending", "report": "pending",
    }


def test_grading_stage_lights_up_next():
    rows = run_stages(
        status="running", progress="раунд 1/1: предварительное ревью решений (2)", persona_type="both"
    )
    assert states(rows)["solving"] == "done"
    assert states(rows)["grading"] == "active"


def test_a_completed_run_shows_every_stage_done():
    rows = run_stages(status="completed", progress="готово", persona_type="reviewer")
    assert set(states(rows).values()) == {"done"}


def test_a_failed_run_marks_the_stage_that_broke():
    rows = run_stages(
        status="failed", progress="раунд 1/1: предварительное ревью решений (2)", persona_type="reviewer"
    )
    assert states(rows)["grading"] == "failed"
    assert states(rows)["solving"] == "done"


def test_a_student_run_does_not_advertise_a_grading_step():
    """Оценки там тоже считаются, но методисту этот шаг ничего не объясняет."""

    keys = [row["key"] for row in run_stages(status="running", progress="", persona_type="student")]
    assert "grading" not in keys and "solving" in keys


def test_repeats_are_named_where_they_happen():
    rows = run_stages(status="running", progress="", persona_type="reviewer", samples=5)
    grading = next(row for row in rows if row["key"] == "grading")
    assert "5 повтор" in grading["note"]
    once = run_stages(status="running", progress="", persona_type="reviewer", samples=1)
    assert "повтор" not in next(r for r in once if r["key"] == "grading")["note"]


def test_unknown_wording_does_not_break_the_pipeline():
    """Движок может переформулировать прогресс — картина обязана пережить это."""

    rows = run_stages(status="running", progress="что-то новое", persona_type="reviewer")
    assert [row["state"] for row in rows] == ["active", "pending", "pending", "pending", "pending"]


def test_every_stage_explains_itself():
    for row in run_stages(status="running", progress="", persona_type="both"):
        assert row["title"] and row["note"], "шаг без объяснения бесполезен"


def test_preparation_already_means_the_students_are_working():
    """Между запуском решателей и первым решением проходит минута с лишним —
    держать экран на «снимке» всё это время значит врать."""

    rows = run_stages(status="running", progress="раунд 1/1: подготовка", persona_type="reviewer")
    assert states(rows)["solving"] == "active"
    assert states(rows)["snapshot"] == "done"


def test_a_long_stage_shows_how_much_is_done():
    rows = run_stages(
        status="running", progress="раунд 1/1: решают профили (2)", persona_type="reviewer", personas=4
    )
    solving = next(row for row in rows if row["key"] == "solving")
    assert "Готово: 2 из 4" in solving["note"]


def test_grading_counts_include_the_repeats():
    rows = run_stages(
        status="running", progress="раунд 1/1: предварительное ревью решений (5)",
        persona_type="reviewer", personas=4, samples=3,
    )
    grading = next(row for row in rows if row["key"] == "grading")
    assert "Готово: 5 из 12" in grading["note"]


def test_a_finished_stage_does_not_carry_a_counter():
    rows = run_stages(status="completed", progress="готово", persona_type="reviewer")
    assert not [row for row in rows if "Готово:" in row["note"]]


def test_a_finished_counter_moves_the_run_on():
    """20 из 20 и спиннер на том же шаге — это уже неправда: считает следующий."""

    rows = run_stages(
        status="running", progress="раунд 1/1: предварительное ревью решений (20)",
        persona_type="reviewer", personas=4, samples=5,
    )
    assert states(rows)["grading"] == "done"
    assert states(rows)["critique"] == "active"


def test_all_solutions_in_means_grading_started():
    rows = run_stages(
        status="running", progress="раунд 1/1: решают профили (4)", persona_type="reviewer", personas=4
    )
    assert states(rows)["solving"] == "done"
    assert states(rows)["grading"] == "active"


def test_a_partial_counter_keeps_the_stage_active():
    rows = run_stages(
        status="running", progress="раунд 1/1: предварительное ревью решений (7)",
        persona_type="reviewer", personas=4, samples=5,
    )
    assert states(rows)["grading"] == "active"
    assert "Готово: 7 из 20" in next(r for r in rows if r["key"] == "grading")["note"]


def test_the_last_stage_never_advances_past_itself():
    rows = run_stages(
        status="running", progress="раунд 1/1: решают профили (4)", persona_type="student", personas=4
    )
    assert [row["state"] for row in rows][-1] != "done" or states(rows)["report"] == "active"
