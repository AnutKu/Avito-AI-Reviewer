"""Таблицы модуля детекции и блиц-опроса.

Отдельным модулем рядом с core: кабинет про них не знает, фича добавляет своё
и core-схему не меняет.

Новые таблицы `create_all` создаёт нормально — в отличие от новых колонок в уже
существующих таблицах, для которых в проекте нет ни Alembic, ни ALTER.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .core import Base, now_col, pk


class AiDetection(Base):
    """Один прогон детектора.

    Append-only: перезапуск создаёт новую строку, старая остаётся, потому что на
    неё мог опираться вердикт ревьюера.
    """

    __tablename__ = "ai_detections"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    # Индекс признаков 0–100, а не вероятность: считает services/detection_scale.py.
    score: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(16))
    # None при confidence=low — делить нечего.
    category: Mapped[str | None] = mapped_column(String(32))
    contributions: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    limitations: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(64), default="pending")
    error: Mapped[str | None] = mapped_column(Text)
    raw_result: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = now_col()


class BlitzEvent(Base):
    """Одно наблюдение с устройства студента во время ответа на блиц.

    Что здесь есть и чего нет — решение, а не недоделка:

    * `offset_ms` — смещение от открытия формы, а не абсолютное время. Часы на
      устройстве студента нам не подчиняются, а длительности от их сдвига не
      зависят. Сверка с сервером идёт по одному числу — общей длительности.
    * `size` — только ДЛИНА вставленного или набранного, никогда содержимое.
      Записать вставленный текст значило бы читать буфер обмена студента: там
      бывает всё что угодно, и к проверке домашней работы оно отношения не имеет.

    Данные пришли с клиента и подделываются кем угодно, кто откроет консоль.
    Это вспомогательное наблюдение для человека, а не доказательство, и
    интерфейс обязан говорить об этом прямо.
    """

    __tablename__ = "blitz_events"

    id: Mapped[uuid.UUID] = pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("blitz_sessions.id", ondelete="CASCADE"), index=True
    )
    # None у событий уровня формы: уход с вкладки не привязан к вопросу.
    question_id: Mapped[str | None] = mapped_column(String(16))
    kind: Mapped[str] = mapped_column(String(24))
    offset_ms: Mapped[int] = mapped_column(Integer, default=0)
    size: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = now_col()


class FraudDecision(Base):
    """Финальное решение человека.

    Отдельно от прогона: решение принимается ПО прогону, и в аудите должно быть
    видно, по какому именно. Повторный вызов добавляет строку, а не переписывает
    старую, — история пересмотров видна целиком.
    """

    __tablename__ = "fraud_decisions"

    id: Mapped[uuid.UUID] = pk()
    review_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reviews.id", ondelete="CASCADE"), index=True
    )
    detection_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("ai_detections.id"))
    blitz_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("blitz_sessions.id"))
    verdict: Mapped[str] = mapped_column(String(32))
    rationale: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime] = now_col()
