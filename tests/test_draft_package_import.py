from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import func, select
from test_draft_estimates import add_payload, prepare
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_project_packages import save
from test_draft_scope import setup as _setup
from test_draft_scope import uid
from test_draft_system_matches import counts, create

from classifire.models import AuditEvent, User
from classifire.services import draft_estimate_reports as estimate_reports
from classifire.services import draft_estimates as estimates
from classifire.services import draft_package_import as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope_reports as scope_reports

setup = _setup
base_case = _base_case
case = _case


def rebuild(manifest, members):
    manifest["members"] = [
        {"path": p, "sha256": packages.digest(v), "size_bytes": len(v)}
        for p, v in sorted(members.items())
    ]
    return packages._archive(manifest, members)


def rehash(value):
    value["sha256"] = packages.digest(
        packages.encode({k: v for k, v in value.items() if k != "sha256"})
    )
    return packages.encode(value)


def test_scope_only_no_write_preview_and_untrusted_lineage(setup):
    with setup() as db:
        actor, draft, _ = prepare(db)
        row = save(db, actor, draft.id, {"scope_revision": 2})
        before = counts(db)
        preview = imports.preview_import(db, actor, row.archive_bytes)
        assert counts(db) == before
        assert preview["manifest"]["capabilities"]["scope"] == "included"
        assert preview["reports"] == []
        assert preview["archive_sha256"] == row.archive_hash
        assert preview["authority"] == "foreign_unverified"
        assert preview["import_available"] is False
        assert preview["binary_status"] == "not_scanned_or_opened"
        assert imports.inspect_package(row.archive_bytes).scope["review_status"] == "unreviewed"
        actor.role = "read_only"
        db.flush()
        with pytest.raises(packages.scopes.DraftScopeError, match="PERMISSION"):
            imports.preview_import(db, actor, row.archive_bytes)


def populated(db, case):
    actor = db.get(User, uid(100))
    match = create(db, case)
    draft_id = case["draft_id"]
    estimate = estimates.create_estimate(
        db, actor, draft_id, 2, match_id=match.id, match_revision=1
    )
    artifact = estimates.add_line(db, actor, draft_id, estimate.id, 1, add_payload())
    estimates.override_line(
        db,
        actor,
        draft_id,
        estimate.id,
        2,
        artifact["lines"][0]["line_id"],
        {"quantity": "3", "unit_sell_rate": "2", "reason": "Synthetic override"},
    )
    scope = scope_reports.create_report(db, actor, draft_id, 2)
    system = scope_reports.create_report(
        db, actor, draft_id, 2, match_id=match.id, match_revision=1
    )
    cost = estimate_reports.create_report(db, actor, draft_id, estimate.id, 3)
    complete = estimate_reports.create_report(
        db, actor, draft_id, estimate.id, 3, profile="complete"
    )
    selected = {
        "scope_revision": 2,
        "match_id": match.id,
        "match_revision": 1,
        "estimate_id": estimate.id,
        "estimate_revision": 3,
        "scope_reports": [scope.id, system.id],
        "estimate_reports": [cost.id, complete.id],
    }
    return actor, save(db, actor, draft_id, selected)


def test_all_profiles_preserve_values_bytes_and_reject_rehashed_dependency_lies(case):
    with case["factory"]() as db:
        actor, row = populated(db, case)
        before = counts(db)
        audited = db.scalar(select(func.count()).select_from(AuditEvent))
        result = imports.preview_import(db, actor, row.archive_bytes)
        assert counts(db) == before
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == audited
        assert {r["profile"] for r in result["reports"]} == {
            "scope-only",
            "scope-and-system",
            "estimate-only",
            "complete",
        }
        inspected = imports.inspect_package(row.archive_bytes)
        assert len(inspected.members) == 15
        assert len(inspected.estimate["lines"][0]["history"]) >= 2
        assert packages.encode(inspected.estimate) == inspected.members["artifacts/estimate.json"]
        assert inspected.match["review_status"] == "unreviewed"
        for mutation in (
            "project",
            "scope_revision",
            "match_revision",
            "estimate_revision",
            "capability",
            "source_inventory",
            "extra_manifest",
            "boolean_revision",
            "parent",
            "unselected_member",
            "missing_report",
            "duplicate_report",
            "scope_hash",
            "match_scope",
            "estimate_total",
            "report_dependency",
            "report_id",
            "report_authority",
            "binary_header",
            "duplicate_json",
        ):
            manifest = copy.deepcopy(inspected.manifest)
            members = dict(inspected.members)
            scope_id = manifest["selection"]["scope_reports"][0]
            report_key = f"reports/{scope_id}.json"
            if mutation == "project":
                manifest["project"]["id"] = uid(987)
            elif mutation.endswith("_revision") and mutation != "boolean_revision":
                manifest["selection"][mutation] += 1
            elif mutation == "capability":
                manifest["capabilities"]["estimate"] = "not_selected"
            elif mutation == "source_inventory":
                manifest["source_manifest"] = []
            elif mutation == "extra_manifest":
                manifest["approval"] = "approved"
            elif mutation == "boolean_revision":
                manifest["revision"] = True
            elif mutation == "parent":
                manifest["parent_hash"] = "0" * 64
            elif mutation == "unselected_member":
                members["artifacts/hidden.json"] = b"{}"
            elif mutation == "missing_report":
                del members[f"reports/{scope_id}.pdf"]
            elif mutation == "duplicate_report":
                manifest["selection"]["estimate_reports"].append(scope_id)
            elif mutation == "scope_hash":
                value = json.loads(members["artifacts/scope.json"])
                value["sha256"] = "0" * 64
                members["artifacts/scope.json"] = packages.encode(value)
            elif mutation == "match_scope":
                value = json.loads(members["artifacts/system-match.json"])
                value["scope"]["created_by"] = uid(987)
                value["scope"] = json.loads(rehash(value["scope"]))
                members["artifacts/system-match.json"] = rehash(value)
            elif mutation == "estimate_total":
                value = json.loads(members["artifacts/estimate.json"])
                value["summary"]["subtotal"] = "999999.00"
                members["artifacts/estimate.json"] = rehash(value)
            elif mutation.startswith("report_"):
                value = json.loads(members[report_key])
                if mutation == "report_id":
                    value["report_id"] = uid(988)
                elif mutation == "report_authority":
                    value["review_status"] = "approved"
                else:
                    value["scope"]["created_by"] = uid(987)
                    value["scope"] = json.loads(rehash(value["scope"]))
                members[report_key] = rehash(value)
            elif mutation == "binary_header":
                members[f"reports/{scope_id}.pdf"] = b"not a PDF"
            elif mutation == "duplicate_json":
                value = members["artifacts/scope.json"]
                members["artifacts/scope.json"] = b'{"state":"Draft",' + value[1:]
            raw = rebuild(manifest, members)
            packages.inspect_archive(raw)  # Each attack passes the old structural-only checker.
            with pytest.raises(packages.PackageError):
                imports.inspect_package(raw)
        assert counts(db) == before
        actor.role = "project_manager"
        db.flush()
        with pytest.raises(packages.scopes.DraftScopeError, match="PERMISSION"):
            imports.preview_import(db, actor, row.archive_bytes)


def test_binary_hash_is_not_treated_as_clean_or_truth(case):
    with case["factory"]() as db:
        actor, row = populated(db, case)
        manifest, members = packages.inspect_archive(row.archive_bytes)
        report_id = manifest["selection"]["scope_reports"][0]
        # No PDF parser or malware scanner should see the untrusted report during preview.
        members[f"reports/{report_id}.pdf"] = b"%PDF-1.4 untrusted synthetic bytes"
        preview = imports.preview_import(db, actor, rebuild(manifest, members))
        assert preview["binary_status"] == "not_scanned_or_opened"
        assert preview["import_available"] is False
