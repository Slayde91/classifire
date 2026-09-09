from __future__ import annotations

import copy
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_draft_client_pdf_scope import (  # noqa: F401
    decision_form,
    login,
    pdf_client_case,
    postgresql_session_factory,
    prepare,
    proposal,
    scope_password_hash,
)
from test_draft_client_pdf_scope import (
    review_case as _review_case,
)
from test_draft_project_package_ui import fields
from test_draft_scope_ui import _assert_no_canonical_scope

from classifire.draft_project_package_ui import router
from classifire.models import DraftPdfSource, DraftProjectPackage, User
from classifire.services import draft_import_reports as attachments
from classifire.services import draft_package_import as inspection
from classifire.services import draft_package_materialization as materialization
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import malware_scan

review_case = _review_case


def test_reviewed_pdf_package_import_scan_and_reexport(review_case, monkeypatch):
    c = review_case
    monkeypatch.setattr(packages, "get_settings", lambda: c.settings)
    monkeypatch.setattr("classifire.draft_project_package_ui.get_settings", lambda: c.settings)
    existing = len(c.app.router.routes)
    c.app.include_router(router)
    c.app.router.routes[:] = c.app.router.routes[existing:] + c.app.router.routes[:existing]
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        pending = proposal(client, c, operation)
        page = client.get(pending["review_url"])
        assert client.post(pending["review_url"], data=decision_form(page)).status_code == 200
        selection = {"scope_revision": 2, "pdf_sources": [operation["source_id"]]}
        page = client.get(f"/scopes/{c.draft_id}/packages", params=selection)
        assert page.status_code == 200, page.text
        assert "Include reviewed project PDFs" in page.text and "inspection.pdf" in page.text
        response = client.post(f"/scopes/{c.draft_id}/packages", data=fields(page),
                               follow_redirects=False)
        assert response.status_code == 303, response.text
        location = response.headers["location"]
        download = client.get(location + "/download")
        assert download.status_code == 200
        saved_id = location.rsplit("/", 1)[-1]
    with c.factory() as db:
        actor = db.get(User, c.owner_id)
        legacy = packages.preview(db, actor, c.draft_id, {"scope_revision": 2})
        assert legacy["manifest"]["schema_version"] == packages.SCHEMA
        assert "pdf_sources" not in legacy["manifest"]["selection"]
        preview = packages.preview(db, actor, c.draft_id, selection)
        assert preview["manifest"]["schema_version"] == packages.SCHEMA_V3
        row = db.get(DraftProjectPackage, saved_id)
        archive = packages.package_bytes(db, actor, c.draft_id, row.id)
        assert archive == download.content
        inspected = inspection.inspect_package(archive)
        evidence_path = f"evidence/{operation['source_id']}.pdf"
        assert inspected.members[evidence_path] == c.content
        altered_manifest = copy.deepcopy(inspected.manifest)
        altered_members = dict(inspected.members)
        altered_members[evidence_path] += b"\n% altered bytes"
        for member in altered_manifest["members"]:
            if member["path"] == evidence_path:
                member.update(sha256=packages.digest(altered_members[evidence_path]),
                              size_bytes=len(altered_members[evidence_path]))
        with pytest.raises(scopes.DraftScopeError, match="CONTENT_INVALID"):
            inspection.inspect_package(packages._archive(altered_manifest, altered_members))
        assert all(ref["membership"] == "included" for ref in inspected.manifest["source_manifest"])
        imported = materialization.create_import(
            db, actor, archive, expected_sha256=packages.digest(archive),
            reference="SYNTHETIC-PDF-IMPORT", name="Synthetic PDF evidence import",
            settings=c.settings,
        )
        imported_id = imported.draft_scope_id
        _row, _original, mapping = materialization.read_import(db, actor, imported_id)
        assert mapping["schema_version"] == "CLASSIFIRE-IMPORT-MAPPING-v2"
        local_source = mapping["evidence"][0]["source_id"]
        imported_scope = scopes.read_revision(db, actor, imported_id)
        assert all(ref["origin"] != "local_retained" for ref in imported_scope["evidence_refs"])
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, imported_id, settings=c.settings)
        attachments.scan(db, actor, imported_id, local_source, settings=c.settings)
        assert attachments.checked_bytes(db, actor, imported_id, local_source,
                                         settings=c.settings) == c.content
        assert attachments.original_archive(db, actor, imported_id, settings=c.settings) == archive
        reselected = {"scope_revision": imported_scope["revision"]}
        again = packages.preview(db, actor, imported_id, reselected)
        saved = packages.create_package(
            db, actor, imported_id, reselected, 0, again["preview_hash"],
        )
        reexport = packages.package_bytes(db, actor, imported_id, saved.id)
        assert list(inspection.inspect_package(reexport).evidence_members())
        second = materialization.create_import(
            db, actor, reexport, expected_sha256=packages.digest(reexport),
            reference="SYNTHETIC-PDF-SECOND", name="Second synthetic PDF import",
            settings=c.settings,
        )
        second_id = second.draft_scope_id
        _row, _original, second_mapping = materialization.read_import(db, actor, second_id)
        second_source = second_mapping["evidence"][0]["source_id"]
        assert second_source != local_source
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, second_id, settings=c.settings)
        attachments.scan(db, actor, second_id, second_source, settings=c.settings)
        assert attachments.original_archive(db, actor, second_id, settings=c.settings) == reexport
        db.commit()
    with c.factory() as db:
        actor = db.get(User, c.owner_id)
        assert packages.package_bytes(db, actor, imported_id, saved.id) == reexport
        foreign = db.scalar(select(User).where(User.email == "other@pdf-client.example.test"))
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, foreign, imported_id, settings=c.settings)
        clean_scan = malware_scan.scan_bytes
        monkeypatch.setattr(malware_scan, "scan_bytes",
                            lambda data, **kw: replace(clean_scan(data, **kw),
                                                      status="malware_detected"))
        attachments.scan(db, actor, imported_id, local_source, settings=c.settings)
        db.commit()
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, imported_id, settings=c.settings)
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, imported_id, saved.id)
        with pytest.raises(scopes.DraftScopeError):
            packages.package_bytes(db, actor, c.draft_id, saved_id)
        with pytest.raises(scopes.DraftScopeError):
            attachments.original_archive(db, actor, second_id, settings=c.settings)
    _assert_no_canonical_scope(c.factory)


def test_pdf_membership_refuses_unreviewed_or_changed_source(review_case, monkeypatch):
    c = review_case
    monkeypatch.setattr(packages, "get_settings", lambda: c.settings)
    with TestClient(c.app, base_url="https://testserver") as client:
        login(client)
        operation = prepare(client, c)
        with c.factory() as db:
            actor = db.get(User, c.owner_id)
            with pytest.raises(scopes.DraftScopeError, match="PDF_SELECTION_INVALID"):
                packages.preview(db, actor, c.draft_id,
                                 {"scope_revision": 1, "pdf_sources": [operation["source_id"]]})
        pending = proposal(client, c, operation)
        page = client.get(pending["review_url"])
        assert client.post(pending["review_url"], data=decision_form(page)).status_code == 200
    with c.factory() as db:
        actor = db.get(User, c.owner_id)
        chosen = {"scope_revision": 2, "pdf_sources": [operation["source_id"]]}
        preview = packages.preview(db, actor, c.draft_id, chosen)
        db.get(DraftPdfSource, operation["source_id"]).document_sha256 = "a" * 64
        db.flush()
        with pytest.raises(scopes.DraftScopeError):
            packages.create_package(db, actor, c.draft_id, chosen, 0, preview["preview_hash"])
        assert db.scalar(select(func.count()).select_from(DraftProjectPackage)) == 0


def test_imported_evidence_pdf_rejects_active_actions():
    import io

    from reportlab.pdfgen.canvas import Canvas

    content = io.BytesIO()
    canvas = Canvas(content)
    canvas.drawString(30, 700, "Synthetic project evidence")
    canvas.linkURL("https://example.test", (20, 20, 40, 40))
    canvas.save()
    with pytest.raises(scopes.DraftScopeError, match="PROCESSING_FAILED"):
        attachments.evidence_intake().policy.process(content.getvalue())
