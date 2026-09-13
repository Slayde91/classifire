"""Native attachments reuse retained Word evidence without AI or Scope writes."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope_docx import word_bytes
from test_draft_scope_docx_ui import word_app as _word_app
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_draft_workspace_chat import snapshot
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_workspace_word_ui import router
from classifire.models import AuditEvent, DraftScopeDocxSource, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_docx as word
from classifire.services.malware_scan import MalwareScanError

pdf_setup = _pdf_setup
pdf_app = _pdf_app
word_app = _word_app
postgresql_session_factory = _postgres
scope_password_hash = _password_hash


@pytest.fixture
def attachment_app(word_app, monkeypatch):
    x = word_app
    x.app.include_router(router)
    monkeypatch.setattr("classifire.draft_workspace_word_ui.get_settings", lambda: x.settings)

    def no_provider(*args, **kwargs):
        pytest.fail("Attachment, scan and inspection must not call AI")

    monkeypatch.setattr(
        "classifire.services.draft_workspace_chat_transport.OpenAIWorkspaceChatPort.complete",
        no_provider,
    )
    return x


def attach(client, x, *, content=None):
    token = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    response = client.post(
        f"/scopes/{x.ids[2]}/assistant/word/upload",
        data={"csrf_token": token},
        files={"file": ("synthetic.docx", content or word_bytes(), word.MEDIA_TYPE)},
    )
    assert response.status_code == 200, response.text
    return response.json(), token


def test_native_attach_explicit_scan_inspect_and_reopen_leave_scope_unchanged(attachment_app):
    x = attachment_app
    base = f"/scopes/{x.ids[2]}/assistant/word"
    original = word_bytes()
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        document = archive.read("word/document.xml").decode()
    extra = "".join(
        f"<w:p><w:r><w:t>Extra source paragraph {i}</w:t></w:r></w:p>" for i in range(6)
    )
    original = word_bytes(
        extra={"word/document.xml": document.replace("</w:body>", extra + "</w:body>").encode()}
    )
    with x.factory() as db:
        before = scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2])
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(f"/scopes/{x.ids[2]}")
        assert 'class="chat-word-upload"' in page.text
        assert "Files stay in CLASSIFIRE" in page.text
        initial = client.get(base)
        assert initial.status_code == 200 and initial.json()["sources"] == []
        assert initial.headers["cache-control"] == "no-store"
        allowed = {"users", "audit_events", "stored_files", "draft_scope_docx_sources"}
        protected_before = {name: rows for name, rows in snapshot(x).items() if name not in allowed}
        source, token = attach(client, x, content=original)
        assert source["status"] == "pending" and source["ready"] is False
        assert source["sha256"] == hashlib.sha256(original).hexdigest()
        repeated, _ = attach(client, x, content=original)
        assert repeated == source
        path = base + "/" + source["id"]
        assert client.get(path).status_code == 409
        result = client.post(path + "/scan", data={"csrf_token": token})
        assert result.status_code == 200 and result.json()["ready"] is True
        evidence = client.get(path)
        assert evidence.status_code == 200 and evidence.headers["cache-control"] == "no-store"
        data = evidence.json()
        assert 1 <= len(data["blocks"]) <= 5
        assert any("Synthetic D-01" in b["text"] for b in data["blocks"])
        assert data["source_id"] == source["id"]
        assert data["next_after_block"] == 5 and data["total_blocks"] == 9
        second = client.get(path + "?after_block=5").json()
        assert len(second["blocks"]) == 4 and second["next_after_block"] is None
        assert second["pictures"] == []
        assert {p["id"] for p in data["pictures"]} <= {
            p for b in data["blocks"] for p in b["pictures"]
        }
        word_path = f"/scopes/{x.ids[2]}/word/{source['id']}"
        assert client.get(word_path + "/original").content == original
        assert client.get(word_path + "/pictures/picture-1").content.startswith(b"\x89PNG")
        assert client.get(path + "?after_block=-1").status_code == 422
        assert client.get(path + "?after_block=1001").status_code == 422
    with TestClient(x.app) as reopened:
        _login(reopened)
        assert reopened.get(base).json()["sources"][0]["id"] == source["id"]
        assert reopened.get(path).json() == data
    assert {
        name: rows for name, rows in snapshot(x).items() if name not in allowed
    } == protected_before
    with x.factory() as db:
        assert scopes.revision_bytes(db, db.get(User, x.ids[0]), x.ids[2]) == before
        assert db.scalar(select(func.count()).select_from(DraftScopeDocxSource)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "draft_scope_docx.upload")
            )
            == 1
        )


def test_native_attachment_denials_do_not_mutate_state(attachment_app):
    x = attachment_app
    base = f"/scopes/{x.ids[2]}/assistant/word"
    with TestClient(x.app) as client, TestClient(x.app) as other:
        _login(client)
        _login(other, "other")
        source, token = attach(client, x)
        path = base + "/" + source["id"]
        other_token = _csrf(other.get("/scopes").text)
        before = snapshot(x)
        assert other.get(base).status_code == 404
        assert other.get(path).status_code == 404
        assert other.post(path + "/scan", data={"csrf_token": other_token}).status_code == 404
        assert (
            other.post(
                base + "/upload",
                data={"csrf_token": other_token},
                files={"file": ("new.docx", word_bytes(), word.MEDIA_TYPE)},
            ).status_code
            == 404
        )
        assert client.post(path + "/scan", data={"csrf_token": "wrong"}).status_code == 403
        assert (
            client.post(path + "/scan", data={"csrf_token": token, "confirm": "yes"}).status_code
            == 422
        )
        assert (
            client.post(
                base + "/upload",
                data={"csrf_token": "wrong"},
                files={"file": ("new.docx", word_bytes(), word.MEDIA_TYPE)},
            ).status_code
            == 403
        )
        assert (
            client.post(
                base + "/upload",
                data={"csrf_token": token},
                files={"file": ("wrong.pdf", b"%PDF-fake", "application/pdf")},
            ).status_code
            == 422
        )
        assert snapshot(x) == before
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        before = snapshot(x)
        assert client.get(base).json()["can_write"] is False
        assert client.post(path + "/scan", data={"csrf_token": token}).status_code == 403
        assert (
            client.post(
                base + "/upload",
                data={"csrf_token": token},
                files={"file": ("new.docx", word_bytes(), word.MEDIA_TYPE)},
            ).status_code
            == 403
        )
        assert snapshot(x) == before


def test_failed_and_expired_scan_cannot_expose_evidence(attachment_app, monkeypatch):
    x = attachment_app
    with TestClient(x.app) as client:
        _login(client)
        source, token = attach(client, x)
        path = f"/scopes/{x.ids[2]}/assistant/word/{source['id']}"

        def failure(*args, **kwargs):
            raise MalwareScanError("SCANNER_UNAVAILABLE")

        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", failure)
        result = client.post(path + "/scan", data={"csrf_token": token})
        assert result.status_code == 200
        assert result.json()["status"] == "scan_error" and result.json()["ready"] is False
        assert client.get(path).status_code == 409
        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", x.clean)
        assert client.post(path + "/scan", data={"csrf_token": token}).json()["ready"] is True
        with x.factory() as db:
            row = db.get(DraftScopeDocxSource, source["id"])
            scan = json.loads(row.scan_json)
            scan["database_date"] = (datetime.now(UTC) - timedelta(days=10)).isoformat()
            row.scan_json = json.dumps(scan)
            db.commit()
        before = snapshot(x)
        assert client.get(path).status_code == 409
        assert snapshot(x) == before
