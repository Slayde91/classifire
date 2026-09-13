"""Native Excel inspection reuses retained Scope evidence, never pricing or AI."""

from __future__ import annotations

import hashlib
import io
import json
from datetime import UTC, datetime, timedelta

import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import update
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import snapshot
from test_draft_workspace_word_ui import attachment_app as _attachment_app
from test_draft_workspace_word_ui import pdf_app as _pdf_app
from test_draft_workspace_word_ui import pdf_setup as _pdf_setup
from test_draft_workspace_word_ui import postgresql_session_factory as _postgres
from test_draft_workspace_word_ui import scope_password_hash as _password_hash
from test_draft_workspace_word_ui import word_app as _word_app

from classifire import draft_scope_xlsx_ui
from classifire.models import DraftScopeXlsxSource, User
from classifire.services import draft_pricing_intake as pricing
from classifire.services import draft_scope_xlsx as xlsx
from classifire.services.draft_scope import DraftScopeError
from classifire.services.malware_scan import MalwareScanError

attachment_app = _attachment_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


def register_bytes():
    output, picture = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(picture, format="PNG")
    book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False})
    sheet = book.add_worksheet("Defects")
    sheet.write_row(0, 0, ["Defect", "Description", "Quantity"])
    for index in range(1, 8):
        sheet.write_row(index, 0, [f"D-{index:02}", "Relationship and dimensions unknown"])
    sheet.write_formula(1, 2, "=1+1", None, 2)
    sheet.write_string(2, 1, "<script>untrusted report instructions</script>")
    sheet.insert_image("B2", "picture.png", {"image_data": picture})
    second = book.add_worksheet("Other sheet")
    second.write_row(0, 0, ["Other notes", "Not selected"])
    book.close()
    return output.getvalue()


@pytest.fixture
def xlsx_attachment_app(attachment_app, monkeypatch):
    x = attachment_app
    x.app.include_router(draft_scope_xlsx_ui.router)
    monkeypatch.setattr(draft_scope_xlsx_ui, "get_settings", lambda: x.settings)
    return x


def attach(client, x, original):
    base = f"/scopes/{x.ids[2]}/assistant/xlsx"
    token = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    response = client.post(
        base + "/upload",
        data={"csrf_token": token},
        files={"file": ("synthetic.xlsx", original, xlsx.intake().policy.media_type)},
    )
    assert response.status_code == 200, response.text
    return base + "/" + response.json()["id"], response.json(), token


def test_native_xlsx_pages_formula_images_original_and_reopen(xlsx_attachment_app):
    x = xlsx_attachment_app
    original = register_bytes()
    allowed = {"users", "audit_events", "stored_files", "draft_scope_xlsx_sources"}
    with TestClient(x.app) as client:
        _login(client)
        before = snapshot(x)
        path, source, token = attach(client, x, original)
        assert not source["ready"] and source["status"] == "pending"
        assert source["sha256"] == hashlib.sha256(original).hexdigest()
        assert attach(client, x, original)[1] == source
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        ready = client.post(path + "/scan", data={"csrf_token": token})
        assert ready.status_code == 200 and ready.json()["ready"], ready.text
        first = client.get(path)
        assert first.headers["cache-control"] == "no-store"
        value = first.json()
        assert value["sheet"]["name"] == "Defects" and value["sheet"]["rows"] == 8
        assert value["start_row"] == 1 and value["end_row"] == 5 and value["next_row"] == 6
        assert [s["index"] for s in value["sheets"]] == [1, 2]
        assert {c["row"] for c in value["cells"]} == {1, 2, 3, 4, 5}
        formula = next(c for c in value["cells"] if c["address"] == "C2")
        assert formula["kind"] == "formula" and formula["value"] == "=1+1"
        assert any(c["value"].startswith("<script>") for c in value["cells"])
        assert len(value["images"]) == 1 and value["omitted_images"] == 0
        image = value["images"][0]
        normal = f"/scopes/{x.ids[2]}/workbooks/{source['id']}"
        picture = client.get(normal + f"/images/1/{image['occurrence_id']}.png")
        assert picture.status_code == 200 and picture.content.startswith(b"\x89PNG")
        assert hashlib.sha256(picture.content).hexdigest() == image["preview_sha256"]
        last = client.get(path + "?sheet=1&row=6").json()
        assert last["next_row"] is None and {c["row"] for c in last["cells"]} == {6, 7, 8}
        assert not last["images"] and last["omitted_images"] == 1
        second = client.get(path + "?sheet=2").json()
        assert second["sheet"]["name"] == "Other sheet" and len(second["cells"]) == 2
        assert not second["images"]
        review = client.get(normal + "?sheet=2&row=1")
        assert review.status_code == 200 and "Other notes" in review.text
        assert "Formulas are shown as source text and never evaluated" in review.text
        assert "<script>untrusted report instructions" not in review.text
        downloaded = client.get(path + "/original")
        assert downloaded.content == original
        assert downloaded.headers["content-type"] == xlsx.intake().policy.media_type
        assert downloaded.headers["content-disposition"].startswith("attachment;")
        assert downloaded.headers["cache-control"] == "no-store"
        for query, status in (
            ("sheet=0", 422),
            ("sheet=11", 422),
            ("sheet=3", 404),
            ("row=0", 422),
            ("row=9", 404),
            ("row=1001", 422),
            ("page=2", 422),
            ("after_block=1", 422),
        ):
            assert client.get(path + "?" + query).status_code == status
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(path + "?sheet=2").json() == second
        assert client.get(path + "/original").content == original
    assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
        k: v for k, v in before.items() if k not in allowed
    }


def test_native_xlsx_rights_csrf_and_source_purpose_isolation(xlsx_attachment_app):
    x = xlsx_attachment_app
    original = register_bytes()
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        _login(other, "other")
        path, source, token = attach(owner, x, original)
        base = path.rsplit("/", 1)[0]
        other_token = _csrf(other.get("/scopes").text)
        before = snapshot(x)
        for endpoint in (base, path, path + "/original"):
            assert other.get(endpoint).status_code == 404
        assert other.post(path + "/scan", data={"csrf_token": other_token}).status_code == 404
        assert owner.post(path + "/scan", data={"csrf_token": "bad"}).status_code == 403
        assert (
            owner.post(path + "/scan", data={"csrf_token": token, "save": "yes"}).status_code == 422
        )
        for kind in ("word", "pdf"):
            assert owner.get(path.replace("assistant/xlsx", "assistant/" + kind)).status_code == 404
            assert owner.get(base.replace("/xlsx", "/" + kind)).json()["sources"] == []
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            with pytest.raises(DraftScopeError):
                pricing.intake()._document(
                    db, actor, x.ids[2], source["id"], x.settings.storage_root
                )
            with pytest.raises(DraftScopeError, match="PRICING_XLSX_UPLOAD_CONFLICT"):
                pricing.intake().retain(
                    db, actor, x.ids[2], "synthetic.xlsx", original, settings=x.settings
                )
        for filename, content, csrf, status in (
            ("wrong.docx", original, token, 422),
            ("wrong.xlsx", b"not a workbook", token, 422),
            ("empty.xlsx", b"", token, 422),
            ("valid.xlsx", original, "bad", 403),
        ):
            assert (
                owner.post(
                    base + "/upload",
                    data={"csrf_token": csrf},
                    files={"file": (filename, content, xlsx.intake().policy.media_type)},
                ).status_code
                == status
            )
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
                files={"file": ("valid.xlsx", original, xlsx.intake().policy.media_type)},
            ).status_code
            == 403
        )
        assert snapshot(x) == before


def test_native_xlsx_failed_expired_corrupt_sources_withhold_reads(
    xlsx_attachment_app, monkeypatch
):
    x = xlsx_attachment_app
    with TestClient(x.app) as client:
        _login(client)
        path, source, token = attach(client, x, register_bytes())

        def unavailable(*args, **kwargs):
            raise MalwareScanError("SCANNER_UNAVAILABLE")

        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", unavailable)
        failed = client.post(path + "/scan", data={"csrf_token": token})
        assert failed.json()["status"] == "scan_error" and not failed.json()["ready"]
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        monkeypatch.setattr("classifire.services.malware_scan.scan_bytes", x.clean)
        assert client.post(path + "/scan", data={"csrf_token": token}).json()["ready"]
        with x.factory() as db:
            source = db.get(DraftScopeXlsxSource, source["id"])
            scan = json.loads(source.scan_json)
            scan["database_date"] = (datetime.now(UTC) - timedelta(days=10)).isoformat()
            source.scan_json = json.dumps(scan)
            db.commit()
        before = snapshot(x)
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        assert snapshot(x) == before
        assert client.post(path + "/scan", data={"csrf_token": token}).json()["ready"]
        with x.factory() as db:
            row = db.get(DraftScopeXlsxSource, path.rsplit("/", 1)[1])
            row.document_sha256 = "0" * 64
            db.commit()
        before = snapshot(x)
        assert client.get(path).status_code == client.get(path + "/original").status_code == 409
        assert snapshot(x) == before
