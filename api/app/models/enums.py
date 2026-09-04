from enum import StrEnum


class Role(StrEnum):
    STUDENT = "student"
    REVIEWER = "reviewer"
    METHODIST = "methodist"


class SubmissionStatus(StrEnum):
    """Автомат работы. `completed` — терминальный: цикл доработки в MVP свёрнут."""

    SUBMITTED = "submitted"
    PROPOSED = "proposed"
    ASSIGNED = "assigned"
    IN_REVIEW = "in_review"
    BLITZ_SENT = "blitz_sent"
    BLITZ_ANSWERED = "blitz_answered"
    COMPLETED = "completed"


SUBMISSION_FLOW: dict[str, list[str]] = {
    SubmissionStatus.SUBMITTED: [SubmissionStatus.PROPOSED],
    SubmissionStatus.PROPOSED: [SubmissionStatus.ASSIGNED, SubmissionStatus.PROPOSED],
    SubmissionStatus.ASSIGNED: [SubmissionStatus.IN_REVIEW, SubmissionStatus.ASSIGNED],
    SubmissionStatus.IN_REVIEW: [
        SubmissionStatus.BLITZ_SENT,
        SubmissionStatus.COMPLETED,
        SubmissionStatus.ASSIGNED,
    ],
    SubmissionStatus.BLITZ_SENT: [SubmissionStatus.BLITZ_ANSWERED, SubmissionStatus.IN_REVIEW],
    SubmissionStatus.BLITZ_ANSWERED: [SubmissionStatus.COMPLETED, SubmissionStatus.IN_REVIEW],
    SubmissionStatus.COMPLETED: [],
}

SUBMISSION_STATUS_TITLES: dict[str, str] = {
    SubmissionStatus.SUBMITTED: "Принята",
    SubmissionStatus.PROPOSED: "Ждёт распределения",
    SubmissionStatus.ASSIGNED: "Назначена ревьюеру",
    SubmissionStatus.IN_REVIEW: "На проверке",
    SubmissionStatus.BLITZ_SENT: "Ожидает ответа студента",
    SubmissionStatus.BLITZ_ANSWERED: "Ответ получен",
    SubmissionStatus.COMPLETED: "Проверена",
}


class AiStatus(StrEnum):
    """Автомат AI-прогона. Стартует при приёме работы, независимо от назначения."""

    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    FAILED = "failed"


class Confidence(StrEnum):
    """Три градации с описанной шкалой — не проценты (FR-041)."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


CONFIDENCE_TITLES: dict[str, str] = {
    Confidence.HIGH: "Высокая — вывод опирается на детерминированный факт из ноутбука",
    Confidence.MEDIUM: "Средняя — вывод опирается на текст решения, требует взгляда ревьюера",
    Confidence.LOW: "Низкая — признаки противоречивы, решение за ревьюером",
}


class Verdict(StrEnum):
    PASSED = "passed"
    PARTIAL = "partial"
    FAILED = "failed"


class ReviewerAction(StrEnum):
    """Единственный источник данных для аналитики правок."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    CHANGED = "changed"
    REJECTED = "rejected"


class SignalKind(StrEnum):
    AI_USE = "ai_use"
    UNDERSTANDING_RISK = "understanding_risk"


class SignalDecision(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    BLITZ = "blitz"


class DetectionCategory(StrEnum):
    """Характер использования AI, а не факт нарушения (FR-046).

    Инструментальное использование курсом разрешено: `TOOL_ASSISTED` не повод
    ни для чего, кроме внимания.
    """

    NO_SIGNS = "no_signs"
    TOOL_ASSISTED = "tool_assisted"
    LIKELY_GENERATED = "likely_generated"


class FraudVerdict(StrEnum):
    """Решение человека. Балл не меняет — для этого есть решения по критериям."""

    NO_SIGNS = "no_signs"
    TOOL_ASSISTED = "tool_assisted"
    MISCONDUCT = "misconduct"
    INCONCLUSIVE = "inconclusive"


class BlitzStatus(StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    ANSWERED = "answered"
    EXPIRED = "expired"
    CLOSED = "closed"


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    TELEGRAM = "telegram"
