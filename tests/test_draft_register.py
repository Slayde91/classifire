from __future__ import annotations

import copy
import json

import pytest
from test_draft_estimates import add_payload, prepare
from test_draft_scope import sample_payload, setup, uid  # noqa: F401
from test_draft_system_matches import case, counts, create  # noqa: F401

from classifire.models import User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_system_matches as matches
from classifire.services.draft_register import hierarchy_review, register_context
from classifire.services.draft_scope import DraftScopeError, save_revision, validate_payload


def normalized():
    model, _warnings = validate_payload(sample_payload())
    return model.model_dump(mode="json")


def test_linked_register_preserves_blank_and_unresolved_history():
    content = normalized()
    before = copy.deepcopy(content)
    result = hierarchy_review(content)
    assert result[uid(5)]  # Historical Service spans two openings: review, never split.
    assert result[uid(6)] == []
    assert result[uid(4)]  # Blank has no known parent Defect.
    assert content == before
    content["openings"][2]["defect_id"] = uid(1)
    assert hierarchy_review(content)[uid(4)] == []  # Zero services is valid for a blank.
    content["services"][1]["opening_ids"] = []
    assert hierarchy_review(content)[uid(6)]


def test_explicit_saved_prices_no_implicit_recalculation_or_writes(setup, tmp_path, monkeypatch):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        saved = estimates.add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        db.commit()
        original = estimates.revision_bytes(db, actor, draft.id, estimate.id, 2)
        before = counts(db)

        def forbidden(*args, **kwargs):
            raise AssertionError("A register read must not invoke a downstream capability.")

        monkeypatch.setattr(estimates, "create_estimate", forbidden)
        monkeypatch.setattr(estimates, "add_line", forbidden)
        monkeypatch.setattr(matches, "create_match", forbidden)
        empty = register_context(db, actor, draft.id, 2, storage_root=tmp_path)
        assert empty["targets"] == {}
        assert len(empty["estimate_choices"]) == 1
        selected = register_context(
            db,
            actor,
            draft.id,
            2,
            storage_root=tmp_path,
            estimate_selection=f"{estimate.id}:2",
        )
        target = selected["targets"]["service:" + uid(5)]
        assert target["price_text"] == "AUD 2.01 ex tax"
        assert target["price_status"] == "Saved Draft amount"
        assert saved["lines"][0]["subtotal_ex_tax"] == "2.01"
        assert counts(db) == before
        assert estimates.revision_bytes(db, actor, draft.id, estimate.id, 2) == original
        changed = sample_payload()
        changed["services"][0]["quantity"] = "3"
        save_revision(db, actor, draft.id, 2, changed)
        db.commit()
        stale = register_context(
            db,
            actor,
            draft.id,
            3,
            storage_root=tmp_path,
            estimate_selection=f"{estimate.id}:2",
        )
        assert stale["targets"]["service:" + uid(5)]["price_text"] == "AUD 2.01 ex tax"
        assert stale["targets"]["service:" + uid(5)]["price_status"] == "Stale"
        assert estimates.revision_bytes(db, actor, draft.id, estimate.id, 2) == original


def test_register_rejects_other_owner_and_invalid_selection(setup, tmp_path):  # noqa: F811
    with setup() as db:
        actor, draft, estimate = prepare(db)
        with pytest.raises(DraftScopeError) as denied:
            register_context(db, db.get(User, uid(101)), draft.id, 2, storage_root=tmp_path)
        assert denied.value.status_code in {403, 404}
        for selection in ("bad", f"{estimate.id}:0", f"{estimate.id}:01"):
            with pytest.raises(DraftScopeError, match="REGISTER_SELECTION_INVALID"):
                register_context(
                    db,
                    actor,
                    draft.id,
                    2,
                    storage_root=tmp_path,
                    estimate_selection=selection,
                )


def test_system_projection_is_explicit_unapproved_and_does_not_leak_source(case):  # noqa: F811
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        db.commit()
        before = counts(db)
        context = register_context(
            db,
            actor,
            case["draft_id"],
            2,
            storage_root=case["storage_root"],
            match_selection=f"{match.id}:1",
        )
        target = context["targets"]["service:" + uid(5)]
        assert "awaiting review" in target["system_text"]
        assert target["system_status"] == "Unapproved candidate review"
        assert "must-never-export-source-json" not in json.dumps(context)
        assert counts(db) == before
