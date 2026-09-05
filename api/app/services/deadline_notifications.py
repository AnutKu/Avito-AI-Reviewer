"""Напоминания о сроках работ — студенту и ревьюеру.

Планировщика в кабинете нет: это HTTP-приложение без воркера, и заводить cron
ради двух напоминаний значит завести ещё один процесс, который надо поднимать,
чинить и мониторить. Поэтому напоминания собираются при открытии кабинета —
в тот самый момент, когда их можно прочитать. Плата ровно одна: уведомление
появляется не в секунду наступления порога, а при следующем заходе человека.

Идемпотентность держится на ключе в `payload`: за один порог по одной работе
уведомление создаётся ровно один раз, сколько бы раз страницу ни обновляли.
Решение «что сейчас положено» — чистая функция от срока и состояния работы,
поэтому оно проверяется тестами без базы.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Assignment,
    Enrollment,
    Notification,
    ReviewAssignment,
    Role,
    Submission,
    SubmissionStatus,
    User,
)

# Пороги напоминаний, в часах до срока. Студенту нужно время на саму работу,
# поэтому первое напоминание — за трое суток. Ревьюеру напоминаем за сутки: тем
# же окном, каким очередь красит работу как «риск» (`status.deadline_state`), —
# два разных определения «скоро» на одном экране противоречили бы друг другу.
STUDENT_THRESHOLDS = (72, 24)
REVIEWER_THRESHOLDS = (24,)

THRESHOLD_WORDS = {72: "меньше трёх суток", 48: "меньше двух суток", 24: "меньше суток"}

# Сколько ещё напоминать о пропущенном сроке. Через неделю это уже не
# напоминание, а сводка за курс — её место в списке работ, а не в колокольчике.
MISSED_WINDOW = timedelta(days=7)


@dataclass(frozen=True)
class Notice:
    """Одно напоминание. `key` — то, по чему оно не создастся повторно."""

    key: str
    kind: str
    title: str
    body: str
    route: str


def tightest_threshold(hours_left: float, thresholds: tuple[int, ...]) -> int | None:
    """Самый близкий из сработавших порогов — или None, если не сработал ни один.

    Порог здесь один, а не все подходящие: человек, открывший кабинет за три
    часа до срока, должен получить одно напоминание, а не сразу «за трое суток»
    и «за сутки» — историю, которой для него не было.
    """

    matched = [value for value in thresholds if hours_left <= value]
    return min(matched) if matched else None


def _hours_left(deadline: datetime, now: datetime) -> float:
    return (deadline - now).total_seconds() / 3600


def student_notices(
    *,
    assignment_id: UUID | str,
    title: str,
    deadline: datetime | None,
    now: datetime,
    submitted: bool,
) -> list[Notice]:
    """Что положено студенту по одному заданию.

    Сдал — напоминать не о чем: срок сдачи для этой работы уже ни на что не
    влияет, а проверка идёт по срокам ревьюера.
    """

    if submitted or deadline is None:
        return []
    route = "/student/assignments"
    if now >= deadline:
        if now - deadline > MISSED_WINDOW:
            return []
        return [
            Notice(
                key=f"deadline_missed:{assignment_id}",
                kind="deadline_missed",
                title="Срок сдачи прошёл",
                body=(
                    f"«{title}» — работа не сдана. Сдать ещё можно: такая работа "
                    "помечается как сданная после срока."
                ),
                route=route,
            )
        ]
    threshold = tightest_threshold(_hours_left(deadline, now), STUDENT_THRESHOLDS)
    if threshold is None:
        return []
    return [
        Notice(
            key=f"deadline_soon:{assignment_id}:{threshold}",
            kind="deadline_soon",
            title="Скоро дедлайн",
            body=f"«{title}» — до срока сдачи {THRESHOLD_WORDS[threshold]}, работа не сдана",
            route=route,
        )
    ]


def reviewer_notices(
    *,
    submission_id: UUID | str,
    title: str,
    student: str,
    deadline: datetime | None,
    now: datetime,
    completed: bool,
) -> list[Notice]:
    """Что положено ревьюеру по одной работе из его очереди."""

    if completed or deadline is None:
        return []
    route = "/reviewer/queue"
    if now >= deadline:
        if now - deadline > MISSED_WINDOW:
            return []
        return [
            Notice(
                key=f"review_overdue:{submission_id}",
                kind="review_overdue",
                title="Срок проверки вышел",
                body=f"{student} · «{title}» — работа всё ещё не проверена",
                route=route,
            )
        ]
    threshold = tightest_threshold(_hours_left(deadline, now), REVIEWER_THRESHOLDS)
    if threshold is None:
        return []
    return [
        Notice(
            key=f"review_deadline:{submission_id}:{threshold}",
            kind="review_deadline",
            title="Скоро срок проверки",
            body=f"{student} · «{title}» — до срока {THRESHOLD_WORDS[threshold]}",
            route=route,
        )
    ]


def _for_student(db: Session, user: User, now: datetime) -> list[Notice]:
    rows = db.execute(
        select(Assignment, Submission.id)
        .join(Enrollment, Enrollment.course_id == Assignment.course_id)
        .outerjoin(
            Submission,
            (Submission.assignment_id == Assignment.id) & (Submission.student_id == user.id),
        )
        .where(
            Enrollment.user_id == user.id,
            Assignment.published_at.is_not(None),
            Assignment.deadline_at.is_not(None),
        )
    ).all()
    notices: list[Notice] = []
    for assignment, submission_id in rows:
        notices += student_notices(
            assignment_id=assignment.id,
            title=assignment.title,
            deadline=assignment.deadline_at,
            now=now,
            submitted=submission_id is not None,
        )
    return notices


def _for_reviewer(db: Session, user: User, now: datetime) -> list[Notice]:
    rows = db.scalars(
        select(Submission)
        .join(ReviewAssignment, ReviewAssignment.submission_id == Submission.id)
        .where(
            ReviewAssignment.reviewer_id == user.id,
            ReviewAssignment.is_active.is_(True),
            Submission.status != SubmissionStatus.COMPLETED,
        )
    )
    notices: list[Notice] = []
    for submission in rows:
        notices += reviewer_notices(
            submission_id=submission.id,
            title=submission.assignment.title,
            student=submission.student.full_name,
            deadline=submission.assignment.deadline_at,
            now=now,
            completed=submission.status == SubmissionStatus.COMPLETED,
        )
    return notices


def sync_deadline_notifications(db: Session, user: User) -> int:
    """Дописать недостающие напоминания этому человеку. Возвращает, сколько создано."""

    now = datetime.now(UTC)
    if user.role == Role.STUDENT:
        notices = _for_student(db, user, now)
    elif user.role == Role.REVIEWER:
        notices = _for_reviewer(db, user, now)
    else:
        return 0
    if not notices:
        return 0

    known = set(
        db.scalars(
            select(Notification.payload["key"].astext).where(
                Notification.recipient_id == user.id,
                Notification.payload["key"].astext.in_([notice.key for notice in notices]),
            )
        )
    )
    fresh = [notice for notice in notices if notice.key not in known]
    for notice in fresh:
        db.add(
            Notification(
                recipient_id=user.id,
                kind=notice.kind,
                title=notice.title,
                body=notice.body,
                payload={"key": notice.key, "route": notice.route},
            )
        )
    if fresh:
        db.commit()
    return len(fresh)
