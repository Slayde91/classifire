from __future__ import annotations

import copy
import json

import pytest
from sqlalchemy import func, select
from test_draft_package_import import rebuild, rehash
from test_draft_pdf_intake import pdf_setup as _pdf_setup
from test_draft_pdf_intake import postgresql_session_factory as _postgres
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_project_packages import save
from test_draft_scope import uid
from test_draft_system_matches import create

from classifire.config import Settings
from classifire.models import (
    AuditEvent,
    DraftEstimate,
    DraftEstimateRevision,
    DraftPackageImport,
    DraftScope,
    DraftScopeRevision,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    LibraryRelease,
    Project,
    User,
)
from classifire.services import draft_estimates as estimates
from classifire.services import draft_import_origin as origins
from classifire.services import draft_import_reports as imported_reports
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as materialization
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as scope_reports
from classifire.services import draft_system_matches as matches

base_case = _base_case
case = _case
pdf_setup = _pdf_setup
postgresql_session_factory = _postgres


def _prepared(db, case, *, with_reports=False, with_estimate=True):
    actor = db.get(User, uid(100))
    first = create(db, case)
    second = create(db, case, opening_id=uid(2), service_id=uid(6))
    chosen = sorted([first, second], key=lambda row: row.id)
    selected = {
        "scope_revision": 2,
        "matches": [{"match_id": row.id, "match_revision": 1} for row in chosen],
    }
    # Deliberately choose the later identity, so an arbitrary first-review binding fails.
    if with_estimate:
        estimate = estimates.create_estimate(
            db, actor, case["draft_id"], 2, match_id=chosen[-1].id, match_revision=1
        )
        selected.update(estimate_id=estimate.id, estimate_revision=1)
    if with_reports:
        selected["scope_reports"] = [
            scope_reports.create_report(
                db, actor, case["draft_id"], 2, match_id=row.id, match_revision=1
            ).id
            for row in chosen
        ]
    return actor, save(db, actor, case["draft_id"], selected)


def _import(db, actor, case, package, *, reference="MULTI-IMPORT"):
    return materialization.create_import(
        db,
        actor,
        package.archive_bytes,
        expected_sha256=package.archive_hash,
        reference=reference,
        name="Synthetic multi-review import",
        settings=Settings(storage_root=case["storage_root"]),
    )


def _counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (
            Project,
            DraftScope,
            DraftScopeRevision,
            DraftSystemMatch,
            DraftSystemMatchRevision,
            DraftEstimate,
            DraftEstimateRevision,
            DraftPackageImport,
            AuditEvent,
            LibraryRelease,
        )
    }


def test_multiple_reviews_import_reopen_estimate_exact_binding_and_reexport(case):
    with case["factory"]() as db:
        actor, package = _prepared(db, case)
        original = inspection.inspect_package(package.archive_bytes)
        assert original.match is None and len(original.matches) == 2
        releases = db.scalar(select(func.count()).select_from(LibraryRelease))
        imported = _import(db, actor, case, package)
        mapping = json.loads(imported.mapping_json)
        assert mapping["schema_version"] == "CLASSIFIRE-IMPORT-MAPPING-v3"
        assert mapping["match"] is None
        assert [item["source_id"] for item in mapping["matches"]] == [
            item["artifact_id"] for item in original.matches
        ]
        assert len({item["local_id"] for item in mapping["matches"]}) == 2
        for bound in mapping["matches"]:
            local = matches.read_match_revision(
                db, actor, imported.draft_scope_id, bound["local_id"]
            )
            source = original.match_by_id(bound["source_id"])
            assert local["target"] == source["target"]
            assert local["candidates"] == source["candidates"]
            assert local["import_origin"]["source_artifact_id"] == source["artifact_id"]
            assert local["import_origin"]["source_sha256"] == source["sha256"]
            assert local["import_origin"]["authority"] == "foreign_unverified"
            assert db.get(DraftSystemMatch, bound["local_id"]).release_id is None
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == releases
        local_estimate = estimates.read_estimate_revision(
            db, actor, imported.draft_scope_id, mapping["estimate"]["local_id"]
        )
        bound = next(
            item
            for item in mapping["matches"]
            if item["source_id"] == original.estimate["system_match"]["artifact_id"]
        )
        assert local_estimate["system_match"]["artifact_id"] == bound["local_id"]
        assert local_estimate["system_match"]["sha256"] == bound["local_sha256"]
        assert local_estimate["lines"] == original.estimate["lines"]
        assert local_estimate["summary"] == original.estimate["summary"]
        exported = save(
            db,
            actor,
            imported.draft_scope_id,
            {
                "scope_revision": 2,
                "matches": [
                    {"match_id": item["local_id"], "match_revision": 1}
                    for item in mapping["matches"]
                ],
                "estimate_id": mapping["estimate"]["local_id"],
                "estimate_revision": 1,
            },
        )
        reexported = inspection.inspect_package(exported.archive_bytes)
        assert len(reexported.matches) == 2
        assert next(iter(reexported.origins.values())).archive_sha256 == package.archive_hash
        assert next(iter(reexported.origins)) in reexported.members
        assert reexported.members[next(iter(reexported.origins))] == package.archive_bytes
        second = _import(db, actor, case, exported, reference="SECOND-MULTI-IMPORT")
        second_mapping = json.loads(second.mapping_json)
        assert len(second_mapping["matches"]) == 2
        identities = (
            imported.draft_scope_id,
            mapping["estimate"]["local_id"],
            package.archive_bytes,
        )
        db.commit()
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        retained, original, mapping = materialization.read_import(db, actor, identities[0])
        assert retained.archive_bytes == identities[2]
        assert len(original.matches) == len(mapping["matches"]) == 2
        reopened = estimates.read_estimate_revision(db, actor, identities[0], identities[1])
        assert reopened == local_estimate


def test_review_reports_bind_their_respective_exact_selected_review(case):
    with case["factory"]() as db:
        actor, package = _prepared(db, case, with_reports=True)
        before = _counts(db)
        original = inspection.inspect_package(package.archive_bytes)
        preview = inspection.preview_import(db, actor, package.archive_bytes)
        assert _counts(db) == before
        assert preview["match_count"] == 2
        assert len(original.reports) == 2
        assert {item["system_match"]["artifact_id"] for item in original.reports} == {
            item["artifact_id"] for item in original.matches
        }
        assert preview["binary_status"] == "not_scanned_or_opened"


@pytest.mark.parametrize(
    "mutation",
    ["missing", "reordered", "duplicate-local", "source-hash", "local-hash", "swap-local-bindings"],
)
def test_multi_review_mapping_tampering_is_rejected_even_when_rehashed(case, mutation):
    with case["factory"]() as db:
        actor, package = _prepared(db, case)
        imported = _import(db, actor, case, package)
        mapping = json.loads(imported.mapping_json)
        if mutation == "missing":
            mapping["matches"].pop()
        elif mutation == "reordered":
            mapping["matches"].reverse()
        elif mutation == "duplicate-local":
            mapping["matches"][1]["local_id"] = mapping["matches"][0]["local_id"]
        elif mutation == "source-hash":
            mapping["matches"][1]["source_sha256"] = "0" * 64
        elif mutation == "swap-local-bindings":
            first, second = mapping["matches"]
            for field in ("local_id", "local_revision", "local_sha256"):
                first[field], second[field] = second[field], first[field]
        else:
            mapping["matches"][1]["local_sha256"] = "0" * 64
        imported.mapping_json = packages.encode(mapping).decode()
        imported.mapping_hash = packages.digest(imported.mapping_json.encode())
        db.flush()
        with pytest.raises(scopes.DraftScopeError, match="PACKAGE_IMPORT_INTEGRITY_FAILED"):
            materialization.read_import(db, actor, imported.draft_scope_id)


def test_second_review_import_failure_rolls_back_every_created_record(case, monkeypatch):
    with case["factory"]() as db:
        actor, package = _prepared(db, case)
        db.commit()
        before = _counts(db)
        wrap = origins.wrap
        calls = []

        def fail_second(value, kind, origin, base):
            if kind == "match":
                calls.append(origin["source_artifact_id"])
                if len(calls) == 2:
                    raise ValueError("Synthetic second-review failure")
            return wrap(value, kind, origin, base)

        monkeypatch.setattr(origins, "wrap", fail_second)
        with pytest.raises(ValueError, match="Synthetic second-review failure"):
            _import(db, actor, case, package)
        assert len(calls) == 2
        assert _counts(db) == before


@pytest.mark.parametrize(
    "mutation",
    ["missing-member", "revision", "scope", "duplicate-target", "estimate-review", "report-review"],
)
def test_multi_review_semantic_inspection_rejects_rehashed_dependency_lies(case, mutation):
    with case["factory"]() as db:
        actor, package = _prepared(db, case, with_reports=True)
        original = inspection.inspect_package(package.archive_bytes)
        manifest = copy.deepcopy(original.manifest)
        members = dict(original.members)
        ref = manifest["selection"]["matches"][0]
        path = packages.match_member_path(ref["match_id"])
        if mutation == "missing-member":
            del members[path]
        elif mutation == "revision":
            ref["match_revision"] += 1
        elif mutation == "scope":
            value = json.loads(members[path])
            value["scope"]["created_by"] = uid(987)
            value["scope"] = json.loads(rehash(value["scope"]))
            members[path] = rehash(value)
        elif mutation == "duplicate-target":
            value = copy.deepcopy(original.matches[0])
            other = original.matches[1]
            value["artifact_id"] = other["artifact_id"]
            members[packages.match_member_path(other["artifact_id"])] = rehash(value)
        else:
            extra = create(db, case, opening_id=uid(3), service_id=uid(5))
            unselected = matches.read_match_revision(db, actor, case["draft_id"], extra.id)
            target_path = (
                "artifacts/estimate.json"
                if mutation == "estimate-review"
                else f"reports/{manifest['selection']['scope_reports'][0]}.json"
            )
            value = json.loads(members[target_path])
            value["system_match"] = unselected
            members[target_path] = rehash(value)
        before = _counts(db)
        with pytest.raises(packages.PackageError):
            inspection.preview_import(db, actor, rebuild(manifest, members))
        assert _counts(db) == before


def test_multi_review_import_permissions_apply_to_every_included_review(case):
    with case["factory"]() as db:
        actor, package = _prepared(db, case)
        actor.role = "project_manager"
        db.flush()
        before = _counts(db)
        with pytest.raises(scopes.DraftScopeError, match="PERMISSION"):
            inspection.preview_import(db, actor, package.archive_bytes)
        with pytest.raises(scopes.DraftScopeError, match="PERMISSION"):
            _import(db, actor, case, package)
        assert _counts(db) == before


def test_report_import_keeps_exact_review_mappings_and_clean_byte_download_gates(
    case, pdf_setup, monkeypatch
):
    with case["factory"]() as db:
        _actor, package = _prepared(db, case, with_reports=True)
        raw = package.archive_bytes
    settings = pdf_setup.settings
    monkeypatch.setattr(packages, "get_settings", lambda: settings)
    with pdf_setup.factory() as db:
        actor = db.get(User, pdf_setup.ids[0])
        original = inspection.inspect_package(raw)
        imported = materialization.create_import(
            db,
            actor,
            raw,
            expected_sha256=packages.digest(raw),
            reference="REPORT-MULTI-IMPORT",
            name="Synthetic reports and multiple reviews",
            settings=settings,
        )
        mapping = json.loads(imported.mapping_json)
        for record, report in zip(mapping["reports"], original.reports, strict=True):
            bound = next(
                item
                for item in mapping["matches"]
                if item["source_id"] == report["system_match"]["artifact_id"]
            )
            assert record["match"] == bound
        assert len({row["match"]["local_id"] for row in mapping["reports"]}) == 2
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            imported_reports.original_archive(db, actor, imported.draft_scope_id, settings=settings)
        db.rollback()
        for report in mapping["reports"]:
            for member in report["members"].values():
                assert imported_reports.scan(
                    db, actor, imported.draft_scope_id, member["source_id"], settings=settings
                ) == {"status": "clean", "processing_error": None}
                db.commit()
                assert imported_reports.checked_bytes(
                    db, actor, imported.draft_scope_id, member["source_id"], settings=settings
                ) == original.resolve(member["path"])
        assert (
            imported_reports.original_archive(db, actor, imported.draft_scope_id, settings=settings)
            == raw
        )
        selected = {
            "scope_revision": 2,
            "matches": [
                {"match_id": bound["local_id"], "match_revision": 1} for bound in mapping["matches"]
            ],
            "estimate_id": mapping["estimate"]["local_id"],
            "estimate_revision": 1,
        }
        exported = save(db, actor, imported.draft_scope_id, selected)
        assert next(
            iter(inspection.inspect_package(exported.archive_bytes).origins.values())
        ).archive_sha256 == packages.digest(raw)
        second = materialization.create_import(
            db,
            actor,
            exported.archive_bytes,
            expected_sha256=exported.archive_hash,
            reference="NESTED-REPORT-MULTI-IMPORT",
            name="Nested report history",
            settings=settings,
        )
        nested = json.loads(second.mapping_json)
        assert all(record["match"]["local_id"] is None for record in nested["reports"])
        assert {record["match"]["source_id"] for record in nested["reports"]} == {
            report["system_match"]["artifact_id"] for report in original.reports
        }
        tampered = copy.deepcopy(mapping)
        tampered["reports"][0]["match"] = tampered["reports"][1]["match"]
        imported.mapping_json = packages.encode(tampered).decode()
        imported.mapping_hash = packages.digest(imported.mapping_json.encode())
        db.flush()
        with pytest.raises(scopes.DraftScopeError, match="PACKAGE_IMPORT_INTEGRITY_FAILED"):
            materialization.read_import(db, actor, imported.draft_scope_id)


def test_manual_estimate_without_review_stays_unlinked_when_other_reviews_are_included(case):
    with case["factory"]() as db:
        actor, initial = _prepared(db, case, with_estimate=False)
        selected = json.loads(initial.manifest_json)["selection"]
        estimate = estimates.create_estimate(db, actor, case["draft_id"], 2)
        selected.update(estimate_id=estimate.id, estimate_revision=1)
        package = save(db, actor, case["draft_id"], selected, revision=1)
        imported = _import(db, actor, case, package)
        mapping = json.loads(imported.mapping_json)
        assert len(mapping["matches"]) == 2
        local = estimates.read_estimate_revision(
            db, actor, imported.draft_scope_id, mapping["estimate"]["local_id"]
        )
        row = db.get(DraftEstimate, local["artifact_id"])
        assert local["system_match"] is None
        assert row.match_id is row.match_revision is row.match_hash is None
