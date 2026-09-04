"""Знаменатель балла приходит с сервера, а не дорисовывается интерфейсом.

Раньше все экраны писали «из 10» прямо в разметке. Методист заводит критерии
с любой суммой — экран «Задания и критерии» это прямо позволяет, — и у любой
рубрики, кроме десятибалльной, студенту показывали неверную шкалу: 11 из 10.

Тест намеренно берёт рубрику на 12 баллов: на десятке ошибка не видна.
"""

import pytest


def enrolled_student(course_id: str, email: str) -> dict:
    from app.db import SessionLocal
    from app.models import Enrollment, Role, User
    from app.security import issue_token

    with SessionLocal() as db:
        student = User(email=email, full_name="Шкала Студент", role=Role.STUDENT)
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=course_id, user_id=student.id))
        db.commit()
        return {"Authorization": f"Bearer {issue_token(student)}"}


@pytest.fixture
def twelve_point_assignment(methodist):
    course = methodist.get("/api/methodist/courses").json()[0]
    created = methodist.post("/api/methodist/assignments", json={
        "course_id": course["id"],
        "title": "ДЗ на двенадцать баллов",
        "criteria": [
            {"title": "Первый критерий", "max_score": 7},
            {"title": "Второй критерий", "max_score": 5},
        ],
        "pass_score": 8,
        "publish": True,
    }).json()
    return course, created


def test_rubric_max_is_not_ten(twelve_point_assignment):
    _, created = twelve_point_assignment

    assert created["max_score"] == 12, "иначе тест не проверяет то, ради чего написан"


def test_student_assignment_list_carries_the_real_maximum(methodist, twelve_point_assignment):
    course, created = twelve_point_assignment
    auth = enrolled_student(course["id"], "scale-list@demo.local")

    rows = methodist.get("/api/student/assignments", headers=auth).json()
    row = next(a for a in rows if a["id"] == created["id"])

    assert row["max_score"] == 12


def test_reviewer_history_carries_the_real_maximum(reviewer):
    rows = reviewer.get("/api/reviewer/history").json()

    assert rows, "на пустой истории проверка ничего не значит"
    for row in rows:
        assert "max_score" in row, "знаменатель нужен рядом с каждым баллом"


def test_a_review_without_a_rubric_reports_no_maximum():
    # Знаменатель либо настоящий, либо отсутствует. Подставлять число, когда
    # рубрики нет, — это ровно то, что здесь чинилось.
    from app.models import Review
    from app.serializers import review_max_score

    assert review_max_score(Review()) is None
    assert review_max_score(None) is None
