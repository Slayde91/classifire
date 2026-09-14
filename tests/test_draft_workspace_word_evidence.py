"""Explicit retained Word evidence disclosure; synthetic transport and disposable DB."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import update
from test_draft_scope_docx import word_bytes
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import response_body, snapshot
from test_draft_workspace_word_ui import pdf_app as _pdf_app
from test_draft_workspace_word_ui import pdf_setup as _pdf_setup
from test_draft_workspace_word_ui import postgresql_session_factory as _postgres
from test_draft_workspace_word_ui import scope_password_hash as _password_hash
from test_draft_workspace_word_ui import word_app as _word_app

from classifire.draft_workspace_chat_ui import router
from classifire.models import DraftScopeDocxSource, User
from classifire.services import draft_scope_docx as word
from classifire.services import draft_workspace_chat as chat
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort

pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


@pytest.fixture
def evidence_app(word_app, monkeypatch):
    x = word_app
    x.settings = x.settings.model_copy(
        update={
            "workspace_chat_enabled": True,
            "workspace_chat_model": "gpt-5-mini",
            "workspace_chat_api_key": SecretStr("synthetic-key"),
        }
    )
    x.app.include_router(router)
    monkeypatch.setattr("classifire.draft_workspace_chat_ui.get_settings", lambda: x.settings)
    x.calls = []

    def respond(request):
        x.calls.append(json.loads(request.content))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(response_body()).encode()),
        )

    x.app.state.workspace_chat_port = OpenAIWorkspaceChatPort(
        x.settings, transport=httpx.MockTransport(respond)
    )
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        source = word.intake().retain(
            db, actor, x.ids[2], "synthetic.docx", word_bytes(), settings=x.settings
        )
        word.intake().scan_source(db, actor, x.ids[2], source.id, settings=x.settings)
        source, document, _ = word.intake()._document(
            db, actor, x.ids[2], source.id, x.settings.storage_root
        )
        x.selection = {
            "source_id": source.id,
            "document_sha256": source.document_sha256,
            "locators": [document["blocks"][0]["locator"]],
            "picture_ids": ["picture-1"],
        }
        x.picture = word.image_preview(
            db, actor, x.ids[2], source.id, "picture-1", settings=x.settings
        )
        db.commit()
    return x


def request(x):
    return {
        "screen": {"name": "scopes"},
        "draft_id": x.ids[2],
        "revision": 1,
        "question": "Explain the selected evidence; preserve unknown quantities.",
        "word": copy.deepcopy(x.selection),
    }


def test_explicit_word_preview_consent_exact_png_and_zero_writes(evidence_app):
    x = evidence_app
    with TestClient(x.app) as client:
        _login(client)
        headers = {"X-CSRF-Token": _csrf(client.get(f"/scopes/{x.ids[2]}").text)}
        before = snapshot(x)
        value = request(x)
        empty = dict(value, word=None)
        response = client.post("/workspace/assistant/context", json=empty, headers=headers)
        assert response.status_code == 200 and "word_evidence" not in response.json()
        preview = client.post("/workspace/assistant/context", json=value, headers=headers)
        assert preview.status_code == 200, preview.text
        context = preview.json()
        assert preview.headers["cache-control"] == "no-store"
        evidence = context["word_evidence"]
        assert len(evidence["blocks"]) == len(evidence["pictures"]) == 1
        assert evidence["omitted_blocks"] > 0
        assert evidence["pictures"][0]["preview_sha256"] == hashlib.sha256(x.picture).hexdigest()
        assert "data:image" not in preview.text and not x.calls
        denied = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert denied.status_code == 422 and not x.calls
        value.update(consent=True, context_sha256=context["context_sha256"])
        result = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert result.status_code == 200, result.text
        assert len(x.calls) == 1 and result.json()["uncertainty"]
        body = x.calls[0]
        assert body["store"] is False and body["tools"] == [] and body["tool_choice"] == "none"
        assert body["model"] == "gpt-5-mini" and body["max_output_tokens"] == 5000
        parts = body["input"][0]["content"]
        assert [item["type"] for item in parts] == ["input_text", "input_text", "input_image"]
        assert base64.b64decode(parts[2]["image_url"].split(",", 1)[1], validate=True) == x.picture
        assert parts[2]["detail"] == "high"
        sent = json.loads(parts[0]["text"])["selected_saved_context"]
        assert sent == context and sent["word_evidence"]["blocks"] == evidence["blocks"]
        assert snapshot(x) == before
        value["word"]["picture_ids"] = []
        stale = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert stale.status_code == 409 and len(x.calls) == 1
        assert snapshot(x) == before


def test_foreign_stale_invalid_word_selection_refused_without_provider(evidence_app):
    x = evidence_app
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        _login(other, "other")
        headers = {"X-CSRF-Token": _csrf(owner.get(f"/scopes/{x.ids[2]}").text)}
        other_headers = {"X-CSRF-Token": _csrf(other.get("/scopes").text)}
        before = snapshot(x)
        value = request(x)
        assert other.post(
            "/workspace/assistant/context", json=value, headers=other_headers
        ).status_code in {403, 404}
        assert (
            owner.post(
                "/workspace/assistant/context", json=value, headers={"X-CSRF-Token": "bad"}
            ).status_code
            == 403
        )
        for changes, expected in [
            ({"document_sha256": "0" * 64}, 409),
            ({"locators": ["body-999"]}, 422),
            ({"picture_ids": ["picture-40"]}, 422),
        ]:
            changed = copy.deepcopy(value)
            changed["word"].update(changes)
            response = owner.post("/workspace/assistant/context", json=changed, headers=headers)
            assert response.status_code == expected, response.text
        assert not x.calls and snapshot(x) == before


@pytest.mark.parametrize(
    "word_selection",
    [
        {"source_id": "bad", "document_sha256": "a" * 64, "locators": ["body-1"]},
        {"source_id": "00000000-0000-0000-0000-000000000001", "document_sha256": "a" * 64},
        {
            "source_id": "00000000-0000-0000-0000-000000000001",
            "document_sha256": "a" * 64,
            "locators": ["body-1"] * 2,
        },
        {
            "source_id": "00000000-0000-0000-0000-000000000001",
            "document_sha256": "a" * 64,
            "picture_ids": ["picture-1"] * 2,
        },
        {
            "source_id": "00000000-0000-0000-0000-000000000001",
            "document_sha256": "a" * 64,
            "picture_ids": ["picture-1", "picture-2", "picture-3"],
        },
        {
            "source_id": "00000000-0000-0000-0000-000000000001",
            "document_sha256": "a" * 64,
            "locators": [f"body-{i}" for i in range(11)],
        },
        {
            "source_id": "00000000-0000-0000-0000-000000000001",
            "document_sha256": "a" * 64,
            "locators": ["body-1"],
            "text": "browser-forged evidence",
        },
    ],
)
def test_word_selector_rejects_unbounded_duplicate_or_browser_content(word_selection):
    with pytest.raises(chat.DraftScopeError, match="CHAT_INPUT_INVALID"):
        chat.parse_workspace(
            {
                "screen": {"name": "scopes"},
                "draft_id": "00000000-0000-0000-0000-000000000002",
                "revision": 1,
                "question": "Review",
                "word": word_selection,
            }
        )


def test_expired_scan_after_preview_refuses_without_provider(evidence_app):
    x = evidence_app
    with TestClient(x.app) as client:
        _login(client)
        headers = {"X-CSRF-Token": _csrf(client.get(f"/scopes/{x.ids[2]}").text)}
        value = request(x)
        preview = client.post("/workspace/assistant/context", json=value, headers=headers)
        assert preview.status_code == 200
        value.update(consent=True, context_sha256=preview.json()["context_sha256"])
        with x.factory() as db:
            source = db.get(DraftScopeDocxSource, x.selection["source_id"])
            scan = json.loads(source.scan_json)
            scan["database_date"] = (datetime.now(UTC) - timedelta(days=40)).isoformat()
            source.scan_json = json.dumps(scan)
            db.commit()
        before = snapshot(x)
        result = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert result.status_code == 409 and not x.calls
        assert snapshot(x) == before


def test_permission_revoked_during_word_reply_withholds_reply(evidence_app):
    x = evidence_app

    def revoke(request):
        x.calls.append(json.loads(request.content))
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(is_active=False))
            db.commit()
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(response_body()).encode()),
        )

    x.app.state.workspace_chat_port = OpenAIWorkspaceChatPort(
        x.settings, transport=httpx.MockTransport(revoke)
    )
    with TestClient(x.app) as client:
        _login(client)
        headers = {"X-CSRF-Token": _csrf(client.get(f"/scopes/{x.ids[2]}").text)}
        value = request(x)
        preview = client.post("/workspace/assistant/context", json=value, headers=headers)
        assert preview.status_code == 200
        value.update(consent=True, context_sha256=preview.json()["context_sha256"])
        before = {k: v for k, v in snapshot(x).items() if k != "users"}
        result = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert result.status_code == 403 and "answer" not in result.json() and len(x.calls) == 1
        assert {k: v for k, v in snapshot(x).items() if k != "users"} == before


@pytest.mark.parametrize(
    "bad_part",
    [
        {"type": "input_image", "image_url": "https://example.invalid/image.png", "detail": "high"},
        {"type": "input_image", "image_url": "data:image/png;base64,invalid!", "detail": "high"},
        {
            "type": "input_image",
            "image_url": "data:image/png;base64,iVBORw0KGgo=",
            "detail": "high",
        },
    ],
)
def test_image_transport_refuses_nonmatching_or_remote_bytes(bad_part):
    from test_draft_workspace_chat import settings

    parsed = chat.parse_workspace(
        {
            "screen": {"name": "scopes"},
            "draft_id": "00000000-0000-0000-0000-000000000002",
            "revision": 1,
            "question": "Review",
            "word": {
                "source_id": "00000000-0000-0000-0000-000000000001",
                "document_sha256": "a" * 64,
                "picture_ids": ["picture-1"],
            },
        }
    )
    calls = []
    port = OpenAIWorkspaceChatPort(
        settings(), transport=httpx.MockTransport(lambda r: calls.append(r))
    )
    context = {
        "word_evidence": {"pictures": [{"preview_size_bytes": 8, "preview_sha256": "b" * 64}]}
    }
    with pytest.raises(chat.DraftScopeError, match="CHAT_INPUT_INVALID"):
        port.complete(context, parsed, images=[{"type": "input_text", "text": "Picture"}, bad_part])
    assert not calls
