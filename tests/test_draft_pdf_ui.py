from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_draft_pdf_intake import pdf_bytes
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_scope_ui import _app, _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres_fixture

from classifire.draft_pdf_ui import router
from classifire.models import DraftPdfSource, Estimate, User

pdf_setup = _pdf_setup
postgresql_session_factory = _postgres_fixture
scope_password_hash = _password_hash


@pytest.fixture
def pdf_app(pdf_setup, scope_password_hash, monkeypatch):
    x = pdf_setup
    with x.factory() as db:
        for identifier, name in [(x.ids[0], "owner"), (x.ids[1], "other")]:
            db.execute(
                update(User)
                .where(User.id == identifier)
                .values(email=f"{name}@scope.example.test", password_hash=scope_password_hash)
            )
        db.commit()
    x.app = _app(x.factory)
    x.app.include_router(router)
    monkeypatch.setattr("classifire.draft_pdf_ui.get_settings", lambda: x.settings)
    return x


def upload(client, x):
    path = f"/scopes/{x.ids[2]}/evidence"
    page = client.get(path)
    assert page.status_code == 200
    response = client.post(
        path,
        data={"csrf_token": _csrf(page.text)},
        files={"file": ("synthetic.pdf", pdf_bytes(), "application/pdf")},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    return response.headers["location"]


def test_real_http_upload_scan_preview_and_explicit_review(pdf_app):
    x = pdf_app
    with TestClient(x.app) as client:
        _login(client)
        path = upload(client, x)
        page = client.get(path)
        assert "Scan status: pending" in page.text
        assert client.get(path + "/pages/1.png").status_code == 409
        response = client.post(
            path + "/scan", data={"csrf_token": _csrf(page.text)}, follow_redirects=False
        )
        assert response.status_code == 303, response.text
        page = client.get(path)
        assert "Scan status: clean" in page.text
        assert "Synthetic evidence only" in page.text
        image = client.get(path + "/pages/1.png")
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
        assert image.headers["cache-control"] == "no-store"
        source_hash = re.search(r'name="document_hash" value="([^"]+)"', page.text).group(1)
        values = {
            "csrf_token": _csrf(page.text),
            "revision": "1",
            "page": "1",
            "document_hash": source_hash,
            "reviewed": "yes",
            "state": "Unresolved",
            "observation": "Shared opening; count remains unresolved.",
        }
        saved = client.post(path + "/review", data=values, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        scope_page = client.get(saved.headers["location"])
        assert "Saved page-review references (1)" in scope_page.text
        downloaded = client.get(f"/scopes/{x.ids[2]}/download?revision=2")
        assert downloaded.status_code == 200
        artifact = downloaded.json()
        assert artifact["evidence_refs"][0]["page_number"] == 1
        assert artifact["content"]["observations"][0]["text"] == values["observation"]
        assert client.post(path + "/review", data=values).status_code == 409
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").content == downloaded.content
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0


def test_csrf_foreign_owner_and_lost_write_permission_refuse(pdf_app):
    x = pdf_app
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        _login(other, "other")
        path = upload(owner, x)
        assert other.get(path).status_code == 404
        assert owner.post(path + "/scan", data={"csrf_token": "wrong"}).status_code == 403
        page = owner.get(path)
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        assert owner.post(path + "/scan", data={"csrf_token": _csrf(page.text)}).status_code == 403
        assert "Scan and prepare PDF pages" not in owner.get(path).text


@pytest.mark.parametrize("filename,content", [("bad.pdf", b"not a PDF"), ("bad.txt", b"%PDF-fake")])
def test_unsupported_uploads_do_not_create_sources(pdf_app, filename, content):
    x = pdf_app
    with TestClient(x.app) as client:
        _login(client)
        path = f"/scopes/{x.ids[2]}/evidence"
        response = client.post(
            path,
            data={"csrf_token": _csrf(client.get(path).text)},
            files={"file": (filename, content, "application/pdf")},
        )
        assert response.status_code == 422
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftPdfSource)) == 0
