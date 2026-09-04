"""Срок проверки в очереди ревьюера зависит только от срока.

Раньше признак примешивал две посторонние вещи: статус работы (риск считался
только для `assigned`/`proposed`, и работа переставала быть красной, стоило
ревьюеру её открыть) и опоздание студента. В итоге две работы одного задания
с одним и тем же дедлайном подсвечивались по-разному. БД тестам не нужна.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models import SubmissionStatus
from app.services.status import deadline_state

# Все статусы, при которых работа ещё на руках у ревьюера.
OPEN_STATUSES = (
    SubmissionStatus.PROPOSED,
    SubmissionStatus.ASSIGNED,
    SubmissionStatus.IN_REVIEW,
    SubmissionStatus.BLITZ_SENT,
    SubmissionStatus.BLITZ_ANSWERED,
)


def work(status, *, hours_left=None, is_overdue=False):
    deadline = None if hours_left is None else datetime.now(UTC) + timedelta(hours=hours_left)
    return SimpleNamespace(
        status=status,
        is_overdue=is_overdue,
        assignment=SimpleNamespace(deadline_at=deadline),
    )


def test_one_deadline_gives_one_state_whatever_the_status():
    states = {deadline_state(work(s, hours_left=5)) for s in OPEN_STATUSES}
    assert states == {"risk"}, "срок един — признак тоже, статус на него не влияет"


def test_passed_deadline_reads_as_overdue_for_every_open_status():
    states = {deadline_state(work(s, hours_left=-1)) for s in OPEN_STATUSES}
    assert states == {"overdue"}


def test_far_deadline_stays_quiet():
    assert deadline_state(work(SubmissionStatus.ASSIGNED, hours_left=72)) is None


def test_exactly_24_hours_out_is_already_a_risk():
    assert deadline_state(work(SubmissionStatus.IN_REVIEW, hours_left=23.9)) == "risk"


def test_completed_work_is_never_flagged():
    assert deadline_state(work(SubmissionStatus.COMPLETED, hours_left=-10)) is None


def test_work_without_a_deadline_is_never_flagged():
    assert deadline_state(work(SubmissionStatus.ASSIGNED)) is None


def test_student_lateness_does_not_colour_the_review_deadline():
    late = work(SubmissionStatus.ASSIGNED, hours_left=72, is_overdue=True)
    assert deadline_state(late) is None, "опоздание студента — отдельный факт"
