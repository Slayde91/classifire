"""Independent review receipts for immutable technical source documents."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import get_settings
from ..models import (
    Approval,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    User,
)
from .storage import StoredFileBindingError, require_stored_file_binding
from .technical_document_metadata import (
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
    TechnicalDocumentMetadataError,
    normalize_technical_source_registration,
)

TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE = "technical_document_review"
TECHNICAL_DOCUMENT_REVIEW_POLICY_V1 = "technical-document-review-v1"
TECHNICAL_DOCUMENT_REVIEW_POLICY_V2 = "technical-document-review-v2"
TECHNICAL_DOCUMENT_REVIEW_POLICY = TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
TECHNICAL_DOCUMENT_REVIEW_POLICIES = frozenset(
    {
        TECHNICAL_DOCUMENT_REVIEW_POLICY_V1,
        TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
    }
)
TECHNICAL_DOCUMENT_REVIEW_REASON_SCHEMA = "technical-document-review-reasons-v1"

_REVIEWABLE_STATUSES = frozenset({"draft", "rejected"})
_REASON_MAX_LENGTH = 4_000
_ERROR_CODES = frozenset(
    {
        "INDEPENDENT_SOURCE_REVIEWER_REQUIRED",
        "RELATED_SOURCE_FILE_INVALID",
        "RELATED_SOURCE_NOT_APPROVED",
        "RELATED_SOURCE_REVIEW_INVALID",
        "SUMMARY_SOURCE_RELATIONSHIP_REQUIRED",
        "SUMMARY_SOURCE_TARGET_INVALID",
        "SOURCE_DOCUMENT_NOT_FOUND",
        "SOURCE_DOCUMENT_NOT_REVIEWABLE",
        "SOURCE_DOCUMENT_REGISTRATION_REQUIRED",
        "SOURCE_RELATIONSHIP_NOT_YET_EFFECTIVE",
        "SOURCE_DOCUMENT_STATE_CHANGED",
        "SOURCE_FILE_INVALID",
        "SOURCE_REVIEW_ACTOR_INVALID",
        "SOURCE_REVIEW_DECISION_CHANGED",
        "SOURCE_REVIEW_REASON_INVALID",
        "SOURCE_REVIEW_REQUEST_REQUIRED",
        "SOURCE_REVIEW_SNAPSHOT_CHANGED",
    }
)


class TechnicalDocumentReviewError(ValueError):
    """A stable, presentation-safe source-review failure."""

    def __init__(self, code: str) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical-document review error code")
        self.code = code
        super().__init__(code)


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _canonical_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _reason(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REASON_INVALID")
    normalised = value.strip()
    if len(normalised) > _REASON_MAX_LENGTH or any(
        not character.isprintable() and character not in {"\r", "\n", "\t"}
        for character in normalised
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REASON_INVALID")
    return normalised


def _require_actor(db: Session, actor: User) -> None:
    if (
        not isinstance(actor, User)
        or not actor.id
        or db.get(User, actor.id) is None
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_ACTOR_INVALID")


def _updated_exactly_one(result: Any) -> bool:
    return getattr(result, "rowcount", 0) == 1


def technical_document_review_policy(document: TechnicalDocument) -> str | None:
    metadata = document.metadata_json
    if not isinstance(metadata, dict):
        return None
    policy = metadata.get("source_review_policy")
    return policy if policy in TECHNICAL_DOCUMENT_REVIEW_POLICIES else None


def technical_summary_source_target_is_eligible(
    document: TechnicalDocument,
) -> bool:
    """Return whether a summary edge terminates at reviewed full-source evidence."""

    # A v1 receipt does not bind the new evidence-scope field. Treating its
    # migrated NULL (or a later unbound value) as full-source evidence would
    # invent a classification that no reviewer approved.
    return (
        technical_document_review_policy(document)
        == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
        and document.evidence_scope == "full_source"
    )


def _relationship_is_currently_effective(
    relationship: TechnicalDocumentRelationship,
) -> bool:
    return (
        relationship.effective_date is None
        or relationship.effective_date <= date.today()
    )


def _require_current_source_registration(document: TechnicalDocument) -> None:
    metadata = document.metadata_json
    role = document.declared_source_role
    provenance = document.artifact_provenance_status
    evidence_scope = document.evidence_scope
    if (
        not isinstance(metadata, dict)
        or metadata.get("source_review_policy")
        != TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
        or metadata.get("source_registration_schema")
        != TECHNICAL_SOURCE_REGISTRATION_SCHEMA
        or metadata.get("human_review_required") is not True
        or not isinstance(role, str)
        or not isinstance(provenance, str)
        or not isinstance(evidence_scope, str)
    ):
        raise TechnicalDocumentReviewError(
            "SOURCE_DOCUMENT_REGISTRATION_REQUIRED"
        )
    try:
        normalize_technical_source_registration(
            document_type=document.document_type,
            declared_source_role=role,
            sponsor_organisation=document.sponsor_organisation,
            artifact_provenance_status=provenance,
            artifact_provenance_note=document.artifact_provenance_note,
            evidence_scope=evidence_scope,
            evidence_limitations=document.evidence_limitations,
        )
    except TechnicalDocumentMetadataError as exc:
        raise TechnicalDocumentReviewError(
            "SOURCE_DOCUMENT_REGISTRATION_REQUIRED"
        ) from exc


def _summary_source_requires_relationship(document: TechnicalDocument) -> bool:
    return (
        document.declared_source_role == "regulatory_summary"
        or document.evidence_scope == "summary_only"
    )


def _document_manifest(
    document: TechnicalDocument,
    *,
    policy: str,
) -> dict[str, Any]:
    """Fields a reviewer accepts, excluding mutable workflow projections."""

    manifest = {
        "id": document.id,
        "document_id": document.document_id,
        "stored_file_id": document.stored_file_id,
        "document_type": document.document_type,
        "manufacturer": document.manufacturer,
        "title": document.title,
        "reference": document.reference,
        "revision": document.revision,
        "issuing_organisation": document.issuing_organisation,
        "publication_date": _canonical_date(document.publication_date),
        "review_date": _canonical_date(document.review_date),
        "expiry_date": _canonical_date(document.expiry_date),
        "jurisdiction": document.jurisdiction,
        "standards": document.standards,
        "metadata_json": document.metadata_json,
        "supersedes_document_id": document.supersedes_document_id,
    }
    if policy == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2:
        manifest.update(
            {
                "declared_source_role": document.declared_source_role,
                "sponsor_organisation": document.sponsor_organisation,
                "artifact_provenance_status": document.artifact_provenance_status,
                "artifact_provenance_note": document.artifact_provenance_note,
                "evidence_scope": document.evidence_scope,
                "evidence_limitations": document.evidence_limitations,
            }
        )
    return manifest


def _stored_file_manifest(stored_file: StoredFile, *, storage_root: Path) -> dict[str, Any]:
    try:
        binding = require_stored_file_binding(
            stored_file,
            storage_root=storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError as exc:
        raise TechnicalDocumentReviewError("SOURCE_FILE_INVALID") from exc
    return {
        "id": stored_file.id,
        "original_filename": stored_file.original_filename,
        "media_type": stored_file.media_type,
        "sha256": binding.sha256,
        "size_bytes": binding.size_bytes,
        "suffix": binding.suffix,
        "purpose": binding.purpose,
        "malware_scan_status": stored_file.malware_scan_status,
        "immutable": stored_file.immutable,
    }


def latest_technical_document_review(
    db: Session,
    document_id: str,
    *,
    for_update: bool = False,
) -> Approval | None:
    statement = (
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document_id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at.desc(), Approval.id.desc())
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return db.scalar(statement)


def technical_document_review_reasons(approval: Approval) -> dict[str, str | None]:
    """Expose separate request and decision reasons from the generic text field."""

    raw = approval.decision_reason
    if approval.status == "pending":
        return {"request_reason": raw, "decision_reason": None}
    try:
        value = json.loads(raw or "")
    except (TypeError, ValueError) as exc:
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REQUEST_REQUIRED") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema") != TECHNICAL_DOCUMENT_REVIEW_REASON_SCHEMA
        or not isinstance(value.get("request_reason"), str)
        or not value["request_reason"].strip()
        or not isinstance(value.get("decision_reason"), str)
        or not value["decision_reason"].strip()
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REQUEST_REQUIRED")
    return {
        "request_reason": value["request_reason"],
        "decision_reason": value["decision_reason"],
    }


def _decided_reasons(*, request_reason: str, decision_reason: str) -> str:
    return json.dumps(
        {
            "schema": TECHNICAL_DOCUMENT_REVIEW_REASON_SCHEMA,
            "request_reason": request_reason,
            "decision_reason": decision_reason,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _review_receipt_manifest(
    db: Session,
    document: TechnicalDocument,
    *,
    storage_root: Path,
    visiting: frozenset[str],
) -> dict[str, Any]:
    policy = technical_document_review_policy(document)
    if policy is None:
        # A current review may only rely on other sources whose exact evidence
        # and outgoing lineage have themselves been independently reviewed
        # under a recognised versioned policy. Marker-less historical
        # approvals remain historical evidence; they do not become v3
        # authority merely by being linked from a new source.
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    approval = latest_technical_document_review(db, document.id)
    if approval is None:
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    if (
        approval.status != "approved"
        or not approval.requested_by_id
        or not approval.decided_by_id
        or approval.requested_by_id == approval.decided_by_id
        or not approval.decided_at
        or not approval.decision_reason
        or not approval.snapshot_hash
    ):
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    target_file = db.get(StoredFile, document.stored_file_id)
    if (
        document.reviewed_by_id != approval.decided_by_id
        or document.approved_by_id != approval.decided_by_id
        or _canonical_datetime(document.approved_at)
        != _canonical_datetime(approval.decided_at)
        or _uploader_id(document, target_file) == approval.decided_by_id
    ):
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    try:
        current_snapshot_hash = _technical_document_review_snapshot_hash(
            db,
            document.id,
            storage_root=storage_root,
            visiting=visiting,
        )
    except TechnicalDocumentReviewError as exc:
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID") from exc
    if current_snapshot_hash != approval.snapshot_hash:
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    try:
        reasons = technical_document_review_reasons(approval)
    except TechnicalDocumentReviewError as exc:
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID") from exc
    return {
        "policy": policy,
        "approval_id": approval.id,
        "approval_type": approval.approval_type,
        "requested_by_id": approval.requested_by_id,
        "decided_by_id": approval.decided_by_id,
        "decided_at": _canonical_datetime(approval.decided_at),
        "snapshot_hash": approval.snapshot_hash,
        "reasons": reasons,
    }


def _lock_review_graph(
    db: Session,
    document_id: str,
) -> tuple[
    TechnicalDocument,
    list[TechnicalDocumentRelationship],
    dict[str, TechnicalDocument],
    dict[str, StoredFile],
]:
    """Discover the full graph, lock it globally once, and reject graph drift."""

    document_ids = {document_id}
    discovered_signatures: set[tuple[Any, ...]] = set()
    while True:
        discovered_relationships = list(
            db.scalars(
                select(TechnicalDocumentRelationship)
                .where(TechnicalDocumentRelationship.document_id.in_(document_ids))
                .order_by(
                    TechnicalDocumentRelationship.document_id,
                    TechnicalDocumentRelationship.related_document_id,
                    TechnicalDocumentRelationship.relationship_type,
                    TechnicalDocumentRelationship.id,
                )
            ).all()
        )
        discovered_signatures = {
            (
                relationship.id,
                relationship.document_id,
                relationship.related_document_id,
                relationship.relationship_type,
                relationship.reason,
                relationship.scope,
                relationship.effective_date,
                relationship.created_by_id,
                relationship.record_version,
            )
            for relationship in discovered_relationships
        }
        expanded_document_ids = document_ids | {
            relationship.related_document_id
            for relationship in discovered_relationships
        }
        if expanded_document_ids == document_ids:
            break
        document_ids = expanded_document_ids
    # Discover bindings without locks so every source file can be locked before
    # any document. Reject the graph if a binding moves while locks are acquired.
    discovered_documents = {
        item.id: item
        for item in db.scalars(
            select(TechnicalDocument)
            .where(TechnicalDocument.id.in_(document_ids))
            .order_by(TechnicalDocument.id)
        ).all()
    }
    discovered_bindings = {
        item.id: item.stored_file_id
        for item in discovered_documents.values()
    }
    stored_file_ids = set(discovered_bindings.values())
    stored_files = {
        item.id: item
        for item in db.scalars(
            select(StoredFile)
            .where(StoredFile.id.in_(stored_file_ids))
            .order_by(StoredFile.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    }
    locked_documents = {
        item.id: item
        for item in db.scalars(
            select(TechnicalDocument)
            .where(TechnicalDocument.id.in_(document_ids))
            .order_by(TechnicalDocument.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    }
    if set(locked_documents) != document_ids:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    locked_bindings = {
        item.id: item.stored_file_id
        for item in locked_documents.values()
    }
    if locked_bindings != discovered_bindings:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    source = locked_documents.get(document_id)
    if source is None:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_FOUND")

    locked_relationships = list(
        db.scalars(
            select(TechnicalDocumentRelationship)
            .where(TechnicalDocumentRelationship.document_id.in_(document_ids))
            .order_by(
                TechnicalDocumentRelationship.document_id,
                TechnicalDocumentRelationship.related_document_id,
                TechnicalDocumentRelationship.relationship_type,
                TechnicalDocumentRelationship.id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )
    locked_signatures = {
        (
            relationship.id,
            relationship.document_id,
            relationship.related_document_id,
            relationship.relationship_type,
            relationship.reason,
            relationship.scope,
            relationship.effective_date,
            relationship.created_by_id,
            relationship.record_version,
        )
        for relationship in locked_relationships
    }
    if locked_signatures != discovered_signatures:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    relationships = sorted(
        (
            relationship
            for relationship in locked_relationships
            if relationship.document_id == document_id
        ),
        key=lambda relationship: (
            relationship.relationship_type,
            relationship.related_document_id,
            relationship.id,
        ),
    )

    return source, relationships, locked_documents, stored_files


def _technical_document_review_snapshot(
    db: Session,
    document_id: str,
    *,
    storage_root: Path,
    visiting: frozenset[str],
) -> dict[str, Any]:
    if document_id in visiting:
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    visiting = visiting | {document_id}
    source, relationships, documents, stored_files = _lock_review_graph(db, document_id)
    policy = technical_document_review_policy(source)
    if policy is None:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_REVIEWABLE")
    if any(
        relationship.relationship_type == "summary_of"
        and not _relationship_is_currently_effective(relationship)
        for relationship in relationships
    ):
        raise TechnicalDocumentReviewError(
            "SOURCE_RELATIONSHIP_NOT_YET_EFFECTIVE"
        )
    if _summary_source_requires_relationship(source) and not any(
        relationship.relationship_type == "summary_of"
        and _relationship_is_currently_effective(relationship)
        for relationship in relationships
    ):
        raise TechnicalDocumentReviewError("SUMMARY_SOURCE_RELATIONSHIP_REQUIRED")
    if source.supersedes_document_id is not None and not any(
        relationship.related_document_id == source.supersedes_document_id
        and relationship.relationship_type in {"revision_of", "replaces"}
        for relationship in relationships
    ):
        raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
    source_file = stored_files.get(source.stored_file_id)
    if source_file is None:
        raise TechnicalDocumentReviewError("SOURCE_FILE_INVALID")
    source_file_manifest = _stored_file_manifest(source_file, storage_root=storage_root)

    relationship_manifests: list[dict[str, Any]] = []
    for relationship in relationships:
        if (
            relationship.relationship_type == "summary_of"
            and not _relationship_is_currently_effective(relationship)
        ):
            raise TechnicalDocumentReviewError(
                "SOURCE_RELATIONSHIP_NOT_YET_EFFECTIVE"
            )
        target = documents.get(relationship.related_document_id)
        if target is None or target.status != "approved":
            raise TechnicalDocumentReviewError("RELATED_SOURCE_NOT_APPROVED")
        target_policy = technical_document_review_policy(target)
        if target_policy is None:
            raise TechnicalDocumentReviewError("RELATED_SOURCE_REVIEW_INVALID")
        if (
            relationship.relationship_type == "summary_of"
            and not technical_summary_source_target_is_eligible(target)
        ):
            raise TechnicalDocumentReviewError("SUMMARY_SOURCE_TARGET_INVALID")
        target_file = stored_files.get(target.stored_file_id)
        if target_file is None:
            raise TechnicalDocumentReviewError("RELATED_SOURCE_FILE_INVALID")
        try:
            target_file_manifest = _stored_file_manifest(
                target_file,
                storage_root=storage_root,
            )
        except TechnicalDocumentReviewError as exc:
            raise TechnicalDocumentReviewError("RELATED_SOURCE_FILE_INVALID") from exc
        relationship_manifests.append(
            {
                "id": relationship.id,
                "document_id": relationship.document_id,
                "related_document_id": relationship.related_document_id,
                "relationship_type": relationship.relationship_type,
                "reason": relationship.reason,
                "scope": relationship.scope,
                "effective_date": _canonical_date(relationship.effective_date),
                "created_by_id": relationship.created_by_id,
                "target_document": {
                    **_document_manifest(target, policy=target_policy),
                    "status": target.status,
                    "reviewed_by_id": target.reviewed_by_id,
                    "approved_by_id": target.approved_by_id,
                    "approved_at": _canonical_datetime(target.approved_at),
                },
                "target_stored_file": target_file_manifest,
                "target_review_receipt": _review_receipt_manifest(
                    db,
                    target,
                    storage_root=storage_root,
                    visiting=visiting,
                ),
            }
        )

    return {
        "policy": policy,
        "document": _document_manifest(source, policy=policy),
        "stored_file": source_file_manifest,
        "outgoing_relationships": relationship_manifests,
    }


def technical_document_review_snapshot(
    db: Session,
    document_id: str,
    *,
    storage_root: Path | None = None,
) -> dict[str, Any]:
    return _technical_document_review_snapshot(
        db,
        document_id,
        storage_root=storage_root or get_settings().storage_root,
        visiting=frozenset(),
    )


def _technical_document_review_snapshot_hash(
    db: Session,
    document_id: str,
    *,
    storage_root: Path,
    visiting: frozenset[str],
) -> str:
    raw = json.dumps(
        _technical_document_review_snapshot(
            db,
            document_id,
            storage_root=storage_root,
            visiting=visiting,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def technical_document_review_snapshot_hash(
    db: Session,
    document_id: str,
    *,
    storage_root: Path | None = None,
) -> str:
    return _technical_document_review_snapshot_hash(
        db,
        document_id,
        storage_root=storage_root or get_settings().storage_root,
        visiting=frozenset(),
    )


def _uploader_id(document: TechnicalDocument, stored_file: StoredFile | None) -> str | None:
    metadata = document.metadata_json
    if isinstance(metadata, dict):
        uploaded_by_id = metadata.get("uploaded_by_id")
        if isinstance(uploaded_by_id, str) and uploaded_by_id:
            return uploaded_by_id
    return stored_file.uploaded_by_id if stored_file is not None else None


def submit_technical_document_review(
    db: Session,
    *,
    actor: User,
    document_id: str,
    reason: str,
    storage_root: Path | None = None,
    source_ip: str | None = None,
) -> Approval:
    """Freeze one review request without committing or granting authority."""

    _require_actor(db, actor)
    safe_reason = _reason(reason)
    document, relationships, _documents, _files = _lock_review_graph(db, document_id)
    if document.status not in _REVIEWABLE_STATUSES:
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_REVIEWABLE")
    _require_current_source_registration(document)
    if any(
        relationship.relationship_type == "summary_of"
        and not _relationship_is_currently_effective(relationship)
        for relationship in relationships
    ):
        raise TechnicalDocumentReviewError(
            "SOURCE_RELATIONSHIP_NOT_YET_EFFECTIVE"
        )
    if _summary_source_requires_relationship(document) and not any(
        relationship.relationship_type == "summary_of"
        and _relationship_is_currently_effective(relationship)
        for relationship in relationships
    ):
        raise TechnicalDocumentReviewError("SUMMARY_SOURCE_RELATIONSHIP_REQUIRED")
    previous_status = document.status
    transition = db.execute(
        update(TechnicalDocument)
        .where(
            TechnicalDocument.id == document.id,
            TechnicalDocument.status == previous_status,
        )
        .values(
            status="in_review",
            reviewed_by_id=None,
            approved_by_id=None,
            approved_at=None,
            record_version=TechnicalDocument.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(transition):
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    db.expire(document)
    db.refresh(document)
    snapshot_hash = technical_document_review_snapshot_hash(
        db,
        document.id,
        storage_root=storage_root,
    )
    approval = Approval(
        entity_type="technical_document",
        entity_id=document.id,
        approval_type=TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        status="pending",
        requested_by_id=actor.id,
        decision_reason=safe_reason,
        snapshot_hash=snapshot_hash,
    )
    db.add(approval)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="submit_source_review",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": previous_status},
        new_value={
            "status": "in_review",
            "approval_id": approval.id,
            "snapshot_hash": snapshot_hash,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    return approval


def approve_technical_document_review(
    db: Session,
    *,
    actor: User,
    document_id: str,
    reason: str,
    storage_root: Path | None = None,
    source_ip: str | None = None,
) -> Approval:
    """Approve exactly the independently submitted source-review snapshot."""

    _require_actor(db, actor)
    safe_reason = _reason(reason)
    document, _relationships, _documents, stored_files = _lock_review_graph(db, document_id)
    if document.status != "in_review":
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_REVIEWABLE")
    _require_current_source_registration(document)
    approval = latest_technical_document_review(db, document.id, for_update=True)
    if (
        approval is None
        or approval.status != "pending"
        or not approval.requested_by_id
        or not approval.decision_reason
        or not approval.snapshot_hash
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REQUEST_REQUIRED")
    request_reason = approval.decision_reason
    source_file = stored_files.get(document.stored_file_id)
    if (
        approval.requested_by_id == actor.id
        or _uploader_id(document, source_file) == actor.id
    ):
        raise TechnicalDocumentReviewError("INDEPENDENT_SOURCE_REVIEWER_REQUIRED")
    current_snapshot_hash = technical_document_review_snapshot_hash(
        db,
        document.id,
        storage_root=storage_root,
    )
    if current_snapshot_hash != approval.snapshot_hash:
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_SNAPSHOT_CHANGED")

    decided_at = datetime.now(UTC)
    document_transition = db.execute(
        update(TechnicalDocument)
        .where(
            TechnicalDocument.id == document.id,
            TechnicalDocument.status == "in_review",
        )
        .values(
            status="approved",
            reviewed_by_id=actor.id,
            approved_by_id=actor.id,
            approved_at=decided_at,
            record_version=TechnicalDocument.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(document_transition):
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    approval_transition = db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "pending",
            Approval.requested_by_id == approval.requested_by_id,
            Approval.snapshot_hash == approval.snapshot_hash,
            Approval.decision_reason == request_reason,
        )
        .values(
            status="approved",
            decided_by_id=actor.id,
            decided_at=decided_at,
            decision_reason=_decided_reasons(
                request_reason=request_reason,
                decision_reason=safe_reason,
            ),
            record_version=Approval.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(approval_transition):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_DECISION_CHANGED")
    record_audit(
        db,
        actor=actor,
        action="approve_source_review",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": "in_review"},
        new_value={
            "status": "approved",
            "approval_id": approval.id,
            "requested_by_id": approval.requested_by_id,
            "decided_by_id": actor.id,
            "snapshot_hash": approval.snapshot_hash,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    db.expire(approval)
    db.refresh(approval)
    return approval


def reject_technical_document_review(
    db: Session,
    *,
    actor: User,
    document_id: str,
    reason: str,
    source_ip: str | None = None,
) -> Approval:
    """Reject a pending review; rejection never grants evidence authority."""

    _require_actor(db, actor)
    safe_reason = _reason(reason)
    document, _relationships, _documents, stored_files = _lock_review_graph(db, document_id)
    if document.status != "in_review":
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_REVIEWABLE")
    approval = latest_technical_document_review(db, document.id, for_update=True)
    if (
        approval is None
        or approval.status != "pending"
        or not approval.requested_by_id
        or not approval.decision_reason
        or not approval.snapshot_hash
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REQUEST_REQUIRED")
    request_reason = approval.decision_reason
    source_file = stored_files.get(document.stored_file_id)
    if (
        approval.requested_by_id == actor.id
        or _uploader_id(document, source_file) == actor.id
    ):
        raise TechnicalDocumentReviewError("INDEPENDENT_SOURCE_REVIEWER_REQUIRED")

    decided_at = datetime.now(UTC)
    document_transition = db.execute(
        update(TechnicalDocument)
        .where(
            TechnicalDocument.id == document.id,
            TechnicalDocument.status == "in_review",
        )
        .values(
            status="rejected",
            reviewed_by_id=actor.id,
            approved_by_id=None,
            approved_at=None,
            record_version=TechnicalDocument.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(document_transition):
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    approval_transition = db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "pending",
            Approval.requested_by_id == approval.requested_by_id,
            Approval.snapshot_hash == approval.snapshot_hash,
            Approval.decision_reason == request_reason,
        )
        .values(
            status="rejected",
            decided_by_id=actor.id,
            decided_at=decided_at,
            decision_reason=_decided_reasons(
                request_reason=request_reason,
                decision_reason=safe_reason,
            ),
            record_version=Approval.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(approval_transition):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_DECISION_CHANGED")
    record_audit(
        db,
        actor=actor,
        action="reject_source_review",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": "in_review"},
        new_value={
            "status": "rejected",
            "approval_id": approval.id,
            "requested_by_id": approval.requested_by_id,
            "decided_by_id": actor.id,
            "submitted_snapshot_hash": approval.snapshot_hash,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    db.expire(approval)
    db.refresh(approval)
    return approval


def request_technical_document_review_changes(
    db: Session,
    *,
    actor: User,
    document_id: str,
    reason: str,
    source_ip: str | None = None,
) -> Approval:
    """Return a submitted source to Draft without granting evidence authority."""

    _require_actor(db, actor)
    safe_reason = _reason(reason)
    document, _relationships, _documents, stored_files = _lock_review_graph(db, document_id)
    if document.status != "in_review":
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_NOT_REVIEWABLE")
    approval = latest_technical_document_review(db, document.id, for_update=True)
    if (
        approval is None
        or approval.status != "pending"
        or not approval.requested_by_id
        or not approval.decision_reason
        or not approval.snapshot_hash
    ):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_REQUEST_REQUIRED")
    request_reason = approval.decision_reason
    source_file = stored_files.get(document.stored_file_id)
    if (
        approval.requested_by_id == actor.id
        or _uploader_id(document, source_file) == actor.id
    ):
        raise TechnicalDocumentReviewError("INDEPENDENT_SOURCE_REVIEWER_REQUIRED")

    decided_at = datetime.now(UTC)
    document_transition = db.execute(
        update(TechnicalDocument)
        .where(
            TechnicalDocument.id == document.id,
            TechnicalDocument.status == "in_review",
        )
        .values(
            status="draft",
            reviewed_by_id=None,
            approved_by_id=None,
            approved_at=None,
            record_version=TechnicalDocument.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(document_transition):
        raise TechnicalDocumentReviewError("SOURCE_DOCUMENT_STATE_CHANGED")
    approval_transition = db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "pending",
            Approval.requested_by_id == approval.requested_by_id,
            Approval.snapshot_hash == approval.snapshot_hash,
            Approval.decision_reason == request_reason,
        )
        .values(
            status="changes_requested",
            decided_by_id=actor.id,
            decided_at=decided_at,
            decision_reason=_decided_reasons(
                request_reason=request_reason,
                decision_reason=safe_reason,
            ),
            record_version=Approval.record_version + 1,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(approval_transition):
        raise TechnicalDocumentReviewError("SOURCE_REVIEW_DECISION_CHANGED")
    record_audit(
        db,
        actor=actor,
        action="request_source_changes",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": "in_review"},
        new_value={
            "status": "draft",
            "approval_id": approval.id,
            "review_status": "changes_requested",
            "requested_by_id": approval.requested_by_id,
            "decided_by_id": actor.id,
            "submitted_snapshot_hash": approval.snapshot_hash,
            "runtime_eligible": False,
        },
        reason=safe_reason,
        source_ip=source_ip,
    )
    db.expire(approval)
    db.refresh(approval)
    return approval


__all__ = [
    "TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE",
    "TECHNICAL_DOCUMENT_REVIEW_POLICY",
    "TECHNICAL_DOCUMENT_REVIEW_POLICIES",
    "TECHNICAL_DOCUMENT_REVIEW_POLICY_V1",
    "TECHNICAL_DOCUMENT_REVIEW_POLICY_V2",
    "TECHNICAL_DOCUMENT_REVIEW_REASON_SCHEMA",
    "TechnicalDocumentReviewError",
    "approve_technical_document_review",
    "latest_technical_document_review",
    "reject_technical_document_review",
    "request_technical_document_review_changes",
    "submit_technical_document_review",
    "technical_document_review_snapshot",
    "technical_document_review_snapshot_hash",
    "technical_document_review_reasons",
    "technical_document_review_policy",
    "technical_summary_source_target_is_eligible",
]
