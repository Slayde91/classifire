from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import select
from starlette.datastructures import QueryParams

from classifire import technical_admin, ui
from classifire.models import StoredFile, TechnicalDocument
from classifire.services.technical_document_lineage import (
    TechnicalDocumentLineageError,
    prepare_technical_document_supersession,
    technical_document_lineage_state,
)

api_router = import_module("classifire.api.router")
TEST_FORM_VALUE = "test-form-value"


def _stored_file(db, storage_root: Path, *, name: str, content: bytes) -> StoredFile:
    digest = hashlib.sha256(content).hexdigest()
    path = storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=name,
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    return stored


def _document(
    db,
    storage_root: Path,
    *,
    document_id: str,
    status: str = "approved",
    content: bytes = b"retained technical source",
) -> TechnicalDocument:
    stored = _stored_file(db, storage_root, name=f"{document_id}.pdf", content=content)
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="assessment",
        title=document_id,
        manufacturer="Example manufacturer",
        reference=f"REF-{document_id}",
        revision="Rev 1",
        status=status,
    )
    db.add(document)
    db.flush()
    return document


def test_prepared_supersession_snapshots_a_verified_approved_predecessor(tmp_path: Path) -> None:
    with physical_session() as db:
        predecessor = _document(db, tmp_path, document_id="TECH-PREV-001")

        predecessor_id, lineage, lineage_hash = prepare_technical_document_supersession(
            db,
            supersedes_document_id=predecessor.id,
            storage_root=tmp_path,
        )

        assert predecessor_id == predecessor.id
        assert lineage is not None
        assert lineage["predecessor"] == {
            "id": predecessor.id,
            "document_id": "TECH-PREV-001",
            "document_type": "assessment",
            "manufacturer": "Example manufacturer",
            "issuing_organisation": None,
            "reference": "REF-TECH-PREV-001",
            "revision": "Rev 1",
            "stored_file": {
                "id": predecessor.stored_file_id,
                "sha256": hashlib.sha256(b"retained technical source").hexdigest(),
                "size_bytes": len(b"retained technical source"),
            },
        }
        assert lineage_hash and len(lineage_hash) == 64


def test_supersession_refuses_a_nonapproved_or_changed_predecessor(tmp_path: Path) -> None:
    with physical_session() as db:
        draft = _document(db, tmp_path, document_id="TECH-DRAFT-001", status="draft")
        with pytest.raises(
            TechnicalDocumentLineageError,
            match="TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_NOT_APPROVED",
        ):
            prepare_technical_document_supersession(
                db,
                supersedes_document_id=draft.id,
                storage_root=tmp_path,
            )

        approved = _document(
            db,
            tmp_path,
            document_id="TECH-CHANGED-001",
            content=b"different retained technical source",
        )
        stored = db.get(StoredFile, approved.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"changed retained source")
        with pytest.raises(
            TechnicalDocumentLineageError,
            match="TECHNICAL_DOCUMENT_SUPERSESSION_PREDECESSOR_SOURCE_INVALID",
        ):
            prepare_technical_document_supersession(
                db,
                supersedes_document_id=approved.id,
                storage_root=tmp_path,
            )


def test_lineage_state_rejects_a_tampered_snapshot(tmp_path: Path) -> None:
    with physical_session() as db:
        predecessor = _document(db, tmp_path, document_id="TECH-LINEAGE-PREV")
        child = _document(
            db,
            tmp_path,
            document_id="TECH-LINEAGE-CHILD",
            status="draft",
            content=b"replacement technical source",
        )
        predecessor_id, lineage, lineage_hash = prepare_technical_document_supersession(
            db,
            supersedes_document_id=predecessor.id,
            storage_root=tmp_path,
        )
        child.supersedes_document_id = predecessor_id
        child.source_lineage_json = lineage
        child.source_lineage_sha256 = lineage_hash
        assert technical_document_lineage_state(child) == ("verified", lineage)

        child.source_lineage_json = {"schema": "tampered"}
        assert technical_document_lineage_state(child) == ("invalid", None)

def test_api_and_ui_uploads_persist_only_draft_lineage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    with physical_session() as db:
        predecessor = _document(db, tmp_path, document_id="TECH-UPLOAD-PREV")
        api_stored = _stored_file(
            db,
            tmp_path,
            name="api-replacement.pdf",
            content=b"API replacement source",
        )
        ui_stored = _stored_file(
            db,
            tmp_path,
            name="ui-replacement.pdf",
            content=b"UI replacement source",
        )
        user = SimpleNamespace(
            id=None,
            email="writer@example.test",
            full_name="Technical writer",
        )
        settings = SimpleNamespace(storage_root=tmp_path, jurisdiction="AU")
        monkeypatch.setattr(api_router, "save_upload", lambda *_args, **_kwargs: api_stored)
        api_result = api_router.upload_technical_document(
            SimpleNamespace(client=None),
            db,
            settings,
            user,  # type: ignore[arg-type]
            object(),
            "TECH-UPLOAD-API",
            "assessment",
            "API replacement",
            manufacturer=None,
            reference=None,
            revision=None,
            jurisdiction=None,
            supersedes_document_id=predecessor.id,
        )
        api_document = db.get(TechnicalDocument, api_result["id"])
        assert api_document is not None
        assert api_document.status == "draft"
        assert api_document.supersedes_document_id == predecessor.id
        assert technical_document_lineage_state(api_document)[0] == "verified"
        assert predecessor.status == "approved"

        monkeypatch.setattr(ui, "verify_csrf", lambda *_args: None)
        monkeypatch.setattr(ui, "_require", lambda *_args: user)
        monkeypatch.setattr(ui, "save_upload", lambda *_args, **_kwargs: ui_stored)
        ui_result = ui.technical_upload(
            object(),  # type: ignore[arg-type]
            db,
            settings,
            "csrf-token",
            object(),
            "TECH-UPLOAD-UI",
            "assessment",
            "UI replacement",
            manufacturer=None,
            reference=None,
            revision=None,
            supersedes_document_id=predecessor.id,
        )
        ui_document = db.scalar(
            select(TechnicalDocument).where(
                TechnicalDocument.document_id == "TECH-UPLOAD-UI"
            )
        )
        assert ui_result.status_code == 303
        assert ui_document is not None
        assert ui_document.status == "draft"
        assert ui_document.supersedes_document_id == predecessor.id
        assert technical_document_lineage_state(ui_document)[0] == "verified"
        assert predecessor.status == "approved"

def test_document_detail_renders_only_verified_lineage(tmp_path: Path, monkeypatch) -> None:
    with physical_session() as db:
        predecessor = _document(db, tmp_path, document_id="TECH-DETAIL-PREV")
        child = _document(
            db,
            tmp_path,
            document_id="TECH-DETAIL-CHILD",
            status="draft",
            content=b"replacement detail source",
        )
        predecessor_id, lineage, lineage_hash = prepare_technical_document_supersession(
            db,
            supersedes_document_id=predecessor.id,
            storage_root=tmp_path,
        )
        child.supersedes_document_id = predecessor_id
        child.source_lineage_json = lineage
        child.source_lineage_sha256 = lineage_hash
        captured: dict[str, object] = {}
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: object())
        monkeypatch.setattr(technical_admin, "_context", lambda _request, _db, **values: values)
        monkeypatch.setattr(
            technical_admin.templates,
            "TemplateResponse",
            lambda _request, name, context: captured.update(name=name, context=context),
        )

        technical_admin.technical_document_detail(child.id, object(), db)  # type: ignore[arg-type]

        assert captured["name"] == "technical_document_detail.html"
        context = captured["context"]
        assert isinstance(context, dict)
        assert context["source_lineage_state"] == "verified"
        assert context["predecessor"] == predecessor


def test_document_detail_template_states_the_non_authority_boundary() -> None:
    template = technical_admin.templates.get_template("technical_document_detail.html")
    html = template.render(
        request=SimpleNamespace(query_params=QueryParams()),
        user=SimpleNamespace(full_name="Technical reviewer", role="administrator"),
        csrf_token=TEST_FORM_VALUE,
        attribution="CLASSIFIRE",
        has_permission=lambda _permission: False,
        document=SimpleNamespace(
            id="child-id",
            document_id="TECH-CHILD",
            title="Replacement source",
            status="draft",
            document_type="assessment",
            manufacturer=None,
            reference=None,
            revision=None,
            extraction_status="not_started",
        ),
        linked=[],
        approvals=[],
        source_authority_state="blocked",
        source_authority_messages=["The source document is not approved."],
        source_lineage_state="verified",
        source_lineage={
            "predecessor": {
                "document_id": "TECH-PREV",
                "reference": "PREV-REF",
                "revision": "Rev 1",
                "stored_file": {"sha256": "a" * 64},
            }
        },
        predecessor=SimpleNamespace(id="predecessor-id", document_id="TECH-PREV"),
    )

    assert "Verified historical predecessor." in html
    assert (
        "does not retire the earlier source, approve this document, activate a variant, "
        "or create a release"
    ) in html
    assert "/technical/documents/predecessor-id" in html