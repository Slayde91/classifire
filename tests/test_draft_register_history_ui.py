"""Isolated HTTP and saved-artifact regressions for the integrated register."""

from __future__ import annotations

import copy
import html
import json
import re
from types import SimpleNamespace
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_draft_estimates import add_payload
from test_draft_scope_ui import _csrf, _login, _payload, _uid
from test_draft_scope_ui import scope_app as _scope_app
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_draft_system_matches import case as _match_case
from test_draft_system_matches import create as create_match
from test_draft_word_evidence_outputs import word_scope

from classifire.models import User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches
from classifire.services.draft_register import register_context
from classifire.services.draft_scope_evidence import observation_hash

scope_app = _scope_app
scope_password_hash = _scope_password_hash
match_case = _match_case


@pytest.fixture
def history_app(scope_app):
    x = SimpleNamespace(app=scope_app.app, factory=scope_app.factory, users=scope_app.users)
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        draft = scopes.create_draft_project(db, actor, "REGISTER-HISTORY", "Synthetic history")
        x.draft_id = draft.id
        scopes.save_revision(db, actor, draft.id, 1, _payload())
        estimate = estimates.create_estimate(db, actor, draft.id, 2)
        x.estimate_id = estimate.id
        first = estimates.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        estimates.override_line(
            db,
            actor,
            draft.id,
            estimate.id,
            2,
            first["lines"][0]["line_id"],
            {"quantity": "2", "unit_sell_rate": "2", "reason": "Synthetic revised price"},
        )
        db.commit()
        x.scope_original = scopes.read_revision(db, actor, draft.id, 2)
        x.estimate_original = estimates.revision_bytes(db, actor, draft.id, estimate.id, 2)
    x.path = f"/scopes/{x.draft_id}"
    x.selection = f"{x.estimate_id}:2"
    x.selected_path = x.path + "?" + urlencode({"estimate": x.selection})
    return x


def script(page, identity):
    match = re.search(
        r'<script[^>]+id="' + re.escape(identity) + r'"[^>]*>(.*?)</script>', page, re.S
    )
    assert match is not None
    return json.loads(match.group(1))


def action(page):
    match = re.search(r'<form[^>]+action="([^"]+)"[^>]+id="scope-editor"', page)
    assert match is not None
    return html.unescape(match.group(1))


def post(client, page, payload, *, revision=2, command="validate"):
    return client.post(
        action(page),
        data={
            "csrf_token": _csrf(page),
            "payload": json.dumps(payload),
            "expected_revision": str(revision),
            "action": command,
        },
        follow_redirects=False,
    )


def test_historical_scope_get_uses_exact_revision_and_preserves_latest(history_app):
    x = history_app
    later = _payload()
    later["services"][0]["label"] = "Later saved service"
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        scopes.save_revision(db, actor, x.draft_id, 2, later)
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        old = client.get(x.path + "?revision=2")
        assert old.status_code == 200
        assert script(old.text, "scope-initial-payload") == x.scope_original["content"]
        assert 'name="expected_revision" value="2"' in old.text
        latest = client.get(x.path)
        assert (
            script(latest.text, "scope-initial-payload")["services"][0]["label"]
            == "Later saved service"
        )
        assert client.get(x.path + "?revision=999").status_code == 404


def test_selectors_survive_validate_save_and_saved_price_becomes_stale(history_app):
    x = history_app
    changed = _payload()
    changed["services"][0]["quantity"] = "3"
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(x.selected_path)
        assert page.status_code == 200
        assert parse_qs(urlsplit(action(page.text)).query) == {"estimate": [x.selection]}
        validated = post(client, page.text, changed)
        assert validated.status_code == 200
        assert script(validated.text, "scope-initial-payload")["services"][0]["quantity"] == "3"
        context = script(validated.text, "scope-register-context")
        assert context["estimate_selection"] == x.selection
        assert context["targets"]["service:" + _uid(5)]["price_text"] == "AUD 2.01 ex tax"
        saved = post(client, validated.text, changed, command="save")
        assert saved.status_code == 303
        assert parse_qs(urlsplit(saved.headers["location"]).query) == {"estimate": [x.selection]}
        reopened = client.get(saved.headers["location"])
        assert reopened.status_code == 200
        context = script(reopened.text, "scope-register-context")
        target = context["targets"]["service:" + _uid(5)]
        assert target["price_text"] == "AUD 2.01 ex tax" and target["price_status"] == "Stale"
        assert context["estimate_selection"] == x.selection
    with x.factory() as db:
        assert (
            estimates.revision_bytes(
                db, db.get(User, x.users["owner"]), x.draft_id, x.estimate_id, 2
            )
            == x.estimate_original
        )


def test_future_revision_conflict_retains_unsaved_payload_and_selection(history_app):
    x = history_app
    changed = _payload()
    changed["defects"][0]["description"] = "Preserve this unsaved human description"
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(x.selected_path)
        response = post(client, page.text, changed, revision=999, command="save")
        assert response.status_code == 409
        assert script(response.text, "scope-initial-payload") == changed
        assert "Saved system or pricing context is unavailable" in response.text
        assert parse_qs(urlsplit(action(response.text)).query) == {"estimate": [x.selection]}
    with x.factory() as db:
        assert (
            scopes.read_revision(db, db.get(User, x.users["owner"]), x.draft_id) == x.scope_original
        )


def test_historical_estimate_option_is_selected_and_amount_does_not_use_latest(history_app):
    x = history_app
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(x.selected_path)
        assert page.status_code == 200
        assert f'<option value="{x.selection}" selected>' in page.text
        assert "Selected historical estimate" in page.text
        context = script(page.text, "scope-register-context")
        assert context["targets"]["service:" + _uid(5)]["price_text"] == "AUD 2.01 ex tax"
        assert {item["value"] for item in context["estimate_choices"]} == {
            f"{x.estimate_id}:3",
            x.selection,
        }


def test_unavailable_optional_artifact_keeps_manual_editor(history_app):
    x = history_app
    with TestClient(x.app) as client:
        _login(client)
        response = client.get(x.path + "?estimate=" + _uid(999) + ":1")
        assert response.status_code == 200
        assert script(response.text, "scope-initial-payload") == x.scope_original["content"]
        assert script(response.text, "scope-register-context")["targets"] == {}
        assert "Saved system or pricing context is unavailable" in response.text


def test_explicit_match_has_opening_qualifier_and_historical_option(match_case):
    x = match_case
    with x["factory"]() as db:
        actor = db.get(User, _uid(100))
        match = create_match(db, x)
        saved = matches.read_match_revision(db, actor, x["draft_id"], match.id, 1)
        matches.save_review(db, actor, x["draft_id"], match.id, 1, saved["decisions"])
        db.commit()
        context = register_context(
            db,
            actor,
            x["draft_id"],
            2,
            storage_root=x["storage_root"],
            match_selection=f"{match.id}:1",
        )
        target = context["targets"]["service:" + _uid(5)]
        assert target["system_opening_id"] == _uid(2)
        assert saved["scope"]["content"]["services"][0]["opening_ids"] == [_uid(2), _uid(3)]
        choices = {item["value"]: item["label"] for item in context["match_choices"]}
        assert f"{match.id}:2" in choices and "historical" in choices[f"{match.id}:1"]


def test_saved_word_source_status_remains_stale_after_reopening(history_app):
    x = history_app
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        content = x.scope_original["content"]
        ref = copy.deepcopy(word_scope()["evidence_refs"][-1])
        ref.update(
            target_kind="service",
            target_id=_uid(5),
            target_sha256=observation_hash(content["services"][0]),
        )
        scopes._append_revision(db, actor, x.draft_id, 2, content, entity_evidence_refs=[ref])
        changed = copy.deepcopy(content)
        changed["services"][0]["label"] = "Human changed source-bound field"
        scopes.save_revision(db, actor, x.draft_id, 3, changed)
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        response = client.get(x.path)
        assert response.status_code == 200
        context = script(response.text, "scope-register-context")
        assert "changed since Word review" in context["evidence_refs"][0]["status"]
        assert context["evidence_refs"][0]["source_id"] == ref["source_id"]
