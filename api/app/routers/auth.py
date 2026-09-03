from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Role, User
from ..security import current_user, issue_token

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/demo/{role}")
def demo_login(role: Role, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.role == role).order_by(User.created_at))
    if not user:
        raise HTTPException(404, "Демо-пользователь не найден")
    return {
        "access_token": issue_token(user),
        "token_type": "bearer",
        "user": {"id": str(user.id), "name": user.full_name, "email": user.email, "role": user.role},
    }


@router.get("/me")
def me(user: User = Depends(current_user)) -> dict:
    return {"id": str(user.id), "name": user.full_name, "email": user.email, "role": user.role}
