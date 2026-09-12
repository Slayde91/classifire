from __future__ import annotations

import copy

import pytest
from sqlalchemy import func, select
from test_draft_estimates import add_payload
from test_draft_multi_review_reports import review_selection
from test_draft_scope import uid
from test_draft_system_matches import case as _case
from test_draft_system_matches import counts, create

from classifire.models import DraftEstimate, DraftEstimateReport, DraftEstimateRevision, User
from classifire.outputs import draft_estimate as renderers
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches

case = _case


def fast_renderers(monkeypatch):
    monkeypatch.setattr(
        renderers, "render_estimate_report_pdf", lambda s: b"%PDF-1.4\n" + s["sha256"].encode()
    )
    monkeypatch.setattr(
        renderers, "render_estimate_report_xlsx", lambda s: b"PK\x03\x04" + s["sha256"].encode()
    )


def report_counts(db):
    return {
        **counts(db),
        **{
            model.__tablename__: db.scalar(select(func.count()).select_from(model))
            for model in (DraftEstimate, DraftEstimateRevision, DraftEstimateReport)
        },
    }


def prepared(db, case, *, bound=True, scope_revision=2):
    actor = db.get(User, uid(100))
    rows, selected = review_selection(db, case)
    estimate = estimates.create_estimate(
        db,
        actor,
        case["draft_id"],
        scope_revision,
        match_id=rows[0].id if bound else None,
        match_revision=1 if bound else None,
    )
    if scope_revision == 2:
        for revision, payload in enumerate(
            (
                add_payload(),
                add_payload(
                    target_id=uid(6),
                    quantity="0",
                    unit_sell_rate="100",
                    reason="Explicit zero for synthetic commercial exclusion",
                ),
                add_payload(
                    target_kind="blank_opening",
                    target_id=uid(4),
                    quantity=None,
                    unit_sell_rate="2.5",
                    reason="Unknown quantity held for synthetic review",
                ),
            ),
            1,
        ):
            estimates.add_line(db, actor, case["draft_id"], estimate.id, revision, payload)
    return actor, estimate, rows, selected


@pytest.mark.parametrize("bound", [False, True])
def test_complete_collection_keeps_saved_estimate_exact_and_legacy_history(
    case, monkeypatch, bound
):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, rows, selected = prepared(db, case, bound=bound)
        draft_id, estimate_id = case["draft_id"], estimate.id
        envelope = estimates.read_estimate_revision(db, actor, draft_id, estimate_id, 4)
        original = estimates.revision_bytes(db, actor, draft_id, estimate_id, 4)
        before = report_counts(db)
        preview = reports.preview_report(
            db, actor, draft_id, estimate_id, 4, profile="complete", matches=selected[::-1]
        )
        assert preview == reports.preview_report(
            db, actor, draft_id, estimate_id, 4, profile="complete", matches=selected
        )
        assert report_counts(db) == before
        assert preview["estimate"] == envelope and preview["render_version"] == 12
        monkeypatch.setattr(
            matches, "create_match", lambda *a, **k: pytest.fail("implicit matching")
        )
        monkeypatch.setattr(
            estimates, "create_estimate", lambda *a, **k: pytest.fail("implicit estimating")
        )
        legacy = [
            reports.create_report(db, actor, draft_id, estimate_id, 4, profile=profile, matches=[])
            for profile in reports.REPORT_PROFILES
        ]
        history = [(r.id, r.snapshot_json, r.pdf_bytes, r.xlsx_bytes) for r in legacy]
        assert [
            reports.read_report(db, actor, draft_id, estimate_id, r.id)["schema_version"]
            for r in legacy
        ] == [reports.REPORT_SCHEMA_VERSION, reports.COMPLETE_SCHEMA_VERSION]
        row = reports.create_report(
            db, actor, draft_id, estimate_id, 4, profile="complete", matches=selected
        )
        snapshot = reports.read_report(db, actor, draft_id, estimate_id, row.id)
        assert snapshot["schema_version"] == reports.MULTI_COMPLETE_SCHEMA_VERSION
        assert (
            snapshot["estimate"] == envelope
            and reports.report_matches(snapshot) == preview["system_matches"]
        )
        assert "system_match" not in snapshot
        assert snapshot["estimate"]["system_match"] == (
            next(r for r in snapshot["system_matches"] if r["artifact_id"] == rows[0].id)
            if bound
            else None
        )
        assert [line["subtotal_ex_tax"] for line in envelope["lines"]] == ["2.01", "0.00", None]
        assert envelope["summary"]["priced_subtotal_ex_tax"] == "2.01"
        assert estimates.revision_bytes(db, actor, draft_id, estimate_id, 4) == original
        assert not reports.report_staleness(
            db, actor, draft_id, estimate_id, row.id, storage_root=case["storage_root"]
        )
        extra = rows[-1]
        saved = matches.read_match_revision(db, actor, draft_id, extra.id, 1)
        matches.save_review(db, actor, draft_id, extra.id, 1, saved["decisions"])
        assert reports.report_staleness(
            db, actor, draft_id, estimate_id, row.id, storage_root=case["storage_root"]
        ) == ["REPORT_REVIEW_CHANGED"]
        captured = row.id, row.pdf_bytes, row.xlsx_bytes
        db.commit()
    monkeypatch.setattr(renderers, "render_estimate_report_pdf", lambda *a: pytest.fail("rerender"))
    monkeypatch.setattr(
        renderers, "render_estimate_report_xlsx", lambda *a: pytest.fail("rerender")
    )
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert reports.read_report(db, actor, draft_id, estimate_id, captured[0]) == snapshot
        for identity, frozen, pdf, xlsx in [
            *history,
            (captured[0], reports._canonical(snapshot).decode(), captured[1], captured[2]),
        ]:
            assert (
                reports._canonical(
                    reports.read_report(db, actor, draft_id, estimate_id, identity)
                ).decode()
                == frozen
            )
            assert reports.report_bytes(db, actor, draft_id, estimate_id, identity, "pdf") == pdf
            assert reports.report_bytes(db, actor, draft_id, estimate_id, identity, "xlsx") == xlsx
        assert estimates.revision_bytes(db, actor, draft_id, estimate_id, 4) == original


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "same-target",
        "wrong-scope",
        "missing-bound",
        "newer-bound",
        "profile",
        "invalid-revision",
        "too-many",
        "non-list",
    ],
)
def test_invalid_explicit_collection_refused_without_writes(case, monkeypatch, change):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, rows, selected = prepared(
            db,
            case,
            bound=change != "wrong-scope",
            scope_revision=1 if change == "wrong-scope" else 2,
        )
        kwargs = {"profile": "complete", "matches": selected}
        if change == "duplicate":
            selected.append(selected[0].copy())
        elif change == "same-target":
            selected.append({"match_id": create(db, case).id, "match_revision": 1})
        elif change == "missing-bound":
            selected.pop(0)
        elif change == "newer-bound":
            old = matches.read_match_revision(db, actor, case["draft_id"], rows[0].id, 1)
            matches.save_review(db, actor, case["draft_id"], rows[0].id, 1, old["decisions"])
            selected[0]["match_revision"] = 2
        elif change == "profile":
            kwargs["profile"] = "estimate-only"
        elif change == "invalid-revision":
            selected[0]["match_revision"] = True
        elif change == "too-many":
            kwargs["matches"] = [
                {"match_id": uid(1000 + i), "match_revision": 1} for i in range(31)
            ]
        elif change == "non-list":
            kwargs["matches"] = {}
        before = report_counts(db)
        with pytest.raises(scopes.DraftScopeError):
            reports.create_report(
                db,
                actor,
                case["draft_id"],
                estimate.id,
                1 if change == "wrong-scope" else 4,
                **kwargs,
            )
        assert report_counts(db) == before


@pytest.mark.parametrize(
    "change", ["empty", "reverse", "duplicate", "singular", "profile", "renderer", "missing-bound"]
)
def test_resealed_complete_snapshot_enforces_collection_contract(case, monkeypatch, change):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, rows, selected = prepared(db, case)
        row = reports.create_report(
            db, actor, case["draft_id"], estimate.id, 4, profile="complete", matches=selected
        )
        snapshot = copy.deepcopy(
            reports.read_report(db, actor, case["draft_id"], estimate.id, row.id)
        )
        if change == "empty":
            snapshot["system_matches"] = []
        elif change == "reverse":
            snapshot["system_matches"].reverse()
        elif change == "duplicate":
            snapshot["system_matches"].append(copy.deepcopy(snapshot["system_matches"][0]))
        elif change == "singular":
            snapshot["system_match"] = snapshot["system_matches"][0]
        elif change == "profile":
            snapshot["profile"] = "estimate-only"
        elif change == "renderer":
            snapshot["render_version"] = 3
        else:
            snapshot["system_matches"] = [
                r for r in snapshot["system_matches"] if r["artifact_id"] != rows[0].id
            ]
        snapshot["sha256"] = reports._checksum(snapshot)
        with pytest.raises(scopes.DraftScopeError, match="ESTIMATE_REPORT_SNAPSHOT_INVALID"):
            reports.validate_report_snapshot(snapshot)


def test_every_review_rechecked_after_render_and_on_read(case, monkeypatch):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, rows, selected = prepared(db, case, bound=False)
        row = reports.create_report(
            db, actor, case["draft_id"], estimate.id, 4, profile="complete", matches=selected
        )
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
        with pytest.raises(scopes.DraftScopeError, match="ESTIMATE_REPORT_SOURCE_CHANGED"):
            reports.create_report(
                db, actor, case["draft_id"], estimate.id, 4, profile="complete", matches=selected
            )
        assert report_counts(db) == before
        with pytest.raises(scopes.DraftScopeError, match="ESTIMATE_REPORT_INTEGRITY_FAILED"):
            reports.read_report(db, actor, case["draft_id"], estimate.id, row.id)


@pytest.mark.parametrize("failure", ["exception", "mutation", "oversize"])
def test_failed_pair_is_atomic(case, monkeypatch, failure):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, _, selected = prepared(db, case)
        before = report_counts(db)

        def invalid(snapshot):
            if failure == "exception":
                raise ValueError("private renderer error")
            if failure == "mutation":
                snapshot["system_matches"].pop()
                return b"PK\x03\x04fixture"
            from classifire.services.draft_scope_reports import MAX_OUTPUT_BYTES

            return b"PK\x03\x04" + b"x" * MAX_OUTPUT_BYTES

        monkeypatch.setattr(renderers, "render_estimate_report_xlsx", invalid)
        with pytest.raises(scopes.DraftScopeError):
            reports.create_report(
                db, actor, case["draft_id"], estimate.id, 4, profile="complete", matches=selected
            )
        assert report_counts(db) == before


def test_context_only_technical_permission_filters_list_and_rechecks_export(case, monkeypatch):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, estimate, _, selected = prepared(db, case, bound=False)
        draft_id, estimate_id = case["draft_id"], estimate.id
        db.commit()
        before = report_counts(db)
        transient = reports.create_report(
            db, actor, draft_id, estimate_id, 4, profile="complete", matches=selected
        )
        db.rollback()
        assert report_counts(db) == before and db.get(DraftEstimateReport, transient.id) is None
        old = reports.create_report(db, actor, draft_id, estimate_id, 4, profile="complete")
        row = reports.create_report(
            db, actor, draft_id, estimate_id, 4, profile="complete", matches=selected
        )
        db.commit()
        with pytest.raises(scopes.DraftScopeError) as denied:
            reports.read_report(db, db.get(User, uid(101)), draft_id, estimate_id, row.id)
        assert denied.value.status_code == 404
        actor.role = "project_manager"
        db.commit()
        assert [r.id for r in reports.list_reports(db, actor, draft_id, estimate_id)] == [old.id]
        assert (
            reports.read_report(db, actor, draft_id, estimate_id, old.id)["profile"] == "complete"
        )
        for operation in (
            lambda: reports.read_report(db, actor, draft_id, estimate_id, row.id),
            lambda: reports.report_bytes(db, actor, draft_id, estimate_id, row.id, "pdf"),
        ):
            with pytest.raises(scopes.DraftScopeError) as denied:
                operation()
            assert denied.value.status_code == 403
        actor.role = "estimator"
        db.commit()
        output = reports._output

        def revoked(*args):
            value = output(*args)
            actor.role = "project_manager"
            db.flush()
            return value

        monkeypatch.setattr(reports, "_output", revoked)
        before = report_counts(db)
        with pytest.raises(scopes.DraftScopeError) as denied:
            reports.report_bytes(db, actor, draft_id, estimate_id, row.id, "pdf")
        assert denied.value.status_code == 403
        assert report_counts(db) == before
