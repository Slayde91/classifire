from __future__ import annotations

import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "administrator": {"*"},
    "estimator": {
        "project:read",
        "project:write",
        "estimate:read",
        "estimate:write",
        "estimate:export",
        "library:read",
        "technical:read",
        "rule:read",
    },
    "pricing_manager": {
        "library:read",
        "pricing:write",
        "pricing:approve",
        "change:review",
        "audit:read",
    },
    "technical_reviewer": {
        "library:read",
        "technical:read",
        "technical:write",
        "technical:approve",
        "rule:read",
        "rule:write",
        "rule:approve",
        "change:review",
        "audit:read",
    },
    "approver": {
        "project:read",
        "estimate:read",
        "estimate:approve",
        "estimate:export",
        "library:read",
        "technical:read",
        "rule:read",
        "audit:read",
    },
    "read_only": {
        "project:read",
        "estimate:read",
        "library:read",
        "technical:read",
        "rule:read",
        "audit:read",
    },
}


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return ph.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def has_permission(user: User, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(user.role, set())
    return "*" in permissions or permission in permissions


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower(), User.is_active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def create_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, supplied: str | None) -> None:
    expected = request.session.get("csrf_token")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return user


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency
