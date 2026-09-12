"""An original-bearing Word package retains every explicitly selected row review."""

from __future__ import annotations

import copy
import json

import pytest
from test_draft_pdf_scope_review import _canonical_empty
from test_draft_project_packages import save as save_package
from test_draft_scope_docx_review import _save as save_word_review
from test_draft_scope_docx_review import pdf_app as _pdf_app
from test_draft_scope_docx_review import pdf_setup as _pdf_setup
from test_draft_scope_docx_review import postgresql_session_factory as _postgres
from test_draft_scope_docx_review import scope_password_hash as _password_hash
from test_draft_scope_docx_review import word_app as _word_app
from test_draft_scope_docx_review import word_case as _word_case
from test_technical_release_publication import _actor, _bound_variant

from classifire.models import DraftProjectPackage, User
from classifire.services import draft_estimates as estimates
from classifire.services import draft_import_reports as imported_reports
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as reports
from classifire.services import draft_system_matches as matches
from classifire.services.storage import quarantine_stored_file_bytes_for_update
from classifire.services.technical_release_publication import publish_governed_technical_release

pdf_setup = _pdf_setup
pdf_app = _pdf_app
word_app = _word_app
word_case = _word_case
scope_password_hash = _password_hash
postgresql_session_factory = _postgres


def test_word_original_and_three_reviews_survive_import_reexport_and_scan_gates(
    word_case, monkeypatch, tmp_path
):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        saved_scope = save_word_review(db, x)
        legacy_selection = {"scope_revision": 2, "docx_sources": [x.source_id]}
        assert packages.preview(db, actor, x.ids[2], legacy_selection) == packages.preview(
            db, actor, x.ids[2], {**legacy_selection, "matches": []}
        )
        legacy = save_package(db, actor, x.ids[2], legacy_selection)
        legacy_bytes, legacy_id = legacy.archive_bytes, legacy.id
        legacy_manifest, legacy_members = packages.inspect_archive(legacy_bytes)
        assert legacy_manifest["schema_version"] == packages.SCHEMA_V5
        assert "matches" not in legacy_manifest["selection"]
        assert legacy_members[f"evidence/{x.source_id}.docx"] == x.content

        # This is the established synthetic technical-library fixture, not report inference.
        reviewer = _actor(db)
        _bound_variant(db, x.settings.storage_root, suffix="WORD-MULTI")
        release = publish_governed_technical_release(
            db,
            version="SYNTHETIC-WORD-MULTI",
            notes="Synthetic multi-review Word package regression only",
            actor=reviewer,
            storage_root=x.settings.storage_root,
        )
        content = saved_scope["content"]
        targets = [(service["opening_ids"][0], service["id"]) for service in content["services"]]
        targets.extend((opening["id"], None) for opening in content["openings"] if opening["blank"])
        reviews = [
            matches.create_match(
                db,
                actor,
                x.ids[2],
                2,
                release.id,
                opening_id,
                service_id,
                storage_root=x.settings.storage_root,
            )
            for opening_id, service_id in targets
        ]
        original_reviews = {
            row.id: matches.revision_bytes(db, actor, x.ids[2], row.id, 1) for row in reviews
        }
        assert len(reviews) == 3

        def forbidden(*args, **kwargs):
            pytest.fail("Package operations must not run matching, estimating or reporting")

        monkeypatch.setattr(matches, "create_match", forbidden)
        monkeypatch.setattr(estimates, "create_estimate", forbidden)
        monkeypatch.setattr(reports, "create_report", forbidden)
        selected = {
            **legacy_selection,
            "matches": [{"match_id": row.id, "match_revision": 1} for row in reviews],
        }
        original = save_package(db, actor, x.ids[2], selected, revision=1)
        raw, original_hash = original.archive_bytes, original.archive_hash
        checked = inspection.inspect_package(raw)
        assert checked.manifest["schema_version"] == packages.SCHEMA_V6
        assert checked.scope == saved_scope
        assert checked.scope["evidence_refs"] == saved_scope["evidence_refs"]
        assert len(checked.scope["evidence_refs"]) == 5
        assert sum(len(ref["images"]) for ref in checked.scope["evidence_refs"]) == 1
        assert all(service["quantity"] is None for service in content["services"])
        assert checked.match is None and len(checked.matches) == 3
        evidence_path = f"evidence/{x.source_id}.docx"
        assert checked.members[evidence_path] == x.content
        evidence_entry = next(
            entry for entry in checked.manifest["members"] if entry["path"] == evidence_path
        )
        assert evidence_entry == {
            "path": evidence_path,
            "sha256": packages.digest(x.content),
            "size_bytes": len(x.content),
        }
        for row in reviews:
            assert checked.members[packages.match_member_path(row.id)] == original_reviews[row.id]
        assert packages.package_bytes(db, actor, x.ids[2], legacy_id) == legacy_bytes
        assert packages._archive(legacy_manifest, legacy_members) == legacy_bytes
        downgraded = copy.deepcopy(checked.manifest)
        downgraded["schema_version"] = packages.SCHEMA_V5
        with pytest.raises(scopes.DraftScopeError):
            inspection.inspect_package(packages._archive(downgraded, checked.members))

        imported = imports.create_import(
            db,
            actor,
            raw,
            expected_sha256=original_hash,
            reference="WORD-MULTI-IMPORT",
            name="Synthetic original Word and three independent row reviews",
            settings=x.settings,
        )
        imported_id = imported.draft_scope_id
        mapping = json.loads(imported.mapping_json)
        assert len(mapping["matches"]) == 3 and len(mapping["evidence"]) == 1
        local_scope = scopes.read_revision(db, actor, imported_id)
        assert [dict(ref, origin="local_retained") for ref in local_scope["evidence_refs"]] == (
            saved_scope["evidence_refs"]
        )
        assert all(ref["origin"] == "imported_unverified" for ref in local_scope["evidence_refs"])
        for bound in mapping["matches"]:
            local = matches.read_match_revision(db, actor, imported_id, bound["local_id"], 1)
            source = checked.match_by_id(bound["source_id"])
            assert local["scope"] == local_scope and local["target"] == source["target"]
            assert local["candidates"] == source["candidates"]
            assert local["import_origin"]["authority"] == "foreign_unverified"
        export_selection = {
            "scope_revision": local_scope["revision"],
            "matches": [
                {"match_id": bound["local_id"], "match_revision": 1} for bound in mapping["matches"]
            ],
        }
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            packages.preview(db, actor, imported_id, export_selection)
        db.rollback()
        evidence = mapping["evidence"][0]
        assert imported_reports.scan(
            db, actor, imported_id, evidence["source_id"], settings=x.settings
        ) == {"status": "clean", "processing_error": None}
        db.commit()
        assert (
            imported_reports.checked_bytes(
                db, actor, imported_id, evidence["source_id"], settings=x.settings
            )
            == x.content
        )
        assert imported_reports.original_archive(db, actor, imported_id, settings=x.settings) == raw
        exported = save_package(db, actor, imported_id, export_selection)
        exported_bytes, exported_id = exported.archive_bytes, exported.id
        reopened = inspection.inspect_package(exported_bytes)
        assert reopened.manifest["schema_version"] == packages.SCHEMA_V6
        assert len(reopened.matches) == 3
        assert next(iter(reopened.origins.values())).archive_sha256 == original_hash
        inherited = list(reopened.evidence_members())
        assert len(inherited) == 1 and inherited[0][0] == x.source_id
        assert reopened.resolve(inherited[0][1]) == x.content
        assert reopened.scope["evidence_refs"] == local_scope["evidence_refs"]
        db.commit()

    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert packages.package_bytes(db, actor, x.ids[2], legacy_id) == legacy_bytes
        assert packages.package_bytes(db, actor, imported_id, exported_id) == exported_bytes
        source, _, verified = imported_reports.evidence_intake("docx")._document(
            db, actor, imported_id, evidence["source_id"], x.settings.storage_root
        )
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=source.stored_file_id,
            observed_sha256=verified.sha256,
            observed_size_bytes=verified.size_bytes,
        )
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, imported_id, exported_id)
        # The same original hash is contained everywhere; history stays byte-identical.
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, x.ids[2], legacy_id)
        assert db.get(DraftProjectPackage, legacy_id).archive_bytes == legacy_bytes
        assert db.get(DraftProjectPackage, exported_id).archive_bytes == exported_bytes
        _canonical_empty(db)

    (tmp_path / "word-v5-original-package.zip").write_bytes(legacy_bytes)
    (tmp_path / "word-v6-three-reviews.zip").write_bytes(raw)
    (tmp_path / "word-v6-imported-reexport.zip").write_bytes(exported_bytes)
