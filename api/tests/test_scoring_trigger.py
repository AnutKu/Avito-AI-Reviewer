"""Разбор запускается назначением ревьюера, а не сдачей работы.

Раньше прогон стартовал в момент сдачи. У работы, которая ждёт распределения,
ревьюера нет — считать не для кого, а прогон уже оплачен; заодно демо-база
раздавала таким работам готовые фикстуры, и назначенный ревьюер открывал
«разбор», которого никто не делал.

Здесь проверяется момент запуска и то, что ревьюер об этом узнаёт.
"""

import pytest

from app.models import AiStatus, Review, ReviewAssignment, Submission, SubmissionStatus


@pytest.fixture
def started(monkeypatch):
    """Кого поставили в очередь на разбор. Прогон при этом не выполняется."""

    from app.services import review_pipeline

    calls: list = []
    monkeypatch.setattr(review_pipeline, "run_review", lambda review_id: calls.append(review_id))
    monkeypatch.setattr(review_pipeline, "run_detection", lambda review_id: None)
    return calls


def submit_new_work(client) -> str:
    """Сдаёт работу от лица нового студента. Возвращает id работы."""

    from app.db import SessionLocal
    from app.models import Enrollment, Role, User
    from app.security import issue_token

    with SessionLocal() as db:
        published = db.scalars(published_assignments()).first()
        student = User(
            email=f"trig{id(client)}@demo.local",
            full_name="Триггер Студент",
            role=Role.STUDENT,
        )
        db.add(student)
        db.flush()
        db.add(Enrollment(course_id=published.course_id, user_id=student.id))
        db.commit()
        token = issue_token(student)
        assignment_id = str(published.id)

    response = client.post(
        f"/api/student/assignments/{assignment_id}/submissions",
        json={"source_url": "https://github.com/demo/trigger"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 202, response.text
    return response.json()["id"]


def published_assignments():
    from sqlalchemy import select

    from app.models import Assignment

    return (
        select(Assignment)
        .where(Assignment.published_at.is_not(None))
        .order_by(Assignment.created_at)
    )


def review_of(submission_id: str) -> Review:
    from sqlalchemy import select

    from app.db import SessionLocal

    with SessionLocal() as db:
        return db.scalar(select(Review).where(Review.submission_id == submission_id))


def test_submitting_alone_does_not_start_scoring(methodist, started):
    submission_id = submit_new_work(methodist)

    assert started == [], "у работы ещё нет ревьюера — считать не для кого"
    assert review_of(submission_id).ai_status == AiStatus.PENDING


def test_assigning_a_reviewer_starts_scoring(methodist, started):
    submission_id = submit_new_work(methodist)
    reviewer = methodist.get("/api/methodist/reviewers").json()[0]

    applied = methodist.post("/api/methodist/distribution/apply", json={
        "assignments": [{"submission_id": submission_id, "reviewer_id": reviewer["id"]}],
    })

    assert applied.status_code == 200, applied.text
    assert applied.json()["scoring_started"] >= 1
    assert str(review_of(submission_id).id) in [str(call) for call in started]


def test_a_finished_review_is_not_scored_again(methodist, started):
    submission_id = submit_new_work(methodist)
    reviewer = methodist.get("/api/methodist/reviewers").json()[0]
    methodist.post("/api/methodist/distribution/apply", json={
        "assignments": [{"submission_id": submission_id, "reviewer_id": reviewer["id"]}],
    })
    # Прогон в тестах заглушён, поэтому доводим статус руками — свип смотрит на него.
    from app.db import SessionLocal

    with SessionLocal() as db:
        review = db.scalar(review_query(submission_id))
        review.ai_status = AiStatus.READY
        db.commit()
    started.clear()

    other = methodist.get("/api/methodist/reviewers").json()[-1]
    methodist.patch(
        f"/api/methodist/submissions/{submission_id}/reviewer",
        json={"reviewer_id": other["id"], "force": True},
    )

    assert started == [], "переназначение не должно перезапускать готовый разбор"


def review_query(submission_id):
    from sqlalchemy import select

    return select(Review).where(Review.submission_id == submission_id)


def test_the_reviewer_is_told_when_scoring_finishes(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Notification
    from app.services.review_pipeline import notify_scoring_done

    with SessionLocal() as db:
        assignment = db.scalar(
            select(ReviewAssignment).where(
                ReviewAssignment.is_active.is_(True),
                ReviewAssignment.approved_at.is_not(None),
            )
        )
        review = db.scalar(select(Review).where(Review.submission_id == assignment.submission_id))
        review.ai_status = AiStatus.READY

        notify_scoring_done(db, review)
        db.commit()

        note = db.scalars(
            select(Notification)
            .where(Notification.recipient_id == assignment.reviewer_id)
            .order_by(Notification.sent_at.desc())
        ).first()

    assert note.kind == "ai_review_ready"


def test_a_failed_run_is_reported_too(client):
    # Молчание об отказе оставляет работу висеть в очереди без разбора и без
    # причины: ревьюер не знает, ждать ему или перезапускать.
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Notification
    from app.services.review_pipeline import notify_scoring_done

    with SessionLocal() as db:
        assignment = db.scalar(
            select(ReviewAssignment).where(
                ReviewAssignment.is_active.is_(True),
                ReviewAssignment.approved_at.is_not(None),
            )
        )
        review = db.scalar(select(Review).where(Review.submission_id == assignment.submission_id))
        review.ai_status = AiStatus.FAILED
        review.ai_error = "Z.AI недоступен"

        notify_scoring_done(db, review)
        db.commit()

        note = db.scalars(
            select(Notification)
            .where(Notification.recipient_id == assignment.reviewer_id)
            .order_by(Notification.sent_at.desc())
        ).first()

    assert note.kind == "ai_review_failed"
    assert "Z.AI недоступен" in note.body


def test_seeded_work_awaiting_distribution_has_no_invented_review(client):
    # Ровно то, что видел ревьюер: работа без ревьюера приходила из сидов с
    # готовым разбором, и после назначения он выдавался за настоящий.
    from sqlalchemy import select

    from app.db import SessionLocal

    with SessionLocal() as db:
        waiting = db.scalars(
            select(Submission).where(
                Submission.status.in_((SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED))
            )
        ).all()
        assert waiting, "в демо-базе должна быть хотя бы одна нераспределённая работа"
        for submission in waiting:
            review = db.scalar(select(Review).where(Review.submission_id == submission.id))
            assert review.ai_status == AiStatus.PENDING, submission.id
            assert not review.items, "разбора не было — items быть не должно"
