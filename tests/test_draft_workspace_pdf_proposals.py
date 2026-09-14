"""Native PDF page evidence and additions keep disclosure and save separate."""

from __future__ import annotations

import base64
import copy
import hashlib
import html
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import response_body, snapshot
from test_draft_workspace_pdf_ui import pages_pdf
from test_draft_workspace_word_evidence import evidence_app as _evidence_app
from test_draft_workspace_word_evidence import pdf_app as _pdf_app
from test_draft_workspace_word_evidence import pdf_setup as _pdf_setup
from test_draft_workspace_word_evidence import postgresql_session_factory as _postgres
from test_draft_workspace_word_evidence import scope_password_hash as _password_hash
from test_draft_workspace_word_evidence import word_app as _word_app

from classifire.draft_workspace_word_ui import router
from classifire.models import DraftPdfSource, User
from classifire.services import draft_pdf_intake as pdf
from classifire.services import draft_scope as scopes
from classifire.services import draft_workspace_chat as chat
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort
from classifire.services.draft_workspace_word_proposals import validate_output

evidence_app = _evidence_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


@pytest.fixture
def pdf_evidence_app(evidence_app, monkeypatch):
    x = evidence_app
    x.app.include_router(router)
    monkeypatch.setattr("classifire.draft_workspace_word_ui.get_settings", lambda: x.settings)
    x.pdf_original = pages_pdf()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = pdf.retain_pdf(
            db, actor, x.ids[2], "synthetic.pdf", x.pdf_original, settings=x.settings
        )
        pdf.scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        x.pdf_selection = {
            "source_id": source.id,
            "document_sha256": source.document_sha256,
            "page_number": 1,
            "include_text": True,
            "include_image": True,
        }
        x.png = pdf.page_preview(db, actor, x.ids[2], source.id, 1, settings=x.settings)
        db.commit()
    return x


def proposal(context):
    evidence = context["pdf_evidence"]
    graph = scopes.DraftScopePayload.model_validate(
        {
            "defects": [{"id": str(UUID(int=7001)), "label": "Synthetic PDF defect"}],
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
        "claims": [
            {
                "target_kind": kind,
                "target_id": row["id"],
                "locator": evidence["page"]["locator"],
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
                "answer": "Selected PDF remains unverified.",
                "uncertainty": ["Dimensions unknown."],
                "record_ids": [],
                "source_ids": [x.pdf_selection["source_id"]],
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


def start(client, x, *, action="propose_pdf_scope", selection=None):
    _login(client)
    csrf = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    headers = {"X-CSRF-Token": csrf}
    value = {
        "screen": {"name": "scopes"},
        "draft_id": x.ids[2],
        "revision": 1,
        "pdf": selection or copy.deepcopy(x.pdf_selection),
        "action": action,
        "question": "Review the selected page and preserve unknowns.",
    }
    response = client.post("/workspace/assistant/context", json=value, headers=headers)
    assert response.status_code == 200, response.text
    value.update(consent=True, context_sha256=response.json()["context_sha256"])
    return value, headers, csrf, response.json()


def test_pdf_exact_disclosure_proposal_separate_confirm_and_reopen(pdf_evidence_app):
    x = pdf_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, csrf, context = start(client, x)
        assert "word_evidence" not in context and context["pdf_evidence"]["omitted_pages"] == 1
        assert "second page" not in json.dumps(context) and "data:image" not in json.dumps(context)
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
        assert body["text"]["format"]["name"] == "workspace_pdf_proposal"
        assert body["tools"] == [] and body["store"] is False
        png = base64.b64decode(body["input"][0]["content"][2]["image_url"].split(",", 1)[1])
        assert png == x.png
        assert (
            hashlib.sha256(png).hexdigest()
            == context["pdf_evidence"]["pictures"][0]["preview_sha256"]
        )
        assert result["source_kind"] == "pdf" and result["page_number"] == 1
        assert not result["payload"]["services"] and result["additions"]["openings"][0]["blank"]
        assert result["additions"]["openings"][0]["width_mm"] is None
        form = {
            "csrf_token": csrf,
            "expected_revision": "1",
            "page": "1",
            "document_hash": x.pdf_selection["document_sha256"],
            "payload": json.dumps(result["payload"]),
            "targets": json.dumps(result["targets"]),
        }
        path = f"/scopes/{x.ids[2]}/evidence/{x.pdf_selection['source_id']}/scope"
        assert client.post(path + "/confirm", data=form).status_code == 422
        reviewed = client.post(path + "/preview", data=form)
        assert reviewed.status_code == 200 and 'id="pdf-scope-confirm"' in reviewed.text
        assert snapshot(x) == before
        token = html.unescape(re.search(r'name="preview_token" value="([^"]+)"', reviewed.text)[1])
        confirm = form | {"preview_token": token, "confirm": "save"}
        assert client.post(path + "/confirm", data=confirm | {"page": "2"}).status_code == 409
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
        assert {ref["method"] for ref in envelope["evidence_refs"]} == {"human_page_entity_review"}
        allowed = {"draft_scopes", "draft_scope_revisions", "audit_events"}
        assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
            k: v for k, v in before.items() if k not in allowed
        }
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").json() == envelope
        original = f"/scopes/{x.ids[2]}/assistant/pdf/{x.pdf_selection['source_id']}/original"
        assert client.get(original).content == x.pdf_original


@pytest.mark.parametrize("image", [False, True])
def test_pdf_text_or_image_only_advice_excludes_unselected_content(pdf_evidence_app, image):
    x = pdf_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, context = start(
            client,
            x,
            action="advice",
            selection=x.pdf_selection | {"include_text": not image, "include_image": image},
        )
        evidence = context["pdf_evidence"]
        assert len(evidence["blocks"]) == int(not image) and len(evidence["pictures"]) == int(image)
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 200 and snapshot(x) == before
        content = x.calls[0]["input"][0]["content"]
        assert isinstance(content, list if image else str)
        if image:
            assert "Blank opening" not in content[0]["text"]


@pytest.mark.parametrize("change", ["page", "quote", "picture", "confirmed", "missing", "unbound"])
def test_pdf_invalid_claims_are_rejected(change):
    context = {
        "pdf_evidence": {
            "source_id": str(UUID(int=7000)),
            "page": {"locator": "page-one"},
            "blocks": [{"locator": "page-one", "text": "Blank opening"}],
            "pictures": [],
        }
    }
    value = proposal(context)
    if change == "page":
        value["claims"][0]["locator"] = "page-two"
    if change == "quote":
        value["claims"][0]["quote"] = "invented"
    if change == "picture":
        value["claims"][0].update(image_ids=["page-2"], basis="both")
    if change == "confirmed":
        value["additions"]["openings"][0]["state"] = "Confirmed"
    if change == "missing":
        del value["additions"]["openings"][0]["width_mm"]
    if change == "unbound":
        value["claims"].pop()
    with pytest.raises((ValueError, scopes.DraftScopeError)):
        validate_output(value, context, source_kind="pdf")


@pytest.mark.parametrize("change", ["empty", "page", "bool", "browser_text", "mixed", "no_pdf"])
def test_pdf_selector_requires_one_explicit_bounded_format(change):
    selection = {
        "source_id": str(UUID(int=7000)),
        "document_sha256": "a" * 64,
        "page_number": 1,
        "include_text": True,
        "include_image": False,
    }
    value = {
        "screen": {"name": "scopes"},
        "draft_id": str(UUID(int=1)),
        "revision": 1,
        "question": "Review",
        "pdf": selection,
        "action": "propose_pdf_scope",
    }
    if change == "empty":
        selection["include_text"] = False
    if change == "page":
        selection["page_number"] = 51
    if change == "bool":
        selection["page_number"] = True
    if change == "browser_text":
        selection["text"] = "untrusted browser replacement"
    if change == "mixed":
        value["word"] = {
            "source_id": str(UUID(int=2)),
            "document_sha256": "a" * 64,
            "locators": ["body-1"],
        }
    if change == "no_pdf":
        value["pdf"] = None
    with pytest.raises(scopes.DraftScopeError):
        chat.parse_workspace(value)


@pytest.mark.parametrize("change", ["expired", "permission", "document"])
def test_pdf_changed_source_or_access_refuses_before_provider(pdf_evidence_app, change):
    x = pdf_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, _ = start(client, x)
        with x.factory() as db:
            source = db.get(DraftPdfSource, x.pdf_selection["source_id"])
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


def test_pdf_permission_revoked_during_reply_withholds_proposal(pdf_evidence_app):
    x = pdf_evidence_app

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


def test_image_only_pdf_proposal_cannot_claim_unselected_text():
    context = {
        "pdf_evidence": {
            "source_id": str(UUID(int=7000)),
            "page": {"locator": "page-one"},
            "blocks": [],
            "pictures": [{"id": "page-1"}],
        }
    }
    value = proposal(context)
    assert validate_output(value, context, source_kind="pdf").claims[0].basis == "picture"
    value["claims"][0].update(basis="both", quote="Blank opening")
    with pytest.raises(ValueError, match="unbound quote"):
        validate_output(value, context, source_kind="pdf")


def test_pdf_page_selection_change_requires_new_preview(pdf_evidence_app):
    x = pdf_evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, _, _ = start(client, x)
        before = snapshot(x)
        value["pdf"]["page_number"] = 2
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 409 and response.json()["detail"] == "CHAT_CONTEXT_CHANGED"
        assert not x.calls and snapshot(x) == before
