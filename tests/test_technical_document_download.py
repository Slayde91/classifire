# ruff: noqa: S106
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.requests import Request
from starlette.responses import StreamingResponse

from classifire import models  # noqa: F401
from classifire import technical_admin as technical_admin_module
from classifire.config import Settings
from classifire.db import Base
from classifire.models import AuditEvent, StoredFile, TechnicalDocument, User
from classifire.services import storage as storage_service
from classifire.services.storage import (
    StoredFileBindingError,
    open_verified_stored_file,
)
from classifire.technical_admin import (
    technical_document_detail,
    technical_document_download,
)


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, *, role: str = "read_only") -> User:
    user = User(
        email=f"{role}@example.test",
        full_name=role.replace("_", " ").title(),
        password_hash="not-used",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _request(user: User | None, path: str) -> Request:
    session = {"csrf_token": "csrf-token"}
    if user is not None:
        session["user_id"] = user.id
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 1234),
            "server": ("testserver", 443),
            "session": session,
        }
    )


def _document(
    db: Session,
    settings: Settings,
    *,
    content: bytes = b"%PDF-1.7\nimmutable technical evidence\n%%EOF",
    original_filename: str = "customer-report.pdf",
    standards: list[str] | None = None,
) -> tuple[TechnicalDocument, StoredFile, bytes]:
    digest = hashlib.sha256(content).hexdigest()
    suffix = Path(original_filename).suffix.lower()
    path = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    stored_file = StoredFile(
        original_filename=original_filename,
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(content),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored_file)
    db.flush()
    document = TechnicalDocument(
        document_id="SOURCE-DOWNLOAD-001",
        stored_file_id=stored_file.id,
        document_type="fire_test_report",
        title="Download boundary report",
        standards=standards,
        status="draft",
        extraction_status="awaiting_safe_extraction",
    )
    db.add(document)
    db.commit()
    return document, stored_file, content


async def _response_body(response: StreamingResponse) -> bytes:
    chunks: list[bytes] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
    if response.background is not None:
        await response.background()
    return b"".join(chunks)


def test_download_requires_read_permission_and_returns_exact_attachment(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    reader = _user(db)
    document, _stored_file, content = _document(
        db,
        settings,
        original_filename="../customer\r\n report.PDF",
    )

    response = technical_document_download(
        document.id,
        _request(reader, f"/technical/documents/{document.id}/download"),
        db,
        settings,
    )
    body = asyncio.run(_response_body(response))

    assert body == content
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.headers["content-length"] == str(len(content))
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''" in disposition
    assert "inline" not in disposition.casefold()
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert "/" not in disposition
    assert "\\" not in disposition
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0
    assert db.get(TechnicalDocument, document.id).status == "draft"


def test_download_holds_quarantine_lock_session_until_stream_finishes(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    reader = _user(db)
    document, _stored_file, content = _document(db, settings)

    class _TrackingDeliverySession(Session):
        delivery_closed = False
        rollback_count = 0

        def rollback(self) -> None:
            self.rollback_count += 1
            super().rollback()

        def close(self) -> None:
            self.delivery_closed = True
            super().close()

    delivery_sessions: list[_TrackingDeliverySession] = []

    def tracked_delivery_session(bind: Any) -> Session:
        session = _TrackingDeliverySession(
            bind=bind,
            autoflush=False,
            expire_on_commit=False,
        )
        delivery_sessions.append(session)
        return session

    monkeypatch.setattr(
        technical_admin_module,
        "_technical_source_delivery_session",
        tracked_delivery_session,
    )

    response = technical_document_download(
        document.id,
        _request(reader, f"/technical/documents/{document.id}/download"),
        db,
        settings,
    )

    assert len(delivery_sessions) == 1
    delivery_session = delivery_sessions[0]
    assert delivery_session.in_transaction() is True
    assert delivery_session.delivery_closed is False

    assert asyncio.run(_response_body(response)) == content
    assert delivery_session.delivery_closed is True
    assert delivery_session.rollback_count == 1
    assert delivery_session.in_transaction() is False


@pytest.mark.parametrize(
    ("user_role", "expected_status"),
    [(None, 401), ("pricing_manager", 403)],
)
def test_download_requires_an_active_user_with_technical_read(
    db: Session,
    tmp_path: Path,
    user_role: str | None,
    expected_status: int,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    document, _stored_file, _content = _document(db, settings)
    user = _user(db, role=user_role) if user_role else None

    with pytest.raises(HTTPException) as caught:
        technical_document_download(
            document.id,
            _request(user, f"/technical/documents/{document.id}/download"),
            db,
            settings,
        )

    assert caught.value.status_code == expected_status


@pytest.mark.parametrize("malware_scan_status", ["unknown", "quarantined"])
def test_download_has_stable_missing_and_invalid_source_errors(
    db: Session,
    tmp_path: Path,
    malware_scan_status: str,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    reader = _user(db)

    with pytest.raises(HTTPException) as missing:
        technical_document_download(
            "missing-document",
            _request(reader, "/technical/documents/missing-document/download"),
            db,
            settings,
        )
    assert missing.value.status_code == 404
    assert missing.value.detail == "TECHNICAL_DOCUMENT_NOT_FOUND"

    document, stored_file, _content = _document(db, settings)
    stored_file.malware_scan_status = malware_scan_status
    db.commit()
    with pytest.raises(HTTPException) as invalid:
        technical_document_download(
            document.id,
            _request(reader, f"/technical/documents/{document.id}/download"),
            db,
            settings,
        )
    assert invalid.value.status_code == 409
    assert invalid.value.detail == "SOURCE_FILE_INVALID"
    assert str(settings.storage_root) not in str(invalid.value.detail)


def test_download_reloads_quarantine_state_before_opening(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path / 'storage')
    reader = _user(db)
    document, stored_file, _content = _document(db, settings)
    stale_stored_file = db.get(StoredFile, stored_file.id)
    assert stale_stored_file is not None
    assert stale_stored_file.malware_scan_status == 'clean'
    with Session(db.get_bind()) as containment_session:
        contained = containment_session.get(StoredFile, stored_file.id)
        assert contained is not None
        contained.malware_scan_status = 'quarantined'
        contained.record_version += 1
        containment_session.commit()
    assert stale_stored_file.malware_scan_status == 'clean'

    with pytest.raises(HTTPException) as caught:
        technical_document_download(
            document.id,
            _request(reader, f'/technical/documents/{document.id}/download'),
            db,
            settings,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == 'SOURCE_FILE_INVALID'
    assert stale_stored_file.malware_scan_status == 'quarantined'


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("purpose", "other_evidence"),
        ("immutable", False),
        ("size_bytes", 999),
    ],
)
def test_download_fails_closed_for_invalid_file_binding(
    db: Session,
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    reader = _user(db)
    document, stored_file, _content = _document(db, settings)
    setattr(stored_file, field, value)
    db.commit()

    with pytest.raises(HTTPException) as caught:
        technical_document_download(
            document.id,
            _request(reader, f"/technical/documents/{document.id}/download"),
            db,
            settings,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "SOURCE_FILE_INVALID"


def test_download_fails_closed_when_retained_bytes_change(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    reader = _user(db)
    document, stored_file, content = _document(db, settings)
    Path(stored_file.storage_path).write_bytes(b"x" * len(content))

    with pytest.raises(HTTPException) as caught:
        technical_document_download(
            document.id,
            _request(reader, f"/technical/documents/{document.id}/download"),
            db,
            settings,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "SOURCE_FILE_INVALID"


def test_verified_stream_hashes_once_and_closes_after_consumption(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    _document_row, stored_file, content = _document(db, settings)
    calls = 0
    original_hash = storage_service._sha256_descriptor

    def counted_hash(descriptor: int) -> tuple[str, int]:
        nonlocal calls
        calls += 1
        return original_hash(descriptor)

    monkeypatch.setattr(storage_service, "_sha256_descriptor", counted_hash)

    stream = open_verified_stored_file(
        stored_file,
        storage_root=settings.storage_root,
        required_purpose="technical_evidence",
    )

    assert calls == 1
    assert b"".join(stream) == content
    assert stream.closed is True


def test_verified_stream_closes_on_early_consumer_exit(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    content = b"%PDF-" + b"x" * (1024 * 1024 + 20)
    _document_row, stored_file, _content = _document(db, settings, content=content)
    stream = open_verified_stored_file(
        stored_file,
        storage_root=settings.storage_root,
        required_purpose="technical_evidence",
    )
    iterator = iter(stream)

    assert next(iterator)
    iterator.close()

    assert stream.closed is True


def test_failed_stream_verification_closes_the_descriptor(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(storage_root=tmp_path / "storage")
    _document_row, stored_file, content = _document(db, settings)
    Path(stored_file.storage_path).write_bytes(b"x" * len(content))
    descriptors: list[int] = []
    original_open = storage_service.os.open

    def tracked_open(*args: object, **kwargs: object) -> int:
        descriptor = original_open(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor

    monkeypatch.setattr(storage_service.os, "open", tracked_open)

    with pytest.raises(StoredFileBindingError) as caught:
        open_verified_stored_file(
            stored_file,
            storage_root=settings.storage_root,
            required_purpose="technical_evidence",
        )

    assert caught.value.code == "STORED_FILE_HASH_MISMATCH"
    assert descriptors
    with pytest.raises(OSError):
        os.fstat(descriptors[-1])


def test_detail_page_offers_source_bound_png_without_raw_inline_pdf(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=True,
    )
    reader = _user(db)
    document, _stored_file, _content = _document(db, settings)

    response = technical_document_detail(
        document.id,
        _request(reader, f"/technical/documents/{document.id}"),
        db,
        settings,
    )
    html = response.body.decode("utf-8")

    assert f'href="/technical/documents/{document.id}/download"' in html
    assert "data-technical-pdf-preview" in html
    assert (
        f'data-preview-url-prefix="/technical/documents/{document.id}/preview/'
        f"{_stored_file.sha256}/pages/"
    ) in html
    assert 'src="/static/js/technical-preview.js"' in html
    assert "Viewing aid only." in html
    assert "never grants source approval" in html
    assert "Full Fire Test Report" in html
    assert "Current minimum standards are not demonstrated" in html
    assert "NCC 2022, AS 1530.4:2014, AS 4072.1:2005" in html
    assert 'role="group" aria-label="PDF page navigation and size"' in html
    assert 'role="status" aria-live="polite" aria-atomic="true"' in html
    assert 'role="region" aria-label="Technical report raster page"' in html
    assert 'tabindex="0"' in html
    assert "data-preview-fit" in html
    assert "data-preview-actual" in html
    assert "<noscript>" in html
    lowered = html.casefold()
    assert "<iframe" not in lowered
    assert "<object" not in lowered
    assert "<embed" not in lowered


def test_detail_page_never_treats_declared_current_references_as_compliance(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=False,
    )
    reader = _user(db)
    document, _stored_file, _content = _document(
        db,
        settings,
        standards=["NCC 2022", "AS1530.4:2014", "AS 4072.1:2005"],
    )

    response = technical_document_detail(
        document.id,
        _request(reader, f"/technical/documents/{document.id}"),
        db,
        settings,
    )
    html = response.body.decode("utf-8")

    assert "Current references are declared, but compliance is not established" in html
    assert "competent reviewer must still verify" in html
    assert "Current minimum standards are not demonstrated" not in html


def test_source_approval_does_not_clear_missing_standards_evidence_warning(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=False,
    )
    reader = _user(db)
    document, _stored_file, _content = _document(
        db,
        settings,
        standards=["NCC 2022"],
    )
    document.status = "approved"
    db.commit()

    response = technical_document_detail(
        document.id,
        _request(reader, f"/technical/documents/{document.id}"),
        db,
        settings,
    )
    html = response.body.decode("utf-8")

    assert "Reviewed source." in html
    assert "Current minimum standards are not demonstrated" in html
    assert "AS 1530.4:2014, AS 4072.1:2005" in html


def test_detail_page_does_not_advertise_disabled_preview(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=False,
    )
    reader = _user(db)
    document, _stored_file, _content = _document(db, settings)

    response = technical_document_detail(
        document.id,
        _request(reader, f"/technical/documents/{document.id}"),
        db,
        settings,
    )
    html = response.body.decode("utf-8")

    assert f'href="/technical/documents/{document.id}/download"' in html
    assert "data-technical-pdf-preview" not in html
    assert 'src="/static/js/technical-preview.js"' not in html
    assert "Controlled inline preview is disabled." in html
