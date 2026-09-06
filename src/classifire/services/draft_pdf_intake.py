"""Draft PDF upload, genuine scan, retained-page review and explicit Scope revision."""

from __future__ import annotations

import hashlib
import hmac
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
    _valid_hash,
    get_draft,
    read_revision,
    validate_payload,
)
from .draft_scope_evidence import (
    MAX_EVIDENCE_REFS,
    TARGET_COLLECTIONS,
    observation_hash,
    reference_changed,
    reference_identity,
    reference_label,
)
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


def preview_scope_page(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    page_number: int,
    payload: dict[str, Any],
    targets: list[dict[str, str]],
    expected_document_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """No-write preview of explicit human page links and the complete edited graph."""
    with db.no_autoflush:
        actor = _actor(db, actor, "project:write")
        current = read_revision(db, actor, draft_id)
        if type(expected_revision) is not int or expected_revision != current["revision"]:
            raise DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
        source, document, content = _document(db, actor, draft_id, source_id, settings.storage_root)
        if source.document_sha256 != expected_document_hash:
            raise DraftScopeError("PDF_REVIEW_SOURCE_CHANGED", 409)
        if type(page_number) is not int or not 1 <= page_number <= len(document["pages"]):
            raise DraftScopeError("PDF_PAGE_NOT_FOUND", 404)
        page = document["pages"][page_number - 1]
        if page["page_number"] != page_number:
            raise DraftScopeError("PDF_REVIEW_SOURCE_CHANGED", 409)
        model, findings = validate_payload(payload)
        normalized = model.model_dump(mode="json")
        if type(targets) is not list or not 1 <= len(targets) <= MAX_EVIDENCE_REFS:
            raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
        identities: set[tuple[str, str]] = set()
        selected = []
        for target in targets:
            if (
                type(target) is not dict
                or set(target) != {"target_kind", "target_id"}
                or type(target["target_kind"]) is not str
                or target["target_kind"] not in TARGET_COLLECTIONS
                or type(target["target_id"]) is not str
            ):
                raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
            identity = (target["target_kind"], target["target_id"])
            collection = normalized[TARGET_COLLECTIONS[identity[0]]]
            item = next((item for item in collection if item["id"] == identity[1]), None)
            if item is None or identity in identities:
                raise DraftScopeError("PDF_REVIEW_TARGETS_INVALID")
            identities.add(identity)
            selected.append(dict(target))
        selected.sort(key=lambda item: (item["target_kind"], item["target_id"]))
        old_observations = {item["id"] for item in normalized["observations"]}
        existing = {
            reference_identity(ref)
            for ref in current.get("evidence_refs", [])
            if "target_kind" in ref or ref["observation_id"] in old_observations
        }
        existing.update((kind, identity, source.id, page_number) for kind, identity in identities)
        if len(existing) > MAX_EVIDENCE_REFS:
            raise DraftScopeError("PDF_REVIEW_REFERENCE_LIMIT")
        binding = {
            "schema": "CLASSIFIRE-DRAFT-PDF-SCOPE-REVIEW-v1",
            "actor_id": actor.id,
            "draft_id": draft_id,
            "current_hash": current["sha256"],
            "expected_revision": expected_revision,
            "payload": normalized,
            "targets": selected,
            "source_id": source.id,
            "source_sha256": content.sha256,
            "source_size_bytes": content.size_bytes,
            "original_filename": source.original_filename,
            "document_hash": source.document_sha256,
            "scan_sha256": hashlib.sha256(cast(str, source.scan_json).encode("utf-8")).hexdigest(),
            "page": page_number,
            "locator_key": page["locator_key"],
            "page_text_sha256": page["page_text_sha256"],
        }
        _actor(db, actor, "project:write")
        get_draft(db, actor, draft_id)
        return binding | {
            "review_sha256": hashlib.sha256(_json(binding)).hexdigest(),
            "findings": findings,
            "target_labels": [reference_label(target, normalized) for target in selected],
        }


def save_scope_page(
    db: Session,
    actor: User,
    draft_id: str,
    source_id: str,
    expected_revision: int,
    page_number: int,
    payload: dict[str, Any],
    targets: list[dict[str, str]],
    expected_document_hash: str,
    expected_review_hash: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Recheck exact preview inputs under source locks and append one Draft revision."""
    preview = preview_scope_page(
        db,
        actor,
        draft_id,
        source_id,
        expected_revision,
        page_number,
        payload,
        targets,
        expected_document_hash,
        settings=settings,
    )
    if not _valid_hash(expected_review_hash) or not hmac.compare_digest(
        preview["review_sha256"], expected_review_hash
    ):
        raise DraftScopeError("PDF_REVIEW_PREVIEW_CHANGED", 409)
    reviewed_at = datetime.now(UTC).isoformat()
    refs = []
    for target in preview["targets"]:
        item = next(
            item
            for item in preview["payload"][TARGET_COLLECTIONS[target["target_kind"]]]
            if item["id"] == target["target_id"]
        )
        refs.append(
            dict(target)
            | {
                "target_sha256": observation_hash(item),
                "source_id": preview["source_id"],
                "source_sha256": preview["source_sha256"],
                "source_size_bytes": preview["source_size_bytes"],
                "original_filename": preview["original_filename"],
                "page_number": page_number,
                "locator_key": preview["locator_key"],
                "page_text_sha256": preview["page_text_sha256"],
                "document_sha256": preview["document_hash"],
                "scan_sha256": preview["scan_sha256"],
                "reviewed_by": actor.id,
                "reviewed_at": reviewed_at,
                "method": "human_page_entity_review",
                "origin": "local_retained",
            }
        )
    return _append_revision(
        db, actor, draft_id, expected_revision, preview["payload"], entity_evidence_refs=refs
    )


def scope_evidence_staleness(
    db: Session, actor: User, draft_id: str, scope: dict[str, Any], *, storage_root: Path | None
) -> list[str]:
    refs = scope.get("evidence_refs", [])
    if not refs:
        return []
    reasons = []
    for ref in refs:
        if ref["origin"] != "local_retained":
            reasons.append("SCOPE_SOURCE_UNVERIFIED")
            continue
        if reference_changed(ref, scope["content"]):
            reasons.append(
                "SCOPE_WORKBOOK_REVIEW_CHANGED"
                if ref.get("source_kind") == "xlsx"
                else "SCOPE_PAGE_REVIEW_CHANGED"
            )
        if storage_root is None:
            reasons.append("SCOPE_SOURCE_CHECK_UNAVAILABLE")
            continue
        try:
            # Use only the caller-supplied retained root, never ambient application settings.
            if ref.get("source_kind") == "xlsx":
                from .draft_scope_xlsx import intake as workbook_intake

                source, _document_value, content = workbook_intake()._document(
                    db, actor, draft_id, ref["source_id"], storage_root
                )
            else:
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
