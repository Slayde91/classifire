"""Shared Draft-owned retained-source upload, scan and integrity boundaries."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
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
from ..models import DraftImportedReportSource, DraftPdfSource, DraftPricingSource, StoredFile, User
from . import malware_scan
from .draft_scope import DraftScopeError, _actor, _atomic, _json, get_draft
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

MAX_SOURCES = 20
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
SourceRow = DraftPdfSource | DraftPricingSource | DraftImportedReportSource


@dataclass(frozen=True)
class SourcePolicy:
    model: type[SourceRow]
    purpose: str
    extension: str
    magic: bytes
    media_type: str
    schema: str
    code_prefix: str
    audit_name: str
    process: Callable[[bytes], bytes]
    valid_document: Callable[[dict[str, Any]], bool]
    allow_supplied_content_reuse: bool = False
    max_sources: int = MAX_SOURCES
    read_permissions: tuple[str, ...] = ()
    write_permissions: tuple[str, ...] = ()


class DraftSourceIntake:
    def __init__(self, policy: SourcePolicy) -> None:
        self.policy = policy

    def _actor(self, db: Session, actor: User, *, write: bool = False) -> User:
        actor = _actor(db, actor, "project:write" if write else "project:read")
        for permission in self.policy.read_permissions + (
            self.policy.write_permissions if write else ()
        ):
            actor = _actor(db, actor, permission)
        return actor

    def _postgres(self, db: Session) -> None:
        try:
            _require_serialized_containment_transaction(db)
        except StoredFileBindingError as exc:
            raise DraftScopeError(self.policy.code_prefix + "POSTGRESQL_REQUIRED", 409) from exc

    def _source(
        self,
        db: Session,
        actor: User,
        draft_id: str,
        source_id: str,
        *,
        write: bool = False,
        lock: bool = False,
    ) -> tuple[User, SourceRow]:
        actor = self._actor(db, actor, write=write)
        get_draft(db, actor, draft_id)
        query = (
            select(self.policy.model)
            .where(self.policy.model.id == source_id, self.policy.model.draft_scope_id == draft_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            self._postgres(db)
            query = query.with_for_update()
        source = db.scalar(query)
        if source is None:
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_NOT_FOUND", 404)
        return actor, cast(SourceRow, source)

    def _file(self, db: Session, source: SourceRow) -> StoredFile:
        row = db.scalar(
            select(StoredFile)
            .where(StoredFile.id == source.stored_file_id)
            .execution_options(populate_existing=True)
        )
        if row is None or (row.sha256, row.size_bytes, row.purpose) != (
            source.source_sha256,
            source.source_size_bytes,
            self.policy.purpose,
        ):
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_INTEGRITY_FAILED", 409)
        return row

    def list_sources(self, db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
        self._actor(db, actor)
        get_draft(db, actor, draft_id)
        sources = db.scalars(
            select(self.policy.model)
            .where(self.policy.model.draft_scope_id == draft_id)
            .order_by(self.policy.model.created_at.desc(), self.policy.model.id)
            .limit(MAX_SOURCES)
        ).all()
        return [self.source_info(db, actor, draft_id, cast(SourceRow, row).id) for row in sources]

    def source_info(
        self, db: Session, actor: User, draft_id: str, source_id: str
    ) -> dict[str, Any]:
        actor, row = self._source(db, actor, draft_id, source_id)
        stored = self._file(db, row)
        try:
            scan = json.loads(row.scan_json) if row.scan_json else None
            if scan is not None and not isinstance(scan, dict):
                raise ValueError("scan metadata")
        except (ValueError, TypeError) as exc:
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_INTEGRITY_FAILED", 409) from exc
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

    def retain(
        self,
        db: Session,
        actor: User,
        draft_id: str,
        filename: str,
        content: bytes,
        *,
        settings: Settings,
    ) -> SourceRow:
        actor = self._actor(db, actor, write=True)
        draft = get_draft(db, actor, draft_id)
        self._postgres(db)
        name = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if (
            not name.lower().endswith(self.policy.extension)
            or not 1 <= len(name) <= 200
            or any(ord(c) < 32 for c in name)
            or type(content) is not bytes
            or not 1 <= len(content) <= min(settings.max_upload_bytes, malware_scan.MAX_SCAN_BYTES)
            or not content.startswith(self.policy.magic)
        ):
            raise DraftScopeError(self.policy.code_prefix + "UPLOAD_INVALID")
        digest = hashlib.sha256(content).hexdigest()
        # Serialize same-byte submissions without granting one project access to another.
        key = int.from_bytes(bytes.fromhex(digest[:16]), "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        existing = db.scalar(select(StoredFile).where(StoredFile.sha256 == digest))
        if existing is not None:
            source = db.scalar(
                select(self.policy.model).where(
                    self.policy.model.stored_file_id == existing.id,
                    self.policy.model.draft_scope_id == draft_id,
                )
            )
            if existing.purpose != self.policy.purpose or (
                source is None and not self.policy.allow_supplied_content_reuse
            ):
                raise DraftScopeError(self.policy.code_prefix + "UPLOAD_CONFLICT", 409)
            if source is not None:
                return cast(SourceRow, source)
            # An explicit exact-byte upload may create a NEW owner-scoped binding.
            # Never reuse the foreign source row or reset the shared quarantine status.
        # Serialize the per-Draft quota with other source additions.
        from ..models import DraftScope

        db.scalar(select(DraftScope.id).where(DraftScope.id == draft_id).with_for_update())
        if (
            db.scalar(
                select(func.count())
                .select_from(self.policy.model)
                .where(self.policy.model.draft_scope_id == draft_id)
            )
            or 0
        ) >= self.policy.max_sources:
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_LIMIT", 409)
        try:
            with _atomic(db):
                stored = save_upload(
                    db,
                    settings,
                    UploadFile(
                        filename=name,
                        file=io.BytesIO(content),
                        headers=Headers({"content-type": self.policy.media_type}),
                    ),
                    purpose=self.policy.purpose,
                    user=actor,
                )
                # Upload never infers a clean verdict, including when no scanner is configured.
                actor = self._actor(db, actor, write=True)
                get_draft(db, actor, draft_id)
                source = self.policy.model(
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
                    action=self.policy.audit_name + ".upload",
                    entity_type=self.policy.audit_name + "_source",
                    entity_id=source.id,
                    project_id=draft.project_id,
                    new_value={"sha256": digest, "size_bytes": len(content)},
                )
                db.flush()
                return cast(SourceRow, source)
        except (IntegrityError, ValueError, OSError, StoredFileBindingError) as exc:
            if isinstance(exc, DraftScopeError):
                raise
            raise DraftScopeError(self.policy.code_prefix + "UPLOAD_FAILED", 409) from exc

    def scan_source(
        self, db: Session, actor: User, draft_id: str, source_id: str, *, settings: Settings
    ) -> dict[str, Any]:
        actor, source = self._source(db, actor, draft_id, source_id, write=True, lock=True)
        rows = _locked_stored_files_by_sha256(db, source.source_sha256)
        stored = self._file(db, source)
        if not rows or any(row.malware_scan_status == "malware_detected" for row in rows):
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_QUARANTINED", 409)
        try:
            content = read_verified_stored_file(
                stored,
                storage_root=settings.storage_root,
                required_purpose=self.policy.purpose,
                allowed_scan_statuses=("pending", "not_configured", "scan_error", "clean"),
            )
        except StoredFileBindingError as exc:
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_INTEGRITY_FAILED", 409) from exc
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
            actor = self._actor(db, actor, write=True)
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
                    required_purpose=self.policy.purpose,
                )
                document_bytes = self.policy.process(verified.content)
                source.document_json = document_bytes.decode("utf-8")
                source.document_sha256 = hashlib.sha256(document_bytes).hexdigest()
            except (DraftScopeError, StoredFileBindingError):
                source.processing_error = self.policy.code_prefix + "PROCESSING_FAILED"
            try:
                actor = self._actor(db, actor, write=True)
                get_draft(db, actor, draft_id)
            except DraftScopeError:
                stored.malware_scan_status = "scan_error"
                source.document_json = None
                source.document_sha256 = None
                source.processing_error = "SCAN_PERMISSION_CHANGED"
        record_audit(
            db,
            actor=actor,
            action=self.policy.audit_name + ".scan",
            entity_type=self.policy.audit_name + "_source",
            entity_id=source.id,
            project_id=draft.project_id,
            previous_value=previous,
            new_value=scan | {"processing_error": source.processing_error},
        )
        db.flush()
        return {"status": stored.malware_scan_status, "processing_error": source.processing_error}

    def _document(
        self, db: Session, actor: User, draft_id: str, source_id: str, storage_root: Path
    ) -> tuple[SourceRow, dict[str, Any], VerifiedStoredFileContent]:
        actor, source = self._source(db, actor, draft_id, source_id, lock=True)
        self._file(db, source)
        try:
            content = read_clean_stored_file_for_update(
                db,
                stored_file_id=source.stored_file_id,
                storage_root=storage_root,
                required_purpose=self.policy.purpose,
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
                or document["schema"] != self.policy.schema
                or document["manifest"]["source_sha256"] != content.sha256
                or document["manifest"]["source_size_bytes"] != content.size_bytes
                or not self.policy.valid_document(document)
            ):
                raise ValueError("binding")
            # An expired signature database requires a fresh scan before active viewing/review.
            database_date = datetime.fromisoformat(scan["database_date"])
            if (
                datetime.now(UTC) - database_date
            ).total_seconds() > malware_scan.MAX_DATABASE_AGE_DAYS * 86400:
                raise DraftScopeError(self.policy.code_prefix + "SCAN_EXPIRED", 409)
        except (StoredFileBindingError, ValueError, TypeError, KeyError, UnicodeError) as exc:
            if isinstance(exc, DraftScopeError):
                raise
            raise DraftScopeError(self.policy.code_prefix + "SOURCE_NOT_READY", 409) from exc
        self._actor(db, actor)
        get_draft(db, actor, draft_id)
        return source, cast(dict[str, Any], document), content
