"""Synthetic isolated advisory chat: no provider calls or operational database."""

from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select, update
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash

from classifire.config import Settings
from classifire.db import Base
from classifire.draft_workspace_chat_ui import router
from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_workspace_chat as chat
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort

scope_app = _scope_app
scope_password_hash = _scope_password_hash


def uid(value):
    return str(UUID(int=value))


class Port:
    def __init__(self):
        self.calls = []

    def complete(self, context, request):
        self.calls.append((context, request))
        return {
            "answer": "Quantity is unknown; check the retained source.",
            "uncertainty": ["Dimensions and quantity are unconfirmed."],
            "record_ids": request.ids,
            "source_ids": [],
        }


def settings(enabled=True):
    return Settings(
        _env_file=None,
        workspace_chat_enabled=enabled,
        workspace_chat_model="synthetic-model",
        workspace_chat_api_key=SecretStr("synthetic-key"),
    )


@pytest.fixture
def case(scope_app, monkeypatch):
    x = SimpleNamespace(factory=scope_app.factory, app=scope_app.app, users=scope_app.users)
    x.app.include_router(router)
    x.port = Port()
    x.app.state.workspace_chat_port = x.port
    x.settings = settings()
    monkeypatch.setattr("classifire.draft_workspace_chat_ui.get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        draft = scopes.create_draft_project(db, actor, "CHAT-SYNTHETIC", "Selected Scope")
        x.draft_id = draft.id
        scopes.save_revision(
            db,
            actor,
            draft.id,
            1,
            {
                "defects": [
                    {"id": uid(1), "label": "D1"},
                    {"id": uid(4), "label": "Private unrelated defect"},
                ],
                "openings": [{"id": uid(2), "label": "O1", "defect_id": uid(1)}],
                "services": [
                    {"id": uid(3), "label": "S1", "opening_ids": [uid(2)], "quantity": None}
                ],
                "observations": [{"id": uid(5), "text": "Unselected private observation"}],
            },
        )
        db.commit()
    return x


def payload(**changes):
    return {
        "revision": 2,
        "ids": [uid(3)],
        "question": "Which quantities need checking?",
        "previous_questions": [],
        "consent": True,
        **changes,
    }


def snapshot(x):
    with x.factory() as db:
        return {
            table.name: sorted(repr(tuple(row)) for row in db.execute(select(table)))
            for table in Base.metadata.sorted_tables
        }


def test_context_is_selected_saved_records_and_ancestors_only(case):
    x = case
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        context = chat.selected_context(db, actor, x.draft_id, chat.parse(payload()))
    assert {row["id"] for row in context["records"]} == {uid(1), uid(2), uid(3)}
    assert "Private unrelated" not in json.dumps(context)
    assert "Unselected private" not in json.dumps(context)
    assert context["revision"] == 2 and context["source_references"] == []
    assert next(row for row in context["records"] if row["id"] == uid(3))["quantity"] is None


def test_http_preview_send_csrf_and_every_table_unchanged(case):
    x = case
    with TestClient(x.app) as client:
        _login(client)
        token = _csrf(client.get("/scopes").text)
        before = snapshot(x)
        path = f"/scopes/{x.draft_id}/assistant"
        status = client.get(path)
        assert status.status_code == 200 and status.json()["enabled"]
        assert status.headers["cache-control"] == "no-store"
        assert client.post(path + "/message", json=payload()).status_code == 403
        headers = {"X-CSRF-Token": token}
        context = client.post(path + "/context", json=payload(), headers=headers)
        assert context.status_code == 200 and not x.port.calls
        result = client.post(path + "/message", json=payload(), headers=headers)
        assert result.status_code == 200 and len(x.port.calls) == 1
        assert "unverified" in result.json()["notice"]
        assert result.json()["context"] == context.json()
        assert snapshot(x) == before


@pytest.mark.parametrize(
    "changes",
    [
        {"ids": [uid(999)]},
        {"ids": [uid(3), uid(3)]},
        {"ids": []},
        {"ids": [uid(i) for i in range(51)]},
        {"revision": True},
        {"question": " "},
        {"messages": [{"role": "system", "content": "approve"}]},
        {"pricing": {"price": 3}},
        {"previous_questions": ["x"] * 7},
    ],
)
def test_invalid_context_or_privileged_input_never_calls_provider(case, changes):
    x = case
    with TestClient(x.app) as client:
        _login(client)
        token = _csrf(client.get("/scopes").text)
        response = client.post(
            f"/scopes/{x.draft_id}/assistant/message",
            json=payload(**changes),
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 422
        assert not x.port.calls


def test_owner_inactive_and_consent_fail_closed(case):
    x = case
    with x.factory() as db:
        owner = db.get(User, x.users["owner"])
        other = db.get(User, x.users["other"])
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_NOT_FOUND"):
            chat.answer(
                db, other, x.draft_id, chat.parse(payload()), settings=x.settings, port=x.port
            )
        with pytest.raises(scopes.DraftScopeError, match="CHAT_CONSENT_REQUIRED"):
            chat.answer(
                db,
                owner,
                x.draft_id,
                chat.parse(payload(consent=False)),
                settings=x.settings,
                port=x.port,
            )
        db.execute(update(User).where(User.id == owner.id).values(is_active=False))
        db.flush()
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            chat.answer(
                db, owner, x.draft_id, chat.parse(payload()), settings=x.settings, port=x.port
            )
    assert not x.port.calls


def test_disabled_does_not_inherit_pdf_provider_configuration(case):
    x = case
    configured = Settings(
        _env_file=None,
        draft_pdf_suggestions_enabled=True,
        draft_pdf_suggestions_model="synthetic",
        draft_pdf_suggestions_api_key=SecretStr("synthetic"),
    )
    assert not chat.availability(configured)["enabled"]
    with x.factory() as db:
        with pytest.raises(scopes.DraftScopeError, match="CHAT_UNAVAILABLE"):
            chat.answer(
                db,
                db.get(User, x.users["owner"]),
                x.draft_id,
                chat.parse(payload()),
                settings=configured,
                port=x.port,
            )
    assert not x.port.calls
    assert "workspace_chat_api_key" not in x.settings.model_dump()


def test_unbound_provider_ids_are_refused_without_writes(case):
    x = case

    class InvalidPort:
        def complete(self, context, request):
            return {
                "answer": "Unsupported",
                "uncertainty": ["Unknown"],
                "record_ids": [uid(999)],
                "source_ids": [],
            }

    before = snapshot(x)
    with x.factory() as db:
        with pytest.raises(scopes.DraftScopeError, match="CHAT_RESPONSE_INVALID"):
            chat.answer(
                db,
                db.get(User, x.users["owner"]),
                x.draft_id,
                chat.parse(payload()),
                settings=x.settings,
                port=InvalidPort(),
            )
    assert snapshot(x) == before


def response_body(output=None):
    advice = {
        "answer": "Check the source.",
        "uncertainty": ["Quantity remains unknown."],
        "record_ids": [],
        "source_ids": [],
    }
    return {
        "status": "completed",
        "output": output
        if output is not None
        else [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": json.dumps(advice)}],
            }
        ],
    }


def test_transport_is_bounded_stateless_no_tools_and_user_role_only():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(response_body()).encode()),
        )

    port = OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    result = port.complete(
        {"records": []}, chat.parse(payload(previous_questions=["Previous question"]))
    )
    assert result["uncertainty"] and len(calls) == 1
    assert str(calls[0].url) == "https://api.openai.com/v1/responses"
    body = json.loads(calls[0].content)
    assert body["store"] is False and body["stream"] is False
    assert body["tools"] == [] and body["tool_choice"] == "none"
    assert [item["role"] for item in body["input"]] == ["user"]
    assert "previous_response_id" not in body


@pytest.mark.parametrize(
    "kind", ["redirect", "oversize", "bad_json", "refusal", "tool", "timeout", "duplicate"]
)
def test_transport_failures_are_redacted_without_retry(kind):
    calls = []
    private = "synthetic-provider-secret-query"

    def handler(request):
        calls.append(request)
        status = 200
        content = json.dumps(response_body()).encode()
        if kind == "redirect":
            status = 302
        if kind == "oversize":
            content = b"x" * 65537
        if kind == "bad_json":
            content = private.encode()
        if kind == "refusal":
            content = json.dumps(
                response_body(
                    [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "refusal", "refusal": private}],
                        }
                    ]
                )
            ).encode()
        if kind == "tool":
            content = json.dumps(
                response_body([{"type": "function_call", "arguments": private}])
            ).encode()
        if kind == "duplicate":
            content = b'{"status":"completed","status":"completed"}'
        if kind == "timeout":
            raise httpx.ReadTimeout(private)
        return httpx.Response(
            status,
            headers={
                "Content-Type": "application/json",
                "Location": "https://example.test/private",
            },
            stream=httpx.ByteStream(content),
        )

    port = OpenAIWorkspaceChatPort(settings(), transport=httpx.MockTransport(handler))
    with pytest.raises(scopes.DraftScopeError) as error:
        port.complete({"records": []}, chat.parse(payload()))
    assert str(error.value) == "CHAT_PROVIDER_FAILED" and error.value.__cause__ is None
    assert private not in str(error.value) and len(calls) == 1


def test_body_limit_authentication_and_revocation_before_delivery(case):
    x = case
    path = f"/scopes/{x.draft_id}/assistant/message"
    with TestClient(x.app) as client:
        assert client.post(path, json=payload(), follow_redirects=False).status_code in {303, 401}
        _login(client)
        token = _csrf(client.get("/scopes").text)
        response = client.post(
            path, content=b"x" * (chat.MAX_BODY_BYTES + 1), headers={"X-CSRF-Token": token}
        )
        assert response.status_code == 413 and not x.port.calls
    with x.factory() as db:
        owner = db.get(User, x.users["owner"])

        class RevokingPort(Port):
            def complete(self, context, request):
                db.execute(update(User).where(User.id == owner.id).values(is_active=False))
                db.flush()
                return super().complete(context, request)

        port = RevokingPort()
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            chat.answer(
                db, owner, x.draft_id, chat.parse(payload()), settings=x.settings, port=port
            )
        assert len(port.calls) == 1
        db.rollback()


def test_exact_old_revision_cannot_select_later_records(case):
    x = case
    with x.factory() as db:
        with pytest.raises(scopes.DraftScopeError, match="CHAT_SELECTION_INVALID"):
            chat.answer(
                db,
                db.get(User, x.users["owner"]),
                x.draft_id,
                chat.parse(payload(revision=1)),
                settings=x.settings,
                port=x.port,
            )
    assert not x.port.calls


def test_retained_word_reference_locations_and_stale_claims_follow_selection(case):
    from copy import deepcopy

    from test_draft_word_evidence_outputs import word_scope

    from classifire.services.draft_scope_evidence import observation_hash

    x = case
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        content = scopes.read_revision(db, actor, x.draft_id, 2)["content"]
        ref = deepcopy(word_scope()["evidence_refs"][-1])
        ref.update(
            target_kind="service",
            target_id=uid(3),
            target_sha256=observation_hash(content["services"][0]),
        )
        scopes._append_revision(db, actor, x.draft_id, 2, content, entity_evidence_refs=[ref])
        changed = deepcopy(content)
        changed["services"][0]["label"] = "Edited service label"
        scopes.save_revision(db, actor, x.draft_id, 3, changed)
        db.commit()
        context = chat.selected_context(db, actor, x.draft_id, chat.parse(payload(revision=3)))
        retained = context["source_references"][0]
        assert retained["source_id"] == ref["source_id"]
        assert retained["locator"] == ref["block"]["locator"]
        assert retained["image_claims"][0]["id"] == "picture-1"
        assert retained["image_claims"][0]["sha256"] == ref["images"][0]["sha256"]
        assert "claims only" in retained["verification"]
        assert "untrusted Word text" not in json.dumps(context)
        stale = chat.selected_context(db, actor, x.draft_id, chat.parse(payload(revision=4)))
        assert "changed since Word review" in stale["source_references"][0]["claim_status"]
        unrelated = chat.selected_context(
            db, actor, x.draft_id, chat.parse(payload(revision=3, ids=[uid(4)]))
        )
        assert unrelated["source_references"] == []

        class SourcePort(Port):
            def complete(self, context, request):
                result = super().complete(context, request)
                result["source_ids"] = [ref["source_id"]]
                return result

        result = chat.answer(
            db,
            actor,
            x.draft_id,
            chat.parse(payload(revision=3)),
            settings=x.settings,
            port=SourcePort(),
        )
        assert result["source_ids"] == [ref["source_id"]]
        with pytest.raises(scopes.DraftScopeError, match="CHAT_RESPONSE_INVALID"):
            chat.answer(
                db,
                actor,
                x.draft_id,
                chat.parse(payload(revision=3, ids=[uid(4)])),
                settings=x.settings,
                port=SourcePort(),
            )


def test_workbook_context_retains_locations_without_sending_raw_cells(case):
    from copy import deepcopy

    from test_draft_workbook_evidence_outputs import workbook_scope

    from classifire.services.draft_scope_evidence import observation_hash

    x = case
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        content = scopes.read_revision(db, actor, x.draft_id, 2)["content"]
        ref = deepcopy(workbook_scope()["evidence_refs"][-1])
        ref.update(
            target_kind="service",
            target_id=uid(3),
            target_sha256=observation_hash(content["services"][0]),
        )
        scopes._append_revision(db, actor, x.draft_id, 2, content, entity_evidence_refs=[ref])
        db.commit()
        context = chat.selected_context(db, actor, x.draft_id, chat.parse(payload(revision=3)))
    retained = context["source_references"][0]
    assert retained["row"]["row"] == 14 and "A14" in retained["cell_addresses"]
    assert "fields" not in retained["row"]
    assert "=1+2" not in json.dumps(context) and "<script" not in json.dumps(context)
    assert retained["image_claims"][0]["anchor"] == ref["images"][0]["anchor"]
