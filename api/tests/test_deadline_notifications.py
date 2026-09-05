"""Что и когда напоминать о сроках.

Главное здесь — что человек не получает пачку напоминаний за один заход и не
получает одно и то же дважды: ключ уведомления зависит от порога, а порог
берётся один — самый близкий из сработавших. БД тестам не нужна.
"""

from datetime import UTC, datetime, timedelta

from app.services.deadline_notifications import (
    REVIEWER_THRESHOLDS,
    STUDENT_THRESHOLDS,
    reviewer_notices,
    student_notices,
    tightest_threshold,
)

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


def student(*, hours_left=None, submitted=False):
    deadline = None if hours_left is None else NOW + timedelta(hours=hours_left)
    return student_notices(
        assignment_id="a1",
        title="Трекинг экспериментов",
        deadline=deadline,
        now=NOW,
        submitted=submitted,
    )


def review(*, hours_left=None, completed=False):
    deadline = None if hours_left is None else NOW + timedelta(hours=hours_left)
    return reviewer_notices(
        submission_id="s1",
        title="Трекинг экспериментов",
        student="Иван Петров",
        deadline=deadline,
        now=NOW,
        completed=completed,
    )


def test_far_deadline_says_nothing():
    assert student(hours_left=100) == []
    assert review(hours_left=100) == []


def test_student_is_warned_three_days_out():
    (notice,) = student(hours_left=70)
    assert notice.kind == "deadline_soon"
    assert "меньше трёх суток" in notice.body


def test_one_visit_gives_one_notice_even_when_every_threshold_matched():
    notices = student(hours_left=2)
    assert len(notices) == 1, "иначе за два часа до срока прилетает и «за трое суток»"
    assert "меньше суток" in notices[0].body


def test_thresholds_have_different_keys_so_both_reach_the_student():
    (early,) = student(hours_left=70)
    (late,) = student(hours_left=5)
    assert early.key != late.key


def test_the_same_threshold_keeps_one_key_whenever_it_is_checked():
    assert student(hours_left=20)[0].key == student(hours_left=3)[0].key


def test_submitted_work_is_not_nagged():
    assert student(hours_left=1, submitted=True) == []
    assert student(hours_left=-1, submitted=True) == []


def test_missed_deadline_is_reported_once_and_says_that_submitting_is_still_possible():
    (notice,) = student(hours_left=-5)
    assert notice.kind == "deadline_missed"
    assert notice.key == student(hours_left=-30)[0].key
    assert "после срока" in notice.body


def test_old_miss_stops_being_a_reminder():
    assert student(hours_left=-24 * 8) == []


def test_work_without_a_deadline_is_never_flagged():
    assert student() == []
    assert review() == []


def test_reviewer_is_warned_a_day_out_and_after_the_deadline():
    (soon,) = review(hours_left=20)
    (late,) = review(hours_left=-2)
    assert soon.kind == "review_deadline"
    assert late.kind == "review_overdue"
    assert soon.route == late.route == "/reviewer/queue"


def test_completed_review_is_never_flagged():
    assert review(hours_left=-2, completed=True) == []


def test_tightest_threshold_picks_the_nearest_match():
    assert tightest_threshold(70, STUDENT_THRESHOLDS) == 72
    assert tightest_threshold(20, STUDENT_THRESHOLDS) == 24
    assert tightest_threshold(200, STUDENT_THRESHOLDS) is None
    assert tightest_threshold(20, REVIEWER_THRESHOLDS) == 24


# --- через API -------------------------------------------------------------
# Здесь проверяется то, чего чистые функции не видят: напоминание доходит до
# конкретного человека и не размножается от обновления страницы.


def login(client, role: str) -> dict:
    body = client.post(f"/api/auth/demo/{role}").json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    return body["user"]


def publish_assignment(client, *, title: str, hours_left: int) -> dict:
    deadline = datetime.now(UTC) + timedelta(hours=hours_left)
    return client.post(
        "/api/methodist/assignments",
        json={
            "title": title,
            "deadline_at": deadline.isoformat(),
            "publish": True,
            "criteria": [{"title": "Решение работает", "max_score": 5}],
        },
    ).json()


def notices(client, kind: str, needle: str) -> list[dict]:
    rows = client.get("/api/notifications").json()
    return [row for row in rows if row["kind"] == kind and needle in row["payload"].get("key", "")]


def test_a_near_deadline_reaches_the_student_and_does_not_multiply(client):
    login(client, "methodist")
    assignment = publish_assignment(client, title="Валидация и утечки данных", hours_left=20)

    login(client, "student")
    first = notices(client, "deadline_soon", assignment["id"])
    assert len(first) == 1, "несданная работа со сроком через 20 часов — это напоминание"
    assert first[0]["payload"]["route"] == "/student/assignments"

    # Обновление страницы — не событие: второй раз то же напоминание не заводится.
    assert len(notices(client, "deadline_soon", assignment["id"])) == 1


def test_a_submitted_work_stops_reminding_the_student(client):
    login(client, "methodist")
    assignment = publish_assignment(client, title="Кросс-валидация", hours_left=20)

    login(client, "student")
    client.post(
        f"/api/student/assignments/{assignment['id']}/submissions",
        json={"source_url": "https://github.com/demo-student/cv-homework"},
    )
    assert notices(client, "deadline_soon", assignment["id"]) == []


def test_the_reviewer_is_reminded_about_the_work_on_his_hands(client):
    reviewer = login(client, "reviewer")
    login(client, "methodist")
    assignment = publish_assignment(client, title="Подбор порога классификации", hours_left=20)

    login(client, "student")
    submission = client.post(
        f"/api/student/assignments/{assignment['id']}/submissions",
        json={"source_url": "https://github.com/demo-student/threshold-homework"},
    ).json()

    login(client, "methodist")
    client.patch(
        f"/api/methodist/submissions/{submission['id']}/reviewer",
        json={"reviewer_id": reviewer["id"], "force": True},
    )

    login(client, "reviewer")
    assert len(notices(client, "review_deadline", submission["id"])) == 1


def test_the_methodist_gets_no_deadline_reminders(client):
    login(client, "methodist")
    assignment = publish_assignment(client, title="Ансамбли моделей", hours_left=20)

    assert notices(client, "deadline_soon", assignment["id"]) == []
