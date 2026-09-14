"""Selected saved-record edits use a separate human validation/save step."""

from __future__ import annotations

import copy
import json
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
from test_draft_workspace_word_evidence import scope_password_hash as _password_hash
from test_draft_workspace_word_evidence import word_app as _word_app

from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_docx_review as word_review
from classifire.services.draft_scope_evidence import reference_changed
from classifire.services.draft_workspace_chat import parse_workspace
from classifire.services.draft_workspace_chat_transport import OpenAIWorkspaceChatPort
from classifire.services.draft_workspace_scope_edits import response_schema, validate_edits

pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app
evidence_app = _evidence_app


def uid(number):
    return str(UUID(int=number))


def baseline():
    return scopes.DraftScopePayload.model_validate(
        {
            "defects": [
                {"id": uid(1001), "label": "Selected defect"},
                {"id": uid(1010), "label": "Unselected defect"},
            ],
            "openings": [
                {"id": uid(1002), "label": "Selected opening", "defect_id": uid(1001)},
                {"id": uid(1011), "label": "Unselected opening", "defect_id": uid(1010)},
            ],
            "services": [
                {"id": uid(1003), "label": "Conduit", "opening_ids": [uid(1002)]},
                {"id": uid(1012), "label": "Untouched cable", "opening_ids": [uid(1011)]},
            ],
            "observations": [{"id": uid(1020), "text": "Keep this unresolved observation."}],
            "assumptions": ["No rating inferred."],
            "exclusions": ["No pricing selected."],
        }
    ).model_dump(mode="json")


def edit_reply(context):
    row = next(row for row in context["records"] if row["id"] == uid(1003))
    changed = {key: value for key, value in row.items() if key != "kind"}
    changed.update(label="Reviewed conduit", quantity="2.5", unit="m", state="Provisional")
    graph = scopes.DraftScopePayload.model_validate({"services": [changed]}).model_dump(mode="json")
    return {
        "answer": "Review the requested service changes before saving.",
        "uncertainty": ["These are proposed edits, not approved source facts."],
        "record_ids": [uid(1003)],
        "source_ids": [],
        "replacements": graph,
        "reasons": [
            {
                "target_kind": "service",
                "target_id": uid(1003),
                "rationale": "Apply the explicitly requested description and quantity.",
            }
        ],
    }


@pytest.fixture
def edit_app(evidence_app):
    x = evidence_app
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        targets = [
            {
                "target_kind": kind,
                "target_id": identity,
                "locator": x.selection["locators"][0],
                "image_ids": [],
            }
            for kind, identity in (("service", uid(1003)), ("opening", uid(1002)))
        ]
        preview = word_review.preview_review(
            db,
            actor,
            x.ids[2],
            x.selection["source_id"],
            1,
            baseline(),
            targets,
            x.selection["document_sha256"],
            settings=x.settings,
        )
        word_review.save_review(
            db,
            actor,
            x.ids[2],
            x.selection["source_id"],
            1,
            baseline(),
            targets,
            x.selection["document_sha256"],
            preview["review_sha256"],
            settings=x.settings,
        )
        db.commit()
    return x


def provider(x, transform=lambda value: value, reply=edit_reply):
    def respond(req):
        body = json.loads(req.content)
        x.calls.append(body)
        content = body["input"][0]["content"]
        context = json.loads(content[0]["text"] if isinstance(content, list) else content)[
            "selected_saved_context"
        ]
        envelope = response_body()
        envelope["output"][0]["content"][0]["text"] = json.dumps(transform(reply(context)))
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=httpx.ByteStream(json.dumps(envelope).encode()),
        )

    x.app.state.workspace_chat_port = OpenAIWorkspaceChatPort(
        x.settings, transport=httpx.MockTransport(respond)
    )


def start(client, x, ids=None):
    _login(client)
    csrf = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    headers = {"X-CSRF-Token": csrf}
    value = {
        "screen": {"name": "scopes"},
        "draft_id": x.ids[2],
        "revision": 2,
        "ids": ids or [uid(1003)],
        "action": "propose_scope_edits",
        "question": "Rename to Reviewed conduit; set quantity to 2.5 m, provisional.",
    }
    response = client.post("/workspace/assistant/context", json=value, headers=headers)
    assert response.status_code == 200, response.text
    value.update(consent=True, context_sha256=response.json()["context_sha256"])
    return value, headers, csrf


def test_edits_diff_validate_then_separate_save_preserves_rows_claims_and_downstream(edit_app):
    x = edit_app
    provider(x)
    path = f"/scopes/{x.ids[2]}"
    with TestClient(x.app) as client:
        value, headers, csrf = start(client, x)
        original = client.get(path + "/download?revision=2").json()
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
        result = response.json()["edit_proposal"]
        assert snapshot(x) == before and len(x.calls) == 1
        assert x.calls[0]["text"]["format"]["name"] == "workspace_scope_edits"
        assert x.calls[0]["tools"] == [] and x.calls[0]["store"] is False
        assert result["changed_source_claims"] == 1
        assert [item["id"] for item in result["changes"]] == [uid(1003)]
        changes = {item["field"]: item for item in result["changes"][0]["fields"]}
        assert changes["quantity"] == {"field": "quantity", "before": None, "after": "2.5"}
        assert changes["state"]["after"] == "Provisional"
        expected = copy.deepcopy(original["content"])
        expected["services"][0].update(
            label="Reviewed conduit", quantity="2.5", unit="m", state="Provisional"
        )
        assert result["payload"] == expected
        form = {
            "csrf_token": csrf,
            "expected_revision": "2",
            "payload": json.dumps(result["payload"]),
            "action": "validate",
        }
        page = client.post(result["review_url"], data=form)
        assert page.status_code == 200 and "Changes have not been saved" in page.text
        assert snapshot(x) == before
        assert (
            client.post(path, data=form | {"action": "save", "csrf_token": "bad"}).status_code
            == 403
        )
        saved = client.post(path, data=form | {"action": "save"}, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        assert client.post(path, data=form | {"action": "save"}).status_code == 409
        reopened = client.get(path + "/download?revision=3").json()
        assert reopened["content"] == expected
        assert reopened["evidence_refs"] == original["evidence_refs"]
        changed = [ref for ref in reopened["evidence_refs"] if reference_changed(ref, expected)]
        assert len(changed) == 1 and changed[0]["target_id"] == uid(1003)
        assert (
            client.post("/workspace/assistant/message", json=value, headers=headers).status_code
            == 409
        )
        allowed = {"draft_scopes", "draft_scope_revisions", "audit_events"}
        assert {k: v for k, v in snapshot(x).items() if k not in allowed} == {
            k: v for k, v in before.items() if k not in allowed
        }
    with TestClient(x.app) as client:
        _login(client)
        assert client.get(path + "/download?revision=3").json() == reopened


def context():
    graph = baseline()
    return {
        "selected_ids": [uid(1003)],
        "records": [
            {"kind": kind, **row}
            for kind, rows in graph.items()
            if kind in {"defects", "openings", "services", "observations"}
            for row in rows
            if row["id"] in {uid(1001), uid(1002), uid(1003)}
        ],
    }


@pytest.mark.parametrize(
    "change",
    [
        "ancestor",
        "new_id",
        "missing",
        "confirmed",
        "undisclosed_link",
        "global",
        "duplicate",
        "reason",
        "unchanged",
    ],
)
def test_unselected_incomplete_or_unbound_edits_refused(change):
    ctx = context()
    value = edit_reply(ctx)
    graph = value["replacements"]
    if change == "ancestor":
        row = copy.deepcopy(baseline()["openings"][0])
        row["label"] = "Ancestor edit"
        graph["openings"] = [row]
    if change == "new_id":
        graph["services"][0]["id"] = uid(9999)
    if change == "missing":
        del graph["services"][0]["quantity"]
    if change == "confirmed":
        graph["services"][0]["state"] = "Confirmed"
    if change == "undisclosed_link":
        graph["services"][0]["opening_ids"] = [uid(1011)]
    if change == "global":
        graph["assumptions"] = ["Unselected change"]
    if change == "duplicate":
        graph["services"].append(copy.deepcopy(graph["services"][0]))
    if change == "reason":
        value["reasons"] = []
    if change == "unchanged":
        graph["services"][0] = baseline()["services"][0]
    with pytest.raises(ValueError):
        validate_edits(value, ctx)


def test_empty_edits_and_schema_are_explicit():
    value = edit_reply(context())
    value.update(replacements=scopes.DraftScopePayload().model_dump(mode="json"), reasons=[])
    assert validate_edits(value, context()).replacements.services == []
    schema = response_schema()
    assert "Confirmed" not in json.dumps(schema) and "default" not in json.dumps(schema)
    for node in [schema, *schema["$defs"].values()]:
        if node.get("type") == "object":
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
    with pytest.raises(scopes.DraftScopeError):
        parse_workspace(
            {
                "screen": {"name": "scopes"},
                "draft_id": uid(1),
                "revision": 1,
                "action": "propose_scope_edits",
                "question": "Edit",
            }
        )


@pytest.mark.parametrize("during", [False, True])
def test_revoked_write_permission_withholds_edits(edit_app, during):
    x = edit_app

    def revoke(value):
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        return value

    provider(x, revoke if during else lambda value: value)
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x)
        if not during:
            revoke(None)
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 403 and len(x.calls) == int(during)
        assert {k: v for k, v in snapshot(x).items() if k != "users"} == {
            k: v for k, v in before.items() if k != "users"
        }


def test_full_graph_relationship_conflict_refused_without_save(edit_app):
    x = edit_app

    def blank_reply(ctx):
        row = copy.deepcopy(baseline()["openings"][0])
        row["blank"] = True
        return {
            "answer": "Proposed blank opening.",
            "uncertainty": ["Check service relationships."],
            "record_ids": [uid(1002)],
            "source_ids": [],
            "replacements": scopes.DraftScopePayload.model_validate({"openings": [row]}).model_dump(
                mode="json"
            ),
            "reasons": [
                {
                    "target_kind": "opening",
                    "target_id": uid(1002),
                    "rationale": "Synthetic conflicting edit.",
                }
            ],
        }

    provider(x, reply=blank_reply)
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x, [uid(1002)])
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 422 and response.json()["detail"] == "CHAT_EDIT_CONFLICT"
        assert snapshot(x) == before


def test_multiple_selected_record_kinds_prepare_one_graph_without_writes(edit_app):
    x = edit_app
    selected = [uid(1001), uid(1002), uid(1003), uid(1020)]

    def reply(ctx):
        value = edit_reply(ctx)
        for kind, field, identity in (
            ("defect", "label", uid(1001)),
            ("opening", "label", uid(1002)),
            ("observation", "text", uid(1020)),
        ):
            collection = {
                "defect": "defects", "opening": "openings", "observation": "observations"
            }[kind]
            source = next(row for row in ctx["records"] if row["id"] == identity)
            row = {key: item for key, item in source.items() if key != "kind"}
            row[field] = "Proposed " + row[field]
            value["replacements"][collection].append(row)
            value["reasons"].append(
                {"target_kind": kind, "target_id": identity, "rationale": "Requested wording edit."}
            )
        return value

    provider(x, reply=reply)
    with TestClient(x.app) as client:
        value, headers, _ = start(client, x, selected)
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()["edit_proposal"]
        assert {row["id"] for row in result["changes"]} == set(selected)
        expected = baseline()
        expected["services"][0].update(
            label="Reviewed conduit", quantity="2.5", unit="m", state="Provisional"
        )
        for collection, field in (
            ("defects", "label"), ("openings", "label"), ("observations", "text")
        ):
            expected[collection][0][field] = "Proposed " + expected[collection][0][field]
        assert result["payload"] == expected
        assert result["changed_source_claims"] == 2
        assert snapshot(x) == before and len(x.calls) == 1


def test_total_edit_budget_applies_across_complete_replacement_records():
    graph = scopes.DraftScopePayload.model_validate(
        {"defects": [{"id": uid(2000 + i), "label": "Before"} for i in range(26)]}
    ).model_dump(mode="json")
    ctx = {"selected_ids": [row["id"] for row in graph["defects"]],
           "records": [{"kind": "defects", **row} for row in graph["defects"]]}
    replacements = copy.deepcopy(graph)
    for row in replacements["defects"]:
        row["label"] = "After"
    value = {
        "answer": "Proposed wording", "uncertainty": ["Unverified wording."],
        "record_ids": [], "source_ids": [], "replacements": replacements, "reasons": []
    }
    with pytest.raises(ValueError, match="edit budget"):
        validate_edits(value, ctx)
