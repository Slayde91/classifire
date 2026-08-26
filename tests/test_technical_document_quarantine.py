from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi import HTTPException
from malware_scan_support import append_clean_attestation
from physical_foundation_support import physical_session
from sqlalchemy import select
from sqlalchemy.orm.attributes import set_committed_value
from starlette.requests import Request

import classifire.services.technical as technical_service
from classifire.config import Settings
from classifire.models import (
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.security import create_human_session
from classifire.services.technical import search_variants
from classifire.technical_admin import (
    technical_document_approve,
    technical_variant_approve,
)

_CSRF_TOKEN = "q" * 43


def _request(session_token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "session": {
                "session_schema": 1,
                "session_token": session_token,
                "csrf_token": _CSRF_TOKEN,
            },
        }
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(env="test", storage_root=tmp_path, _env_file=None)


def _document(
    session,
    tmp_path: Path,
    *,
    scan_status: str,
    suffix: str = "001",
) -> tuple[TechnicalDocument, str]:  # type: ignore[no-untyped-def]
    session.info["retained_storage_root"] = tmp_path
    reviewer = User(
        email=f"technical-reviewer-{suffix.lower()}@example.test",
        full_name="Technical reviewer",
        password_hash="not-used-by-this-test",  # noqa: S106 - authentication is out of scope.
        role="technical_reviewer",
        is_active=True,
    )
    payload = f"controlled technical source {suffix}".encode()
    source_path = tmp_path / f"technical-source-{suffix}.pdf"
    source_path.write_bytes(payload)
    stored = StoredFile(
        original_filename=source_path.name,
        media_type="application/pdf",
        storage_path=str(source_path),
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status=scan_status,
        immutable=True,
    )
    session.add_all([reviewer, stored])
    session.flush()
    if scan_status == "clean":
        append_clean_attestation(session, stored)
    document = TechnicalDocument(
        document_id=f"TECH-DOC-{suffix}",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Technical source",
        status="draft",
    )
    session.add(document)
    session.flush()
    return document, create_human_session(session, reviewer)


def _variant(
    session,
    *,
    suffix: str,
    technical_document_id: str | None,
    status: str = "in_review",
    release_id: str | None = None,
) -> TechnicalVariant:  # type: ignore[no-untyped-def]
    variant = TechnicalVariant(
        variant_id=f"TECH-VARIANT-{suffix}",
        system_id=f"SYSTEM-{suffix}",
        technical_document_id=technical_document_id,
        source_document_reference=f"TECH-DOC-{suffix}",
        source_page="1",
        service_type="pipe",
        source_hash="e" * 64,
        source_json={
            "Variant_ID": f"TECH-VARIANT-{suffix}",
            "System_ID": f"SYSTEM-{suffix}",
        },
        release_id=release_id,
        status=status,
        expert_review_required=True,
    )
    session.add(variant)
    session.flush()
    return variant


@pytest.mark.parametrize("scan_status", ["not_configured", "pending", "infected", "scan_error"])
def test_technical_document_approval_rejects_every_nonclean_scan_status(
    tmp_path: Path,
    scan_status: str,
) -> None:
    with physical_session() as session:
        document, token = _document(session, tmp_path, scan_status=scan_status)

        with pytest.raises(HTTPException) as rejected:
            technical_document_approve(
                document.id,
                _request(token),
                session,
                _settings(tmp_path),
                _CSRF_TOKEN,
                "Reviewed",
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == "TECHNICAL_DOCUMENT_STORED_FILE_NOT_CLEAN"
        assert document.status == "draft"
        assert document.approved_at is None


def test_technical_document_approval_allows_a_clean_stored_file(tmp_path: Path) -> None:
    with physical_session() as session:
        document, token = _document(session, tmp_path, scan_status="clean")

        response = technical_document_approve(
            document.id,
            _request(token),
            session,
            _settings(tmp_path),
            _CSRF_TOKEN,
            "Reviewed",
        )

        assert response.status_code == 303
        assert document.status == "approved"
        assert document.approved_at is not None


def test_technical_document_approval_rejects_a_missing_stored_file(tmp_path: Path) -> None:
    with physical_session() as session:
        document, token = _document(session, tmp_path, scan_status="clean")
        # Simulate a corrupt/historical reference without asking the database
        # to persist an impossible foreign-key value.
        set_committed_value(document, "stored_file_id", "missing-stored-file")

        with pytest.raises(HTTPException) as rejected:
            technical_document_approve(
                document.id,
                _request(token),
                session,
                _settings(tmp_path),
                _CSRF_TOKEN,
                "Reviewed",
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == "TECHNICAL_DOCUMENT_STORED_FILE_NOT_CLEAN"
        assert document.status == "draft"


def test_technical_document_approval_rejects_tampered_retained_bytes(tmp_path: Path) -> None:
    with physical_session() as session:
        document, token = _document(session, tmp_path, scan_status="clean")
        stored = session.get(StoredFile, document.stored_file_id)
        assert stored is not None
        Path(stored.storage_path).write_bytes(b"tampered after clean scan")

        with pytest.raises(HTTPException) as rejected:
            technical_document_approve(
                document.id,
                _request(token),
                session,
                _settings(tmp_path),
                _CSRF_TOKEN,
                "Reviewed",
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == "TECHNICAL_DOCUMENT_STORED_FILE_NOT_CLEAN"
        assert document.status == "draft"


@pytest.mark.parametrize("scan_status", ["pending", "not_configured", "infected"])
def test_variant_activation_rejects_unclean_linked_source(
    tmp_path: Path,
    scan_status: str,
) -> None:
    with physical_session() as session:
        document, token = _document(session, tmp_path, scan_status=scan_status)
        document.status = "approved"
        variant = _variant(
            session,
            suffix="001",
            technical_document_id=document.id,
        )

        with pytest.raises(HTTPException) as rejected:
            technical_variant_approve(
                variant.id,
                _request(token),
                session,
                _settings(tmp_path),
                _CSRF_TOKEN,
                "Reviewed",
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == "TECHNICAL_VARIANT_SOURCE_NOT_APPROVED_OR_CLEAN"
        assert variant.status == "in_review"


def test_variant_activation_rejects_new_unlinked_source(tmp_path: Path) -> None:
    with physical_session() as session:
        _document_row, token = _document(session, tmp_path, scan_status="clean")
        variant = _variant(
            session,
            suffix="UNLINKED",
            technical_document_id=None,
        )

        with pytest.raises(HTTPException) as rejected:
            technical_variant_approve(
                variant.id,
                _request(token),
                session,
                _settings(tmp_path),
                _CSRF_TOKEN,
                "Reviewed",
            )

        assert rejected.value.status_code == 409
        assert rejected.value.detail == "TECHNICAL_VARIANT_SOURCE_NOT_APPROVED_OR_CLEAN"
        assert variant.status == "in_review"


def test_technical_search_excludes_active_variant_after_linked_source_becomes_unclean(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with physical_session() as session:
        clean_document, _token = _document(
            session,
            tmp_path,
            scan_status="clean",
            suffix="CLEAN",
        )
        clean_document.status = "approved"
        clean_variant = _variant(
            session,
            suffix="CLEAN",
            technical_document_id=clean_document.id,
            status="active",
        )
        second_clean_variant = _variant(
            session,
            suffix="CLEAN-SECOND",
            technical_document_id=clean_document.id,
            status="active",
        )
        unclean_document, _ = _document(
            session,
            tmp_path,
            scan_status="pending",
            suffix="UNCLEAN",
        )
        unclean_document.status = "approved"
        _variant(
            session,
            suffix="UNCLEAN",
            technical_document_id=unclean_document.id,
            status="active",
        )
        package_hash = "d" * 64
        package_release = LibraryRelease(
            library_type="technical",
            version="package-15-test",
            status="superseded",
            release_hash=package_hash,
            source_manifest={
                "filename": "package-15-variants.jsonl",
                "sha256": package_hash,
            },
        )
        session.add(package_release)
        session.flush()
        legacy_variant = _variant(
            session,
            suffix="LEGACY",
            technical_document_id=None,
            status="active",
            release_id=package_release.id,
        )
        assert legacy_variant not in {
            item.variant for item in search_variants(session, service_type="pipe")
        }

        approver = session.scalar(select(User).order_by(User.id))
        assert approver is not None
        approved_manifest = {
            "release_type": "technical",
            "version": "approved-technical-test",
            "created_by_id": approver.id,
            "record_count": 1,
            "records": [
                {
                    "id": legacy_variant.id,
                    "variant_id": legacy_variant.variant_id,
                    "system_id": legacy_variant.system_id,
                    "source_hash": legacy_variant.source_hash,
                    "record_version": legacy_variant.record_version,
                }
            ],
        }
        approved_hash = hashlib.sha256(
            json.dumps(
                approved_manifest,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        session.add(
            LibraryRelease(
                library_type="technical",
                version="approved-technical-test",
                status="active",
                release_hash=approved_hash,
                source_manifest=approved_manifest,
                created_by_id=approver.id,
                approved_by_id=approver.id,
                approved_at=datetime.now(UTC),
            )
        )
        session.flush()
        integrity_calls = 0
        real_integrity_check = technical_service.require_clean_stored_file_for_session

        def counted_integrity_check(*args: object, **kwargs: object) -> Path:
            nonlocal integrity_calls
            integrity_calls += 1
            return real_integrity_check(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(
            technical_service,
            "require_clean_stored_file_for_session",
            counted_integrity_check,
        )

        candidates = search_variants(session, service_type="pipe")

        assert {item.variant.id for item in candidates} == {
            clean_variant.id,
            second_clean_variant.id,
        }
        assert legacy_variant not in {item.variant for item in candidates}
        assert integrity_calls == 2


def test_technical_search_rejects_clean_source_outside_governed_root(
    tmp_path: Path,
) -> None:
    with physical_session() as session:
        document, _token = _document(
            session,
            tmp_path,
            scan_status="clean",
            suffix="OUTSIDE-ROOT",
        )
        document.status = "approved"
        _variant(
            session,
            suffix="OUTSIDE-ROOT",
            technical_document_id=document.id,
            status="active",
        )
        governed_root = tmp_path / "different-governed-root"
        governed_root.mkdir()
        session.info["retained_storage_root"] = governed_root

        assert search_variants(session, service_type="pipe") == []
