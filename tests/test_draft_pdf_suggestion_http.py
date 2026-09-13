"""Guarded PostgreSQL HTTP coverage; all provider responses are scripted synthetic data."""

from __future__ import annotations

import json
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import prepared
from test_draft_pdf_scope_templates import Forms
from test_draft_pdf_suggestions import ScriptedPort
from test_draft_pdf_ui import pdf_app as _pdf_app
from test_draft_scope_ui import _csrf, _login
from test_draft_scope_ui import scope_password_hash as _password_hash
from test_shared_file_containment import postgresql_session_factory as _postgres

from classifire.draft_pdf_suggestion_ui import router
from classifire.models import DraftPdfSuggestion, DraftScopeRevision, Estimate, User
from classifire.services import draft_scope as scopes

pdf_setup = _pdf_setup
pdf_app = _pdf_app
postgresql_session_factory = _postgres
scope_password_hash = _password_hash


@pytest.fixture
def suggestion_app(pdf_app, monkeypatch):
    x = pdf_app
    x.app.include_router(router)
    x.port = ScriptedPort()
    x.app.state.draft_pdf_suggestion_port = x.port
    monkeypatch.setattr("classifire.draft_pdf_suggestion_ui.get_settings", lambda: x.settings)
    with x.factory() as db:
        actor, source = prepared(db, x)
        x.source_id = source.id
        x.document_hash = source.document_sha256
        x.original = scopes.revision_bytes(db, actor, x.ids[2])
    x.source_path = f"/scopes/{x.ids[2]}/evidence/{x.source_id}"
    return x


def request_form(client, x):
    page = client.get(x.source_path)
    assert page.status_code == 200, page.text
    return {
        "csrf_token": _csrf(page.text),
        "expected_revision": "1",
        "page": "1",
        "document_hash": x.document_hash,
        "consent": "yes",
    }


def generated(client, x):
    response = client.post(
        x.source_path + "/suggestions", data=request_form(client, x), follow_redirects=False
    )
    assert response.status_code == 303, response.text
    path = response.headers["location"]
    page = client.get(path)
    assert page.status_code == 200, page.text
    payload = json.loads(
        re.search(r'id="scope-initial-payload">(.*?)</script>', page.text, re.S).group(1)
    )
    items = json.loads(
        re.search(r'id="scope-initial-suggestion-items">(.*?)</script>', page.text, re.S).group(1)
    )
    form = {
        "csrf_token": _csrf(page.text),
        "expected_revision": "1",
        "payload": json.dumps(payload),
        "targets": json.dumps(
            [{key: item[key] for key in ("target_kind", "target_id")} for item in items]
        ),
    }
    return path, form, payload


def confirm_form(html):
    form = next(item for item in Forms(html).forms if (item["action"] or "").endswith("/confirm"))
    return {name: fields[0]["value"] for name, fields in form["fields"].items()}


def assert_advice_only_review_page(html):
    """The shared chat adds advice controls, never a second saved-review action."""
    parsed = Forms(html)
    assert not parsed.nested
    assert parsed.ids.count("workspace-chat") == 1
    assert [form["action"] for form in parsed.forms] == ["/logout", None]
    advice = parsed.forms[1]["fields"]
    assert set(advice) == {"prompt", "question", "consent"}
    assert "required" in advice["question"][0]
    assert "required" in advice["consent"][0]
    assert advice["consent"][0]["type"] == "checkbox"


def test_http_review_edit_back_confirm_retains_claims_and_reopens(suggestion_app):
    x = suggestion_app
    with TestClient(x.app) as client:
        _login(client)
        path, form, payload = generated(client, x)
        assert len(x.port.calls) == 1
        assert x.port.calls[0].page_png.startswith(b"\x89PNG")
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=1").content == x.original
        payload["openings"][0]["substrate"] = "Human-reviewed concrete; dimensions unknown"
        payload["observations"] = []
        form["payload"] = json.dumps(payload)
        form["targets"] = json.dumps(
            [
                target
                for target in json.loads(form["targets"])
                if target["target_kind"] != "observation"
            ]
        )
        preview = client.post(path + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        assert "Kept with edits" in preview.text and "Rejected" in preview.text
        back = client.post(path + "/preview", data=dict(form, action="edit"))
        assert back.status_code == 200 and "Human-reviewed concrete" in back.text
        submitted = confirm_form(preview.text)
        saved = client.post(path + "/confirm", data=submitted, follow_redirects=False)
        assert saved.status_code == 303, saved.text
        downloaded = client.get(f"/scopes/{x.ids[2]}/download?revision=2")
        assert downloaded.status_code == 200, downloaded.text
        envelope = downloaded.json()
        assert envelope["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v6"
        assert envelope["content"] == payload
        assert len(envelope["evidence_refs"]) == 3
        assert all(ref["suggestion"]["provider"] == "scripted" for ref in envelope["evidence_refs"])
        reopened = client.get(path)
        assert (
            reopened.status_code == 200 and "Original proposed graph (read-only)" in reopened.text
        )
        assert_advice_only_review_page(reopened.text)
        assert path in client.get(x.source_path).text
        assert client.post(path + "/confirm", data=submitted).status_code == 409
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").content == downloaded.content
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=1").content == x.original
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 2
        assert db.scalar(select(func.count()).select_from(Estimate)) == 0
        assert db.scalar(select(DraftPdfSuggestion.status)) == "applied"


def test_http_explicit_rejection_changes_no_scope_revision(suggestion_app):
    x = suggestion_app
    with TestClient(x.app) as client:
        _login(client)
        path, form, _ = generated(client, x)
        refused = client.post(path + "/reject", data={"csrf_token": form["csrf_token"]})
        assert refused.status_code == 422
        rejected = client.post(
            path + "/reject",
            data={"csrf_token": form["csrf_token"], "confirm": "reject"},
            follow_redirects=False,
        )
        assert rejected.status_code == 303, rejected.text
        page = client.get(path)
        assert "This batch was rejected" in page.text
        assert_advice_only_review_page(page.text)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=1").content == x.original
    with x.factory() as db:
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1
        assert db.scalar(select(DraftPdfSuggestion.status)) == "rejected"


def test_http_consent_csrf_and_permissions_refuse_before_provider(suggestion_app):
    x = suggestion_app
    with TestClient(x.app) as owner, TestClient(x.app) as other:
        _login(owner)
        _login(other, "other")
        form = request_form(owner, x)
        assert (
            owner.post(x.source_path + "/suggestions", data=dict(form, consent="")).status_code
            == 422
        )
        assert (
            owner.post(
                x.source_path + "/suggestions", data=(form | {"csrf_token": "bad"})
            ).status_code
            == 403
        )
        form["csrf_token"] = _csrf(other.get("/scopes").text)
        assert other.post(x.source_path + "/suggestions", data=form).status_code == 404
        with x.factory() as db:
            db.execute(update(User).where(User.id == x.ids[0]).values(role="read_only"))
            db.commit()
        form["csrf_token"] = _csrf(owner.get(x.source_path).text)
        assert owner.post(x.source_path + "/suggestions", data=form).status_code == 403
        assert not x.port.calls


def test_http_preview_confirmation_is_session_bound_and_rejects_extra_claims(suggestion_app):
    x = suggestion_app
    with TestClient(x.app) as first, TestClient(x.app) as second:
        _login(first)
        _login(second)
        path, form, _ = generated(first, x)
        assert first.post(path + "/preview", data=dict(form, provider="trusted")).status_code == 422
        unselected = first.post(path + "/preview", data=dict(form, targets="[]"))
        assert unselected.status_code == 422 and "Keep and review at least one" in unselected.text
        preview = first.post(path + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        submitted = confirm_form(preview.text)
        submitted["csrf_token"] = _csrf(second.get(path).text)
        refused = second.post(path + "/confirm", data=submitted)
        assert refused.status_code == 422 and "preview is invalid or expired" in refused.text
        assert not any(
            (item["action"] or "").endswith("/confirm") for item in Forms(refused.text).forms
        )
        assert second.get(f"/scopes/{x.ids[2]}/download?revision=1").content == x.original
        wrong_source = path.replace(x.source_id, "00000000-0000-0000-0000-000000000099")
        assert first.get(wrong_source).status_code == 404


def test_http_stale_confirmation_preserves_attempted_graph_without_stale_save(suggestion_app):
    x = suggestion_app
    with TestClient(x.app) as client:
        _login(client)
        path, form, _ = generated(client, x)
        preview = client.post(path + "/preview", data=form)
        assert preview.status_code == 200, preview.text
        submitted = confirm_form(preview.text)
        with x.factory() as db:
            actor = db.get(User, x.ids[0])
            current = scopes.read_revision(db, actor, x.ids[2])
            current["content"]["assumptions"].append("Another session saved this note")
            newer = scopes.save_revision(db, actor, x.ids[2], 1, current["content"])
            db.commit()
        refused = client.post(path + "/confirm", data=submitted)
        assert refused.status_code == 409, refused.text
        assert "Unsaved attempted graph" in refused.text and "Draft has changed" in refused.text
        assert_advice_only_review_page(refused.text)
        assert client.get(f"/scopes/{x.ids[2]}/download?revision=2").json() == newer
        assert len(x.port.calls) == 1
