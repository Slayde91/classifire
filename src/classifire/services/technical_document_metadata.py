"""Validated, Draft-only metadata for retained technical source documents."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import TechnicalDocument, User

TECHNICAL_SOURCE_REGISTRATION_SCHEMA = "technical-source-registration-v1"
TECHNICAL_SOURCE_ROLES = frozenset(
    {
        "primary_test",
        "assessment",
        "regulatory_summary",
        "supporting_reference",
        "manufacturer_information",
        "administrative_notice",
    }
)
TECHNICAL_ARTIFACT_PROVENANCE_STATUSES = frozenset(
    {
        "issuer_original",
        "issuer_copy",
        "transformed_derivative",
        "unknown",
    }
)
TECHNICAL_EVIDENCE_SCOPES = frozenset(
    {
        "full_source",
        "summary_only",
        "bibliographic_only",
    }
)
TECHNICAL_CURRENT_STANDARDS_ADVISORY_SCHEMA = (
    "technical-current-standards-advisory-v1"
)
TECHNICAL_CURRENT_STANDARD_REFERENCES: tuple[str, ...] = (
    "NCC 2022",
    "AS 1530.4:2014",
    "AS 4072.1:2005",
)
_CURRENT_STANDARD_REFERENCE_BY_COMPACT_VALUE = {
    "NCC2022": "NCC 2022",
    "AS1530.4:2014": "AS 1530.4:2014",
    "AS4072.1:2005": "AS 4072.1:2005",
}

_SPONSOR_MAX_LENGTH = 300
_PROVENANCE_NOTE_MAX_LENGTH = 4_000
_EVIDENCE_LIMITATIONS_MAX_LENGTH = 20_000
_REASON_MAX_LENGTH = 4_000
_METADATA_EDITABLE_STATUSES = frozenset({"draft", "rejected"})
_ERROR_CODES = frozenset(
    {
        "ARTIFACT_PROVENANCE_INVALID",
        "ARTIFACT_PROVENANCE_NOTE_REQUIRED",
        "EVIDENCE_SCOPE_INVALID",
        "SOURCE_CLASSIFICATION_INVALID",
        "SOURCE_DOCUMENT_NOT_DRAFT",
        "SOURCE_DOCUMENT_NOT_EDITABLE",
        "SOURCE_METADATA_ACTOR_INVALID",
        "SOURCE_METADATA_FIELD_INVALID",
        "SOURCE_METADATA_REASON_INVALID",
        "SOURCE_METADATA_STALE",
        "SOURCE_ROLE_INVALID",
    }
)


class TechnicalDocumentMetadataError(ValueError):
    """A stable metadata-validation or optimistic-update failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical-document metadata error code")
        self.code = code
        super().__init__(code)


def _enum(value: str, *, allowed: frozenset[str], code: str) -> str:
    if not isinstance(value, str):
        raise TechnicalDocumentMetadataError(code)
    normalised = value.strip()
    if normalised not in allowed:
        raise TechnicalDocumentMetadataError(code)
    return normalised


def _optional_text(
    value: str | None,
    *,
    maximum: int,
    multiline: bool = False,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_FIELD_INVALID")
    normalised = (
        value.replace("\r\n", "\n").replace("\r", "\n").strip()
        if multiline
        else value.strip()
    )
    if not normalised:
        return None
    allowed_controls = {"\r", "\n", "\t"} if multiline else set()
    if len(normalised) > maximum or any(
        not character.isprintable() and character not in allowed_controls
        for character in normalised
    ):
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_FIELD_INVALID")
    return normalised


def _reason(value: str) -> str:
    try:
        normalised = _optional_text(value, maximum=_REASON_MAX_LENGTH, multiline=True)
    except TechnicalDocumentMetadataError as exc:
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_REASON_INVALID") from exc
    if normalised is None:
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_REASON_INVALID")
    return normalised


@dataclass(frozen=True, slots=True)
class TechnicalSourceRegistrationMetadata:
    declared_source_role: str
    sponsor_organisation: str | None
    artifact_provenance_status: str
    artifact_provenance_note: str | None
    evidence_scope: str
    evidence_limitations: str | None

    def model_values(self) -> dict[str, str | None]:
        return {
            "declared_source_role": self.declared_source_role,
            "sponsor_organisation": self.sponsor_organisation,
            "artifact_provenance_status": self.artifact_provenance_status,
            "artifact_provenance_note": self.artifact_provenance_note,
            "evidence_scope": self.evidence_scope,
            "evidence_limitations": self.evidence_limitations,
        }

    def manifest(self) -> dict[str, str | None]:
        return {
            "schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
            **self.model_values(),
        }


@dataclass(frozen=True, slots=True)
class TechnicalCurrentStandardsAdvisory:
    """A declaration-only attention signal that never asserts compliance."""

    declared_current_references: tuple[str, ...]
    missing_references: tuple[str, ...]
    evidence_attention_required: bool
    independent_evidence_review_required: bool = True

    def manifest(self) -> dict[str, object]:
        return {
            "schema": TECHNICAL_CURRENT_STANDARDS_ADVISORY_SCHEMA,
            "basis": "declared_standards_metadata_only",
            "declared_current_references": list(
                self.declared_current_references
            ),
            "missing_references": list(self.missing_references),
            "evidence_attention_required": self.evidence_attention_required,
            "independent_evidence_review_required": (
                self.independent_evidence_review_required
            ),
        }


def technical_current_standards_advisory(
    standards: object,
) -> TechnicalCurrentStandardsAdvisory:
    """Compare human-declared metadata with current reference editions.

    This deliberately ignores titles, filenames, OCR, extracted text, source
    approval, and document type. A matching declaration is not evidence that a
    report is compliant or that any system is applicable.
    """

    values = standards if isinstance(standards, (list, tuple)) else ()
    declared: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        compact = "".join(value.upper().split())
        canonical = _CURRENT_STANDARD_REFERENCE_BY_COMPACT_VALUE.get(compact)
        if canonical is not None:
            declared.add(canonical)
    declared_references = tuple(
        reference
        for reference in TECHNICAL_CURRENT_STANDARD_REFERENCES
        if reference in declared
    )
    missing_references = tuple(
        reference
        for reference in TECHNICAL_CURRENT_STANDARD_REFERENCES
        if reference not in declared
    )
    return TechnicalCurrentStandardsAdvisory(
        declared_current_references=declared_references,
        missing_references=missing_references,
        evidence_attention_required=bool(missing_references),
    )


def normalize_technical_source_registration(
    *,
    document_type: str,
    declared_source_role: str,
    sponsor_organisation: str | None,
    artifact_provenance_status: str,
    artifact_provenance_note: str | None,
    evidence_scope: str,
    evidence_limitations: str | None,
) -> TechnicalSourceRegistrationMetadata:
    """Validate user-declared source metadata without granting technical authority."""

    role = _enum(
        declared_source_role,
        allowed=TECHNICAL_SOURCE_ROLES,
        code="SOURCE_ROLE_INVALID",
    )
    provenance = _enum(
        artifact_provenance_status,
        allowed=TECHNICAL_ARTIFACT_PROVENANCE_STATUSES,
        code="ARTIFACT_PROVENANCE_INVALID",
    )
    scope = _enum(
        evidence_scope,
        allowed=TECHNICAL_EVIDENCE_SCOPES,
        code="EVIDENCE_SCOPE_INVALID",
    )
    sponsor = _optional_text(sponsor_organisation, maximum=_SPONSOR_MAX_LENGTH)
    provenance_note = _optional_text(
        artifact_provenance_note,
        maximum=_PROVENANCE_NOTE_MAX_LENGTH,
        multiline=True,
    )
    limitations = _optional_text(
        evidence_limitations,
        maximum=_EVIDENCE_LIMITATIONS_MAX_LENGTH,
        multiline=True,
    )
    if provenance == "transformed_derivative" and provenance_note is None:
        raise TechnicalDocumentMetadataError("ARTIFACT_PROVENANCE_NOTE_REQUIRED")
    if document_type == "regulatory_information_report" and (
        role != "regulatory_summary" or scope != "summary_only"
    ):
        raise TechnicalDocumentMetadataError("SOURCE_CLASSIFICATION_INVALID")
    return TechnicalSourceRegistrationMetadata(
        declared_source_role=role,
        sponsor_organisation=sponsor,
        artifact_provenance_status=provenance,
        artifact_provenance_note=provenance_note,
        evidence_scope=scope,
        evidence_limitations=limitations,
    )


def _updated_exactly_one(result: Any) -> bool:
    return getattr(result, "rowcount", 0) == 1


def update_technical_document_draft_metadata(
    db: Session,
    *,
    actor: User,
    document_id: str,
    expected_record_version: int,
    registration: TechnicalSourceRegistrationMetadata,
    reason: str,
    source_ip: str | None = None,
) -> TechnicalDocument:
    """Optimistically update metadata on one non-authoritative reviewable source."""

    # Kept local so the review service can reuse registration validation
    # without creating a module-import cycle.
    from .technical_document_review import TECHNICAL_DOCUMENT_REVIEW_POLICY_V2

    if not isinstance(actor, User) or not actor.id or db.get(User, actor.id) is None:
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_ACTOR_INVALID")
    if (
        not isinstance(document_id, str)
        or not document_id
        or not isinstance(expected_record_version, int)
        or isinstance(expected_record_version, bool)
        or expected_record_version < 1
        or not isinstance(registration, TechnicalSourceRegistrationMetadata)
    ):
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_STALE")
    safe_reason = _reason(reason)
    document = db.get(TechnicalDocument, document_id)
    if document is None:
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_STALE")
    if document.status not in _METADATA_EDITABLE_STATUSES:
        raise TechnicalDocumentMetadataError("SOURCE_DOCUMENT_NOT_EDITABLE")

    # Revalidate against the persisted document type. A caller cannot validate
    # one classification and apply it to a different kind of source.
    registration = normalize_technical_source_registration(
        document_type=document.document_type,
        declared_source_role=registration.declared_source_role,
        sponsor_organisation=registration.sponsor_organisation,
        artifact_provenance_status=registration.artifact_provenance_status,
        artifact_provenance_note=registration.artifact_provenance_note,
        evidence_scope=registration.evidence_scope,
        evidence_limitations=registration.evidence_limitations,
    )
    previous_values = {
        **{
            key: getattr(document, key)
            for key in registration.model_values()
        },
        "metadata_json": copy.deepcopy(document.metadata_json),
        "record_version": document.record_version,
        "status": document.status,
        "stored_file_id": document.stored_file_id,
    }
    metadata = (
        copy.deepcopy(document.metadata_json)
        if isinstance(document.metadata_json, dict)
        else {}
    )
    metadata.update(
        {
            "human_review_required": True,
            "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
            "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
        }
    )
    new_record_version = expected_record_version + 1
    result = db.execute(
        update(TechnicalDocument)
        .where(
            TechnicalDocument.id == document.id,
            TechnicalDocument.status.in_(_METADATA_EDITABLE_STATUSES),
            TechnicalDocument.record_version == expected_record_version,
        )
        .values(
            **registration.model_values(),
            metadata_json=metadata,
            record_version=new_record_version,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(result):
        db.expire(document)
        refreshed = db.get(TechnicalDocument, document.id)
        if (
            refreshed is not None
            and refreshed.status not in _METADATA_EDITABLE_STATUSES
        ):
            raise TechnicalDocumentMetadataError("SOURCE_DOCUMENT_NOT_EDITABLE")
        raise TechnicalDocumentMetadataError("SOURCE_METADATA_STALE")

    record_audit(
        db,
        actor=actor,
        action="update_draft_source_metadata",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value=previous_values,
        new_value={
            **registration.model_values(),
            "metadata_json": metadata,
            "record_version": new_record_version,
            "status": document.status,
            "stored_file_id": document.stored_file_id,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    db.expire(document)
    db.refresh(document)
    return document


__all__ = [
    "TECHNICAL_ARTIFACT_PROVENANCE_STATUSES",
    "TECHNICAL_CURRENT_STANDARDS_ADVISORY_SCHEMA",
    "TECHNICAL_CURRENT_STANDARD_REFERENCES",
    "TECHNICAL_EVIDENCE_SCOPES",
    "TECHNICAL_SOURCE_REGISTRATION_SCHEMA",
    "TECHNICAL_SOURCE_ROLES",
    "TechnicalDocumentMetadataError",
    "TechnicalCurrentStandardsAdvisory",
    "TechnicalSourceRegistrationMetadata",
    "normalize_technical_source_registration",
    "technical_current_standards_advisory",
    "update_technical_document_draft_metadata",
]
