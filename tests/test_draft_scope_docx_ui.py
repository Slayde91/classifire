from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope_docx import word_bytes
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_scope_docx_ui import router
from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_docx as word
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
postgresql_session_factory = _postgres
scope_password_hash = _password_hash


@pytest.fixture
def word_app(pdf_app, monkeypatch):
    pdf_app.app.include_router(router)
    monkeypatch.setattr("classifire.draft_scope_docx_ui.get_settings", lambda: pdf_app.settings)
    return pdf_app


def test_word_upload_scan_reopen_original_and_quarantine(word_app):
    x = word_app
    content = word_bytes()
    base = f"/scopes/{x.ids[2]}/word"
    with x.factory() as db:
        original_scope = scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2])
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(base)
        assert page.status_code == 200
        response = client.post(
            base + "/upload",
            data={"csrf_token": _csrf(page.text)},
            files={"file": ("synthetic.docx", content, word.MEDIA_TYPE)},
            follow_redirects=False,
        )
        assert response.status_code == 303, response.text
        path = response.headers["location"]
        assert client.get(path + "/original").status_code == 409
        page = client.get(path)
        assert "pending" in page.text
        response = client.post(
            path + "/scan", data={"csrf_token": _csrf(page.text)}, follow_redirects=False
        )
        assert response.status_code == 303, response.text
        page = client.get(path)
        assert page.status_code == 200
        assert "Synthetic D-01" in page.text
        assert "body-2/row-1/cell-2/p-1" in page.text
        assert "not Word page numbers" in page.text
        assert client.get(path + "/pictures/picture-1").content.startswith(b"\x89PNG")
        downloaded = client.get(path + "/original")
        assert downloaded.status_code == 200 and downloaded.content == content
        assert downloaded.headers["cache-control"] == "no-store"
        assert client.get(path + "/pictures/picture-2").status_code == 404
    with TestClient(x.app) as reopened:
        _login(reopened)
        assert "Synthetic D-01" in reopened.get(path).text
        assert reopened.get(path + "/original").content == content
    with TestClient(x.app) as foreign:
        _login(foreign, "other")
        assert foreign.get(path + "/original").status_code in {403, 404}
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert scopes.revision_bytes(db, actor, x.ids[2]) == original_scope
        source, _, verified = word.intake()._document(
            db, actor, x.ids[2], path.rsplit("/", 1)[1], x.settings.storage_root
        )
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=source.stored_file_id,
            observed_sha256=verified.sha256,
            observed_size_bytes=verified.size_bytes,
        )
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(path + "/original").status_code == 409
        assert client.get(path + "/pictures/picture-1").status_code == 409
