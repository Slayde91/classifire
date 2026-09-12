from __future__ import annotations

import copy

import pytest
from sqlalchemy import func, select
from test_draft_scope import uid
from test_draft_scope_reports import _fast_renderers
from test_draft_system_matches import case as _case
from test_draft_system_matches import counts, create

from classifire.models import DraftScopeReport, User
from classifire.outputs import draft_scope as renderers
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as reports
from classifire.services import draft_system_matches as matches

case = _case


def review_selection(db, case):
    rows = [
        create(db, case, opening_id=uid(2), service_id=uid(5)),
        create(db, case, opening_id=uid(2), service_id=uid(6)),
        create(db, case, opening_id=uid(4), service_id=None),
    ]
    return rows, [{"match_id": row.id, "match_revision": 1} for row in rows]


def report_counts(db):
    return {**counts(db), "reports": db.scalar(select(func.count()).select_from(DraftScopeReport))}


def test_exact_collection_preview_pair_restart_and_later_review_never_recalculates(
    case, monkeypatch
):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows, selected = review_selection(db, case)
        before = report_counts(db)
        preview = reports.preview_report(db, actor, case["draft_id"], 2, matches=selected)
        assert report_counts(db) == before
        assert preview == reports.preview_report(
            db, actor, case["draft_id"], 2, matches=selected[::-1]
        )
        assert preview["profile"] == "scope-and-system" and preview["render_version"] == 11
        monkeypatch.setattr(matches, "create_match", lambda *a, **kw: pytest.fail("implicit Match"))
        old = reports.create_report(db, actor, case["draft_id"], 2)
        single = reports.create_report(
            db, actor, case["draft_id"], 2, match_id=rows[0].id, match_revision=1, matches=[]
        )
        histories = [
            (row.id, row.snapshot_json, row.pdf_bytes, row.xlsx_bytes) for row in (old, single)
        ]
        row = reports.create_report(db, actor, case["draft_id"], 2, matches=selected[::-1])
        snapshot = reports.read_report(db, actor, case["draft_id"], row.id)
        assert snapshot["schema_version"] == reports.MULTI_SYSTEM_REPORT_SCHEMA_VERSION
        assert "system_match" not in snapshot
        assert reports.report_matches(snapshot) == preview["system_matches"]
        assert [review["artifact_id"] for review in snapshot["system_matches"]] == sorted(
            r.id for r in rows
        )
        assert all(
            review["scope"] == snapshot["scope"] for review in reports.report_matches(snapshot)
        )
        assert snapshot["scope"]["content"]["services"][1]["quantity"] is None
        assert snapshot["system_matches"] == sorted(
            [matches.read_match_revision(db, actor, case["draft_id"], item.id, 1) for item in rows],
            key=lambda review: review["artifact_id"],
        )
        assert not reports.report_freshness(
            db, actor, case["draft_id"], row.id, storage_root=case["storage_root"]
        )
        last = snapshot["system_matches"][-1]
        matches.save_review(db, actor, case["draft_id"], last["artifact_id"], 1, last["decisions"])
        assert reports.report_freshness(
            db, actor, case["draft_id"], row.id, storage_root=case["storage_root"]
        )
        captured = row.id, row.pdf_bytes, row.xlsx_bytes
        db.commit()
    monkeypatch.setattr(renderers, "render_scope_report_pdf", lambda *a: pytest.fail("rerender"))
    monkeypatch.setattr(renderers, "render_scope_report_xlsx", lambda *a: pytest.fail("rerender"))
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert reports.read_report(db, actor, case["draft_id"], captured[0]) == snapshot
        assert reports.report_bytes(db, actor, case["draft_id"], captured[0], "pdf") == captured[1]
        assert reports.report_bytes(db, actor, case["draft_id"], captured[0], "xlsx") == captured[2]
        for identity, frozen, pdf, xlsx in histories:
            assert (
                reports._canonical(
                    reports.read_report(db, actor, case["draft_id"], identity)
                ).decode()
                == frozen
            )
            assert reports.report_bytes(db, actor, case["draft_id"], identity, "pdf") == pdf
            assert reports.report_bytes(db, actor, case["draft_id"], identity, "xlsx") == xlsx


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "same-target",
        "wrong-scope",
        "mixed",
        "invalid-revision",
        "too-many",
        "non-list",
    ],
)
def test_collection_selection_refused_without_report_or_audit(case, monkeypatch, change):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows, selected = review_selection(db, case)
        kwargs = {"matches": selected}
        revision = 2
        if change == "duplicate":
            selected.append(selected[0].copy())
        elif change == "same-target":
            other = create(db, case)
            selected.append({"match_id": other.id, "match_revision": 1})
        elif change == "wrong-scope":
            revision = 1
        elif change == "mixed":
            kwargs.update(match_id=rows[0].id, match_revision=1)
        elif change == "invalid-revision":
            selected[0]["match_revision"] = True
        elif change == "too-many":
            kwargs["matches"] = [
                {"match_id": uid(1000 + i), "match_revision": 1} for i in range(31)
            ]
        else:
            kwargs["matches"] = {}
        before = report_counts(db)
        with pytest.raises(scopes.DraftScopeError):
            reports.create_report(db, actor, case["draft_id"], revision, **kwargs)
        assert report_counts(db) == before


@pytest.mark.parametrize(
    "change", ["empty", "reverse", "duplicate", "singular", "profile", "renderer"]
)
def test_resealed_collection_snapshot_refuses_invalid_shape_or_authority(case, monkeypatch, change):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        _, selected = review_selection(db, case)
        row = reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        snapshot = copy.deepcopy(reports.read_report(db, actor, case["draft_id"], row.id))
        if change == "empty":
            snapshot["system_matches"] = []
        elif change == "reverse":
            snapshot["system_matches"].reverse()
        elif change == "duplicate":
            snapshot["system_matches"].append(copy.deepcopy(snapshot["system_matches"][0]))
        elif change == "singular":
            snapshot["system_match"] = snapshot["system_matches"][0]
        elif change == "profile":
            snapshot["profile"] = "scope-only"
        else:
            snapshot["render_version"] = 2
        snapshot["sha256"] = reports._checksum(snapshot)
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_REPORT_SNAPSHOT_INVALID"):
            reports.validate_report_snapshot(snapshot)


def test_each_member_rechecked_after_render_and_on_retained_read(case, monkeypatch):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows, selected = review_selection(db, case)
        row = reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        original_read = reports.read_match_revision
        changed_id = sorted(r.id for r in rows)[-1]
        calls = 0

        def changed(*args, **kwargs):
            nonlocal calls
            value = original_read(*args, **kwargs)
            if value["artifact_id"] == changed_id:
                calls += 1
                if calls > 1:
                    value = copy.deepcopy(value)
                    value["created_at"] = "changed after rendering"
            return value

        monkeypatch.setattr(reports, "read_match_revision", changed)
        before = report_counts(db)
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_REPORT_SOURCE_CHANGED"):
            reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        assert report_counts(db) == before
        with pytest.raises(scopes.DraftScopeError, match="DRAFT_REPORT_INTEGRITY_FAILED"):
            reports.read_report(db, actor, case["draft_id"], row.id)


@pytest.mark.parametrize("failure", ["exception", "mutation", "oversize"])
def test_collection_failed_pair_retains_neither_output_nor_audit(case, monkeypatch, failure):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        _, selected = review_selection(db, case)
        before = report_counts(db)

        def invalid(snapshot):
            if failure == "exception":
                raise ValueError("private renderer error")
            if failure == "mutation":
                snapshot["system_matches"].pop()
                return b"PK\x03\x04fixture"
            return b"PK\x03\x04" + b"x" * reports.MAX_OUTPUT_BYTES

        monkeypatch.setattr(renderers, "render_scope_report_xlsx", invalid)
        with pytest.raises(scopes.DraftScopeError):
            reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        assert report_counts(db) == before


def test_collection_permissions_list_filter_and_caller_rollback(case, monkeypatch):
    _fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        _, selected = review_selection(db, case)
        db.commit()
        before = report_counts(db)
        row = reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        db.rollback()
        assert report_counts(db) == before and db.get(DraftScopeReport, row.id) is None
        old = reports.create_report(db, actor, case["draft_id"], 2)
        row = reports.create_report(db, actor, case["draft_id"], 2, matches=selected)
        db.commit()
        with pytest.raises(scopes.DraftScopeError) as denied:
            reports.read_report(db, db.get(User, uid(101)), case["draft_id"], row.id)
        assert denied.value.status_code == 404
        actor.role = "project_manager"
        db.commit()
        assert [item.id for item in reports.list_reports(db, actor, case["draft_id"])] == [old.id]
        before = report_counts(db)
        with pytest.raises(scopes.DraftScopeError) as denied:
            reports.report_bytes(db, actor, case["draft_id"], row.id, "pdf")
        assert denied.value.status_code == 403 and report_counts(db) == before
