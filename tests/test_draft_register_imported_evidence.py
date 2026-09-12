from __future__ import annotations

import copy
import hashlib
import json

import pytest
from sqlalchemy import update
from test_draft_project_packages import save as save_package
from test_draft_register_evidence import no_writes, save_pdf, save_word, save_xlsx
from test_draft_register_evidence import pdf_app as _pdf_app
from test_draft_register_evidence import pdf_setup as _pdf_setup
from test_draft_register_evidence import postgresql_session_factory as _postgres
from test_draft_register_evidence import review_case as _review_case
from test_draft_register_evidence import scope_password_hash as _password_hash
from test_draft_register_evidence import word_app as _word_app
from test_draft_register_evidence import word_case as _word_case
from test_draft_register_evidence import xlsx_case as _xlsx_case
from test_draft_scope import uid

from classifire.models import DraftImportedReportSource, User
from classifire.services import draft_import_reports as attachments
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_pdf_intake as pdf
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services.draft_register import evidence_context, evidence_image
from classifire.services.draft_source_intake import DraftSourceIntake
from classifire.services.storage import quarantine_stored_file_bytes_for_update

pdf_setup = _pdf_setup
pdf_app = _pdf_app
review_case = _review_case
word_app = _word_app
word_case = _word_case
xlsx_case = _xlsx_case
scope_password_hash = _password_hash
postgresql_session_factory = _postgres


def view(db, x, draft_id, revision=2, *, actor=None, defect=False):
    return evidence_context(
        db,
        actor or db.get(User, x.ids[0]),
        draft_id,
        revision,
        None if defect else x.payload["openings"][0]["id"],
        None if defect else x.payload["services"][0]["id"],
        defect_id=x.payload["defects"][0]["id"] if defect else None,
        settings=x.settings,
    )


def archive_for(db, x, kind, *, include=True):
    actor = db.get(User, x.ids[0])
    selected = {"scope_revision": scopes.read_revision(db, actor, x.ids[2])["revision"]}
    if include:
        selected[kind + "_sources"] = [x.source_id]
    package = save_package(db, actor, x.ids[2], selected)
    return packages.package_bytes(db, actor, x.ids[2], package.id)


def import_archive(db, x, archive, reference):
    return imports.create_import(
        db,
        db.get(User, x.ids[0]),
        archive,
        expected_sha256=packages.digest(archive),
        reference=reference,
        name="Synthetic imported evidence navigation",
        settings=x.settings,
    ).draft_scope_id


def url(draft_id, path):
    return (
        f"/scopes/{draft_id}/imported-package#evidence-" + hashlib.sha256(path.encode()).hexdigest()
    )


def no_body(value, expected_url=None):
    assert value["refs"]
    for ref in value["refs"]:
        assert ref["availability"] == "imported_unverified"
        assert ref["text"] is None and ref["fields"] == [] and ref["images"] == []
        assert ref.get("imported_review_url") == expected_url


def forbid_implicit(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("Imported navigation invoked a source reader, scan, download or writer")

    for name in ("_document", "retain", "scan_source"):
        monkeypatch.setattr(DraftSourceIntake, name, forbidden)
    for name in (
        "scan",
        "checked_bytes",
        "download",
        "original_archive",
        "download_original_archive",
    ):
        monkeypatch.setattr(attachments, name, forbidden)
    monkeypatch.setattr(packages, "preview", forbidden)
    monkeypatch.setattr(packages, "create_package", forbidden)


@pytest.mark.parametrize("kind", ["pdf", "docx", "xlsx"])
def test_exact_native_review_import_links_without_local_authority_or_writes(
    request, monkeypatch, kind
):
    fixture, save = {
        "pdf": ("review_case", save_pdf),
        "docx": ("word_case", save_word),
        "xlsx": ("xlsx_case", save_xlsx),
    }[kind]
    x = request.getfixturevalue(fixture)
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        save(db, x)
        if kind == "pdf":
            x.content = (
                pdf._intake()
                ._document(
                    db, db.get(User, x.ids[0]), x.ids[2], x.source_id, x.settings.storage_root
                )[2]
                .content
            )
        archive = archive_for(db, x, kind)
        draft_id = import_archive(db, x, archive, "NAV-" + kind)
        actor = db.get(User, x.ids[0])
        row, original, mapping = imports.read_import(db, actor, draft_id)
        member = mapping["evidence"][0]
        assert member["source_id"] != x.source_id
        assert original.resolve(member["path"]) == x.content
        source = db.get(DraftImportedReportSource, member["source_id"])
        assert source.document_json is None  # link is available before any local scan
        initial = scopes.revision_bytes(db, actor, draft_id, 2)
        changed = copy.deepcopy(scopes.read_revision(db, actor, draft_id, 2)["content"])
        changed["services"][0]["label"] = "Manual correction; old evidence remains inspectable"
        scopes.save_revision(db, actor, draft_id, 2, changed)
        db.commit()
        original_mapping, original_archive = row.mapping_json, row.archive_bytes
        calls = []
        real_read = imports.read_import

        def counted(*args, **kwargs):
            calls.append(args[2])
            return real_read(*args, **kwargs)

        monkeypatch.setattr(imports, "read_import", counted)
        forbid_implicit(monkeypatch)
        with no_writes(db):
            value = view(db, x, draft_id)
            assert calls == [draft_id]  # all three row/ancestor refs use one inspection
            no_body(value, url(draft_id, member["path"]))
            assert {r["role"] for r in value["refs"]} == {
                "selected_service",
                "opening_context",
                "defect_context",
            }
            stale = view(db, x, draft_id, 3)
            no_body(stale, url(draft_id, member["path"]))
            assert next(r for r in stale["refs"] if r["role"] == "selected_service")[
                "claim_changed"
            ]
            no_body(view(db, x, draft_id, defect=True), url(draft_id, member["path"]))
            with pytest.raises(scopes.DraftScopeError, match="SOURCE_UNAVAILABLE"):
                evidence_image(
                    db,
                    actor,
                    draft_id,
                    2,
                    x.payload["openings"][0]["id"],
                    x.payload["services"][0]["id"],
                    ref_index=value["refs"][0]["index"],
                    image_id="page",
                    settings=x.settings,
                )
            assert scopes._json(scopes.read_revision(db, actor, draft_id, 2)) == initial
            assert row.mapping_json == original_mapping and row.archive_bytes == original_archive
            assert source.document_json is None
            (x.settings.storage_root.parent / f"imported-navigation-{kind}.json").write_text(
                json.dumps(value, indent=2), encoding="utf-8"
            )
    with x.factory() as db, no_writes(db):
        assert view(db, x, draft_id) == value


def test_json_only_omitted_original_and_unrelated_later_import_do_not_gain_links(
    word_case, monkeypatch
):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        saved = save_word(db, x)
        actor = db.get(User, x.ids[0])
        archive = archive_for(db, x, "docx")
        draft_id = import_archive(db, x, archive, "NAV-REPLACED")
        # Same IDs and exact source bytes alone cannot establish review/ancestor membership.
        foreign = copy.deepcopy(saved)
        foreign.update(artifact_id=uid(9900), project_id=uid(9901))
        foreign["sha256"] = packages.digest(
            scopes._json({key: value for key, value in foreign.items() if key != "sha256"})
        )
        raw = scopes._json(foreign)
        scopes.apply_import(db, actor, draft_id, 2, raw, expected_source_hash=packages.digest(raw))
        json_only = scopes.create_draft_project(db, actor, "NAV-JSON", "JSON only")
        scopes.apply_import(
            db,
            actor,
            json_only.id,
            1,
            scopes._json(saved),
            expected_source_hash=packages.digest(scopes._json(saved)),
        )
        omitted = save_package(db, actor, x.ids[2], {"scope_revision": 2}, revision=1)
        omitted_id = import_archive(
            db, x, packages.package_bytes(db, actor, x.ids[2], omitted.id), "NAV-OMITTED"
        )
        db.commit()
        forbid_implicit(monkeypatch)
        with no_writes(db):
            no_body(view(db, x, draft_id), url(draft_id, f"evidence/{x.source_id}.docx"))
            no_body(view(db, x, draft_id, 3))
            no_body(view(db, x, json_only.id))
            no_body(view(db, x, omitted_id))


def test_changed_full_claim_cannot_link_even_with_exact_ancestor_and_bytes(word_case, monkeypatch):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        save_word(db, x)
        draft_id = import_archive(db, x, archive_for(db, x, "docx"), "NAV-CLAIM")
        actor = db.get(User, x.ids[0])
        foreign = copy.deepcopy(scopes.read_revision(db, actor, draft_id, 2))
        foreign["evidence_refs"][0]["original_filename"] = "different-review-claim.docx"
        foreign["sha256"] = packages.digest(
            scopes._json({key: value for key, value in foreign.items() if key != "sha256"})
        )
        raw = scopes._json(foreign)
        scopes.apply_import(db, actor, draft_id, 2, raw, expected_source_hash=packages.digest(raw))
        db.commit()
        forbid_implicit(monkeypatch)
        with no_writes(db):
            current = view(db, x, draft_id, 3)
            changed_index = 0
            changed = next(r for r in current["refs"] if r["index"] == changed_index)
            assert "imported_review_url" not in changed
            assert any("imported_review_url" in ref for ref in current["refs"] if ref["index"] != 0)


def test_nested_path_is_exact_and_duplicate_retention_is_ambiguous(word_case, monkeypatch):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        save_word(db, x)
        first_archive = archive_for(db, x, "docx")
        first_id = import_archive(db, x, first_archive, "NAV-NESTED-FIRST")
        actor = db.get(User, x.ids[0])
        _, _, mapping = imports.read_import(db, actor, first_id)
        attachments.scan(
            db, actor, first_id, mapping["evidence"][0]["source_id"], settings=x.settings
        )
        package = save_package(db, actor, first_id, {"scope_revision": 2})
        nested_archive = packages.package_bytes(db, actor, first_id, package.id)
        nested_id = import_archive(db, x, nested_archive, "NAV-NESTED-SECOND")
        _, _, nested_mapping = imports.read_import(db, actor, nested_id)
        nested_path = nested_mapping["evidence"][0]["path"]
        assert "!" in nested_path
        # Valid portable input may include the same binary directly and through an
        # origin. Retention deliberately reuses its one owned source row.
        inspected = inspection.inspect_package(nested_archive)
        manifest, members = copy.deepcopy(inspected.manifest), dict(inspected.members)
        direct_path = f"evidence/{x.source_id}.docx"
        members[direct_path] = x.content
        manifest["schema_version"] = packages.SCHEMA_V5
        manifest["selection"]["docx_sources"] = [x.source_id]
        manifest["source_manifest"] = packages.source_manifest(
            inspected.scope, None, None, [], [], [x.source_id]
        )
        manifest["members"].append(
            {
                "path": direct_path,
                "sha256": packages.digest(x.content),
                "size_bytes": len(x.content),
            }
        )
        manifest["members"].sort(key=lambda member: member["path"])
        duplicate_archive = packages._archive(manifest, members)
        inspection.inspect_package(duplicate_archive)
        duplicate_id = import_archive(db, x, duplicate_archive, "NAV-NESTED-DUPLICATE")
        _, _, duplicate_mapping = imports.read_import(db, actor, duplicate_id)
        evidence = duplicate_mapping["evidence"]
        assert len(evidence) == 2 and len({m["source_id"] for m in evidence}) == 1
        assert len({m["path"] for m in evidence}) == 2
        db.commit()
        forbid_implicit(monkeypatch)
        with no_writes(db):
            no_body(view(db, x, nested_id), url(nested_id, nested_path))
            no_body(view(db, x, duplicate_id))


def test_package_integrity_access_and_quarantine_preserve_navigation_boundaries(
    word_case, monkeypatch
):
    x = word_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        save_word(db, x)
        draft_id = import_archive(db, x, archive_for(db, x, "docx"), "NAV-GUARDS")
        actor = db.get(User, x.ids[0])
        row, _, mapping = imports.read_import(db, actor, draft_id)
        source = db.get(DraftImportedReportSource, mapping["evidence"][0]["source_id"])
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=source.stored_file_id,
            observed_sha256=source.source_sha256,
            observed_size_bytes=source.source_size_bytes,
        )
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            attachments.checked_bytes(db, actor, draft_id, source.id, settings=x.settings)
        forbid_implicit(monkeypatch)
        with no_writes(db):
            # Navigation is not a clean-source claim; explicit download still fails above.
            no_body(view(db, x, draft_id), url(draft_id, mapping["evidence"][0]["path"]))
            with pytest.raises(scopes.DraftScopeError) as denied:
                view(db, x, draft_id, actor=db.get(User, x.ids[1]))
            assert denied.value.status_code in (403, 404)
        raw_mapping = row.mapping_json
        row.mapping_json = "{}"
        db.commit()
        with no_writes(db):
            no_body(view(db, x, draft_id))
        row.mapping_json = raw_mapping
        db.commit()

        def no_package_rights(*_args, **_kwargs):
            raise scopes.DraftScopeError("FORBIDDEN", 403)

        monkeypatch.setattr(imports, "_access", no_package_rights)
        with no_writes(db):
            no_body(view(db, x, draft_id))
        db.execute(update(User).where(User.id == actor.id).values(is_active=False))
        db.commit()
        with no_writes(db), pytest.raises(scopes.DraftScopeError) as denied:
            view(db, x, draft_id)
        assert denied.value.status_code == 403
