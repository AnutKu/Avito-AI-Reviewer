"""AI-инструменты банка заданий через API, с подставным движком.

Сеть не нужна: `TaskCreaterClient` подменяется фейком, который отвечает в том же
контракте, что и настоящий task-creater. Так проверяется именно наш код —
снимок, фоновой прогон, сборка рекомендаций и три решения по каждой из них.
"""

import pytest

from app.services import task_ai

RESULT = {
    "converged": False,
    "summary": "Рубрика требует уточнения.",
    "metrics": {"cost_rub": 1.2, "total_tokens": 900},
    "open_findings": [
        {
            "id": "F1",
            "criterion_key": None,
            "kind": "unfair_hidden",
            "severity": "medium",
            "target": "brief",
            "explanation": "Из условия не следует, что нужен расчёт в деньгах.",
            "fix_suggestion": "Добавьте требование оценить эффект в рублях.",
            "evidence": "Двое решателей денег не посчитали.",
        }
    ],
    "proposed_edits": [],
    "rounds": [
        {
            "round_no": 1,
            "solutions": [
                {"persona": "diligent_strong", "approach_notes": "по пунктам", "exploited_ambiguities": []},
                {"persona": "minimalist_weak", "approach_notes": "минимум", "exploited_ambiguities": ["деньги?"]},
            ],
            "gradings": [],
            "score_matrix": {},
        }
    ],
}


class FakeEngine:
    """Движок в контракте task-creater. Считает вызовы — их проверяют тесты."""

    calls: list[str] = []
    result = RESULT
    run_status = "succeeded"

    def __init__(self, *args, **kwargs):
        del args, kwargs

    def import_task(self, payload):
        FakeEngine.calls.append("import")
        FakeEngine.last_payload = payload
        return {"id": "engine-task-1"}

    def start_validation(self, task_id, *, persona_type, max_rounds=1):
        del task_id, max_rounds
        FakeEngine.calls.append(f"validate:{persona_type}")
        return {"id": "engine-run-1", "status": "running", "progress": "решатели работают"}

    def get_run(self, run_id):
        del run_id
        return {"id": "engine-run-1", "status": self.run_status, "result": self.result, "error": "движок упал"}

    def assist_field(self, *, field, mode, current="", instruction="", context=None):
        del context
        FakeEngine.calls.append(f"assist:{mode}")
        return {"field": field, "proposed": f"{current}\nУточнение: {instruction}".strip(), "note": "ок"}


@pytest.fixture
def engine(monkeypatch):
    FakeEngine.calls = []
    FakeEngine.result = RESULT
    FakeEngine.run_status = "succeeded"
    monkeypatch.setattr(task_ai, "TaskCreaterClient", FakeEngine)
    monkeypatch.setattr(task_ai.settings, "ai_task_run_poll_seconds", 0)
    return FakeEngine


@pytest.fixture
def draft(methodist):
    """Черновик с одним критерием — минимум, с которым можно запускать прогон."""

    created = methodist.post(
        "/api/methodist/assignments",
        json={
            "title": "Кейс по оттоку",
            "statement": "Посчитайте отток и предложите меры.",
            "authoring": {"topic": "Аналитика данных", "context": "Вы аналитик вертикали."},
            "criteria": [{"title": "Метрики", "max_score": 6, "student_hint": "как измеряем"}],
            "pass_score": 4,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _run(client, assignment_id, persona_type="student", **body):
    return client.post(
        f"/api/methodist/assignments/{assignment_id}/ai-runs",
        json={"persona_type": persona_type, **body},
    )


# --- блоки задания ---------------------------------------------------------


def test_authoring_blocks_survive_a_round_trip(methodist, draft):
    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert row["authoring"]["topic"] == "Аналитика данных"
    assert row["revision"] == 1


def test_hidden_criterion_fields_are_stored(methodist):
    created = methodist.post(
        "/api/methodist/assignments",
        json={
            "title": "С скрытой рубрикой",
            "criteria": [
                {
                    "title": "Метрики",
                    "max_score": 5,
                    "description": "Названы 2+ метрики с формулой",
                    "expected_signals": ["есть формула"],
                }
            ],
        },
    )
    assert created.status_code == 201, created.text
    row = next(
        a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == created.json()["id"]
    )
    assert row["rubric"][0]["description"].startswith("Названы")
    assert row["rubric"][0]["expected_signals"] == ["есть формула"]


# --- помощь по блоку -------------------------------------------------------


def test_ai_fill_returns_a_proposal_and_writes_nothing(methodist, draft, engine):
    before = methodist.get("/api/methodist/assignments").json()
    response = methodist.post(
        "/api/methodist/ai-fill",
        json={"field": "statement", "mode": "improve", "current": "Посчитайте отток."},
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposed"]
    after = methodist.get("/api/methodist/assignments").json()
    assert before == after, "предложение не попадает в задание до подтверждения человеком"


def test_ai_fill_is_methodist_only(client):
    token = client.post("/api/auth/demo/student").json()["access_token"]
    response = client.post(
        "/api/methodist/ai-fill",
        json={"field": "statement"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_ai_fill_works_before_the_task_exists(methodist, engine):
    """Помощник нужен на пустом черновике — до того, как задание сохранено."""

    response = methodist.post(
        "/api/methodist/ai-fill",
        json={"field": "statement", "mode": "fill", "context": {"title": "Кейс по оттоку"}},
    )
    assert response.status_code == 200, response.text
    assert response.json()["proposed"]


# --- прогон ----------------------------------------------------------------


def test_a_run_checks_one_persona_type(methodist, draft, engine):
    response = _run(methodist, draft, "student")
    assert response.status_code == 202, response.text
    assert response.json()["persona_type"] == "student"
    assert "validate:student" in engine.calls
    assert not [c for c in engine.calls if c.startswith("validate:reviewer")]


def test_a_run_remembers_the_revision_it_checked(methodist, draft, engine):
    run_id = _run(methodist, draft, "student").json()["id"]
    methodist.patch(f"/api/methodist/assignments/{draft}", json={"title": "Кейс по оттоку v2"})
    detail = methodist.get(f"/api/methodist/ai-runs/{run_id}").json()
    assert detail["revision"] == 1
    assert detail["assignment_revision"] == 2
    assert detail["stale"] is True, "после правки разбор обязан честно сказать, что он про старую версию"


def test_a_run_builds_recommendations_nobody_applied_yet(methodist, draft, engine):
    run_id = _run(methodist, draft, "student").json()["id"]
    detail = methodist.get(f"/api/methodist/ai-runs/{run_id}").json()
    assert detail["status"] == "completed"
    assert detail["summary"]["counts"]["important"] == 1
    assert len(detail["recommendations"]) == 1
    assert detail["recommendations"][0]["status"] == "new"
    statement = next(
        a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft
    )["statement"]
    assert statement == "Посчитайте отток и предложите меры.", "прогон не правит задание сам"


def test_a_brief_recommendation_gets_a_ready_text(methodist, draft, engine):
    run_id = _run(methodist, draft, "student").json()["id"]
    row = methodist.get(f"/api/methodist/ai-runs/{run_id}").json()["recommendations"][0]
    assert row["proposed_value"], "«Применить» должно класть в поле готовый текст"
    assert row["original_value"] == "Посчитайте отток и предложите меры."


def test_double_click_creates_one_run(methodist, draft, engine):
    first = _run(methodist, draft, "student", idempotency_key="click-1")
    second = _run(methodist, draft, "student", idempotency_key="click-1")
    assert first.json()["id"] == second.json()["id"]
    assert len(methodist.get(f"/api/methodist/assignments/{draft}/ai-runs").json()) == 1


def test_a_second_type_runs_after_the_first(methodist, draft, engine):
    _run(methodist, draft, "student", idempotency_key="a")
    second = _run(methodist, draft, "reviewer", idempotency_key="b")
    assert second.status_code == 202
    types = [row["persona_type"] for row in methodist.get(f"/api/methodist/assignments/{draft}/ai-runs").json()]
    assert sorted(types) == ["reviewer", "student"]


def test_a_run_needs_criteria(methodist, engine):
    created = methodist.post(
        "/api/methodist/assignments", json={"title": "Пустое", "criteria": [{"title": "x", "max_score": 1}]}
    ).json()["id"]
    methodist.post(
        f"/api/methodist/assignments/{created}/rubrics", json={"criteria": [], "pass_score": 0}
    )
    assert _run(methodist, created, "reviewer").status_code == 422


def test_an_unknown_persona_type_is_refused(methodist, draft, engine):
    assert _run(methodist, draft, "teacher").status_code == 422


def test_a_failed_engine_leaves_the_draft_alone(methodist, draft, engine):
    engine.run_status = "failed"
    run_id = _run(methodist, draft, "student").json()["id"]
    detail = methodist.get(f"/api/methodist/ai-runs/{run_id}").json()
    assert detail["status"] == "failed" and detail["error"]
    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert row["statement"] == "Посчитайте отток и предложите меры."


def test_the_bank_shows_the_last_run(methodist, draft, engine):
    _run(methodist, draft, "student")
    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert row["last_run"]["persona_type"] == "student"
    assert row["last_run"]["status"] == "completed"


# --- решения по рекомендациям ---------------------------------------------


def _first_recommendation(client, draft_id, persona_type="student"):
    run_id = _run(client, draft_id, persona_type).json()["id"]
    return client.get(f"/api/methodist/ai-runs/{run_id}").json()["recommendations"][0]


def test_apply_writes_the_proposal_into_the_task(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    response = methodist.post(f"/api/methodist/ai-recommendations/{row['id']}/apply", json={})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "applied"
    updated = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert updated["statement"] == row["proposed_value"]
    assert updated["revision"] == 2, "правка задания версионируется, как любая другая"


def test_edit_keeps_both_the_agents_wording_and_the_humans(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    response = methodist.post(
        f"/api/methodist/ai-recommendations/{row['id']}/edit", json={"value": "Мой текст условия"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "edited" and body["final_value"] == "Мой текст условия"
    assert body["proposed_value"] == row["proposed_value"]
    updated = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert updated["statement"] == "Мой текст условия"


def test_reject_changes_nothing_but_stays_visible(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    response = methodist.post(
        f"/api/methodist/ai-recommendations/{row['id']}/reject", json={"reason": "у нас так принято"}
    )
    assert response.json()["status"] == "rejected"
    updated = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert updated["statement"] == "Посчитайте отток и предложите меры."
    again = methodist.get(f"/api/methodist/ai-runs/{row['run_id']}").json()
    assert again["recommendations"][0]["rejection_reason"] == "у нас так принято"


def test_a_decision_is_taken_once(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    methodist.post(f"/api/methodist/ai-recommendations/{row['id']}/reject", json={})
    second = methodist.post(f"/api/methodist/ai-recommendations/{row['id']}/apply", json={})
    assert second.status_code == 409


def test_a_stale_recommendation_refuses_to_overwrite_a_changed_task(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    methodist.patch(f"/api/methodist/assignments/{draft}", json={"statement": "правка из другой вкладки"})
    response = methodist.post(
        f"/api/methodist/ai-recommendations/{row['id']}/apply", json={"expected_revision": 1}
    )
    assert response.status_code == 409
    updated = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == draft)
    assert updated["statement"] == "правка из другой вкладки"


def test_applying_does_not_start_another_run(methodist, draft, engine):
    row = _first_recommendation(methodist, draft)
    engine.calls = []
    methodist.post(f"/api/methodist/ai-recommendations/{row['id']}/apply", json={})
    assert engine.calls == [], "повторный прогон — только явным действием человека"
