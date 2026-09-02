from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from physical_foundation_support import physical_session
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from classifire import technical_admin
from classifire.models import Approval, StoredFile, TechnicalDocument, TechnicalVariant, User


def _user(db: Session, email: str) -> User:
    user = User(email=email, full_name=email, password_hash=email, role="administrator")
    db.add(user)
    db.flush()
    return user


def _document(
    db: Session,
    *,
    storage_root: Path,
    status: str = "draft",
    scan_status: str = "clean",
) -> tuple[TechnicalDocument, bytes]:
    content = b"verified retained technical source for metadata refresh"
    digest = hashlib.sha256(content).hexdigest()
    path = storage_root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored = StoredFile(
        original_filename="technical-source.pdf",
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status=scan_status,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-REFRESH-METADATA-001",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Retained technical source",
        status=status,
        extraction_status="deferred_pending_clean_source",
        metadata_json={"extraction_status": "deferred_pending_clean_source"},
    )
    db.add(document)
    db.flush()
    return document, content


def _refresh(
    db: Session,
    document: TechnicalDocument,
) -> object:
    return technical_admin.technical_document_refresh_draft_metadata(
        document.id,
        object(),  # type: ignore[arg-type]
        db,
        "csrf-token",
    )


def test_refresh_uses_verified_bytes_and_remains_draft_only(
    monkeypatch,
    tmp_path: Path,
) -> None:
    events: list[dict[str, object]] = []
    candidate_metadata = {
        "human_review_required": True,
        "automatic_activation_permitted": False,
        "extraction_status": "draft_candidate_only",
        "page_count": 1,
    }
    monkeypatch.setattr(
        technical_admin,
        "get_settings",
        lambda: SimpleNamespace(storage_root=tmp_path / "storage"),
    )
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(
        technical_admin,
        "record_audit",
        lambda *_args, **kwargs: events.append(kwargs),
    )
    seen: list[tuple[bytes, str]] = []

    def build_metadata(*, content: bytes, filename: str) -> dict[str, object]:
        seen.append((content, filename))
        return candidate_metadata

    monkeypatch.setattr(
        technical_admin,
        "build_technical_document_draft_metadata_from_verified_content",
        build_metadata,
    )
    with physical_session() as db:
        writer = _user(db, "metadata-writer@example.test")
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: writer)
        document, content = _document(db, storage_root=tmp_path / "storage")
        stored = db.get(StoredFile, document.stored_file_id)
        assert stored is not None

        result = _refresh(db, document)

        assert "success=Draft+candidate+metadata+refreshed" in result.headers["location"]
        assert seen == [(content, stored.original_filename)]
        assert document.status == "draft"
        assert document.extraction_status == "draft_candidate_only"
        assert document.metadata_json == candidate_metadata
        assert db.scalar(select(func.count()).select_from(Approval)) == 0
        assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
        assert events == [
            {
                "actor": writer,
                "action": "refresh_draft_metadata",
                "entity_type": "technical_document",
                "entity_id": document.id,
                "previous_value": {"extraction_status": "deferred_pending_clean_source"},
                "new_value": {
                    "extraction_status": "draft_candidate_only",
                    "source_sha256": stored.sha256,
                },
                "reason": "Refresh Draft candidate metadata from clean retained source",
            }
        ]


def test_refresh_rejects_unclean_source_before_extraction_or_mutation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        technical_admin,
        "get_settings",
        lambda: SimpleNamespace(storage_root=tmp_path / "storage"),
    )
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(
        technical_admin,
        "record_audit",
        lambda *_args, **kwargs: events.append(kwargs),
    )

    def should_not_extract(**_kwargs: object) -> None:
        raise AssertionError("unclean retained source must not reach the extractor")

    monkeypatch.setattr(
        technical_admin,
        "build_technical_document_draft_metadata_from_verified_content",
        should_not_extract,
    )
    with physical_session() as db:
        writer = _user(db, "unclean-metadata-writer@example.test")
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: writer)
        document, _content = _document(
            db,
            storage_root=tmp_path / "storage",
            scan_status="pending",
        )

        result = _refresh(db, document)

        assert (
            "error=Technical+source+file+must+be+clean+and+unchanged" in result.headers["location"]
        )
        assert document.status == "draft"
        assert document.extraction_status == "deferred_pending_clean_source"
        assert document.metadata_json == {"extraction_status": "deferred_pending_clean_source"}
        assert events == []


def test_refresh_refuses_non_draft_document_before_extraction(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(technical_admin, "verify_csrf", lambda *_args: None)

    def should_not_extract(**_kwargs: object) -> None:
        raise AssertionError("non-Draft document must not reach the extractor")

    monkeypatch.setattr(
        technical_admin,
        "build_technical_document_draft_metadata_from_verified_content",
        should_not_extract,
    )
    with physical_session() as db:
        writer = _user(db, "in-review-metadata-writer@example.test")
        monkeypatch.setattr(technical_admin, "_require", lambda *_args: writer)
        document, _content = _document(
            db,
            storage_root=tmp_path / "storage",
            status="in_review",
        )

        result = _refresh(db, document)

        assert "error=Only+Draft+technical+documents+can+refresh" in result.headers["location"]
        assert document.status == "in_review"
        assert document.extraction_status == "deferred_pending_clean_source"
