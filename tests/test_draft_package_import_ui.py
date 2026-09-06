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
        assert "Create imported Draft project" in response.text
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


def test_confirm_import_roundtrip_replay_changed_file_owner_and_restart(scope_app):  # noqa: F811
    from test_draft_project_package_ui import fields

    app = scope_app
    app.app.include_router(ui.router)
    with TestClient(app.app) as client:
        _login(client)
        draft_id = _create(client).rsplit("/", 1)[-1]
        with app.factory() as db:
            actor = db.get(User, app.users["owner"])
            selected = {"scope_revision": 1}
            preview = packages.preview(db, actor, draft_id, selected)
            row = packages.create_package(db, actor, draft_id, selected, 0, preview["preview_hash"])
            raw = row.archive_bytes
            db.commit()
        csrf = _csrf(client.get("/package-import").text)
        preview = client.post(
            "/package-import/preview",
            data={"csrf_token": csrf},
            files={"file": ("project.zip", raw)},
        )
        form = fields(preview) | {
            "reference": "IMPORTED",
            "name": "Imported editable project",
            "confirm": "yes",
        }
        assert (
            client.post(
                "/package-import/confirm", data=form, files={"file": ("changed.zip", raw + b"x")}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/package-import/confirm",
                data=form | {"csrf_token": "bad"},
                files={"file": ("project.zip", raw)},
            ).status_code
            == 403
        )
        created = client.post(
            "/package-import/confirm",
            data=form,
            files={"file": ("project.zip", raw)},
            follow_redirects=False,
        )
        assert created.status_code == 303, created.text
        location = created.headers["location"]
        local_id = location.split("/")[2]
        assert local_id != draft_id
        page = client.get(location)
        assert page.status_code == 200 and "Imported editable project" in page.text
        assert "Foreign sources and approval claims remain unverified" in page.text
        assert client.get(location + "/download").content == raw
        assert (
            "Imported package, original reports and history"
            in client.get(f"/scopes/{local_id}").text
        )
        # Session-bound token is consumed after this explicit successful confirmation.
        assert (
            client.post(
                "/package-import/confirm", data=form, files={"file": ("project.zip", raw)}
            ).status_code
            == 409
        )
        selected_page = client.get(f"/scopes/{local_id}/packages")
        assert selected_page.status_code == 200, selected_page.text
        saved = client.post(
            f"/scopes/{local_id}/packages", data=fields(selected_page), follow_redirects=False
        )
        assert saved.status_code == 303, saved.text
        package_path = saved.headers["location"]
        exported = client.get(package_path + "/download").content
        manifest, members = packages.inspect_archive(exported)
        assert manifest["schema_version"].endswith("v2")
        assert members[manifest["origins"][0]["path"]] == raw
    with TestClient(app.app) as client:
        _login(client)
        assert client.get(location).status_code == 200
        assert client.get(package_path + "/download").content == exported
        _login(client, "other")
        assert client.get(location).status_code in (403, 404)
        assert client.get(location + "/download").status_code in (403, 404)
    _assert_no_canonical_scope(app.factory)
