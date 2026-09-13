"""Explicit native decisions; synthetic provider, separate confirmation, no inferred approval."""

from __future__ import annotations

import html
import importlib
import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from test_draft_scope_ui import _csrf
from test_draft_workspace_chat import snapshot
from test_draft_workspace_proposal_history import edit_app as _edit_app
from test_draft_workspace_proposal_history import evidence_app as _evidence_app
from test_draft_workspace_proposal_history import pdf_app as _pdf_app
from test_draft_workspace_proposal_history import pdf_evidence_app as _pdf_evidence_app
from test_draft_workspace_proposal_history import pdf_setup as _pdf_setup
from test_draft_workspace_proposal_history import scope_password_hash as _password
from test_draft_workspace_proposal_history import word_app as _word_app
from test_draft_workspace_proposal_history import xlsx_evidence_app as _xlsx_app
from test_shared_file_containment import postgresql_session_factory as _standard_postgres

from classifire.db import Base
from classifire.models import (
    DraftScopeRevision,
    DraftWorkspaceProposal,
    DraftWorkspaceProposalDecision,
    User,
)
from classifire.services import draft_workspace_proposals as saved

edit_app = _edit_app
evidence_app = _evidence_app
pdf_app = _pdf_app
pdf_evidence_app = _pdf_evidence_app
pdf_setup = _pdf_setup
scope_password_hash = _password
word_app = _word_app
xlsx_evidence_app = _xlsx_app
standard_postgresql_session_factory = _standard_postgres


@pytest.fixture
def postgresql_session_factory(request):
    # Optional separately guarded database permits a local run alongside the full suite.
    # CI/default execution retains the existing dedicated containment fixture and guard.
    url = os.environ.get("CLASSIFIRE_NATIVE_DECISION_TEST_URL")
    if url is None:
        yield request.getfixturevalue("standard_postgresql_session_factory")
        return
    parsed = make_url(url)
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.host == "127.0.0.1" and parsed.port == 15433
    assert parsed.database == "classifire_native_decisions_test" and not parsed.query
    assert os.environ.get("CLASSIFIRE_NATIVE_DECISION_TEST_RESET") == "owned-synthetic-decision-db"
    engine = create_engine(url, pool_size=4, max_overflow=0, pool_pre_ping=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def generated(client, x, kind):
    module = importlib.import_module(
        {
            "word": "test_draft_workspace_word_proposals",
            "pdf": "test_draft_workspace_pdf_proposals",
            "xlsx": "test_draft_workspace_xlsx_proposals",
            "edits": "test_draft_workspace_scope_edits",
        }[kind]
    )
    module.provider(x)
    value, headers = module.start(client, x)[:2]
    before = snapshot(x)
    response = client.post("/workspace/assistant/message", json=value, headers=headers)
    assert response.status_code == 200, response.text
    assert snapshot(x) == before
    result = response.json()
    csrf = _csrf(client.get(f"/scopes/{x.ids[2]}").text)
    offer = result["retention"]
    retained = client.post(
        f"/scopes/{x.ids[2]}/native-proposals",
        data={
            "csrf_token": csrf,
            "document": json.dumps(offer["document"]),
            "authorization": offer["authorization"],
        },
    )
    assert retained.status_code == 200, retained.text
    proposal = result["edit_proposal" if kind == "edits" else "proposal"]
    fields = {
        "csrf_token": csrf,
        "native_proposal_id": retained.json()["id"],
        "expected_revision": str(proposal["expected_revision"]),
        "payload": json.dumps(proposal["payload"]),
    }
    if kind == "edits":
        path = proposal["review_url"]
        fields["action"] = "validate"
    else:
        fields.update(targets=json.dumps(proposal["targets"]))
        if kind == "pdf":
            fields.update(
                page=str(proposal["page_number"]), document_hash=proposal["document_sha256"]
            )
            path = f"/scopes/{x.ids[2]}/evidence/{proposal['source_id']}/scope"
        elif kind == "xlsx":
            fields.update(
                plan=json.dumps(proposal["plan"]), document_sha256=proposal["document_sha256"]
            )
            path = f"/scopes/{x.ids[2]}/workbooks/{proposal['source_id']}"
        else:
            fields["document_sha256"] = proposal["document_sha256"]
            path = f"/scopes/{x.ids[2]}/word/{proposal['source_id']}"
    return path, fields, offer


def preview(client, path, fields, kind):
    response = client.post(path if kind == "edits" else path + "/preview", data=fields)
    assert response.status_code == 200, response.text
    assert f'name="native_proposal_id" value="{fields["native_proposal_id"]}"' in response.text
    if kind == "edits":
        return fields | {"action": "save"}
    token = html.unescape(re.search(r'name="preview_token" value="([^"]+)"', response.text)[1])
    return fields | {"preview_token": token, "confirm": "save"}


def commit(client, path, fields, kind):
    return client.post(
        path if kind == "edits" else path + "/confirm", data=fields, follow_redirects=False
    )


def opened(client, x, identity):
    result = client.get(f"/scopes/{x.ids[2]}/native-proposals/{identity}")
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.parametrize(
    "kind,fixture",
    [
        ("word", "evidence_app"),
        ("pdf", "pdf_evidence_app"),
        ("xlsx", "xlsx_evidence_app"),
        ("edits", "edit_app"),
    ],
)
def test_explicit_review_links_exact_revision_without_rewriting_generation(
    request, kind, fixture, tmp_path
):
    x = request.getfixturevalue(fixture)
    with TestClient(x.app) as client:
        path, fields, offer = generated(client, x, kind)
        before = snapshot(x)
        confirmation = preview(client, path, fields, kind)
        assert snapshot(x) == before
        assert opened(client, x, fields["native_proposal_id"])["decision"] is None
        result = commit(client, path, confirmation, kind)
        assert result.status_code == 303, result.text
        value = opened(client, x, fields["native_proposal_id"])
        assert value["document"] == offer["document"]
        assert value["can_review"] is False and value["can_reject"] is False
        assert value["decision"]["outcome"] == "confirmed"
        assert value["decision"]["scope_revision"] == int(fields["expected_revision"]) + 1
        assert value["decision"]["proposal_payload_changed"] is False
        import hashlib

        raw = client.get(
            f"/scopes/{x.ids[2]}/download?revision={value['decision']['scope_revision']}"
        ).content
        assert hashlib.sha256(raw).hexdigest() == value["decision"]["scope_sha256"]
        (tmp_path / "retained-proposal-decision.json").write_text(
            json.dumps(value, indent=2), encoding="utf-8"
        )
        (tmp_path / "scope-revision.json").write_bytes(raw)
        after = snapshot(x)
        allowed = {
            "draft_scopes",
            "draft_scope_revisions",
            "draft_workspace_proposal_decisions",
            "audit_events",
        }
        assert {k: v for k, v in before.items() if k not in allowed} == {
            k: v for k, v in after.items() if k not in allowed
        }
        assert len(after["draft_workspace_proposal_decisions"]) == 1 and len(x.calls) == 1
        assert commit(client, path, confirmation, kind).status_code == 409
        assert snapshot(x) == after


@pytest.mark.parametrize("tamper", ["remove", "swap", "csrf"])
def test_signed_review_identity_cannot_be_removed_or_swapped(xlsx_evidence_app, tamper):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        before = snapshot(x)
        if tamper == "remove":
            confirmation.pop("native_proposal_id")
        elif tamper == "swap":
            confirmation["native_proposal_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        else:
            confirmation["csrf_token"] = fields["csrf_token"] + "-invalid"
        result = commit(client, path, confirmation, "xlsx")
        assert result.status_code in {403, 422}, result.text
        assert snapshot(x) == before


def test_rejection_is_explicit_and_blocks_a_previously_signed_confirmation(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, offer = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        reject_path = f"/scopes/{x.ids[2]}/native-proposals/{fields['native_proposal_id']}/reject"
        before = snapshot(x)
        assert (
            client.post(reject_path, data={"csrf_token": fields["csrf_token"]}).status_code == 422
        )
        assert (
            client.post(reject_path, data={"csrf_token": "bad", "confirm": "reject"}).status_code
            == 403
        )
        assert snapshot(x) == before
        result = client.post(
            reject_path, data={"csrf_token": fields["csrf_token"], "confirm": "reject"}
        )
        assert result.status_code == 200, result.text
        value = opened(client, x, fields["native_proposal_id"])
        assert value["document"] == offer["document"]
        assert (
            value["decision"]["outcome"] == "rejected"
            and value["decision"]["scope_revision"] is None
        )
        assert not value["can_review"] and not value["can_reject"]
        after = snapshot(x)
        assert {
            k: v
            for k, v in before.items()
            if k not in {"draft_workspace_proposal_decisions", "audit_events"}
        } == {
            k: v
            for k, v in after.items()
            if k not in {"draft_workspace_proposal_decisions", "audit_events"}
        }
        assert commit(client, path, confirmation, "xlsx").status_code == 409
        assert (
            client.post(
                reject_path, data={"csrf_token": fields["csrf_token"], "confirm": "reject"}
            ).status_code
            == 409
        )
        assert snapshot(x) == after


def test_decision_failure_rolls_back_the_same_scope_save(xlsx_evidence_app, monkeypatch):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        before = snapshot(x)

        def fail(*args, **kwargs):
            raise saved.DraftScopeError("SYNTHETIC_DECISION_FAILURE", 409)

        with monkeypatch.context() as patch:
            patch.setattr(saved, "record_confirmation", fail)
            response = commit(client, path, confirmation, "xlsx")
            assert response.status_code == 409, response.text
        assert snapshot(x) == before
        assert commit(client, path, confirmation, "xlsx").status_code == 303


def test_changed_review_payload_is_recorded_and_decision_corruption_withheld(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        payload = json.loads(fields["payload"])
        payload["defects"][-1]["label"] = "Human corrected label"
        fields["payload"] = json.dumps(payload)
        confirmation = preview(client, path, fields, "xlsx")
        assert commit(client, path, confirmation, "xlsx").status_code == 303
        value = opened(client, x, fields["native_proposal_id"])
        assert value["decision"]["proposal_payload_changed"] is True
        with x.factory() as db:
            db.execute(update(DraftWorkspaceProposalDecision).values(decision_sha256="0" * 64))
            db.commit()
        before = snapshot(x)
        result = client.get(f"/scopes/{x.ids[2]}/native-proposals/{fields['native_proposal_id']}")
        assert (
            result.status_code == 409
            and result.json()["detail"] == "CHAT_PROPOSAL_DECISION_CORRUPT"
        )
        assert snapshot(x) == before


def test_revoked_actor_cannot_confirm_a_saved_proposal(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(is_active=False))
            db.commit()
        before = snapshot(x)
        response = commit(client, path, confirmation, "xlsx")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authentication required"
        assert snapshot(x) == before


def test_matching_manual_review_without_a_link_never_infers_a_decision(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, offer = generated(client, x, "xlsx")
        identity = fields.pop("native_proposal_id")
        response = client.post(path + "/preview", data=fields)
        assert response.status_code == 200, response.text
        token = html.unescape(re.search(r'name="preview_token" value="([^"]+)"', response.text)[1])
        assert (
            commit(
                client, path, fields | {"preview_token": token, "confirm": "save"}, "xlsx"
            ).status_code
            == 303
        )
        value = opened(client, x, identity)
        assert value["document"] == offer["document"]
        assert value["decision"] is None and not value["can_review"]
        assert snapshot(x)["draft_workspace_proposal_decisions"] == []
        assert len(x.calls) == 1


def test_foreign_saved_proposal_cannot_be_linked_before_scope_save(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        with x.factory() as db:
            db.execute(
                update(DraftWorkspaceProposal)
                .where(DraftWorkspaceProposal.id == fields["native_proposal_id"])
                .values(created_by_id=x.ids[1])
            )
            db.commit()
        before = snapshot(x)
        assert commit(client, path, confirmation, "xlsx").status_code == 404
        assert snapshot(x) == before


def test_saved_source_proposal_cannot_be_attributed_to_a_different_review_action(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _path, fields, _ = generated(client, x, "xlsx")
        before = snapshot(x)
        response = client.post(
            f"/scopes/{x.ids[2]}",
            data={
                key: fields[key]
                for key in ("csrf_token", "native_proposal_id", "expected_revision", "payload")
            }
            | {"action": "save"},
        )
        assert response.status_code == 409, response.text
        assert snapshot(x) == before


@pytest.mark.parametrize("tamper", ["prior_revision", "boolean_base"])
def test_decision_record_integrity_requires_more_than_a_matching_checksum(
    xlsx_evidence_app, tamper
):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        path, fields, _ = generated(client, x, "xlsx")
        confirmation = preview(client, path, fields, "xlsx")
        assert commit(client, path, confirmation, "xlsx").status_code == 303
        with x.factory() as db:
            row = db.scalar(select(DraftWorkspaceProposalDecision))
            document = json.loads(row.decision_json)
            if tamper == "prior_revision":
                prior = db.scalar(
                    select(DraftScopeRevision).where(
                        DraftScopeRevision.draft_scope_id == x.ids[2],
                        DraftScopeRevision.revision == int(fields["expected_revision"]),
                    )
                )
                row.scope_revision_id = prior.id
                document["scope_revision"] = prior.revision
                document["scope_sha256"] = saved._hash(prior.envelope_json)
            else:
                document["base_revision"] = True
            row.decision_json = saved._raw(document)
            row.decision_sha256 = saved._hash(row.decision_json)
            db.commit()
        before = snapshot(x)
        response = client.get(f"/scopes/{x.ids[2]}/native-proposals/{fields['native_proposal_id']}")
        assert (
            response.status_code == 409
            and response.json()["detail"] == "CHAT_PROPOSAL_DECISION_CORRUPT"
        )
        assert snapshot(x) == before
