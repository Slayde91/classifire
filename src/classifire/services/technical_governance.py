from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    Approval,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
)
from .storage import (
    StoredFileBinding,
    StoredFileBindingError,
    require_stored_file_binding,
)
from .technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
    TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
    TechnicalDocumentReviewError,
    latest_technical_document_review,
    technical_document_review_policy,
    technical_document_review_reasons,
    technical_document_review_snapshot,
    technical_document_review_snapshot_hash,
    technical_summary_source_target_is_eligible,
)

TECHNICAL_REVIEW_APPROVAL_TYPE = "technical_review"
PENDING_TECHNICAL_REVIEW = "EXCLUDE_PENDING_TECHNICAL_REVIEW"
APPROVED_RELEASE_CANDIDATE = "INCLUDE_APPROVED_RELEASE_CANDIDATE"
TECHNICAL_VARIANT_UI_INTAKE_POLICY = "technical-variant-ui-draft-v1"
GOVERNED_TECHNICAL_RELEASE_POLICY_V2 = "technical-authority-registry-v2"
GOVERNED_TECHNICAL_RELEASE_POLICY_V3 = "technical-authority-registry-v3"
GOVERNED_TECHNICAL_RELEASE_POLICY = GOVERNED_TECHNICAL_RELEASE_POLICY_V3
GOVERNED_TECHNICAL_RELEASE_POLICIES = frozenset(
    {
        GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
        GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    }
)
TECHNICAL_RUNTIME_SOURCE_ROLES = frozenset({"primary_test", "assessment"})
TECHNICAL_REVIEW_POLICY_V2 = "technical-review-v2"
TECHNICAL_REVIEW_POLICY_V3 = "technical-review-v3"

_SNAPSHOT_EXCLUDED_COLUMNS = {
    "id",
    "created_at",
    "updated_at",
    "record_version",
    "status",
    "release_id",
}

_DOCUMENT_SNAPSHOT_EXCLUDED_COLUMNS = {
    "created_at",
    "updated_at",
    "record_version",
}

_DOCUMENT_REVIEW_V2_COLUMNS = frozenset(
    {
        "declared_source_role",
        "sponsor_organisation",
        "artifact_provenance_status",
        "artifact_provenance_note",
        "evidence_scope",
        "evidence_limitations",
    }
)


class TechnicalGovernanceError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class TechnicalSourceBinding:
    binding_policy: str
    document: dict[str, Any]
    stored_file: dict[str, Any]
    file_binding: StoredFileBinding
    source_review: dict[str, Any] | None = None
    outgoing_relationships: tuple[dict[str, Any], ...] | None = None

    def manifest(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "document": self.document,
            "stored_file": self.stored_file,
        }
        if self.binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
            manifest["binding_policy"] = self.binding_policy
        if self.source_review is not None:
            manifest["source_review"] = self.source_review
        if self.outgoing_relationships is not None:
            manifest["outgoing_relationships"] = list(self.outgoing_relationships)
        return manifest


def technical_variant_snapshot(variant: TechnicalVariant) -> dict[str, Any]:
    """Return every material variant field covered by technical approval."""
    return {
        column.name: getattr(variant, column.name)
        for column in TechnicalVariant.__table__.columns
        if column.name not in _SNAPSHOT_EXCLUDED_COLUMNS
    }


def technical_variant_snapshot_hash(variant: TechnicalVariant) -> str:
    raw = json.dumps(
        technical_variant_snapshot(variant),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def technical_variant_author_id(variant: TechnicalVariant) -> str | None:
    """Return the server-recorded author of the current candidate, when known."""

    source = variant.source_json if isinstance(variant.source_json, dict) else {}
    if source.get("user_revision") is True:
        author_id = source.get("revision_created_by_id")
    elif source.get("intake_policy") == TECHNICAL_VARIANT_UI_INTAKE_POLICY:
        author_id = source.get("created_by_id")
    else:
        return None
    return author_id if isinstance(author_id, str) and author_id else None


def _canonical_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _json_snapshot_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def technical_document_snapshot(document: TechnicalDocument) -> dict[str, Any]:
    review_policy = technical_document_review_policy(document)
    return {
        column.name: _json_snapshot_value(getattr(document, column.name))
        for column in TechnicalDocument.__table__.columns
        if column.name not in _DOCUMENT_SNAPSHOT_EXCLUDED_COLUMNS
        and (
            column.name not in _DOCUMENT_REVIEW_V2_COLUMNS
            or review_policy == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
        )
    }


def technical_approval_binding(approval: Approval) -> dict[str, Any]:
    return {
        "id": approval.id,
        "entity_type": approval.entity_type,
        "entity_id": approval.entity_id,
        "approval_type": approval.approval_type,
        "status": approval.status,
        "requested_by_id": approval.requested_by_id,
        "decided_by_id": approval.decided_by_id,
        "requested_at": _canonical_datetime(approval.requested_at),
        "decided_at": _canonical_datetime(approval.decided_at),
        "decision_reason": approval.decision_reason,
        "snapshot_hash": approval.snapshot_hash,
    }


def _require_v3_source_graph_contract(
    db: Session,
    root_document: TechnicalDocument,
) -> None:
    """Require a supported review policy and typed lineage on every graph node."""

    document_ids = {root_document.id}
    relationships: list[TechnicalDocumentRelationship] = []
    while True:
        relationships = list(
            db.scalars(
                select(TechnicalDocumentRelationship).where(
                    TechnicalDocumentRelationship.document_id.in_(document_ids)
                )
            ).all()
        )
        expanded = document_ids | {
            relationship.related_document_id for relationship in relationships
        }
        if expanded == document_ids:
            break
        document_ids = expanded
    documents = {
        document.id: document
        for document in db.scalars(
            select(TechnicalDocument).where(TechnicalDocument.id.in_(document_ids))
        ).all()
    }
    if set(documents) != document_ids:
        raise TechnicalGovernanceError("source_graph_document_missing")
    relationships_by_source: dict[str, list[TechnicalDocumentRelationship]] = {}
    for relationship in relationships:
        if (
            relationship.effective_date is not None
            and relationship.effective_date > date.today()
        ):
            raise TechnicalGovernanceError("source_relationship_not_yet_effective")
        relationships_by_source.setdefault(relationship.document_id, []).append(
            relationship
        )
    for document in documents.values():
        if document.expiry_date and document.expiry_date < date.today():
            raise TechnicalGovernanceError("source_graph_document_expired")
        if document.evidence_scope == "bibliographic_only":
            raise TechnicalGovernanceError(
                "bibliographic_source_not_runtime_eligible"
            )
        if (
            document.declared_source_role == "regulatory_summary"
            or document.evidence_scope == "summary_only"
        ):
            raise TechnicalGovernanceError("summary_source_not_runtime_eligible")
        if technical_document_review_policy(document) is None:
            raise TechnicalGovernanceError("source_graph_review_policy_required")
        review = latest_technical_document_review(db, document.id)
        if (
            review is None
            or review.status != "approved"
            or not review.snapshot_hash
            or not review.decided_by_id
            or not review.decided_at
        ):
            raise TechnicalGovernanceError(
                "source_document_review_required"
                if document.id == root_document.id
                else "source_graph_review_required"
            )
        if document.supersedes_document_id is not None and not any(
            relationship.related_document_id == document.supersedes_document_id
            and relationship.relationship_type in {"revision_of", "replaces"}
            for relationship in relationships_by_source.get(document.id, [])
        ):
            raise TechnicalGovernanceError(
                "source_graph_legacy_supersession_requires_typed_lineage"
            )
        document_relationships = relationships_by_source.get(document.id, [])
        summary_relationships = [
            relationship
            for relationship in document_relationships
            if relationship.relationship_type == "summary_of"
        ]
        if any(
            not technical_summary_source_target_is_eligible(
                documents[relationship.related_document_id]
            )
            for relationship in summary_relationships
        ):
            raise TechnicalGovernanceError("summary_source_target_invalid")
        if (
            document.declared_source_role == "regulatory_summary"
            or document.evidence_scope == "summary_only"
        ) and not summary_relationships:
            raise TechnicalGovernanceError("summary_source_relationship_required")


def require_technical_source_binding(
    db: Session,
    variant: TechnicalVariant,
    *,
    binding_policy: str = GOVERNED_TECHNICAL_RELEASE_POLICY,
    storage_root: Path | None = None,
    stored_binding_cache: dict[str, StoredFileBinding] | None = None,
) -> TechnicalSourceBinding:
    if binding_policy not in GOVERNED_TECHNICAL_RELEASE_POLICIES:
        raise TechnicalGovernanceError("technical_source_binding_policy_invalid")
    if not variant.technical_document_id:
        raise TechnicalGovernanceError("approved_source_document_required")
    document = db.get(TechnicalDocument, variant.technical_document_id)
    if document is None:
        raise TechnicalGovernanceError("approved_source_document_required")
    if not variant.source_document_reference or not variant.source_page:
        raise TechnicalGovernanceError("source_locator_incomplete")
    if variant.source_document_reference.strip() != document.document_id:
        raise TechnicalGovernanceError("source_document_reference_mismatch")
    if document.status != "approved":
        raise TechnicalGovernanceError("source_document_not_approved")
    if document.expiry_date and document.expiry_date < date.today():
        raise TechnicalGovernanceError("source_document_expired")
    if document.evidence_scope == "bibliographic_only":
        raise TechnicalGovernanceError("bibliographic_source_not_runtime_eligible")
    source_review_policy = technical_document_review_policy(document)
    if (
        document.declared_source_role == "regulatory_summary"
        or document.evidence_scope == "summary_only"
    ):
        raise TechnicalGovernanceError("summary_source_not_runtime_eligible")
    if (
        source_review_policy == TECHNICAL_DOCUMENT_REVIEW_POLICY_V2
        and document.declared_source_role not in TECHNICAL_RUNTIME_SOURCE_ROLES
    ):
        raise TechnicalGovernanceError("source_role_not_runtime_eligible")
    if not document.reviewed_by_id or not document.approved_by_id or not document.approved_at:
        raise TechnicalGovernanceError("source_document_approval_incomplete")
    outgoing_relationship_types = set(
        db.scalars(
            select(TechnicalDocumentRelationship.relationship_type).where(
                TechnicalDocumentRelationship.document_id == document.id
            )
        ).all()
    )
    if (
        document.declared_source_role == "regulatory_summary"
        or document.evidence_scope == "summary_only"
    ) and "summary_of" not in outgoing_relationship_types:
        raise TechnicalGovernanceError("summary_source_relationship_required")
    has_outgoing_lineage = bool(outgoing_relationship_types)
    if (
        binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2
        and has_outgoing_lineage
    ):
        # v2 release manifests do not bind typed source lineage. Keep the
        # reviewed source available as evidence, but do not present its graph
        # as runtime technical authority until a versioned v3 policy does.
        raise TechnicalGovernanceError("source_lineage_requires_v3_release_binding")

    stored_file = db.get(StoredFile, document.stored_file_id)
    if stored_file is None:
        raise TechnicalGovernanceError("source_file_missing")
    file_binding = (
        stored_binding_cache.get(stored_file.id) if stored_binding_cache is not None else None
    )
    if file_binding is None:
        try:
            file_binding = require_stored_file_binding(
                stored_file,
                storage_root=storage_root or get_settings().storage_root,
                required_purpose="technical_evidence",
            )
        except StoredFileBindingError as exc:
            raise TechnicalGovernanceError(exc.code) from exc
        if stored_binding_cache is not None:
            stored_binding_cache[stored_file.id] = file_binding

    source_review_manifest: dict[str, Any] | None = None
    outgoing_relationships: tuple[dict[str, Any], ...] | None = None
    review_snapshot: dict[str, Any] | None = None
    metadata = document.metadata_json
    has_supported_review_policy = source_review_policy is not None
    if (
        binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        and not has_supported_review_policy
    ):
        raise TechnicalGovernanceError("source_document_review_policy_required")
    if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
        _require_v3_source_graph_contract(db, document)
    requires_independent_source_review = (
        binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
        or has_supported_review_policy
    )
    if requires_independent_source_review:
        source_review = latest_technical_document_review(db, document.id)
        if source_review is None or source_review.status != "approved":
            raise TechnicalGovernanceError("source_document_review_required")
        if (
            not source_review.requested_by_id
            or not source_review.decided_by_id
            or not source_review.requested_at
            or not source_review.decided_at
            or not source_review.decision_reason
            or not source_review.snapshot_hash
        ):
            raise TechnicalGovernanceError("source_document_review_incomplete")
        uploader_id = metadata.get("uploaded_by_id") if isinstance(metadata, dict) else None
        if (
            source_review.requested_by_id == source_review.decided_by_id
            or uploader_id == source_review.decided_by_id
            or document.reviewed_by_id != source_review.decided_by_id
            or document.approved_by_id != source_review.decided_by_id
            or _canonical_datetime(document.approved_at)
            != _canonical_datetime(source_review.decided_at)
        ):
            raise TechnicalGovernanceError(
                "independent_source_document_reviewer_required"
            )
        try:
            source_review_reasons = technical_document_review_reasons(source_review)
            current_source_review_hash = technical_document_review_snapshot_hash(
                db,
                document.id,
                storage_root=storage_root or get_settings().storage_root,
            )
        except TechnicalDocumentReviewError as exc:
            raise TechnicalGovernanceError("source_document_review_invalid") from exc
        if current_source_review_hash != source_review.snapshot_hash:
            raise TechnicalGovernanceError("source_document_review_snapshot_changed")
        source_review_manifest = {
            "policy": source_review_policy,
            **technical_approval_binding(source_review),
            "reasons": source_review_reasons,
        }
        if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
            try:
                review_snapshot = technical_document_review_snapshot(
                    db,
                    document.id,
                    storage_root=storage_root or get_settings().storage_root,
                )
            except TechnicalDocumentReviewError as exc:
                raise TechnicalGovernanceError("source_document_review_invalid") from exc
            relationships = review_snapshot.get("outgoing_relationships")
            if not isinstance(relationships, list) or any(
                not isinstance(item, dict) for item in relationships
            ):
                raise TechnicalGovernanceError("source_document_review_invalid")
            outgoing_relationships = tuple(relationships)

    document_manifest = technical_document_snapshot(document)
    stored_file_manifest = {
        "id": stored_file.id,
        "original_filename": stored_file.original_filename,
        "media_type": stored_file.media_type,
        "sha256": file_binding.sha256,
        "size_bytes": file_binding.size_bytes,
        "purpose": stored_file.purpose,
        "malware_scan_status": stored_file.malware_scan_status,
        "immutable": stored_file.immutable,
    }
    if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3:
        reviewed_document = review_snapshot.get("document") if review_snapshot else None
        reviewed_stored_file = review_snapshot.get("stored_file") if review_snapshot else None
        if not isinstance(reviewed_document, dict) or not isinstance(
            reviewed_stored_file, dict
        ):
            raise TechnicalGovernanceError("source_document_review_invalid")
        document_manifest = reviewed_document
        stored_file_manifest = reviewed_stored_file

    return TechnicalSourceBinding(
        binding_policy=binding_policy,
        document=document_manifest,
        stored_file=stored_file_manifest,
        file_binding=file_binding,
        source_review=source_review_manifest,
        outgoing_relationships=outgoing_relationships,
    )


def technical_review_snapshot_hash(
    variant: TechnicalVariant,
    source_binding: TechnicalSourceBinding,
    *,
    review_policy: str | None = None,
) -> str:
    if review_policy is None:
        review_policy = (
            TECHNICAL_REVIEW_POLICY_V3
            if source_binding.binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
            else TECHNICAL_REVIEW_POLICY_V2
        )
    payload: dict[str, Any] = {
        "variant": technical_variant_snapshot(variant),
        "source_binding": source_binding.manifest(),
    }
    if review_policy == TECHNICAL_REVIEW_POLICY_V3:
        payload["review_policy"] = review_policy
    elif review_policy != TECHNICAL_REVIEW_POLICY_V2:
        raise TechnicalGovernanceError("technical_review_policy_invalid")
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def latest_technical_review(db: Session, variant_id: str) -> Approval | None:
    return db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant_id,
            Approval.approval_type == TECHNICAL_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    )


def technical_source_file(db: Session, variant: TechnicalVariant) -> StoredFile | None:
    if not variant.technical_document_id:
        return None
    document = db.get(TechnicalDocument, variant.technical_document_id)
    return db.get(StoredFile, document.stored_file_id) if document else None


def technical_source_reviewer_ids(db: Session, document_id: str) -> set[str]:
    """Return reviewers for the root source and every transitive outgoing target."""

    document_ids = {document_id}
    while True:
        related_ids = set(
            db.scalars(
                select(TechnicalDocumentRelationship.related_document_id).where(
                    TechnicalDocumentRelationship.document_id.in_(document_ids)
                )
            ).all()
        )
        expanded = document_ids | related_ids
        if expanded == document_ids:
            break
        document_ids = expanded

    reviewers: set[str] = set()
    documents = db.scalars(
        select(TechnicalDocument).where(TechnicalDocument.id.in_(document_ids))
    ).all()
    for document in documents:
        if document.reviewed_by_id:
            reviewers.add(document.reviewed_by_id)
        if document.approved_by_id:
            reviewers.add(document.approved_by_id)
    approvals = db.scalars(
        select(Approval).where(
            Approval.entity_type == "technical_document",
            Approval.entity_id.in_(document_ids),
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
            Approval.status == "approved",
        )
    ).all()
    reviewers.update(
        approval.decided_by_id for approval in approvals if approval.decided_by_id
    )
    return reviewers


def release_candidate_blockers(
    db: Session,
    variant: TechnicalVariant,
    *,
    binding_policy: str = GOVERNED_TECHNICAL_RELEASE_POLICY,
    storage_root: Path | None = None,
    stored_binding_cache: dict[str, StoredFileBinding] | None = None,
) -> tuple[list[str], Approval | None, TechnicalSourceBinding | None]:
    """Explain why an approved candidate cannot enter a governed release."""
    blockers: list[str] = []
    approval = latest_technical_review(db, variant.id)

    if variant.status != "approved":
        blockers.append("variant_not_approved")
    if variant.search_eligibility != APPROVED_RELEASE_CANDIDATE:
        blockers.append("release_candidate_not_search_eligible")
    source_binding: TechnicalSourceBinding | None = None
    try:
        source_binding = require_technical_source_binding(
            db,
            variant,
            binding_policy=binding_policy,
            storage_root=storage_root,
            stored_binding_cache=stored_binding_cache,
        )
    except TechnicalGovernanceError as exc:
        blockers.append(exc.code)

    if variant.effective_date and variant.effective_date > date.today():
        blockers.append("variant_not_yet_effective")
    if variant.expiry_date and variant.expiry_date < date.today():
        blockers.append("variant_expired")

    if approval is None or approval.status != "approved":
        blockers.append("approved_review_required")
    elif (
        approval.entity_type != "technical_variant"
        or approval.entity_id != variant.id
        or approval.approval_type != TECHNICAL_REVIEW_APPROVAL_TYPE
    ):
        blockers.append("review_scope_mismatch")
    elif (
        not approval.requested_by_id
        or not approval.decided_by_id
        or not approval.requested_at
        or not approval.decided_at
        or not approval.decision_reason
    ):
        blockers.append("review_decision_incomplete")
    elif approval.requested_by_id == approval.decided_by_id:
        blockers.append("independent_reviewer_required")
    elif approval.decided_by_id == technical_variant_author_id(variant):
        blockers.append("independent_candidate_author_reviewer_required")
    elif source_binding is not None and approval.snapshot_hash != technical_review_snapshot_hash(
        variant,
        source_binding,
        review_policy=(
            TECHNICAL_REVIEW_POLICY_V3
            if binding_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
            else TECHNICAL_REVIEW_POLICY_V2
        ),
    ):
        blockers.append("approved_snapshot_changed")

    return blockers, approval, source_binding
