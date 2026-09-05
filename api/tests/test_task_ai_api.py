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

    task_state = "ready"

    def get_task(self, task_id):
        del task_id
        return {
            "id": "engine-task-1", "gen_status": self.task_state, "gen_error": "модель не ответила",
            "total_points": 10,
            "data": {
                "title": "Кейс по оттоку", "statement_md": "Посчитайте отток.",
                "context_md": "Вы аналитик.", "deliverables": ["отчёт"],
                "learning_objectives": ["считать отток"], "reference_solution_md": "эталон",
                "criteria": [{"key": "metrics", "title": "Метрики", "max_points": 6}],
            },
        }

    def generate_task(self, idea):
        del idea
        FakeEngine.calls.append("generate")
        return {"id": "engine-task-1", "gen_status": "generating"}

    def import_task(self, payload):
        FakeEngine.calls.append("import")
        FakeEngine.last_payload = payload
        return {"id": "engine-task-1"}

    last_samples = 1

    def start_validation(self, task_id, *, persona_type, max_rounds=1, samples=1):
        del task_id, max_rounds
        FakeEngine.calls.append(f"validate:{persona_type}")
        FakeEngine.last_samples = samples
        return {"id": "engine-run-1", "status": "running", "progress": "решатели работают"}

    last_existing: list = []

    def assist_criterion(
        self, *, title="", max_points, student_hint="", description="", task_context=None, existing=None
    ):
        del student_hint, description, task_context
        FakeEngine.calls.append("assist:criterion")
        FakeEngine.last_existing = list(existing or [])
        return {
            "key": "c1", "title": title or "Придуманный критерий", "max_points": max_points,
            "student_hint": "что оценивается", "description": "проверяемый признак",
            "check_kind": "subjective", "evidence_hint": "куда смотреть",
            "expected_signals": ["есть формула", "есть вывод"],
            "rubric_levels": [
                {"points": 0, "label": "Не выполнено", "descriptor": "нет"},
                {"points": max_points, "label": "Полно", "descriptor": "есть"},
            ],
        }

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
    FakeEngine.task_state = "ready"
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


def _run(client, assignment_id, persona_type="student", **body):  # noqa: D103
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


# --- черновик из идеи ------------------------------------------------------


def test_draft_from_idea_answers_immediately(methodist, engine):
    """Сборка идёт минуты — ручка обязана вернуть номер задачи, а не ждать её."""

    response = methodist.post(
        "/api/methodist/assignments/draft-from-idea",
        json={"idea": "Кейс про падение ROMI за год", "track": "Аналитика данных"},
    )
    assert response.status_code == 202, response.text
    assert response.json()["job_id"] == "engine-task-1"
    assert response.json()["status"] == "generating"


def test_draft_status_reports_while_generating(methodist, engine):
    engine.task_state = "generating"
    body = methodist.get("/api/methodist/assignments/draft-from-idea/engine-task-1").json()
    assert body == {"status": "generating"}


def test_ready_draft_comes_back_as_a_preview(methodist, engine):
    body = methodist.get(
        "/api/methodist/assignments/draft-from-idea/engine-task-1?track=Аналитика&total_points=10"
    ).json()
    assert body["status"] == "ready"
    draft = body["draft"]
    assert draft["title"] == "Кейс по оттоку"
    assert draft["criteria"][0]["max_score"] == 6
    assert draft["authoring"]["topic"] == "Аналитика"
    assert len(methodist.get("/api/methodist/assignments").json()) == 5, "предпросмотр ничего не создаёт"


def test_a_failed_generation_is_reported_not_swallowed(methodist, engine):
    engine.task_state = "generation_failed"
    body = methodist.get("/api/methodist/assignments/draft-from-idea/engine-task-1").json()
    assert body["status"] == "failed" and body["error"]


# --- «оба», сэмплы и детализация критерия -----------------------------------


def test_both_is_a_valid_run_type(methodist, draft, engine):
    response = _run(methodist, draft, "both")
    assert response.status_code == 202, response.text
    assert response.json()["persona_type"] == "both"
    assert "validate:both" in engine.calls


def test_samples_reach_the_engine(methodist, draft, engine):
    response = _run(methodist, draft, "reviewer", samples=3)
    assert response.status_code == 202, response.text
    assert response.json()["samples"] == 3
    assert engine.last_samples == 3, "число повторов должно доехать до движка"


def test_one_sample_by_default(methodist, draft, engine):
    assert _run(methodist, draft, "reviewer").json()["samples"] == 1


def test_too_many_samples_are_refused(methodist, draft, engine):
    assert _run(methodist, draft, "reviewer", samples=99).status_code == 422


def test_criterion_assist_returns_signals_and_levels(methodist, engine):
    response = methodist.post(
        "/api/methodist/ai-criterion",
        json={"title": "Тесты на фикстурах", "max_score": 3, "context": {"title": "Кейс"}},
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["max_score"] == 3
    assert out["expected_signals"] and out["levels"]


def test_criterion_assist_writes_nothing(methodist, draft, engine):
    before = methodist.get("/api/methodist/assignments").json()
    methodist.post("/api/methodist/ai-criterion", json={"title": "Метрики", "max_score": 5})
    assert methodist.get("/api/methodist/assignments").json() == before


def test_rubric_levels_survive_a_save(methodist):
    """Уровни терялись при сохранении — и ревьюеры каждый раз требовали их снова."""

    created = methodist.post(
        "/api/methodist/assignments",
        json={
            "title": "С уровнями",
            "criteria": [
                {
                    "title": "Метрики",
                    "max_score": 4,
                    "description": "Названы метрики с формулой",
                    "expected_signals": ["есть формула"],
                    "levels": [
                        {"points": 0, "label": "Не выполнено", "descriptor": "метрик нет"},
                        {"points": 4, "label": "Полно", "descriptor": "метрики с формулой"},
                    ],
                }
            ],
        },
    )
    assignment_id = created.json()["id"]
    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == assignment_id)
    assert len(row["rubric"][0]["levels"]) == 2
    assert row["rubric"][0]["levels"][1]["descriptor"] == "метрики с формулой"


def test_the_hidden_half_of_a_task_never_reaches_a_student(client, methodist):
    """Эталон и заметки ревьюеру живут в authoring — студенту их видеть нельзя."""

    methodist.post(
        "/api/methodist/assignments",
        json={
            "title": "С эталоном",
            "statement": "Условие",
            "authoring": {"reference_solution": "СЕКРЕТНЫЙ ЭТАЛОН", "reviewer_notes": "калибровка"},
            "criteria": [
                {
                    "title": "Метрики",
                    "max_score": 4,
                    "description": "скрытое описание",
                    "expected_signals": ["скрытый признак"],
                    "levels": [{"points": 0, "label": "Нет", "descriptor": "скрытый уровень"}],
                }
            ],
            "publish": True,
        },
    )
    token = client.post("/api/auth/demo/student").json()["access_token"]
    body = client.get("/api/student/assignments", headers={"Authorization": f"Bearer {token}"}).text
    for secret in ("СЕКРЕТНЫЙ ЭТАЛОН", "калибровка", "скрытое описание", "скрытый признак", "скрытый уровень"):
        assert secret not in body, f"«{secret}» утекло студенту"
    assert "authoring" not in body





def test_reviewer_sees_levels_without_the_reference_solution(methodist, client):
    created = methodist.post(
        "/api/methodist/assignments",
        json={
            "title": "Для ревьюера",
            "authoring": {"reference_solution": "СЕКРЕТНЫЙ ЭТАЛОН"},
            "criteria": [
                {
                    "title": "Метрики",
                    "max_score": 2,
                    "levels": [
                        {"points": 0, "label": "Нет", "descriptor": "метрик нет"},
                        {"points": 2, "label": "Есть", "descriptor": "метрики с формулой"},
                    ],
                }
            ],
            "publish": True,
        },
    )
    assert created.status_code == 201, created.text

    from app.models import Assignment, RubricVersion
    from app.serializers import assignment_data
    from app.db import SessionLocal

    with SessionLocal() as db:
        row = db.get(Assignment, __import__("uuid").UUID(created.json()["id"]))
        rubric = db.get(RubricVersion, row.current_rubric_version_id)
        for_reviewer = assignment_data(row, rubric, full=True)

    assert for_reviewer["rubric"][0]["levels"], "градация ревьюеру нужна"
    assert "authoring" not in for_reviewer
    assert "СЕКРЕТНЫЙ ЭТАЛОН" not in str(for_reviewer)


def test_a_criterion_can_be_asked_for_without_a_title(methodist, engine):
    """Методист добавил критерий и не знает, что писать, — это законный вход."""

    response = methodist.post(
        "/api/methodist/ai-criterion",
        json={"max_score": 4, "context": {"title": "Кейс"}, "existing": ["Метрики"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"], "название приходит от агента"


def test_existing_criteria_are_passed_so_the_agent_does_not_repeat_them(methodist, engine):
    methodist.post(
        "/api/methodist/ai-criterion",
        json={"max_score": 4, "existing": ["Метрики", "Выводы"]},
    )
    assert engine.last_existing == ["Метрики", "Выводы"]


# --- согласие ревьюеров с AI, по каждому заданию ---------------------------


def test_the_bank_shows_how_often_reviewers_agree_with_the_ai(methodist):
    """Низкая доля — это не про плохой AI, а про критерии, по которым не сходятся."""

    rows = methodist.get("/api/methodist/assignments").json()
    scored = [r for r in rows if r["agreement"]["decided"]]
    assert scored, "в демо-курсе есть проверенные работы — статистика должна быть"
    for row in scored:
        stat = row["agreement"]
        assert 0 <= stat["accepted"] <= stat["decided"]
        if stat["rate"] is not None:
            assert 0 <= stat["rate"] <= 100


def test_a_fresh_task_reports_no_agreement_instead_of_a_hundred_percent(methodist):
    """Одно принятое решение — это «100%». Показать его рядом с сотней настоящих
    значит соврать, поэтому до порога доля не считается вовсе."""

    created = methodist.post(
        "/api/methodist/assignments",
        json={"title": "Свежее", "criteria": [{"title": "Метрики", "max_score": 4}]},
    ).json()["id"]
    row = next(r for r in methodist.get("/api/methodist/assignments").json() if r["id"] == created)
    assert row["agreement"] == {"decided": 0, "accepted": 0, "rate": None}
