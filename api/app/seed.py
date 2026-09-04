from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import (
    AiStatus,
    Assignment,
    BlitzSession,
    BlitzStatus,
    Confidence,
    Course,
    Enrollment,
    Notification,
    Review,
    ReviewAssignment,
    ReviewerAction,
    ReviewItem,
    Role,
    RubricVersion,
    Snapshot,
    StatusHistory,
    Submission,
    SubmissionStatus,
    User,
    Verdict,
)
from .services.mock_review import demo_blitz_questions, fill_demo_review


# --------------------------------------------------------------------------- #
# История сданных ДЗ
#
# Дашборд и успеваемость считаются по живым записям, поэтому одного текущего
# задания им мало: без закрытых работ нет ни динамики по неделям, ни статистики
# правок, ни среднего балла. Ниже — архив прошлых ДЗ курса: он создаётся один
# раз и только для демо-курса, продовый сценарий им не затрагивается.
# --------------------------------------------------------------------------- #

# Базовая «сила» студента (порядок — по алфавиту полного имени, как в кабинете).
BASE_QUALITY = (0.92, 0.74, 0.55, 0.83, 0.68, 0.88)

HISTORY_ASSIGNMENTS = (
    {
        "title": "Разведочный анализ данных",
        "statement": (
            "Изучите датасет: проверьте пропуски и выбросы, постройте распределения "
            "ключевых признаков и их взаимосвязи, сформулируйте гипотезы о том, что "
            "влияет на целевую переменную."
        ),
        "weeks_ago": 4,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("data_quality", "Проверка качества данных", 3.0),
            ("visual_analysis", "Визуальный анализ признаков", 3.0),
            ("hypotheses", "Гипотезы и выводы", 2.0),
            ("notebook_style", "Оформление ноутбука", 2.0),
        ),
        "problem_index": 2,
        "drift": -0.05,
        "assign_delay_hours": 20,
        "review_hours": 34.0,
        "skipped": (),
        "overdue": (4,),
    },
    {
        "title": "Базовая модель и метрики качества",
        "statement": (
            "Обучите базовую модель, обоснуйте выбор метрик под задачу, опишите схему "
            "валидации и разберите типичные ошибки модели на примерах."
        ),
        "weeks_ago": 3,
        "effort_weight": 1.5,
        "pass_score": 6.0,
        "criteria": (
            ("baseline", "Обучение базовой модели", 3.0),
            ("metrics", "Выбор и обоснование метрик", 3.0),
            ("validation", "Схема валидации", 2.0),
            ("error_analysis", "Анализ ошибок", 2.0),
        ),
        "problem_index": 3,
        "drift": 0.0,
        "assign_delay_hours": 12,
        "review_hours": 26.0,
        "skipped": (2,),
        "overdue": (5,),
    },
    {
        "title": "Отбор и конструирование признаков",
        "statement": (
            "Постройте новые признаки на основе доменных гипотез, оцените их вклад в "
            "качество модели и обоснуйте итоговый набор."
        ),
        "weeks_ago": 2,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("feature_ideas", "Гипотезы о признаках", 2.0),
            ("feature_code", "Реализация преобразований", 3.0),
            ("feature_impact", "Оценка вклада признаков", 3.0),
            ("feature_selection", "Обоснование итогового набора", 2.0),
        ),
        "problem_index": 2,
        "drift": 0.02,
        "assign_delay_hours": 9,
        "review_hours": 20.0,
        "skipped": (4,),
        "overdue": (0,),
    },
    {
        "title": "Подбор гиперпараметров",
        "statement": (
            "Определите пространство поиска, подберите гиперпараметры выбранным методом, "
            "покажите контроль переобучения и зафиксируйте итоговую конфигурацию."
        ),
        "weeks_ago": 1,
        "effort_weight": 1.0,
        "pass_score": 6.0,
        "criteria": (
            ("search_space", "Пространство поиска", 2.0),
            ("search_method", "Метод подбора", 3.0),
            ("overfit_control", "Контроль переобучения", 3.0),
            ("conclusions", "Выводы и итоговая конфигурация", 2.0),
        ),
        "problem_index": 2,
        "drift": 0.05,
        "assign_delay_hours": 6,
        "review_hours": 14.0,
        "skipped": (2,),
        "overdue": (1,),
    },
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _verdict(score: float, max_score: float) -> str:
    if score >= max_score * 0.85:
        return Verdict.PASSED
    if score <= max_score * 0.35:
        return Verdict.FAILED
    return Verdict.PARTIAL


def _decision(spec: dict, student_index: int, position: int, score: float, max_score: float):
    """Решение ревьюера по критерию: (действие, итоговый балл).

    Правки не размазаны равномерно — иначе «критерии с частыми правками»
    показывали бы одинаковый шум по всем строкам. Один критерий задания
    проблемный, соседний правится изредка, остальные принимаются как есть."""

    if position == spec["problem_index"]:
        if student_index % 4 == 3:
            return ReviewerAction.REJECTED, None
        if student_index % 5 == 1:
            return ReviewerAction.ACCEPTED, score
        step = 0.5 if student_index % 2 == 0 else -0.5
        return ReviewerAction.CHANGED, _clamp(score + step, 0.0, max_score)
    if position == (spec["problem_index"] + 1) % len(spec["criteria"]) and student_index % 3 == 0:
        return ReviewerAction.CHANGED, _clamp(score - 0.5, 0.0, max_score)
    return ReviewerAction.ACCEPTED, score


def _seed_history_assignment(
    db: Session,
    spec: dict,
    *,
    course: Course,
    methodist: User | None,
    reviewers: list[User],
    students: list[User],
    now: datetime,
) -> None:
    deadline = now - timedelta(weeks=spec["weeks_ago"])
    opened = deadline - timedelta(days=10)
    assignment = Assignment(
        course_id=course.id,
        title=spec["title"],
        statement=spec["statement"],
        deadline_at=deadline,
        effort_weight=spec["effort_weight"],
        submission_channel="github",
        published_at=opened,
        created_at=opened,
    )
    db.add(assignment)
    db.flush()

    criteria = [
        {"key": key, "title": title, "max_score": max_score}
        for key, title, max_score in spec["criteria"]
    ]
    rubric = RubricVersion(
        assignment_id=assignment.id,
        version=1,
        criteria=criteria,
        max_score=sum(item["max_score"] for item in criteria),
        pass_score=spec["pass_score"],
        author_id=methodist.id if methodist else None,
        published_at=opened,
        note="Архивная версия задания",
    )
    db.add(rubric)
    db.flush()
    assignment.current_rubric_version_id = rubric.id

    for index, student in enumerate(students):
        if index in spec["skipped"]:
            continue
        overdue = index in spec["overdue"]
        submitted_at = (
            deadline + timedelta(hours=7)
            if overdue
            else deadline - timedelta(hours=8 + index * 5)
        )
        submission = Submission(
            assignment_id=assignment.id,
            student_id=student.id,
            source_url=f"https://github.com/demo-student/{spec['criteria'][0][0]}-{index + 1}",
            submitted_at=submitted_at,
            status=SubmissionStatus.COMPLETED,
            is_overdue=overdue,
        )
        db.add(submission)
        db.flush()
        db.add(
            Snapshot(
                submission_id=submission.id,
                content=f"# {spec['title']}\n\nАрхивная работа демо-курса.\n",
                content_hash=f"demo-{spec['criteria'][0][0]}-{index + 1:02d}",
                fetched_at=submitted_at,
                parsed_facts={"archived": True, "seed": 42},
            )
        )

        reviewer = reviewers[(index + spec["weeks_ago"]) % len(reviewers)]
        approved_at = submitted_at + timedelta(hours=spec["assign_delay_hours"])
        completed_at = approved_at + timedelta(hours=spec["review_hours"] + index * 1.5)
        db.add(
            ReviewAssignment(
                submission_id=submission.id,
                reviewer_id=reviewer.id,
                explanation="Специализация совпадает · минимальная загрузка на момент назначения",
                approved_by=methodist.id if methodist else None,
                approved_at=approved_at,
                created_at=submitted_at + timedelta(minutes=5),
            )
        )
        review = Review(
            submission_id=submission.id,
            rubric_version_id=rubric.id,
            model="demo-fixture/v1",
            ai_status=AiStatus.READY,
            raw_result={
                "summary": f"Архивное ревью по заданию «{spec['title']}».",
                "pipeline": ["extract", "grade", "signal", "feedback"],
                "demo_data": True,
            },
            draft_feedback="Черновик обратной связи из архива демо-курса.",
            final_feedback="Обратная связь опубликована ревьюером.",
            completed_by=reviewer.id,
            completed_at=completed_at,
            created_at=submitted_at + timedelta(minutes=2),
        )
        db.add(review)
        db.flush()

        total = 0.0
        for position, criterion in enumerate(criteria):
            quality = _clamp(
                BASE_QUALITY[index % len(BASE_QUALITY)]
                + spec["drift"]
                + ((index + position) % 3 - 1) * 0.06
            )
            max_score = criterion["max_score"]
            ai_score = round(max_score * quality * 2) / 2
            action, final_score = _decision(spec, index, position, ai_score, max_score)
            total += final_score or 0.0
            db.add(
                ReviewItem(
                    review_id=review.id,
                    position=position,
                    criterion_key=criterion["key"],
                    criterion_title=criterion["title"],
                    max_score=max_score,
                    ai_score=ai_score,
                    verdict=_verdict(ai_score, max_score),
                    confidence=Confidence.MEDIUM,
                    evidence=[{"quote": "Фрагмент работы", "anchor": f"Ячейка {position + 3}"}],
                    recommendation="Замечание из архивного ревью.",
                    reviewer_action=action,
                    final_score=final_score,
                    reviewer_comment=(
                        "" if action == ReviewerAction.ACCEPTED else "Скорректировано ревьюером"
                    ),
                )
            )
        review.final_score = round(total, 1)

        db.add_all(
            [
                StatusHistory(
                    submission_id=submission.id,
                    from_status=None,
                    to_status=SubmissionStatus.SUBMITTED,
                    actor_id=student.id,
                    comment="Работа сдана",
                    created_at=submitted_at,
                ),
                StatusHistory(
                    submission_id=submission.id,
                    from_status=SubmissionStatus.IN_REVIEW,
                    to_status=SubmissionStatus.COMPLETED,
                    actor_id=reviewer.id,
                    comment="Проверка завершена",
                    created_at=completed_at,
                ),
            ]
        )


def seed_history(db: Session) -> None:
    """Досоздать архив прошлых ДЗ. Идемпотентно: задание с таким названием — один раз."""

    course = db.scalar(select(Course).order_by(Course.created_at))
    if not course:
        return
    methodist = db.scalar(select(User).where(User.role == Role.METHODIST))
    reviewers = list(
        db.scalars(select(User).where(User.role == Role.REVIEWER).order_by(User.full_name))
    )
    students = list(
        db.scalars(
            select(User)
            .join(Enrollment, Enrollment.user_id == User.id)
            .where(Enrollment.course_id == course.id, User.role == Role.STUDENT)
            .order_by(User.full_name)
        )
    )
    if not reviewers or not students:
        return

    now = datetime.now(UTC)
    created = False
    for spec in HISTORY_ASSIGNMENTS:
        exists = db.scalar(
            select(Assignment.id).where(
                Assignment.course_id == course.id, Assignment.title == spec["title"]
            )
        )
        if exists:
            continue
        _seed_history_assignment(
            db,
            spec,
            course=course,
            methodist=methodist,
            reviewers=reviewers,
            students=students,
            now=now,
        )
        created = True
    if created:
        db.commit()


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
        # Кабинет уже засеян: досоздаём только то, чего в нём ещё нет.
        seed_history(db)
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
        published_at=now - timedelta(days=7),
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
        # Градация внутри критерия: за что ставится каждый балл. Её видит
        # ревьюер и AI-разбор, студент — нет. Уровни здесь целочисленные:
        # рубрика на 10 баллов из пяти критериев, дробить дальше нечего.
        criteria=[
            {
                "key": "experiment_tracking",
                "title": "Трекинг экспериментов",
                "max_score": 3,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "запуски не логируются или логируется только финальный прогон"},
                    {"points": 1, "label": "частично", "descriptor": "логируются метрики без параметров (или наоборот) — сравнить запуски нельзя"},
                    {"points": 2, "label": "почти полно", "descriptor": "параметры и метрики логируются, но часть прогонов заведена вручную или вне эксперимента"},
                    {"points": 3, "label": "полно", "descriptor": "у каждого прогона есть параметры, метрики и тег версии кода — запуски сравнимы между собой"},
                ],
            },
            {
                "key": "runs_count",
                "title": "Не менее 20 запусков",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "меньше 10 запусков"},
                    {"points": 1, "label": "частично", "descriptor": "10–19 запусков либо запуски отличаются только сидом"},
                    {"points": 2, "label": "выполнено", "descriptor": "20 и больше запусков с разными гиперпараметрами"},
                ],
            },
            {
                "key": "model_registry",
                "title": "Регистрация лучшей модели",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "модель в Model Registry не зарегистрирована"},
                    {"points": 1, "label": "частично", "descriptor": "модель зарегистрирована, но не видно, по какой метрике она выбрана лучшей"},
                    {"points": 2, "label": "выполнено", "descriptor": "зарегистрирована модель конкретного run_id, выбор обоснован метрикой"},
                ],
            },
            {
                "key": "reproducibility",
                "title": "Воспроизводимость",
                "max_score": 2,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "сид не зафиксирован, версии библиотек не указаны — повторить прогон нельзя"},
                    {"points": 1, "label": "частично", "descriptor": "зафиксировано что-то одно: сид без версий или версии без сида"},
                    {"points": 2, "label": "выполнено", "descriptor": "сид зафиксирован, версии зафиксированы, ноутбук проходит сверху вниз"},
                ],
            },
            {
                "key": "conclusions",
                "title": "Выводы по экспериментам",
                "max_score": 1,
                "levels": [
                    {"points": 0, "label": "нет", "descriptor": "выводов нет или это пересказ таблицы метрик"},
                    {"points": 1, "label": "есть", "descriptor": "сказано, какой фактор на что повлиял, со ссылкой на конкретные прогоны"},
                ],
            },
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
        # Фикстура только там, где ревьюер уже назначен. Работа, ждущая
        # распределения, приходила сюда с готовым «разбором», которого никто
        # не делал: методист её назначал, ревьюер открывал и видел чужой
        # придуманный текст под своей фамилией. Теперь такая работа лежит с
        # `pending`, и разбор по ней запускает назначение — как в проде.
        if state not in (SubmissionStatus.SUBMITTED, SubmissionStatus.PROPOSED):
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
                    questions=demo_blitz_questions(),
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
                payload={"route": "/methodist/performance"},
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
    seed_history(db)
