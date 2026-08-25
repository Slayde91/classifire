from __future__ import annotations

import re

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from classifire.agent_security import authenticate_agent, provision_agent_principal
from classifire.db import Base, get_db
from classifire.main import http_exception_handler
from classifire.models import AgentServicePrincipal, User
from classifire.security import get_current_user, get_optional_user, hash_password
from classifire.ui import _require, _user
from classifire.ui import router as ui_router

_SENSITIVE_PERMISSIONS = frozenset(
    {
        "project:write",
        "estimate:write",
        "estimate:approve",
        "estimate:export",
        "pricing:write",
        "pricing:approve",
        "technical:write",
        "technical:approve",
        "rule:write",
        "rule:approve",
    }
)


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _create_user(
    factory: sessionmaker[Session],
    *,
    email: str,
    role: str = "administrator",
    is_active: bool = True,
) -> str:
    with factory() as db:
        user = User(
            email=email,
            full_name=f"{role} test user",
            password_hash=hash_password("inactive-session-password"),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return str(user.id)


def _request(user_id: object) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [],
            "session": {
                "user_id": user_id,
                "csrf_token": "stale-session-csrf",
                "unrelated": "must-also-be-cleared",
            },
        }
    )


def _ui_app(factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="inactive-session-test-secret",  # noqa: S106 - isolated test value.
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.include_router(ui_router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app


def _csrf(response_text: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', response_text)
    assert match is not None
    return match.group(1)


def _login(client: TestClient, email: str) -> None:
    login_page = client.get("/login")
    response = client.post(
        "/login",
        data={
            "csrf_token": _csrf(login_page.text),
            "email": email,
            "password": "inactive-session-password",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _agent_request(agent_id: str, token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [
                (b"x-classifire-agent-id", agent_id.encode("ascii")),
                (b"authorization", f"Bearer {token}".encode("ascii")),
            ],
        }
    )


def test_deactivated_account_loses_existing_ui_session_immediately() -> None:
    factory = _session_factory()
    user_id = _create_user(factory, email="deactivated@example.test")
    app = _ui_app(factory)

    with TestClient(app) as client:
        _login(client, "deactivated@example.test")
        assert client.get("/").status_code == 200
        assert client.cookies.get("session") is not None

        with factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            user.is_active = False
            db.commit()

        blocked = client.get("/", follow_redirects=False)
        assert blocked.status_code == 303
        assert blocked.headers["location"] == "/login?next=/"
        assert "session=" in blocked.headers["set-cookie"]
        assert client.cookies.get("session") is None

        fresh_login_page = client.get("/login", follow_redirects=False)
        assert fresh_login_page.status_code == 200
        rejected_login = client.post(
            "/login",
            data={
                "csrf_token": _csrf(fresh_login_page.text),
                "email": "deactivated@example.test",
                "password": "inactive-session-password",
            },
            follow_redirects=False,
        )
        assert rejected_login.status_code == 303
        assert rejected_login.headers["location"].startswith(
            "/login?error=Invalid+email+or+password"
        )


@pytest.mark.parametrize("account_state", ["inactive", "missing"])
def test_invalid_ui_session_is_fully_cleared(account_state: str) -> None:
    factory = _session_factory()
    if account_state == "inactive":
        user_id = _create_user(
            factory,
            email="inactive-lookup@example.test",
            is_active=False,
        )
    else:
        user_id = "missing-user-id"

    request = _request(user_id)
    with factory() as db:
        assert _user(request, db) is None

    assert dict(request.session) == {}


@pytest.mark.parametrize(
    "user_id",
    [None, "", "   ", 0, False, [], {}],
    ids=["none", "empty", "whitespace", "zero", "false", "list", "mapping"],
)
def test_malformed_authentication_session_is_fully_cleared(user_id: object) -> None:
    factory = _session_factory()
    request = _request(user_id)

    with factory() as db:
        assert get_optional_user(request, db) is None

    assert dict(request.session) == {}


def test_api_current_user_uses_the_same_inactive_session_boundary() -> None:
    factory = _session_factory()
    user_id = _create_user(
        factory,
        email="inactive-api@example.test",
        is_active=False,
    )
    request = _request(user_id)

    with factory() as db, pytest.raises(HTTPException) as blocked:
        get_current_user(request, db)

    assert blocked.value.status_code == 401
    assert dict(request.session) == {}


def test_api_current_user_preserves_an_active_session() -> None:
    factory = _session_factory()
    user_id = _create_user(
        factory,
        email="active-api@example.test",
    )
    request = _request(user_id)

    with factory() as db:
        assert get_current_user(request, db).id == user_id

    assert request.session["user_id"] == user_id
    assert request.session["csrf_token"] == "stale-session-csrf"  # noqa: S105 - test value.


def test_inactive_agent_principal_cannot_reuse_its_bearer_token() -> None:
    factory = _session_factory()
    with factory() as db:
        principal, token = provision_agent_principal(
            db,
            agent_id="cf-orchestrator",
        )
        db.commit()
        principal_id = str(principal.id)
        agent_id = principal.agent_id
        assert authenticate_agent(_agent_request(agent_id, token), db).id == principal_id

        stored = db.get(AgentServicePrincipal, principal_id)
        assert stored is not None
        stored.is_active = False
        db.commit()

    with factory() as db, pytest.raises(HTTPException) as blocked:
        authenticate_agent(_agent_request(agent_id, token), db)

    assert blocked.value.status_code == 401


def test_anonymous_optional_lookup_preserves_non_authentication_session_state() -> None:
    factory = _session_factory()
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [],
            "session": {"csrf_token": "anonymous-csrf"},
        }
    )

    with factory() as db:
        assert get_optional_user(request, db) is None

    assert dict(request.session) == {"csrf_token": "anonymous-csrf"}


@pytest.mark.parametrize(
    ("role", "allowed_permissions"),
    [
        ("administrator", _SENSITIVE_PERMISSIONS),
        (
            "estimator",
            frozenset({"project:write", "estimate:write", "estimate:export"}),
        ),
        ("pricing_manager", frozenset({"pricing:write", "pricing:approve"})),
        (
            "technical_reviewer",
            frozenset(
                {
                    "technical:write",
                    "technical:approve",
                    "rule:write",
                    "rule:approve",
                }
            ),
        ),
        ("approver", frozenset({"estimate:approve", "estimate:export"})),
        ("read_only", frozenset()),
        ("unknown_role", frozenset()),
    ],
)
def test_active_ui_sensitive_permission_matrix_is_unchanged(
    role: str,
    allowed_permissions: frozenset[str],
) -> None:
    factory = _session_factory()
    user_id = _create_user(
        factory,
        email=f"{role}@example.test",
        role=role,
    )

    with factory() as db:
        for permission in sorted(_SENSITIVE_PERMISSIONS):
            request = _request(user_id)
            if permission in allowed_permissions:
                assert _require(request, db, permission).id == user_id
            else:
                with pytest.raises(HTTPException) as denied:
                    _require(request, db, permission)
                assert denied.value.status_code == 403
            assert request.session["user_id"] == user_id


def test_role_downgrade_applies_to_the_next_ui_request() -> None:
    factory = _session_factory()
    user_id = _create_user(
        factory,
        email="role-downgrade@example.test",
        role="estimator",
    )
    request = _request(user_id)

    with factory() as db:
        assert _require(request, db, "estimate:write").id == user_id

    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        user.role = "read_only"
        db.commit()

    with factory() as db, pytest.raises(HTTPException) as denied:
        _require(request, db, "estimate:write")

    assert denied.value.status_code == 403
    assert request.session["user_id"] == user_id


def test_logout_csrf_failure_retains_session_and_valid_logout_clears_it() -> None:
    factory = _session_factory()
    _create_user(factory, email="logout@example.test")
    app = _ui_app(factory)

    with TestClient(app) as client:
        _login(client, "logout@example.test")
        dashboard = client.get("/")
        assert dashboard.status_code == 200

        invalid_logout = client.post(
            "/logout",
            data={"csrf_token": "invalid"},
            follow_redirects=False,
        )
        assert invalid_logout.status_code == 403
        assert client.get("/").status_code == 200

        dashboard = client.get("/")
        valid_logout = client.post(
            "/logout",
            data={"csrf_token": _csrf(dashboard.text)},
            follow_redirects=False,
        )
        assert valid_logout.status_code == 303
        assert client.get("/login", follow_redirects=False).status_code == 200
