from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from typer.testing import CliRunner

from classifire.cli import app as cli_app
from classifire.db import Base, get_db
from classifire.main import http_exception_handler
from classifire.models import AuditEvent, HumanSession, User
from classifire.security import (
    create_human_session,
    get_optional_user,
    hash_password,
    verify_password,
)
from classifire.ui import router as ui_router

_PASSWORD = "session-test-password"  # noqa: S105 - isolated test credential.
_NEW_PASSWORD = "replacement-session-test-password"  # noqa: S105 - isolated test credential.
_OPERATOR = "CHANGE-SESSION-TEST"
_TEST_CSRF_TOKEN = "c" * 43  # noqa: S105 - isolated test value.


@dataclass(frozen=True)
class DatabaseHarness:
    engine: Engine
    factory: sessionmaker[Session]


@pytest.fixture
def database_harness(monkeypatch: pytest.MonkeyPatch) -> Iterator[DatabaseHarness]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    monkeypatch.setattr("classifire.cli.engine", engine)
    monkeypatch.setattr("classifire.cli.SessionLocal", factory)
    try:
        yield DatabaseHarness(engine=engine, factory=factory)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _create_user(
    factory: sessionmaker[Session],
    *,
    email: str,
    password: str = _PASSWORD,
    role: str = "estimator",
    is_active: bool = True,
) -> str:
    with factory() as db:
        user = User(
            email=email,
            full_name="Human session test user",
            password_hash=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return str(user.id)


def _issue_session(factory: sessionmaker[Session], user_id: str) -> str:
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        token = create_human_session(db, user, source_ip="192.0.2.10")
        db.commit()
        return token


def _session_request(token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [],
            "session": {
                "session_schema": 1,
                "session_token": token,
                "csrf_token": _TEST_CSRF_TOKEN,
            },
        }
    )


def _assert_token_rejected(factory: sessionmaker[Session], token: str) -> None:
    request = _session_request(token)
    with factory() as db:
        assert get_optional_user(request, db) is None
    assert dict(request.session) == {}


def _audit_text(event: AuditEvent) -> str:
    return json.dumps(
        {
            "actor_name": event.actor_name,
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "previous_value": event.previous_value,
            "new_value": event.new_value,
            "reason": event.reason,
        },
        default=str,
        sort_keys=True,
    )


def _ui_app(factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="human-session-ui-test-secret",  # noqa: S106 - isolated test value.
    )
    app.add_exception_handler(
        HTTPException,
        http_exception_handler,  # type: ignore[arg-type]
    )

    @app.get("/_test/session")
    def session_contents(request: Request) -> dict[str, object]:
        return dict(request.session)

    app.include_router(ui_router)

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app


def _csrf(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def _login(client: TestClient, *, email: str, password: str = _PASSWORD) -> dict[str, object]:
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": _csrf(login_page.text),
            "email": email,
            "password": password,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    session = cast(dict[str, object], client.get("/_test/session").json())
    assert session["session_schema"] == 1
    assert isinstance(session["session_token"], str)
    assert session["session_token"]
    assert isinstance(session["csrf_token"], str)
    assert "user_id" not in session
    assert "auth_generation" not in session
    return session


def test_create_admin_reset_revokes_existing_sessions_in_the_same_commit(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "existing-admin@example.test"
    user_id = _create_user(
        factory,
        email=email,
        role="read_only",
    )
    old_token = _issue_session(factory, user_id)
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        old_generation = user.auth_generation
        user.is_active = False
        db.commit()

    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "create-admin",
            "--email",
            email,
            "--full-name",
            "Reset administrator",
            "--password",
            _NEW_PASSWORD,
            "--operator-reference",
            _OPERATOR,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Administrator reset and prior sessions revoked" in result.output
    assert _NEW_PASSWORD not in result.output
    assert old_token not in result.output
    assert _OPERATOR not in result.output
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.full_name == "Reset administrator"
        assert user.role == "administrator"
        assert user.is_active is True
        assert verify_password(_NEW_PASSWORD, user.password_hash)
        assert user.auth_generation != old_generation
        sessions = db.scalars(
            select(HumanSession).where(HumanSession.user_id == user_id)
        ).all()
        assert len(sessions) == 1
        assert sessions[0].revoked_at is not None
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.actor_name == _OPERATOR)
        ).all()
        assert {event.action for event in events} == {
            "revoke_all_human_sessions",
            "update_user_security",
        }
        audit_text = "\n".join(_audit_text(event) for event in events)
        assert _NEW_PASSWORD not in audit_text
        assert old_token not in audit_text
    _assert_token_rejected(factory, old_token)


def test_create_admin_creates_a_new_user_without_revocation(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "new-admin@example.test"
    runner = CliRunner()

    result = runner.invoke(
        cli_app,
        [
            "create-admin",
            "--email",
            email,
            "--password",
            _PASSWORD,
            "--operator-reference",
            _OPERATOR,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Administrator created" in result.output
    assert _PASSWORD not in result.output
    assert _OPERATOR not in result.output
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.role == "administrator"
        assert user.is_active is True
        assert len(user.auth_generation) == 64
        assert db.scalar(select(HumanSession)) is None
        event = db.scalar(
            select(AuditEvent).where(AuditEvent.actor_name == _OPERATOR)
        )
        assert event is not None
        assert event.action == "create_administrator"
        assert event.entity_type == "user"
        assert event.entity_id == user.id
        audit_text = _audit_text(event)
        assert _PASSWORD not in audit_text
        assert user.password_hash not in audit_text


def test_revoke_user_sessions_invalidates_every_token_and_records_operator_reason(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "revoke-all@example.test"
    user_id = _create_user(factory, email=email)
    tokens = [_issue_session(factory, user_id), _issue_session(factory, user_id)]
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        old_generation = user.auth_generation

    reason = "Operator-directed access review"
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "revoke-user-sessions",
            "--email",
            email,
            "--reason",
            reason,
            "--operator-reference",
            _OPERATOR,
        ],
    )

    assert result.exit_code == 0, result.output
    assert "All human sessions revoked" in result.output
    assert "(2 active session(s))" in result.output
    assert reason not in result.output
    assert _OPERATOR not in result.output
    assert all(token not in result.output for token in tokens)
    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        assert user.auth_generation != old_generation
        sessions = db.scalars(
            select(HumanSession).where(HumanSession.user_id == user_id)
        ).all()
        assert len(sessions) == 2
        assert all(item.revoked_at is not None for item in sessions)
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.actor_name == _OPERATOR)
        ).all()
        assert len(events) == 1
        audit_text = _audit_text(events[0])
        assert reason in audit_text
        assert all(token not in audit_text for token in tokens)
    for token in tokens:
        _assert_token_rejected(factory, token)


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--email", "   "),
        ("--reason", "   "),
        ("--operator-reference", "   "),
    ],
)
def test_revoke_user_sessions_rejects_blank_audit_inputs_without_mutation(
    database_harness: DatabaseHarness,
    option: str,
    value: str,
) -> None:
    factory = database_harness.factory
    email = "blank-input@example.test"
    user_id = _create_user(factory, email=email)
    token = _issue_session(factory, user_id)
    arguments = {
        "--email": email,
        "--reason": "Controlled security response",
        "--operator-reference": _OPERATOR,
    }
    arguments[option] = value
    command = ["revoke-user-sessions"]
    for name, supplied in arguments.items():
        command.extend([name, supplied])

    result = CliRunner().invoke(cli_app, command)

    assert result.exit_code != 0
    with factory() as db:
        session = db.scalar(
            select(HumanSession).where(HumanSession.user_id == user_id)
        )
        assert session is not None
        assert session.revoked_at is None
        assert db.scalar(select(AuditEvent)) is None
    request = _session_request(token)
    with factory() as db:
        assert get_optional_user(request, db) is not None


def test_logout_revokes_only_the_current_server_session(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "browser-logout@example.test"
    _create_user(factory, email=email)
    app = _ui_app(factory)

    with TestClient(app) as first, TestClient(app) as second:
        first_session = _login(first, email=email)
        second_session = _login(second, email=email)
        first_token = first_session["session_token"]
        second_token = second_session["session_token"]
        assert isinstance(first_token, str)
        assert isinstance(second_token, str)
        dashboard = first.get("/")
        assert dashboard.status_code == 200
        assert "Sign out this browser" in dashboard.text
        assert "Sign out everywhere" in dashboard.text

        response = first.post(
            "/logout",
            data={"csrf_token": _csrf(dashboard.text)},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert first.cookies.get("session") is None
        assert second.get("/").status_code == 200
        with factory() as db:
            sessions = db.scalars(select(HumanSession)).all()
            assert len(sessions) == 2
            assert sum(item.revoked_at is not None for item in sessions) == 1
            audit_text = "\n".join(_audit_text(item) for item in db.scalars(select(AuditEvent)))
            assert first_token not in audit_text
            assert second_token not in audit_text
    _assert_token_rejected(factory, first_token)


def test_logout_all_revokes_other_browsers_and_rotates_generation(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "browser-logout-all@example.test"
    user_id = _create_user(factory, email=email)
    app = _ui_app(factory)

    with TestClient(app) as first, TestClient(app) as second:
        first_session = _login(first, email=email)
        second_session = _login(second, email=email)
        first_token = first_session["session_token"]
        second_token = second_session["session_token"]
        assert isinstance(first_token, str)
        assert isinstance(second_token, str)
        with factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            old_generation = user.auth_generation

        dashboard = first.get("/")
        response = first.post(
            "/logout-all",
            data={"csrf_token": _csrf(dashboard.text)},
            follow_redirects=False,
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/login"
        assert first.cookies.get("session") is None
        blocked = second.get("/", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/login?next=/"
        assert second.cookies.get("session") is None
        with factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            assert user.auth_generation != old_generation
            sessions = db.scalars(
                select(HumanSession).where(HumanSession.user_id == user_id)
            ).all()
            assert len(sessions) == 2
            assert all(item.revoked_at is not None for item in sessions)
            audit_text = "\n".join(_audit_text(item) for item in db.scalars(select(AuditEvent)))
            assert first_token not in audit_text
            assert second_token not in audit_text
    for copied_token in (first_token, second_token):
        _assert_token_rejected(factory, copied_token)


def test_invalid_logout_csrf_does_not_revoke_the_server_session(
    database_harness: DatabaseHarness,
) -> None:
    factory = database_harness.factory
    email = "browser-csrf@example.test"
    _create_user(factory, email=email)
    app = _ui_app(factory)

    with TestClient(app) as client:
        _login(client, email=email)
        response = client.post(
            "/logout",
            data={"csrf_token": "invalid"},
            follow_redirects=False,
        )

        assert response.status_code == 403
        assert client.get("/").status_code == 200
        with factory() as db:
            session = db.scalar(select(HumanSession))
            assert session is not None
            assert session.revoked_at is None


def test_revoke_user_sessions_rejects_unknown_user_without_audit(
    database_harness: DatabaseHarness,
) -> None:
    result = CliRunner().invoke(
        cli_app,
        [
            "revoke-user-sessions",
            "--email",
            "missing@example.test",
            "--reason",
            "Controlled security response",
            "--operator-reference",
            _OPERATOR,
        ],
    )

    assert result.exit_code != 0
    assert "No user exists for --email" in result.output
    with database_harness.factory() as db:
        assert db.scalar(select(AuditEvent)) is None


def test_create_admin_refuses_0009_without_schema_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL)")
        )
        connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "VALUES ('0009_visual_validation_receipts')"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE users ("
                "id VARCHAR(36) PRIMARY KEY, "
                "email VARCHAR(320) NOT NULL)"
            )
        )
    before_tables = tuple(sorted(inspect(engine).get_table_names()))
    before_user_columns = tuple(
        sorted(column["name"] for column in inspect(engine).get_columns("users"))
    )
    monkeypatch.setattr("classifire.cli.engine", engine)
    monkeypatch.setattr("classifire.cli.SessionLocal", factory)

    result = CliRunner().invoke(
        cli_app,
        [
            "create-admin",
            "--email",
            "blocked@example.test",
            "--password",
            _PASSWORD,
            "--operator-reference",
            _OPERATOR,
        ],
    )

    assert result.exit_code != 0
    assert "DATABASE_MIGRATION_REQUIRED" in result.output
    assert tuple(sorted(inspect(engine).get_table_names())) == before_tables
    assert tuple(
        sorted(column["name"] for column in inspect(engine).get_columns("users"))
    ) == before_user_columns
    assert "human_sessions" not in before_tables
    assert "auth_generation" not in before_user_columns
    engine.dispose()
