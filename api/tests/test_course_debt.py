"""Образовательный долг: что считается сигналом, а что — шумом.

Главное, что здесь проверяется, — не формулы, а сдержанность. Долг курса легко
превратить в генератор уверенных выводов из трёх наблюдений, и такой экран хуже
пустого: он выглядит убедительно и врёт. Поэтому почти каждый тест — про то,
где система обязана промолчать и сказать, чего ей не хватило.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.services.analytics import ItemFact, WorkFact
from app.services.course_debt import (
    FAIL_SHARE,
    MIN_REVIEWS_PER_CRITERION,
    MIN_WORKS_PER_TOPIC,
    TaskFact,
    build_debt,
    manual_corrections,
    question_hotspots,
    repeated_errors,
    stale_tasks,
    topic_gaps,
)

NOW = datetime(2026, 9, 5, tzinfo=UTC)
TASK_A, TASK_B = uuid4(), uuid4()


def task(task_id=TASK_A, *, title="Кейс", topic="Аналитика", works=10, **kw):
    return TaskFact(
        id=task_id,
        title=title,
        topic=topic,
        published_at=NOW - timedelta(days=30),
        rubric_updated_at=kw.pop("rubric_updated_at", NOW - timedelta(days=10)),
        works=works,
        **kw,
    )


def work(assignment_id=TASK_A, *, score, pass_score=6.0, max_score=10.0):
    return WorkFact(
        submission_id=uuid4(), assignment_id=assignment_id, student_id=uuid4(),
        status="completed", is_overdue=False, submitted_at=NOW, assigned_at=NOW,
        completed_at=NOW, final_score=score, max_score=max_score, pass_score=pass_score,
        ai_status="ready",
    )


def item(assignment_id=TASK_A, *, key="metrics", final, action="accepted", max_score=4.0):
    return ItemFact(
        criterion_key=key, criterion_title="Метрики", max_score=max_score, ai_score=final,
        final_score=final, action=action, assignment_id=assignment_id,
    )


# --- темы -------------------------------------------------------------------


def test_a_topic_everyone_fails_is_reported():
    works = [work(score=3.0) for _ in range(6)] + [work(score=8.0)]
    rows, _ = topic_gaps(works, {TASK_A: task()})
    assert len(rows) == 1
    assert rows[0]["kind"] == "topic" and rows[0]["metric"] == 86
    assert "6 из 7" in rows[0]["evidence"]


def test_a_topic_with_too_few_works_stays_silent():
    """Две неудачи — это не «массово», это вторник."""

    works = [work(score=3.0) for _ in range(MIN_WORKS_PER_TOPIC - 1)]
    rows, notes = topic_gaps(works, {TASK_A: task()})
    assert rows == []
    assert any("для вывода о теме мало" in note for note in notes)


def test_unfinished_work_says_nothing_about_understanding():
    works = [work(score=None) for _ in range(20)]
    rows, notes = topic_gaps(works, {TASK_A: task()})
    assert rows == [] and notes == [], "непроверенные работы просто не участвуют"


def test_tasks_without_a_topic_are_counted_out_loud():
    works = [work(score=3.0) for _ in range(6)]
    rows, notes = topic_gaps(works, {TASK_A: task(topic="")})
    assert rows == []
    assert any("не указана тема" in note for note in notes)


def test_a_healthy_topic_is_not_a_debt():
    works = [work(score=9.0) for _ in range(8)]
    assert topic_gaps(works, {TASK_A: task()})[0] == []


# --- повторяющиеся ошибки ---------------------------------------------------


def test_a_criterion_most_students_fail_is_a_repeated_error():
    items = [item(final=1.0) for _ in range(6)] + [item(final=4.0) for _ in range(2)]
    rows, _ = repeated_errors(items, {TASK_A: task()})
    assert len(rows) == 1 and rows[0]["kind"] == "repeated_error"
    assert rows[0]["metric"] == 75


def test_half_the_maximum_is_the_line_not_zero():
    """Ноль ставят редко; «меньше половины» — уже провал, а не придирка."""

    items = [item(final=2.0, max_score=4.0) for _ in range(8)]
    assert repeated_errors(items, {TASK_A: task()})[0] == [], "ровно половина — ещё не провал"
    items = [item(final=1.9, max_score=4.0) for _ in range(8)]
    assert repeated_errors(items, {TASK_A: task()})[0] != []


def test_a_rarely_reviewed_criterion_is_counted_out_not_reported():
    items = [item(final=0.0) for _ in range(MIN_REVIEWS_PER_CRITERION - 1)]
    rows, notes = repeated_errors(items, {TASK_A: task()})
    assert rows == []
    assert any("не считали" in note for note in notes)


def test_errors_are_grouped_per_task_not_across_the_course():
    """Один и тот же критерий в двух заданиях — два разных сигнала."""

    items = [item(TASK_A, final=0.0) for _ in range(5)] + [item(TASK_B, final=4.0) for _ in range(5)]
    rows, _ = repeated_errors(items, {TASK_A: task(), TASK_B: task(TASK_B, title="Второе")})
    assert len(rows) == 1
    assert rows[0]["target"]["assignment_id"] == str(TASK_A)


# --- ручные правки ----------------------------------------------------------


def test_a_criterion_reviewers_keep_rewriting_is_reported():
    items = [item(final=2.0, action="changed") for _ in range(5)] + [
        item(final=4.0, action="accepted") for _ in range(3)
    ]
    rows, _ = manual_corrections(items, {TASK_A: task()})
    assert len(rows) == 1 and rows[0]["kind"] == "criterion_corrections"
    assert "5 правок из 8" in rows[0]["evidence"]


def test_undecided_rows_are_not_evidence_of_anything():
    """Пока ревьюер не принял решение, правки не было — и статистики тоже."""

    items = [item(final=None, action="pending") for _ in range(20)]
    assert manual_corrections(items, {TASK_A: task()})[0] == []


def test_agreement_is_not_a_debt():
    items = [item(final=4.0, action="accepted") for _ in range(10)]
    assert manual_corrections(items, {TASK_A: task()})[0] == []


# --- вопросы после задания --------------------------------------------------


def test_a_task_that_needs_follow_up_questions_is_flagged():
    rows, _ = question_hotspots({TASK_A: task(works=10, questioned=5)})
    assert len(rows) == 1 and rows[0]["kind"] == "questions"
    assert "доп. вопросы по 5 работам" in rows[0]["evidence"]


def test_understanding_risk_counts_too():
    rows, _ = question_hotspots({TASK_A: task(works=10, risk_flagged=4)})
    assert len(rows) == 1 and "риск непонимания у 4" in rows[0]["evidence"]


def test_the_two_question_signals_are_not_summed():
    """Одна работа могла и получить блиц, и словить риск — это одна работа."""

    rows, _ = question_hotspots({TASK_A: task(works=10, questioned=4, risk_flagged=4)})
    assert rows[0]["metric"] == 40, "берётся большее, а не сумма"


def test_a_task_with_few_works_is_not_judged():
    rows, notes = question_hotspots({TASK_A: task(works=3, questioned=3)})
    assert rows == [] and any("не считали" in note for note in notes)


# --- пора пересмотреть ------------------------------------------------------


def test_an_untouched_rubric_with_live_work_is_a_reason():
    tasks = {TASK_A: task(rubric_updated_at=NOW - timedelta(days=200), works=5)}
    rows, _ = stale_tasks(tasks, [], NOW)
    assert len(rows) == 1 and "не меняли 200 дней" in rows[0]["detail"]


def test_an_old_task_nobody_submits_is_not_a_debt():
    """Старое, но неиспользуемое задание никого не портит — молчим."""

    tasks = {TASK_A: task(rubric_updated_at=NOW - timedelta(days=400), works=0)}
    assert stale_tasks(tasks, [], NOW)[0] == []


def test_open_critical_findings_are_a_reason():
    rows, _ = stale_tasks({TASK_A: task(open_findings=2)}, [], NOW)
    assert len(rows) == 1 and "критичных замечаний прогона: 2" in rows[0]["detail"]


def test_a_criterion_that_gives_everyone_the_same_score_stopped_measuring():
    items = [item(final=4.0) for _ in range(6)]
    rows, _ = stale_tasks({TASK_A: task()}, items, NOW)
    assert len(rows) == 1 and "не различают работы" in rows[0]["detail"]


def test_one_identical_score_out_of_two_reviews_proves_nothing():
    items = [item(final=4.0) for _ in range(MIN_REVIEWS_PER_CRITERION - 1)]
    assert stale_tasks({TASK_A: task()}, items, NOW)[0] == []


def test_several_reasons_raise_the_severity():
    tasks = {TASK_A: task(rubric_updated_at=NOW - timedelta(days=300), works=5, open_findings=1)}
    rows, _ = stale_tasks(tasks, [], NOW)
    assert rows[0]["severity"] == "important"
    single, _ = stale_tasks({TASK_A: task(open_findings=1)}, [], NOW)
    assert single[0]["severity"] == "watch"


# --- сборка -----------------------------------------------------------------


def test_the_worst_debt_comes_first():
    works = [work(score=1.0) for _ in range(8)]
    items = [item(final=0.0, action="changed") for _ in range(8)]
    report = build_debt(works, items, {TASK_A: task(works=8, questioned=6)}, NOW)
    severities = [row["severity"] for row in report["items"]]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "important": 1, "watch": 2}[s])
    assert report["counts"]["critical"] >= 1


def test_an_empty_course_says_so_instead_of_showing_no_debt():
    """Пустой экран читается как «всё хорошо». Это разные вещи."""

    report = build_debt([], [], {}, NOW)
    assert report["items"] == []
    assert report["coverage"]["enough"] is False


def test_coverage_reports_what_was_actually_counted():
    works = [work(score=9.0) for _ in range(6)] + [work(score=None)]
    report = build_debt(works, [], {TASK_A: task()}, NOW)
    assert report["coverage"] == {"works": 7, "graded": 6, "tasks": 1, "enough": True}


def test_every_debt_item_says_what_to_do_about_it():
    works = [work(score=1.0) for _ in range(8)]
    report = build_debt(works, [], {TASK_A: task(works=8)}, NOW)
    for row in report["items"]:
        assert row["action"] and row["evidence"], "вывод без основания и без действия бесполезен"


def test_a_healthy_course_produces_no_debt_but_keeps_coverage():
    works = [work(score=9.0) for _ in range(10)]
    items = [item(final=4.0, action="accepted") for _ in range(10)]
    # Разные баллы, иначе критерий справедливо сочтут неразличающим.
    items[0] = item(final=1.0, action="accepted")
    report = build_debt(works, items, {TASK_A: task(works=10)}, NOW)
    assert report["items"] == []
    assert report["coverage"]["enough"] is True


def test_the_fail_threshold_is_a_shared_constant_not_a_magic_number():
    assert 0 < FAIL_SHARE < 100
