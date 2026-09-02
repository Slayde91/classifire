from __future__ import annotations

import hashlib
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

from physical_foundation_support import physical_session
from sqlalchemy.orm import Session

from classifire import ui
from classifire.models import StoredFile, TechnicalDocument, User
from classifire.services import technical
from classifire.services.storage import StoredFileBindingError

api_router = import_module("classifire.api.router")


def test_pdf_metadata_failure_uses_a_stable_safe_code(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "technical-source.pdf"
    source.write_bytes(b"not a real PDF")
    source_derived_message = "customer-note: do-not-persist-this-parser-message"

    def fail_extraction(_content: bytes) -> dict[str, object]:
        raise ValueError(source_derived_message)

    monkeypatch.setattr(technical, "extract_pdf_candidate_metadata", fail_extraction)

    metadata = technical.build_technical_document_draft_metadata_from_verified_content(
        content=source.read_bytes(),
        filename=source.name,
    )

    assert metadata == {
        "human_review_required": True,
        "automatic_activation_permitted": False,
        "extraction_status": "failed",
        "extraction_failure_code": "TECHNICAL_DOCUMENT_EXTRACTION_FAILED",
    }
    assert source_derived_message not in str(metadata)


def test_non_pdf_metadata_remains_draft_only_without_extraction(tmp_path: Path) -> None:
    source = tmp_path / "technical-source.docx"
    source.write_bytes(b"draft source")

    metadata = technical.build_technical_document_draft_metadata_from_verified_content(
        content=source.read_bytes(),
        filename=source.name,
    )

    assert metadata == {
        "human_review_required": True,
        "automatic_activation_permitted": False,
    }


def _user(db: Session, email: str) -> User:
    user = User(email=email, full_name=email, password_hash=email, role="administrator")
    db.add(user)
    db.flush()
    return user


def _stored_file(db: Session, path: Path) -> StoredFile:
    content = b"technical source evidence"
    stored = StoredFile(
        original_filename=path.name,
        media_type="application/pdf",
        storage_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    return stored


def _failed_metadata() -> dict[str, object]:
    return {
        "human_review_required": True,
        "automatic_activation_permitted": False,
        "extraction_status": "failed",
        "extraction_failure_code": "TECHNICAL_DOCUMENT_EXTRACTION_FAILED",
    }


def test_api_upload_persists_shared_safe_draft_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        user = _user(db, "api-intake@example.test")
        stored = _stored_file(db, tmp_path / "api-source.pdf")
        metadata = _failed_metadata()
        seen: list[tuple[bytes, str]] = []
        verified_content = b"verified API technical source"
        monkeypatch.setattr(api_router, "save_upload", lambda *_args, **_kwargs: stored)
        monkeypatch.setattr(
            api_router,
            "read_verified_stored_file",
            lambda *_args, **_kwargs: SimpleNamespace(content=verified_content),
        )

        def build_metadata(*, content: bytes, filename: str) -> dict[str, object]:
            seen.append((content, filename))
            return metadata

        monkeypatch.setattr(
            api_router,
            "build_technical_document_draft_metadata_from_verified_content",
            build_metadata,
        )
        monkeypatch.setattr(api_router, "record_audit", lambda *_args, **_kwargs: None)

        response = api_router.upload_technical_document(
            SimpleNamespace(client=None),
            db,
            SimpleNamespace(storage_root=tmp_path),
            user,
            object(),
            "TECH-API-SAFE-METADATA",
            "assessment",
            "API source",
            manufacturer=None,
            reference=None,
            revision=None,
            jurisdiction=None,
        )

        document = db.query(TechnicalDocument).filter_by(document_id=response["document_id"]).one()
        assert response["metadata"] == metadata
        assert document.metadata_json == metadata
        assert seen == [(verified_content, stored.original_filename)]


def test_ui_upload_persists_shared_safe_draft_metadata(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        user = _user(db, "ui-intake@example.test")
        stored = _stored_file(db, tmp_path / "ui-source.pdf")
        metadata = _failed_metadata()
        seen: list[tuple[bytes, str]] = []
        verified_content = b"verified UI technical source"
        monkeypatch.setattr(ui, "verify_csrf", lambda *_args: None)
        monkeypatch.setattr(ui, "_require", lambda *_args: user)
        monkeypatch.setattr(ui, "save_upload", lambda *_args, **_kwargs: stored)
        monkeypatch.setattr(
            ui,
            "read_verified_stored_file",
            lambda *_args, **_kwargs: SimpleNamespace(content=verified_content),
        )

        def build_metadata(*, content: bytes, filename: str) -> dict[str, object]:
            seen.append((content, filename))
            return metadata

        monkeypatch.setattr(
            ui,
            "build_technical_document_draft_metadata_from_verified_content",
            build_metadata,
        )
        monkeypatch.setattr(ui, "record_audit", lambda *_args, **_kwargs: None)

        response = ui.technical_upload(
            object(),
            db,
            SimpleNamespace(jurisdiction="AU", storage_root=tmp_path),
            "csrf-token",
            object(),
            "TECH-UI-SAFE-METADATA",
            "assessment",
            "UI source",
            manufacturer=None,
            reference=None,
            revision=None,
        )

        document = db.query(TechnicalDocument).filter_by(document_id="TECH-UI-SAFE-METADATA").one()
        assert response.status_code == 303
        assert document.metadata_json == metadata
        assert seen == [(verified_content, stored.original_filename)]


def test_api_upload_defers_extraction_when_source_is_not_clean(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        user = _user(db, "api-deferred@example.test")
        stored = _stored_file(db, tmp_path / "api-deferred.pdf")
        monkeypatch.setattr(api_router, "save_upload", lambda *_args, **_kwargs: stored)
        monkeypatch.setattr(api_router, "record_audit", lambda *_args, **_kwargs: None)

        def fail_verification(*_args, **_kwargs):
            raise StoredFileBindingError("STORED_FILE_SCAN_STATUS_FORBIDDEN")

        def should_not_extract(**_kwargs):
            raise AssertionError("unverified source must not reach the PDF parser")

        monkeypatch.setattr(api_router, "read_verified_stored_file", fail_verification)
        monkeypatch.setattr(
            api_router,
            "build_technical_document_draft_metadata_from_verified_content",
            should_not_extract,
        )

        response = api_router.upload_technical_document(
            SimpleNamespace(client=None),
            db,
            SimpleNamespace(jurisdiction="AU", storage_root=tmp_path),
            user,
            object(),
            "TECH-API-DEFERRED-METADATA",
            "assessment",
            "API deferred source",
            manufacturer=None,
            reference=None,
            revision=None,
            jurisdiction=None,
        )

        expected = technical.build_technical_document_extraction_deferred_metadata()
        document = db.query(TechnicalDocument).filter_by(document_id=response["document_id"]).one()
        assert response["metadata"] == expected
        assert document.status == "draft"
        assert document.metadata_json == expected


def test_ui_upload_defers_extraction_when_source_is_not_clean(
    monkeypatch,
    tmp_path: Path,
) -> None:
    with physical_session() as db:
        user = _user(db, "ui-deferred@example.test")
        stored = _stored_file(db, tmp_path / "ui-deferred.pdf")
        monkeypatch.setattr(ui, "verify_csrf", lambda *_args: None)
        monkeypatch.setattr(ui, "_require", lambda *_args: user)
        monkeypatch.setattr(ui, "save_upload", lambda *_args, **_kwargs: stored)
        monkeypatch.setattr(ui, "record_audit", lambda *_args, **_kwargs: None)

        def fail_verification(*_args, **_kwargs):
            raise StoredFileBindingError("STORED_FILE_SCAN_STATUS_FORBIDDEN")

        def should_not_extract(**_kwargs):
            raise AssertionError("unverified source must not reach the PDF parser")

        monkeypatch.setattr(ui, "read_verified_stored_file", fail_verification)
        monkeypatch.setattr(
            ui,
            "build_technical_document_draft_metadata_from_verified_content",
            should_not_extract,
        )

        response = ui.technical_upload(
            object(),
            db,
            SimpleNamespace(jurisdiction="AU", storage_root=tmp_path),
            "csrf-token",
            object(),
            "TECH-UI-DEFERRED-METADATA",
            "assessment",
            "UI deferred source",
            manufacturer=None,
            reference=None,
            revision=None,
        )

        expected = technical.build_technical_document_extraction_deferred_metadata()
        document = (
            db.query(TechnicalDocument)
            .filter_by(document_id="TECH-UI-DEFERRED-METADATA")
            .one()
        )
        assert response.status_code == 303
        assert document.status == "draft"
        assert document.metadata_json == expected
