from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import DEMO_DATA_SECTIONS, MOCK_MODULES, settings
from ..db import get_db
from ..models import Notification, User
from ..security import current_user
from ..serializers import iso
from ..services.ai_reviewer_client import AiReviewerClient

router = APIRouter(tags=["common"])


@router.get("/config")
def config() -> dict:
    ai_status = AiReviewerClient().health()
    return {
        "features": settings.feature_flags(),
        "demo_data_sections": DEMO_DATA_SECTIONS,
        "mock_modules": MOCK_MODULES,
        "ai": ai_status,
    }


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Notification)
        .where(Notification.recipient_id == user.id)
        .order_by(Notification.sent_at.desc())
    )
    return [
        {
            "id": str(row.id),
            "kind": row.kind,
            "title": row.title,
            "body": row.body,
            "payload": row.payload,
            "sent_at": iso(row.sent_at),
            "read": row.read_at is not None,
        }
        for row in rows
    ]


@router.post("/notifications/{notification_id}/read")
def mark_read(
    notification_id: UUID,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    notification = db.get(Notification, notification_id)
    if not notification or notification.recipient_id != user.id:
        raise HTTPException(404, "Уведомление не найдено")
    notification.read_at = datetime.now(UTC)
    db.commit()
    return {"ok": True}
