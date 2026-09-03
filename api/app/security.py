"""JWT и RBAC.

Инвариант, который проверяется, а не декларируется: студенту эндпоинты
AI-сигнала и черновиков не отдаются на уровне доступа, а не на уровне вёрстки.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Role, User

bearer = HTTPBearer(auto_error=False)


def issue_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "name": user.full_name,
        "exp": datetime.now(UTC) + timedelta(hours=settings.jwt_ttl_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужна авторизация")
    try:
        payload = jwt.decode(
            creds.credentials, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Недействительный токен") from None

    user = db.get(User, UUID(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Пользователь не найден")
    return user


def require(*roles: Role):
    """Зависимость роли. Вешается на роутер целиком, а не на отдельные поля ответа."""

    allowed = {str(r) for r in roles}

    def guard(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Недостаточно прав")
        return user

    return guard
