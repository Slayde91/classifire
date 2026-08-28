"""Durable, owner-bound state for multi-report technical intake."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

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
from .technical_document_lineage import TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES
from .technical_document_metadata import (
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
    TechnicalDocumentMetadataError,
    normalize_technical_source_registration,
)
from .technical_intake import (
    _ACCEPTED_ITEM_RECEIPT_FIELDS,
    _ACCEPTED_REPLAY_EVIDENCE_INTEGRITY_CODES,
    _RETAINED_STORAGE_INTEGRITY_CODES,
    TECHNICAL_DOCUMENT_TYPES,
    TechnicalIntakeError,
    _multiline_text,
    _optional_iso_date,
    _standards,
    _text,
)

TECHNICAL_INTAKE_BATCH_SCHEMA = "technical-intake-batch-v1"
TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA = "technical-intake-item-receipt-v1"
TECHNICAL_INTAKE_BATCH_MAX_ITEMS = 20
TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES = 256 * 1024
TECHNICAL_INTAKE_CLAIM_TTL = timedelta(minutes=15)
TECHNICAL_INTAKE_BATCH_EXTENSIONS = frozenset(
    {".pdf", ".docx", ".xlsx", ".xlsb"}
)

TECHNICAL_INTAKE_REGISTRATION_FIELDS = frozenset(
    {
        "artifact_provenance_note",
        "artifact_provenance_status",
        "declared_source_role",
        "document_id",
        "document_type",
        "evidence_limitations",
        "evidence_scope",
        "expiry_date",
        "issuing_organisation",
        "jurisdiction",
        "manufacturer",
        "publication_date",
        "reference",
        "related_document_id",
        "relationship_effective_date",
        "relationship_reason",
        "relationship_scope",
        "relationship_type",
        "review_date",
        "revision",
        "sponsor_organisation",
        "standards",
        "title",
    }
)

_CREATE_ITEM_FIELDS = frozenset(
    {
        "client_item_id",
        "expected_sha256",
        "filename",
        "ordinal",
        "registration",
        "size_bytes",
    }
)
_HEX = frozenset("0123456789abcdef")
_UNSAFE_FILENAME_CHARACTERS = frozenset('<>:"/\\|?*')
_ERROR_ITEM_RECEIPT_FIELDS = frozenset(
    {
        "batch_id",
        "code",
        "expected_sha256",
        "expected_size_bytes",
        "http_status",
        "item_id",
        "ok",
        "operator_attention",
        "retryable",
        "schema",
    }
)
_PREACCEPT_ATTENTION_CODES = _RETAINED_STORAGE_INTEGRITY_CODES | frozenset(
    {
        "TECHNICAL_INTAKE_AUDIT_FAILURE",
        "UPLOAD_MULTIPLE_CLEANUP_FAILED",
        "UPLOAD_RETENTION_CLEANUP_FAILED",
        "UPLOAD_TEMP_CLEANUP_FAILED",
    }
)
_BATCH_ERROR_STATUS = {
    "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN": 503,
    "INTAKE_BATCH_BODY_INVALID": 422,
    "INTAKE_BATCH_CONTENT_TYPE_INVALID": 422,
    "INTAKE_BATCH_ID_INVALID": 422,
    "INTAKE_BATCH_ITEM_ID_INVALID": 422,
    "INTAKE_BATCH_ITEM_IN_PROGRESS": 409,
    "INTAKE_BATCH_ITEM_NOT_FOUND": 404,
    "INTAKE_BATCH_ITEM_NOT_RETRYABLE": 409,
    "INTAKE_BATCH_ITEM_REPLAY_MISMATCH": 409,
    "INTAKE_BATCH_MANIFEST_INVALID": 422,
    "INTAKE_BATCH_MANIFEST_MISMATCH": 409,
    "INTAKE_BATCH_NOT_FOUND": 404,
    "INTAKE_BATCH_PERSISTENCE_CONFLICT": 503,
}


class TechnicalIntakeBatchError(RuntimeError):
    """A stable, path-free batch validation or lifecycle failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.status_code = _BATCH_ERROR_STATUS.get(code, 422)
        self.retryable = code in {
            "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN",
            "INTAKE_BATCH_ITEM_IN_PROGRESS",
            "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        }
        self.fatal = code in {
            "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN",
            "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        }
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalIntakeBatchCreateResult:
    batch: TechnicalIntakeBatch
    items: tuple[TechnicalIntakeBatchItem, ...]
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class TechnicalIntakeBatchClaim:
    batch_id: str
    item_id: str
    attempt_token: str | None
    registration_sha256: str
    expected_sha256: str
    expected_size_bytes: int
    original_filename: str
    accepted_replay: bool
    prior_status: str


@dataclass(frozen=True, slots=True)
class TechnicalIntakeBatchItemUploadEligibility:
    """A mutation-free lifecycle decision shared by preflight and claim."""

    accepted_replay: bool
    prior_status: str


def canonical_json_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_canonical_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX for character in value)
    )


def _raise_persistence_conflict() -> NoReturn:
    raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")


def _verify_error_item_receipt(
    item: TechnicalIntakeBatchItem,
    *,
    batch_id: str,
) -> None:
    receipt = item.receipt_json
    code = item.outcome_code
    if (
        item.receipt_schema != TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
        or not isinstance(receipt, dict)
        or set(receipt) != _ERROR_ITEM_RECEIPT_FIELDS
        or not _is_canonical_sha256(item.receipt_sha256)
        or canonical_json_sha256(receipt) != item.receipt_sha256
        or not isinstance(code, str)
        or not code
    ):
        _raise_persistence_conflict()
    try:
        error = TechnicalIntakeError(code)
    except ValueError:
        _raise_persistence_conflict()
        return

    retained_evidence = (
        item.technical_document_id is not None
        and item.retained_file_sha256 is not None
    )
    if item.status == "processing":
        valid_lifecycle = (
            item.outcome_retryable is True
            and error.retryable
            and code not in _PREACCEPT_ATTENTION_CODES
            and not retained_evidence
        )
    elif item.status == "rejected":
        valid_lifecycle = (
            item.outcome_retryable is error.retryable
            and code not in _PREACCEPT_ATTENTION_CODES
            and not retained_evidence
        )
    elif item.status == "needs_attention":
        allowed_codes = (
            _ACCEPTED_REPLAY_EVIDENCE_INTEGRITY_CODES
            if retained_evidence
            else _PREACCEPT_ATTENTION_CODES
        )
        valid_lifecycle = item.outcome_retryable is False and code in allowed_codes
    else:
        valid_lifecycle = False

    if (
        not valid_lifecycle
        or receipt.get("schema") != TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
        or receipt.get("ok") is not False
        or receipt.get("batch_id") != batch_id
        or receipt.get("item_id") != item.id
        or receipt.get("code") != code
        or type(receipt.get("http_status")) is not int
        or receipt.get("http_status") != error.status_code
        or receipt.get("retryable") is not item.outcome_retryable
        or receipt.get("operator_attention") is not (
            item.status == "needs_attention"
        )
        or receipt.get("expected_sha256") != item.expected_sha256
        or receipt.get("expected_size_bytes") != item.declared_size_bytes
    ):
        _raise_persistence_conflict()


def _verify_retained_evidence_binding(
    db: Session,
    item: TechnicalIntakeBatchItem,
) -> tuple[TechnicalDocument, StoredFile]:
    document_id = item.technical_document_id
    if document_id is None or item.retained_file_sha256 is None:
        _raise_persistence_conflict()
    try:
        _uuid(document_id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
    except TechnicalIntakeBatchError:
        _raise_persistence_conflict()
    document = db.get(TechnicalDocument, document_id)
    if document is None:
        _raise_persistence_conflict()
    try:
        _uuid(document.id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
        _uuid(document.stored_file_id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
    except TechnicalIntakeBatchError:
        _raise_persistence_conflict()
    stored = db.get(StoredFile, document.stored_file_id)
    if (
        stored is None
        or document.document_id != item.declared_document_id
        or not _is_canonical_sha256(item.retained_file_sha256)
        or stored.sha256 != item.retained_file_sha256
        or item.retained_file_sha256 != item.expected_sha256
        or stored.size_bytes != item.declared_size_bytes
    ):
        _raise_persistence_conflict()
    try:
        _uuid(stored.id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
    except TechnicalIntakeBatchError:
        _raise_persistence_conflict()
    return document, stored


def _verify_quarantined_context_conflict_binding(
    db: Session,
    item: TechnicalIntakeBatchItem,
) -> None:
    document_id = item.technical_document_id
    retained_sha256 = item.retained_file_sha256
    if (
        document_id is None
        or retained_sha256 is None
        or retained_sha256 != item.expected_sha256
        or not _is_canonical_sha256(retained_sha256)
    ):
        _raise_persistence_conflict()
    document = db.get(TechnicalDocument, document_id)
    if document is None:
        _raise_persistence_conflict()
    linked_stored = db.get(StoredFile, document.stored_file_id)
    retained_stored = db.scalar(
        select(StoredFile).where(StoredFile.sha256 == retained_sha256)
    )
    if (
        linked_stored is None
        or retained_stored is None
        or linked_stored.id == retained_stored.id
        or retained_stored.size_bytes != item.declared_size_bytes
        or linked_stored.purpose != 'technical_evidence'
        or retained_stored.purpose != 'technical_evidence'
        or linked_stored.immutable is not True
        or retained_stored.immutable is not True
        or 'quarantined'
        not in {
            linked_stored.malware_scan_status,
            retained_stored.malware_scan_status,
        }
    ):
        _raise_persistence_conflict()
    try:
        _uuid(document.id, code='INTAKE_BATCH_PERSISTENCE_CONFLICT')
        _uuid(document.stored_file_id, code='INTAKE_BATCH_PERSISTENCE_CONFLICT')
        _uuid(linked_stored.id, code='INTAKE_BATCH_PERSISTENCE_CONFLICT')
        _uuid(retained_stored.id, code='INTAKE_BATCH_PERSISTENCE_CONFLICT')
    except TechnicalIntakeBatchError:
        _raise_persistence_conflict()


def _verify_accepted_item_receipt(
    db: Session,
    batch: TechnicalIntakeBatch,
    item: TechnicalIntakeBatchItem,
    registration: dict[str, Any],
) -> None:
    receipt = item.receipt_json
    if (
        item.outcome_code != "ACCEPTED"
        or item.outcome_retryable is not False
        or item.receipt_schema != TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
        or not isinstance(receipt, dict)
        or set(receipt) != _ACCEPTED_ITEM_RECEIPT_FIELDS
        or not _is_canonical_sha256(item.receipt_sha256)
        or canonical_json_sha256(receipt) != item.receipt_sha256
    ):
        _raise_persistence_conflict()
    document, stored = _verify_retained_evidence_binding(db, item)
    expected_relationship = (
        {
            "relationship_type": registration["relationship_type"],
            "related_document_id": registration["related_document_id"],
        }
        if registration["relationship_type"] is not None
        and registration["related_document_id"] is not None
        else None
    )
    if (
        receipt.get("schema") != TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
        or receipt.get("ok") is not True
        or type(receipt.get("http_status")) is not int
        or receipt.get("http_status") != 201
        or receipt.get("batch_id") != batch.id
        or receipt.get("item_id") != item.id
        or receipt.get("id") != document.id
        or receipt.get("document_id") != item.declared_document_id
        or receipt.get("document_type") != registration["document_type"]
        or receipt.get("declared_source_role")
        != registration["declared_source_role"]
        or receipt.get("artifact_provenance_status")
        != registration["artifact_provenance_status"]
        or receipt.get("evidence_scope") != registration["evidence_scope"]
        or receipt.get("status") != "draft"
        or receipt.get("file_sha256") != item.expected_sha256
        or receipt.get("malware_scan_status") != "clean"
        or receipt.get("extraction_status") != "awaiting_safe_extraction"
        or receipt.get("relationship") != expected_relationship
        or receipt.get("status_url")
        != f"/api/v1/technical/upload-batches/{batch.id}"
        or stored.purpose != "technical_evidence"
        or stored.immutable is not True
        or stored.malware_scan_status != "clean"
    ):
        _raise_persistence_conflict()
    duplicate_values = receipt.get("exact_content_duplicate_document_ids")
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
        _raise_persistence_conflict()

    if expected_relationship is None:
        return
    related_internal_id = db.scalar(
        select(TechnicalDocument.id).where(
            TechnicalDocument.document_id
            == expected_relationship["related_document_id"]
        )
    )
    if related_internal_id is None:
        _raise_persistence_conflict()
    relationship = db.scalar(
        select(TechnicalDocumentRelationship).where(
            TechnicalDocumentRelationship.document_id == document.id,
            TechnicalDocumentRelationship.related_document_id
            == related_internal_id,
            TechnicalDocumentRelationship.relationship_type
            == expected_relationship["relationship_type"],
        )
    )
    if (
        relationship is None
        or relationship.reason != registration["relationship_reason"]
        or relationship.scope != registration["relationship_scope"]
        or (
            relationship.effective_date.isoformat()
            if relationship.effective_date is not None
            else None
        )
        != registration["relationship_effective_date"]
    ):
        _raise_persistence_conflict()


def _verify_persisted_item_state(
    db: Session,
    batch: TechnicalIntakeBatch,
    item: TechnicalIntakeBatchItem,
    registration: dict[str, Any],
) -> None:
    try:
        _uuid(item.id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
    except TechnicalIntakeBatchError:
        _raise_persistence_conflict()
    if (
        not isinstance(item.attempt_count, int)
        or isinstance(item.attempt_count, bool)
        or item.attempt_count < 0
    ):
        _raise_persistence_conflict()
    if item.status == "processing":
        try:
            _uuid(item.attempt_token, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
        except TechnicalIntakeBatchError:
            _raise_persistence_conflict()
        if item.attempt_started_at is None or item.attempt_count <= 0:
            _raise_persistence_conflict()
    elif item.attempt_token is not None or item.attempt_started_at is not None:
        _raise_persistence_conflict()

    has_outcome = item.outcome_code is not None
    if item.status == "pending":
        if (
            has_outcome
            or item.outcome_retryable is not None
            or item.last_outcome_at is not None
            or item.receipt_schema is not None
            or item.receipt_json is not None
            or item.receipt_sha256 is not None
            or item.technical_document_id is not None
            or item.retained_file_sha256 is not None
        ):
            _raise_persistence_conflict()
        return
    if item.status == "processing" and not has_outcome:
        if (
            item.outcome_retryable is not None
            or item.last_outcome_at is not None
            or item.receipt_schema is not None
            or item.receipt_json is not None
            or item.receipt_sha256 is not None
            or item.technical_document_id is not None
            or item.retained_file_sha256 is not None
        ):
            _raise_persistence_conflict()
        return
    if item.attempt_count <= 0 or item.last_outcome_at is None:
        _raise_persistence_conflict()
    if item.status == "accepted":
        _verify_accepted_item_receipt(db, batch, item, registration)
        return
    if item.status not in {"processing", "rejected", "needs_attention"}:
        _raise_persistence_conflict()
    _verify_error_item_receipt(item, batch_id=batch.id)
    if item.status == "needs_attention" and item.technical_document_id is not None:
        try:
            _document, stored = _verify_retained_evidence_binding(db, item)
        except TechnicalIntakeBatchError:
            if item.outcome_code != "STORED_FILE_CONTEXT_CONFLICT":
                raise
            _verify_quarantined_context_conflict_binding(db, item)
            return
        if item.outcome_code == "MALWARE_DETECTED" and (
            stored.malware_scan_status != "quarantined"
        ):
            _raise_persistence_conflict()


def _derived_batch_status(items: tuple[TechnicalIntakeBatchItem, ...]) -> str:
    statuses = tuple(item.status for item in items)
    if "needs_attention" in statuses:
        return "needs_attention"
    if all(status == "accepted" for status in statuses):
        return "completed"
    if all(status in {"accepted", "rejected"} for status in statuses):
        return "completed_with_rejections"
    if any(status != "pending" for status in statuses):
        return "in_progress"
    return "open"


def _uuid(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        raise TechnicalIntakeBatchError(code)
    try:
        parsed = UUID(value.strip())
        normalised = str(parsed)
    except (AttributeError, ValueError):
        raise TechnicalIntakeBatchError(code) from None
    if parsed.version != 4 or normalised != value:
        raise TechnicalIntakeBatchError(code)
    return normalised


def canonical_technical_intake_filename(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        raise TechnicalIntakeBatchError(code)
    if (
        not value
        or value != value.strip()
        or len(value) > 500
        or any(character in _UNSAFE_FILENAME_CHARACTERS for character in value)
        or any(not character.isprintable() for character in value)
        or Path(value).suffix.lower() not in TECHNICAL_INTAKE_BATCH_EXTENSIONS
    ):
        raise TechnicalIntakeBatchError(code)
    return value


def _raw_text(value: object, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    if required and not value.strip():
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    return value


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def require_technical_intake_batch_item_upload_eligible(
    item: TechnicalIntakeBatchItem,
    *,
    now: datetime,
) -> TechnicalIntakeBatchItemUploadEligibility:
    """Fail closed unless an item may be replayed, attempted, or reclaimed."""

    if item.status == "accepted":
        return TechnicalIntakeBatchItemUploadEligibility(True, "accepted")
    if item.status == "pending":
        return TechnicalIntakeBatchItemUploadEligibility(False, "pending")
    if item.status == "rejected":
        if item.outcome_retryable is True:
            return TechnicalIntakeBatchItemUploadEligibility(False, "rejected")
        raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_NOT_RETRYABLE")
    if item.status == "processing":
        if item.attempt_started_at is None:
            raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_NOT_RETRYABLE")
        if (
            _as_utc(item.attempt_started_at) + TECHNICAL_INTAKE_CLAIM_TTL
            > _as_utc(now)
        ):
            raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_IN_PROGRESS")
        return TechnicalIntakeBatchItemUploadEligibility(
            False,
            "rejected" if item.outcome_retryable is True else "processing",
        )
    raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_NOT_RETRYABLE")


def normalize_technical_intake_registration(
    payload: Mapping[str, object],
) -> dict[str, Any]:
    """Return the one canonical registration snapshot used by create and replay."""

    if set(payload) != TECHNICAL_INTAKE_REGISTRATION_FIELDS:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    try:
        document_id = _text(
            _raw_text(payload["document_id"], required=True),
            code="DOCUMENT_ID_INVALID",
            maximum=200,
            required=True,
        )
        document_type = _text(
            _raw_text(payload["document_type"], required=True),
            code="DOCUMENT_TYPE_INVALID",
            maximum=100,
            required=True,
        )
        title = _text(
            _raw_text(payload["title"], required=True),
            code="INTAKE_FIELD_INVALID",
            maximum=500,
            required=True,
        )
        if document_type not in TECHNICAL_DOCUMENT_TYPES:
            raise TechnicalIntakeError("DOCUMENT_TYPE_INVALID")
        registration = normalize_technical_source_registration(
            document_type=document_type,
            declared_source_role=_raw_text(
                payload["declared_source_role"], required=True
            )
            or "",
            sponsor_organisation=_raw_text(payload["sponsor_organisation"]),
            artifact_provenance_status=_raw_text(
                payload["artifact_provenance_status"], required=True
            )
            or "",
            artifact_provenance_note=_raw_text(
                payload["artifact_provenance_note"]
            ),
            evidence_scope=_raw_text(payload["evidence_scope"], required=True)
            or "",
            evidence_limitations=_raw_text(payload["evidence_limitations"]),
        )
        relationship_type = _text(
            _raw_text(payload["relationship_type"]),
            code="RELATIONSHIP_TYPE_INVALID",
            maximum=50,
        )
        related_document_id = _text(
            _raw_text(payload["related_document_id"]),
            code="RELATED_DOCUMENT_ID_INVALID",
            maximum=200,
        )
        relationship_reason = _text(
            _raw_text(payload["relationship_reason"]),
            code="RELATIONSHIP_REASON_INVALID",
            maximum=2_000,
        )
        relationship_scope = _multiline_text(
            _raw_text(payload["relationship_scope"]),
            code="RELATIONSHIP_SCOPE_INVALID",
            maximum=4_000,
        )
        relationship_effective_date = _optional_iso_date(
            _raw_text(payload["relationship_effective_date"])
        )
        relationship_core = (
            relationship_type,
            related_document_id,
            relationship_reason,
        )
        if any(relationship_core) and not all(relationship_core):
            raise TechnicalIntakeError("RELATIONSHIP_FIELDS_INCOMPLETE")
        if (
            relationship_scope is not None
            or relationship_effective_date is not None
        ) and not all(relationship_core):
            raise TechnicalIntakeError("RELATIONSHIP_FIELDS_INCOMPLETE")
        if relationship_type is not None:
            if relationship_type not in TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES:
                raise TechnicalIntakeError("RELATIONSHIP_TYPE_INVALID")
            if related_document_id == document_id:
                raise TechnicalIntakeError("RELATIONSHIP_SELF_REFERENCE")

        publication_date = _optional_iso_date(
            _raw_text(payload["publication_date"])
        )
        review_date = _optional_iso_date(_raw_text(payload["review_date"]))
        expiry_date = _optional_iso_date(_raw_text(payload["expiry_date"]))
        standards_value = payload["standards"]
        standards_input: str | None
        if isinstance(standards_value, list):
            if not all(isinstance(item, str) for item in standards_value):
                raise TechnicalIntakeError("INTAKE_STANDARDS_INVALID")
            standards_input = "\n".join(standards_value)
        else:
            standards_input = _raw_text(standards_value)
        standards = _standards(standards_input)
        snapshot: dict[str, Any] = {
            "artifact_provenance_note": registration.artifact_provenance_note,
            "artifact_provenance_status": registration.artifact_provenance_status,
            "declared_source_role": registration.declared_source_role,
            "document_id": document_id,
            "document_type": document_type,
            "evidence_limitations": registration.evidence_limitations,
            "evidence_scope": registration.evidence_scope,
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
            "issuing_organisation": _text(
                _raw_text(payload["issuing_organisation"]),
                code="INTAKE_FIELD_INVALID",
                maximum=300,
            ),
            "jurisdiction": _text(
                _raw_text(payload["jurisdiction"]),
                code="INTAKE_FIELD_INVALID",
                maximum=200,
            ),
            "manufacturer": _text(
                _raw_text(payload["manufacturer"]),
                code="INTAKE_FIELD_INVALID",
                maximum=200,
            ),
            "publication_date": publication_date.isoformat()
            if publication_date
            else None,
            "reference": _text(
                _raw_text(payload["reference"]),
                code="INTAKE_FIELD_INVALID",
                maximum=300,
            ),
            "related_document_id": related_document_id,
            "relationship_effective_date": (
                relationship_effective_date.isoformat()
                if relationship_effective_date
                else None
            ),
            "relationship_reason": relationship_reason,
            "relationship_scope": relationship_scope,
            "relationship_type": relationship_type,
            "review_date": review_date.isoformat() if review_date else None,
            "revision": _text(
                _raw_text(payload["revision"]),
                code="INTAKE_FIELD_INVALID",
                maximum=100,
            ),
            "sponsor_organisation": registration.sponsor_organisation,
            "standards": standards,
            "title": title,
        }
    except TechnicalDocumentMetadataError as exc:
        raise TechnicalIntakeBatchError(exc.code) from None
    except TechnicalIntakeError as exc:
        raise TechnicalIntakeBatchError(exc.code) from None
    return snapshot


def _normalise_item(
    payload: object,
    *,
    settings: Settings,
    enforce_size_limit: bool,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != _CREATE_ITEM_FIELDS:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    client_item_id = _uuid(
        payload["client_item_id"], code="INTAKE_BATCH_ITEM_ID_INVALID"
    )
    ordinal = payload["ordinal"]
    if not isinstance(ordinal, int) or isinstance(ordinal, bool):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    filename = canonical_technical_intake_filename(
        payload["filename"],
        code="INTAKE_BATCH_MANIFEST_INVALID",
    )
    size_bytes = payload["size_bytes"]
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
        or (enforce_size_limit and size_bytes > settings.max_upload_bytes)
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    expected_sha256 = payload["expected_sha256"]
    if (
        not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in _HEX for character in expected_sha256)
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    registration_value = payload["registration"]
    if not isinstance(registration_value, Mapping):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    registration = normalize_technical_intake_registration(registration_value)
    if registration["jurisdiction"] is None:
        raise TechnicalIntakeBatchError("INTAKE_FIELD_INVALID")
    return {
        "client_item_id": client_item_id,
        "expected_sha256": expected_sha256,
        "filename": filename,
        "ordinal": ordinal,
        "registration": registration,
        "registration_sha256": canonical_json_sha256(registration),
        "size_bytes": size_bytes,
    }


def create_technical_intake_batch(
    db: Session,
    settings: Settings,
    *,
    actor: User,
    client_request_id: object,
    items: object,
    source_ip: str | None = None,
) -> TechnicalIntakeBatchCreateResult:
    if not actor.id or db.get(User, actor.id) is None:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    safe_request_id = _uuid(
        client_request_id, code="INTAKE_BATCH_ID_INVALID"
    )
    if not isinstance(items, list) or not 1 <= len(items) <= TECHNICAL_INTAKE_BATCH_MAX_ITEMS:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    try:
        existing, existing_items = (
            get_owned_technical_intake_batch_by_client_request(
                db,
                actor=actor,
                client_request_id=safe_request_id,
            )
        )
    except TechnicalIntakeBatchError as exc:
        if exc.code != "INTAKE_BATCH_NOT_FOUND":
            raise
        existing = None
        existing_items = ()
    normalised_items = [
        _normalise_item(
            item,
            settings=settings,
            enforce_size_limit=existing is None,
        )
        for item in items
    ]
    if {item["ordinal"] for item in normalised_items} != set(
        range(1, len(normalised_items) + 1)
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    for key in ("client_item_id",):
        if len({item[key] for item in normalised_items}) != len(normalised_items):
            raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    document_ids = [item["registration"]["document_id"] for item in normalised_items]
    if len(set(document_ids)) != len(document_ids):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_INVALID")
    for item in normalised_items:
        related_document_id = item["registration"]["related_document_id"]
        if existing is None and related_document_id is not None and not db.scalar(
            select(TechnicalDocument.id).where(
                TechnicalDocument.document_id == related_document_id
            )
        ):
            raise TechnicalIntakeBatchError("RELATED_DOCUMENT_NOT_FOUND")
    normalised_items.sort(key=lambda item: item["ordinal"])
    manifest = {
        "batch_schema": TECHNICAL_INTAKE_BATCH_SCHEMA,
        "client_request_id": safe_request_id,
        "items": normalised_items,
    }
    manifest_sha256 = canonical_json_sha256(manifest)
    if existing is not None:
        if existing.manifest_sha256 != manifest_sha256:
            raise TechnicalIntakeBatchError("INTAKE_BATCH_MANIFEST_MISMATCH")
        if len(existing_items) != len(normalised_items):
            raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
        return TechnicalIntakeBatchCreateResult(existing, existing_items, True)

    batch = TechnicalIntakeBatch(
        batch_schema=TECHNICAL_INTAKE_BATCH_SCHEMA,
        client_request_id=safe_request_id,
        created_by_id=actor.id,
        expected_item_count=len(normalised_items),
        manifest_sha256=manifest_sha256,
        status="open",
    )
    db.add(batch)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        try:
            existing, existing_items = (
                get_owned_technical_intake_batch_by_client_request(
                    db,
                    actor=actor,
                    client_request_id=safe_request_id,
                )
            )
        except TechnicalIntakeBatchError as exc:
            if exc.code != "INTAKE_BATCH_NOT_FOUND":
                raise
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            ) from None
        if existing.manifest_sha256 != manifest_sha256:
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_MANIFEST_MISMATCH"
            ) from None
        if len(existing_items) != len(normalised_items):
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            ) from None
        return TechnicalIntakeBatchCreateResult(
            existing,
            existing_items,
            True,
        )
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise TechnicalIntakeBatchError(
            "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN"
        ) from None
    rows: list[TechnicalIntakeBatchItem] = []
    for item in normalised_items:
        row = TechnicalIntakeBatchItem(
            batch_id=batch.id,
            client_item_id=item["client_item_id"],
            ordinal=item["ordinal"],
            original_filename=item["filename"],
            declared_size_bytes=item["size_bytes"],
            expected_sha256=item["expected_sha256"],
            declared_document_id=item["registration"]["document_id"],
            registration_schema=TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
            registration_snapshot=item["registration"],
            registration_sha256=item["registration_sha256"],
            status="pending",
        )
        db.add(row)
        rows.append(row)
    try:
        db.flush()
        record_audit(
            db,
            actor=actor,
            action="create",
            entity_type="technical_intake_batch",
            entity_id=batch.id,
            new_value={
                "batch_schema": batch.batch_schema,
                "expected_item_count": batch.expected_item_count,
                "manifest_sha256": batch.manifest_sha256,
                "status": batch.status,
            },
            reason="Created an immutable multi-report intake manifest",
            source_ip=source_ip,
            correlation_id=batch.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        try:
            existing, existing_items = (
                get_owned_technical_intake_batch_by_client_request(
                    db,
                    actor=actor,
                    client_request_id=safe_request_id,
                )
            )
        except TechnicalIntakeBatchError as exc:
            if exc.code != "INTAKE_BATCH_NOT_FOUND":
                raise
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            ) from None
        if existing.manifest_sha256 != manifest_sha256:
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_MANIFEST_MISMATCH"
            ) from None
        if len(existing_items) != len(normalised_items):
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            ) from None
        return TechnicalIntakeBatchCreateResult(existing, existing_items, True)
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise TechnicalIntakeBatchError("INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN") from None
    return TechnicalIntakeBatchCreateResult(batch, tuple(rows), False)


def _verify_persisted_batch_manifest(
    db: Session,
    batch: TechnicalIntakeBatch,
    items: tuple[TechnicalIntakeBatchItem, ...],
) -> None:
    try:
        _uuid(batch.id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
        _uuid(batch.client_request_id, code="INTAKE_BATCH_PERSISTENCE_CONFLICT")
    except TechnicalIntakeBatchError:
        raise TechnicalIntakeBatchError(
            "INTAKE_BATCH_PERSISTENCE_CONFLICT"
        ) from None
    if (
        batch.batch_schema != TECHNICAL_INTAKE_BATCH_SCHEMA
        or not 1 <= batch.expected_item_count <= TECHNICAL_INTAKE_BATCH_MAX_ITEMS
        or batch.expected_item_count != len(items)
        or {item.ordinal for item in items} != set(range(1, len(items) + 1))
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    manifest_items: list[dict[str, Any]] = []
    for item in items:
        registration = item.registration_snapshot
        if not isinstance(registration, dict):
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            )
        try:
            canonical_filename = canonical_technical_intake_filename(
                item.original_filename,
                code="INTAKE_BATCH_PERSISTENCE_CONFLICT",
            )
            _uuid(
                item.client_item_id,
                code="INTAKE_BATCH_PERSISTENCE_CONFLICT",
            )
            canonical_registration = normalize_technical_intake_registration(
                registration
            )
        except TechnicalIntakeBatchError:
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            ) from None
        if (
            item.registration_schema != TECHNICAL_SOURCE_REGISTRATION_SCHEMA
            or canonical_registration != registration
            or canonical_registration["jurisdiction"] is None
            or canonical_json_sha256(registration) != item.registration_sha256
            or registration.get("document_id") != item.declared_document_id
            or canonical_filename != item.original_filename
            or item.declared_size_bytes <= 0
            or not _is_canonical_sha256(item.expected_sha256)
        ):
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_PERSISTENCE_CONFLICT"
            )
        _verify_persisted_item_state(db, batch, item, canonical_registration)
        manifest_items.append(
            {
                "client_item_id": item.client_item_id,
                "expected_sha256": item.expected_sha256,
                "filename": item.original_filename,
                "ordinal": item.ordinal,
                "registration": registration,
                "registration_sha256": item.registration_sha256,
                "size_bytes": item.declared_size_bytes,
            }
        )
    manifest = {
        "batch_schema": batch.batch_schema,
        "client_request_id": batch.client_request_id,
        "items": manifest_items,
    }
    if canonical_json_sha256(manifest) != batch.manifest_sha256:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    derived_status = _derived_batch_status(items)
    is_completed = derived_status in {"completed", "completed_with_rejections"}
    if (
        batch.status != derived_status
        or (batch.completed_at is not None) is not is_completed
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")


def get_owned_technical_intake_batch(
    db: Session,
    *,
    actor: User,
    batch_id: object,
) -> tuple[TechnicalIntakeBatch, tuple[TechnicalIntakeBatchItem, ...]]:
    safe_batch_id = _uuid(batch_id, code="INTAKE_BATCH_ID_INVALID")
    rows = db.execute(
        select(TechnicalIntakeBatch, TechnicalIntakeBatchItem)
        .outerjoin(
            TechnicalIntakeBatchItem,
            TechnicalIntakeBatchItem.batch_id == TechnicalIntakeBatch.id,
        )
        .where(
            TechnicalIntakeBatch.id == safe_batch_id,
            TechnicalIntakeBatch.created_by_id == actor.id,
        )
        .order_by(TechnicalIntakeBatchItem.ordinal)
        .execution_options(populate_existing=True)
    ).all()
    if not rows:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_NOT_FOUND")
    batch = rows[0][0]
    items = tuple(item for _batch, item in rows if item is not None)
    if len(items) != batch.expected_item_count:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    _verify_persisted_batch_manifest(db, batch, items)
    return batch, items


def get_owned_technical_intake_batch_by_client_request(
    db: Session,
    *,
    actor: User,
    client_request_id: object,
) -> tuple[TechnicalIntakeBatch, tuple[TechnicalIntakeBatchItem, ...]]:
    safe_request_id = _uuid(
        client_request_id,
        code="INTAKE_BATCH_ID_INVALID",
    )
    rows = db.execute(
        select(TechnicalIntakeBatch, TechnicalIntakeBatchItem)
        .outerjoin(
            TechnicalIntakeBatchItem,
            TechnicalIntakeBatchItem.batch_id == TechnicalIntakeBatch.id,
        )
        .where(
            TechnicalIntakeBatch.created_by_id == actor.id,
            TechnicalIntakeBatch.client_request_id == safe_request_id,
        )
        .order_by(TechnicalIntakeBatchItem.ordinal)
        .execution_options(populate_existing=True)
    ).all()
    if not rows:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_NOT_FOUND")
    batch = rows[0][0]
    items = tuple(item for _batch, item in rows if item is not None)
    if len(items) != batch.expected_item_count:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    _verify_persisted_batch_manifest(db, batch, items)
    return batch, items


def serialize_technical_intake_batch(
    batch: TechnicalIntakeBatch,
    items: tuple[TechnicalIntakeBatchItem, ...],
    *,
    idempotent_replay: bool = False,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    counts = {
        state: sum(item.status == state for item in items)
        for state in ("pending", "processing", "accepted", "rejected", "needs_attention")
    }
    return {
        "ok": True,
        "batch_id": batch.id,
        "batch_schema": batch.batch_schema,
        "client_request_id": batch.client_request_id,
        "manifest_sha256": batch.manifest_sha256,
        "status": batch.status,
        "expected_item_count": batch.expected_item_count,
        "counts": counts,
        "created_at": _as_utc(batch.created_at).isoformat(),
        "updated_at": _as_utc(batch.updated_at).isoformat(),
        "completed_at": (
            _as_utc(batch.completed_at).isoformat()
            if batch.completed_at
            else None
        ),
        "idempotent_replay": idempotent_replay,
        "status_url": f"/api/v1/technical/upload-batches/{batch.id}",
        "items": [
            {
                "item_id": item.id,
                "client_item_id": item.client_item_id,
                "ordinal": item.ordinal,
                "filename": item.original_filename,
                "size_bytes": item.declared_size_bytes,
                "expected_sha256": item.expected_sha256,
                "document_id": item.declared_document_id,
                "registration_schema": item.registration_schema,
                "registration": item.registration_snapshot,
                "registration_sha256": item.registration_sha256,
                "status": item.status,
                "attempt_count": item.attempt_count,
                "outcome_code": item.outcome_code,
                "claim_expires_at": (
                    (
                        _as_utc(item.attempt_started_at)
                        + TECHNICAL_INTAKE_CLAIM_TTL
                    ).isoformat()
                    if item.status == "processing"
                    and item.attempt_started_at is not None
                    else None
                ),
                "retryable": (
                    item.status == "pending"
                    or (item.status == "rejected" and item.outcome_retryable is True)
                    or (
                        item.status == "processing"
                        and item.attempt_started_at is not None
                        and _as_utc(item.attempt_started_at)
                        + TECHNICAL_INTAKE_CLAIM_TTL
                        <= now
                    )
                ),
                "technical_document_id": item.technical_document_id,
                "retained_file_sha256": item.retained_file_sha256,
                "receipt": item.receipt_json,
                "receipt_sha256": item.receipt_sha256,
            }
            for item in items
        ],
    }


def claim_technical_intake_batch_item(
    db: Session,
    *,
    actor: User,
    batch_id: object,
    item_id: object,
    filename: str,
    registration_snapshot: Mapping[str, object],
) -> TechnicalIntakeBatchClaim:
    batch, _items = get_owned_technical_intake_batch(
        db, actor=actor, batch_id=batch_id
    )
    safe_item_id = _uuid(item_id, code="INTAKE_BATCH_ITEM_ID_INVALID")
    item = db.scalar(
        select(TechnicalIntakeBatchItem).where(
            TechnicalIntakeBatchItem.id == safe_item_id,
            TechnicalIntakeBatchItem.batch_id == batch.id,
        )
    )
    if item is None:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_NOT_FOUND")
    safe_filename = canonical_technical_intake_filename(
        filename,
        code="INTAKE_BATCH_ITEM_REPLAY_MISMATCH",
    )
    canonical_registration = normalize_technical_intake_registration(
        registration_snapshot
    )
    registration_sha256 = canonical_json_sha256(canonical_registration)
    if (
        safe_filename != item.original_filename
        or registration_sha256 != item.registration_sha256
        or canonical_registration != item.registration_snapshot
    ):
        raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_REPLAY_MISMATCH")
    now = datetime.now(UTC)
    eligibility = require_technical_intake_batch_item_upload_eligible(
        item,
        now=now,
    )
    if eligibility.accepted_replay:
        return TechnicalIntakeBatchClaim(
            batch.id,
            item.id,
            None,
            item.registration_sha256,
            item.expected_sha256,
            item.declared_size_bytes,
            item.original_filename,
            True,
            "accepted",
        )
    token = str(uuid4())
    try:
        claimed = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.batch_id == batch.id,
                TechnicalIntakeBatchItem.record_version == item.record_version,
            )
            .values(
                status="processing",
                attempt_token=token,
                attempt_started_at=now,
                attempt_count=TechnicalIntakeBatchItem.attempt_count + 1,
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if getattr(claimed, "rowcount", 0) != 1:
            raise TechnicalIntakeBatchError("INTAKE_BATCH_ITEM_IN_PROGRESS")
        db.flush()
        refresh_technical_intake_batch_status(
            db,
            batch_id=batch.id,
         )
        db.commit()
    except TechnicalIntakeBatchError:
        try:
            db.rollback()
        except SQLAlchemyError:
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN"
            ) from None
        raise
    except SQLAlchemyError:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass
        raise TechnicalIntakeBatchError("INTAKE_BATCH_ACKNOWLEDGEMENT_UNKNOWN") from None
    return TechnicalIntakeBatchClaim(
        batch.id,
        item.id,
        token,
        item.registration_sha256,
        item.expected_sha256,
        item.declared_size_bytes,
        item.original_filename,
        False,
        eligibility.prior_status,
    )


def refresh_technical_intake_batch_status(
    db: Session,
    *,
    batch_id: str,
    now: datetime | None = None,
) -> None:
    batch = db.scalar(
        select(TechnicalIntakeBatch)
        .where(TechnicalIntakeBatch.id == batch_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if batch is None:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    statuses = tuple(
        db.scalars(
            select(TechnicalIntakeBatchItem.status).where(
                TechnicalIntakeBatchItem.batch_id == batch_id
            )
        ).all()
    )
    if len(statuses) != batch.expected_item_count:
        raise TechnicalIntakeBatchError("INTAKE_BATCH_PERSISTENCE_CONFLICT")
    completed_at: datetime | None = None
    if "needs_attention" in statuses:
        status = "needs_attention"
    elif all(item_status == "accepted" for item_status in statuses):
        status = "completed"
        completed_at = batch.completed_at or now or datetime.now(UTC)
    elif all(item_status in {"accepted", "rejected"} for item_status in statuses):
        status = "completed_with_rejections"
        completed_at = batch.completed_at or now or datetime.now(UTC)
    elif any(item_status != "pending" for item_status in statuses):
        status = "in_progress"
    else:
        status = "open"
    if batch.status != status or batch.completed_at != completed_at:
        batch.status = status
        batch.completed_at = completed_at
        batch.record_version += 1


__all__ = [
    "TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES",
    "TECHNICAL_INTAKE_BATCH_SCHEMA",
    "TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA",
    "TECHNICAL_INTAKE_REGISTRATION_FIELDS",
    "TechnicalIntakeBatchClaim",
    "TechnicalIntakeBatchCreateResult",
    "TechnicalIntakeBatchError",
    "TechnicalIntakeBatchItemUploadEligibility",
    "canonical_json_sha256",
    "canonical_technical_intake_filename",
    "claim_technical_intake_batch_item",
    "create_technical_intake_batch",
    "get_owned_technical_intake_batch",
    "get_owned_technical_intake_batch_by_client_request",
    "normalize_technical_intake_registration",
    "refresh_technical_intake_batch_status",
    "require_technical_intake_batch_item_upload_eligible",
    "serialize_technical_intake_batch",
]
