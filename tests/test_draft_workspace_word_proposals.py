"""Typed synthetic Word proposals never save until the separate session-bound review."""

from __future__ import annotations

import copy
import html
import json
import re
from uuid import UUID

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_draft_scope_ui import _csrf, _login
from test_draft_workspace_chat import response_body, snapshot
from test_draft_workspace_word_evidence import evidence_app as _evidence_app
from test_draft_workspace_word_evidence import pdf_app as _pdf_app
from test_draft_workspace_word_evidence import pdf_setup as _pdf_setup
from test_draft_workspace_word_evidence import postgresql_session_factory as _postgres
from test_draft_workspace_word_evidence import request
from test_draft_workspace_word_evidence import scope_password_hash as _password_hash
from test_draft_workspace_word_evidence import word_app as _word_app

from classifire.models import User
from classifire.services.draft_scope import DraftScopePayload
from classifire.services.draft_workspace_chat import DraftScopeError, parse_workspace
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort
from classifire.services.draft_workspace_word_proposals import response_schema, validate_output

evidence_app = _evidence_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


def uid(number):
    return str(UUID(int=number))


def proposal(context):
    block = context["word_evidence"]["blocks"][0]
    graph = DraftScopePayload.model_validate(
        {
            "defects": [{"id": uid(801), "label": "Synthetic report defect"}],
            "openings": [
                {"id": uid(802), "label": "Blank opening", "defect_id": uid(801), "blank": True},
                {"id": uid(803), "label": "Unresolved opening", "defect_id": None},
            ],
            "services": [{"id": uid(804), "label": "Unlinked service", "opening_ids": []}],
            "observations": [],
        }
    ).model_dump(mode="json")
    claims = [
        {
            "target_kind": kind,
            "target_id": row["id"],
            "locator": block["locator"],
            "image_ids": [],
            "basis": "text",
            "quote": block["text"],
            "rationale": "Scripted confirmation test; not accuracy evidence.",
        }
        for kind in ("defect", "opening", "service")
        for row in graph[kind + "s"]
    ]
    return {
        "answer": "Review these synthetic additions before saving.",
        "uncertainty": ["Dimensions, quantities and relationships remain unknown."],
        "record_ids": [],
        "source_ids": [context["word_evidence"]["source_id"]],
        "additions": graph,
        "claims": claims,
    }


def provider(x, transform=lambda value: value):
    def respond(req):
        body = json.loads(req.content)
        x.calls.append(body)
        content = body["input"][0]["content"]
        context = json.loads(content[0]["text"] if isinstance(content, list) else content)[
            "selected_saved_context"
        ]
        envelope = response_body()
        envelope["output"][0]["content"][0]["text"] = json.dumps(transform(proposal(context)))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(envelope).encode()),
        )

    x.app.state.workspace_chat_port = OpenAIWorkspaceChatPort(
        x.settings, transport=httpx.MockTransport(respond)
    )


def start(client, x):
    _login(client)
    csrf = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    headers = {"X-CSRF-Token": csrf}
    value = request(x) | {"action": "propose_word_scope"}
    preview = client.post("/workspace/assistant/context", json=value, headers=headers)
    assert preview.status_code == 200, preview.text
    value.update(consent=True, context_sha256=preview.json()["context_sha256"])
    return value, headers, csrf


def review_form(result, csrf):
    return {
        "csrf_token": csrf,
        "expected_revision": str(result["expected_revision"]),
        "document_sha256": result["document_sha256"],
        "payload": json.dumps(result["payload"]),
        "targets": json.dumps(result["targets"]),
    }


def test_proposal_preview_separate_confirm_reopen_preserves_old_rows_and_unknowns(evidence_app):
    x = evidence_app
    provider(x)
    with TestClient(x.app) as client:
        value, headers, csrf = start(client, x)
        saved = client.get(f"/scopes/{x.ids[2]}/download?revision=1").json()
        path = f"/scopes/{x.ids[2]}/word/{x.selection['source_id']}"
        original = client.get(path + "/original").content
        before = snapshot(x)
        denied = client.post(
            "/workspace/assistant/message", json=value | {"consent": False}, headers=headers
        )
        assert denied.status_code == 422 and not x.calls
        answer = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert answer.status_code == 200, answer.text
        result = answer.json()["proposal"]
        assert snapshot(x) == before and len(x.calls) == 1
        assert x.calls[0]["text"]["format"]["name"] == "workspace_word_proposal"
        assert x.calls[0]["tools"] == [] and x.calls[0]["store"] is False
        additions = result["additions"]
        for kind in ("defects", "openings", "services", "observations"):
            assert result["payload"][kind] == saved["content"][kind] + additions[kind]
        assert additions["openings"][0]["blank"] is True
        assert additions["openings"][0]["width_mm"] is None
        assert additions["openings"][1]["defect_id"] is None
        assert additions["services"][0]["quantity"] is None
        assert additions["services"][0]["opening_ids"] == []
        assert additions["defects"][0]["id"] != uid(801)
        assert additions["openings"][0]["defect_id"] == additions["defects"][0]["id"]
        path = f"/scopes/{x.ids[2]}/word/{x.selection['source_id']}"
        form = review_form(result, csrf)
        assert client.post(path + "/confirm", data=form).status_code == 422
        page = client.post(path + "/preview", data=form)
        assert page.status_code == 200, page.text
        assert "Preview Word-linked draft" in page.text and 'id="word-scope-confirm"' in page.text
        assert snapshot(x) == before
        token = html.unescape(re.search(r'name="preview_token" value="([^"]+)"', page.text)[1])
        confirm = form | {"preview_token": token, "confirm": "save"}
        forged = confirm | {"payload": json.dumps(result["payload"] | {"exclusions": ["forged"]})}
        assert client.post(path + "/confirm", data=forged).status_code == 409
        assert snapshot(x) == before
        response = client.post(path + "/confirm", data=confirm, follow_redirects=False)
        assert response.status_code == 303, response.text
        assert client.post(path + "/confirm", data=confirm).status_code == 409
        reopened = client.get(f"/scopes/{x.ids[2]}/download?revision=2").json()
        assert reopened["content"] == result["payload"]
        assert len(reopened["evidence_refs"]) == 4
        assert {ref["method"] for ref in reopened["evidence_refs"]} == {"human_docx_entity_review"}
        assert client.get(path + "/original").content == original
        stale = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert stale.status_code == 409 and len(x.calls) == 1
        allowed = {"draft_scopes", "draft_scope_revisions", "audit_events"}
        assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
            k: v for k, v in before.items() if k not in allowed
        }
    with TestClient(x.app) as reopened_client:
        _login(reopened_client)
        assert reopened_client.get(f"/scopes/{x.ids[2]}/download?revision=2").json() == reopened


@pytest.mark.parametrize(
    "change",
    [
        "quote",
        "image",
        "target",
        "confirmed",
        "missing",
        "blank_link",
        "old_link",
        "assumption",
        "duplicate",
        "uncovered",
    ],
)
def test_invalid_proposals_rejected(change):
    context = {
        "word_evidence": {
            "source_id": uid(900),
            "blocks": [{"locator": "body-1", "text": "Synthetic evidence"}],
            "pictures": [],
        }
    }
    value = proposal(context)
    if change == "quote":
        value["claims"][0]["quote"] = "invented quote"
    if change == "image":
        value["claims"][0].update(basis="both", image_ids=["picture-1"])
    if change == "target":
        value["claims"][0]["target_id"] = uid(777)
    if change == "confirmed":
        value["additions"]["openings"][0]["state"] = "Confirmed"
    if change == "missing":
        del value["additions"]["services"][0]["quantity"]
    if change == "blank_link":
        value["additions"]["services"][0]["opening_ids"] = [uid(802)]
    if change == "old_link":
        value["additions"]["openings"][0]["defect_id"] = uid(777)
    if change == "assumption":
        value["additions"]["assumptions"] = ["Unbound assumption"]
    if change == "duplicate":
        value["claims"].append(copy.deepcopy(value["claims"][0]))
    if change == "uncovered":
        value["claims"].pop()
    with pytest.raises((ValueError, DraftScopeError)):
        validate_output(value, context)


def test_output_schema_requires_explicit_fields_and_proposal_requires_word_text():
    schema = response_schema()
    for node in [schema, *schema["$defs"].values()]:
        if node.get("type") == "object":
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
    assert "default" not in json.dumps(schema)
    assert "Confirmed" not in json.dumps(schema)
    with pytest.raises(DraftScopeError):
        parse_workspace(
            {
                "screen": {"name": "scopes"},
                "action": "propose_word_scope",
                "question": "Propose",
                "draft_id": uid(1),
                "revision": 1,
            }
        )


def test_action_change_requires_new_preview_and_invalid_reply_saves_nothing(evidence_app):
    x = evidence_app
    provider(x, lambda value: value | {"claims": []})
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x)
        before = snapshot(x)
        advice = value | {"action": "advice"}
        assert (
            client.post("/workspace/assistant/message", json=advice, headers=headers).status_code
            == 409
        )
        assert not x.calls
        invalid = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert invalid.status_code == 502 and len(x.calls) == 1
        assert snapshot(x) == before


def test_empty_unsupported_proposal_has_no_review_action(evidence_app):
    x = evidence_app
    provider(
        x,
        lambda value: (
            value | {"additions": DraftScopePayload().model_dump(mode="json"), "claims": []}
        ),
    )
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x)
        before = snapshot(x)
        answer = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert answer.status_code == 200, answer.text
        assert answer.json()["proposal"] is None and snapshot(x) == before


@pytest.mark.parametrize("during_reply", [False, True])
def test_write_rights_are_required_before_and_after_proposal(evidence_app, during_reply):
    x = evidence_app

    def revoke(value):
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        return value

    provider(x, revoke if during_reply else lambda value: value)
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x)
        if not during_reply:
            revoke(None)
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 403, response.text
        assert len(x.calls) == int(during_reply)
        assert "proposal" not in response.json()
        assert {k: v for k, v in snapshot(x).items() if k != "users"} == {
            k: v for k, v in before.items() if k != "users"
        }


def test_bound_graph_preserves_explicit_dimensions_quantity_and_shared_opening():
    context = {
        "word_evidence": {
            "source_id": uid(900),
            "blocks": [
                {"locator": "body-1", "text": "Synthetic two services in one 100 x 200 mm opening."}
            ],
            "pictures": [{"id": "picture-1"}],
        }
    }
    value = proposal(context)
    opening = value["additions"]["openings"][1]
    opening.update(width_mm="100", height_mm="200", defect_id=uid(801))
    service = value["additions"]["services"][0]
    service.update(quantity="2.5", unit="m", opening_ids=[uid(803)])
    other = copy.deepcopy(service) | {"id": uid(806)}
    value["additions"]["services"].append(other)
    claim = copy.deepcopy(value["claims"][-1]) | {"target_id": uid(806)}
    value["claims"].append(claim)
    value["claims"][0].update(basis="both", image_ids=["picture-1"])
    graph = validate_output(value, context).additions.model_dump(mode="json")
    assert graph["openings"][1]["width_mm"] == "100"
    assert graph["openings"][1]["height_mm"] == "200"
    assert [row["opening_ids"] for row in graph["services"]] == [[uid(803)], [uid(803)]]
    assert graph["services"][0]["quantity"] == "2.5"
    assert graph["services"][0]["unit"] == "m"
