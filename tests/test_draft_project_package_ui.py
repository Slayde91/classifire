from __future__ import annotations

import html
import json
import re

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_scope_ui import (  # noqa: F401
    _assert_no_canonical_scope,
    _create,
    _login,
    scope_app,
    scope_password_hash,
)  # noqa: F401

from classifire.draft_project_package_ui import router
from classifire.models import AuditEvent, DraftProjectPackage, User
from classifire.services import draft_project_packages as packages


def fields(response):
    return {
        name: html.unescape(value)
        for name, value in re.findall(
            r'<input type="hidden" name="([^"]+)" value="([^"]*)">', response.text
        )
    }


def test_package_browser_api_preview_save_download_and_rights(scope_app):  # noqa: F811
    app = scope_app
    app.app.include_router(router)
    with TestClient(app.app) as client:
        _login(client)
        path = _create(client) + "/packages"
        with app.factory() as db:
            before = db.scalar(select(func.count()).select_from(AuditEvent))
        preview = client.get(path)
        assert preview.status_code == 200
        assert "Package contents" in preview.text and "Save package revision 1" in preview.text
        with app.factory() as db:
            assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 0
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == before
        form = fields(preview)
        assert client.post(path, data={**form, "csrf_token": "bad"}).status_code == 403
        response = client.post(path, data=form, follow_redirects=False)
        assert response.status_code == 303
        saved = response.headers["location"]
        assert "Download saved project ZIP" in client.get(saved).text
        zip_response = client.get(saved + "/download")
        assert (
            zip_response.status_code == 200 and zip_response.headers["cache-control"] == "no-store"
        )
        manifest, members = packages.inspect_archive(zip_response.content)
        assert json.loads(members["artifacts/scope.json"])["revision"] == 1
        assert manifest["revision"] == 1
        assert client.post(path, data=form).status_code == 409
        assert client.get(path + "?scope_revision=1&scope_revision=2").status_code == 422
        assert (
            client.post(
                path,
                content=b"x" * 8193,
                headers={"content-type": "application/x-www-form-urlencoded"},
            ).status_code
            == 413
        )
        with app.factory() as db:
            user = db.get(User, app.users["owner"])
            user.role = "read_only"
            db.commit()
        assert client.get(saved + "/download").content == zip_response.content
        assert client.post(path, data=form).status_code == 403
    with TestClient(app.app) as client:
        _login(client, "other")
        assert client.get(saved).status_code == 404
        assert client.get(saved + "/download").status_code == 404
    _assert_no_canonical_scope(app.factory)
