"""Аналитика: юнит-тесты формул + интеграционные проверки эндпоинтов.

Ядро в `services/analytics.py` — чистые функции над фактами, поэтому формулы
проверяются без БД. Эндпоинты (`/methodist/analytics`, `/methodist/performance`)
требуют `TEST_DATABASE_URL`, иначе помечаются skipped.
"""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models import ReviewerAction, SubmissionStatus
from app.services.analytics import (
    AssignmentRef,
    ItemFact,
    StudentRef,
    WorkFact,
    agreement,
    criteria_report,
    funnel,
    overview,
    performance,
    reviewer_report,
    week_start,
    weekly,
)

NOW = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
STUDENT = uuid4()
ASSIGNMENT = uuid4()


def work(**kwargs) -> WorkFact:
    base = {
        "submission_id": uuid4(),
        "assignment_id": ASSIGNMENT,
        "student_id": STUDENT,
        "status": SubmissionStatus.COMPLETED,
        "is_overdue": False,
        "submitted_at": NOW - timedelta(hours=48),
        "assigned_at": NOW - timedelta(hours=40),
        "completed_at": NOW - timedelta(hours=24),
        "final_score": 8.0,
        "max_score": 10.0,
        "pass_score": 6.0,
        "ai_status": "ready",
    }
    base.update(kwargs)
    return WorkFact(**base)


def item(**kwargs) -> ItemFact:
    base = {
        "criterion_key": "quality",
        "criterion_title": "Качество решения",
        "max_score": 3.0,
        "ai_score": 2.0,
        "final_score": 2.0,
        "action": ReviewerAction.ACCEPTED,
        "reviewer_id": None,
        "completed_at": NOW - timedelta(hours=24),
    }
    base.update(kwargs)
    return ItemFact(**base)


# --------------------------------------------------------------------------- #
# Время и производные
# --------------------------------------------------------------------------- #


def test_lead_and_review_hours_are_measured_from_real_timestamps():
    row = work()
    assert row.lead_hours == 24.0     # сдал 48 ч назад, результат 24 ч назад
    assert row.review_hours == 16.0   # назначено 40 ч назад


def test_unfinished_work_has_no_durations():
    row = work(status=SubmissionStatus.IN_REVIEW, completed_at=None, final_score=None)
    assert row.lead_hours is None
    assert row.review_hours is None
    assert row.passed is None
    assert row.percent is None


def test_pass_uses_rubric_threshold():
    assert work(final_score=6.0).passed is True     # порог ровно 6 — зачёт
    assert work(final_score=5.9).passed is False
    assert work(final_score=7.5).percent == 75.0


# --------------------------------------------------------------------------- #
# Согласие AI и ревьюера
# --------------------------------------------------------------------------- #


def test_agreement_counts_only_decided_items():
    items = [
        item(action=ReviewerAction.ACCEPTED),
        item(action=ReviewerAction.ACCEPTED),
        item(action=ReviewerAction.CHANGED, final_score=1.0),
        item(action=ReviewerAction.REJECTED, final_score=None),
        item(action=ReviewerAction.PENDING),  # ревьюер ещё не решил — в статистику не идёт
    ]
    result = agreement(items)
    assert result["decided"] == 4
    assert result["accepted"] == 2
    assert result["changed"] == 1
    assert result["rejected"] == 1
    assert result["rate"] == 50.0


def test_agreement_delta_shows_direction_of_corrections():
    result = agreement(
        [item(ai_score=2.0, final_score=1.0, action=ReviewerAction.CHANGED)]
    )
    assert result["delta"] == -1.0  # ревьюер снизил оценку AI


def test_agreement_on_empty_input_does_not_divide_by_zero():
    assert agreement([])["rate"] == 0.0
    assert agreement([])["delta"] is None


# --------------------------------------------------------------------------- #
# Обзор и воронка
# --------------------------------------------------------------------------- #


def test_overview_counts_stages_and_rates():
    works = [
        work(final_score=8.0),
        work(final_score=4.0),
        work(status=SubmissionStatus.IN_REVIEW, completed_at=None, final_score=None),
        work(status=SubmissionStatus.PROPOSED, completed_at=None, final_score=None),
        work(status=SubmissionStatus.SUBMITTED, completed_at=None, final_score=None, is_overdue=True),
    ]
    result = overview(works, [], expected=10, students=5, assignments=2, now=NOW)
    assert result["submitted"] == 5
    assert result["completed"] == 2
    assert result["in_progress"] == 1      # только in_review
    assert result["waiting"] == 2          # submitted + proposed
    assert result["not_submitted"] == 5
    assert result["overdue"] == 1
    assert result["submission_rate"] == 50.0
    assert result["avg_score"] == 6.0
    assert result["pass_rate"] == 50.0     # 8 из 10 — зачёт, 4 — нет


def test_overview_week_over_week_delta_is_real():
    works = [
        work(completed_at=NOW - timedelta(days=1)),
        work(completed_at=NOW - timedelta(days=3)),
        work(completed_at=NOW - timedelta(days=9)),   # прошлая неделя
    ]
    result = overview(works, [], expected=3, students=3, assignments=1, now=NOW)
    assert result["completed_7d"] == 2
    assert result["completed_prev_7d"] == 1
    assert result["completed_delta"] == 1


def test_funnel_keeps_every_stage_in_flow_order():
    rows = funnel([work(), work(status=SubmissionStatus.ASSIGNED)])
    assert [row["status"] for row in rows] == list(SubmissionStatus)
    counts = {row["status"]: row["count"] for row in rows}
    assert counts[SubmissionStatus.COMPLETED] == 1
    assert counts[SubmissionStatus.BLITZ_SENT] == 0
    assert counts[SubmissionStatus.ASSIGNED] == 1


# --------------------------------------------------------------------------- #
# Динамика по неделям
# --------------------------------------------------------------------------- #


def test_weekly_keeps_empty_weeks_so_the_chart_does_not_lie():
    rows = weekly([work()], [], now=NOW, weeks=4)
    assert len(rows) == 4
    assert rows[-1]["completed"] == 1
    assert [row["completed"] for row in rows[:-1]] == [0, 0, 0]
    assert rows[0]["avg_lead_hours"] is None
    assert rows[0]["agreement"] is None


def test_weekly_buckets_by_completion_week():
    old = NOW - timedelta(days=14)
    rows = weekly(
        [work(submitted_at=old - timedelta(hours=10), completed_at=old)],
        [item(completed_at=old, action=ReviewerAction.CHANGED, final_score=1.0)],
        now=NOW,
        weeks=4,
    )
    by_week = {row["week_start"]: row for row in rows}
    bucket = by_week[week_start(old).isoformat()]
    assert bucket["completed"] == 1
    assert bucket["agreement"] == 0.0     # единственное решение — правка
    assert bucket["avg_lead_hours"] == 10.0


def test_weekly_ignores_facts_outside_the_window():
    ancient = NOW - timedelta(days=200)
    rows = weekly([work(submitted_at=ancient, completed_at=ancient)], [], now=NOW, weeks=4)
    assert sum(row["completed"] for row in rows) == 0


# --------------------------------------------------------------------------- #
# Критерии и ревьюеры
# --------------------------------------------------------------------------- #


def test_criteria_report_ranks_by_correction_rate():
    items = [
        item(criterion_key="a", criterion_title="Спорный", action=ReviewerAction.CHANGED, final_score=1.0),
        item(criterion_key="a", criterion_title="Спорный", action=ReviewerAction.REJECTED, final_score=None),
        item(criterion_key="b", criterion_title="Ясный", action=ReviewerAction.ACCEPTED),
        item(criterion_key="b", criterion_title="Ясный", action=ReviewerAction.ACCEPTED),
    ]
    rows = criteria_report(items)
    assert [row["key"] for row in rows] == ["a", "b"]
    assert rows[0]["correction_rate"] == 100.0
    assert rows[0]["reviews"] == 2
    assert rows[1]["correction_rate"] == 0.0


def test_criteria_report_skips_undecided_items():
    assert criteria_report([item(action=ReviewerAction.PENDING)]) == []


def test_reviewer_report_attributes_work_to_who_completed_it():
    finisher, holder = uuid4(), uuid4()
    works = [work(reviewer_id=holder, completed_by=finisher)]
    loads = [
        {"id": str(finisher), "name": "Финишер", "load": 1.0, "capacity": 12.0},
        {"id": str(holder), "name": "Держатель", "load": 3.0, "capacity": 12.0},
    ]
    rows = {row["name"]: row for row in reviewer_report(works, [], loads)}
    assert rows["Финишер"]["completed"] == 1
    assert rows["Держатель"]["completed"] == 0
    assert rows["Финишер"]["avg_review_hours"] == 16.0
    assert rows["Финишер"]["load"] == 1.0   # поля нагрузки не потерялись


# --------------------------------------------------------------------------- #
# Успеваемость
# --------------------------------------------------------------------------- #


def _matrix():
    first, second = uuid4(), uuid4()
    alice, bob = StudentRef(uuid4(), "Алиса"), StudentRef(uuid4(), "Борис")
    columns = [
        AssignmentRef(first, "ДЗ-1", 10.0, 6.0, None),
        AssignmentRef(second, "ДЗ-2", 10.0, 6.0, None),
    ]
    works = [
        work(student_id=alice.id, assignment_id=first, final_score=9.0),
        work(student_id=alice.id, assignment_id=second, final_score=5.0),
        work(student_id=bob.id, assignment_id=first, final_score=7.0, is_overdue=True),
        # ДЗ-2 Борис не сдавал
    ]
    return performance([alice, bob], columns, works)


def test_performance_matrix_marks_missing_work():
    report = _matrix()
    boris = next(row for row in report["rows"] if row["student"] == "Борис")
    assert boris["cells"][1]["status"] == "not_submitted"
    assert boris["cells"][1]["score"] is None
    assert boris["totals"]["submitted"] == 1
    assert boris["totals"]["overdue"] == 1


def test_performance_totals_per_student():
    report = _matrix()
    alice = next(row for row in report["rows"] if row["student"] == "Алиса")
    assert alice["totals"]["avg_score"] == 7.0
    assert alice["totals"]["avg_percent"] == 70.0
    assert alice["totals"]["passed"] == 1     # 9 — зачёт, 5 — нет
    assert alice["totals"]["failed"] == 1


def test_performance_column_and_summary_stats():
    report = _matrix()
    first, second = report["assignments"]
    assert first["stats"]["submitted"] == 2
    assert first["stats"]["pass_rate"] == 100.0
    assert second["stats"]["submitted"] == 1
    summary = report["summary"]
    assert summary["expected"] == 4
    assert summary["submitted"] == 3
    assert summary["not_submitted"] == 1
    assert summary["submission_rate"] == 75.0


def test_performance_rows_are_sorted_by_name():
    report = _matrix()
    assert [row["student"] for row in report["rows"]] == ["Алиса", "Борис"]


# --------------------------------------------------------------------------- #
# Эндпоинты
# --------------------------------------------------------------------------- #


def test_analytics_endpoint_returns_live_numbers(methodist):
    body = methodist.get("/api/methodist/analytics").json()
    assert body["overview"]["submitted"] == body["live_records"]
    assert body["overview"]["submitted"] > 0
    assert len(body["funnel"]) == len(list(SubmissionStatus))
    assert body["reviewers"] and "completed" in body["reviewers"][0]
    assert body["quality"]["weekly"]
    assert body["quality"]["agreement"]["decided"] > 0


def test_analytics_numbers_agree_with_registry(methodist):
    body = methodist.get("/api/methodist/analytics").json()
    groups = methodist.get("/api/methodist/submissions").json()
    submitted = sum(group["stats"]["submitted"] for group in groups)
    assert body["overview"]["submitted"] == submitted
    assert body["overview"]["expected"] == sum(group["stats"]["students"] for group in groups)


def test_performance_endpoint_covers_every_student_and_assignment(methodist):
    body = methodist.get("/api/methodist/performance").json()
    assignments = methodist.get("/api/methodist/assignments").json()
    published = [row for row in assignments if row["published"]]
    assert len(body["assignments"]) == len(published)
    assert len(body["rows"]) == body["summary"]["students"]
    for row in body["rows"]:
        assert len(row["cells"]) == len(body["assignments"])


def test_performance_hides_draft_assignments(methodist):
    created = methodist.post(
        "/api/methodist/assignments",
        json={"title": "Черновик для аналитики", "criteria": [{"title": "Критерий", "max_score": 5}]},
    ).json()
    before = methodist.get("/api/methodist/performance").json()
    assert all(column["id"] != created["id"] for column in before["assignments"])

    methodist.post(f"/api/methodist/assignments/{created['id']}/publish", json={"published": True})
    after = methodist.get("/api/methodist/performance").json()
    column = next(item for item in after["assignments"] if item["id"] == created["id"])
    assert column["stats"]["submitted"] == 0
    assert all(row["cells"][-1]["status"] == "not_submitted" for row in after["rows"])


def test_analytics_is_methodist_only(reviewer):
    assert reviewer.get("/api/methodist/analytics").status_code == 403
    assert reviewer.get("/api/methodist/performance").status_code == 403
