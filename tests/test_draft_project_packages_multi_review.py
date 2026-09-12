"""Forward multi-review package selection preserves exact independent artifacts."""

from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import func, select
from test_draft_project_packages import save
from test_draft_scope import uid
from test_draft_system_matches import case as _case
from test_draft_system_matches import counts, create

from classifire.models import AuditEvent, DraftProjectPackage, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as reports
from classifire.services import draft_system_matches as matches

case = _case


def _reviews(db, case):
    return [
        create(db, case, opening_id=uid(2), service_id=uid(5)),
        create(db, case, opening_id=uid(2), service_id=uid(6)),
        create(db, case, opening_id=uid(4), service_id=None),
    ]


def _selection(rows):
    return {
        "scope_revision": 2,
        "matches": [{"match_id": row.id, "match_revision": 1} for row in rows],
    }


def _counts(db):
    return {
        **counts(db),
        "packages": db.scalar(select(func.count()).select_from(DraftProjectPackage)),
    }


def test_multi_review_preview_saves_exact_independent_members_and_history(case, monkeypatch):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows = _reviews(db, case)
        selected = _selection(rows)
        originals = {
            row.id: matches.revision_bytes(db, actor, case["draft_id"], row.id, 1) for row in rows
        }

        def forbidden(*args, **kwargs):
            pytest.fail("Package composition must not run a downstream capability")

        monkeypatch.setattr(matches, "create_match", forbidden)
        monkeypatch.setattr(estimates, "create_estimate", forbidden)
        monkeypatch.setattr(reports, "create_report", forbidden)
        before = _counts(db)
        preview = packages.preview(db, actor, case["draft_id"], selected)
        assert _counts(db) == before
        assert preview["manifest"]["schema_version"] == packages.SCHEMA_V6
        assert preview["manifest"]["origins"] == []
        assert preview["manifest"]["capabilities"] == {
            "scope": "included",
            "system_match": "included",
            "estimate": "not_selected",
            "reports": "not_selected",
        }
        assert preview == packages.preview(
            db,
            actor,
            case["draft_id"],
            {**selected, "matches": list(reversed(selected["matches"]))},
        )
        first = save(db, actor, case["draft_id"], selected)
        content = packages.package_bytes(db, actor, case["draft_id"], first.id)
        manifest, members = packages.inspect_archive(content)
        assert set(members) == {
            "artifacts/scope.json",
            *[packages.match_member_path(row.id) for row in rows],
        }
        for row in rows:
            assert members[packages.match_member_path(row.id)] == originals[row.id]
        blank = json.loads(originals[rows[-1].id])
        assert blank["target"]["blank_opening"] is True
        assert blank["target"]["service_ids"] == []
        assert len(blank["scope"]["content"]["services"]) == 2
        assert blank["scope"]["content"]["services"][1]["quantity"] is None
        assert all(item["membership"] == "withheld" for item in manifest["source_manifest"])
        assert all("system-match-" in item["reference"] for item in manifest["source_manifest"])
        assert b"must-never-export-source-json" not in content
        saved = matches.read_match_revision(db, actor, case["draft_id"], rows[0].id, 1)
        decisions = copy.deepcopy(saved["decisions"])
        for decision in decisions:
            decision.update(decision="keep", notes="Later explicit synthetic review")
        matches.save_review(db, actor, case["draft_id"], rows[0].id, 1, decisions)
        assert "PACKAGE_REVIEW_CHANGED" in packages.staleness(
            db, actor, case["draft_id"], manifest, storage_root=case["storage_root"]
        )
        assert packages.package_bytes(db, actor, case["draft_id"], first.id) == content
        selected["matches"][0]["match_revision"] = 2
        second = save(db, actor, case["draft_id"], selected, 1)
        assert second.parent_hash == first.manifest_hash
        assert second.archive_bytes != content
        ids = first.id, second.id
        db.commit()
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert packages.package_bytes(db, actor, case["draft_id"], ids[0]) == content
        newer, _ = packages.read_package(db, actor, case["draft_id"], ids[1])
        _, members = packages.inspect_archive(newer.archive_bytes)
        assert json.loads(members[packages.match_member_path(rows[0].id)])["revision"] == 2
        assert json.loads(members[packages.match_member_path(rows[1].id)])["revision"] == 1


def test_legacy_and_empty_collection_keep_identical_selection_and_archive(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        row = create(db, case)
        selected = {"scope_revision": 2, "match_id": row.id, "match_revision": 1}
        absent = packages.preview(db, actor, case["draft_id"], selected)
        empty = packages.preview(db, actor, case["draft_id"], {**selected, "matches": []})
        assert absent == empty
        assert absent["manifest"]["schema_version"] == packages.SCHEMA
        assert "matches" not in absent["manifest"]["selection"]
        saved = save(db, actor, case["draft_id"], selected)
        manifest, members = packages.inspect_archive(saved.archive_bytes)
        assert set(members) == {"artifacts/scope.json", "artifacts/system-match.json"}
        assert packages._archive(manifest, members) == saved.archive_bytes
        assert all(
            item["reference"].startswith("artifacts/system-match.json#")
            for item in manifest["source_manifest"]
        )


@pytest.mark.parametrize("attached", [False, True])
def test_collection_keeps_optional_estimate_and_single_review_reports_exact(
    case, attached, monkeypatch
):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows = _reviews(db, case)
        selected = _selection(rows)
        estimate = estimates.create_estimate(
            db,
            actor,
            case["draft_id"],
            2,
            match_id=rows[1].id if attached else None,
            match_revision=1 if attached else None,
        )
        selected.update(estimate_id=estimate.id, estimate_revision=1)
        saved_reports = [
            reports.create_report(db, actor, case["draft_id"], 2, match_id=row.id, match_revision=1)
            for row in (rows[0], rows[2])
        ]
        selected["scope_reports"] = [report.id for report in saved_reports]

        def forbidden(*args, **kwargs):
            pytest.fail("Packaging existing reports must not render or calculate them again")

        monkeypatch.setattr(reports, "create_report", forbidden)
        before = _counts(db)
        preview = packages.preview(db, actor, case["draft_id"], selected)
        assert _counts(db) == before
        package = packages.create_package(
            db, actor, case["draft_id"], selected, 0, preview["preview_hash"]
        )
        _, members = packages.inspect_archive(package.archive_bytes)
        envelope = json.loads(members["artifacts/estimate.json"])
        assert envelope["system_match"] == (
            matches.read_match_revision(db, actor, case["draft_id"], rows[1].id, 1)
            if attached
            else None
        )
        for report in saved_reports:
            assert members[f"reports/{report.id}.pdf"] == report.pdf_bytes
            assert members[f"reports/{report.id}.xlsx"] == report.xlsx_bytes
        missing_report_dependency = {**selected, "matches": selected["matches"][1:]}
        with pytest.raises(packages.PackageError, match="REPORT_DEPENDENCIES_DIFFER"):
            packages.preview(db, actor, case["draft_id"], missing_report_dependency)
        if attached:
            missing_estimate_dependency = {
                **selected,
                "matches": [selected["matches"][0], selected["matches"][2]],
            }
            with pytest.raises(packages.PackageError, match="PACKAGE_DEPENDENCIES_DIFFER"):
                packages.preview(db, actor, case["draft_id"], missing_estimate_dependency)


@pytest.mark.parametrize(
    "invalid",
    [
        [{"match_id": uid(1)}],
        [{"match_id": uid(1), "match_revision": True}],
        [{"match_id": uid(1), "match_revision": 0}],
        [{"match_id": "not-a-uuid", "match_revision": 1}],
        [{"match_id": uid(1), "match_revision": 1, "approval": "approved"}],
        [{"match_id": uid(1), "match_revision": 1}, {"match_id": uid(1), "match_revision": 2}],
        [{"match_id": uid(index + 1), "match_revision": 1} for index in range(31)],
    ],
)
def test_match_collection_refuses_ambiguous_or_unbounded_selection(invalid):
    with pytest.raises(packages.PackageError, match="PACKAGE_SELECTION_INVALID"):
        packages.selection({"scope_revision": 2, "matches": invalid})


def test_match_collection_refuses_legacy_pair_alongside_new_collection():
    with pytest.raises(packages.PackageError, match="PACKAGE_SELECTION_INVALID"):
        packages.selection(
            {
                "scope_revision": 2,
                "match_id": uid(1),
                "match_revision": 1,
                "matches": [{"match_id": uid(2), "match_revision": 1}],
            }
        )


@pytest.mark.parametrize("invalid", ["same-target", "wrong-scope", "service-only", "opening-only"])
def test_collection_refuses_conflicting_targets_and_scopes_without_writes(case, invalid):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        first = create(db, case)
        if invalid == "same-target":
            second = create(db, case)
        elif invalid == "wrong-scope":
            scope = scopes.read_revision(db, actor, case["draft_id"], 2)
            scopes.save_revision(db, actor, case["draft_id"], 2, scope["content"])
            second = create(db, case, scope_revision=3, opening_id=uid(4), service_id=None)
        else:
            second = create(
                db,
                case,
                opening_id=None if invalid == "service-only" else uid(2),
                service_id=uid(5) if invalid == "service-only" else None,
            )
        before = _counts(db)
        with pytest.raises(packages.PackageError):
            packages.preview(db, actor, case["draft_id"], _selection([first, second]))
        assert _counts(db) == before


def test_collection_rechecks_owner_and_technical_access_for_every_member(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows = _reviews(db, case)
        selected = _selection(rows)
        package = save(db, actor, case["draft_id"], selected)
        other = db.get(User, uid(101))
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError) as caught:
            packages.preview(db, other, case["draft_id"], selected)
        assert caught.value.status_code == 404
        actor.role = "project_manager"
        db.flush()
        with pytest.raises(scopes.DraftScopeError) as caught:
            packages.package_bytes(db, actor, case["draft_id"], package.id)
        assert caught.value.status_code == 403
        assert packages.list_packages(db, actor, case["draft_id"]) == []
        assert _counts(db) == before


def test_collection_still_enforces_aggregate_archive_member_budget(case, monkeypatch):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows = _reviews(db, case)
        monkeypatch.setattr(packages, "MAX_MEMBERS", 4)
        before = _counts(db)
        with pytest.raises(packages.PackageError) as caught:
            packages.preview(db, actor, case["draft_id"], _selection(rows))
        assert caught.value.status_code == 413
        assert _counts(db) == before


def test_collection_changed_preview_and_caller_rollback_leave_no_package(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        rows = _reviews(db, case)
        selected = _selection(rows)
        before = _counts(db)
        with pytest.raises(packages.PackageError, match="PREVIEW_CHANGED"):
            packages.create_package(db, actor, case["draft_id"], selected, 0, "0" * 64)
        assert _counts(db) == before
        row = save(db, actor, case["draft_id"], selected)
        identifier = row.id
        db.rollback()
    with case["factory"]() as db:
        assert db.get(DraftProjectPackage, identifier) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "draft_project_package.create")
            )
            == 0
        )
