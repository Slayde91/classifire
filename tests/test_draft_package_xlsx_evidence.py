from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_project_package_ui import fields
from test_draft_scope_ui import _assert_no_canonical_scope, _login
from test_draft_scope_xlsx import _save
from test_draft_scope_xlsx import pdf_app as _pdf_app
from test_draft_scope_xlsx import pdf_setup as _pdf_setup
from test_draft_scope_xlsx import postgresql_session_factory as _postgres
from test_draft_scope_xlsx import scope_password_hash as _password
from test_draft_scope_xlsx import xlsx_app as _xlsx_app
from test_draft_scope_xlsx import xlsx_case as _xlsx_case

from classifire.draft_project_package_ui import router
from classifire.models import DraftProjectPackage, DraftScopeXlsxSource, User
from classifire.services import draft_import_reports as attachments
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import malware_scan

pdf_setup = _pdf_setup
pdf_app = _pdf_app
postgresql_session_factory = _postgres
scope_password_hash = _password
xlsx_case = _xlsx_case
xlsx_app = _xlsx_app


def test_workbook_package_ui_import_scan_reexport_and_quarantine(xlsx_app, monkeypatch):
    x = xlsx_app
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    monkeypatch.setattr("classifire.draft_project_package_ui.get_settings", lambda: x.settings)
    x.app.include_router(router)
    with x.factory() as db:
        _save(db, x)
        db.commit()
    chosen = {"scope_revision": 2, "xlsx_sources": [x.source_id]}
    with TestClient(x.app) as client:
        _login(client)
        path = f"/scopes/{x.ids[2]}/packages"
        page = client.get(path, params=chosen)
        assert page.status_code == 200, page.text
        assert "Include reviewed Scope workbooks" in page.text
        assert "synthetic-defects.xlsx" in page.text
        response = client.post(path, data=fields(page), follow_redirects=False)
        assert response.status_code == 303, response.text
        saved_id = response.headers["location"].rsplit("/", 1)[-1]
        download = client.get(response.headers["location"] + "/download")
        assert download.status_code == 200
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        archive = packages.package_bytes(db, actor, x.ids[2], saved_id)
        assert archive == download.content
        inspected = inspection.inspect_package(archive)
        assert inspected.manifest["schema_version"] == packages.SCHEMA_V4
        evidence_path = f"evidence/{x.source_id}.xlsx"
        assert inspected.members[evidence_path] == x.content
        assert len(inspected.scope["evidence_refs"]) == 4
        assert all(ref["membership"] == "included" for ref in inspected.manifest["source_manifest"])
        assert all(s["quantity"] is None for s in inspected.scope["content"]["services"][:1])
        legacy = packages.preview(db, actor, x.ids[2], {"scope_revision": 2})
        for old_version in (packages.SCHEMA, packages.SCHEMA_V2, packages.SCHEMA_V3):
            downgraded = copy.deepcopy(inspected.manifest)
            downgraded["schema_version"] = old_version
            with pytest.raises(scopes.DraftScopeError):
                inspection.inspect_package(packages._archive(downgraded, inspected.members))
        assert legacy["manifest"]["schema_version"] == packages.SCHEMA
        assert "xlsx_sources" not in legacy["manifest"]["selection"]
        assert all(ref["membership"] == "external" for ref in legacy["manifest"]["source_manifest"])
        changed = dict(inspected.members)
        changed[evidence_path] += b"changed"
        manifest = copy.deepcopy(inspected.manifest)
        for item in manifest["members"]:
            if item["path"] == evidence_path:
                item.update(
                    sha256=packages.digest(changed[evidence_path]),
                    size_bytes=len(changed[evidence_path]),
                )
        with pytest.raises(scopes.DraftScopeError, match="CONTENT_INVALID"):
            inspection.inspect_package(packages._archive(manifest, changed))
        imported = imports.create_import(
            db,
            actor,
            archive,
            expected_sha256=packages.digest(archive),
            reference="XLSX-IMPORT",
            name="Synthetic workbook import",
            settings=x.settings,
        )
        imported_id = imported.draft_scope_id
        _, _, mapping = imports.read_import(db, actor, imported_id)
        assert mapping["schema_version"] == "CLASSIFIRE-IMPORT-MAPPING-v2"
        local_source = mapping["evidence"][0]["source_id"]
        assert local_source != x.source_id
        scope = scopes.read_revision(db, actor, imported_id)
        assert all(ref["origin"] != "local_retained" for ref in scope["evidence_refs"])
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, imported_id, settings=x.settings)
        result = attachments.scan(db, actor, imported_id, local_source, settings=x.settings)
        assert result["status"] == "clean" and result["processing_error"] is None
        assert (
            attachments.checked_bytes(db, actor, imported_id, local_source, settings=x.settings)
            == x.content
        )
        assert attachments.original_archive(db, actor, imported_id, settings=x.settings) == archive
        selected = {"scope_revision": scope["revision"]}
        preview = packages.preview(db, actor, imported_id, selected)
        saved = packages.create_package(
            db, actor, imported_id, selected, 0, preview["preview_hash"]
        )
        again = packages.package_bytes(db, actor, imported_id, saved.id)
        second = imports.create_import(
            db,
            actor,
            again,
            expected_sha256=packages.digest(again),
            reference="XLSX-SECOND",
            name="Second synthetic workbook import",
            settings=x.settings,
        )
        second_id = second.draft_scope_id
        _, _, mapping2 = imports.read_import(db, actor, second_id)
        second_source = mapping2["evidence"][0]["source_id"]
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, second_id, settings=x.settings)
        attachments.scan(db, actor, second_id, second_source, settings=x.settings)
        assert attachments.original_archive(db, actor, second_id, settings=x.settings) == again
        db.commit()
    with TestClient(x.app) as client:
        _login(client)
        page = client.get(f"/scopes/{imported_id}/imported-package")
        assert page.status_code == 200 and "XLSX" in page.text
        assert "Retained original reports and evidence" in page.text
        download = client.get(
            f"/scopes/{imported_id}/imported-package/reports/{local_source}/download"
        )
        assert download.status_code == 200 and download.content == x.content
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        assert packages.package_bytes(db, actor, imported_id, saved.id) == again
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(
                db, db.get(User, x.ids[1]), imported_id, settings=x.settings
            )
        clean = malware_scan.scan_bytes
        monkeypatch.setattr(
            malware_scan,
            "scan_bytes",
            lambda data, **kw: replace(clean(data, **kw), status="malware_detected"),
        )
        attachments.scan(db, actor, imported_id, local_source, settings=x.settings)
        db.commit()
        for target in (imported_id, second_id):
            with pytest.raises(scopes.DraftScopeError):
                attachments.original_archive(db, actor, target, settings=x.settings)
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, x.ids[2], saved_id)
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, imported_id, saved.id)
    _assert_no_canonical_scope(x.factory)


def test_workbook_membership_requires_review_and_unchanged_source(xlsx_case, monkeypatch):
    x = xlsx_case
    monkeypatch.setattr(packages, "get_settings", lambda: x.settings)
    with x.factory() as db:
        actor = db.get(User, x.ids[0])
        with pytest.raises(scopes.DraftScopeError, match="XLSX_SELECTION_INVALID"):
            packages.preview(
                db, actor, x.ids[2], {"scope_revision": 1, "xlsx_sources": [x.source_id]}
            )
        _save(db, x)
        chosen = {"scope_revision": 2, "xlsx_sources": [x.source_id]}
        preview = packages.preview(db, actor, x.ids[2], chosen)
        with pytest.raises(scopes.DraftScopeError, match="PDF_SELECTION_INVALID"):
            packages.preview(
                db, actor, x.ids[2], {"scope_revision": 2, "pdf_sources": [x.source_id]}
            )
        db.get(DraftScopeXlsxSource, x.source_id).document_sha256 = "a" * 64
        db.flush()
        with pytest.raises(scopes.DraftScopeError):
            packages.create_package(db, actor, x.ids[2], chosen, 0, preview["preview_hash"])
        assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 0


def test_workbook_selection_is_bounded_and_disjoint():
    source = "00000000-0000-0000-0000-000000000001"
    for chosen in (
        {"xlsx_sources": [source, source]},
        {"xlsx_sources": [source], "pdf_sources": [source]},
        {"xlsx_sources": [str(i) for i in range(5)]},
    ):
        with pytest.raises(packages.PackageError, match="PACKAGE_SELECTION_INVALID"):
            packages.selection({"scope_revision": 1, **chosen})
