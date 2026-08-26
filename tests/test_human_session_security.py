from __future__ import annotations

import re
from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

from classifire.db import Base, get_db
from classifire.models import Product, User
from classifire.security import get_current_user, get_optional_user, hash_password
from classifire.ui import router as ui_router


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def _add_admin(factory: sessionmaker[Session]) -> str:
    with factory() as db:
        user = User(
            email="session-security@example.test",
            full_name="Session Security Administrator",
            password_hash=hash_password("session-security-password"),
            role="administrator",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _request(session: dict[str, object]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 50000),
            "server": ("testserver", 80),
            "session": session,
        }
    )


def _test_app(factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="human-session-security-test-secret",  # noqa: S106 - isolated fixture
    )
    app.include_router(ui_router)

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app


def _csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_optional_session_user_accepts_only_an_active_account() -> None:
    factory = _session_factory()
    user_id = _add_admin(factory)

    with factory() as db:
        active_session: dict[str, object] = {
            "user_id": user_id,
            "csrf_token": "active-csrf",
        }
        active = get_optional_user(_request(active_session), db)
        assert active is not None
        assert active.id == user_id
        assert get_current_user(_request(active_session), db).id == user_id
        assert active_session == {"user_id": user_id, "csrf_token": "active-csrf"}

        active.is_active = False
        db.commit()
        inactive_session: dict[str, object] = {
            "user_id": user_id,
            "csrf_token": "inactive-csrf",
        }
        assert get_optional_user(_request(inactive_session), db) is None
        assert inactive_session == {}

        current_session: dict[str, object] = {
            "user_id": user_id,
            "csrf_token": "current-csrf",
        }
        with pytest.raises(HTTPException) as rejected:
            get_current_user(_request(current_session), db)
        assert rejected.value.status_code == 401
        assert current_session == {}


def test_optional_session_user_clears_a_deleted_account() -> None:
    factory = _session_factory()
    user_id = _add_admin(factory)

    with factory() as db:
        user = db.get(User, user_id)
        assert user is not None
        db.delete(user)
        db.commit()
        deleted_session: dict[str, object] = {
            "user_id": user_id,
            "csrf_token": "deleted-csrf",
        }
        assert get_optional_user(_request(deleted_session), db) is None
        assert deleted_session == {}


def test_inactive_user_cannot_complete_a_protected_ui_write() -> None:
    factory = _session_factory()
    user_id = _add_admin(factory)
    app = _test_app(factory)

    with TestClient(app) as client:
        login_page = client.get("/login")
        login = client.post(
            "/login",
            data={
                "csrf_token": _csrf_token(login_page.text),
                "email": "session-security@example.test",
                "password": "session-security-password",
            },
            follow_redirects=False,
        )
        assert login.status_code == 303

        products_page = client.get("/products")
        assert products_page.status_code == 200
        csrf_token = _csrf_token(products_page.text)

        with factory() as db:
            user = db.get(User, user_id)
            assert user is not None
            user.is_active = False
            db.commit()

        rejected = client.post(
            "/products",
            data={
                "csrf_token": csrf_token,
                "sku": "SHOULD-NOT-EXIST",
                "name": "Revoked session write",
                "item_type": "product",
                "unit": "each",
                "base_cost": "10",
                "default_markup_percent": "30",
                "reason": "Prove revoked users cannot write",
            },
            follow_redirects=False,
        )

        assert rejected.status_code == 401
        assert client.get("/login", follow_redirects=False).status_code == 200

    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Product)) == 0
