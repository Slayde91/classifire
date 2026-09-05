"""Draft PDF upload, genuine scan, retained-page review and explicit Scope revision."""

from __future__ import annotations

import hashlib
import io
import json
import os

# Fixed parser subprocess only; no shell and no content in command arguments.
import subprocess  # nosec B404
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.datastructures import Headers

from ..audit import record_audit
from ..config import Settings
from ..models import DraftPdfSource, StoredFile, User, new_id
from . import malware_scan
from .draft_scope import (
    DraftScopeError,
    _actor,
    _append_revision,
    _atomic,
    _json,
    get_draft,
    read_revision,
)
from .draft_scope_evidence import observation_hash
from .storage import (
    StoredFileBindingError,
    VerifiedStoredFileContent,
    _locked_stored_files_by_sha256,
    _require_serialized_containment_transaction,
    quarantine_stored_file_bytes_for_update,
    read_clean_stored_file_for_update,
    read_verified_stored_file,
    save_upload,
)

PURPOSE = "draft_scope_pdf"
MAX_SOURCES = 20
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_BYTES = 4 * 1024 * 1024


def _postgres(db: Session) -> None:
    try:
        _require_serialized_containment_transaction(db)
    except StoredFileBindingError as exc:
        raise DraftScopeError("PDF_POSTGRESQL_REQUIRED", 409) from exc


def _source(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    *,
    write: bool = False,
    lock: bool = False,
) -> tuple[User, DraftPdfSource]:
    actor = _actor(db, actor, "project:write" if write else "project:read")
    get_draft(db, actor, draft_id)
    query = (
        select(DraftPdfSource)
        .where(DraftPdfSource.id == source_id, DraftPdfSource.draft_scope_id == draft_id)
        .execution_options(populate_existing=True)
    )
    if lock:
        _postgres(db)
        query = query.with_for_update()
    source = db.scalar(query)
    if source is None:
        raise DraftScopeError("PDF_SOURCE_NOT_FOUND", 404)
    return actor, source


def _file(db: Session, source: DraftPdfSource) -> StoredFile:
    row = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == source.stored_file_id)
        .execution_options(populate_existing=True)
    )
    if row is None or (row.sha256, row.size_bytes, row.purpose) != (
        source.source_sha256,
        source.source_size_bytes,
        PURPOSE,
    ):
        raise DraftScopeError("PDF_SOURCE_INTEGRITY_FAILED", 409)
    return row


def list_sources(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    get_draft(db, actor, draft_id)
    sources = db.scalars(
        select(DraftPdfSource)
        .where(DraftPdfSource.draft_scope_id == draft_id)
        .order_by(DraftPdfSource.created_at.desc(), DraftPdfSource.id)
        .limit(MAX_SOURCES)
    ).all()
    return [source_info(db, actor, draft_id, row.id) for row in sources]


def source_info(db: Session, actor: User, draft_id: str, source_id: str) -> dict[str, Any]:
    actor, row = _source(db, actor, draft_id, source_id)
    stored = _file(db, row)
    try:
        scan = json.loads(row.scan_json) if row.scan_json else None
        if scan is not None and not isinstance(scan, dict):
            raise ValueError("scan metadata")
    except (ValueError, TypeError) as exc:
        raise DraftScopeError("PDF_SOURCE_INTEGRITY_FAILED", 409) from exc
    return {
        "id": row.id,
        "filename": row.original_filename,
        "sha256": row.source_sha256,
        "size_bytes": row.source_size_bytes,
        "status": stored.malware_scan_status,
        "scan": scan,
        "processing_error": row.processing_error,
        "ready": stored.malware_scan_status == "clean" and row.document_json is not None,
        "created_at": row.created_at,
        "document_sha256": row.document_sha256,
    }


def retain_pdf(
    db: Session, actor: User, draft_id: str, filename: str, content: bytes, *, settings: Settings
) -> DraftPdfSource:
    actor = _actor(db, actor, "project:write")
    draft = get_draft(db, actor, draft_id)
    _postgres(db)
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if (
        not name.lower().endswith(".pdf")
        or not 1 <= len(name) <= 200
        or any(ord(c) < 32 for c in name)
        or type(content) is not bytes
        or not 1 <= len(content) <= min(settings.max_upload_bytes, malware_scan.MAX_SCAN_BYTES)
        or not content.startswith(b"%PDF-")
    ):
        raise DraftScopeError("PDF_UPLOAD_INVALID")
    digest = hashlib.sha256(content).hexdigest()
    # Serialize same-byte submissions without granting one project access to another.
    key = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    existing = db.scalar(select(StoredFile).where(StoredFile.sha256 == digest))
    if existing is not None:
        source = db.scalar(
            select(DraftPdfSource).where(
                DraftPdfSource.stored_file_id == existing.id,
                DraftPdfSource.draft_scope_id == draft_id,
            )
        )
        if source is None or existing.purpose != PURPOSE:
            raise DraftScopeError("PDF_UPLOAD_CONFLICT", 409)
        return source
    # Serialize the per-Draft quota with other source additions.
    from ..models import DraftScope

    db.scalar(select(DraftScope.id).where(DraftScope.id == draft_id).with_for_update())
    if (
        db.scalar(
            select(func.count())
            .select_from(DraftPdfSource)
            .where(DraftPdfSource.draft_scope_id == draft_id)
        )
        or 0
    ) >= MAX_SOURCES:
        raise DraftScopeError("PDF_SOURCE_LIMIT", 409)
    try:
        with _atomic(db):
            stored = save_upload(
                db,
                settings,
                UploadFile(
                    filename=name,
                    file=io.BytesIO(content),
                    headers=Headers({"content-type": "application/pdf"}),
                ),
                purpose=PURPOSE,
                user=actor,
            )
            # Upload never infers a clean verdict, including when no scanner is configured.
            actor = _actor(db, actor, "project:write")
            get_draft(db, actor, draft_id)
            source = DraftPdfSource(
                draft_scope_id=draft_id,
                stored_file_id=stored.id,
                source_sha256=digest,
                source_size_bytes=len(content),
                original_filename=name,
                created_by_id=actor.id,
            )
            db.add(source)
            db.flush()
            record_audit(
                db,
                actor=actor,
                action="draft_pdf.upload",
                entity_type="draft_pdf_source",
                entity_id=source.id,
                project_id=draft.project_id,
                new_value={"sha256": digest, "size_bytes": len(content)},
            )
            db.flush()
            return source
    except (IntegrityError, ValueError, OSError, StoredFileBindingError) as exc:
        if isinstance(exc, DraftScopeError):
            raise
        raise DraftScopeError("PDF_UPLOAD_FAILED", 409) from exc


def _process(content: bytes, page_number: int | None = None) -> bytes:
    command = [sys.executable, "-m", "classifire.services.draft_pdf_worker"]
    if page_number is not None:
        command.append(str(page_number))
    # Do not pass application/provider/database credentials to the parser process.
    environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}
    }
    environment.update(
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
    )
    try:
        result = subprocess.run(  # noqa: S603  # nosec B603
            command,
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
            env=environment,
        )  # noqa: S603
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DraftScopeError("PDF_PROCESSING_FAILED", 422) from exc
    limit = MAX_DOCUMENT_BYTES if page_number is None else MAX_PREVIEW_BYTES
    if result.returncode != 0 or not 1 <= len(result.stdout) <= limit:
        raise DraftScopeError("PDF_PROCESSING_FAILED", 422)
    if page_number is not None and not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
        raise DraftScopeError("PDF_PROCESSING_FAILED", 422)
    if page_number is None:
        try:
            document = json.loads(result.stdout)
            if (
                document["schema"] != "CLASSIFIRE-DRAFT-PDF-v1"
                or document["manifest"]["source_sha256"] != hashlib.sha256(content).hexdigest()
                or not 1 <= len(document["pages"]) <= 50
            ):
                raise ValueError("worker binding")
        except (ValueError, TypeError, KeyError) as exc:
            raise DraftScopeError("PDF_PROCESSING_FAILED", 422) from exc
    return result.stdout


def scan_source(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> dict[str, Any]:
    actor, source = _source(db, actor, draft_id, source_id, write=True, lock=True)
    rows = _locked_stored_files_by_sha256(db, source.source_sha256)
    stored = _file(db, source)
    if not rows or any(row.malware_scan_status == "malware_detected" for row in rows):
        raise DraftScopeError("PDF_SOURCE_QUARANTINED", 409)
    try:
        content = read_verified_stored_file(
            stored,
            storage_root=settings.storage_root,
            required_purpose=PURPOSE,
            allowed_scan_statuses=("pending", "not_configured", "scan_error", "clean"),
        )
    except StoredFileBindingError as exc:
        raise DraftScopeError("PDF_SOURCE_INTEGRITY_FAILED", 409) from exc
    draft = get_draft(db, actor, draft_id)
    previous = json.loads(source.scan_json) if source.scan_json else None
    source.processing_error = None
    source.document_json = None
    source.document_sha256 = None
    stored.malware_scan_status = "pending"
    try:
        verdict = malware_scan.scan_bytes(
            content.content, host=settings.clamav_host, port=settings.clamav_port
        )
        if verdict.sha256 != content.sha256 or verdict.size_bytes != content.size_bytes:
            raise malware_scan.MalwareScanError("SCAN_BINDING_INVALID")
        scan = asdict(verdict)
    except malware_scan.MalwareScanError as exc:
        scan = {
            "sha256": content.sha256,
            "size_bytes": content.size_bytes,
            "status": "not_configured" if exc.code == "SCAN_NOT_CONFIGURED" else "scan_error",
            "code": exc.code,
            "scanned_at": datetime.now(UTC).isoformat(),
        }
    authorized = True
    try:
        actor = _actor(db, actor, "project:write")
    except DraftScopeError:
        authorized = False
    if not authorized and scan["status"] != "malware_detected":
        scan = {
            "sha256": content.sha256,
            "size_bytes": content.size_bytes,
            "status": "scan_error",
            "code": "SCAN_PERMISSION_CHANGED",
            "scanned_at": datetime.now(UTC).isoformat(),
        }
    if scan["status"] == "malware_detected":
        quarantine_stored_file_bytes_for_update(
            db,
            stored_file_id=stored.id,
            observed_sha256=content.sha256,
            observed_size_bytes=content.size_bytes,
        )
    else:
        stored.malware_scan_status = scan["status"]
    source.scan_json = _json(scan).decode("utf-8")
    db.flush()
    if scan["status"] == "clean":
        try:
            # Re-read exact bytes under the existing shared quarantine lock boundary.
            verified = read_clean_stored_file_for_update(
                db,
                stored_file_id=stored.id,
                storage_root=settings.storage_root,
                required_purpose=PURPOSE,
            )
            document_bytes = _process(verified.content)
            source.document_json = document_bytes.decode("utf-8")
            source.document_sha256 = hashlib.sha256(document_bytes).hexdigest()
        except (DraftScopeError, StoredFileBindingError):
            source.processing_error = "PDF_PROCESSING_FAILED"
        try:
            actor = _actor(db, actor, "project:write")
            get_draft(db, actor, draft_id)
        except DraftScopeError:
            stored.malware_scan_status = "scan_error"
            source.document_json = None
            source.document_sha256 = None
            source.processing_error = "SCAN_PERMISSION_CHANGED"
    record_audit(
        db,
        actor=actor,
        action="draft_pdf.scan",
        entity_type="draft_pdf_source",
        entity_id=source.id,
        project_id=draft.project_id,
        previous_value=previous,
        new_value=scan | {"processing_error": source.processing_error},
    )
    db.flush()
    return {"status": stored.malware_scan_status, "processing_error": source.processing_error}


def _document(
    db: Session, actor: User, draft_id: str, source_id: str, storage_root: Path
) -> tuple[DraftPdfSource, dict[str, Any], VerifiedStoredFileContent]:
    actor, source = _source(db, actor, draft_id, source_id, lock=True)
    _file(db, source)
    try:
        content = read_clean_stored_file_for_update(
            db,
            stored_file_id=source.stored_file_id,
            storage_root=storage_root,
            required_purpose=PURPOSE,
        )
        if source.document_json is None or source.scan_json is None:
            raise ValueError("missing")
        raw = source.document_json.encode("utf-8")
        if (
            len(raw) > MAX_DOCUMENT_BYTES
            or hashlib.sha256(raw).hexdigest() != source.document_sha256
        ):
            raise ValueError("document")
        document = json.loads(raw)
        scan = json.loads(source.scan_json)
        if (
            scan["status"] != "clean"
            or scan["sha256"] != content.sha256
            or scan["size_bytes"] != content.size_bytes
            or document["schema"] != "CLASSIFIRE-DRAFT-PDF-v1"
            or document["manifest"]["source_sha256"] != content.sha256
            or document["manifest"]["source_size_bytes"] != content.size_bytes
            or not 1 <= len(document["pages"]) <= 50
        ):
            raise ValueError("binding")
        # An expired signature database requires a fresh scan before active viewing/review.
        database_date = datetime.fromisoformat(scan["database_date"])
        if (
            datetime.now(UTC) - database_date
        ).total_seconds() > malware_scan.MAX_DATABASE_AGE_DAYS * 86400:
            raise DraftScopeError("PDF_SCAN_EXPIRED", 409)
    except (StoredFileBindingError, ValueError, TypeError, KeyError, UnicodeError) as exc:
        if isinstance(exc, DraftScopeError):
            raise
        raise DraftScopeError("PDF_SOURCE_NOT_READY", 409) from exc
    _actor(db, actor, "project:read")
    get_draft(db, actor, draft_id)
    return source, cast(dict[str, Any], document), content


def read_document(
    db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
) -> dict[str, Any]:
    return _document(db, actor, draft_id, source_id, settings.storage_root)[1]


def page_preview(
    db: Session, actor: User, draft_id: str, source_id: str, page_number: int, *, settings: Settings
) -> bytes:
    source, document, content = _document(db, actor, draft_id, source_id, settings.storage_root)
    if type(page_number) is not int or not 1 <= page_number <= len(document["pages"]):
        raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
    result = _process(content.content, page_number)
    _actor(db, actor, "project:read")
    get_draft(db, actor, draft_id)
    return result


def review_page(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    page_number: int,
    observation: str,
    state: str,
    expected_document_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    actor = _actor(db, actor, "project:write")
    source, document, _content = _document(db, actor, draft_id, source_id, settings.storage_root)
    if source.document_sha256 != expected_document_hash:
        raise DraftScopeError("PDF_REVIEW_SOURCE_CHANGED", 409)
    if type(page_number) is not int or not 1 <= page_number <= len(document["pages"]):
        raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
    envelope = read_revision(db, actor, draft_id)
    if envelope["revision"] != expected_revision:
        raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
    payload = json.loads(_json(envelope["content"]))
    item = {"id": new_id(), "text": observation.strip(), "state": state}
    payload["observations"].append(item)
    page = document["pages"][page_number - 1]
    ref = {
        "observation_id": item["id"],
        "observation_sha256": observation_hash(item),
        "source_id": source.id,
        "source_sha256": source.source_sha256,
        "source_size_bytes": source.source_size_bytes,
        "original_filename": source.original_filename,
        "page_number": page_number,
        "locator_key": page["locator_key"],
        "page_text_sha256": page["page_text_sha256"],
        "document_sha256": source.document_sha256,
        "scan_sha256": hashlib.sha256(cast(str, source.scan_json).encode("utf-8")).hexdigest(),
        "reviewed_by": actor.id,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "method": "human_page_review",
        "origin": "local_retained",
    }
    actor = _actor(db, actor, "project:write")
    return _append_revision(db, actor, draft_id, expected_revision, payload, evidence_ref=ref)


def scope_evidence_staleness(
    db: Session, actor: User, draft_id: str, scope: dict[str, Any], *, storage_root: Path | None
) -> list[str]:
    refs = scope.get("evidence_refs", [])
    if not refs:
        return []
    reasons = []
    observations = {item["id"]: item for item in scope["content"]["observations"]}
    for ref in refs:
        if ref["origin"] != "local_retained":
            reasons.append("SCOPE_SOURCE_UNVERIFIED")
            continue
        if observation_hash(observations[ref["observation_id"]]) != ref["observation_sha256"]:
            reasons.append("SCOPE_PAGE_REVIEW_CHANGED")
        if storage_root is None:
            reasons.append("SCOPE_SOURCE_CHECK_UNAVAILABLE")
            continue
        try:
            # Use only the caller-supplied retained root, never ambient application settings.
            source, _document_value, content = _document(
                db, actor, draft_id, ref["source_id"], storage_root
            )
            if (
                content.sha256 != ref["source_sha256"]
                or source.document_sha256 != ref["document_sha256"]
                or hashlib.sha256(cast(str, source.scan_json).encode("utf-8")).hexdigest()
                != ref["scan_sha256"]
            ):
                reasons.append("SCOPE_SOURCE_CHANGED")
        except DraftScopeError as exc:
            if exc.status_code == 403:
                raise
            reasons.append("SCOPE_SOURCE_UNAVAILABLE")
    return list(dict.fromkeys(reasons))
