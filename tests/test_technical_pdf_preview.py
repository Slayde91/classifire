# ruff: noqa: S106
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping
from io import BytesIO
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import Response

from classifire import models  # noqa: F401
from classifire import technical_admin as technical_admin_module
from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.main import http_exception_handler, security_headers
from classifire.models import Approval, AuditEvent, StoredFile, TechnicalDocument, User
from classifire.services import technical_pdf_preview as preview_service
from classifire.services.storage import StoredFileBinding, VerifiedStoredFileStream
from classifire.services.technical_pdf_preview import (
    TECHNICAL_PDF_PREVIEW_POLICY,
    TechnicalPdfPreviewError,
    render_technical_pdf_preview,
)
from classifire.technical_admin import (
    router as technical_admin_router,
)
from classifire.technical_admin import (
    technical_document_preview,
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


def _pdf(*, pages: int = 2, uri_annotation: bool = False, encrypted: bool = False) -> bytes:
    document = pymupdf.open()
    for index in range(pages):
        page = document.new_page()
        page.insert_text((72, 72), f"CLASSIFIRE technical source page {index + 1}")
        if uri_annotation and index == 0:
            page.insert_link(
                {
                    "kind": pymupdf.LINK_URI,
                    "from": pymupdf.Rect(70, 90, 240, 120),
                    "uri": "http://127.0.0.1/private-preview-must-not-fetch",
                }
            )
    if encrypted:
        raw = document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="owner-password",
            user_pw="reader-password",
        )
    else:
        raw = document.tobytes()
    document.close()
    return bytes(raw)


def _stream(
    tmp_path: Path,
    content: bytes,
    *,
    suffix: str = ".pdf",
    purpose: str = "technical_evidence",
) -> VerifiedStoredFileStream:
    path = tmp_path / f"descriptor-source{suffix}"
    path.write_bytes(content)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    return VerifiedStoredFileStream(
        StoredFileBinding(
            path=path,
            sha256=hashlib.sha256(content).hexdigest(),
            size_bytes=len(content),
            suffix=suffix,
            purpose=purpose,
        ),
        descriptor,
    )


def _user(db: Session, *, role: str = "read_only") -> User:
    user = User(
        email=f"{role}-{os.urandom(4).hex()}@example.test",
        full_name=role.replace("_", " ").title(),
        password_hash="not-used",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _request(
    user: User | None,
    path: str,
    *,
    headers: Mapping[str, str] | None = None,
) -> Request:
    session = {"csrf_token": "csrf-token"}
    if user is not None:
        session["user_id"] = user.id
    raw_headers = [
        (key.casefold().encode("ascii"), value.encode("ascii"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": raw_headers,
            "client": ("testclient", 1234),
            "server": ("testserver", 443),
            "session": session,
        }
    )


def _preview_http_app(db: Session, settings: Settings) -> FastAPI:
    test_app = FastAPI()
    test_app.add_middleware(
        SessionMiddleware,
        secret_key="preview-http-regression-secret",
    )
    test_app.middleware("http")(security_headers)
    test_app.exception_handler(HTTPException)(http_exception_handler)
    test_app.include_router(technical_admin_router)

    def override_db() -> Iterator[Session]:
        yield db

    @test_app.get("/_preview-test-login/{user_id}")
    def preview_test_login(user_id: str, request: Request) -> dict[str, bool]:
        request.session["user_id"] = user_id
        return {"ok": True}

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_settings] = lambda: settings
    return test_app


def _document(
    db: Session,
    settings: Settings,
    *,
    content: bytes | None = None,
    original_filename: str = "technical-report.pdf",
) -> tuple[TechnicalDocument, StoredFile]:
    raw = content if content is not None else _pdf()
    digest = hashlib.sha256(raw).hexdigest()
    suffix = Path(original_filename).suffix.lower()
    path = settings.storage_root / digest[:2] / digest[2:4] / f"{digest}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    stored = StoredFile(
        original_filename=original_filename,
        media_type="application/pdf",
        storage_path=str(path),
        sha256=digest,
        size_bytes=len(raw),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=f"SOURCE-PREVIEW-{os.urandom(4).hex()}",
        stored_file_id=stored.id,
        document_type="fire_test_report",
        title="Preview boundary report",
        status="draft",
        extraction_status="awaiting_safe_extraction",
    )
    db.add(document)
    db.commit()
    return document, stored


def test_worker_renders_only_requested_source_bound_png(tmp_path: Path) -> None:
    content = _pdf(pages=2, uri_annotation=True)
    stream = _stream(tmp_path, content)

    preview = render_technical_pdf_preview(stream, page_number=2)

    assert preview.page_number == 2
    assert preview.page_count == 2
    assert preview.source_sha256 == hashlib.sha256(content).hexdigest()
    assert preview.source_size_bytes == len(content)
    assert preview.policy_version == TECHNICAL_PDF_PREVIEW_POLICY
    assert preview.png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"%PDF" not in preview.png_bytes
    assert b"127.0.0.1" not in preview.png_bytes
    assert hashlib.sha256(preview.png_bytes).hexdigest() == preview.png_sha256
    assert len(preview.binding_sha256) == 64
    assert stream.closed is True


@pytest.mark.parametrize(
    ("content", "expected_codes"),
    [
        (b"%PDF-1.7\nmalformed\n%%EOF", {"PREVIEW_DOCUMENT_INVALID", "PREVIEW_PAGE_COUNT_INVALID"}),
        (_pdf(encrypted=True), {"PREVIEW_DOCUMENT_ENCRYPTED"}),
    ],
)
def test_worker_rejects_malformed_and_encrypted_pdfs(
    tmp_path: Path,
    content: bytes,
    expected_codes: set[str],
) -> None:
    stream = _stream(tmp_path, content)

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(stream, page_number=1)

    assert caught.value.code in expected_codes
    assert str(tmp_path) not in str(caught.value)
    assert stream.closed is True


def test_worker_rejects_out_of_range_page_and_excessive_page_count(
    tmp_path: Path,
) -> None:
    missing_page_stream = _stream(tmp_path, _pdf(pages=1))
    with pytest.raises(TechnicalPdfPreviewError) as missing:
        render_technical_pdf_preview(missing_page_stream, page_number=2)
    assert missing.value.code == "PREVIEW_PAGE_NOT_FOUND"

    too_many_pages_stream = _stream(tmp_path, _pdf(pages=501))
    with pytest.raises(TechnicalPdfPreviewError) as excessive:
        render_technical_pdf_preview(too_many_pages_stream, page_number=1)
    assert excessive.value.code == "PREVIEW_PAGE_COUNT_INVALID"


def test_worker_recomputes_descriptor_binding_before_parsing(tmp_path: Path) -> None:
    content = _pdf(pages=1)
    stream = _stream(tmp_path, content)
    stream.binding = StoredFileBinding(
        path=stream.binding.path,
        sha256="0" * 64,
        size_bytes=stream.binding.size_bytes,
        suffix=".pdf",
        purpose="technical_evidence",
    )

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(stream, page_number=1)

    assert caught.value.code == "PREVIEW_SOURCE_BINDING_MISMATCH"
    assert stream.closed is True


def test_preview_process_concurrency_limit_fails_closed(tmp_path: Path) -> None:
    stream = _stream(tmp_path, _pdf(pages=1))
    acquired = 0
    try:
        for _index in range(preview_service.TECHNICAL_PDF_PREVIEW_CONCURRENCY):
            assert preview_service._preview_slots.acquire(blocking=False) is True
            acquired += 1
        with pytest.raises(TechnicalPdfPreviewError) as caught:
            render_technical_pdf_preview(stream, page_number=1)
        assert caught.value.code == "PREVIEW_BUSY"
        assert stream.closed is False
    finally:
        for _index in range(acquired):
            preview_service._preview_slots.release()
        stream.close()


def test_service_rejects_non_pdf_before_starting_worker(tmp_path: Path) -> None:
    stream = _stream(tmp_path, b"office bytes", suffix=".docx")
    invoked = False

    def runner(_args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        nonlocal invoked
        invoked = True
        raise AssertionError("worker must not run")

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(stream, page_number=1, runner=runner)

    assert caught.value.code == "PREVIEW_FILE_TYPE_UNSUPPORTED"
    assert invoked is False
    stream.close()


def test_service_closes_descriptor_on_timeout(tmp_path: Path) -> None:
    content = _pdf(pages=1)
    stream = _stream(tmp_path, content)
    worker = tmp_path / "fixed-worker.py"
    worker.write_text("# fixed test worker\n", encoding="utf-8")

    def timeout_runner(args: Any, **_kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        raise subprocess.TimeoutExpired(args, 15)

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(
            stream,
            page_number=1,
            runner=timeout_runner,
            worker_path=worker,
            interpreter_path=Path(sys.executable),
        )

    assert caught.value.code == "PREVIEW_TIMEOUT"
    assert stream.closed is True


def test_service_rejects_malformed_worker_output(tmp_path: Path) -> None:
    content = _pdf(pages=1)
    stream = _stream(tmp_path, content)
    worker = tmp_path / "fixed-worker.py"
    worker.write_text("# fixed test worker\n", encoding="utf-8")

    def malformed_runner(
        args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["stdin"].read() == content
        return subprocess.CompletedProcess(args, 0, b'{"ok":true}\nnot-a-png', b"")

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(
            stream,
            page_number=1,
            runner=malformed_runner,
            worker_path=worker,
            interpreter_path=Path(sys.executable),
        )

    assert caught.value.code == "PREVIEW_WORKER_OUTPUT_INVALID"
    assert stream.closed is True


def test_default_runner_hard_bounds_real_worker_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = _pdf(pages=1)
    stream = _stream(tmp_path, content)
    worker = tmp_path / "oversized-worker.py"
    worker.write_text(
        "import sys\n"
        "sys.stdin.buffer.read()\n"
        "sys.stdout.buffer.write(b'x' * 8192)\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        preview_service,
        "TECHNICAL_PDF_PREVIEW_MAX_PNG_BYTES",
        64,
    )

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(
            stream,
            page_number=1,
            worker_path=worker,
            interpreter_path=Path(sys.executable),
        )

    assert caught.value.code == "PREVIEW_WORKER_OUTPUT_INVALID"
    assert stream.closed is True


def test_service_rejects_png_ihdr_dimensions_that_disagree_with_receipt(
    tmp_path: Path,
) -> None:
    content = _pdf(pages=1)
    stream = _stream(tmp_path, content)
    worker = tmp_path / "fixed-worker.py"
    worker.write_text("# fixed test worker\n", encoding="utf-8")
    png_buffer = BytesIO()
    with Image.new("RGB", (1, 1), color="white") as png_image:
        png_image.save(png_buffer, format="PNG")
    png_bytes = png_buffer.getvalue()
    metadata = {
        "height_pixels": 1,
        "ok": True,
        "page_count": 1,
        "page_number": 1,
        "png_sha256": hashlib.sha256(png_bytes).hexdigest(),
        "policy_version": TECHNICAL_PDF_PREVIEW_POLICY,
        "renderer": "PyMuPDF",
        "renderer_version": "1.28.2",
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "source_size_bytes": len(content),
        "width_pixels": 2,
    }

    def forged_runner(
        args: Any,
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[bytes]:
        assert kwargs["stdin"].read() == content
        stdout = json.dumps(metadata, separators=(",", ":")).encode() + b"\n" + png_bytes
        return subprocess.CompletedProcess(args, 0, stdout, b"")

    with pytest.raises(TechnicalPdfPreviewError) as caught:
        render_technical_pdf_preview(
            stream,
            page_number=1,
            runner=forged_runner,
            worker_path=worker,
            interpreter_path=Path(sys.executable),
        )

    assert caught.value.code == "PREVIEW_WORKER_OUTPUT_INVALID"
    assert stream.closed is True


def test_preview_runtime_configuration_is_fail_closed(tmp_path: Path) -> None:
    disabled = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "disabled",
        technical_pdf_preview_enabled=False,
    )
    enabled_test = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "enabled-test",
        technical_pdf_preview_enabled=True,
    )
    enabled_production = Settings(
        _env_file=None,
        env="production",
        storage_root=tmp_path / "enabled-production",
        technical_pdf_preview_enabled=True,
    )

    assert disabled.technical_pdf_preview_runtime_allowed is False
    assert enabled_test.technical_pdf_preview_runtime_allowed is True
    assert enabled_production.technical_pdf_preview_runtime_allowed is False
    assert any(
        finding.startswith("CLASSIFIRE_TECHNICAL_PDF_PREVIEW_ENABLED")
        for finding in enabled_production.validate_production()
    )


def test_preview_route_returns_verified_png_headers_without_state_changes(
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
    document, stored = _document(db, settings)
    path = (
        f"/technical/documents/{document.id}/preview/"
        f"{stored.sha256}/pages/2"
    )
    original_state = (
        document.status,
        document.extraction_status,
        stored.malware_scan_status,
        stored.sha256,
    )

    response = technical_document_preview(
        document.id,
        stored.sha256,
        "2",
        _request(reader, path),
        db,
        settings,
    )

    assert response.status_code == 200
    assert response.media_type == "image/png"
    assert response.body.startswith(b"\x89PNG\r\n\x1a\n")
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["content-disposition"] == (
        'inline; filename="preview-page-0002.png"'
    )
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-classifire-source-sha256"] == stored.sha256
    assert response.headers["x-classifire-source-size"] == str(stored.size_bytes)
    assert response.headers["x-classifire-preview-page"] == "2"
    assert response.headers["x-classifire-preview-page-count"] == "2"
    assert response.headers["x-classifire-preview-policy"] == (
        TECHNICAL_PDF_PREVIEW_POLICY
    )
    assert response.headers["accept-ranges"] == "none"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert response.headers["cross-origin-resource-policy"] == "same-origin"
    db.expire_all()
    current_document = db.get(TechnicalDocument, document.id)
    current_stored = db.get(StoredFile, stored.id)
    assert current_document is not None and current_stored is not None
    assert (
        current_document.status,
        current_document.extraction_status,
        current_stored.malware_scan_status,
        current_stored.sha256,
    ) == original_state
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize(
    ("role", "expected_status"),
    [(None, 401), ("pricing_manager", 403)],
)
def test_preview_route_requires_technical_read_before_rendering(
    db: Session,
    tmp_path: Path,
    role: str | None,
    expected_status: int,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=True,
    )
    document, stored = _document(db, settings)
    user = _user(db, role=role) if role else None
    path = (
        f"/technical/documents/{document.id}/preview/"
        f"{stored.sha256}/pages/1"
    )

    with pytest.raises(HTTPException) as caught:
        technical_document_preview(
            document.id,
            stored.sha256,
            "1",
            _request(user, path),
            db,
            settings,
        )

    assert caught.value.status_code == expected_status


def test_preview_route_refuses_quarantined_retained_evidence(
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
    document, stored = _document(db, settings)
    stored.malware_scan_status = "quarantined"
    db.commit()
    path = f"/technical/documents/{document.id}/preview/{stored.sha256}/pages/1"

    with pytest.raises(HTTPException) as caught:
        technical_document_preview(
            document.id,
            stored.sha256,
            "1",
            _request(reader, path),
            db,
            settings,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == "SOURCE_FILE_INVALID"


def test_preview_route_reloads_quarantine_state_before_opening(
    db: Session,
    tmp_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        env='test',
        storage_root=tmp_path / 'storage',
        technical_pdf_preview_enabled=True,
    )
    reader = _user(db)
    document, stored = _document(db, settings)
    stale_stored_file = db.get(StoredFile, stored.id)
    assert stale_stored_file is not None
    assert stale_stored_file.malware_scan_status == 'clean'
    with Session(db.get_bind()) as containment_session:
        contained = containment_session.get(StoredFile, stored.id)
        assert contained is not None
        contained.malware_scan_status = 'quarantined'
        contained.record_version += 1
        containment_session.commit()
    assert stale_stored_file.malware_scan_status == 'clean'
    path = f'/technical/documents/{document.id}/preview/{stored.sha256}/pages/1'

    with pytest.raises(HTTPException) as caught:
        technical_document_preview(
            document.id,
            stored.sha256,
            '1',
            _request(reader, path),
            db,
            settings,
        )

    assert caught.value.status_code == 409
    assert caught.value.detail == 'SOURCE_FILE_INVALID'
    assert stale_stored_file.malware_scan_status == 'quarantined'


def test_preview_route_fails_closed_for_stale_hash_tamper_and_ranges(
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
    document, stored = _document(db, settings)
    path = f"/technical/documents/{document.id}/preview/{stored.sha256}/pages/1"

    with pytest.raises(HTTPException) as stale:
        technical_document_preview(
            document.id,
            "0" * 64,
            "1",
            _request(reader, path),
            db,
            settings,
        )
    assert stale.value.status_code == 409
    assert stale.value.detail == "PREVIEW_SOURCE_BINDING_CHANGED"

    original = Path(stored.storage_path).read_bytes()
    Path(stored.storage_path).write_bytes(b"x" * len(original))
    with pytest.raises(HTTPException) as tampered:
        technical_document_preview(
            document.id,
            stored.sha256,
            "1",
            _request(reader, path),
            db,
            settings,
        )
    assert tampered.value.status_code == 409
    assert tampered.value.detail == "SOURCE_FILE_INVALID"

    Path(stored.storage_path).write_bytes(original)
    with pytest.raises(HTTPException) as ranged:
        technical_document_preview(
            document.id,
            stored.sha256,
            "1",
            _request(reader, path, headers={"Range": "bytes=0-10"}),
            db,
            settings,
        )
    assert ranged.value.status_code == 416
    assert ranged.value.detail == "PREVIEW_RANGES_NOT_SUPPORTED"
    assert ranged.value.headers == {
        "Accept-Ranges": "none",
        "Cache-Control": "private, no-store",
    }


def test_disabled_preview_never_opens_retained_source(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=False,
    )
    reader = _user(db)
    document, stored = _document(db, settings)
    opens = 0

    def unexpected_open(*_args: object, **_kwargs: object) -> object:
        nonlocal opens
        opens += 1
        raise AssertionError("disabled preview must not open retained evidence")

    monkeypatch.setattr(
        technical_admin_module,
        "open_verified_stored_file",
        unexpected_open,
    )
    path = f"/technical/documents/{document.id}/preview/{stored.sha256}/pages/1"

    with pytest.raises(HTTPException) as caught:
        technical_document_preview(
            document.id,
            stored.sha256,
            "1",
            _request(reader, path),
            db,
            settings,
        )

    assert caught.value.status_code == 503
    assert caught.value.detail == "PREVIEW_DISABLED"
    assert opens == 0


def test_preview_capacity_is_reserved_before_source_hashing(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        technical_pdf_preview_enabled=True,
    )
    reader = _user(db)
    document, stored = _document(db, settings)
    opens = 0

    def unexpected_open(*_args: object, **_kwargs: object) -> object:
        nonlocal opens
        opens += 1
        raise AssertionError("busy preview must not open or hash retained evidence")

    monkeypatch.setattr(
        technical_admin_module,
        "open_verified_stored_file",
        unexpected_open,
    )
    acquired = 0
    try:
        for _index in range(preview_service.TECHNICAL_PDF_PREVIEW_CONCURRENCY):
            assert preview_service._preview_slots.acquire(blocking=False) is True
            acquired += 1
        path = f"/technical/documents/{document.id}/preview/{stored.sha256}/pages/1"
        with pytest.raises(HTTPException) as caught:
            technical_document_preview(
                document.id,
                stored.sha256,
                "1",
                _request(reader, path),
                db,
                settings,
            )
        assert caught.value.status_code == 503
        assert caught.value.detail == "PREVIEW_BUSY"
        assert opens == 0
    finally:
        for _index in range(acquired):
            preview_service._preview_slots.release()


def test_preview_asgi_errors_are_not_redirected_or_cached(
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
    document, stored = _document(db, settings)
    path = f"/technical/documents/{document.id}/preview/{stored.sha256}/pages/1"
    test_app = _preview_http_app(db, settings)

    with TestClient(test_app) as client:
        unauthenticated = client.get(path, follow_redirects=False)
        assert unauthenticated.status_code == 401
        assert "location" not in unauthenticated.headers
        assert unauthenticated.json() == {"detail": "Authentication required"}
        assert unauthenticated.headers["accept-ranges"] == "none"
        assert "no-store" in unauthenticated.headers["cache-control"]
        assert unauthenticated.headers["vary"] == "Cookie"
        malformed_binding = client.get(
            f"/technical/documents/{document.id}/preview/not-a-digest/pages/-1",
            follow_redirects=False,
        )
        assert malformed_binding.status_code == 401
        assert "location" not in malformed_binding.headers
        assert "no-store" in malformed_binding.headers["cache-control"]
        malformed_page_path = (
            f"/technical/documents/{document.id}/preview/"
            f"{stored.sha256}/pages/not-a-number"
        )
        malformed_page = client.get(
            malformed_page_path,
            follow_redirects=False,
        )
        assert malformed_page.status_code == 401
        assert "location" not in malformed_page.headers
        assert "no-store" in malformed_page.headers["cache-control"]

        login = client.get(f"/_preview-test-login/{reader.id}")
        assert login.status_code == 200
        invalid_page = client.get(
            malformed_page_path,
            follow_redirects=False,
        )
        assert invalid_page.status_code == 404
        assert invalid_page.json() == {"detail": "PREVIEW_PAGE_NOT_FOUND"}
        assert "no-store" in invalid_page.headers["cache-control"]
        ranged = client.get(
            path,
            headers={"Range": "bytes=0-10"},
            follow_redirects=False,
        )
        rendered = client.get(path, follow_redirects=False)

    assert ranged.status_code == 416
    assert ranged.json() == {"detail": "PREVIEW_RANGES_NOT_SUPPORTED"}
    assert ranged.headers["accept-ranges"] == "none"
    assert "no-store" in ranged.headers["cache-control"]
    assert ranged.headers["vary"] == "Cookie"
    assert rendered.status_code == 200
    assert rendered.headers["content-type"] == "image/png"
    assert rendered.headers["x-classifire-source-sha256"] == stored.sha256
    assert hashlib.sha256(rendered.content).hexdigest() == (
        rendered.headers["x-classifire-preview-png-sha256"]
    )
    assert "no-store" in rendered.headers["cache-control"]
    assert rendered.headers["vary"] == "Cookie"


def test_security_middleware_preserves_stricter_preview_policy() -> None:
    request = _request(None, "/technical/preview.png")

    async def strict_response(_request: Request) -> Response:
        return Response(
            b"png",
            headers={
                "Content-Security-Policy": (
                    "default-src 'none'; sandbox; frame-ancestors 'none'"
                ),
                "Referrer-Policy": "no-referrer",
            },
        )

    response = asyncio.run(security_headers(request, strict_response))

    assert response.headers["content-security-policy"] == (
        "default-src 'none'; sandbox; frame-ancestors 'none'"
    )
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


def test_default_security_policy_explicitly_blocks_frames_and_objects() -> None:
    request = _request(None, "/")

    async def plain_response(_request: Request) -> Response:
        return Response(b"ok")

    response = asyncio.run(security_headers(request, plain_response))
    policy = response.headers["content-security-policy"]

    assert "object-src 'none'" in policy
    assert "frame-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


def test_preview_javascript_syntax_and_fail_closed_contract() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "classifire"
        / "static"
        / "js"
        / "technical-preview.js"
    )
    source = script.read_text(encoding="utf-8")

    assert "parsePngDimensions" in source
    assert "actualBindingSha256 !== receipt.bindingSha256" in source
    assert "restoreFocus(initiatingControl)" in source
    assert "if (!initiatingControl)" in source
    assert "focusTarget = pageInput.disabled ? stage : pageInput" in source
    assert "initializationFailure()" in source
    assert 'redirect: "error"' in source
    assert "safe preview" not in source.casefold()

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable for JavaScript syntax validation")
    completed = subprocess.run(  # noqa: S603
        (node, "--check", str(script)),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
