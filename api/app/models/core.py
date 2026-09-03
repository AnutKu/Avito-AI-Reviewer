"""Core-схема кабинета.

Владелец — кабинет. Фичи (AI-ревью, конструктор критериев, аналитика)
добавляют свои таблицы своими модулями рядом и core не меняют.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now_col(**kw) -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), **kw)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), index=True)
    specialization: Mapped[str | None] = mapped_column(String(64))
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = now_col()


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = pk()
    title: Mapped[str] = mapped_column(String(255))
    specialization: Mapped[str] = mapped_column(String(64), default="data_science")
    tone_of_voice: Mapped[dict] = mapped_column(JSONB, default=dict)
    reviewer_capacity: Mapped[int] = mapped_column(Integer, default=12)
    created_at: Mapped[datetime] = now_col()


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_enrollment"),)

    id: Mapped[uuid.UUID] = pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = pk()
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    statement: Mapped[str] = mapped_column(Text, default="")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    effort_weight: Mapped[float] = mapped_column(Float, default=1.0)
    submission_channel: Mapped[str] = mapped_column(String(32), default="github")
    current_rubric_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = now_col()

    course: Mapped[Course] = relationship()


class RubricVersion(Base):
    """Инвариант: опубликованная версия не редактируется никогда. Правка = новая версия."""

    __tablename__ = "rubric_versions"
    __table_args__ = (UniqueConstraint("assignment_id", "version", name="uq_rubric_version"),)

    id: Mapped[uuid.UUID] = pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    criteria: Mapped[list] = mapped_column(JSONB, default=list)
    max_score: Mapped[float] = mapped_column(Float, default=0.0)
    pass_score: Mapped[float] = mapped_column(Float, default=0.0)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime] = now_col()
    note: Mapped[str] = mapped_column(Text, default="")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[uuid.UUID] = pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    source_url: Mapped[str] = mapped_column(Text)
    submitted_at: Mapped[datetime] = now_col()
    status: Mapped[str] = mapped_column(String(32), index=True)
    is_overdue: Mapped[bool] = mapped_column(Boolean, default=False)

    assignment: Mapped[Assignment] = relationship()
    student: Mapped[User] = relationship()


class Snapshot(Base):
    """Снапшот сохраняется при приёме. Всё ревью работает с ним, повторных походов в GitHub нет."""

    __tablename__ = "snapshots"

    id: Mapped[uuid.UUID] = pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    fetched_at: Mapped[datetime] = now_col()
    parsed_facts: Mapped[dict] = mapped_column(JSONB, default=dict)


class ReviewAssignment(Base):
    __tablename__ = "review_assignments"

    id: Mapped[uuid.UUID] = pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    proposed_by: Mapped[str] = mapped_column(String(32), default="system")
    explanation: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = now_col()

    reviewer: Mapped[User] = relationship(foreign_keys=[reviewer_id])


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )
    rubric_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_versions.id"))
    model: Mapped[str] = mapped_column(String(64), default="pending")
    ai_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    ai_error: Mapped[str | None] = mapped_column(Text)
    raw_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    draft_feedback: Mapped[str] = mapped_column(Text, default="")
    final_score: Mapped[float | None] = mapped_column(Float)
    final_feedback: Mapped[str] = mapped_column(Text, default="")
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_col()

    items: Mapped[list[ReviewItem]] = relationship(
        back_populates="review", cascade="all, delete-orphan", order_by="ReviewItem.position"
    )
    signals: Mapped[list[AiSignal]] = relationship(cascade="all, delete-orphan")


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    criterion_key: Mapped[str] = mapped_column(String(64), index=True)
    criterion_title: Mapped[str] = mapped_column(String(255))
    max_score: Mapped[float] = mapped_column(Float, default=1.0)
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(16), default="partial")
    confidence: Mapped[str] = mapped_column(String(16), default="medium")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")
    reviewer_action: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    final_score: Mapped[float | None] = mapped_column(Float)
    reviewer_comment: Mapped[str] = mapped_column(Text, default="")

    review: Mapped[Review] = relationship(back_populates="items")


class AiSignal(Base):
    __tablename__ = "ai_signals"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    level: Mapped[str] = mapped_column(String(16), default="low")
    summary: Mapped[str] = mapped_column(Text, default="")
    grounds: Mapped[list] = mapped_column(JSONB, default=list)
    limitations: Mapped[str] = mapped_column(Text, default="")
    reviewer_decision: Mapped[str] = mapped_column(String(16), default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BlitzSession(Base):
    __tablename__ = "blitz_sessions"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    answers: Mapped[list] = mapped_column(JSONB, default=list)
    ai_analysis: Mapped[dict] = mapped_column(JSONB, default=dict)
    reviewer_decision: Mapped[str] = mapped_column(String(32), default="pending")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now_col()


class StatusHistory(Base):
    """Из неё считаются время обработки и доля просрочек (M-001, M-004)."""

    __tablename__ = "status_history"

    id: Mapped[uuid.UUID] = pk()
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = now_col(index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = pk()
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    channel: Mapped[str] = mapped_column(String(16), default="in_app")
    sent_at: Mapped[datetime] = now_col()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LlmCall(Base):
    """Честная стоимость обработки берётся отсюда, а не из оценки (NFR-022)."""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("reviews.id", ondelete="CASCADE"))
    stage: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_hash: Mapped[str] = mapped_column(String(64), index=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = now_col()
