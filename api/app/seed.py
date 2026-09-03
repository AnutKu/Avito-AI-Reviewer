from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    Assignment,
    BlitzSession,
    BlitzStatus,
    Course,
    Enrollment,
    Notification,
    Review,
    ReviewAssignment,
    ReviewerAction,
    Role,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
    User,
)
from .services.mock_review import blitz_questions, fill_demo_review


def seed_demo(db: Session) -> None:
    legacy_reviews = list(db.scalars(select(Review).where(Review.model == "mock/ai-review-v1")))
    for review in legacy_reviews:
        review.model = "demo-fixture/v1"
        review.raw_result = {
            **review.raw_result,
            "mock": False,
            "demo_data": True,
        }
    if legacy_reviews:
        db.commit()
    if db.scalar(select(User.id).limit(1)):
        return

    now = datetime.now(UTC)
    methodist = User(
        email="methodist@demo.local",
        full_name="Анна Воронова",
        role=Role.METHODIST,
        specialization="data_science",
    )
    reviewers = [
        User(
            email="reviewer@demo.local",
            full_name="Максим Орлов",
            role=Role.REVIEWER,
            specialization="data_science",
        ),
        User(
            email="reviewer2@demo.local",
            full_name="Елена Соколова",
            role=Role.REVIEWER,
            specialization="data_science",
        ),
    ]
    students = [
        User(email="student@demo.local", full_name="Алексей Смирнов", role=Role.STUDENT),
        User(email="student2@demo.local", full_name="Мария Иванова", role=Role.STUDENT),
        User(email="student3@demo.local", full_name="Дмитрий Волков", role=Role.STUDENT),
        User(email="student4@demo.local", full_name="София Лебедева", role=Role.STUDENT),
        User(email="student5@demo.local", full_name="Кирилл Попов", role=Role.STUDENT),
        User(email="student6@demo.local", full_name="Алина Морозова", role=Role.STUDENT),
    ]
    db.add_all([methodist, *reviewers, *students])
    db.flush()

    course = Course(
        title="Аналитика данных: поток 2026",
        specialization="data_science",
        reviewer_capacity=12,
        tone_of_voice={
            "style": "доброжелательный и предметный",
            "address": "на вы",
            "rules": ["Начинать с сильных сторон", "Замечания подкреплять примером"],
        },
    )
    db.add(course)
    db.flush()
    db.add_all([Enrollment(course_id=course.id, user_id=student.id) for student in students])

    assignment = Assignment(
        course_id=course.id,
        title="Трекинг экспериментов в MLflow",
        statement=(
            "Проведите серию экспериментов над моделью, зафиксируйте параметры и метрики "
            "в MLflow, сравните результаты и зарегистрируйте лучшую модель. Передайте ссылку "
            "на GitHub-репозиторий с воспроизводимым ноутбуком."
        ),
        deadline_at=now + timedelta(days=2),
        effort_weight=1.0,
        submission_channel="github",
    )
    db.add(assignment)
    db.flush()
    rubric = RubricVersion(
        assignment_id=assignment.id,
        version=3,
        author_id=methodist.id,
        max_score=10,
        pass_score=6,
        note="Уточнены требования к Model Registry и воспроизводимости",
        criteria=[
            {"key": "experiment_tracking", "title": "Трекинг экспериментов", "max_score": 3},
            {"key": "runs_count", "title": "Не менее 20 запусков", "max_score": 2},
            {"key": "model_registry", "title": "Регистрация лучшей модели", "max_score": 2},
            {"key": "reproducibility", "title": "Воспроизводимость", "max_score": 2},
            {"key": "conclusions", "title": "Выводы по экспериментам", "max_score": 1},
        ],
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id

    states = [
        SubmissionStatus.COMPLETED,
        SubmissionStatus.IN_REVIEW,
        SubmissionStatus.ASSIGNED,
        SubmissionStatus.BLITZ_SENT,
        SubmissionStatus.PROPOSED,
        SubmissionStatus.SUBMITTED,
    ]
    qualities = [1.0, 0.82, 0.68, 0.9, 0.58, 0.75]
    for index, (student, state, quality) in enumerate(zip(students, states, qualities, strict=True)):
        submission = Submission(
            assignment_id=assignment.id,
            student_id=student.id,
            source_url=f"https://github.com/demo-student/mlflow-homework-{index + 1}",
            submitted_at=now - timedelta(hours=34 - index * 4),
            status=state,
            is_overdue=index == 4,
        )
        db.add(submission)
        db.flush()
        db.add(
            Snapshot(
                submission_id=submission.id,
                content=(
                    "# MLflow experiments\n\n"
                    "В работе сравниваются Logistic Regression и Random Forest.\n\n"
                    "```python\n"
                    "with mlflow.start_run():\n"
                    "    mlflow.log_params(params)\n"
                    "    mlflow.log_metrics({'accuracy': accuracy, 'f1': f1})\n"
                    "    mlflow.sklearn.log_model(model, artifact_path='model')\n"
                    "```\n\n"
                    "Лучший результат показал Random Forest."
                ),
                content_hash=f"demo-snapshot-{index + 1:02d}",
                parsed_facts={
                    "runs": 24 - index,
                    "metrics": ["accuracy", "precision", "recall", "f1"],
                    "seed": 42,
                    "registered_model": index == 0,
                    "failed_cells_ratio": 0.08,
                },
            )
        )
        review = Review(submission_id=submission.id, rubric_version_id=rubric.id)
        db.add(review)
        db.flush()
        fill_demo_review(db, review, quality)

        if state not in (SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED):
            reviewer = reviewers[index % len(reviewers)]
            db.add(
                ReviewAssignment(
                    submission_id=submission.id,
                    reviewer_id=reviewer.id,
                    explanation="Специализация совпадает · минимальная загрузка на момент назначения",
                    approved_by=methodist.id,
                    approved_at=now - timedelta(hours=24 - index),
                )
            )
        if state == SubmissionStatus.PROPOSED:
            db.add(
                ReviewAssignment(
                    submission_id=submission.id,
                    reviewer_id=reviewers[0].id,
                    explanation="Специализация совпадает · загрузка 2 работы · рассмотрено кандидатов: 2",
                )
            )
        if state == SubmissionStatus.COMPLETED:
            review.final_score = 8.0
            review.final_feedback = review.draft_feedback
            review.completed_by = reviewers[0].id
            review.completed_at = now - timedelta(hours=3)
            for item in review.items:
                item.reviewer_action = ReviewerAction.ACCEPTED
                item.final_score = item.ai_score
        if state == SubmissionStatus.BLITZ_SENT:
            db.add(
                BlitzSession(
                    review_id=review.id,
                    status=BlitzStatus.SENT,
                    questions=blitz_questions()[:2],
                    sent_at=now - timedelta(hours=4),
                    due_at=now + timedelta(hours=44),
                )
            )
        db.add(
            StatusHistory(
                submission_id=submission.id,
                from_status=None,
                to_status=state,
                actor_id=methodist.id,
                comment="Демонстрационная история",
            )
        )

    db.add_all(
        [
            Notification(
                recipient_id=reviewers[0].id,
                kind="assignment",
                title="Назначены новые работы",
                body="В очереди 2 работы по MLflow",
                payload={"route": "/reviewer/queue"},
            ),
            Notification(
                recipient_id=methodist.id,
                kind="deadline_risk",
                title="Риск просрочки",
                body="Одна работа не начата менее чем за 24 часа до контрольного срока",
                payload={"route": "/methodist/registry"},
            ),
            Notification(
                recipient_id=students[0].id,
                kind="review_completed",
                title="Работа проверена",
                body="Опубликованы оценка и обратная связь",
                payload={"route": "/student/assignments"},
            ),
        ]
    )
    db.commit()
