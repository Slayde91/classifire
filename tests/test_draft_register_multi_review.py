"""Explicit row-qualified saved review sets never select latest or write artifacts."""

from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest
from fastapi.testclient import TestClient
from test_draft_register_history_ui import script
from test_draft_scope_ui import _app, _login, _uid
from test_draft_scope_ui import scope_password_hash as _scope_password_hash
from test_draft_system_matches import case as _case
from test_draft_system_matches import counts, create

from classifire.models import User
from classifire.services import draft_system_matches as matches
from classifire.services.draft_register import register_context
from classifire.services.draft_scope import DraftScopeError

case = _case
scope_password_hash = _scope_password_hash


def _reviews(db, case):
    return [
        create(db, case),
        create(db, case, service_id=_uid(6)),
        create(db, case, opening_id=_uid(4), service_id=None),
    ]


def _context(db, case, values):
    return register_context(
        db,
        db.get(User, _uid(100)),
        case["draft_id"],
        2,
        storage_root=case["storage_root"],
        match_selections=values,
    )


def test_three_row_reviews_keep_exact_history_when_one_is_updated(case):
    with case["factory"]() as db:
        actor = db.get(User, _uid(100))
        rows = _reviews(db, case)
        selections = [f"{row.id}:1" for row in rows]
        originals = [matches.revision_bytes(db, actor, case["draft_id"], row.id, 1) for row in rows]
        saved = matches.read_match_revision(db, actor, case["draft_id"], rows[0].id, 1)
        matches.save_review(db, actor, case["draft_id"], rows[0].id, 1, saved["decisions"])
        db.commit()
        before = counts(db)
        historical = _context(db, case, selections)
        assert historical["match_selections"] == selections
        assert len(historical["row_targets"]) == 3
        assert {target["match_selection"] for target in historical["row_targets"].values()} == set(
            selections
        )
        updated = _context(db, case, [f"{rows[0].id}:2", *selections[1:]])
        assert len(updated["row_targets"]) == 3
        assert {target["match_selection"] for target in updated["row_targets"].values()} == {
            f"{rows[0].id}:2",
            *selections[1:],
        }
        assert counts(db) == before
        assert [
            matches.revision_bytes(db, actor, case["draft_id"], row.id, 1) for row in rows
        ] == originals
        # Explicit downloads are audited; the preceding register reads were not.
        assert counts(db) == {**before, "audit_events": before["audit_events"] + len(rows)}


def test_shared_service_reviews_remain_opening_qualified(case):
    with case["factory"]() as db:
        first = create(db, case)
        second = create(db, case, opening_id=_uid(3))
        db.commit()
        context = _context(db, case, [f"{first.id}:1", f"{second.id}:1"])
        assert set(context["row_targets"]) == {
            f"opening:{_uid(2)}:service:{_uid(5)}",
            f"opening:{_uid(3)}:service:{_uid(5)}",
        }
        assert "service:" + _uid(5) not in context["targets"]
        assert len(context["readiness"][_uid(5)]) > 0


def test_conflicting_reviews_for_one_row_fail_without_partial_projection_or_writes(case):
    with case["factory"]() as db:
        first = create(db, case)
        second = create(db, case)
        db.commit()
        before = counts(db)
        with pytest.raises(DraftScopeError, match="REGISTER_REVIEW_TARGET_CONFLICT"):
            _context(db, case, [f"{first.id}:1", f"{second.id}:1"])
        assert counts(db) == before


@pytest.mark.parametrize("values", [[""], ["invalid"], [f"{_uid(900)}:1"] * 31])
def test_malformed_or_over_limit_review_sets_fail_without_writes(case, values):
    with case["factory"]() as db:
        before = counts(db)
        with pytest.raises(DraftScopeError, match="REGISTER_SELECTION_INVALID"):
            _context(db, case, values)
        assert counts(db) == before


def test_explicit_reviews_outside_latest_picker_window_are_not_lost(case, monkeypatch):
    with case["factory"]() as db:
        rows = _reviews(db, case)
        db.commit()
        selections = [f"{row.id}:1" for row in rows]
        monkeypatch.setattr(matches, "list_matches", lambda *args: [])
        context = _context(db, case, selections)
        assert {item["value"] for item in context["match_choices"]} == set(selections)
        assert len(context["row_targets"]) == 3


def test_register_http_preserves_all_refs_and_separate_package_preview_link(
    case, scope_password_hash, monkeypatch
):
    from types import SimpleNamespace

    with case["factory"]() as db:
        actor = db.get(User, _uid(100))
        actor.email = "owner@scope.example.test"
        actor.password_hash = scope_password_hash
        rows = _reviews(db, case)
        db.commit()
        selections = [f"{row.id}:1" for row in rows]
    monkeypatch.setattr(
        "classifire.draft_scope_ui.get_settings",
        lambda: SimpleNamespace(storage_root=case["storage_root"]),
    )
    app = _app(case["factory"])
    path = f"/scopes/{case['draft_id']}"
    with TestClient(app) as client:
        _login(client)
        with case["factory"]() as db:
            before = counts(db)
        page = client.get(
            path + "?" + urlencode([("revision", "2"), *[("match", value) for value in selections]])
        )
        assert page.status_code == 200
        context = script(page.text, "scope-register-context")
        assert context["match_selections"] == selections
        assert len(context["row_targets"]) == 3
        assert 'name="match" multiple' in page.text
        action = re.search(r'<form[^>]+action="([^"]+)"[^>]+id="scope-editor"', page.text)
        assert parse_qs(urlsplit(html.unescape(action.group(1))).query)["match"] == selections
        link = re.search(r'data-register-package href="([^"]+)"', page.text)
        assert parse_qs(urlsplit(html.unescape(link.group(1))).query) == {
            "scope_revision": ["2"],
            "matches": selections,
        }
        invalid = client.get(
            path + "?" + urlencode([("match", selections[0]), ("match", selections[0])])
        )
        assert invalid.status_code == 200
        assert "REGISTER_SELECTION_INVALID" in invalid.text
        assert "data-register-package href=" not in invalid.text
        assert "Resolve selected reviews and estimate before packaging" in invalid.text
        assert script(invalid.text, "scope-initial-payload")
        single = client.get(path + "?" + urlencode({"revision": 2, "match": selections[0]}))
        single_link = re.search(r'data-register-package href="([^"]+)"', single.text)
        assert parse_qs(urlsplit(html.unescape(single_link.group(1))).query) == {
            "scope_revision": ["2"],
            "match_id": [rows[0].id],
            "match_revision": ["1"],
        }
        with case["factory"]() as db:
            assert counts(db) == before
