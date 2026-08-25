from __future__ import annotations

import base64
import hashlib
import json
import secrets
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import AuditEvent, HumanSession, User
from classifire.security import (
    HUMAN_SESSION_MAX_AGE_SECONDS,
    HumanSessionSecurityError,
    authenticate_user,
    create_human_session,
    get_optional_user,
    hash_password,
    revoke_all_human_sessions,
    revoke_current_human_session,
    update_user_security,
    verify_csrf,
)


@pytest.fixture
def factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, future=True)
    engine.dispose()


def _new_user(
    db: Session,
    *,
    email: str = "human@example.com",
    active: bool = True,
    password_hash: str | None = None,
    auth_generation: str | None = None,
) -> User:
    user = User(
        email=email,
        full_name="Human Session Tester",
        password_hash=password_hash or f"unused-{secrets.token_hex(16)}",
        role="administrator",
        is_active=active,
        auth_generation=auth_generation or secrets.token_hex(32),
    )
    db.add(user)
    db.flush()
    return user


def _request(session: dict[str, Any]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "session": dict(session),
        }
    )


def _cookie(token: str, *, csrf_token: str | None = None) -> dict[str, Any]:
    return {
        "session_schema": 1,
        "session_token": token,
        "csrf_token": csrf_token or secrets.token_urlsafe(32),
    }


def _session_by_token(db: Session, token: str) -> HumanSession:
    token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
    human_session = db.scalar(select(HumanSession).where(HumanSession.token_hash == token_hash))
    assert human_session is not None
    return human_session


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_authenticate_user_locks_then_flushes_without_committing(
    factory: sessionmaker[Session],
) -> None:
    plain_text = "correct horse battery staple"
    with factory() as db:
        user = _new_user(db, password_hash=hash_password(plain_text))
        user_id = user.id
        db.commit()

    with factory() as db:
        authenticated = authenticate_user(db, "HUMAN@EXAMPLE.COM", plain_text)
        assert authenticated is not None
        assert authenticated.id == user_id
        assert authenticated.last_login_at is not None
        db.rollback()

    with factory() as db:
        stored_user = db.get(User, user_id)
        assert stored_user is not None
        assert stored_user.last_login_at is None
        assert authenticate_user(db, stored_user.email, "wrong password") is None
        stored_user.is_active = False
        db.commit()
        assert authenticate_user(db, stored_user.email, plain_text) is None


def test_create_session_stores_only_hash_and_flushes_without_committing(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        user_id = user.id
        generation = user.auth_generation
        db.commit()

        started = datetime.now(UTC)
        token = create_human_session(db, user, source_ip="203.0.113.10")
        finished = datetime.now(UTC)
        human_session = _session_by_token(db, token)

        padded_token = token + ("=" * (-len(token) % 4))
        assert len(base64.urlsafe_b64decode(padded_token.encode("ascii"))) == 32
        assert len(token) == 43
        assert human_session.user_id == user_id
        assert human_session.token_hash == hashlib.sha256(token.encode("ascii")).hexdigest()
        assert human_session.token_hint == token[:12]
        assert human_session.auth_generation == generation
        assert human_session.revoked_at is None
        assert human_session.revoked_reason is None
        assert _as_utc(human_session.expires_at) >= started + timedelta(
            seconds=HUMAN_SESSION_MAX_AGE_SECONDS
        )
        assert _as_utc(human_session.expires_at) <= finished + timedelta(
            seconds=HUMAN_SESSION_MAX_AGE_SECONDS
        )
        db.rollback()

    with factory() as db:
        assert db.scalar(select(func.count()).select_from(HumanSession)) == 0
        assert db.get(User, user_id) is not None


def test_create_session_rejects_inactive_or_corrupt_generation(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        inactive = _new_user(db, active=False)
        corrupt = _new_user(
            db,
            email="corrupt@example.com",
            auth_generation="not-a-valid-generation",
        )
        db.commit()

        with pytest.raises(HumanSessionSecurityError, match="inactive_user"):
            create_human_session(db, inactive)
        with pytest.raises(HumanSessionSecurityError, match="invalid_auth_generation"):
            create_human_session(db, corrupt)
        assert db.scalar(select(func.count()).select_from(HumanSession)) == 0


def test_valid_cookie_authenticates_with_one_indexed_join(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        token = create_human_session(db, user)
        db.commit()
        request = _request(_cookie(token))

        statements: list[str] = []
        engine = db.get_bind()

        def capture(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _executemany: bool,
        ) -> None:
            statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            authenticated = get_optional_user(request, db)
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        assert authenticated is not None
        assert authenticated.id == user.id
        assert dict(request.session) == _cookie(token, csrf_token=request.session["csrf_token"])
        auth_queries = [
            statement
            for statement in statements
            if statement.lstrip().upper().startswith("SELECT") and "human_sessions" in statement
        ]
        assert len(auth_queries) == 1
        assert "JOIN users" in auth_queries[0]
        assert "FOR UPDATE" not in auth_queries[0].upper()


def test_legacy_partial_unknown_and_malformed_cookies_fail_closed(
    factory: sessionmaker[Session],
) -> None:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    malformed_sessions: list[dict[str, Any]] = [
        {"user_id": "legacy-user", "csrf_token": csrf},
        {"session_token": token, "csrf_token": csrf},
        {"session_schema": 1, "csrf_token": csrf},
        {"session_schema": 1, "session_token": token},
        {"session_schema": "1", "session_token": token, "csrf_token": csrf},
        {"session_schema": True, "session_token": token, "csrf_token": csrf},
        {"session_schema": 0, "session_token": token, "csrf_token": csrf},
        {"session_schema": 2, "session_token": token, "csrf_token": csrf},
        {"session_schema": 1, "session_token": "short", "csrf_token": csrf},
        {"session_schema": 1, "session_token": token, "csrf_token": "short"},
        {
            "session_schema": 1,
            "session_token": token,
            "csrf_token": csrf,
            "unexpected": "field",
        },
        {"unexpected": "field"},
    ]
    with factory() as db:
        for session in malformed_sessions:
            request = _request(session)
            assert get_optional_user(request, db) is None
            assert dict(request.session) == {}


def test_anonymous_csrf_only_cookie_is_not_destroyed(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        request = _request({"csrf_token": "anonymous-csrf"})
        assert get_optional_user(request, db) is None
        assert dict(request.session) == {"csrf_token": "anonymous-csrf"}


def test_csrf_rejects_arbitrary_values_without_destroying_a_valid_session() -> None:
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    cookie = _cookie(token, csrf_token=csrf)

    supplied_values: list[object] = [None, 1, True, [], {}, "wrong", "N{LOCK}"]
    for supplied in supplied_values:
        request = _request(cookie)
        with pytest.raises(HTTPException) as error:
            verify_csrf(request, supplied)
        assert error.value.status_code == 403
        assert dict(request.session) == cookie

    request = _request(cookie)
    verify_csrf(request, csrf)
    assert dict(request.session) == cookie


@pytest.mark.parametrize(
    "malformed_cookie",
    [
        {"session_schema": 1, "session_token": secrets.token_urlsafe(32), "csrf_token": 1},
        {"session_schema": 1, "session_token": [], "csrf_token": secrets.token_urlsafe(32)},
        {"session_schema": "1", "session_token": secrets.token_urlsafe(32), "csrf_token": {}},
        {"user_id": "legacy", "csrf_token": secrets.token_urlsafe(32)},
    ],
)
def test_csrf_clears_structurally_malformed_authenticated_state(
    malformed_cookie: dict[str, Any],
) -> None:
    request = _request(malformed_cookie)
    with pytest.raises(HTTPException) as error:
        verify_csrf(request, object())
    assert error.value.status_code == 403
    assert dict(request.session) == {}


def test_anonymous_csrf_remains_compatible_and_malformed_value_is_cleared() -> None:
    request = _request({"csrf_token": "anonymous N{LOCK}"})
    verify_csrf(request, "anonymous N{LOCK}")
    assert dict(request.session) == {"csrf_token": "anonymous N{LOCK}"}

    with pytest.raises(HTTPException):
        verify_csrf(request, ["anonymous"])
    assert dict(request.session) == {"csrf_token": "anonymous N{LOCK}"}

    malformed = _request({"csrf_token": {"not": "text"}})
    with pytest.raises(HTTPException):
        verify_csrf(malformed, "anything")
    assert dict(malformed.session) == {}


@pytest.mark.parametrize(
    "invalid_state",
    ["revoked", "expired", "inactive", "generation_mismatch", "unknown_token"],
)
def test_invalid_persistent_session_states_fail_closed(
    factory: sessionmaker[Session], invalid_state: str
) -> None:
    with factory() as db:
        user = _new_user(db)
        token = create_human_session(db, user)
        human_session = _session_by_token(db, token)
        if invalid_state == "revoked":
            human_session.revoked_at = datetime.now(UTC)
            human_session.revoked_reason = "test revocation"
        elif invalid_state == "expired":
            human_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif invalid_state == "inactive":
            user.is_active = False
        elif invalid_state == "generation_mismatch":
            user.auth_generation = secrets.token_hex(32)
        elif invalid_state == "unknown_token":
            token = secrets.token_urlsafe(32)
        db.commit()

        request = _request(_cookie(token))
        assert get_optional_user(request, db) is None
        assert dict(request.session) == {}


def test_current_session_revocation_is_idempotent_and_replay_safe(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        token = create_human_session(db, user)
        cookie = _cookie(token)
        db.commit()

        first_request = _request(cookie)
        assert revoke_current_human_session(
            db,
            first_request,
            reason="User requested sign out",
            source_ip="203.0.113.20",
        )
        human_session = _session_by_token(db, token)
        human_session_id = human_session.id
        first_revoked_at = human_session.revoked_at
        assert first_revoked_at is not None
        assert human_session.revoked_reason == "User requested sign out"
        # The caller must commit the revocation before clearing the cookie. Keeping
        # it here allows a failed commit to roll back without silently signing the
        # user out of a still-valid server-side session.
        assert dict(first_request.session) == cookie
        audits = list(
            db.scalars(select(AuditEvent).where(AuditEvent.action == "revoke_human_session"))
        )
        assert len(audits) == 1
        audit = audits[0]
        assert audit.actor_user_id == user.id
        assert audit.actor_type == "user"
        assert audit.entity_type == "human_session"
        assert audit.entity_id == human_session_id
        assert audit.previous_value == {"revoked": False}
        assert audit.new_value == {"revoked": True}
        assert audit.reason == "User requested sign out"
        assert audit.source_ip == "203.0.113.20"
        assert audit.created_at is not None
        audit_text = json.dumps(
            {
                "previous": audit.previous_value,
                "new": audit.new_value,
                "reason": audit.reason,
                "event_hash": audit.event_hash,
            },
            sort_keys=True,
        )
        assert token not in audit_text
        assert human_session.token_hash not in audit_text
        assert human_session.token_hint not in audit_text
        db.commit()
        first_request.session.clear()
        assert dict(first_request.session) == {}

        copied_cookie = _request(cookie)
        assert not revoke_current_human_session(
            db,
            copied_cookie,
            reason="second attempt",
        )
        human_session = _session_by_token(db, token)
        assert human_session.revoked_at == first_revoked_at
        assert human_session.revoked_reason == "User requested sign out"
        assert dict(copied_cookie.session) == {}
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "revoke_human_session")
            )
            == 1
        )

        replay = _request(cookie)
        assert get_optional_user(replay, db) is None
        assert dict(replay.session) == {}


def test_current_session_revocation_flush_is_rollbackable(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        token = create_human_session(db, user)
        db.commit()

        cookie = _cookie(token)
        request = _request(cookie)
        assert revoke_current_human_session(
            db,
            request,
            reason="rollback test",
        )
        assert _session_by_token(db, token).revoked_at is not None
        assert dict(request.session) == cookie
        db.rollback()
        assert _session_by_token(db, token).revoked_at is None
        authenticated = get_optional_user(request, db)
        assert authenticated is not None
        assert authenticated.id == user.id
        assert dict(request.session) == cookie


def test_all_session_revocation_rotates_generation_and_has_secret_free_audit(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        other = _new_user(db, email="other@example.com")
        old_generation = user.auth_generation
        target_tokens = [
            create_human_session(db, user),
            create_human_session(db, user),
        ]
        other_token = create_human_session(db, other)
        db.commit()

        assert (
            revoke_all_human_sessions(
                db,
                user,
                actor=user,
                reason="User requested sign out everywhere",
                source_ip="203.0.113.30",
            )
            == 2
        )
        assert user.auth_generation != old_generation
        assert len(user.auth_generation) == 64
        assert set(user.auth_generation) <= set("0123456789abcdef")

        target_rows = [_session_by_token(db, token) for token in target_tokens]
        assert all(row.revoked_at is not None for row in target_rows)
        assert all(
            row.revoked_reason == "User requested sign out everywhere" for row in target_rows
        )
        assert _session_by_token(db, other_token).revoked_at is None

        audits = list(
            db.scalars(select(AuditEvent).where(AuditEvent.action == "revoke_all_human_sessions"))
        )
        assert len(audits) == 1
        audit = audits[0]
        assert audit.actor_user_id == user.id
        assert audit.entity_type == "user"
        assert audit.entity_id == user.id
        assert audit.reason == "User requested sign out everywhere"
        assert audit.source_ip == "203.0.113.30"
        assert audit.previous_value is None
        assert audit.new_value == {
            "auth_generation_rotated": True,
            "revoked_session_count": 2,
        }
        serialised_audit = json.dumps(
            {
                "previous": audit.previous_value,
                "new": audit.new_value,
                "reason": audit.reason,
                "event_hash": audit.event_hash,
            },
            sort_keys=True,
        )
        confidential_values = [old_generation, user.auth_generation]
        for token in [*target_tokens, other_token]:
            row = _session_by_token(db, token)
            confidential_values.extend([token, row.token_hash, row.token_hint])
        assert all(value not in serialised_audit for value in confidential_values)
        db.commit()

    with factory() as db:
        stored_user = db.scalar(select(User).where(User.email == "human@example.com"))
        assert stored_user is not None
        copied_cookie = _request(_cookie(target_tokens[0]))
        assert get_optional_user(copied_cookie, db) is None
        assert dict(copied_cookie.session) == {}
        other_cookie = _request(_cookie(other_token))
        authenticated_other = get_optional_user(other_cookie, db)
        assert authenticated_other is not None
        assert authenticated_other.email == "other@example.com"

        generation_after_first_revoke = stored_user.auth_generation
        assert (
            revoke_all_human_sessions(
                db,
                stored_user,
                actor=None,
                actor_name="security operator",
                reason="repeat revocation",
            )
            == 0
        )
        assert stored_user.auth_generation != generation_after_first_revoke
        db.commit()
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "revoke_all_human_sessions")
            )
            == 2
        )


def test_all_session_revocation_flush_is_rollbackable(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        user_id = user.id
        original_generation = user.auth_generation
        token = create_human_session(db, user)
        db.commit()

        assert (
            revoke_all_human_sessions(
                db,
                user,
                actor=None,
                actor_name="security operator",
                reason="rollback test",
            )
            == 1
        )
        assert user.auth_generation != original_generation
        assert _session_by_token(db, token).revoked_at is not None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
        db.rollback()

    with factory() as db:
        stored_user = db.get(User, user_id)
        assert stored_user is not None
        assert stored_user.auth_generation == original_generation
        assert _session_by_token(db, token).revoked_at is None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_all_session_revocation_preserves_pending_account_changes_with_autoflush_off(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        user_id = user.id
        create_human_session(db, user)
        db.commit()

        replacement_hash = f"replacement-{secrets.token_hex(16)}"
        user.password_hash = replacement_hash
        user.full_name = "Reactivated Administrator"
        user.is_active = False
        assert (
            revoke_all_human_sessions(
                db,
                user,
                actor=None,
                actor_name="security operator",
                reason="credential reset",
            )
            == 1
        )
        db.commit()

    with factory() as db:
        stored_user = db.get(User, user_id)
        assert stored_user is not None
        assert stored_user.password_hash == replacement_hash
        assert stored_user.full_name == "Reactivated Administrator"
        assert stored_user.is_active is False


@pytest.mark.parametrize(
    ("initial_role", "field", "replacement", "expected"),
    [
        ("read_only", "role", "administrator", "administrator"),
        ("administrator", "role", "read_only", "read_only"),
        (
            "administrator",
            "password_hash",
            "replacement-password-hash",
            "replacement-password-hash",
        ),
        ("administrator", "email", " Updated@Example.Test ", "updated@example.test"),
    ],
)
def test_governed_account_changes_reject_copied_sessions_and_flush_with_autoflush_off(
    factory: sessionmaker[Session],
    initial_role: str,
    field: str,
    replacement: str,
    expected: str,
) -> None:
    with factory() as db:
        assert db.autoflush is False
        user = _new_user(db)
        user.role = initial_role
        user_id = user.id
        original_generation = user.auth_generation
        original_password_hash = user.password_hash
        token = create_human_session(db, user)
        cookie = _cookie(token)
        human_session = _session_by_token(db, token)
        token_hash = human_session.token_hash
        token_hint = human_session.token_hint
        db.commit()

        changes: dict[str, Any] = {field: replacement}
        assert (
            update_user_security(
                db,
                user,
                actor=user,
                reason=f"governed {field} change",
                source_ip="203.0.113.40",
                **changes,
            )
            == 1
        )

        db.expire_all()
        persisted = db.get(User, user_id)
        assert persisted is not None
        assert getattr(persisted, field) == expected
        assert persisted.auth_generation != original_generation
        assert _session_by_token(db, token).revoked_at is not None
        audits = list(
            db.scalars(
                select(AuditEvent)
                .where(AuditEvent.entity_type == "user", AuditEvent.entity_id == user_id)
                .order_by(AuditEvent.action)
            )
        )
        assert {audit.action for audit in audits} == {
            "revoke_all_human_sessions",
            "update_user_security",
        }
        account_audit = next(
            audit for audit in audits if audit.action == "update_user_security"
        )
        assert account_audit.actor_user_id == user_id
        assert account_audit.reason == f"governed {field} change"
        assert account_audit.source_ip == "203.0.113.40"
        assert account_audit.previous_value is not None
        assert account_audit.new_value is not None
        assert set(account_audit.previous_value) == {
            "email",
            "full_name",
            "role",
            "is_active",
        }
        assert set(account_audit.new_value) == {
            "email",
            "full_name",
            "role",
            "is_active",
            "password_changed",
        }
        assert account_audit.new_value["password_changed"] is (field == "password_hash")
        audit_text = json.dumps(
            [
                {
                    "previous": audit.previous_value,
                    "new": audit.new_value,
                    "reason": audit.reason,
                    "event_hash": audit.event_hash,
                }
                for audit in audits
            ],
            sort_keys=True,
        )
        confidential_values = [
            token,
            token_hash,
            token_hint,
            original_generation,
            persisted.auth_generation,
            original_password_hash,
        ]
        if field == "password_hash":
            confidential_values.append(replacement)
        assert all(value not in audit_text for value in confidential_values)
        db.commit()

        replay = _request(cookie)
        assert get_optional_user(replay, db) is None
        assert dict(replay.session) == {}

        fresh_token = create_human_session(db, persisted)
        db.commit()
        fresh = _request(_cookie(fresh_token))
        assert get_optional_user(fresh, db) is not None


def test_deactivation_then_reactivation_never_resurrects_an_old_session(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        token = create_human_session(db, user)
        cookie = _cookie(token)
        db.commit()

        assert (
            update_user_security(
                db,
                user,
                actor=user,
                reason="account deactivated",
                is_active=False,
            )
            == 1
        )
        db.commit()
        inactive_replay = _request(cookie)
        assert get_optional_user(inactive_replay, db) is None
        assert dict(inactive_replay.session) == {}

        assert (
            update_user_security(
                db,
                user,
                actor=user,
                reason="account reactivated",
                is_active=True,
            )
            == 0
        )
        db.commit()
        reactivated_replay = _request(cookie)
        assert get_optional_user(reactivated_replay, db) is None
        assert dict(reactivated_replay.session) == {}

        fresh_token = create_human_session(db, user)
        db.commit()
        assert get_optional_user(_request(_cookie(fresh_token)), db) is not None


def test_governed_account_change_is_fully_rollbackable(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        user_id = user.id
        original_email = user.email
        original_role = user.role
        original_generation = user.auth_generation
        token = create_human_session(db, user)
        db.commit()

        assert (
            update_user_security(
                db,
                user,
                actor=user,
                reason="rollback governed change",
                email="changed@example.test",
                role="read_only",
            )
            == 1
        )
        assert _session_by_token(db, token).revoked_at is not None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2
        db.rollback()

    with factory() as db:
        stored_user = db.get(User, user_id)
        assert stored_user is not None
        assert stored_user.email == original_email
        assert stored_user.role == original_role
        assert stored_user.auth_generation == original_generation
        assert _session_by_token(db, token).revoked_at is None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert get_optional_user(_request(_cookie(token)), db) is not None


def test_governed_account_change_noop_does_not_revoke_rotate_or_audit(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        generation = user.auth_generation
        token = create_human_session(db, user)
        db.commit()

        assert (
            update_user_security(
                db,
                user,
                actor=user,
                reason="idempotent account reconciliation",
                email=f"  {user.email.upper()}  ",
                password_hash=user.password_hash,
                role=user.role,
                is_active=user.is_active,
                full_name=f"  {user.full_name}  ",
            )
            == 0
        )
        assert user.auth_generation == generation
        assert _session_by_token(db, token).revoked_at is None
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0
        assert get_optional_user(_request(_cookie(token)), db) is not None


def test_revocation_requires_non_blank_reason_without_mutating_state(
    factory: sessionmaker[Session],
) -> None:
    with factory() as db:
        user = _new_user(db)
        generation = user.auth_generation
        token = create_human_session(db, user)
        db.commit()

        request = _request(_cookie(token))
        with pytest.raises(HumanSessionSecurityError, match="invalid_revocation_reason"):
            revoke_current_human_session(db, request, reason="   ")
        with pytest.raises(HumanSessionSecurityError, match="invalid_revocation_reason"):
            revoke_all_human_sessions(db, user, actor=user, reason="")
        assert user.auth_generation == generation
        assert _session_by_token(db, token).revoked_at is None
        assert dict(request.session) != {}
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0
