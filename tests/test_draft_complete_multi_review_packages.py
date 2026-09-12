from __future__ import annotations

import copy
import json

import pytest
from test_draft_complete_multi_review_reports import (
    fast_renderers,
    report_counts,
)
from test_draft_complete_multi_review_reports import (
    prepared as estimate_prepared,
)
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import postgresql_session_factory as _postgres
from test_draft_project_packages import save
from test_draft_system_matches import case as _case

from classifire.models import User
from classifire.services import draft_estimate_reports as reports
from classifire.services import draft_import_reports as imported_reports
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes

case = _case
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def prepared(db, case, *, include_legacy=False):
    actor, estimate, rows, selected = estimate_prepared(db, case, bound=False)
    report = reports.create_report(
        db, actor, case["draft_id"], estimate.id, 4, profile="complete", matches=selected[:2]
    )
    report_ids = [report.id]
    if include_legacy:
        report_ids.append(
            reports.create_report(
                db, actor, case["draft_id"], estimate.id, 4, profile="complete"
            ).id
        )
    choice = {
        "scope_revision": 2,
        "matches": selected,
        "estimate_id": estimate.id,
        "estimate_revision": 4,
        "estimate_reports": report_ids,
    }
    return actor, save(db, actor, case["draft_id"], choice), report, choice


def test_complete_package_requires_every_context_review_and_retains_exact_pair(case, monkeypatch):
    fast_renderers(monkeypatch)
    with case["factory"]() as db:
        actor, package, report, selected = prepared(db, case)
        inspected = inspection.inspect_package(package.archive_bytes)
        assert len(inspected.matches) == 3 and len(inspected.reports[0]["system_matches"]) == 2
        assert inspected.members[f"reports/{report.id}.pdf"] == report.pdf_bytes
        assert inspected.members[f"reports/{report.id}.xlsx"] == report.xlsx_bytes
        assert inspected.members[f"reports/{report.id}.json"].decode() == report.snapshot_json
        assert inspection.requires_report_collection_mapping(inspected)
        before = report_counts(db)
        missing = {**selected, "matches": selected["matches"][1:]}
        with pytest.raises(scopes.DraftScopeError, match="PACKAGE_REPORT_DEPENDENCIES_DIFFER"):
            packages.preview(db, actor, case["draft_id"], missing)
        assert report_counts(db) == before
        # A foreign ZIP cannot keep the report while silently omitting its exact dependency.
        removed_id = selected["matches"][0]["match_id"]
        manifest, members = copy.deepcopy(inspected.manifest), dict(inspected.members)
        manifest["selection"]["matches"] = [
            item for item in manifest["selection"]["matches"] if item["match_id"] != removed_id
        ]
        del members[packages.match_member_path(removed_id)]
        manifest["members"] = [item for item in manifest["members"] if item["path"] in members]
        manifest["source_manifest"] = packages.source_manifest(
            inspected.scope,
            None,
            inspected.estimate,
            match_collection=[
                item for item in inspected.matches if item["artifact_id"] != removed_id
            ],
        )
        with pytest.raises(scopes.DraftScopeError):
            inspection.inspect_package(packages._archive(manifest, members))


def test_complete_collection_import_maps_all_refs_and_keeps_nested_reports_exact(
    case, pdf_setup, monkeypatch
):
    # Use real paired renderers: imported PDF/XLSX must pass existing file inspection.
    with case["factory"]() as db:
        _, package, _, _ = prepared(db, case, include_legacy=True)
        raw = package.archive_bytes
    x = pdf_setup
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        original = inspection.inspect_package(raw)
        imported = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=packages.digest(raw),
            reference="MULTI-COMPLETE-IMPORT",
            name="Synthetic complete collection report and legacy pair",
            settings=x.settings,
        )
        imported_id = imported.draft_scope_id
        mapping = json.loads(imported.mapping_json)
        assert mapping["schema_version"] == "CLASSIFIRE-IMPORT-MAPPING-v4"
        assert len(mapping["matches"]) == 3
        for entry, snapshot in zip(mapping["reports"], original.reports, strict=True):
            assert "match" not in entry
            expected = reports.report_matches(snapshot)
            assert len(entry["matches"]) == len(expected)
            for bound, review in zip(entry["matches"], expected, strict=True):
                assert bound == next(
                    item
                    for item in mapping["matches"]
                    if item["source_id"] == review["artifact_id"]
                )
        assert sorted(len(entry["matches"]) for entry in mapping["reports"]) == [0, 2]
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            imported_reports.original_archive(db, actor, imported_id, settings=x.settings)
        db.rollback()
        for report in mapping["reports"]:
            for entry in report["members"].values():
                assert imported_reports.scan(
                    db, actor, imported_id, entry["source_id"], settings=x.settings
                ) == {"status": "clean", "processing_error": None}
                db.commit()
                assert imported_reports.checked_bytes(
                    db, actor, imported_id, entry["source_id"], settings=x.settings
                ) == original.resolve(entry["path"])
        assert imported_reports.original_archive(db, actor, imported_id, settings=x.settings) == raw
        # Scope-only re-export still retains every report in the original archive.
        exported = save(db, actor, imported_id, {"scope_revision": 2})
        exported_bytes, exported_id = exported.archive_bytes, exported.id
        inspected = inspection.inspect_package(exported_bytes)
        assert inspected.matches == [] and inspection.requires_report_collection_mapping(inspected)
        assert next(iter(inspected.origins.values())).archive_sha256 == packages.digest(raw)
        second = imports.create_import(
            db,
            actor,
            exported_bytes,
            expected_sha256=exported.archive_hash,
            reference="MULTI-COMPLETE-ANCESTOR",
            name="Ancestor-only collection report",
            settings=x.settings,
        )
        nested = json.loads(second.mapping_json)
        assert nested["schema_version"] == "CLASSIFIRE-IMPORT-MAPPING-v4"
        assert "matches" not in nested and nested["match"] is None
        assert sorted(len(entry["matches"]) for entry in nested["reports"]) == [0, 2]
        assert all(
            bound["local_id"] is None
            and bound["local_revision"] is None
            and bound["local_sha256"] is None
            for entry in nested["reports"]
            for bound in entry["matches"]
        )
        assert {
            bound["source_id"] for entry in nested["reports"] for bound in entry["matches"]
        } == {
            item["artifact_id"]
            for snapshot in original.reports
            for item in reports.report_matches(snapshot)
        }
        for _snapshot, paths in inspected.report_members():
            assert all(inspected.resolve(path) for path in paths.values())
        db.commit()
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        imported, _, reopened = imports.read_import(db, actor, imported_id)
        assert reopened == mapping
        # Pending identical imported report copies remain contained until scanned.
        for entry in nested["reports"]:
            for member in entry["members"].values():
                imported_reports.scan(
                    db, actor, second.draft_scope_id, member["source_id"], settings=x.settings
                )
                db.commit()
        assert packages.package_bytes(db, actor, imported_id, exported_id) == exported_bytes
        altered = copy.deepcopy(mapping)
        target = next(entry for entry in altered["reports"] if len(entry["matches"]) == 2)
        target["matches"][1] = target["matches"][0].copy()
        imported.mapping_json = packages.encode(altered).decode()
        imported.mapping_hash = packages.digest(imported.mapping_json.encode())
        db.flush()
        with pytest.raises(scopes.DraftScopeError, match="PACKAGE_IMPORT_INTEGRITY_FAILED"):
            imports.read_import(db, actor, imported_id)
