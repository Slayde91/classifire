"""Draft PDF upload, genuine scan, retained-page review and explicit Scope revision."""

from __future__ import annotations

import hashlib
import json
import os

# Fixed parser subprocess only; no shell and no content in command arguments.
import subprocess  # nosec B404
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftPdfSource, StoredFile, User, new_id
from . import malware_scan as malware_scan
from .draft_scope import (
    DraftScopeError,
    _actor,
    _append_revision,
    _json,
    get_draft,
    read_revision,
)
from .draft_scope_evidence import observation_hash
from .draft_source_intake import DraftSourceIntake, SourcePolicy
from .storage import (
    VerifiedStoredFileContent,
)

PURPOSE = "draft_scope_pdf"
MAX_SOURCES = 20
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_BYTES = 4 * 1024 * 1024


def _intake() -> DraftSourceIntake:
    return DraftSourceIntake(
        SourcePolicy(
            model=DraftPdfSource,
            purpose=PURPOSE,
            extension=".pdf",
            magic=b"%PDF-",
            media_type="application/pdf",
            schema="CLASSIFIRE-DRAFT-PDF-v1",
            code_prefix="PDF_",
            audit_name="draft_pdf",
            process=_process,
            valid_document=lambda document: 1 <= len(document["pages"]) <= 50,
        )
    )


def _postgres(db: Session) -> None:
    _intake()._postgres(db)


def _source(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    *,
    write: bool = False,
    lock: bool = False,
) -> tuple[User, DraftPdfSource]:
    user, source = _intake()._source(db, actor, draft_id, source_id, write=write, lock=lock)
    return user, cast(DraftPdfSource, source)


def _file(db: Session, source: DraftPdfSource) -> StoredFile:
    return _intake()._file(db, source)


def list_sources(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    return _intake().list_sources(db, actor, draft_id)


def source_info(db: Session, actor: User, draft_id: str, source_id: str) -> dict[str, Any]:
    return _intake().source_info(db, actor, draft_id, source_id)


def retain_pdf(
    db: Session, actor: User, draft_id: str, filename: str, content: bytes, *, settings: Settings
) -> DraftPdfSource:
    return cast(
        DraftPdfSource, _intake().retain(db, actor, draft_id, filename, content, settings=settings)
    )


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
    return _intake().scan_source(db, actor, draft_id, source_id, settings=settings)


def _document(
    db: Session, actor: User, draft_id: str, source_id: str, storage_root: Path
) -> tuple[DraftPdfSource, dict[str, Any], VerifiedStoredFileContent]:
    source, document, content = _intake()._document(db, actor, draft_id, source_id, storage_root)
    return cast(DraftPdfSource, source), document, content


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
