"""Проверка задания на AI-персонах и рекомендации по его доработке.

Фича живёт своими таблицами рядом с core и core не меняет — кроме одной
колонки `assignments.authoring`, где хранятся блоки задания, которых нет в
доменной схеме кабинета (цель, ожидаемый результат, ограничения, эталон).

Три состояния разведены по трём местам намеренно (§18 ТЗ). Публикация задания
живёт в `assignments.published_at`, состояние прогона — в `AiRun.status`,
состояние каждой рекомендации — в `AiRecommendation.status`. Одно поле на всё
дало бы нерепрезентируемые пары вроде «опубликовано и генерируется».
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .core import Base, now_col, pk


class AiRun(Base):
    """Один прогон одного типа персон по одной ревизии задания.

    `revision` — номер версии рубрики на момент запуска. Он и делает результат
    честным: задание правят дальше, а прогон навсегда остаётся про ту версию,
    которую действительно проверяли.
    """

    __tablename__ = "ai_task_runs"

    id: Mapped[uuid.UUID] = pk()
    assignment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assignments.id", ondelete="CASCADE"), index=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    persona_type: Mapped[str] = mapped_column(String(16))  # student | reviewer
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[str] = mapped_column(Text, default="")
    # Ключ идемпотентности присылает клиент: двойной клик по «Запустить» не
    # должен порождать два прогона одного и того же запроса.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), index=True)
    external_task_id: Mapped[str | None] = mapped_column(String(64))
    external_run_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    personas: Mapped[list] = mapped_column(JSONB, default=list)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = now_col()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    recommendations: Mapped[list[AiRecommendation]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AiRecommendation.position",
    )


class AiRecommendation(Base):
    """Предложение изменить один блок задания или один критерий.

    Хранит и то, что предложил агент (`proposed_value`), и то, что в итоге
    вставил человек (`final_value`) — иначе нельзя отличить принятую правку от
    переписанной и незачем разделять статусы `applied` и `edited`.
    """

    __tablename__ = "ai_task_recommendations"

    id: Mapped[uuid.UUID] = pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ai_task_runs.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    target_type: Mapped[str] = mapped_column(String(16))  # task_field | criterion
    target_id: Mapped[str | None] = mapped_column(String(64))  # ключ критерия
    target_field: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(16), default="improvement")
    problem: Mapped[str] = mapped_column(Text, default="")
    evidence: Mapped[list] = mapped_column(JSONB, default=list)
    original_value: Mapped[str] = mapped_column(Text, default="")
    proposed_value: Mapped[str] = mapped_column(Text, default="")
    final_value: Mapped[str | None] = mapped_column(Text)
    expected_effect: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Полная правка критерия из движка: применять её нужно целиком (пороги,
    # признаки, вес), а не одним текстовым полем.
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[AiRun] = relationship(back_populates="recommendations")
