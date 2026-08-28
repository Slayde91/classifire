"""Draft-only, append-only relationships between retained technical sources."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import TechnicalDocument, TechnicalDocumentRelationship, User
from .technical_document_review import technical_summary_source_target_is_eligible

TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES = frozenset(
    {
        "revision_of",
        "assessment_of",
        "amendment_to",
        "replaces",
        "retirement_notice_for",
        "summary_of",
    }
)
TECHNICAL_DOCUMENT_RELATIONSHIP_LABELS = {
    "revision_of": "Revision of",
    "assessment_of": "Assessment of",
    "amendment_to": "Amendment to",
    "replaces": "Replaces",
    "retirement_notice_for": "Retirement notice for",
    "summary_of": "Summary of",
}
TECHNICAL_DOCUMENT_RELATIONSHIP_REASON_MAX_LENGTH = 2_000
TECHNICAL_DOCUMENT_RELATIONSHIP_SCOPE_MAX_LENGTH = 4_000

_ERROR_CODES = frozenset(
    {
        "RELATED_DOCUMENT_ID_INVALID",
        "RELATED_DOCUMENT_NOT_FOUND",
        "RELATIONSHIP_ALREADY_EXISTS",
        "RELATIONSHIP_CYCLE",
        "RELATIONSHIP_EFFECTIVE_DATE_INVALID",
        "RELATIONSHIP_FIELDS_INCOMPLETE",
        "RELATIONSHIP_REASON_INVALID",
        "RELATIONSHIP_SCOPE_INVALID",
        "RELATIONSHIP_SELF_REFERENCE",
        "RELATIONSHIP_TYPE_INVALID",
        "SUMMARY_SOURCE_TARGET_INVALID",
        "SOURCE_DOCUMENT_NOT_DRAFT",
    }
)


class TechnicalDocumentLineageError(ValueError):
    """A stable, presentation-safe technical-source lineage failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical-document lineage error code")
        self.code = code
        super().__init__(code)


def _required_text(
    value: str | None,
    *,
    required_code: str,
    maximum: int,
    too_long_code: str,
    invalid_code: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TechnicalDocumentLineageError(required_code)
    normalised = value.strip()
    if len(normalised) > maximum:
        raise TechnicalDocumentLineageError(too_long_code)
    if any(
        not character.isprintable() and character not in {"\r", "\n", "\t"}
        for character in normalised
    ):
        raise TechnicalDocumentLineageError(invalid_code)
    return normalised


def _optional_text(value: str | None, *, maximum: int, too_long_code: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TechnicalDocumentLineageError(too_long_code)
    if not value.strip():
        return None
    return _required_text(
        value,
        required_code=too_long_code,
        maximum=maximum,
        too_long_code=too_long_code,
        invalid_code=too_long_code,
    )


def _would_create_cycle(
    db: Session,
    *,
    document_id: str,
    related_document_id: str,
) -> bool:
    """Return true when ``related -> ancestors`` already reaches ``document``."""

    frontier = {related_document_id}
    visited: set[str] = set()
    while frontier:
        if document_id in frontier:
            return True
        pending = frontier - visited
        if not pending:
            return False
        visited.update(pending)
        frontier = {
            ancestor_id
            for (ancestor_id,) in db.execute(
                select(TechnicalDocumentRelationship.related_document_id).where(
                    TechnicalDocumentRelationship.document_id.in_(pending)
                )
            )
            if ancestor_id not in visited
        }
    return False


def create_technical_document_relationship(
    db: Session,
    *,
    actor: User,
    document: TechnicalDocument,
    related_document_id: str,
    relationship_type: str,
    reason: str,
    scope: str | None = None,
    effective_date: date | None = None,
    source_ip: str | None = None,
    correlation_id: str | None = None,
) -> TechnicalDocumentRelationship:
    """Create one audited relationship without committing or changing either source.

    ``related_document_id`` is the public document identity. The relationship
    stores database UUIDs only after both retained source registrations resolve.
    Links can be added only while the newer/source document remains Draft.
    Runtime authority continues to be controlled exclusively by release
    publication.
    """

    if not isinstance(actor, User) or not actor.id or db.get(User, actor.id) is None:
        raise TechnicalDocumentLineageError("RELATIONSHIP_FIELDS_INCOMPLETE")
    if (
        not isinstance(document, TechnicalDocument)
        or not document.id
        or db.get(TechnicalDocument, document.id) is None
    ):
        raise TechnicalDocumentLineageError("RELATIONSHIP_FIELDS_INCOMPLETE")
    public_related_id = _required_text(
        related_document_id,
        required_code="RELATED_DOCUMENT_ID_INVALID",
        maximum=200,
        too_long_code="RELATED_DOCUMENT_ID_INVALID",
        invalid_code="RELATED_DOCUMENT_ID_INVALID",
    )
    if not isinstance(relationship_type, str):
        raise TechnicalDocumentLineageError(
            "RELATIONSHIP_TYPE_INVALID"
        )
    safe_relationship_type = relationship_type.strip()
    if safe_relationship_type not in TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES:
        raise TechnicalDocumentLineageError(
            "RELATIONSHIP_TYPE_INVALID"
        )
    safe_reason = _required_text(
        reason,
        required_code="RELATIONSHIP_REASON_INVALID",
        maximum=TECHNICAL_DOCUMENT_RELATIONSHIP_REASON_MAX_LENGTH,
        too_long_code="RELATIONSHIP_REASON_INVALID",
        invalid_code="RELATIONSHIP_REASON_INVALID",
    )
    safe_scope = _optional_text(
        scope,
        maximum=TECHNICAL_DOCUMENT_RELATIONSHIP_SCOPE_MAX_LENGTH,
        too_long_code="RELATIONSHIP_SCOPE_INVALID",
    )
    if effective_date is not None and (
        not isinstance(effective_date, date) or isinstance(effective_date, datetime)
    ):
        raise TechnicalDocumentLineageError(
            "RELATIONSHIP_EFFECTIVE_DATE_INVALID"
        )

    related = db.scalar(
        select(TechnicalDocument).where(
            TechnicalDocument.document_id == public_related_id
        )
    )
    if related is None:
        raise TechnicalDocumentLineageError(
            "RELATED_DOCUMENT_NOT_FOUND"
        )
    locked_documents = {
        item.id: item
        for item in db.scalars(
            select(TechnicalDocument)
            .where(TechnicalDocument.id.in_({document.id, related.id}))
            .order_by(TechnicalDocument.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    }
    locked_document = locked_documents.get(document.id)
    locked_related = locked_documents.get(related.id)
    if locked_document is None or locked_related is None:
        raise TechnicalDocumentLineageError("RELATIONSHIP_FIELDS_INCOMPLETE")
    document = locked_document
    related = locked_related
    if document.status != "draft":
        raise TechnicalDocumentLineageError("SOURCE_DOCUMENT_NOT_DRAFT")
    if document.id == related.id:
        raise TechnicalDocumentLineageError("RELATIONSHIP_SELF_REFERENCE")
    if (
        safe_relationship_type == "summary_of"
        and not technical_summary_source_target_is_eligible(related)
    ):
        raise TechnicalDocumentLineageError("SUMMARY_SOURCE_TARGET_INVALID")

    duplicate = db.scalar(
        select(TechnicalDocumentRelationship.id).where(
            TechnicalDocumentRelationship.document_id == document.id,
            TechnicalDocumentRelationship.related_document_id == related.id,
            TechnicalDocumentRelationship.relationship_type == safe_relationship_type,
        )
    )
    if duplicate is not None:
        raise TechnicalDocumentLineageError(
            "RELATIONSHIP_ALREADY_EXISTS"
        )
    if _would_create_cycle(
        db,
        document_id=document.id,
        related_document_id=related.id,
    ):
        raise TechnicalDocumentLineageError("RELATIONSHIP_CYCLE")

    relationship = TechnicalDocumentRelationship(
        document_id=document.id,
        related_document_id=related.id,
        relationship_type=safe_relationship_type,
        reason=safe_reason,
        scope=safe_scope,
        effective_date=effective_date,
        created_by_id=actor.id,
    )
    db.add(relationship)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="create_lineage_relationship",
        entity_type="technical_document_relationship",
        entity_id=relationship.id,
        new_value={
            "document_id": document.document_id,
            "related_document_id": related.document_id,
            "relationship_type": safe_relationship_type,
            "scope": safe_scope,
            "effective_date": effective_date.isoformat() if effective_date else None,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
        correlation_id=correlation_id,
    )
    return relationship


__all__ = [
    "TECHNICAL_DOCUMENT_RELATIONSHIP_LABELS",
    "TECHNICAL_DOCUMENT_RELATIONSHIP_REASON_MAX_LENGTH",
    "TECHNICAL_DOCUMENT_RELATIONSHIP_SCOPE_MAX_LENGTH",
    "TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES",
    "TechnicalDocumentLineageError",
    "create_technical_document_relationship",
]
