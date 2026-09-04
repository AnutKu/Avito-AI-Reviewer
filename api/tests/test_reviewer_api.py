"""Интеграционные тесты рабочего места ревьюера (нужен Postgres — см. conftest)."""


def test_queue_excludes_completed_but_history_includes_it(reviewer):
    queue = reviewer.get("/api/reviewer/queue").json()
    history = reviewer.get("/api/reviewer/history").json()

    assert all(row["status"] != "completed" for row in queue)
    assert any(row["status"] == "completed" for row in history), "история содержит проверенные работы"
    assert len(history) >= len(queue)


def test_history_rows_carry_score_and_current_flag(reviewer):
    history = reviewer.get("/api/reviewer/history").json()
    assert history
    for row in history:
        assert {"student", "assignment", "status", "final_score", "completed_at", "is_current"} <= row.keys()

    done = next(row for row in history if row["status"] == "completed")
    assert done["final_score"] is not None
    assert done["completed_at"] is not None


def test_history_keeps_a_reassigned_away_work(reviewer):
    """Работа, переданная другому ревьюеру, остаётся в истории первого с is_current=False."""

    mine = next(r for r in reviewer.get("/api/reviewer/queue").json() if r["status"] == "assigned")

    md = {"Authorization": f"Bearer {reviewer.post('/api/auth/demo/methodist').json()['access_token']}"}
    reviewers = reviewer.get("/api/methodist/reviewers", headers=md).json()
    other = next(r["id"] for r in reviewers if r["name"] != "Максим Орлов")
    moved = reviewer.patch(
        f"/api/methodist/submissions/{mine['id']}/reviewer",
        json={"reviewer_id": other, "force": True},
        headers=md,
    )
    assert moved.status_code == 200

    history = reviewer.get("/api/reviewer/history").json()
    row = next((r for r in history if r["id"] == mine["id"]), None)
    assert row is not None and row["is_current"] is False
    assert mine["id"] not in [r["id"] for r in reviewer.get("/api/reviewer/queue").json()]
