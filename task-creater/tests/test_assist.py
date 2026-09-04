"""Точечная помощь по блоку и тип персон у прогона.

Помощник не имеет состояния: он обязан вернуть ПРЕДЛОЖЕНИЕ и не тронуть ни одну
запись — вставку делает человек на стороне кабинета. Тип персон должен доезжать
до конфига прогона, иначе кабинет не сможет показать, что именно проверяли.
"""

from __future__ import annotations

IDEA = {"idea": "Отток в подписке: посчитать, найти причины, предложить меры.", "track": "Аналитика данных"}


async def test_assist_fills_an_empty_block(client):
    r = await client.post(
        "/assist/field",
        json={"field": "Условие", "mode": "fill", "context": {"title": "Пул воркеров"}},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["field"] == "Условие"
    assert out["proposed"].strip()


async def test_assist_improve_keeps_the_authors_text(client):
    current = "Посчитайте отток и сделайте выводы."
    r = await client.post(
        "/assist/field",
        json={"field": "Условие", "mode": "improve", "current": current, "instruction": "добавь сроки"},
    )
    assert r.status_code == 200, r.text
    proposed = r.json()["proposed"]
    assert current in proposed, "improve дополняет текст автора, а не выбрасывает его"


async def test_assist_stores_nothing(client):
    before = (await client.get("/tasks")).json()
    await client.post("/assist/field", json={"field": "Условие", "mode": "fill"})
    after = (await client.get("/tasks")).json()
    assert len(before) == len(after), "помощник по блоку не создаёт заданий"


async def test_validation_run_remembers_persona_type(client):
    task = (await client.post("/tasks/generate", json={"idea": IDEA})).json()
    started = await client.post(
        f"/tasks/{task['id']}/validate", json={"max_rounds": 1, "persona_type": "student"}
    )
    assert started.status_code == 202, started.text
    assert started.json()["config"]["persona_type"] == "student"


async def test_persona_type_defaults_to_reviewer(client):
    task = (await client.post("/tasks/generate", json={"idea": IDEA})).json()
    started = await client.post(f"/tasks/{task['id']}/validate", json={"max_rounds": 1})
    assert started.json()["config"]["persona_type"] == "reviewer"
