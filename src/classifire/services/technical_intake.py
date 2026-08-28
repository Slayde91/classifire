"""Shared, fail-closed intake for immutable technical source documents."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from fastapi import UploadFile
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalIntakeBatch,
    TechnicalIntakeBatchItem,
    User,
)
from .malware_scanning import MalwareScanError
from .storage import (
    StoredFileSecurityError,
    StoredUpload,
    cleanup_uncommitted_upload,
    save_verified_upload,
)
from .technical_document_lineage import (
    TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES,
    TechnicalDocumentLineageError,
    create_technical_document_relationship,
)
from .technical_document_metadata import (
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
    TechnicalDocumentMetadataError,
    normalize_technical_source_registration,
)
from .technical_document_review import TECHNICAL_DOCUMENT_REVIEW_POLICY

if TYPE_CHECKING:
    from .technical_intake_batch import TechnicalIntakeBatchClaim

TECHNICAL_DOCUMENT_TYPE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("fire_test_report", "Full Fire Test Report"),
    ("regulatory_information_report", "Regulatory Information Report"),
    ("fire_assessment", "Fire Assessment Report"),
    ("extended_application_report", "Extended Application Report"),
    ("field_of_application_report", "Field of Application Report"),
    (
        "fire_engineering_report_performance_solution",
        "Fire Engineering Report or Performance Solution",
    ),
    (
        "certificate_summary_of_assessment",
        "Certificate or Summary of Assessment",
    ),
    ("test_certificate", "Test Certificate"),
)
TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "engineering_assessment": "Engineering Assessment (legacy)",
    "manufacturer_manual": "Manufacturer Manual (legacy)",
    "technical_data_sheet": "Technical Data Sheet (legacy)",
}
TECHNICAL_DOCUMENT_TYPE_LABELS: dict[str, str] = {
    **dict(TECHNICAL_DOCUMENT_TYPE_OPTIONS),
    **TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS,
}
# Legacy values remain accepted so retained registrations and open v1 batches
# can be replayed without rewriting their immutable identity snapshots. They are
# intentionally omitted from the new-upload options presented in the UI.
TECHNICAL_DOCUMENT_TYPES = frozenset(TECHNICAL_DOCUMENT_TYPE_LABELS)
_ACCEPTED_ITEM_RECEIPT_FIELDS = frozenset(
    {
        "artifact_provenance_status",
        "batch_id",
        "declared_source_role",
        "document_id",
        "document_type",
        "evidence_scope",
        "exact_content_duplicate_document_ids",
        "extraction_status",
        "file_sha256",
        "http_status",
        "id",
        "item_id",
        "malware_scan_status",
        "ok",
        "relationship",
        "schema",
        "status",
        "status_url",
    }
)

_ERROR_STATUS = {
    "DOCUMENT_ID_ALREADY_EXISTS": 409,
    "DOCUMENT_ID_INVALID": 422,
    "DOCUMENT_TYPE_INVALID": 422,
    "ARTIFACT_PROVENANCE_INVALID": 422,
    "ARTIFACT_PROVENANCE_NOTE_REQUIRED": 422,
    "EVIDENCE_SCOPE_INVALID": 422,
    "INTAKE_BATCH_ID_INVALID": 422,
    "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN": 503,
    "INTAKE_BATCH_ITEM_CLAIM_INVALID": 409,
    "INTAKE_BATCH_MANIFEST_INVALID": 422,
    "INTAKE_FIELD_INVALID": 422,
    "INTAKE_DATE_INVALID": 422,
    "INTAKE_STANDARDS_INVALID": 422,
    "RELATED_DOCUMENT_ID_INVALID": 422,
    "RELATED_DOCUMENT_NOT_FOUND": 422,
    "RELATIONSHIP_ALREADY_EXISTS": 409,
    "RELATIONSHIP_CYCLE": 409,
    "RELATIONSHIP_EFFECTIVE_DATE_INVALID": 422,
    "RELATIONSHIP_FIELDS_INCOMPLETE": 422,
    "RELATIONSHIP_REASON_INVALID": 422,
    "RELATIONSHIP_SCOPE_INVALID": 422,
    "RELATIONSHIP_SELF_REFERENCE": 422,
    "RELATIONSHIP_TYPE_INVALID": 422,
    "SOURCE_DOCUMENT_NOT_DRAFT": 409,
    "SOURCE_CLASSIFICATION_INVALID": 422,
    "SUMMARY_SOURCE_TARGET_INVALID": 422,
    "SOURCE_METADATA_FIELD_INVALID": 422,
    "SOURCE_ROLE_INVALID": 422,
    "MALWARE_DETECTED": 422,
    "MALWARE_SCAN_INPUT_INVALID": 422,
    "MALWARE_SCANNER_CONFIGURATION_INVALID": 503,
    "MALWARE_SCANNER_ERROR": 503,
    "MALWARE_SCANNER_REQUIRED": 503,
    "MALWARE_SCANNER_RESPONSE_MALFORMED": 503,
    "MALWARE_SCANNER_TIMEOUT": 503,
    "MALWARE_SCANNER_UNAVAILABLE": 503,
    "STORED_FILE_CONTENT_COLLISION": 409,
    "STORED_FILE_CONTEXT_CONFLICT": 409,
    "STORED_FILE_PERSISTENCE_CONFLICT": 503,
    "STORED_FILE_STORAGE_FAILURE": 503,
    "TECHNICAL_INTAKE_AUDIT_FAILURE": 503,
    "TECHNICAL_INTAKE_CONFLICT": 409,
    "UPLOAD_CONTENT_SIGNATURE_INVALID": 422,
    "UPLOAD_FILE_EMPTY": 422,
    "UPLOAD_FILE_TYPE_UNSUPPORTED": 422,
    "UPLOAD_EXPECTED_CONTENT_MISMATCH": 409,
    "UPLOAD_SIZE_LIMIT_EXCEEDED": 413,
    "UPLOAD_STAGED_BYTES_CHANGED": 409,
    "UPLOAD_STREAM_INVALID": 422,
    "UPLOAD_TEMP_CLEANUP_FAILED": 503,
    "UPLOAD_RETENTION_CLEANUP_FAILED": 503,
    "UPLOAD_MULTIPLE_CLEANUP_FAILED": 503,
}

_RETRYABLE_CODES = frozenset(
    {
        "MALWARE_SCANNER_CONFIGURATION_INVALID",
        "MALWARE_SCANNER_ERROR",
        "MALWARE_SCANNER_REQUIRED",
        "MALWARE_SCANNER_RESPONSE_MALFORMED",
        "MALWARE_SCANNER_TIMEOUT",
        "MALWARE_SCANNER_UNAVAILABLE",
        "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN",
        "STORED_FILE_PERSISTENCE_CONFLICT",
        "STORED_FILE_STORAGE_FAILURE",
        "TECHNICAL_INTAKE_AUDIT_FAILURE",
        "UPLOAD_TEMP_CLEANUP_FAILED",
        "UPLOAD_RETENTION_CLEANUP_FAILED",
        "UPLOAD_MULTIPLE_CLEANUP_FAILED",
    }
)

_RETAINED_STORAGE_INTEGRITY_CODES = frozenset(
    {
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "UPLOAD_STAGED_BYTES_CHANGED",
    }
)
_ACCEPTED_REPLAY_EVIDENCE_INTEGRITY_CODES = (
    _RETAINED_STORAGE_INTEGRITY_CODES
    | frozenset(
        {
            "MALWARE_DETECTED",
            "UPLOAD_CONTENT_SIGNATURE_INVALID",
        }
    )
)

_BATCH_FATAL_CODES = frozenset(
    {
        "MALWARE_SCANNER_CONFIGURATION_INVALID",
        "MALWARE_SCANNER_ERROR",
        "MALWARE_SCANNER_REQUIRED",
        "MALWARE_SCANNER_RESPONSE_MALFORMED",
        "MALWARE_SCANNER_TIMEOUT",
        "MALWARE_SCANNER_UNAVAILABLE",
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "STORED_FILE_STORAGE_FAILURE",
        "TECHNICAL_INTAKE_AUDIT_FAILURE",
        "UPLOAD_STAGED_BYTES_CHANGED",
        "UPLOAD_TEMP_CLEANUP_FAILED",
        "UPLOAD_RETENTION_CLEANUP_FAILED",
        "UPLOAD_MULTIPLE_CLEANUP_FAILED",
    }
)


class TechnicalIntakeError(RuntimeError):
    """A stable upload failure suitable for API and UI responses."""

    def __init__(
        self,
        code: str,
        *,
        prior_code: str | None = None,
        fatal: bool | None = None,
        operator_attention: bool | None = None,
    ) -> None:
        if code not in _ERROR_STATUS:
            raise ValueError("Unknown technical intake error code")
        self.code = code
        self.prior_code = prior_code
        self.status_code = _ERROR_STATUS[code]
        self.retryable = code in _RETRYABLE_CODES
        self.fatal = code in _BATCH_FATAL_CODES if fatal is None else fatal
        self.operator_attention = (
            code == "TECHNICAL_INTAKE_AUDIT_FAILURE"
            if operator_attention is None
            else operator_attention
        )
        super().__init__(code)


def _outcome_error(
    code: str,
    *,
    batch_claim: TechnicalIntakeBatchClaim | None,
) -> TechnicalIntakeError:
    accepted_replay_integrity = bool(
        batch_claim is not None
        and batch_claim.accepted_replay
        and code in _ACCEPTED_REPLAY_EVIDENCE_INTEGRITY_CODES
    )
    return TechnicalIntakeError(
        code,
        fatal=True if accepted_replay_integrity else None,
        operator_attention=True if accepted_replay_integrity else None,
    )


@dataclass(frozen=True, slots=True)
class TechnicalIntakeResult:
    document: TechnicalDocument
    stored_file: StoredFile
    correlation_id: str
    relationship: TechnicalDocumentRelationship | None
    exact_content_duplicate_document_ids: tuple[str, ...]
    receipt: dict[str, Any] | None = None
    receipt_sha256: str | None = None
    batch_item_id: str | None = None
    idempotent_replay: bool = False


def _text(
    value: str | None,
    *,
    code: str,
    maximum: int,
    required: bool = False,
) -> str | None:
    normalised = value.strip() if isinstance(value, str) else ""
    if required and not normalised:
        raise TechnicalIntakeError(code)
    if len(normalised) > maximum or any(not character.isprintable() for character in normalised):
        raise TechnicalIntakeError(code)
    return normalised or None


def _multiline_text(
    value: str | None,
    *,
    code: str,
    maximum: int,
) -> str | None:
    normalised = (
        value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if isinstance(value, str)
        else ""
    )
    if len(normalised) > maximum or any(
        not character.isprintable() and character not in {"\r", "\n", "\t"}
        for character in normalised
    ):
        raise TechnicalIntakeError(code)
    return normalised or None


def _correlation_id(value: str | None) -> str:
    if value is None or not value.strip():
        return str(uuid4())
    try:
        return str(UUID(value.strip()))
    except (ValueError, AttributeError):
        raise TechnicalIntakeError("INTAKE_BATCH_ID_INVALID") from None


def _optional_iso_date(value: str | None) -> date | None:
    normalised = _text(value, code="INTAKE_DATE_INVALID", maximum=10)
    if normalised is None:
        return None
    try:
        parsed = date.fromisoformat(normalised)
    except ValueError:
        raise TechnicalIntakeError("INTAKE_DATE_INVALID") from None
    if parsed.isoformat() != normalised:
        raise TechnicalIntakeError("INTAKE_DATE_INVALID")
    return parsed


def _standards(value: str | None) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TechnicalIntakeError("INTAKE_STANDARDS_INVALID")
    normalised = value.strip()
    if not normalised:
        return None
    if len(normalised) > 4_000 or any(
        not character.isprintable() and character not in {"\r", "\n", "\t"}
        for character in normalised
    ):
        raise TechnicalIntakeError("INTAKE_STANDARDS_INVALID")
    items: list[str] = []
    seen: set[str] = set()
    for line in normalised.replace(",", "\n").splitlines():
        item = line.strip()
        if not item:
            continue
        if len(item) > 300 or item in seen or len(items) >= 50:
            raise TechnicalIntakeError("INTAKE_STANDARDS_INVALID")
        seen.add(item)
        items.append(item)
    if not items:
        raise TechnicalIntakeError("INTAKE_STANDARDS_INVALID")
    return items


def _best_effort_invalidate(db: Session) -> None:
    try:
        db.invalidate()
    except Exception:
        # The rollback failure remains authoritative; invalidation cannot
        # safely replace it with a second operational error.
        return


def _receipt_sha256(receipt: dict[str, Any]) -> str:
    encoded = json.dumps(
        receipt,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _batch_item_for_claim(
    db: Session,
    *,
    actor: User,
    claim: TechnicalIntakeBatchClaim,
) -> TechnicalIntakeBatchItem:
    item = db.scalar(
        select(TechnicalIntakeBatchItem)
        .join(
            TechnicalIntakeBatch,
            TechnicalIntakeBatch.id == TechnicalIntakeBatchItem.batch_id,
        )
        .where(
            TechnicalIntakeBatchItem.id == claim.item_id,
            TechnicalIntakeBatchItem.batch_id == claim.batch_id,
            TechnicalIntakeBatch.created_by_id == actor.id,
        )
        .execution_options(populate_existing=True)
    )
    if item is None or (
        item.registration_sha256 != claim.registration_sha256
        or item.expected_sha256 != claim.expected_sha256
        or item.declared_size_bytes != claim.expected_size_bytes
        or item.original_filename != claim.original_filename
    ):
        raise TechnicalIntakeError("INTAKE_BATCH_ITEM_CLAIM_INVALID")
    if claim.accepted_replay:
        if item.status != "accepted" or item.attempt_token is not None:
            raise TechnicalIntakeError("INTAKE_BATCH_ITEM_CLAIM_INVALID")
    elif (
        item.status != "processing"
        or claim.attempt_token is None
        or item.attempt_token != claim.attempt_token
    ):
        raise TechnicalIntakeError("INTAKE_BATCH_ITEM_CLAIM_INVALID")
    return item


@dataclass(frozen=True, slots=True)
class _SharedMalwareContainmentResult:
    matched_stored_file: bool = False
    transitioned_item_count: int = 0
    affected_batch_count: int = 0


@dataclass(frozen=True, slots=True)
class _SharedMalwareItemDisposition:
    outcome_code: str
    document_references_malware_file: bool
    retained_sha_references_malware_bytes: bool
    expected_sha_matches_malware_bytes: bool
    declared_size_matches_malware_bytes: bool


_SHARED_MALWARE_CONTAINMENT_REASON = (
    'Exact scanner-bound malware verdict contained across all retained byte references'
)


def _canonical_malware_binding(
    sha256: str | None,
    size_bytes: int | None,
) -> tuple[str, int] | None:
    if (
        not isinstance(sha256, str)
        or len(sha256) != 64
        or not sha256.isascii()
        or sha256 != sha256.lower()
        or any(character not in '0123456789abcdef' for character in sha256)
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
    ):
        return None
    return sha256, size_bytes


def _lock_shared_malware_rows(
    db: Session,
    *,
    sha256: str,
    size_bytes: int,
) -> tuple[
    StoredFile,
    tuple[TechnicalDocument, ...],
    tuple[TechnicalIntakeBatch, ...],
    tuple[TechnicalIntakeBatchItem, ...],
] | None:
    stored_file = db.scalar(
        select(StoredFile)
        .where(
            StoredFile.sha256 == sha256,
            StoredFile.size_bytes == size_bytes,
        )
        .order_by(StoredFile.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if stored_file is None:
        return None

    documents = tuple(
        db.scalars(
            select(TechnicalDocument)
            .where(TechnicalDocument.stored_file_id == stored_file.id)
            .order_by(TechnicalDocument.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    linked_document_ids = tuple(document.id for document in documents)
    linked_item_condition = (
        TechnicalIntakeBatchItem.retained_file_sha256 == stored_file.sha256
    ) | TechnicalIntakeBatchItem.technical_document_id.in_(
        linked_document_ids
    )
    batch_ids = tuple(
        db.scalars(
            select(TechnicalIntakeBatchItem.batch_id)
            .where(
                TechnicalIntakeBatchItem.status == 'accepted',
                linked_item_condition,
            )
            .distinct()
            .order_by(TechnicalIntakeBatchItem.batch_id)
        ).all()
    )

    batches: tuple[TechnicalIntakeBatch, ...] = ()
    items: tuple[TechnicalIntakeBatchItem, ...] = ()
    if batch_ids:
        batches = tuple(
            db.scalars(
                select(TechnicalIntakeBatch)
                .where(TechnicalIntakeBatch.id.in_(batch_ids))
                .order_by(TechnicalIntakeBatch.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            ).all()
        )
        if tuple(batch.id for batch in batches) != batch_ids:
            raise TechnicalIntakeError(
                'INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN',
                prior_code='MALWARE_DETECTED',
            )
        items = tuple(
            db.scalars(
                select(TechnicalIntakeBatchItem)
                .where(
                    TechnicalIntakeBatchItem.status == 'accepted',
                    linked_item_condition,
                )
                .order_by(
                    TechnicalIntakeBatchItem.batch_id,
                    TechnicalIntakeBatchItem.id,
                )
                .with_for_update(of=TechnicalIntakeBatchItem)
                .execution_options(populate_existing=True)
            ).all()
        )
    return stored_file, documents, batches, items


def _shared_malware_item_dispositions(
    *,
    stored_file: StoredFile,
    documents: tuple[TechnicalDocument, ...],
    batches: tuple[TechnicalIntakeBatch, ...],
    items: tuple[TechnicalIntakeBatchItem, ...],
) -> dict[str, _SharedMalwareItemDisposition]:
    target_document_ids = {
        document.id
        for document in documents
        if document.stored_file_id == stored_file.id
    }
    batch_ids = {batch.id for batch in batches}
    dispositions: dict[str, _SharedMalwareItemDisposition] = {}
    for item in items:
        document_matches = item.technical_document_id in target_document_ids
        retained_sha_matches = (
            item.retained_file_sha256 == stored_file.sha256
        )
        expected_sha_matches = item.expected_sha256 == stored_file.sha256
        size_matches = item.declared_size_bytes == stored_file.size_bytes
        if item.batch_id not in batch_ids or not (
            document_matches or retained_sha_matches
        ):
            raise TechnicalIntakeError(
                'INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN',
                prior_code='MALWARE_DETECTED',
            )
        fully_bound = (
            document_matches
            and retained_sha_matches
            and expected_sha_matches
            and size_matches
        )
        dispositions[item.id] = _SharedMalwareItemDisposition(
            outcome_code=(
                'MALWARE_DETECTED'
                if fully_bound
                else 'STORED_FILE_CONTEXT_CONFLICT'
            ),
            document_references_malware_file=document_matches,
            retained_sha_references_malware_bytes=retained_sha_matches,
            expected_sha_matches_malware_bytes=expected_sha_matches,
            declared_size_matches_malware_bytes=size_matches,
        )
    return dispositions


def _malware_attention_receipt(
    item: TechnicalIntakeBatchItem,
    *,
    outcome_code: str,
) -> dict[str, object]:
    return {
        'schema': 'technical-intake-item-receipt-v1',
        'ok': False,
        'batch_id': item.batch_id,
        'item_id': item.id,
        'code': outcome_code,
        'http_status': _ERROR_STATUS[outcome_code],
        'retryable': False,
        'operator_attention': True,
        'expected_sha256': item.expected_sha256,
        'expected_size_bytes': item.declared_size_bytes,
    }


def _transition_shared_malware_item(
    db: Session,
    *,
    actor: User,
    item: TechnicalIntakeBatchItem,
    disposition: _SharedMalwareItemDisposition,
    now: datetime,
    source_ip: str | None,
    correlation_id: str | None,
) -> None:
    previous_value = {
        'batch_id': item.batch_id,
        'batch_item_id': item.id,
        'status': item.status,
        'outcome_code': item.outcome_code,
        'outcome_retryable': item.outcome_retryable,
        'technical_document_id': item.technical_document_id,
        'retained_file_sha256': item.retained_file_sha256,
        'expected_sha256': item.expected_sha256,
        'declared_size_bytes': item.declared_size_bytes,
        'receipt_schema': item.receipt_schema,
        'receipt': deepcopy(item.receipt_json),
        'receipt_sha256': item.receipt_sha256,
        'record_version': item.record_version,
        'last_outcome_at': _utc_iso(item.last_outcome_at),
    }
    receipt = _malware_attention_receipt(
        item,
        outcome_code=disposition.outcome_code,
    )
    item.status = 'needs_attention'
    item.outcome_code = disposition.outcome_code
    item.outcome_retryable = False
    item.last_outcome_at = now
    item.receipt_schema = 'technical-intake-item-receipt-v1'
    item.receipt_json = receipt
    item.receipt_sha256 = _receipt_sha256(receipt)
    item.record_version += 1
    record_audit(
        db,
        actor=actor,
        action='shared_malware_containment',
        entity_type='technical_intake_batch_item',
        entity_id=item.id,
        previous_value=previous_value,
        new_value={
            'batch_id': item.batch_id,
            'batch_item_id': item.id,
            'status': item.status,
            'outcome_code': item.outcome_code,
            'outcome_retryable': item.outcome_retryable,
            'technical_document_id': item.technical_document_id,
            'retained_file_sha256': item.retained_file_sha256,
            'expected_sha256': item.expected_sha256,
            'declared_size_bytes': item.declared_size_bytes,
            'receipt_schema': item.receipt_schema,
            'receipt': receipt,
            'receipt_sha256': item.receipt_sha256,
            'record_version': item.record_version,
            'last_outcome_at': _utc_iso(item.last_outcome_at),
            'binding_evaluation': {
                'document_references_malware_file': (
                    disposition.document_references_malware_file
                ),
                'retained_sha_references_malware_bytes': (
                    disposition.retained_sha_references_malware_bytes
                ),
                'expected_sha_matches_malware_bytes': (
                    disposition.expected_sha_matches_malware_bytes
                ),
                'declared_size_matches_malware_bytes': (
                    disposition.declared_size_matches_malware_bytes
                ),
            },
        },
        reason=_SHARED_MALWARE_CONTAINMENT_REASON,
        source_ip=source_ip,
        correlation_id=correlation_id,
    )


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _transition_shared_malware_batch(
    db: Session,
    *,
    actor: User,
    batch: TechnicalIntakeBatch,
    transitioned_item_count: int,
    source_ip: str | None,
    correlation_id: str | None,
) -> None:
    previous_value = {
        'status': batch.status,
        'completed_at': _utc_iso(batch.completed_at),
        'record_version': batch.record_version,
    }
    state_changed = (
        batch.status != 'needs_attention' or batch.completed_at is not None
    )
    if state_changed:
        batch.status = 'needs_attention'
        batch.completed_at = None
        batch.record_version += 1
    record_audit(
        db,
        actor=actor,
        action='shared_malware_containment',
        entity_type='technical_intake_batch',
        entity_id=batch.id,
        previous_value=previous_value,
        new_value={
            'status': batch.status,
            'completed_at': _utc_iso(batch.completed_at),
            'record_version': batch.record_version,
            'state_changed': state_changed,
            'transitioned_item_count': transitioned_item_count,
        },
        reason=_SHARED_MALWARE_CONTAINMENT_REASON,
        source_ip=source_ip,
        correlation_id=correlation_id,
    )


def _audit_shared_malware_stored_file(
    db: Session,
    *,
    actor: User,
    stored_file: StoredFile,
    previous_status: str,
    previous_record_version: int,
    state_changed: bool,
    transitioned_item_count: int,
    affected_batch_count: int,
    source_ip: str | None,
    correlation_id: str | None,
) -> None:
    record_audit(
        db,
        actor=actor,
        action='shared_malware_containment',
        entity_type='stored_file',
        entity_id=stored_file.id,
        previous_value={
            'malware_scan_status': previous_status,
            'record_version': previous_record_version,
            'sha256': stored_file.sha256,
            'size_bytes': stored_file.size_bytes,
        },
        new_value={
            'affected_batch_count': affected_batch_count,
            'malware_scan_status': stored_file.malware_scan_status,
            'record_version': stored_file.record_version,
            'sha256': stored_file.sha256,
            'size_bytes': stored_file.size_bytes,
            'state_changed': state_changed,
            'transitioned_item_count': transitioned_item_count,
        },
        reason=_SHARED_MALWARE_CONTAINMENT_REASON,
        source_ip=source_ip,
        correlation_id=correlation_id,
    )


def _apply_shared_malware_transitions(
    db: Session,
    *,
    actor: User,
    stored_file: StoredFile,
    documents: tuple[TechnicalDocument, ...],
    batches: tuple[TechnicalIntakeBatch, ...],
    items: tuple[TechnicalIntakeBatchItem, ...],
    source_ip: str | None,
    correlation_id: str | None,
) -> _SharedMalwareContainmentResult:
    dispositions = _shared_malware_item_dispositions(
        stored_file=stored_file,
        documents=documents,
        batches=batches,
        items=items,
    )
    previous_status = stored_file.malware_scan_status
    previous_record_version = stored_file.record_version
    stored_file_changed = previous_status != 'quarantined'
    if stored_file_changed:
        stored_file.malware_scan_status = 'quarantined'
        stored_file.record_version += 1

    now = datetime.now(UTC)
    transitioned_by_batch: dict[str, int] = {}
    for item in items:
        _transition_shared_malware_item(
            db,
            actor=actor,
            item=item,
            disposition=dispositions[item.id],
            now=now,
            source_ip=source_ip,
            correlation_id=correlation_id,
        )
        transitioned_by_batch[item.batch_id] = (
            transitioned_by_batch.get(item.batch_id, 0) + 1
        )
    for batch in batches:
        _transition_shared_malware_batch(
            db,
            actor=actor,
            batch=batch,
            transitioned_item_count=transitioned_by_batch.get(batch.id, 0),
            source_ip=source_ip,
            correlation_id=correlation_id,
        )
    _audit_shared_malware_stored_file(
        db,
        actor=actor,
        stored_file=stored_file,
        previous_status=previous_status,
        previous_record_version=previous_record_version,
        state_changed=stored_file_changed,
        transitioned_item_count=len(items),
        affected_batch_count=len(batches),
        source_ip=source_ip,
        correlation_id=correlation_id,
    )
    return _SharedMalwareContainmentResult(
        matched_stored_file=True,
        transitioned_item_count=len(items),
        affected_batch_count=len(batches),
    )


def _contain_shared_malware_bytes(
    db: Session,
    *,
    actor: User,
    content_sha256: str | None,
    content_size_bytes: int | None,
    source_ip: str | None,
    correlation_id: str | None,
    batch_claim: TechnicalIntakeBatchClaim | None,
) -> _SharedMalwareContainmentResult:
    binding = _canonical_malware_binding(content_sha256, content_size_bytes)
    if binding is None:
        return _SharedMalwareContainmentResult()
    sha256, size_bytes = binding
    if batch_claim is not None and (
        batch_claim.expected_sha256 != sha256
        or batch_claim.expected_size_bytes != size_bytes
    ):
        return _SharedMalwareContainmentResult()
    locked_rows = _lock_shared_malware_rows(
        db,
        sha256=sha256,
        size_bytes=size_bytes,
    )
    if locked_rows is None:
        return _SharedMalwareContainmentResult()
    stored_file, documents, batches, items = locked_rows
    return _apply_shared_malware_transitions(
        db,
        actor=actor,
        stored_file=stored_file,
        documents=documents,
        batches=batches,
        items=items,
        source_ip=source_ip,
        correlation_id=correlation_id,
    )


def _record_batch_item_rejection(
    db: Session,
    *,
    actor: User,
    claim: TechnicalIntakeBatchClaim,
    code: str,
) -> tuple[bool, dict[str, object] | None]:
    if claim.accepted_replay:
        if code == "MALWARE_DETECTED":
            # Shared-byte containment owns all malware-driven demotions.
            return False, None
        if code not in _ACCEPTED_REPLAY_EVIDENCE_INTEGRITY_CODES:
            return False, None
    elif claim.attempt_token is None:
        return False, None
    if claim.accepted_replay:
        locked_batch = db.scalar(
            select(TechnicalIntakeBatch)
            .where(
                TechnicalIntakeBatch.id == claim.batch_id,
                TechnicalIntakeBatch.created_by_id == actor.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if locked_batch is None:
            return False, None
    item = db.scalar(
        select(TechnicalIntakeBatchItem)
        .join(
            TechnicalIntakeBatch,
            TechnicalIntakeBatch.id == TechnicalIntakeBatchItem.batch_id,
        )
        .where(
            TechnicalIntakeBatchItem.id == claim.item_id,
            TechnicalIntakeBatchItem.batch_id == claim.batch_id,
            TechnicalIntakeBatch.created_by_id == actor.id,
        )
        .with_for_update(of=TechnicalIntakeBatchItem)
        .execution_options(populate_existing=True)
    )
    if item is None:
        return False, None
    previous_value: dict[str, object] | None = None
    if claim.accepted_replay:
        if (
            item.status != "accepted"
            or item.attempt_token is not None
            or item.attempt_started_at is not None
            or item.registration_sha256 != claim.registration_sha256
            or item.expected_sha256 != claim.expected_sha256
            or item.declared_size_bytes != claim.expected_size_bytes
            or item.original_filename != claim.original_filename
            or item.outcome_code != "ACCEPTED"
            or item.outcome_retryable is not False
        ):
            return False, None
        now = datetime.now(UTC)
        receipt = {
            "schema": "technical-intake-item-receipt-v1",
            "ok": False,
            "batch_id": claim.batch_id,
            "item_id": claim.item_id,
            "code": code,
            "http_status": _ERROR_STATUS[code],
            "retryable": False,
            "operator_attention": True,
            "expected_sha256": claim.expected_sha256,
            "expected_size_bytes": claim.expected_size_bytes,
        }
        accepted_receipt = deepcopy(item.receipt_json)
        accepted_receipt_sha256 = item.receipt_sha256
        accepted_document_id = item.technical_document_id
        accepted_file_sha256 = item.retained_file_sha256
        resolved = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "accepted",
                TechnicalIntakeBatchItem.record_version == item.record_version,
                TechnicalIntakeBatchItem.technical_document_id
                == accepted_document_id,
                TechnicalIntakeBatchItem.retained_file_sha256
                == accepted_file_sha256,
                TechnicalIntakeBatchItem.receipt_sha256
                == accepted_receipt_sha256,
            )
            .values(
                status="needs_attention",
                outcome_code=code,
                outcome_retryable=False,
                last_outcome_at=now,
                receipt_schema="technical-intake-item-receipt-v1",
                receipt_json=receipt,
                receipt_sha256=_receipt_sha256(receipt),
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        transitioned = getattr(resolved, "rowcount", 0) == 1
        if transitioned:
            previous_value = {
                "batch_id": claim.batch_id,
                "batch_item_id": item.id,
                "status": "accepted",
                "outcome_code": "ACCEPTED",
                "outcome_retryable": False,
                "technical_document_id": accepted_document_id,
                "retained_file_sha256": accepted_file_sha256,
                "receipt_schema": item.receipt_schema,
                "receipt": accepted_receipt,
                "receipt_sha256": accepted_receipt_sha256,
            }
    elif (
        item.status != "processing"
        or item.attempt_token != claim.attempt_token
    ):
        return False, None
    elif code == "UPLOAD_EXPECTED_CONTENT_MISMATCH":
        restored_status = "rejected" if claim.prior_status == "rejected" else "pending"
        restored = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "processing",
                TechnicalIntakeBatchItem.attempt_token == claim.attempt_token,
                TechnicalIntakeBatchItem.record_version == item.record_version,
            )
            .values(
                status=restored_status,
                attempt_token=None,
                attempt_started_at=None,
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        transitioned = getattr(restored, "rowcount", 0) == 1
    else:
        now = datetime.now(UTC)
        needs_attention = code in _RETAINED_STORAGE_INTEGRITY_CODES or code in {
            "TECHNICAL_INTAKE_AUDIT_FAILURE",
            "UPLOAD_MULTIPLE_CLEANUP_FAILED",
            "UPLOAD_RETENTION_CLEANUP_FAILED",
            "UPLOAD_TEMP_CLEANUP_FAILED",
        }
        automatic_retryable = code in _RETRYABLE_CODES and not needs_attention
        receipt = {
            "schema": "technical-intake-item-receipt-v1",
            "ok": False,
            "batch_id": claim.batch_id,
            "item_id": claim.item_id,
            "code": code,
            "http_status": _ERROR_STATUS[code],
            "retryable": automatic_retryable,
            "operator_attention": needs_attention,
            "expected_sha256": claim.expected_sha256,
            "expected_size_bytes": claim.expected_size_bytes,
        }
        resolved = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "processing",
                TechnicalIntakeBatchItem.attempt_token == claim.attempt_token,
                TechnicalIntakeBatchItem.record_version == item.record_version,
            )
            .values(
                status="needs_attention" if needs_attention else "rejected",
                attempt_token=None,
                attempt_started_at=None,
                outcome_code=code,
                outcome_retryable=automatic_retryable,
                last_outcome_at=now,
                receipt_schema="technical-intake-item-receipt-v1",
                receipt_json=receipt,
                receipt_sha256=_receipt_sha256(receipt),
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        transitioned = getattr(resolved, "rowcount", 0) == 1
    if transitioned:
        from .technical_intake_batch import refresh_technical_intake_batch_status

        db.flush()
        refresh_technical_intake_batch_status(db, batch_id=claim.batch_id)
    return transitioned, previous_value


def _record_rejection(
    db: Session,
    *,
    actor: User,
    code: str,
    document_id: str | None,
    filename: str,
    correlation_id: str | None,
    source_ip: str | None,
    prior_outcome: str | None = None,
    cleanup_failures: tuple[str, ...] = (),
    batch_claim: TechnicalIntakeBatchClaim | None = None,
    malware_verdict_code: str | None = None,
    malware_verdict_sha256: str | None = None,
    malware_verdict_size_bytes: int | None = None,
) -> _SharedMalwareContainmentResult:
    try:
        db.rollback()
    except Exception:
        _best_effort_invalidate(db)
        raise TechnicalIntakeError(
            (
                "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN"
                if batch_claim is not None
                else "TECHNICAL_INTAKE_AUDIT_FAILURE"
            ),
            prior_code=code,
        ) from None

    new_value: dict[str, object] = {
        "document_id": document_id,
        "filename": filename,
        "outcome": code,
    }
    previous_value: dict[str, object] | None = None
    if prior_outcome is not None:
        new_value["prior_outcome"] = prior_outcome
    if cleanup_failures:
        new_value["cleanup_failures"] = list(cleanup_failures)
    try:
        containment = _SharedMalwareContainmentResult()
        if malware_verdict_code == "MALWARE_DETECTED":
            containment = _contain_shared_malware_bytes(
                db,
                actor=actor,
                content_sha256=malware_verdict_sha256,
                content_size_bytes=malware_verdict_size_bytes,
                source_ip=source_ip,
                correlation_id=correlation_id,
                batch_claim=batch_claim,
            )
        if containment.matched_stored_file:
            new_value["shared_malware_containment_matched"] = True
            new_value["shared_malware_transitioned_item_count"] = (
                containment.transitioned_item_count
            )
            new_value["shared_malware_affected_batch_count"] = (
                containment.affected_batch_count
            )
            new_value["stored_file_malware_scan_status"] = "quarantined"
        if batch_claim is not None:
            new_value["batch_id"] = batch_claim.batch_id
            new_value["batch_item_id"] = batch_claim.item_id
            transition_recorded, previous_value = _record_batch_item_rejection(
                db,
                actor=actor,
                claim=batch_claim,
                code=code,
            )
            new_value["batch_item_transition_recorded"] = transition_recorded
        record_audit(
            db,
            actor=actor,
            action="upload_rejected",
            entity_type="technical_document",
            entity_id=None,
            previous_value=previous_value,
            new_value=new_value,
            reason="Technical evidence upload rejected by the governed intake boundary",
            source_ip=source_ip,
            correlation_id=correlation_id,
        )
        db.commit()
        return containment
    except Exception:
        try:
            db.rollback()
        except Exception:
            _best_effort_invalidate(db)
        raise TechnicalIntakeError(
            (
                "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN"
                if batch_claim is not None
                else "TECHNICAL_INTAKE_AUDIT_FAILURE"
            ),
            prior_code=code,
        ) from None


def _reject_precommit(
    db: Session,
    *,
    actor: User,
    code: str,
    document_id: str | None,
    filename: str,
    correlation_id: str | None,
    source_ip: str | None,
    stored_upload: StoredUpload | None,
    prior_outcome: str | None = None,
    cleanup_failures: tuple[str, ...] = (),
    batch_claim: TechnicalIntakeBatchClaim | None = None,
    malware_verdict_code: str | None = None,
    malware_verdict_sha256: str | None = None,
    malware_verdict_size_bytes: int | None = None,
) -> str:
    """Compensate before rollback while an uncommitted SHA row excludes winners."""

    cleanup_error = cleanup_uncommitted_upload(stored_upload, prior_code=code)
    if cleanup_error is not None:
        prior_outcome = cleanup_error.prior_code
        cleanup_failures = cleanup_error.cleanup_codes
        code = cleanup_error.code
    containment = _record_rejection(
        db,
        actor=actor,
        code=code,
        document_id=document_id,
        filename=filename,
        correlation_id=correlation_id,
        source_ip=source_ip,
        prior_outcome=prior_outcome,
        cleanup_failures=cleanup_failures,
        batch_claim=batch_claim,
        malware_verdict_code=malware_verdict_code,
        malware_verdict_sha256=malware_verdict_sha256,
        malware_verdict_size_bytes=malware_verdict_size_bytes,
    )
    if (
        malware_verdict_code == "MALWARE_DETECTED"
        and batch_claim is not None
        and batch_claim.accepted_replay
        and not containment.matched_stored_file
    ):
        raise TechnicalIntakeError(
            "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN",
            prior_code="MALWARE_DETECTED",
            fatal=True,
            operator_attention=True,
        )
    return code


def create_technical_document_draft(
    db: Session,
    settings: Settings,
    *,
    actor: User,
    upload: UploadFile,
    document_id: str,
    document_type: str,
    declared_source_role: str,
    artifact_provenance_status: str,
    evidence_scope: str,
    title: str,
    manufacturer: str | None = None,
    sponsor_organisation: str | None = None,
    issuing_organisation: str | None = None,
    reference: str | None = None,
    revision: str | None = None,
    publication_date: str | None = None,
    review_date: str | None = None,
    expiry_date: str | None = None,
    standards: str | None = None,
    jurisdiction: str | None = None,
    artifact_provenance_note: str | None = None,
    evidence_limitations: str | None = None,
    relationship_type: str | None = None,
    related_document_id: str | None = None,
    relationship_reason: str | None = None,
    relationship_scope: str | None = None,
    relationship_effective_date: str | None = None,
    correlation_id: str | None = None,
    source_ip: str | None = None,
    batch_claim: TechnicalIntakeBatchClaim | None = None,
) -> TechnicalIntakeResult:
    """Persist one independently screened Draft source document.

    Extraction is deliberately deferred until an isolated parser boundary is
    available. A clean malware result does not make an in-process parser safe.
    """

    raw_filename = upload.filename or "unnamed"
    safe_filename = (
        raw_filename if batch_claim is not None else Path(raw_filename).name[:500]
    )
    safe_correlation: str | None = None
    safe_document_id: str | None = None
    stored_upload: StoredUpload | None = None
    relationship: TechnicalDocumentRelationship | None = None
    claimed_batch_item: TechnicalIntakeBatchItem | None = None
    exact_content_duplicate_document_ids: tuple[str, ...] = ()
    intake_receipt: dict[str, Any] | None = None
    intake_receipt_sha256: str | None = None
    try:
        safe_correlation = _correlation_id(correlation_id)
        if batch_claim is not None:
            from .technical_intake_batch import (
                TechnicalIntakeBatchError,
                canonical_json_sha256,
                canonical_technical_intake_filename,
                normalize_technical_intake_registration,
            )

            try:
                safe_filename = canonical_technical_intake_filename(
                    raw_filename,
                    code="INTAKE_BATCH_ITEM_CLAIM_INVALID",
                )
                claim_registration = normalize_technical_intake_registration(
                    {
                        "artifact_provenance_note": artifact_provenance_note,
                        "artifact_provenance_status": artifact_provenance_status,
                        "declared_source_role": declared_source_role,
                        "document_id": document_id,
                        "document_type": document_type,
                        "evidence_limitations": evidence_limitations,
                        "evidence_scope": evidence_scope,
                        "expiry_date": expiry_date,
                        "issuing_organisation": issuing_organisation,
                        "jurisdiction": jurisdiction,
                        "manufacturer": manufacturer,
                        "publication_date": publication_date,
                        "reference": reference,
                        "related_document_id": related_document_id,
                        "relationship_effective_date": relationship_effective_date,
                        "relationship_reason": relationship_reason,
                        "relationship_scope": relationship_scope,
                        "relationship_type": relationship_type,
                        "review_date": review_date,
                        "revision": revision,
                        "sponsor_organisation": sponsor_organisation,
                        "standards": standards,
                        "title": title,
                    }
                )
            except TechnicalIntakeBatchError as exc:
                raise TechnicalIntakeError(exc.code) from None
            if (
                safe_correlation != batch_claim.batch_id
                or safe_filename != batch_claim.original_filename
                or canonical_json_sha256(claim_registration)
                != batch_claim.registration_sha256
            ):
                raise TechnicalIntakeError("INTAKE_BATCH_ITEM_CLAIM_INVALID")
        safe_document_id = _text(
            document_id,
            code="DOCUMENT_ID_INVALID",
            maximum=200,
            required=True,
        )
        safe_title = _text(
            title,
            code="INTAKE_FIELD_INVALID",
            maximum=500,
            required=True,
        )
        safe_document_type = _text(
            document_type,
            code="DOCUMENT_TYPE_INVALID",
            maximum=100,
            required=True,
        )
        if safe_document_type not in TECHNICAL_DOCUMENT_TYPES:
            raise TechnicalIntakeError("DOCUMENT_TYPE_INVALID")
        try:
            registration = normalize_technical_source_registration(
                document_type=safe_document_type,
                declared_source_role=declared_source_role,
                sponsor_organisation=sponsor_organisation,
                artifact_provenance_status=artifact_provenance_status,
                artifact_provenance_note=artifact_provenance_note,
                evidence_scope=evidence_scope,
                evidence_limitations=evidence_limitations,
            )
        except TechnicalDocumentMetadataError as exc:
            raise TechnicalIntakeError(exc.code) from None
        safe_manufacturer = _text(
            manufacturer,
            code="INTAKE_FIELD_INVALID",
            maximum=200,
        )
        safe_reference = _text(reference, code="INTAKE_FIELD_INVALID", maximum=300)
        safe_revision = _text(revision, code="INTAKE_FIELD_INVALID", maximum=100)
        safe_issuing_organisation = _text(
            issuing_organisation,
            code="INTAKE_FIELD_INVALID",
            maximum=300,
        )
        safe_publication_date = _optional_iso_date(publication_date)
        safe_review_date = _optional_iso_date(review_date)
        safe_expiry_date = _optional_iso_date(expiry_date)
        safe_standards = _standards(standards)
        safe_jurisdiction = _text(
            jurisdiction,
            code="INTAKE_FIELD_INVALID",
            maximum=200,
        )
        safe_relationship_type = _text(
            relationship_type,
            code="RELATIONSHIP_TYPE_INVALID",
            maximum=50,
        )
        safe_related_document_id = _text(
            related_document_id,
            code="RELATED_DOCUMENT_ID_INVALID",
            maximum=200,
        )
        safe_relationship_reason = _text(
            relationship_reason,
            code="RELATIONSHIP_REASON_INVALID",
            maximum=2000,
        )
        safe_relationship_scope = _multiline_text(
            relationship_scope,
            code="RELATIONSHIP_SCOPE_INVALID",
            maximum=4000,
        )
        safe_relationship_effective_date = _optional_iso_date(
            relationship_effective_date
        )
        relationship_core_values = (
            safe_relationship_type,
            safe_related_document_id,
            safe_relationship_reason,
        )
        if any(relationship_core_values) and not all(relationship_core_values):
            raise TechnicalIntakeError("RELATIONSHIP_FIELDS_INCOMPLETE")
        if (
            safe_relationship_scope is not None
            or safe_relationship_effective_date is not None
        ) and not all(relationship_core_values):
            raise TechnicalIntakeError("RELATIONSHIP_FIELDS_INCOMPLETE")
        if safe_relationship_type is not None:
            if safe_relationship_type not in TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES:
                raise TechnicalIntakeError("RELATIONSHIP_TYPE_INVALID")
            if safe_related_document_id == safe_document_id:
                raise TechnicalIntakeError("RELATIONSHIP_SELF_REFERENCE")
            if not db.scalar(
                select(TechnicalDocument.id).where(
                    TechnicalDocument.document_id == safe_related_document_id
                )
            ):
                raise TechnicalIntakeError("RELATED_DOCUMENT_NOT_FOUND")

        if batch_claim is not None:
            claimed_batch_item = _batch_item_for_claim(
                db,
                actor=actor,
                claim=batch_claim,
            )
            if batch_claim.accepted_replay:
                stored_upload = save_verified_upload(
                    db,
                    settings,
                    upload,
                    purpose="technical_evidence",
                    user=actor,
                    expected_sha256=batch_claim.expected_sha256,
                    expected_size_bytes=batch_claim.expected_size_bytes,
                    manifest_admitted_size_bytes=batch_claim.expected_size_bytes,
                )
                stored = stored_upload.stored_file
                document = (
                    db.get(
                        TechnicalDocument,
                        claimed_batch_item.technical_document_id,
                    )
                    if claimed_batch_item.technical_document_id
                    else None
                )
                receipt = claimed_batch_item.receipt_json
                if (
                    document is None
                    or document.stored_file_id != stored.id
                    or document.document_id
                    != claimed_batch_item.declared_document_id
                    or claimed_batch_item.retained_file_sha256 != stored.sha256
                    or claimed_batch_item.retained_file_sha256
                    != batch_claim.expected_sha256
                    or claimed_batch_item.receipt_schema
                    != "technical-intake-item-receipt-v1"
                    or not isinstance(receipt, dict)
                    or claimed_batch_item.receipt_sha256
                    != _receipt_sha256(receipt)
                ):
                    raise TechnicalIntakeError(
                        "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                    )
                registration_snapshot = claimed_batch_item.registration_snapshot
                if not isinstance(registration_snapshot, dict):
                    raise TechnicalIntakeError(
                        "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                    )
                relationship_type_value = registration_snapshot.get(
                    "relationship_type"
                )
                related_document_id_value = registration_snapshot.get(
                    "related_document_id"
                )
                expected_relationship = (
                    {
                        "relationship_type": relationship_type_value,
                        "related_document_id": related_document_id_value,
                    }
                    if (
                        isinstance(relationship_type_value, str)
                        and isinstance(related_document_id_value, str)
                    )
                    else None
                )
                if (
                    set(receipt) != _ACCEPTED_ITEM_RECEIPT_FIELDS
                    or receipt.get("schema")
                    != "technical-intake-item-receipt-v1"
                    or receipt.get("ok") is not True
                    or receipt.get("http_status") != 201
                    or receipt.get("batch_id") != batch_claim.batch_id
                    or receipt.get("item_id") != batch_claim.item_id
                    or receipt.get("id") != document.id
                    or receipt.get("document_id") != document.document_id
                    or receipt.get("document_type")
                    != registration_snapshot.get("document_type")
                    or receipt.get("declared_source_role")
                    != registration_snapshot.get("declared_source_role")
                    or receipt.get("artifact_provenance_status")
                    != registration_snapshot.get(
                        "artifact_provenance_status"
                    )
                    or receipt.get("evidence_scope")
                    != registration_snapshot.get("evidence_scope")
                    or receipt.get("status") != "draft"
                    or receipt.get("file_sha256") != stored.sha256
                    or receipt.get("malware_scan_status") != "clean"
                    or receipt.get("extraction_status")
                    != "awaiting_safe_extraction"
                    or receipt.get("relationship") != expected_relationship
                    or receipt.get("status_url")
                    != (
                        "/api/v1/technical/upload-batches/"
                        + batch_claim.batch_id
                    )
                ):
                    raise TechnicalIntakeError(
                        "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                    )
                duplicate_values = receipt.get(
                    "exact_content_duplicate_document_ids"
                )
                if (
                    not isinstance(duplicate_values, list)
                    or not all(
                        isinstance(value, str)
                        and value
                        and value.strip() == value
                        and value != document.document_id
                        for value in duplicate_values
                    )
                    or duplicate_values != sorted(set(duplicate_values))
                ):
                    raise TechnicalIntakeError(
                        "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                    )
                relationship = None
                if expected_relationship is not None:
                    related_internal_id = db.scalar(
                        select(TechnicalDocument.id).where(
                            TechnicalDocument.document_id
                            == expected_relationship["related_document_id"]
                        )
                    )
                    if related_internal_id is None:
                        raise TechnicalIntakeError(
                            "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                        )
                    relationship = db.scalar(
                        select(TechnicalDocumentRelationship).where(
                            TechnicalDocumentRelationship.document_id
                            == document.id,
                            TechnicalDocumentRelationship.related_document_id
                            == related_internal_id,
                            TechnicalDocumentRelationship.relationship_type
                            == expected_relationship["relationship_type"],
                        )
                    )
                    if (
                        relationship is None
                        or relationship.reason
                        != registration_snapshot.get("relationship_reason")
                        or relationship.scope
                        != registration_snapshot.get("relationship_scope")
                        or (
                            relationship.effective_date.isoformat()
                            if relationship.effective_date is not None
                            else None
                        )
                        != registration_snapshot.get(
                            "relationship_effective_date"
                        )
                    ):
                        raise TechnicalIntakeError(
                            "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                        )
                return TechnicalIntakeResult(
                    document,
                    stored,
                    batch_claim.batch_id,
                    relationship,
                    tuple(duplicate_values),
                    receipt,
                    claimed_batch_item.receipt_sha256,
                    batch_claim.item_id,
                    True,
                )

        if db.scalar(
            select(TechnicalDocument.id).where(
                TechnicalDocument.document_id == safe_document_id
            )
        ):
            raise TechnicalIntakeError("DOCUMENT_ID_ALREADY_EXISTS")

        stored_upload = save_verified_upload(
            db,
            settings,
            upload,
            purpose="technical_evidence",
            user=actor,
            expected_sha256=(
                batch_claim.expected_sha256
                if batch_claim is not None
                else None
            ),
            expected_size_bytes=(
                batch_claim.expected_size_bytes
                if batch_claim is not None
                else None
            ),
            manifest_admitted_size_bytes=(
                batch_claim.expected_size_bytes
                if batch_claim is not None
                else None
            ),
        )
        stored = stored_upload.stored_file
        exact_content_duplicate_document_ids = tuple(
            db.scalars(
                select(TechnicalDocument.document_id)
                .where(TechnicalDocument.stored_file_id == stored.id)
                .order_by(TechnicalDocument.document_id)
            ).all()
        )
        metadata = {
            "automatic_activation_permitted": False,
            "exact_content_duplicate_document_ids": list(
                exact_content_duplicate_document_ids
            ),
            "extraction_deferred_code": "ISOLATED_PARSER_REQUIRED",
            "human_review_required": True,
            "malware_scan_status": "clean",
            "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
            "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
            "upload_correlation_id": safe_correlation,
            "upload_original_filename": safe_filename,
            "uploaded_by_id": actor.id,
        }
        document = TechnicalDocument(
            document_id=safe_document_id,
            stored_file_id=stored.id,
            document_type=safe_document_type,
            **registration.model_values(),
            manufacturer=safe_manufacturer,
            title=safe_title,
            reference=safe_reference,
            revision=safe_revision,
            issuing_organisation=safe_issuing_organisation,
            publication_date=safe_publication_date,
            review_date=safe_review_date,
            expiry_date=safe_expiry_date,
            standards=safe_standards,
            jurisdiction=safe_jurisdiction or settings.jurisdiction,
            status="draft",
            extraction_status="awaiting_safe_extraction",
            metadata_json=metadata,
        )
        db.add(document)
        db.flush()
        if (
            safe_relationship_type is not None
            and safe_related_document_id is not None
            and safe_relationship_reason is not None
        ):
            relationship = create_technical_document_relationship(
                db,
                actor=actor,
                document=document,
                related_document_id=safe_related_document_id,
                relationship_type=safe_relationship_type,
                reason=safe_relationship_reason,
                scope=safe_relationship_scope,
                effective_date=safe_relationship_effective_date,
                source_ip=source_ip,
                correlation_id=safe_correlation,
            )
        record_audit(
            db,
            actor=actor,
            action="upload",
            entity_type="technical_document",
            entity_id=document.id,
            new_value={
                "document_id": safe_document_id,
                "exact_content_duplicate_document_ids": list(
                    exact_content_duplicate_document_ids
                ),
                "filename": safe_filename,
                "malware_scan_status": stored.malware_scan_status,
                "document_type": safe_document_type,
                "declared_source_role": registration.declared_source_role,
                "artifact_provenance_status": (
                    registration.artifact_provenance_status
                ),
                "evidence_scope": registration.evidence_scope,
                "related_document_id": safe_related_document_id,
                "relationship_type": safe_relationship_type,
                "sha256": stored.sha256,
                "status": "draft",
                "batch_id": (
                    batch_claim.batch_id if batch_claim is not None else None
                ),
                "batch_item_id": (
                    batch_claim.item_id if batch_claim is not None else None
                ),
            },
            reason=(
                "Immutable screened evidence uploaded; extraction remains deferred "
                "and technical content remains Draft"
            ),
            source_ip=source_ip,
            correlation_id=safe_correlation,
        )
        # Flush every statement before commit so failures handled below are
        # known pre-commit outcomes. Only the final commit call is ambiguous.
        db.flush()
        if batch_claim is not None:
            if claimed_batch_item is None or batch_claim.attempt_token is None:
                raise TechnicalIntakeError("INTAKE_BATCH_ITEM_CLAIM_INVALID")
            relationship_receipt: dict[str, str] | None = None
            if relationship is not None:
                related = db.get(
                    TechnicalDocument,
                    relationship.related_document_id,
                )
                if related is None:
                    raise TechnicalIntakeError(
                        "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                    )
                relationship_receipt = {
                    "relationship_type": relationship.relationship_type,
                    "related_document_id": related.document_id,
                }
            intake_receipt = {
                "schema": "technical-intake-item-receipt-v1",
                "ok": True,
                "http_status": 201,
                "batch_id": batch_claim.batch_id,
                "item_id": batch_claim.item_id,
                "id": document.id,
                "document_id": document.document_id,
                "document_type": document.document_type,
                "declared_source_role": document.declared_source_role,
                "artifact_provenance_status": (
                    document.artifact_provenance_status
                ),
                "evidence_scope": document.evidence_scope,
                "status": document.status,
                "file_sha256": stored.sha256,
                "malware_scan_status": stored.malware_scan_status,
                "extraction_status": document.extraction_status,
                "relationship": relationship_receipt,
                "exact_content_duplicate_document_ids": list(
                    exact_content_duplicate_document_ids
                ),
                "status_url": (
                    "/api/v1/technical/upload-batches/"
                    + batch_claim.batch_id
                ),
            }
            intake_receipt_sha256 = _receipt_sha256(intake_receipt)
            accepted = db.execute(
                update(TechnicalIntakeBatchItem)
                .where(
                    TechnicalIntakeBatchItem.id == claimed_batch_item.id,
                    TechnicalIntakeBatchItem.batch_id == batch_claim.batch_id,
                    TechnicalIntakeBatchItem.status == "processing",
                    TechnicalIntakeBatchItem.attempt_token
                    == batch_claim.attempt_token,
                    TechnicalIntakeBatchItem.record_version
                    == claimed_batch_item.record_version,
                )
                .values(
                    status="accepted",
                    attempt_token=None,
                    attempt_started_at=None,
                    technical_document_id=document.id,
                    retained_file_sha256=stored.sha256,
                    outcome_code="ACCEPTED",
                    outcome_retryable=False,
                    last_outcome_at=datetime.now(UTC),
                    receipt_schema="technical-intake-item-receipt-v1",
                    receipt_json=intake_receipt,
                    receipt_sha256=intake_receipt_sha256,
                    record_version=(
                        TechnicalIntakeBatchItem.record_version + 1
                    ),
                )
                .execution_options(synchronize_session=False)
            )
            if getattr(accepted, "rowcount", 0) != 1:
                raise TechnicalIntakeError(
                    "INTAKE_BATCH_ITEM_CLAIM_INVALID"
                )
            from .technical_intake_batch import (
                refresh_technical_intake_batch_status,
            )

            db.flush()
            refresh_technical_intake_batch_status(
                db,
                batch_id=batch_claim.batch_id,
            )
            db.flush()
    except (MalwareScanError, StoredFileSecurityError) as exc:
        outcome = _reject_precommit(
            db,
            actor=actor,
            code=exc.code,
            document_id=safe_document_id,
            filename=safe_filename,
            correlation_id=safe_correlation,
            source_ip=source_ip,
            stored_upload=stored_upload,
            prior_outcome=getattr(exc, "prior_code", None),
            cleanup_failures=getattr(exc, "cleanup_codes", ()),
            batch_claim=batch_claim,
            malware_verdict_code=(
                "MALWARE_DETECTED"
                if (
                    (
                        isinstance(exc, MalwareScanError)
                        and exc.code == "MALWARE_DETECTED"
                    )
                    or (
                        isinstance(exc, StoredFileSecurityError)
                        and exc.prior_code == "MALWARE_DETECTED"
                    )
                )
                else None
            ),
            malware_verdict_sha256=getattr(exc, "content_sha256", None),
            malware_verdict_size_bytes=getattr(
                exc, "content_size_bytes", None
            ),
        )
        raise _outcome_error(outcome, batch_claim=batch_claim) from None
    except TechnicalIntakeError as exc:
        outcome = _reject_precommit(
            db,
            actor=actor,
            code=exc.code,
            document_id=safe_document_id,
            filename=safe_filename,
            correlation_id=safe_correlation,
            source_ip=source_ip,
            stored_upload=stored_upload,
            batch_claim=batch_claim,
        )
        raise _outcome_error(outcome, batch_claim=batch_claim) from None
    except TechnicalDocumentLineageError as exc:
        outcome = _reject_precommit(
            db,
            actor=actor,
            code=exc.code,
            document_id=safe_document_id,
            filename=safe_filename,
            correlation_id=safe_correlation,
            source_ip=source_ip,
            stored_upload=stored_upload,
            batch_claim=batch_claim,
        )
        raise _outcome_error(outcome, batch_claim=batch_claim) from None
    except IntegrityError:
        outcome = _reject_precommit(
            db,
            actor=actor,
            code="TECHNICAL_INTAKE_CONFLICT",
            document_id=safe_document_id,
            filename=safe_filename,
            correlation_id=safe_correlation,
            source_ip=source_ip,
            stored_upload=stored_upload,
            batch_claim=batch_claim,
        )
        raise _outcome_error(outcome, batch_claim=batch_claim) from None
    except SQLAlchemyError:
        outcome = _reject_precommit(
            db,
            actor=actor,
            code="STORED_FILE_PERSISTENCE_CONFLICT",
            document_id=safe_document_id,
            filename=safe_filename,
            correlation_id=safe_correlation,
            source_ip=source_ip,
            stored_upload=stored_upload,
            batch_claim=batch_claim,
        )
        raise _outcome_error(outcome, batch_claim=batch_claim) from None

    try:
        db.commit()
    except SQLAlchemyError:
        # The server may have committed before the connection failed. Retain
        # clean bytes and do not write a rejection audit for an unknown outcome.
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise TechnicalIntakeError(
            "INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN"
            if batch_claim is not None
            else "STORED_FILE_PERSISTENCE_CONFLICT"
        ) from None
    return TechnicalIntakeResult(
        document,
        stored,
        safe_correlation,
        relationship,
        exact_content_duplicate_document_ids,
        intake_receipt,
        intake_receipt_sha256,
        batch_claim.item_id if batch_claim is not None else None,
        False,
    )


__all__ = [
    "TECHNICAL_DOCUMENT_TYPE_LABELS",
    "TECHNICAL_DOCUMENT_TYPE_OPTIONS",
    "TECHNICAL_DOCUMENT_TYPES",
    "TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS",
    "TechnicalIntakeError",
    "TechnicalIntakeResult",
    "create_technical_document_draft",
]
