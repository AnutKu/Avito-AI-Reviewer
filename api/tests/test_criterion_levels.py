"""Градация внутри критерия: за что ставится каждый балл.

Градацию сочиняет конструктор заданий, а нужна она ревьюеру — в тот момент,
когда он решает, ставить 2 или 3. Между ними четыре передачи (конструктор →
кабинет методиста → рубрика → экран ревью), и на любой из них список можно
незаметно потерять: он не обязателен ни в одной схеме.

Второе, что здесь проверяется, — что градация не уезжает студенту. Это скрытая
часть рубрики: по ней решение подгоняется под грейдинг.
"""

import pytest

LEVELS = [
    {"points": 0, "label": "нет", "descriptor": "тестов нет"},
    {"points": 1, "label": "частично", "descriptor": "тесты есть, но крайние случаи не покрыты"},
    {"points": 2, "label": "полно", "descriptor": "не меньше 8 кейсов, из них 3 на крайние случаи"},
]


@pytest.fixture
def graded_assignment(methodist):
    course = methodist.get("/api/methodist/courses").json()[0]
    created = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"],
        "title": "ДЗ с градацией",
        "criteria": [
            {"title": "Тесты", "max_score": 2, "student_hint": "Решение покрыто тестами", "levels": LEVELS},
            {"title": "Структура", "max_score": 2},
        ],
        "pass_score": 2,
        "publish": True,
    })
    assert created.status_code == 201, created.text
    return course, created.json()


def test_gradation_survives_the_trip_into_the_rubric(methodist, graded_assignment):
    _, created = graded_assignment

    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == created["id"])
    criterion = next(c for c in row["rubric"] if c["title"] == "Тесты")

    assert [level["points"] for level in criterion["levels"]] == [0, 1, 2]
    assert criterion["levels"][2]["descriptor"].startswith("не меньше 8")


def test_a_criterion_without_gradation_keeps_working(methodist, graded_assignment):
    # Рубрику заводят и руками: критерий без градации — не ошибка, у него
    # просто пустой список, а не отсутствующее поле.
    _, created = graded_assignment

    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == created["id"])
    criterion = next(c for c in row["rubric"] if c["title"] == "Структура")

    assert criterion["levels"] == []


def test_levels_are_sorted_by_score(methodist, graded_assignment):
    course, _ = graded_assignment
    created = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"],
        "title": "ДЗ с перепутанными уровнями",
        "criteria": [{"title": "Тесты", "max_score": 2, "levels": list(reversed(LEVELS))}],
        "pass_score": 1,
    }).json()

    row = next(a for a in methodist.get("/api/methodist/assignments").json() if a["id"] == created["id"])

    assert [level["points"] for level in row["rubric"][0]["levels"]] == [0, 1, 2]


def test_a_level_above_the_maximum_is_refused(methodist, graded_assignment):
    course, _ = graded_assignment
    response = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"],
        "title": "ДЗ с недостижимым уровнем",
        "criteria": [{
            "title": "Тесты",
            "max_score": 2,
            "levels": [*LEVELS, {"points": 5, "label": "сверх", "descriptor": "столько не поставить"}],
        }],
        "pass_score": 1,
    })

    assert response.status_code == 422


def test_student_does_not_see_the_gradation(methodist, graded_assignment):
    from app.db import SessionLocal
    from app.models import Enrollment, Role, User
    from app.security import issue_token

    course, created = graded_assignment
    with SessionLocal() as db:
        student = User(email="levels@demo.local", full_name="Градация Студент", role=Role.STUDENT)
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=course["id"], user_id=student.id))
        db.commit()
        auth = {"Authorization": f"Bearer {issue_token(student)}"}

    data = methodist.get(f"/api/student/assignments/{created['id']}", headers=auth).json()
    criterion = next(c for c in data["rubric"] if c["title"] == "Тесты")

    assert "levels" not in criterion, "градация — скрытая часть рубрики"
    assert criterion["max_score"] == 2, "вес критерия студент видеть должен"


def test_review_items_carry_the_gradation_of_their_criterion(reviewer):
    # Демо-рубрика с градацией — та же, что открывает ревьюер: если по дороге
    # к экрану список теряется, ревьюер снова оценивает «сколько-то из трёх».
    queue = reviewer.get("/api/reviewer/queue").json()
    assert queue, "на пустой очереди проверка ничего не значит"

    screen = reviewer.get(f"/api/reviewer/submissions/{queue[0]['id']}/review").json()
    items = screen["review"]["items"]
    assert items, "у работы должен быть разбор по критериям"

    graded = [item for item in items if item["levels"]]
    assert graded, "ни у одного критерия не доехала градация"
    for item in graded:
        assert item["levels"][0]["points"] == 0
        assert item["levels"][-1]["points"] == item["max_score"]
        assert all(level["descriptor"] for level in item["levels"])
