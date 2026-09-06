from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import (  # noqa: F401
    _assert_no_canonical_scope,
    _create,
    _csrf,
    _login,
    scope_app,
    scope_password_hash,
)

from classifire import draft_project_package_ui as ui
from classifire.models import AuditEvent, DraftProjectPackage, DraftScope, Project, User
from classifire.services import draft_project_packages as packages


def counts(factory):
    with factory() as db:
        return [
            db.scalar(select(func.count()).select_from(m))
            for m in (AuditEvent, Project, DraftScope, DraftProjectPackage)
        ]


def test_upload_complete_inspection_no_writes_csrf_bounds_and_permissions(scope_app, monkeypatch):  # noqa: F811
    app = scope_app
    app.app.include_router(ui.router)
    with TestClient(app.app) as client:
        _login(client)
        path = _create(client)
        draft_id = path.rsplit("/", 1)[-1]
        with app.factory() as db:
            actor = db.get(User, app.users["owner"])
            preview = packages.preview(db, actor, draft_id, {"scope_revision": 1})
            row = packages.create_package(
                db, actor, draft_id, {"scope_revision": 1}, 0, preview["preview_hash"]
            )
            raw = row.archive_bytes
            db.commit()
        page = client.get("/package-import")
        token = _csrf(page.text)
        assert "Inspect a downloaded project ZIP" in client.get("/scopes").text
        assert page.status_code == 200
        before = counts(app.factory)
        response = client.post(
            "/package-import/preview",
            data={"csrf_token": token},
            files={"file": ("untrusted.zip", raw, "application/zip")},
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "JSON contracts and selected dependencies validated" in response.text
        assert "No project was created" in response.text
        assert "Foreign and unverified" in response.text
        assert "artifacts/scope.json" in response.text
        assert "not available yet" in response.text
        assert packages.digest(raw) in response.text
        assert counts(app.factory) == before
        assert (
            client.post(
                "/package-import/preview",
                data={"csrf_token": "bad"},
                files={"file": ("test.zip", raw)},
            ).status_code
            == 403
        )
        invalid = client.post(
            "/package-import/preview",
            data={"csrf_token": token},
            files={"file": ("<script>secret</script>.zip", b"not a zip")},
        )
        assert invalid.status_code == 409
        assert "secret" not in invalid.text
        assert (
            client.post(
                "/package-import/preview",
                data={"csrf_token": token},
                files=[("file", ("one.zip", raw)), ("file", ("two.zip", raw))],
            ).status_code
            == 400
        )
        assert client.post("/package-import/preview", data={"csrf_token": token}).status_code == 415
        monkeypatch.setattr(ui, "get_settings", lambda: SimpleNamespace(max_upload_bytes=32))
        assert (
            client.post(
                "/package-import/preview",
                data={"csrf_token": token},
                files={"file": ("test.zip", raw)},
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/package-import/preview",
                content=iter([b"x" * 17000]),
                headers={"content-type": "multipart/form-data; boundary=synthetic"},
            ).status_code
            == 413
        )
        assert counts(app.factory) == before
    with TestClient(app.app) as client:
        assert client.get("/package-import", follow_redirects=False).status_code in (303, 401)
        _login(client, "reader")
        assert client.get("/package-import").status_code == 403
        assert client.post("/package-import/preview", content=b"x").status_code == 403
    _assert_no_canonical_scope(app.factory)


def test_foreign_project_text_is_escaped_and_not_used_as_local_identity(scope_app):  # noqa: F811
    app = scope_app
    app.app.include_router(ui.router)
    with TestClient(app.app) as client:
        _login(client)
        draft_id = _create(client).rsplit("/", 1)[-1]
        with app.factory() as db:
            actor = db.get(User, app.users["owner"])
            preview = packages.preview(db, actor, draft_id, {"scope_revision": 1})
            row = packages.create_package(
                db, actor, draft_id, {"scope_revision": 1}, 0, preview["preview_hash"]
            )
            manifest, members = packages.inspect_archive(row.archive_bytes)
            manifest["project"]["name"] = '<script>alert("foreign")</script>'
            raw = packages._archive(manifest, members)
            db.commit()
        before = counts(app.factory)
        token = _csrf(client.get("/package-import").text)
        response = client.post(
            "/package-import/preview",
            data={"csrf_token": token},
            files={"file": ("project.zip", raw)},
        )
        assert response.status_code == 200
        assert '<script>alert("foreign")</script>' not in response.text
        assert "&lt;script&gt;" in response.text
        assert counts(app.factory) == before
