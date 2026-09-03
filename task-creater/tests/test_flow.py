"""Сквозной сценарий через API в оффлайн-режиме LLM."""

from __future__ import annotations

import asyncio

import pytest

IDEA = {
    "idea": "Пул воркеров на Go: очередь задач, graceful shutdown, лимит на конкурентность.",
    "track": "Backend / Go",
    "audience_level": "intermediate",
    "total_points": 10,
    "constraints": "Обязательны тесты. Штраф за просрочку -1/сутки, максимум -3.",
}


async def _wait_run(client, run_id: str, tries: int = 80) -> dict:
    for _ in range(tries):
        run = (await client.get(f"/validation-runs/{run_id}")).json()
        if run["status"] in ("succeeded", "failed"):
            return run
        await asyncio.sleep(0.05)
    raise AssertionError("прогон не завершился вовремя")


async def test_personas(client):
    r = await client.get("/personas")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()}
    assert {"diligent_strong", "minimalist_weak", "rule_lawyer", "ambiguity_prober"} <= keys


async def test_generate_validate_apply_export(client):
    # 1. генерация
    r = await client.post("/tasks/generate", json={"idea": IDEA})
    assert r.status_code == 201, r.text
    task = r.json()
    task_id = task["id"]
    root_id = task["root_id"]
    assert task["version"] == 1 and task["source"] == "generated"
    assert task["root_id"] == task_id
    assert abs(task["total_points"] - 10) < 1e-6
    assert len(task["data"]["criteria"]) >= 3

    # 1a. менеджер задач: задача видна в списке со статусом draft, прогонов нет
    lst = (await client.get("/tasks")).json()
    row = next(x for x in lst if x["root_id"] == root_id)
    assert row["status"] == "draft" and row["last_run"] is None
    assert row["criteria_count"] == len(task["data"]["criteria"])
    assert (await client.get(f"/tasks/{root_id}/runs")).json() == []

    # 2. валидация
    r = await client.post(f"/tasks/{task_id}/validate", json={"max_rounds": 2})
    assert r.status_code == 202, r.text
    run_id = r.json()["id"]
    run = await _wait_run(client, run_id)
    assert run["status"] == "succeeded", run.get("error")

    res = run["result"]
    assert res["rounds"], "должен быть хотя бы один раунд"
    assert res["metrics"]["llm_calls"] > 0
    # расхождение оценок между профилями действительно есть
    matrix = res["rounds"][0]["score_matrix"]
    assert any(len(set(row.values())) > 1 for row in matrix.values())
    # критик что-то нашёл и предложил правки
    assert res["proposed_edits"], "ожидались предложенные правки рубрики"
    edit_ids = [e["id"] for e in res["proposed_edits"]]

    # 2a. после успешного прогона задача в статусе needs_review, прогон в истории
    row = next(x for x in (await client.get("/tasks")).json() if x["root_id"] == root_id)
    assert row["status"] == "needs_review"
    assert row["last_run"]["status"] == "succeeded" and row["last_run"]["proposed_edits"] > 0
    runs = (await client.get(f"/tasks/{root_id}/runs")).json()
    assert len(runs) == 1 and runs[0]["id"] == run_id
    only_review = (await client.get("/tasks", params={"status": "needs_review"})).json()
    assert any(x["root_id"] == root_id for x in only_review)

    # 3. решение человека: принять все правки
    decisions = {
        "decisions": [{"edit_id": eid, "accept": True} for eid in edit_ids],
        "author": "test",
    }
    r = await client.post(f"/validation-runs/{run_id}/decisions", json=decisions)
    assert r.status_code == 200, r.text
    revised = r.json()
    assert revised["version"] == 2 and revised["source"] == "revised"
    assert revised["changelog"][-1]["kind"] == "criteria_revision"
    # правки применились: где-то в описаниях появился маркер уточнения
    assert any("[уточнено]" in c["description"] for c in revised["data"]["criteria"])

    # 3a. статус задачи стал revised, в списке — последняя версия
    row = next(x for x in (await client.get("/tasks")).json() if x["root_id"] == root_id)
    assert row["status"] == "revised" and row["version"] == 2 and row["id"] == revised["id"]

    # 4. экспорт: ревьюерский vs студенческий
    r = await client.get(f"/tasks/{revised['id']}/export", params={"format": "markdown"})
    assert r.status_code == 200
    assert "## Критерии оценки" in r.text
    assert "Только для ревьюера" in r.text and "Эталонное решение" in r.text

    r = await client.get(f"/tasks/{revised['id']}/export", params={"format": "markdown", "view": "student"})
    assert "Только для ревьюера" not in r.text and "Эталонное решение" not in r.text

    r = await client.get(f"/tasks/{revised['id']}/export", params={"format": "json", "view": "student"})
    sj = r.json()
    assert "reference_solution_md" not in sj and "common_mistakes" not in sj
    assert sj["criteria"][0].get("description") is None

    r = await client.get(f"/tasks/{revised['id']}/export", params={"format": "json"})
    assert r.json()["total_points"] == pytest.approx(10, abs=0.5)
    assert "reference_solution_md" in r.json()

    # версий стало две
    versions = (await client.get(f"/tasks/{task_id}/versions")).json()
    assert [v["version"] for v in versions] == [1, 2]


async def test_partial_decisions_reject_some(client):
    task = (await client.post("/tasks/generate", json={"idea": IDEA})).json()
    run_id = (await client.post(f"/tasks/{task['id']}/validate", json={"max_rounds": 1})).json()["id"]
    run = await _wait_run(client, run_id)
    edits = run["result"]["proposed_edits"]
    assert edits
    # принимаем только первую правку
    decisions = {"decisions": [{"edit_id": edits[0]["id"], "accept": True}]}
    for e in edits[1:]:
        decisions["decisions"].append({"edit_id": e["id"], "accept": False})
    revised = (await client.post(f"/validation-runs/{run_id}/decisions", json=decisions)).json()
    assert revised["version"] == 2
    assert revised["changelog"][-1]["applied_edit_ids"] == [edits[0]["id"]]


async def test_patch_creates_edited_version(client):
    task = (await client.post("/tasks/generate", json={"idea": IDEA})).json()
    r = await client.patch(f"/tasks/{task['id']}", json={"title": "Новый заголовок"})
    assert r.status_code == 200
    v2 = r.json()
    assert v2["version"] == 2 and v2["source"] == "edited"
    assert v2["data"]["title"] == "Новый заголовок"


async def test_validate_unknown_persona_fails_gracefully(client):
    task = (await client.post("/tasks/generate", json={"idea": IDEA})).json()
    r = await client.post(f"/tasks/{task['id']}/validate", json={"personas": ["nope"]})
    assert r.status_code == 202
    run = await _wait_run(client, r.json()["id"])
    assert run["status"] == "failed"
    assert "профил" in run["error"].lower()


async def test_decisions_for_unknown_run_is_404(client):
    r = await client.post("/validation-runs/deadbeef/decisions", json={"decisions": []})
    assert r.status_code == 404


async def test_background_generation_shows_in_queue(client):
    r = await client.post("/tasks/generate", json={"idea": IDEA, "background": True})
    assert r.status_code == 202
    tid = r.json()["id"]
    assert r.json()["gen_status"] == "generating"
    # сразу видно в списке со статусом generating
    row = next(x for x in (await client.get("/tasks")).json() if x["id"] == tid)
    assert row["status"] == "generating"
    # фон дозаполняет — ждём ready
    for _ in range(80):
        t = (await client.get(f"/tasks/{tid}")).json()
        if t["gen_status"] == "ready":
            break
        await asyncio.sleep(0.05)
    assert t["gen_status"] == "ready" and len(t["data"]["criteria"]) >= 3
    assert next(x for x in (await client.get("/tasks")).json() if x["id"] == tid)["status"] == "draft"


async def test_import_task_and_grade_solution(client):
    payload = {
        "title": "Импортированное ДЗ по SQL",
        "track": "Аналитика данных",
        "statement_md": "Напишите запрос, считающий DAU по дням за последний месяц.",
        "deliverables": ["SQL-запрос", "краткое пояснение логики"],
        "public_rubric_note": "2 пункта × 0–5 баллов.",
        "criteria": [
            {
                "key": "correctness",
                "title": "Корректность запроса",
                "max_points": 6,
                "student_hint": "запрос считает то, что просили",
                "description": "GROUP BY по дню, DISTINCT user_id, фильтр по дате за 30 дней.",
                "check_kind": "objective",
                "evidence_hint": "тело запроса",
            },
            {
                "key": "clarity",
                "title": "Пояснение",
                "max_points": 4,
                "student_hint": "логика описана словами",
                "description": "есть текстовое пояснение, что и зачем.",
                "check_kind": "subjective",
                "evidence_hint": "текст под запросом",
            },
        ],
        "total_points": 10,
    }
    r = await client.post("/tasks/import", json=payload)
    assert r.status_code == 201, r.text
    task = r.json()
    assert task["source"] == "edited" and abs(task["total_points"] - 10) < 1e-6
    assert task["data"]["criteria"][0]["key"] == "correctness"

    # проверить решение агентом (демо-тестирование)
    r = await client.post(
        f"/tasks/{task['id']}/grade",
        json={
            "solution_md": "SELECT date, COUNT(DISTINCT user_id) FROM events GROUP BY date",
            "persona": "demo",
        },
    )
    assert r.status_code == 200, r.text
    g = r.json()
    assert g["persona"] == "demo"
    assert {s["criterion_key"] for s in g["scores"]} == {"correctness", "clarity"}

    # такую задачу тоже можно прогнать валидацией
    run = await _wait_run(
        client, (await client.post(f"/tasks/{task['id']}/validate", json={"max_rounds": 1})).json()["id"]
    )
    assert run["status"] == "succeeded"
