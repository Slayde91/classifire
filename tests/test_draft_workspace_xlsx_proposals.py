"""Native Excel cell evidence and additions keep disclosure and save separate."""

from __future__ import annotations

import base64
import copy
import hashlib
import html
import io
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
import xlsxwriter
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import update
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import response_body, snapshot
from test_draft_workspace_word_evidence import evidence_app as _evidence_app
from test_draft_workspace_word_evidence import pdf_app as _pdf_app
from test_draft_workspace_word_evidence import pdf_setup as _pdf_setup
from test_draft_workspace_word_evidence import postgresql_session_factory as _postgres
from test_draft_workspace_word_evidence import scope_password_hash as _password_hash
from test_draft_workspace_word_evidence import word_app as _word_app

from classifire import draft_scope_xlsx_ui
from classifire.draft_workspace_word_ui import router
from classifire.models import DraftScopeXlsxSource, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_xlsx as xlsx
from classifire.services import draft_workspace_chat as chat
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort
from classifire.services.draft_workspace_word_proposals import XlsxMapping, validate_output

evidence_app = _evidence_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


def proposal_workbook():
    output, picture = io.BytesIO(), io.BytesIO()
    Image.new("RGB", (12, 8), "red").save(picture, format="PNG")
    book = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False})
    sheet = book.add_worksheet("Defects")
    sheet.write_row(0, 0, ["Defect", "Opening", "Quantity"])
    sheet.write_row(1, 0, ["D-01", "Blank opening", None])
    sheet.write_row(2, 0, ["D-02", "Not selected", None])
    sheet.write_row(3, 0, ["D-03", "Formula row", None])
    sheet.write_formula(3, 2, "=1+1", None, 2)
    sheet.insert_image("B2", "picture.png", {"image_data": picture})
    book.add_worksheet("Other sheet").write_row(0, 0, ["Other sheet evidence excluded"])
    book.close()
    return output.getvalue()


@pytest.fixture
def xlsx_evidence_app(evidence_app, monkeypatch):
    x = evidence_app
    x.app.include_router(router)
    x.app.include_router(draft_scope_xlsx_ui.router)
    monkeypatch.setattr("classifire.draft_workspace_word_ui.get_settings", lambda: x.settings)
    monkeypatch.setattr(draft_scope_xlsx_ui, "get_settings", lambda: x.settings)
    x.xlsx_original = proposal_workbook()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = xlsx.intake().retain(
            db, actor, x.ids[2], "synthetic.xlsx", x.xlsx_original, settings=x.settings
        )
        xlsx.intake().scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        x.xlsx_selection = {
            "source_id": source.id,
            "document_sha256": source.document_sha256,
            "sheet_index": 1,
            "header_row": 1,
            "rows": [2],
            "picture_ids": ["image-1"],
        }
        x.png = xlsx.image_preview(
            db, actor, x.ids[2], source.id, 1, "image-1", settings=x.settings
        )
        db.commit()
    return x


def proposal(context):
    evidence = context["xlsx_evidence"]
    graph = scopes.DraftScopePayload.model_validate(
        {
            "defects": [{"id": str(UUID(int=7001)), "label": "Synthetic Excel defect"}],
            "openings": [
                {
                    "id": str(UUID(int=7002)),
                    "label": "Blank opening",
                    "blank": True,
                    "defect_id": str(UUID(int=7001)),
                }
            ],
        }
    ).model_dump(mode="json")
    return {
        "answer": "Review the proposed blank opening.",
        "record_ids": [],
        "source_ids": [evidence["source_id"]],
        "uncertainty": ["Dimensions and substrate remain unknown."],
        "additions": graph,
        "mapping": {
            field: (1 if field == "defect_label" else 2 if field == "opening_label" else None)
            for field in XlsxMapping.model_fields
        },
        "claims": [
            {
                "target_kind": kind,
                "target_id": row["id"],
                "locator": evidence["blocks"][0]["locator"],
                "image_ids": [image["id"] for image in evidence["pictures"]],
                "basis": ("both" if evidence["pictures"] else "text")
                if evidence["blocks"]
                else "picture",
                "quote": "Blank opening" if evidence["blocks"] else "",
                "rationale": "Scripted source-bound proposal, not accuracy evidence.",
            }
            for kind in ("defect", "opening")
            for row in graph[kind + "s"]
        ],
    }


def provider(x, transform=lambda value: value, callback=lambda: None):
    def respond(req):
        body = json.loads(req.content)
        x.calls.append(body)
        content = body["input"][0]["content"]
        context = json.loads(content[0]["text"] if isinstance(content, list) else content)[
            "selected_saved_context"
        ]
        callback()
        value = (
            proposal(context)
            if "proposal" in body["text"]["format"]["name"]
            else {
                "answer": "Selected Excel remains unverified.",
                "uncertainty": ["Dimensions unknown."],
                "record_ids": [],
                "source_ids": [x.xlsx_selection["source_id"]],
            }
        )
        result = response_body()
        result["output"][0]["content"][0]["text"] = json.dumps(transform(value))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(result).encode()),
        )

    x.app.state.workspace_chat_port = OpenAIWorkspaceChatPort(
        x.settings, transport=httpx.MockTransport(respond)
    )


def start(client, x, *, action="propose_xlsx_scope", selection=None):
    _login(client)
    csrf = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    headers = {"X-CSRF-Token": csrf}
    value = {
        "screen": {"name": "scopes"},
        "draft_id": x.ids[2],
        "revision": 1,
        "xlsx": selection or copy.deepcopy(x.xlsx_selection),
        "action": action,
        "question": "Review the selected page and preserve unknowns.",
    }
    response = client.post("/workspace/assistant/context", json=value, headers=headers)
    assert response.status_code == 200, response.text
    value.update(consent=True, context_sha256=response.json()["context_sha256"])
    return value, headers, csrf, response.json()


def test_xlsx_exact_disclosure_proposal_separate_confirm_and_reopen(xlsx_evidence_app):
    x = xlsx_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, csrf, context = start(client, x)
        evidence = context["xlsx_evidence"]
        assert "word_evidence" not in context and "pdf_evidence" not in context
        assert evidence["omitted_sheets"] == 1 and evidence["omitted_blocks"] == 2
        assert evidence["header"]["row"] == 1 and len(evidence["header"]["cells"]) == 3
        assert "Not selected" not in json.dumps(
            context
        ) and "Other sheet evidence" not in json.dumps(context)
        assert "data:image" not in json.dumps(context)
        before = snapshot(x)
        assert (
            client.post(
                "/workspace/assistant/message", json=value | {"consent": False}, headers=headers
            ).status_code
            == 422
        )
        assert not x.calls
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()["proposal"]
        assert snapshot(x) == before and len(x.calls) == 1
        body = x.calls[0]
        assert body["text"]["format"]["name"] == "workspace_xlsx_proposal"
        assert body["tools"] == [] and body["store"] is False
        png = base64.b64decode(body["input"][0]["content"][2]["image_url"].split(",", 1)[1])
        assert (
            png == x.png
            and hashlib.sha256(png).hexdigest() == evidence["pictures"][0]["preview_sha256"]
        )
        assert result["source_kind"] == "xlsx" and result["plan"]["mapping"]["opening_label"] == 2
        assert not result["payload"]["services"] and result["additions"]["openings"][0]["blank"]
        assert result["additions"]["openings"][0]["width_mm"] is None
        form = {
            "csrf_token": csrf,
            "expected_revision": "1",
            "document_sha256": x.xlsx_selection["document_sha256"],
            "payload": json.dumps(result["payload"]),
            "targets": json.dumps(result["targets"]),
            "plan": json.dumps(result["plan"]),
        }
        path = f"/scopes/{x.ids[2]}/workbooks/{x.xlsx_selection['source_id']}"
        assert client.post(path + "/confirm", data=form).status_code == 422
        reviewed = client.post(path + "/preview", data=form)
        assert reviewed.status_code == 200 and 'id="xlsx-scope-confirm"' in reviewed.text
        assert snapshot(x) == before
        token = html.unescape(re.search(r'name="preview_token" value="([^\"]+)"', reviewed.text)[1])
        confirm = form | {"preview_token": token, "confirm": "save"}
        forged = copy.deepcopy(result["plan"])
        forged["mapping"]["opening_label"] = 1
        assert (
            client.post(path + "/confirm", data=confirm | {"plan": json.dumps(forged)}).status_code
            == 409
        )
        assert snapshot(x) == before
        saved = client.post(path + "/confirm", data=confirm, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        assert client.post(path + "/confirm", data=confirm).status_code == 409
        assert (
            client.post("/workspace/assistant/message", json=value, headers=headers).status_code
            == 409
        )
        envelope = client.get(f"/scopes/{x.ids[2]}/download?revision=2").json()
        assert envelope["content"] == result["payload"] and len(envelope["evidence_refs"]) == 2
        assert {ref["method"] for ref in envelope["evidence_refs"]} == {
            "human_xlsx_row_entity_review"
        }
        for ref in envelope["evidence_refs"]:
            assert ref["row"]["fields"]["opening_label"]["value"] == "Blank opening"
            assert ref["row"]["row"] == 2 and ref["images"][0]["occurrence_id"] == "image-1"
        allowed = {"draft_scopes", "draft_scope_revisions", "audit_events"}
        assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
            k: v for k, v in before.items() if k not in allowed
        }
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").json() == envelope
        assert (
            client.get(
                f"/scopes/{x.ids[2]}/assistant/xlsx/{x.xlsx_selection['source_id']}/original"
            ).content
            == x.xlsx_original
        )


def test_xlsx_text_only_advice_excludes_pictures(xlsx_evidence_app):
    x = xlsx_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, context = start(
            client, x, action="advice", selection=x.xlsx_selection | {"picture_ids": []}
        )
        assert not context["xlsx_evidence"]["pictures"]
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 200 and snapshot(x) == before
        assert isinstance(x.calls[0]["input"][0]["content"], str)


def pure_context():
    return {
        "xlsx_evidence": {
            "source_id": str(UUID(int=7000)),
            "sheet": {"index": 1, "columns": 3},
            "header": {"row": 1, "cells": []},
            "blocks": [
                {
                    "locator": "xlsx:1:2",
                    "row": 2,
                    "text": "B2 (text): Blank opening",
                    "cells": [
                        {
                            "address": "B2",
                            "column": 2,
                            "row": 2,
                            "kind": "text",
                            "value": "Blank opening",
                        }
                    ],
                }
            ],
            "pictures": [],
        }
    }


@pytest.mark.parametrize(
    "change",
    [
        "row",
        "quote",
        "picture",
        "confirmed",
        "missing",
        "unbound",
        "mapping_range",
        "mapping_bool",
        "mapping_missing",
        "unmapped",
        "formula",
    ],
)
def test_xlsx_invalid_claims_and_mapping_are_rejected(change):
    context = pure_context()
    value = proposal(context)
    if change == "row":
        value["claims"][0]["locator"] = "xlsx:1:3"
    if change == "quote":
        value["claims"][0]["quote"] = "invented"
    if change == "picture":
        value["claims"][0].update(image_ids=["image-2"], basis="both")
    if change == "confirmed":
        value["additions"]["openings"][0]["state"] = "Confirmed"
    if change == "missing":
        del value["additions"]["openings"][0]["width_mm"]
    if change == "unbound":
        value["claims"].pop()
    if change == "mapping_range":
        value["mapping"]["opening_label"] = 4
    if change == "mapping_bool":
        value["mapping"]["opening_label"] = True
    if change == "mapping_missing":
        del value["mapping"]["quantity"]
    if change == "unmapped":
        value["mapping"]["opening_label"] = None
    if change == "formula":
        context["xlsx_evidence"]["blocks"][0]["cells"][0]["kind"] = "formula"
    with pytest.raises((ValueError, scopes.DraftScopeError)):
        validate_output(value, context, source_kind="xlsx")


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "header",
        "sheet",
        "bool",
        "browser_text",
        "mixed",
        "no_xlsx",
        "duplicate",
        "too_many",
    ],
)
def test_xlsx_selector_requires_explicit_bounded_rows(change):
    selection = {
        "source_id": str(UUID(int=7000)),
        "document_sha256": "a" * 64,
        "sheet_index": 1,
        "header_row": 1,
        "rows": [2],
        "picture_ids": [],
    }
    value = {
        "screen": {"name": "scopes"},
        "draft_id": str(UUID(int=1)),
        "revision": 1,
        "question": "Review",
        "xlsx": selection,
        "action": "propose_xlsx_scope",
    }
    if change == "empty":
        selection["rows"] = []
    if change == "header":
        selection["header_row"] = 2
    if change == "sheet":
        selection["sheet_index"] = 11
    if change == "bool":
        selection["rows"] = [True]
    if change == "browser_text":
        selection["text"] = "untrusted browser replacement"
    if change == "mixed":
        value["pdf"] = {
            "source_id": str(UUID(int=2)),
            "document_sha256": "a" * 64,
            "page_number": 1,
            "include_text": True,
        }
    if change == "no_xlsx":
        value["xlsx"] = None
    if change == "duplicate":
        selection["rows"] = [2, 2]
    if change == "too_many":
        selection["rows"] = list(range(2, 13))
    with pytest.raises(scopes.DraftScopeError):
        chat.parse_workspace(value)


@pytest.mark.parametrize("change", ["expired", "permission", "document"])
def test_xlsx_changed_source_or_access_refuses_before_provider(xlsx_evidence_app, change):
    x = xlsx_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, _ = start(client, x)
        with x.factory() as db:
            source = db.get(DraftScopeXlsxSource, x.xlsx_selection["source_id"])
            if change == "expired":
                scan = json.loads(source.scan_json)
                scan["database_date"] = (datetime.now(UTC) - timedelta(days=40)).isoformat()
                source.scan_json = json.dumps(scan)
            if change == "document":
                source.document_sha256 = "0" * 64
            if change == "permission":
                db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == (403 if change == "permission" else 409)
        assert not x.calls and snapshot(x) == before


def test_xlsx_permission_revoked_during_reply_withholds_proposal(xlsx_evidence_app):
    x = xlsx_evidence_app

    def revoke():
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()

    provider(x, callback=revoke)
    with TestClient(x.app) as client:
        value, headers, _, _ = start(client, x)
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert (
            response.status_code == 403 and "proposal" not in response.json() and len(x.calls) == 1
        )
        assert {k: v for k, v in snapshot(x).items() if k != "users"} == {
            k: v for k, v in before.items() if k != "users"
        }


def test_xlsx_row_selection_change_requires_new_preview(xlsx_evidence_app):
    x = xlsx_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, _ = start(client, x)
        before = snapshot(x)
        value["xlsx"]["rows"] = [3]
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 409 and response.json()["detail"] == "CHAT_CONTEXT_CHANGED"
        assert not x.calls and snapshot(x) == before
