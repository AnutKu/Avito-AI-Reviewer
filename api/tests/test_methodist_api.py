"""Интеграционные тесты распределения на роутере методиста.

Требуют Postgres (см. `conftest.py`). Проверяют контракты, которые дёргает
кабинет: нагрузка ревьюеров, авто-распределение, снятие ревьюера, кап при
ручном переназначении.
"""

from sqlalchemy import select


def _reviewers(methodist) -> list[dict]:
    resp = methodist.get("/api/methodist/reviewers")
    assert resp.status_code == 200
    return resp.json()


def _state(methodist) -> dict:
    resp = methodist.get("/api/methodist/distribution")
    assert resp.status_code == 200
    return resp.json()


def _apply_all_waiting(methodist) -> None:
    waiting = _state(methodist)["waiting"]
    payload = {
        "assignments": [
            {
                "submission_id": row["submission"]["id"],
                "reviewer_id": row["reviewer"]["id"],
                "explanation": row["explanation"],
            }
            for row in waiting
            if row["reviewer"]
        ]
    }
    assert methodist.post("/api/methodist/distribution/apply", json=payload).status_code == 200


def test_reviewer_loads_expose_capacity_and_free_slots(methodist):
    rows = _reviewers(methodist)
    assert rows
    for row in rows:
        assert {"id", "name", "available", "load", "active_count", "capacity", "slots_left"} <= row.keys()
        assert row["slots_left"] == round(row["capacity"] - row["load"], 1)


def test_distribution_state_has_auto_flag_waiting_and_assigned(methodist):
    state = _state(methodist)
    assert set(state) >= {"auto_assign", "reviewers", "waiting", "assigned"}
    assert state["auto_assign"] is False
    assert state["waiting"], "в демо-данных есть работы, ждущие распределения"
    assert all("over_capacity" in row for row in state["waiting"])
    assert any("нагрузка" in row["explanation"].lower() for row in state["waiting"] if row["reviewer"])


def test_enable_auto_assign_distributes_all_waiting_work(methodist):
    resp = methodist.post("/api/methodist/distribution/auto", json={"enabled": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_assign"] is True and body["assigned"] >= 1

    state = _state(methodist)
    assert state["auto_assign"] is True
    assert all(row["reviewer"] is None or row["over_capacity"] for row in state["waiting"])
    assert state["assigned"], "распределённые работы теперь показываются отдельным списком"

    # повторное включение — распределять уже нечего
    again = methodist.post("/api/methodist/distribution/auto", json={"enabled": True}).json()
    assert again["assigned"] == 0


def test_remove_reviewer_auto_reassigns_pending_work(methodist):
    methodist.post("/api/methodist/distribution/auto", json={"enabled": True})
    _apply_all_waiting(methodist)

    victim = next(r for r in _reviewers(methodist) if r["load"] > 0)
    resp = methodist.patch(f"/api/methodist/reviewers/{victim['id']}", json={"is_available": False})
    assert resp.status_code == 200
    assert resp.json()["available"] is False
    assert "reassigned" in resp.json()

    after = {r["id"]: r for r in _reviewers(methodist)}
    # снятый ревьюер больше не держит НЕ начатых работ (in_review не трогаем)
    not_started = [
        row for row in _state(methodist)["assigned"]
        if row["reviewer"]["id"] == victim["id"] and row["status"] == "assigned"
    ]
    assert not_started == []
    assert after[victim["id"]]["available"] is False


def test_remove_reviewer_in_manual_mode_returns_proposals_without_applying(methodist):
    _apply_all_waiting(methodist)
    victim = next(r for r in _reviewers(methodist) if r["load"] > 0)

    resp = methodist.patch(f"/api/methodist/reviewers/{victim['id']}", json={"is_available": False})
    assert resp.status_code == 200
    body = resp.json()
    assert "proposals" in body and "reassigned" not in body
    for row in body["proposals"]:
        if row["reviewer"]:
            assert row["reviewer"]["id"] != victim["id"]

    # ничего не применилось: работы всё ещё числятся за снятым ревьюером
    still = [row for row in _state(methodist)["assigned"] if row["reviewer"]["id"] == victim["id"]]
    assert still, "в ручном режиме перенос ждёт подтверждения методиста"


def test_manual_reassign_respects_capacity_unless_forced(methodist):
    course = methodist.get("/api/methodist/course").json()
    methodist.patch(
        "/api/methodist/course",
        json={"reviewer_capacity": 1, "tone_of_voice": course["tone_of_voice"]},
    )

    waiting = _state(methodist)["waiting"]
    free_reviewer = next(r["reviewer"]["id"] for r in waiting if r["reviewer"])
    subs = [r["submission"]["id"] for r in waiting if r["reviewer"]]
    assert len(subs) >= 2

    assert methodist.patch(
        f"/api/methodist/submissions/{subs[0]}/reviewer", json={"reviewer_id": free_reviewer}
    ).status_code == 200

    blocked = methodist.patch(
        f"/api/methodist/submissions/{subs[1]}/reviewer", json={"reviewer_id": free_reviewer}
    )
    assert blocked.status_code == 409
    assert "лимит" in blocked.json()["detail"].lower()

    forced = methodist.patch(
        f"/api/methodist/submissions/{subs[1]}/reviewer",
        json={"reviewer_id": free_reviewer, "force": True},
    )
    assert forced.status_code == 200


def test_per_task_handoff_to_a_specific_reviewer(methodist):
    _apply_all_waiting(methodist)
    assigned = _state(methodist)["assigned"]
    assert assigned
    row = assigned[0]
    other = next(
        r["id"] for r in _reviewers(methodist)
        if r["id"] != row["reviewer"]["id"] and r["available"]
    )
    resp = methodist.patch(
        f"/api/methodist/submissions/{row['submission']['id']}/reviewer",
        json={"reviewer_id": other},
    )
    assert resp.status_code == 200
    moved = next(
        x for x in _state(methodist)["assigned"] if x["submission"]["id"] == row["submission"]["id"]
    )
    assert moved["reviewer"]["id"] == other


def test_create_edit_and_submit_assignment(methodist):
    course = methodist.get("/api/methodist/courses").json()[0]
    payload = {
        "course_id": course["id"],
        "title": "Новое ДЗ по продуктовой аналитике",
        "statement": "Разберите кейс и предложите метрики.",
        "effort_weight": 1.5,
        "submission_channel": "stepik",
        "criteria": [
            {"title": "Верификация проблемы", "max_score": 4, "student_hint": "покажите данные"},
            {"title": "Метрики", "max_score": 6},
        ],
        "pass_score": 6,
    }
    created = methodist.post("/api/methodist/assignments", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["rubric_version"] == 1 and body["max_score"] == 10

    listed = methodist.get("/api/methodist/assignments").json()
    row = next(a for a in listed if a["id"] == body["id"])
    assert row["course"] == course["title"] and row["effort_weight"] == 1.5
    assert [c["title"] for c in row["rubric"]] == ["Верификация проблемы", "Метрики"]
    assert all(c["key"] for c in row["rubric"]), "ключи критериев проставляются автоматически"

    assert row["published"] is False, "созданное задание — черновик"

    patched = methodist.patch(
        f"/api/methodist/assignments/{body['id']}", json={"title": "ДЗ · переименовано"}
    )
    assert patched.status_code == 200
    again = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == body["id"])
    assert again["title"] == "ДЗ · переименовано"

    from app.db import SessionLocal
    from app.models import Enrollment, Role, User
    from app.security import issue_token

    with SessionLocal() as db:
        student = User(email="crt@demo.local", full_name="Крит Студент", role=Role.STUDENT)
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=course["id"], user_id=student.id))
        db.commit()
        token = issue_token(student)
    auth = {"Authorization": f"Bearer {token}"}

    # черновик студенту не виден и сдать в него нельзя
    visible = methodist.get("/api/student/assignments", headers=auth).json()
    assert body["id"] not in [a["id"] for a in visible]
    blocked = methodist.post(
        f"/api/student/assignments/{body['id']}/submissions",
        json={"source_url": "https://github.com/demo/crt"}, headers=auth,
    )
    assert blocked.status_code == 404

    # публикуем — появляется у студента и принимает работу
    pub = methodist.post(f"/api/methodist/assignments/{body['id']}/publish", json={"published": True})
    assert pub.status_code == 200 and pub.json()["published"] is True
    visible = methodist.get("/api/student/assignments", headers=auth).json()
    assert body["id"] in [a["id"] for a in visible]
    submit = methodist.post(
        f"/api/student/assignments/{body['id']}/submissions",
        json={"source_url": "https://github.com/demo/crt"}, headers=auth,
    )
    assert submit.status_code == 201


def test_registry_groups_published_assignments_with_non_submitters(methodist):
    course = methodist.get("/api/methodist/courses").json()[0]
    created = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"], "title": "ДЗ без сдач",
        "criteria": [{"title": "Единственный критерий", "max_score": 10}],
        "publish": True,
    }).json()

    groups = methodist.get("/api/methodist/submissions").json()
    assert isinstance(groups, list) and groups
    for g in groups:
        assert set(g) == {"assignment", "stats", "rows"}
        assert g["stats"]["students"] == len(g["rows"])

    fresh = next(g for g in groups if g["assignment"]["id"] == created["id"])
    assert fresh["stats"]["submitted"] == 0
    assert fresh["stats"]["not_submitted"] == fresh["stats"]["students"] > 0
    assert all(r["status"] == "not_submitted" and r["submission_id"] is None for r in fresh["rows"])

    seeded = next(g for g in groups if g["assignment"]["id"] != created["id"])
    assert seeded["stats"]["submitted"] > 0
    assert any(r["status"] != "not_submitted" for r in seeded["rows"])


def test_draft_assignment_is_absent_from_registry(methodist):
    course = methodist.get("/api/methodist/courses").json()[0]
    draft = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"], "title": "Черновик-невидимка",
        "criteria": [{"title": "к", "max_score": 5}],
    }).json()
    ids = [g["assignment"]["id"] for g in methodist.get("/api/methodist/submissions").json()]
    assert draft["id"] not in ids
    methodist.post(f"/api/methodist/assignments/{draft['id']}/publish", json={"published": True})
    ids = [g["assignment"]["id"] for g in methodist.get("/api/methodist/submissions").json()]
    assert draft["id"] in ids


def test_create_assignment_requires_at_least_one_criterion(methodist):
    resp = methodist.post(
        "/api/methodist/assignments",
        json={"title": "Пустое", "criteria": []},
    )
    assert resp.status_code == 422


def test_publish_new_rubric_version_via_criteria_editor(methodist):
    item = methodist.get("/api/methodist/assignments").json()[0]
    before = item["rubric_version"]
    criteria = [{"key": c["key"], "title": c["title"], "max_score": c["max_score"]} for c in item["rubric"]]
    criteria.append({"key": "", "title": "Новый критерий", "max_score": 2})
    resp = methodist.post(
        f"/api/methodist/assignments/{item['id']}/rubrics",
        json={"criteria": criteria, "pass_score": 6, "note": "Обновлено в кабинете"},
    )
    assert resp.status_code == 201
    after = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == item["id"])
    assert after["rubric_version"] == before + 1
    assert len(after["rubric"]) == len(item["rubric"]) + 1


def test_auto_assign_applies_to_freshly_submitted_work(methodist):
    from app.db import SessionLocal
    from app.models import Assignment, Course, Enrollment, Role, User
    from app.security import issue_token

    methodist.post("/api/methodist/distribution/auto", json={"enabled": True})

    with SessionLocal() as db:
        course = db.scalar(select(Course))
        assignment_id = str(db.scalar(select(Assignment.id).where(Assignment.course_id == course.id)))
        student = User(email="fresh@demo.local", full_name="Свежий Студент", role=Role.STUDENT)
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=course.id, user_id=student.id))
        db.commit()
        token = issue_token(student)

    submit = methodist.post(
        f"/api/student/assignments/{assignment_id}/submissions",
        json={"source_url": "https://github.com/demo/fresh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert submit.status_code == 201
    assert submit.json()["status"] == "assigned", "авто-режим назначает ревьюера сразу при сдаче"

    fresh_id = submit.json()["id"]
    placed = next(
        (row for row in _state(methodist)["assigned"] if row["submission"]["id"] == fresh_id),
        None,
    )
    assert placed and placed["reviewer"]["id"]
