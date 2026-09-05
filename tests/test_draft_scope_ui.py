from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.sessions import SessionMiddleware

from classifire.db import Base, get_db
from classifire.draft_scope_ui import router as draft_scope_router
from classifire.models import (
    AuditEvent,
    DraftScope,
    DraftScopeRevision,
    Estimate,
    Opening,
    Project,
    Service,
    User,
)
from classifire.physical_models import PhysicalModelLock, ServiceOpeningLink
from classifire.security import hash_password
from classifire.ui import router as ui_router

PASSWORD = "synthetic-scope-test-password"  # noqa: S105 - isolated test fixture


@dataclass(frozen=True)
class ScopeApplication:
    factory: sessionmaker[Session]
    app: FastAPI
    path: Path
    users: dict[str, str]


def _app(factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        SessionMiddleware,
        secret_key="synthetic-scope-session-secret",  # noqa: S106 - isolated fixture
    )
    app.include_router(ui_router)
    app.include_router(draft_scope_router)
    static = Path(__file__).resolve().parents[1] / "src" / "classifire" / "static"
    app.mount("/brand", StaticFiles(directory=str(static / "brand")), name="brand")
    app.mount("/static", StaticFiles(directory=str(static)), name="static")

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app


@pytest.fixture(scope="module")
def scope_password_hash() -> str:
    return hash_password(PASSWORD)


@pytest.fixture
def scope_app(tmp_path: Path, scope_password_hash: str) -> Iterator[ScopeApplication]:
    path = tmp_path / "synthetic-scope.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    users: dict[str, str] = {}
    with factory() as db:
        for name, role in (
            ("owner", "estimator"),
            ("other", "estimator"),
            ("admin", "administrator"),
            ("reader", "read_only"),
        ):
            user = User(
                email=f"{name}@scope.example.test",
                full_name=f"Synthetic Scope {name}",
                password_hash=scope_password_hash,
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
            users[name] = user.id
        db.commit()
    yield ScopeApplication(factory, _app(factory), path, users)
    engine.dispose()


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None, "The rendered form must include its session CSRF token"
    return match.group(1)


def _login(client: TestClient, name: str = "owner") -> None:
    page = client.get("/login")
    assert page.status_code == 200
    response = client.post(
        "/login",
        data={
            "email": f"{name}@scope.example.test",
            "password": PASSWORD,
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def _create(client: TestClient, reference: str = "SYNTHETIC-SCOPE") -> str:
    page = client.get("/scopes")
    assert page.status_code == 200
    response = client.post(
        "/scopes",
        data={
            "reference": reference,
            "name": "Synthetic shared opening review",
            "csrf_token": _csrf(page.text),
        },
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    path = response.headers["location"]
    assert re.fullmatch(r"/scopes/[0-9a-f-]{36}", path)
    return path


def _uid(value: int) -> str:
    return str(UUID(int=value))


def _payload() -> dict[str, object]:
    return {
        "defects": [{"id": _uid(1), "label": "D-01", "description": "Shared penetration"}],
        "openings": [
            {
                "id": _uid(2),
                "label": "Wall opening A",
                "defect_id": _uid(1),
                "plane": "wall",
                "substrate": "Unverified masonry",
                "width_mm": "250",
                "height_mm": "120",
                "state": "Inferred",
            },
            {
                "id": _uid(3),
                "label": "Wall opening B",
                "defect_id": _uid(1),
                "plane": "wall",
                "state": "Unresolved",
            },
            {
                "id": _uid(4),
                "label": "Blank floor opening",
                "defect_id": _uid(1),
                "plane": "floor",
                "blank": True,
            },
        ],
        "services": [
            {
                "id": _uid(5),
                "label": "Cable group",
                "opening_ids": [_uid(2), _uid(3)],
                "service_type": "cables",
                "quantity": "2",
                "unit": "each",
                "state": "Provisional",
            },
            {
                "id": _uid(6),
                "label": "Pipe",
                "opening_ids": [_uid(2)],
                "service_type": "pipe",
                "quantity": None,
                "unit": "each",
                "state": "Unresolved",
            },
        ],
        "observations": [
            {
                "id": _uid(7),
                "text": "Insulation and fire rating require evidence",
                "state": "Unresolved",
            }
        ],
        "assumptions": ["Manual draft; no retained source evidence has been verified"],
        "exclusions": ["Technical selection and pricing have not been performed"],
    }


def _edit(
    client: TestClient,
    path: str,
    payload: dict[str, object],
    *,
    revision: int = 1,
    action: str = "save",
) -> Response:
    page = client.get(path)
    assert page.status_code == 200
    return client.post(
        path,
        data={
            "csrf_token": _csrf(page.text),
            "expected_revision": str(revision),
            "action": action,
            "payload": json.dumps(payload),
        },
        follow_redirects=False,
    )


def _assert_no_canonical_scope(factory: sessionmaker[Session]) -> None:
    with factory() as db:
        for model in (Estimate, Opening, Service, ServiceOpeningLink, PhysicalModelLock):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_manual_scope_create_validate_save_reopen_and_exact_revision_download(
    scope_app: ScopeApplication,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_downstream(*args: object, **kwargs: object) -> None:
        pytest.fail("Manual Draft Scope must not invoke downstream or AI workflows")

    for target in (
        "classifire.services.technical.search_variants",
        "classifire.services.technical.search_for_opening",
        "classifire.services.calculation.recalculate_estimate",
        "classifire.services.snapshot.build_estimate_snapshot",
        "classifire.services.snapshot.lock_snapshot",
        "classifire.services.initial_canonicalisation_boundary.require_admission_bound_initial_canonicalisation",
        "classifire.services.phase8_openresponses_transport.Phase8OpenResponsesTransport.invoke",
        "classifire.ui.recalculate_estimate",
        "classifire.ui.lock_snapshot",
        "classifire.ui.require_admission_bound_initial_canonicalisation",
    ):
        monkeypatch.setattr(target, forbidden_downstream)
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        page = client.get(path)
        assert page.status_code == 200
        assert "Draft" in page.text
        first = client.get(f"{path}/download?revision=1")
        assert first.status_code == 200
        assert first.json()["revision"] == 1
        assert first.json()["state"] == "Draft"
        assert first.json()["provenance"] == "manual"
        assert first.json()["content"]["defects"] == []

        validation = _edit(client, path, _payload(), action="validate")
        assert validation.status_code == 200
        assert client.get(f"{path}/download?revision=1").content == first.content
        assert client.get(f"{path}/download?revision=2").status_code == 404

        saved = _edit(client, path, _payload())
        assert saved.status_code == 303, saved.text
        reopened = client.get(path)
        assert reopened.status_code == 200
        assert "Insulation and fire rating require evidence" in reopened.text
        second = client.get(f"{path}/download?revision=2")
        assert second.status_code == 200
        assert second.headers["content-type"].startswith("application/json")
        assert "attachment;" in second.headers["content-disposition"]
        assert ".json" in second.headers["content-disposition"]
        envelope = second.json()
        assert envelope["revision"] == 2
        assert envelope["artifact_id"] == path.rsplit("/", 1)[1]
        assert envelope["created_by"] == scope_app.users["owner"]
        assert envelope["parent_hash"] == first.json()["sha256"]
        assert envelope["content"]["services"][0]["opening_ids"] == [_uid(2), _uid(3)]
        assert envelope["content"]["services"][1]["quantity"] is None
        assert envelope["content"]["observations"][0]["state"] == "Unresolved"
        assert client.get(f"{path}/download?revision=1").content == first.content

    # A fresh engine and application prove the saved artifact survives process state.
    fresh_engine = create_engine(
        f"sqlite+pysqlite:///{scope_app.path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    fresh_factory = sessionmaker(bind=fresh_engine, future=True)
    try:
        with TestClient(_app(fresh_factory)) as restarted:
            _login(restarted)
            assert restarted.get(path).status_code == 200
            assert restarted.get(f"{path}/download?revision=2").content == second.content
    finally:
        fresh_engine.dispose()
    _assert_no_canonical_scope(scope_app.factory)


def test_stale_save_cannot_overwrite_a_newer_scope_revision(scope_app: ScopeApplication) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        assert _edit(client, path, _payload()).status_code == 303
        accepted = client.get(f"{path}/download?revision=2")
        stale = _edit(client, path, {"assumptions": ["This old browser tab must lose"]})
        assert stale.status_code == 409
        assert client.get(f"{path}/download?revision=2").content == accepted.content
        assert client.get(f"{path}/download?revision=3").status_code == 404


@pytest.mark.parametrize("invalid", ["schema", "relationship", "blank-opening", "json"])
def test_invalid_scope_input_is_reported_without_saving(
    scope_app: ScopeApplication, invalid: str
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        original = client.get(f"{path}/download?revision=1").content
        payload = _payload()
        if invalid == "schema":
            payload["approved"] = True
        elif invalid == "relationship":
            payload["services"][0]["opening_ids"] = [_uid(999)]
        elif invalid == "blank-opening":
            payload["services"][0]["opening_ids"] = [_uid(4)]
        if invalid == "json":
            page = client.get(path)
            response = client.post(
                path,
                data={
                    "csrf_token": _csrf(page.text),
                    "expected_revision": "1",
                    "action": "save",
                    "payload": "{not-json",
                },
                follow_redirects=False,
            )
        else:
            response = _edit(client, path, payload)
        assert response.status_code == 422, response.text
        assert client.get(f"{path}/download?revision=1").content == original
        assert client.get(f"{path}/download?revision=2").status_code == 404
    _assert_no_canonical_scope(scope_app.factory)


def test_scope_routes_require_an_authenticated_human(scope_app: ScopeApplication) -> None:
    with TestClient(scope_app.app) as client:
        assert client.get("/scopes", follow_redirects=False).status_code == 401
        assert client.get(f"/scopes/{_uid(42)}").status_code == 401
        assert client.get(f"/scopes/{_uid(42)}/download?revision=1").status_code == 401
        refused = client.post(
            "/scopes",
            data={
                "reference": "NO",
                "name": "Unauthorized",
                "csrf_token": _csrf(client.get("/login").text),
            },
            follow_redirects=False,
        )
        assert refused.status_code == 401
    with scope_app.factory() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 0


def test_csrf_rejection_preserves_draft_and_prevents_project_creation(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        refused = client.post(
            "/scopes",
            data={"reference": "NO-CSRF", "name": "Refused", "csrf_token": "forged"},
            follow_redirects=False,
        )
        assert refused.status_code == 403
        path = _create(client)
        before = client.get(f"{path}/download?revision=1").content
        rejected = client.post(
            path,
            data={
                "expected_revision": "1",
                "action": "save",
                "payload": json.dumps(_payload()),
                "csrf_token": "forged",
            },
            follow_redirects=False,
        )
        assert rejected.status_code == 403
        assert client.get(f"{path}/download?revision=1").content == before
        assert client.get(f"{path}/download?revision=2").status_code == 404
    with scope_app.factory() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 1


def test_draft_owner_boundary_and_administrator_access(scope_app: ScopeApplication) -> None:
    with TestClient(scope_app.app) as owner:
        _login(owner)
        path = _create(owner, "OWNER-PRIVATE-DRAFT")
        expected = owner.get(f"{path}/download?revision=1").content
    with TestClient(scope_app.app) as other:
        _login(other, "other")
        index = other.get("/scopes")
        assert index.status_code == 200
        assert "OWNER-PRIVATE-DRAFT" not in index.text
        assert other.get(path).status_code == 404
        assert other.get(f"{path}/download?revision=1").status_code == 404
        refused = other.post(
            path,
            data={
                "expected_revision": "1",
                "action": "save",
                "payload": "{}",
                "csrf_token": _csrf(index.text),
            },
            follow_redirects=False,
        )
        assert refused.status_code == 404
    with TestClient(scope_app.app) as admin:
        _login(admin, "admin")
        assert "OWNER-PRIVATE-DRAFT" in admin.get("/scopes").text
        assert admin.get(path).status_code == 200
        assert admin.get(f"{path}/download?revision=1").content == expected


def test_inactive_user_session_loses_scope_read_and_write_access(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        csrf = _csrf(client.get(path).text)
        with scope_app.factory() as db:
            user = db.get(User, scope_app.users["owner"])
            assert user is not None
            user.is_active = False
            db.commit()
        refused = client.post(
            path,
            data={
                "expected_revision": "1",
                "action": "save",
                "payload": "{}",
                "csrf_token": csrf,
            },
            follow_redirects=False,
        )
        assert refused.status_code == 401
        assert client.get(path, follow_redirects=False).status_code == 401
        assert client.get(f"{path}/download?revision=1").status_code == 401


def test_project_reader_cannot_create_a_scope(scope_app: ScopeApplication) -> None:
    with TestClient(scope_app.app) as client:
        _login(client, "reader")
        page = client.get("/scopes")
        # Reading an empty list must never grant the existing read-only role a write.
        assert page.status_code in (200, 403)
        csrf_page = client.get("/projects")
        assert csrf_page.status_code == 200
        refused = client.post(
            "/scopes",
            data={
                "reference": "READ-ONLY",
                "name": "Forbidden creation",
                "csrf_token": _csrf(csrf_page.text),
            },
            follow_redirects=False,
        )
        assert refused.status_code == 403
    with scope_app.factory() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 0


@pytest.mark.parametrize(
    ("case", "expected"),
    [("duplicate-json", 422), ("duplicate-form", 422), ("oversized", 413), ("content-type", 415)],
)
def test_unsafe_http_payloads_are_rejected_before_new_revision(
    scope_app: ScopeApplication,
    case: str,
    expected: int,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        form = {
            "csrf_token": _csrf(client.get(path).text),
            "expected_revision": "1",
            "action": "save",
            "payload": "{}",
        }
        if case == "duplicate-json":
            form["payload"] = '{"defects":[],"defects":[]}'
            response = client.post(path, data=form)
        elif case == "duplicate-form":
            response = client.post(
                path,
                content=urlencode(form) + "&action=validate",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        elif case == "oversized":
            form["payload"] = "x" * 300_001
            response = client.post(path, data=form)
        else:
            response = client.post(path, json=form)
        assert response.status_code == expected
        assert client.get(f"{path}/download?revision=2").status_code == 404


def test_saved_manual_text_is_escaped_in_editor_and_preserved_in_download(
    scope_app: ScopeApplication,
) -> None:
    hostile = "</script><img src=x onerror=alert(1)>"
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        saved = _edit(
            client,
            path,
            {
                "observations": [{"id": _uid(50), "text": hostile, "state": "Unresolved"}],
            },
        )
        assert saved.status_code == 303
        editor = client.get(path)
        assert editor.status_code == 200
        assert hostile not in editor.text
        package = client.get(f"{path}/download?revision=2")
        assert package.json()["content"]["observations"][0]["text"] == hostile
        assert package.headers["cache-control"] == "no-store"
        assert package.headers["x-content-type-options"] == "nosniff"


def test_download_has_one_audit_event_for_the_exact_saved_revision(
    scope_app: ScopeApplication,
) -> None:
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        package = client.get(f"{path}/download?revision=1")
        assert package.status_code == 200
    with scope_app.factory() as db:
        events = db.scalars(
            select(AuditEvent).where(AuditEvent.action == "draft_scope.download")
        ).all()
        assert len(events) == 1
        assert events[0].entity_id == path.rsplit("/", 1)[1]
        assert events[0].actor_user_id == scope_app.users["owner"]
        assert events[0].new_value == {"revision": 1, "sha256": package.json()["sha256"]}


def test_duplicate_project_reference_keeps_form_entries_without_partial_writes(
    scope_app: ScopeApplication,
) -> None:
    reference = "SYNTHETIC-DUPLICATE"
    unsaved_name = "Keep this unsaved project name"
    counted_models = (Project, DraftScope, DraftScopeRevision, AuditEvent)
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client, reference)
        page = client.get("/scopes")
        with scope_app.factory() as db:
            before = [
                db.scalar(select(func.count()).select_from(model)) for model in counted_models
            ]
        refused = client.post(
            "/scopes",
            data={
                "csrf_token": _csrf(page.text),
                "reference": reference,
                "name": unsaved_name,
            },
            follow_redirects=False,
        )
        assert refused.status_code == 409
        assert refused.headers["content-type"].startswith("text/html")
        assert "That project reference is already in use. Choose another reference." in refused.text
        assert f'name="reference" value="{reference}"' in refused.text
        assert f'name="name" value="{unsaved_name}"' in refused.text
        assert path in refused.text
        assert _csrf(refused.text)
        with scope_app.factory() as db:
            after = [db.scalar(select(func.count()).select_from(model)) for model in counted_models]
            assert after == before
            assert db.scalar(select(Project.name).where(Project.reference == reference)) == (
                "Synthetic shared opening review"
            )


@pytest.mark.parametrize(
    "unknown_key", ["1" * 5000, "\u00b9"], ids=["long-numeric", "unicode-digit"]
)
def test_malformed_field_names_show_validation_errors_without_saving_or_audit(
    scope_app: ScopeApplication,
    unknown_key: str,
) -> None:
    counted_models = (DraftScopeRevision, AuditEvent)
    with TestClient(scope_app.app) as client:
        _login(client)
        path = _create(client)
        with scope_app.factory() as db:
            before = [
                db.scalar(select(func.count()).select_from(model)) for model in counted_models
            ]
        rejected = _edit(client, path, {unknown_key: "unsupported field"})
        assert rejected.status_code == 422
        assert rejected.headers["content-type"].startswith("text/html")
        assert "Some fields are invalid. Check the findings below." in rejected.text
        assert "Check the field type, value and length." in rejected.text
        with scope_app.factory() as db:
            after = [db.scalar(select(func.count()).select_from(model)) for model in counted_models]
            assert after == before
            draft = db.get(DraftScope, path.rsplit("/", 1)[1])
            assert draft is not None
            assert draft.latest_revision == 1
        assert client.get(f"{path}/download?revision=2").status_code == 404
