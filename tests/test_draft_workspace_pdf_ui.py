"""PDF panel intake shares the Word adapter without implicit model or Scope work."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import update
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import snapshot
from test_draft_workspace_word_ui import attachment_app as _attachment_app
from test_draft_workspace_word_ui import pdf_app as _pdf_app
from test_draft_workspace_word_ui import pdf_setup as _pdf_setup
from test_draft_workspace_word_ui import postgresql_session_factory as _postgres
from test_draft_workspace_word_ui import scope_password_hash as _password_hash
from test_draft_workspace_word_ui import word_app as _word_app

from classifire.models import DraftPdfSource, User
from classifire.services import draft_pdf_intake as intake
from classifire.services.malware_scan import MalwareScanError

attachment_app = _attachment_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


def pages_pdf():
    output = io.BytesIO()
    canvas = Canvas(output)
    for label in ("Synthetic PDF first page", "Synthetic PDF second page"):
        canvas.drawString(60, 760, label)
        canvas.drawString(60, 730, "Blank opening; dimensions and substrate unknown.")
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def attach_pdf(client, x, original=None):
    base = f"/scopes/{x.ids[2]}/assistant/pdf"
    token = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    response = client.post(
        base + "/upload",
        data={"csrf_token": token},
        files={"file": ("synthetic.pdf", original or pages_pdf(), "application/pdf")},
    )
    assert response.status_code == 200, response.text
    return base + "/" + response.json()["id"], response.json(), token


def test_native_pdf_scan_pages_original_reopen_and_format_isolation(attachment_app):
    x = attachment_app
    original = pages_pdf()
    allowed = {"users", "audit_events", "stored_files", "draft_pdf_sources"}
    with TestClient(x.app) as client:
        _login(client)
        initial = snapshot(x)
        path, source, token = attach_pdf(client, x, original)
        assert not source["ready"] and source["status"] == "pending"
        assert source["sha256"] == hashlib.sha256(original).hexdigest()
        assert attach_pdf(client, x, original)[1] == source
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        assert client.get(path.replace("assistant/pdf", "assistant/word")).status_code == 404
        assert client.get(path.rsplit("/", 1)[0].replace("/pdf", "/word")).json()["sources"] == []
        ready = client.post(path + "/scan", data={"csrf_token": token})
        assert ready.status_code == 200 and ready.json()["ready"]
        first = client.get(path)
        second = client.get(path + "?page=2")
        assert first.status_code == second.status_code == 200
        assert first.headers["cache-control"] == "no-store"
        assert first.json()["total_pages"] == 2
        assert "first page" in first.json()["page"]["text"]
        assert "second page" not in first.json()["page"]["text"]
        assert "second page" in second.json()["page"]["text"]
        assert first.json()["page"]["locator_key"] != second.json()["page"]["locator_key"]
        assert client.get(path + "?page=3").status_code == 404
        assert client.get(path + "?page=0").status_code == 422
        assert client.get(path + "?after_block=5").status_code == 404
        download = client.get(path + "/original")
        assert (
            download.content == original and download.headers["content-type"] == "application/pdf"
        )
        assert download.headers["content-disposition"].startswith("attachment;")
        assert download.headers["x-content-type-options"] == "nosniff"
        normal = f"/scopes/{x.ids[2]}/evidence/{source['id']}"
        assert client.get(normal + "/pages/2.png").content.startswith(b"\x89PNG")
        review = client.get(normal + "?page=2")
        assert review.status_code == 200 and "second page" in review.text
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(path + "?page=2").json() == second.json()
        assert client.get(path + "/original").content == original
    assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
        k: v for k, v in initial.items() if k not in allowed
    }


def test_native_pdf_session_rights_csrf_and_format_denials(attachment_app):
    x = attachment_app
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        _login(other, "other")
        path, source, token = attach_pdf(owner, x)
        base = path.rsplit("/", 1)[0]
        other_token = _csrf(other.get("/scopes").text)
        before = snapshot(x)
        for target in (base, path, path + "/original"):
            assert other.get(target).status_code == 404
        assert other.post(path + "/scan", data={"csrf_token": other_token}).status_code == 404
        assert owner.post(path + "/scan", data={"csrf_token": "bad"}).status_code == 403
        assert (
            owner.post(path + "/scan", data={"csrf_token": token, "save": "yes"}).status_code == 422
        )
        for filename, content, csrf, status in (
            ("wrong.docx", b"PK00", token, 422),
            ("wrong.pdf", b"not a pdf", token, 422),
            ("empty.pdf", b"", token, 422),
            ("valid.pdf", pages_pdf(), "bad", 403),
        ):
            result = owner.post(
                base + "/upload",
                data={"csrf_token": csrf},
                files={"file": (filename, content, "application/pdf")},
            )
            assert result.status_code == status
        assert owner.get(base.replace("/pdf", "/unsupported")).status_code == 422
        assert snapshot(x) == before
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        before = snapshot(x)
        assert owner.get(base).json()["can_write"] is False
        assert owner.post(path + "/scan", data={"csrf_token": token}).status_code == 403
        assert (
            owner.post(
                base + "/upload",
                data={"csrf_token": token},
                files={"file": ("valid.pdf", pages_pdf(), "application/pdf")},
            ).status_code
            == 403
        )
        assert snapshot(x) == before


def test_native_pdf_failed_expired_and_corrupt_sources_are_withheld(attachment_app, monkeypatch):
    x = attachment_app
    with TestClient(x.app) as client:
        _login(client)
        path, source, token = attach_pdf(client, x)

        def unavailable(*args, **kwargs):
            raise MalwareScanError("SCANNER_UNAVAILABLE")

        monkeypatch.setattr(intake.malware_scan, "scan_bytes", unavailable)
        failed = client.post(path + "/scan", data={"csrf_token": token})
        assert failed.json()["status"] == "scan_error" and not failed.json()["ready"]
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        monkeypatch.setattr(intake.malware_scan, "scan_bytes", x.clean)
        assert client.post(path + "/scan", data={"csrf_token": token}).json()["ready"]
        with x.factory() as db:
            row = db.get(DraftPdfSource, source["id"])
            scan = json.loads(row.scan_json)
            scan["database_date"] = (datetime.now(UTC) - timedelta(days=10)).isoformat()
            row.scan_json = json.dumps(scan)
            db.commit()
        before = snapshot(x)
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        assert snapshot(x) == before
        assert client.post(path + "/scan", data={"csrf_token": token}).json()["ready"]
        with x.factory() as db:
            row = db.get(DraftPdfSource, source["id"])
            row.document_sha256 = "0" * 64
            db.commit()
        before = snapshot(x)
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        assert snapshot(x) == before
