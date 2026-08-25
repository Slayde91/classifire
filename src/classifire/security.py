from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import HumanSession, User

__all__ = [
    "HUMAN_SESSION_MAX_AGE_SECONDS",
    "HumanSessionSecurityError",
    "authenticate_user",
    "create_csrf_token",
    "create_human_session",
    "get_current_user",
    "get_optional_user",
    "has_permission",
    "hash_password",
    "require_permission",
    "revoke_all_human_sessions",
    "revoke_current_human_session",
    "update_user_security",
    "verify_csrf",
    "verify_password",
]

ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

HUMAN_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
HUMAN_SESSION_SCHEMA = 1
_HUMAN_SESSION_TOKEN_BYTES = 32
_HUMAN_SESSION_TOKEN_LENGTH = 43
_AUTH_GENERATION_BYTES = 32
_AUTH_GENERATION_HEX_LENGTH = 64
_URLSAFE_TOKEN_CHARACTERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)
_LOWERCASE_HEX_CHARACTERS = frozenset("0123456789abcdef")
_AUTHENTICATED_SESSION_KEYS = frozenset({"session_schema", "session_token", "csrf_token"})
_AUTHENTICATION_MARKERS = frozenset({"session_schema", "session_token", "user_id"})


class HumanSessionSecurityError(ValueError):
    """A safe, non-secret-bearing error raised by session primitives."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


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
    user = db.scalar(
        select(User)
        .where(User.email == email.lower(), User.is_active.is_(True))
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if not user or not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(UTC)
    db.flush()
    return user


def create_csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verify_csrf(request: Request, supplied: object) -> None:
    """Validate CSRF without trusting signed-cookie value types.

    A structurally invalid authenticated cookie is discarded. A valid cookie
    survives an ordinary missing or incorrect form token so that one rejected
    request cannot act as an implicit logout.
    """

    keys = frozenset(request.session)
    if keys.intersection(_AUTHENTICATION_MARKERS):
        if _cookie_session_token(request) is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )
        expected: object = request.session.get("csrf_token")
    elif keys == {"csrf_token"}:
        expected = request.session.get("csrf_token")
        if not isinstance(expected, str) or not expected:
            request.session.clear()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid CSRF token",
            )
    else:
        if keys:
            request.session.clear()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    if (
        not isinstance(expected, str)
        or not expected
        or not isinstance(supplied, str)
        or not supplied
        or not hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _new_opaque_secret() -> str:
    return secrets.token_urlsafe(_HUMAN_SESSION_TOKEN_BYTES)


def _new_auth_generation() -> str:
    return secrets.token_hex(_AUTH_GENERATION_BYTES)


def _is_opaque_secret(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _HUMAN_SESSION_TOKEN_LENGTH
        and all(character in _URLSAFE_TOKEN_CHARACTERS for character in value)
    )


def _hash_human_session_token(token: str) -> str:
    if not _is_opaque_secret(token):
        raise HumanSessionSecurityError("invalid_session_token")
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _normalise_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise HumanSessionSecurityError("invalid_revocation_reason")
    return reason.strip()


def _normalise_generation(generation: object) -> str:
    if (
        not isinstance(generation, str)
        or len(generation) != _AUTH_GENERATION_HEX_LENGTH
        or any(character not in _LOWERCASE_HEX_CHARACTERS for character in generation)
    ):
        raise HumanSessionSecurityError("invalid_auth_generation")
    return generation


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _cookie_session_token(request: Request) -> str | None:
    keys = frozenset(request.session)
    if not keys:
        return None
    if not keys.intersection(_AUTHENTICATION_MARKERS):
        if keys != {"csrf_token"}:
            request.session.clear()
        return None
    if keys != _AUTHENTICATED_SESSION_KEYS:
        request.session.clear()
        return None

    schema = request.session.get("session_schema")
    token = request.session.get("session_token")
    csrf_token = request.session.get("csrf_token")
    if (
        type(schema) is not int
        or schema != HUMAN_SESSION_SCHEMA
        or not _is_opaque_secret(token)
        or not _is_opaque_secret(csrf_token)
    ):
        request.session.clear()
        return None
    return token


def _locked_user(db: Session, user_id: str) -> User | None:
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def _locked_user_session_state(db: Session, user_id: str) -> tuple[str, bool, str] | None:
    row = db.execute(
        select(User.id, User.is_active, User.auth_generation)
        .where(User.id == user_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        return None
    return row.id, row.is_active, row.auth_generation


def _locked_human_session_user(db: Session, token: str) -> tuple[HumanSession | None, User | None]:
    token_hash = _hash_human_session_token(token)
    owner_ids = list(
        db.scalars(
            select(HumanSession.user_id).where(HumanSession.token_hash == token_hash).limit(2)
        )
    )
    if len(owner_ids) != 1:
        return None, None

    user = _locked_user(db, owner_ids[0])
    if user is None:
        return None, None
    sessions = list(
        db.scalars(
            select(HumanSession)
            .where(
                HumanSession.user_id == user.id,
                HumanSession.token_hash == token_hash,
            )
            .execution_options(populate_existing=True)
            .with_for_update()
            .limit(2)
        )
    )
    if len(sessions) != 1:
        return None, None
    return sessions[0], user


def _human_session_user(db: Session, token: str) -> tuple[HumanSession | None, User | None]:
    rows = list(
        db.execute(
            select(HumanSession, User)
            .join(User, User.id == HumanSession.user_id)
            .where(HumanSession.token_hash == _hash_human_session_token(token))
            .limit(2)
        )
    )
    if len(rows) != 1:
        return None, None
    human_session, user = rows[0]
    return human_session, user


def create_human_session(
    db: Session,
    user: User,
    source_ip: str | None = None,
) -> str:
    """Create a persistent human session and flush it; the caller owns commit."""

    _ = source_ip
    locked_state = _locked_user_session_state(db, user.id)
    if locked_state is None:
        raise HumanSessionSecurityError("user_not_found")
    locked_user_id, is_active, auth_generation = locked_state
    if not is_active:
        raise HumanSessionSecurityError("inactive_user")
    generation = _normalise_generation(auth_generation)
    token = _new_opaque_secret()
    db.add(
        HumanSession(
            user_id=locked_user_id,
            token_hash=_hash_human_session_token(token),
            token_hint=token[:12],
            auth_generation=generation,
            expires_at=_utc_now() + timedelta(seconds=HUMAN_SESSION_MAX_AGE_SECONDS),
            revoked_at=None,
            revoked_reason=None,
        )
    )
    db.flush()
    return token


def _authenticated_session_user(request: Request, db: Session) -> User | None:
    token = _cookie_session_token(request)
    if token is None:
        return None
    human_session, user = _human_session_user(db, token)
    if human_session is None or user is None:
        request.session.clear()
        return None

    try:
        generation_matches = hmac.compare_digest(
            _normalise_generation(human_session.auth_generation),
            _normalise_generation(user.auth_generation),
        )
        session_expired = _as_utc(human_session.expires_at) <= _utc_now()
    except (AttributeError, HumanSessionSecurityError, TypeError, ValueError):
        request.session.clear()
        return None
    if (
        human_session.revoked_at is not None
        or session_expired
        or not user.is_active
        or not generation_matches
    ):
        request.session.clear()
        return None
    return user


def revoke_current_human_session(
    db: Session,
    request: Request,
    reason: str,
    source_ip: str | None = None,
) -> bool:
    """Revoke the presented session and flush it; the caller owns commit."""

    clean_reason = _normalise_reason(reason)
    token = _cookie_session_token(request)
    if token is None:
        return False
    human_session, user = _locked_human_session_user(db, token)
    if human_session is None or user is None or human_session.revoked_at is not None:
        request.session.clear()
        return False

    human_session.revoked_at = _utc_now()
    human_session.revoked_reason = clean_reason
    record_audit(
        db,
        actor=user,
        action="revoke_human_session",
        entity_type="human_session",
        entity_id=human_session.id,
        previous_value={"revoked": False},
        new_value={"revoked": True},
        reason=clean_reason,
        source_ip=source_ip,
    )
    db.flush()
    return True


def revoke_all_human_sessions(
    db: Session,
    user: User,
    actor: User | None,
    reason: str,
    source_ip: str | None = None,
    actor_name: str | None = None,
) -> int:
    """Revoke every session, rotate generation, and flush; caller owns commit."""

    clean_reason = _normalise_reason(reason)
    locked_user = _locked_user(db, user.id)
    if locked_user is None:
        raise HumanSessionSecurityError("user_not_found")

    locked_user.auth_generation = _new_auth_generation()
    db.flush()
    result = db.execute(
        update(HumanSession)
        .where(
            HumanSession.user_id == locked_user.id,
            HumanSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utc_now(), revoked_reason=clean_reason)
    )
    rowcount = getattr(result, "rowcount", None)
    if rowcount is None or rowcount < 0:
        raise HumanSessionSecurityError("revocation_count_unavailable")
    revoked_count = int(rowcount)
    record_audit(
        db,
        actor=actor,
        actor_type="user" if actor is not None else "system",
        actor_name=actor_name,
        action="revoke_all_human_sessions",
        entity_type="user",
        entity_id=locked_user.id,
        new_value={
            "auth_generation_rotated": True,
            "revoked_session_count": revoked_count,
        },
        reason=clean_reason,
        source_ip=source_ip,
    )
    db.flush()
    return revoked_count


def _normalise_account_text(value: object, *, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HumanSessionSecurityError(f"invalid_{field}")
    clean_value = value.strip()
    if len(clean_value) > maximum:
        raise HumanSessionSecurityError(f"invalid_{field}")
    return clean_value


def _safe_account_state(user: User) -> dict[str, object]:
    return {
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
    }


def update_user_security(
    db: Session,
    user: User,
    *,
    actor: User | None,
    reason: str,
    source_ip: str | None = None,
    actor_name: str | None = None,
    email: str | None = None,
    password_hash: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    full_name: str | None = None,
) -> int:
    """Apply governed account changes and invalidate prior sessions atomically.

    The helper flushes but never commits. The caller owns the surrounding
    transaction and can therefore roll back the account changes, generation
    rotation, session revocations, and audit records together.
    """

    clean_reason = _normalise_reason(reason)
    requested: dict[str, object] = {}
    if email is not None:
        requested["email"] = _normalise_account_text(
            email,
            field="email",
            maximum=320,
        ).lower()
    if password_hash is not None:
        requested["password_hash"] = _normalise_account_text(
            password_hash,
            field="password_hash",
            maximum=500,
        )
    if role is not None:
        clean_role = _normalise_account_text(role, field="role", maximum=50)
        if clean_role not in ROLE_PERMISSIONS:
            raise HumanSessionSecurityError("invalid_role")
        requested["role"] = clean_role
    if is_active is not None:
        if type(is_active) is not bool:
            raise HumanSessionSecurityError("invalid_is_active")
        requested["is_active"] = is_active
    if full_name is not None:
        requested["full_name"] = _normalise_account_text(
            full_name,
            field="full_name",
            maximum=200,
        )

    locked_user = _locked_user(db, user.id)
    if locked_user is None:
        raise HumanSessionSecurityError("user_not_found")
    changes = {
        field: value
        for field, value in requested.items()
        if getattr(locked_user, field) != value
    }
    if not changes:
        return 0

    previous_value = _safe_account_state(locked_user)
    for field, value in changes.items():
        setattr(locked_user, field, value)
    new_value = _safe_account_state(locked_user)
    new_value["password_changed"] = "password_hash" in changes

    revoked_count = revoke_all_human_sessions(
        db,
        locked_user,
        actor=actor,
        reason=clean_reason,
        source_ip=source_ip,
        actor_name=actor_name,
    )
    record_audit(
        db,
        actor=actor,
        actor_type="user" if actor is not None else "system",
        actor_name=actor_name,
        action="update_user_security",
        entity_type="user",
        entity_id=locked_user.id,
        previous_value=previous_value,
        new_value=new_value,
        reason=clean_reason,
        source_ip=source_ip,
    )
    db.flush()
    return revoked_count


def _session_user(request: Request, db: Session) -> User | None:
    return _authenticated_session_user(request, db)


def get_current_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = _session_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


def get_optional_user(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> User | None:
    return _session_user(request, db)


def require_permission(permission: str) -> Callable[..., User]:
    def dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if not has_permission(user, permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user

    return dependency
