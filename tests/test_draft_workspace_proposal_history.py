"""Explicit native proposal retention uses synthetic evidence and mocked replies."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_draft_scope_ui import _csrf
from test_draft_workspace_chat import snapshot
from test_draft_workspace_pdf_proposals import pdf_evidence_app as _pdf_evidence_app
from test_draft_workspace_scope_edits import edit_app as _edit_app
from test_draft_workspace_xlsx_proposals import evidence_app as _evidence_app
from test_draft_workspace_xlsx_proposals import pdf_app as _pdf_app
from test_draft_workspace_xlsx_proposals import pdf_setup as _pdf_setup
from test_draft_workspace_xlsx_proposals import postgresql_session_factory as _postgres
from test_draft_workspace_xlsx_proposals import provider, start
from test_draft_workspace_xlsx_proposals import scope_password_hash as _password_hash
from test_draft_workspace_xlsx_proposals import word_app as _word_app
from test_draft_workspace_xlsx_proposals import xlsx_evidence_app as _xlsx_app

from classifire.models import DraftScopeXlsxSource, DraftWorkspaceProposal, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_workspace_proposals as saved

pdf_evidence_app = _pdf_evidence_app
edit_app = _edit_app
xlsx_evidence_app = _xlsx_app
evidence_app = _evidence_app
pdf_app = _pdf_app
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres
scope_password_hash = _password_hash
word_app = _word_app


def generated(client, x):
    provider(x)
    value, headers, _csrf_token, context = start(client, x)
    x.generation_before = snapshot(x)
    response = client.post("/workspace/assistant/message", json=value, headers=headers)
    assert snapshot(x) == x.generation_before
    assert response.status_code == 200, response.text
    offer = response.json()["retention"]
    assert offer["document"]["context"] == context
    return headers, offer


def form(client, x, offer):
    return {
        "csrf_token": _csrf(client.get(f"/scopes/{x.ids[2]}").text),
        "document": json.dumps(offer["document"]),
        "authorization": offer["authorization"],
    }


def test_save_duplicate_reopen_and_stale_proposal_never_apply_scope(xlsx_evidence_app):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        headers, offer = generated(client, x)
        before = x.generation_before
        assert snapshot(x) == before
        path = f"/scopes/{x.ids[2]}/native-proposals"
        assert client.get(path).json() == {"proposals": []}
        fields = form(client, x, offer)
        assert client.post(path, data={**fields, "csrf_token": "wrong"}).status_code == 403
        result = client.post(path, data=fields)
        assert result.status_code == 200, result.text
        assert client.post(path, data=fields).json() == result.json()
        identity = result.json()["id"]
        after = snapshot(x)
        assert len(after["draft_workspace_proposals"]) == 1
        assert {
            k: v for k, v in after.items() if k not in {"draft_workspace_proposals", "audit_events"}
        } == {
            k: v
            for k, v in before.items()
            if k not in {"draft_workspace_proposals", "audit_events"}
        }
        opened = client.get(path + "/" + identity)
        assert opened.status_code == 200, opened.text
        assert opened.headers["cache-control"] == "no-store"
        assert opened.json()["document"] == offer["document"]
        assert opened.json()["can_review"] is True
        assert len(client.get(path).json()["proposals"]) == 1
        with x.factory() as db:
            row = db.get(DraftWorkspaceProposal, identity)
            assert hashlib.sha256(row.proposal_json.encode()).hexdigest() == row.proposal_sha256
            actor = db.get(User, x.ids[0])
            content = scopes.read_revision(db, actor, x.ids[2])["content"]
            scopes.save_revision(db, actor, x.ids[2], 1, content)
            db.commit()
        historic = client.get(path + "/" + identity)
        assert historic.status_code == 200, historic.text
        assert historic.json()["can_review"] is False
        assert historic.json()["document"] == offer["document"]
        assert len(x.calls) == 1


@pytest.mark.parametrize("change", ["response", "context", "identity", "authorization", "expired"])
def test_forged_or_expired_retention_is_refused(xlsx_evidence_app, monkeypatch, change):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _, offer = generated(client, x)
        before = snapshot(x)
        bad = copy.deepcopy(offer)
        if change == "response":
            bad["document"]["response"]["answer"] = "Forged result"
        elif change == "context":
            bad["document"]["context"]["summary"] = "Forged source"
        elif change == "identity":
            bad["document"]["actor_id"] = x.ids[1]
        elif change == "authorization":
            bad["authorization"] = "invalid"
        else:
            real = saved._signer(x.settings)
            binding = real.loads(bad["authorization"])
            with monkeypatch.context() as patch:
                patch.setattr(
                    "itsdangerous.timed.TimestampSigner.get_timestamp",
                    lambda self: int(datetime.now(UTC).timestamp()) - 901,
                )
                bad["authorization"] = real.dumps(binding)
        response = client.post(f"/scopes/{x.ids[2]}/native-proposals", data=form(client, x, bad))
        assert response.status_code in {409, 422}, response.text
        assert snapshot(x) == before
        assert len(x.calls) == 1


@pytest.mark.parametrize("change", ["permission", "foreign", "corrupt", "expired_scan"])
def test_saved_record_requires_current_access_and_integrity(xlsx_evidence_app, change):
    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _, offer = generated(client, x)
        path = f"/scopes/{x.ids[2]}/native-proposals"
        result = client.post(path, data=form(client, x, offer))
        assert result.status_code == 200
        identity = result.json()["id"]
        with x.factory() as db:
            if change == "permission":
                db.execute(update(User).where(User.id == x.ids[0]).values(is_active=False))
            elif change == "foreign":
                db.execute(
                    update(DraftWorkspaceProposal)
                    .where(DraftWorkspaceProposal.id == identity)
                    .values(created_by_id=x.ids[1])
                )
            elif change == "corrupt":
                db.execute(
                    update(DraftWorkspaceProposal)
                    .where(DraftWorkspaceProposal.id == identity)
                    .values(proposal_sha256="0" * 64)
                )
            else:
                source = db.get(DraftScopeXlsxSource, x.xlsx_selection["source_id"])
                scan = json.loads(source.scan_json)
                scan["database_date"] = (datetime.now(UTC) - timedelta(days=90)).isoformat()
                source.scan_json = json.dumps(scan)
            db.commit()
        response = client.get(path + "/" + identity, follow_redirects=False)
        assert response.status_code in {302, 303, 401, 403, 404, 409}, response.text
        assert "Scripted source-bound proposal" not in response.text
        assert len(x.calls) == 1


@pytest.mark.parametrize("kind", ["word", "pdf", "edits"])
def test_existing_other_proposal_paths_retain_exact_review(request, kind):
    import test_draft_workspace_pdf_proposals as pdf
    import test_draft_workspace_scope_edits as edits
    import test_draft_workspace_word_proposals as word

    module = {"word": word, "pdf": pdf, "edits": edits}[kind]
    x = request.getfixturevalue(
        {"word": "evidence_app", "pdf": "pdf_evidence_app", "edits": "edit_app"}[kind]
    )
    module.provider(x)
    with TestClient(x.app) as client:
        values = module.start(client, x)
        value, headers = values[:2]
        before = snapshot(x)
        response = client.post("/workspace/assistant/message", json=value, headers=headers)
        assert response.status_code == 200, response.text
        assert snapshot(x) == before
        result = response.json()
        offer = result["retention"]
        path = f"/scopes/{x.ids[2]}/native-proposals"
        retained = client.post(path, data=form(client, x, offer))
        assert retained.status_code == 200, retained.text
        opened = client.get(path + "/" + retained.json()["id"])
        assert opened.status_code == 200, opened.text
        assert opened.json()["document"] == offer["document"]
        assert opened.json()["can_review"] is True
        key = "edit_proposal" if kind == "edits" else "proposal"
        assert opened.json()["document"]["response"][key] == result[key]
        assert len(x.calls) == 1


def test_retention_failure_rolls_back_and_quota_is_bounded(xlsx_evidence_app, monkeypatch):
    from classifire.models import new_id

    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _, offer = generated(client, x)
        path = f"/scopes/{x.ids[2]}/native-proposals"
        before = snapshot(x)
        with monkeypatch.context() as patch:

            def fail_audit(*args, **kwargs):
                raise ValueError("synthetic audit failure")

            patch.setattr(saved, "record_audit", fail_audit)
            assert client.post(path, data=form(client, x, offer)).status_code == 422
        assert snapshot(x) == before
        with x.factory() as db:
            for _ in range(100):
                document = copy.deepcopy(offer["document"])
                document["id"] = new_id()
                raw = saved._raw(document)
                db.add(
                    DraftWorkspaceProposal(
                        id=document["id"],
                        draft_scope_id=x.ids[2],
                        created_by_id=x.ids[0],
                        base_revision=1,
                        proposal_json=raw,
                        proposal_sha256=saved._hash(raw),
                    )
                )
            db.commit()
        before = snapshot(x)
        response = client.post(path, data=form(client, x, offer))
        assert response.status_code == 429, response.text
        assert snapshot(x) == before


def test_retention_offer_size_limit_has_no_partial_record(xlsx_evidence_app):
    from classifire.services import draft_workspace_chat as chat

    x = xlsx_evidence_app
    with TestClient(x.app) as client:
        _, retained = generated(client, x)
        doc = retained["document"]
        before = snapshot(x)
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            assert (
                saved.offer(
                    actor,
                    chat.parse_workspace(doc["request"]),
                    doc["context"],
                    doc["response"],
                    {"large": "x" * saved.MAX_BYTES},
                    settings=x.settings,
                    injected=True,
                )
                is None
            )
        assert snapshot(x) == before
