from __future__ import annotations

import json

import pytest
from sqlalchemy import func, select
from test_draft_estimates import add_payload
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_project_packages import save
from test_draft_scope import uid
from test_draft_system_matches import create

from classifire.config import Settings
from classifire.models import DraftSystemMatch, LibraryRelease, Project, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_system_matches as matches

base_case = _base_case
case = _case


def test_populated_import_creates_editable_local_records_without_library_authority(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        estimate = estimates.create_estimate(
            db, actor, case["draft_id"], 2, match_id=match.id, match_revision=1
        )
        saved = estimates.add_line(db, actor, case["draft_id"], estimate.id, 1, add_payload())
        row = save(
            db,
            actor,
            case["draft_id"],
            {
                "scope_revision": 2,
                "match_id": match.id,
                "match_revision": 1,
                "estimate_id": estimate.id,
                "estimate_revision": 2,
            },
        )
        original_bytes = row.archive_bytes
        releases = db.scalar(select(func.count()).select_from(LibraryRelease))
        imported = imports.create_import(
            db,
            actor,
            row.archive_bytes,
            expected_sha256=row.archive_hash,
            reference="IMPORTED-SYNTHETIC",
            name="Imported synthetic project",
            settings=Settings(storage_root=case["storage_root"]),
        )
        mapping = json.loads(imported.mapping_json)
        draft_id = imported.draft_scope_id
        local = estimates.read_estimate_revision(
            db, actor, draft_id, mapping["estimate"]["local_id"]
        )
        assert local["lines"] == saved["lines"] and local["summary"] == saved["summary"]
        assert local["schema_version"] == "CLASSIFIRE-DRAFT-ESTIMATE-v3"
        assert local["import_origin"]["authority"] == "foreign_unverified"
        local_match = db.get(DraftSystemMatch, mapping["match"]["local_id"])
        assert local_match.release_id is None and local_match.import_id == imported.id
        assert db.scalar(select(func.count()).select_from(LibraryRelease)) == releases
        changed = estimates.override_line(
            db,
            actor,
            draft_id,
            local["artifact_id"],
            1,
            local["lines"][0]["line_id"],
            {"quantity": "3", "unit_sell_rate": "2", "reason": "Local user correction"},
        )
        assert changed["lines"][0]["history"][:-1] == local["lines"][0]["history"]
        current_match = matches.read_match_revision(db, actor, draft_id, local_match.id)
        assert "FOREIGN_TECHNICAL_SOURCES_UNVERIFIED" in matches.match_staleness(
            db, actor, draft_id, local_match.id, storage_root=case["storage_root"]
        )
        decisions = current_match["decisions"]
        decisions[0]["notes"] = "Local review of foreign claims"
        reviewed = matches.save_review(db, actor, draft_id, local_match.id, 1, decisions)
        assert (
            reviewed["revision"] == 2
            and reviewed["import_origin"] == current_match["import_origin"]
        )
        # Re-export preserves the complete original ZIP and locally edited revisions.
        exported = save(
            db,
            actor,
            draft_id,
            {
                "scope_revision": 2,
                "match_id": local_match.id,
                "match_revision": 1,
                "estimate_id": local["artifact_id"],
                "estimate_revision": 2,
            },
        )
        from classifire.services.draft_package_import import inspect_package

        inspected = inspect_package(exported.archive_bytes)
        assert len(list(inspected.walk())) == 2
        assert next(iter(inspected.origins.values())).archive_sha256 == packages.digest(
            original_bytes
        )
        second = imports.create_import(
            db,
            actor,
            exported.archive_bytes,
            expected_sha256=exported.archive_hash,
            reference="SECOND-IMPORT",
            name="Second import",
            settings=Settings(storage_root=case["storage_root"]),
        )
        second_mapping = json.loads(second.mapping_json)
        second_estimate = estimates.read_estimate_revision(
            db, actor, second.draft_scope_id, second_mapping["estimate"]["local_id"]
        )
        assert second_estimate["lines"] == changed["lines"]
        assert second_estimate["summary"] == changed["summary"]
        db.commit()
        identifiers = (draft_id, local["artifact_id"], local_match.id, imported.id)
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert (
            estimates.read_estimate_revision(db, actor, identifiers[0], identifiers[1])["revision"]
            == 2
        )
        assert (
            matches.read_match_revision(db, actor, identifiers[0], identifiers[2])["revision"] == 2
        )
        assert imports.read_import(db, actor, identifiers[0])[0].archive_bytes == original_bytes


def test_import_rollback_and_changed_preview_do_not_create_project(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        package = save(db, actor, case["draft_id"], {"scope_revision": 2})
        db.commit()
        before = db.scalar(select(func.count()).select_from(Project))
        with pytest.raises(scopes.DraftScopeError, match="PREVIEW_CHANGED"):
            imports.create_import(
                db,
                actor,
                package.archive_bytes,
                expected_sha256="0" * 64,
                reference="NO-WRITE",
                name="No write",
                settings=Settings(storage_root=case["storage_root"]),
            )
        imported = imports.create_import(
            db,
            actor,
            package.archive_bytes,
            expected_sha256=package.archive_hash,
            reference="ROLLBACK",
            name="Rollback",
            settings=Settings(storage_root=case["storage_root"]),
        )
        assert scopes.read_revision(db, actor, imported.draft_scope_id)["provenance"] == "imported"
        db.rollback()
        assert db.scalar(select(func.count()).select_from(Project)) == before
