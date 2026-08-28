from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import (
    Approval,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    PricingLibraryRecord,
    Product,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
    User,
)
from .security import has_permission, verify_csrf
from .services.release_scope import ReleaseScopeError, validate_release
from .services.storage import StoredFileBinding
from .services.technical_document_review import TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE
from .services.technical_governance import (
    APPROVED_RELEASE_CANDIDATE,
    GOVERNED_TECHNICAL_RELEASE_POLICIES,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    TECHNICAL_REVIEW_APPROVAL_TYPE,
    release_candidate_blockers,
    technical_approval_binding,
    technical_source_reviewer_ids,
    technical_variant_snapshot_hash,
)
from .services.technical_retirement import (
    TECHNICAL_RETIREMENT_APPROVAL_TYPE,
    TechnicalRetirementError,
    current_technical_retirement,
    latest_technical_retirement,
    technical_release_record,
    validate_technical_retirement_approval,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]

SUPPORTED_TYPES = ("pricing", "technical", "rules", "labour", "products", "markups")


@dataclass(frozen=True)
class TechnicalReleaseSnapshot:
    records: list[dict[str, Any]]
    approved_ids: list[str]
    carried_ids: list[str]
    carried_v2_ids: list[str]
    superseded_ids: list[str]
    retired_ids: list[str]
    retirement_bindings: list[dict[str, Any]]


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _is_publication_conflict(exc: IntegrityError | OperationalError) -> bool:
    original = getattr(exc, "orig", exc)
    sqlstate = getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)
    if sqlstate in {"40001", "40P01", "55P03"}:
        return True
    message = str(original).lower()
    return any(
        marker in message
        for marker in (
            "uq_library_release_active_publication_slot",
            "uq_library_release_type_version",
            "library_releases.active_publication_slot",
            "library_releases.library_type, library_releases.version",
            "database is locked",
            "database table is locked",
            "could not obtain lock",
            "deadlock detected",
            "serialization failure",
        )
    )


def _publication_conflict_response() -> RedirectResponse:
    return RedirectResponse(
        "/releases?error=TECHNICAL_RELEASE_PUBLICATION_CONFLICT_RETRY:+"
        "publication+state+changed;+refresh+and+review+before+retrying",
        status_code=303,
    )


def _logical_key(record: Any, release_type: str) -> str:
    if release_type == "pricing":
        return str(record.pkb_entry_id)
    if release_type == "rules":
        return str(record.rule_code)
    if release_type == "labour":
        return str(record.code)
    if release_type == "products":
        return str(record.sku)
    if release_type == "technical":
        source = record.source_json or {}
        return str(source.get("original_variant_id") or record.variant_id.split("-QFREV")[0])
    return str(record.id)


def _latest_release(db: Session, release_type: str) -> LibraryRelease | None:
    statement = select(LibraryRelease).where(
        LibraryRelease.library_type == release_type,
        LibraryRelease.status == "active",
    )
    if release_type == "technical":
        statement = statement.where(LibraryRelease.active_publication_slot == "technical")
    return db.scalar(statement.order_by(LibraryRelease.created_at.desc()))


def _latest_valid_technical_release(db: Session) -> LibraryRelease | None:
    governed = db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.status == "active",
            LibraryRelease.active_publication_slot == "technical",
        )
        .order_by(LibraryRelease.created_at.desc())
    )
    if governed is not None:
        try:
            validate_release(db, governed, "technical", allowed_statuses={"active"})
        except ReleaseScopeError as exc:
            raise ValueError(
                "ACTIVE_TECHNICAL_RELEASE_INVALID: repair or explicitly migrate the "
                "current published release before creating another."
            ) from exc
        return governed

    releases = db.scalars(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.status == "active",
            LibraryRelease.active_publication_slot.is_(None),
        )
        .order_by(LibraryRelease.created_at.desc())
    ).all()
    for release in releases:
        manifest = release.source_manifest or {}
        if not manifest.get("records"):
            # Legacy import batches are intake provenance, not published releases.
            continue
        try:
            validate_release(
                db,
                release,
                "technical",
                allowed_statuses={"active"},
                allow_legacy_technical=True,
            )
        except ReleaseScopeError as exc:
            raise ValueError(
                "ACTIVE_TECHNICAL_RELEASE_INVALID: repair or explicitly migrate the "
                "current published release before creating another."
            ) from exc
        return release
    return None


def _relationship_lock_signature(
    relationship: TechnicalDocumentRelationship,
) -> tuple[Any, ...]:
    return (
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


def _lock_technical_publication_state(
    db: Session,
    *,
    publisher_id: str,
) -> list[TechnicalVariant]:
    """Lock and refresh every row that can define the next Technical release."""
    publisher = db.scalar(
        select(User)
        .where(User.id == publisher_id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
    )
    if (
        publisher is None
        or not publisher.is_active
        or not has_permission(publisher, "technical:publish")
    ):
        raise ValueError(
            "TECHNICAL_RELEASE_PUBLISHER_AUTHORITY_CHANGED: sign in again and retry."
        )
    db.scalars(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.status == "active",
        )
        .order_by(LibraryRelease.id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
    ).all()
    referenced_ancestor_ids = select(TechnicalVariant.supersedes_id).where(
        TechnicalVariant.status.in_({"active", "approved"}),
        TechnicalVariant.supersedes_id.is_not(None),
    )
    locked_variants = db.scalars(
        select(TechnicalVariant)
        .where(
            or_(
                TechnicalVariant.status.in_({"active", "approved"}),
                TechnicalVariant.id.in_(referenced_ancestor_ids),
            )
        )
        .order_by(TechnicalVariant.id)
        .with_for_update(nowait=True)
        .execution_options(populate_existing=True)
    ).all()
    variants = [
        variant
        for variant in locked_variants
        if variant.status in {"active", "approved"}
    ]
    variant_ids = [variant.id for variant in variants]
    locked_variant_ids = {variant.id for variant in locked_variants}
    if any(
        variant.supersedes_id
        and variant.supersedes_id not in locked_variant_ids
        for variant in variants
    ):
        raise ValueError("TECHNICAL_RELEASE_UNPUBLISHED_ANCESTOR_MISSING")
    if variant_ids:
        db.scalars(
            select(Approval)
            .where(
                Approval.entity_type == "technical_variant",
                Approval.entity_id.in_(variant_ids),
                Approval.approval_type.in_(
                    {
                        TECHNICAL_REVIEW_APPROVAL_TYPE,
                        TECHNICAL_RETIREMENT_APPROVAL_TYPE,
                    }
                ),
            )
            .order_by(Approval.id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        ).all()
    document_ids = {
        variant.technical_document_id
        for variant in variants
        if variant.technical_document_id is not None
    }
    documents: list[TechnicalDocument] = []
    discovered_relationships: list[TechnicalDocumentRelationship] = []
    discovered_relationship_signatures: set[tuple[Any, ...]] = set()
    if document_ids:
        # Discover the closure without locks first, then acquire every document
        # lock once in global ID order. Never discover a lower-ID target after
        # already holding a higher-ID source lock.
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
            related_ids = {
                relationship.related_document_id
                for relationship in discovered_relationships
            }
            discovered_relationship_signatures = {
                _relationship_lock_signature(relationship)
                for relationship in discovered_relationships
            }
            expanded_document_ids = document_ids | related_ids
            if expanded_document_ids == document_ids:
                break
            document_ids = expanded_document_ids
        documents = list(
            db.scalars(
                select(TechnicalDocument)
                .where(TechnicalDocument.id.in_(document_ids))
                .order_by(TechnicalDocument.id)
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            ).all()
        )
        if {document.id for document in documents} != document_ids:
            raise ValueError("TECHNICAL_SOURCE_GRAPH_DOCUMENT_MISSING")
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
                .with_for_update(nowait=True)
                .execution_options(populate_existing=True)
            ).all()
        )
        if {
            _relationship_lock_signature(relationship)
            for relationship in locked_relationships
        } != discovered_relationship_signatures:
            raise ValueError("TECHNICAL_SOURCE_GRAPH_CHANGED_RETRY")
    stored_file_ids = {document.stored_file_id for document in documents}
    if stored_file_ids:
        db.scalars(
            select(StoredFile)
            .where(StoredFile.id.in_(stored_file_ids))
            .order_by(StoredFile.id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        ).all()
    if document_ids:
        db.scalars(
            select(Approval)
            .where(
                Approval.entity_type == "technical_document",
                Approval.entity_id.in_(document_ids),
                Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
            )
            .order_by(Approval.entity_id, Approval.created_at, Approval.id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        ).all()
    return list(variants)


def _technical_release_snapshot(
    db: Session,
    previous: LibraryRelease | None,
    *,
    eligible_variants: list[TechnicalVariant] | None = None,
    publisher_id: str | None = None,
) -> TechnicalReleaseSnapshot:
    by_key: dict[str, tuple[TechnicalVariant, dict[str, Any]]] = {}
    previous_key_by_id: dict[str, str] = {}
    previous_record_by_id: dict[
        str, tuple[TechnicalVariant, dict[str, Any]]
    ] = {}
    eligible_by_id = (
        {variant.id: variant for variant in eligible_variants}
        if eligible_variants is not None
        else None
    )
    retired_ids: list[str] = []
    retirement_bindings: list[dict[str, Any]] = []
    if previous is not None:
        manifest = previous.source_manifest or {}
        previous_policy = manifest.get("governance_policy")
        if previous_policy not in GOVERNED_TECHNICAL_RELEASE_POLICIES:
            raise ValueError(
                "LEGACY_TECHNICAL_RELEASE_REQUIRES_MIGRATION: existing published "
                "records must be reviewed before a governed release can replace them."
            )
        for item in manifest.get("records", []):
            if not isinstance(item, dict):
                raise ValueError("PREVIOUS_TECHNICAL_RELEASE_RECORD_MALFORMED")
            record = (
                eligible_by_id.get(str(item.get("id") or ""))
                if eligible_by_id is not None
                else db.get(TechnicalVariant, item.get("id"))
            )
            if record is None:
                raise ValueError("PREVIOUS_TECHNICAL_RELEASE_RECORD_MISSING")
            key = _logical_key(record, "technical")
            previous_key_by_id[record.id] = key
            previous_record_by_id[record.id] = (record, dict(item))
            if record.status != "active":
                raise ValueError(
                    f"PREVIOUS_TECHNICAL_RELEASE_STATE_INVALID: {record.variant_id!r} "
                    f"is {record.status!r}, expected 'active'."
                )
            copied_item = dict(item)
            if previous_policy == GOVERNED_TECHNICAL_RELEASE_POLICY_V2:
                if "record_binding_policy" in copied_item:
                    raise ValueError("PREVIOUS_V2_RECORD_POLICY_MALFORMED")
                copied_item["record_binding_policy"] = GOVERNED_TECHNICAL_RELEASE_POLICY_V2
            elif copied_item.get("record_binding_policy") not in (
                GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
                GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
            ):
                raise ValueError("PREVIOUS_V3_RECORD_POLICY_MALFORMED")
            if key in by_key:
                raise ValueError(
                    f"PREVIOUS_TECHNICAL_RELEASE_DUPLICATE_KEY: {key!r}"
                )
            by_key[key] = (record, copied_item)

    approved = (
        sorted(
            (
                variant
                for variant in eligible_variants
                if variant.status == "approved"
            ),
            key=lambda variant: (variant.created_at, variant.id),
            reverse=True,
        )
        if eligible_variants is not None
        else list(
            db.scalars(
                select(TechnicalVariant)
                .where(TechnicalVariant.status == "approved")
                .order_by(TechnicalVariant.created_at.desc())
            ).all()
        )
    )
    approved_by_key: dict[str, TechnicalVariant] = {}
    for record in approved:
        key = _logical_key(record, "technical")
        if key in approved_by_key:
            raise ValueError(
                f"MULTIPLE_APPROVED_TECHNICAL_CANDIDATES: logical key {key!r} "
                "has more than one approved candidate."
            )
        approved_by_key[key] = record

    approved_ids: list[str] = []
    superseded_ids: list[str] = []
    stored_binding_cache: dict[str, StoredFileBinding] = {}
    governed_release_manifests = [
        release.source_manifest or {}
        for release in db.scalars(
            select(LibraryRelease).where(LibraryRelease.library_type == "technical")
        ).all()
        if (release.source_manifest or {}).get("governance_policy")
        in GOVERNED_TECHNICAL_RELEASE_POLICIES
    ]
    governed_record_ids = {
        str(item.get("id") or "")
        for manifest in governed_release_manifests
        for item in manifest.get("records", [])
        if isinstance(item, dict) and item.get("id")
    }
    for key, record in approved_by_key.items():
        blockers, approval, source_binding = release_candidate_blockers(
            db,
            record,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
            stored_binding_cache=stored_binding_cache,
        )
        if blockers or approval is None or source_binding is None:
            details = ",".join(blockers) or "approved_review_required"
            raise ValueError(
                f"TECHNICAL_RELEASE_CANDIDATE_BLOCKED: {record.variant_id!r}: {details}"
            )
        replaced = by_key.get(key)
        claimed_previous_key = (
            previous_key_by_id.get(record.supersedes_id)
            if record.supersedes_id
            else None
        )
        if claimed_previous_key is not None and claimed_previous_key != key:
            raise ValueError(
                "TECHNICAL_RELEASE_REPLACEMENT_KEY_MISMATCH: "
                f"{record.variant_id!r} claims a predecessor under a different key."
            )
        if replaced and replaced[0].id != record.id:
            if record.supersedes_id != replaced[0].id:
                raise ValueError(
                    "TECHNICAL_RELEASE_REPLACEMENT_LINEAGE_MISMATCH: "
                    f"{record.variant_id!r} must supersede {replaced[0].variant_id!r}."
                )
            superseded_ids.append(replaced[0].id)
        unpublished_supersedes_binding: dict[str, str] | None = None
        if record.supersedes_id and claimed_previous_key is None:
            ancestor = db.get(TechnicalVariant, record.supersedes_id)
            if (
                ancestor is None
                or ancestor.id == record.id
                or ancestor.status not in {"draft", "rejected"}
                or _logical_key(ancestor, "technical") != key
                or ancestor.id in governed_record_ids
            ):
                raise ValueError(
                    "TECHNICAL_RELEASE_UNPUBLISHED_ANCESTOR_INVALID: "
                    f"{record.variant_id!r} does not bind an unpublished same-key "
                    "Draft or Rejected intake ancestor."
                )
            unpublished_supersedes_binding = {
                "id": ancestor.id,
                "key": key,
                "record_hash": technical_variant_snapshot_hash(ancestor),
            }
        record_hash = technical_variant_snapshot_hash(record)
        by_key[key] = (
            record,
            {
                "id": record.id,
                "key": key,
                "variant_id": record.variant_id,
                "system_id": record.system_id,
                "frl": record.frl,
                "source_document_reference": record.source_document_reference,
                "source_page": record.source_page,
                "source_hash": record.source_hash,
                "technical_document_id": record.technical_document_id,
                "source_binding": source_binding.manifest(),
                "approval_binding": technical_approval_binding(approval),
                "record_hash": record_hash,
                "record_version": record.record_version,
                "governance_basis": "approved_technical_review",
                "record_binding_policy": GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
                "unpublished_supersedes_binding": unpublished_supersedes_binding,
            },
        )
        approved_ids.append(record.id)

    for target_id, (target, predecessor_item) in sorted(
        previous_record_by_id.items(),
        key=lambda item: item[0],
    ):
        if previous is None:
            raise ValueError('TECHNICAL_RETIREMENT_PREDECESSOR_REQUIRED')
        try:
            retirement = current_technical_retirement(
                db,
                previous,
                predecessor_item,
                target,
            )
            if retirement is None or retirement.status != 'approved':
                continue
            retirement_binding = validate_technical_retirement_approval(
                retirement,
                previous,
                predecessor_item,
                target,
            )
        except TechnicalRetirementError as exc:
            raise ValueError(
                f'TECHNICAL_RELEASE_RETIREMENT_BLOCKED: {target.variant_id!r}: '
                f'{exc.code}'
            ) from exc
        key = previous_key_by_id[target_id]
        current = by_key.get(key)
        if (
            target_id in superseded_ids
            or current is None
            or current[0].id != target_id
        ):
            raise ValueError(
                'TECHNICAL_RELEASE_RETIREMENT_REPLACEMENT_CONFLICT: '
                f'{target.variant_id!r} cannot be retired and replaced in one release.'
            )
        if publisher_id is not None and publisher_id in {
            retirement.requested_by_id,
            retirement.decided_by_id,
        }:
            raise ValueError(
                'TECHNICAL_RETIREMENT_INDEPENDENT_PUBLISHER_REQUIRED: '
                f'{target.variant_id!r}.'
            )
        if (
            publisher_id is not None
            and target.technical_document_id
            and publisher_id
            in technical_source_reviewer_ids(db, target.technical_document_id)
        ):
            raise ValueError(
                'TECHNICAL_RETIREMENT_INDEPENDENT_SOURCE_PUBLISHER_REQUIRED: '
                f'{target.variant_id!r}.'
            )
        del by_key[key]
        retired_ids.append(target_id)
        retirement_bindings.append(retirement_binding)

    records = [item for _record, item in by_key.values()]
    records.sort(key=lambda item: (str(item.get("key") or ""), str(item.get("id") or "")))
    approved_id_set = set(approved_ids)
    carried_ids = sorted(
        str(item["id"])
        for item in records
        if str(item["id"]) not in approved_id_set
    )
    carried_v2_ids = sorted(
        str(item["id"])
        for item in records
        if str(item["id"]) in set(carried_ids)
        and item.get("record_binding_policy") == GOVERNED_TECHNICAL_RELEASE_POLICY_V2
    )
    return TechnicalReleaseSnapshot(
        records=records,
        approved_ids=sorted(approved_ids),
        carried_ids=carried_ids,
        carried_v2_ids=carried_v2_ids,
        superseded_ids=sorted(superseded_ids),
        retired_ids=sorted(retired_ids),
        retirement_bindings=sorted(
            retirement_bindings,
            key=lambda item: str(
                (item.get('request_context') or {}).get(
                    'predecessor_record_id'
                )
                or ''
            ),
        ),
    )


def _technical_retirement_preview(
    db: Session,
    release: LibraryRelease | None,
) -> list[dict[str, Any]]:
    if release is None:
        return []
    previews: list[dict[str, Any]] = []
    records = (release.source_manifest or {}).get('records')
    if not isinstance(records, list):
        return []
    for raw_record in records:
        if not isinstance(raw_record, dict):
            continue
        variant_id = str(raw_record.get('id') or '')
        variant = db.get(TechnicalVariant, variant_id) if variant_id else None
        if variant is None:
            continue
        try:
            record = technical_release_record(release, variant.id)
            retirement = current_technical_retirement(
                db,
                release,
                record,
                variant,
            )
            if retirement is None or retirement.status != 'approved':
                continue
            binding = validate_technical_retirement_approval(
                retirement,
                release,
                record,
                variant,
            )
            valid = True
            error = None
        except TechnicalRetirementError as exc:
            retirement = latest_technical_retirement(db, variant.id)
            if retirement is None or retirement.status not in {'pending', 'approved'}:
                continue
            binding = None
            valid = False
            error = exc.code
        request_context = (
            binding.get('request_context') if isinstance(binding, dict) else {}
        ) or {}
        previews.append(
            {
                'variant_id': variant.variant_id,
                'record_id': variant.id,
                'logical_key': raw_record.get('key'),
                'request_reason': request_context.get('request_reason'),
                'decision_reason': (
                    binding.get('decision_reason')
                    if isinstance(binding, dict)
                    else None
                ),
                'reviewer_id': retirement.decided_by_id,
                'valid': valid,
                'error': error,
            }
        )
    return sorted(previews, key=lambda item: str(item['record_id']))


def _count_status(db: Session, model: Any) -> dict[str, int]:
    return {
        status: count
        for status, count in db.execute(
            select(model.status, func.count()).group_by(model.status)
        ).all()
    }


def _activate_drafts(db: Session, release_type: str) -> list[str]:
    activated_ids: list[str] = []

    if release_type == "pricing":
        pricing_drafts = db.scalars(
            select(PricingLibraryRecord).where(PricingLibraryRecord.status == "draft")
        ).all()
        for pricing_draft in pricing_drafts:
            pricing_prior = db.scalars(
                select(PricingLibraryRecord).where(
                    PricingLibraryRecord.pkb_entry_id == pricing_draft.pkb_entry_id,
                    PricingLibraryRecord.status == "active",
                    PricingLibraryRecord.id != pricing_draft.id,
                )
            ).all()
            for prior_item in pricing_prior:
                prior_item.status = "superseded"
            pricing_draft.status = "active"
            pricing_draft.effective_date = pricing_draft.effective_date or date.today()
            activated_ids.append(pricing_draft.id)

    elif release_type == "rules":
        rule_drafts = db.scalars(
            select(EstimatingRule).where(EstimatingRule.status == "draft")
        ).all()
        for rule_draft in rule_drafts:
            rule_prior = db.scalars(
                select(EstimatingRule).where(
                    EstimatingRule.rule_code == rule_draft.rule_code,
                    EstimatingRule.status == "active",
                    EstimatingRule.id != rule_draft.id,
                )
            ).all()
            for prior_rule in rule_prior:
                prior_rule.status = "superseded"
                prior_rule.expiry_date = date.today()
            rule_draft.status = "active"
            rule_draft.effective_date = rule_draft.effective_date or date.today()
            rule_draft.approved_at = rule_draft.approved_at or datetime.now(UTC)
            activated_ids.append(rule_draft.id)

    elif release_type == "labour":
        labour_drafts = db.scalars(
            select(LabourComponent).where(LabourComponent.status == "draft")
        ).all()
        for labour_draft in labour_drafts:
            labour_prior = db.scalars(
                select(LabourComponent).where(
                    LabourComponent.code == labour_draft.code,
                    LabourComponent.status == "active",
                    LabourComponent.id != labour_draft.id,
                )
            ).all()
            for prior_labour in labour_prior:
                prior_labour.status = "superseded"
                prior_labour.expiry_date = date.today()
            labour_draft.status = "active"
            labour_draft.effective_date = labour_draft.effective_date or date.today()
            activated_ids.append(labour_draft.id)

    elif release_type == "products":
        product_drafts = db.scalars(
            select(Product).where(Product.status == "draft")
        ).all()
        for product_draft in product_drafts:
            product_prior = db.scalars(
                select(Product).where(
                    Product.sku == product_draft.sku,
                    Product.status == "active",
                    Product.id != product_draft.id,
                )
            ).all()
            for prior_product in product_prior:
                prior_product.status = "superseded"
                prior_product.expiry_date = date.today()
            product_draft.status = "active"
            product_draft.effective_date = product_draft.effective_date or date.today()
            activated_ids.append(product_draft.id)

    # Technical records must already have passed their dedicated approval gate.
    # Markup profiles are already activated through the markup workflow.
    return activated_ids


def _snapshot_records(db: Session, release_type: str) -> list[dict[str, Any]]:
    if release_type == "pricing":
        pricing_records = db.scalars(
            select(PricingLibraryRecord)
            .where(PricingLibraryRecord.status == "active")
            .order_by(PricingLibraryRecord.pkb_entry_id, PricingLibraryRecord.created_at.desc())
        ).all()
        pricing_chosen: dict[str, PricingLibraryRecord] = {}
        for pricing_record in pricing_records:
            pricing_chosen.setdefault(pricing_record.pkb_entry_id, pricing_record)
        return [
            {
                "id": record.id,
                "key": record.pkb_entry_id,
                "entry_version": record.entry_version,
                "rate_ex_tax": str(record.rate_ex_tax),
                "source_hash": record.source_hash,
                "record_version": record.record_version,
            }
            for record in pricing_chosen.values()
        ]

    if release_type == "technical":
        previous = _latest_valid_technical_release(db)
        return _technical_release_snapshot(db, previous).records

    if release_type == "rules":
        rule_records = db.scalars(
            select(EstimatingRule)
            .where(EstimatingRule.status == "active")
            .order_by(EstimatingRule.rule_code, EstimatingRule.version.desc())
        ).all()
        rule_chosen: dict[str, EstimatingRule] = {}
        for rule_record in rule_records:
            rule_chosen.setdefault(rule_record.rule_code, rule_record)
        return [
            {
                "id": record.id,
                "key": record.rule_code,
                "version": record.version,
                "conditions": record.conditions,
                "actions": record.actions,
                "record_version": record.record_version,
            }
            for record in rule_chosen.values()
        ]

    if release_type == "labour":
        labour_records = db.scalars(
            select(LabourComponent)
            .where(LabourComponent.status == "active")
            .order_by(LabourComponent.code, LabourComponent.revision.desc())
        ).all()
        labour_chosen: dict[str, LabourComponent] = {}
        for labour_record in labour_records:
            labour_chosen.setdefault(labour_record.code, labour_record)
        return [
            {
                "id": record.id,
                "key": record.code,
                "revision": record.revision,
                "base_rate": str(record.base_rate),
                "default_markup": str(record.default_markup or 0),
                "record_version": record.record_version,
            }
            for record in labour_chosen.values()
        ]

    if release_type == "products":
        product_records = db.scalars(
            select(Product)
            .where(Product.status == "active")
            .order_by(Product.sku, Product.revision.desc())
        ).all()
        product_chosen: dict[str, Product] = {}
        for product_record in product_records:
            product_chosen.setdefault(product_record.sku, product_record)
        return [
            {
                "id": record.id,
                "key": record.sku,
                "revision": record.revision,
                "base_cost": str(record.base_cost),
                "default_markup": str(record.default_markup or 0),
                "record_version": record.record_version,
            }
            for record in product_chosen.values()
        ]

    if release_type == "markups":
        markup_records = db.scalars(
            select(MarkupProfile)
            .where(MarkupProfile.status == "active")
            .order_by(
                MarkupProfile.scope_type, MarkupProfile.scope_id, MarkupProfile.created_at.desc()
            )
        ).all()
        return [
            {
                "id": record.id,
                "key": f"{record.scope_type}:{record.scope_id or 'global'}",
                "product_markup": str(record.product_markup or 0),
                "material_markup": str(record.material_markup or 0),
                "labour_markup": str(record.labour_markup or 0),
                "record_version": record.record_version,
            }
            for record in markup_records
        ]

    raise ValueError(f"Unsupported release type: {release_type}")


@router.get("/releases", response_class=HTMLResponse)
def releases_page(request: Request, db: Db) -> HTMLResponse:
    user = _require(request, db, "library:read")
    releases = db.scalars(
        select(LibraryRelease).order_by(LibraryRelease.created_at.desc()).limit(100)
    ).all()
    counts = {
        "pricing": _count_status(db, PricingLibraryRecord),
        "technical": _count_status(db, TechnicalVariant),
        "rules": _count_status(db, EstimatingRule),
        "labour": _count_status(db, LabourComponent),
        "products": _count_status(db, Product),
        "markups": _count_status(db, MarkupProfile),
    }
    latest = {kind: _latest_release(db, kind) for kind in SUPPORTED_TYPES}
    technical_retirements = _technical_retirement_preview(
        db,
        latest.get('technical'),
    )
    publishable_types = [
        kind
        for kind in SUPPORTED_TYPES
        if has_permission(
            user,
            "pricing:approve"
            if kind in {"pricing", "labour", "products", "markups"}
            else "technical:publish"
            if kind == "technical"
            else "rule:approve",
        )
    ]
    return templates.TemplateResponse(
        request,
        "releases.html",
        _context(
            request,
            db,
            releases=releases,
            counts=counts,
            latest=latest,
            technical_retirements=technical_retirements,
            supported_types=SUPPORTED_TYPES,
            publishable_types=publishable_types,
        ),
    )


@router.get("/releases/{release_id}", response_class=HTMLResponse)
def release_detail(release_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    release = db.get(LibraryRelease, release_id)
    if not release:
        raise HTTPException(404, "Release not found")
    manifest = release.source_manifest or {}
    records = manifest.get("records", [])
    return templates.TemplateResponse(
        request,
        "release_detail.html",
        _context(request, db, release=release, manifest=manifest, records=records),
    )


@router.post("/releases/publish")
def publish_release(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    release_type: Annotated[str, Form()],
    version: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    activate_drafts: Annotated[str | None, Form()] = None,
    expected_previous_release_id: Annotated[str, Form()] = "",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    if release_type not in SUPPORTED_TYPES:
        raise HTTPException(400, "Unsupported release type")
    permission = (
        "pricing:approve"
        if release_type in {"pricing", "labour", "products", "markups"}
        else "technical:publish"
        if release_type == "technical"
        else "rule:approve"
    )
    user = _require(request, db, permission)

    existing = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == release_type,
            LibraryRelease.version == version,
        )
    )
    if existing:
        return RedirectResponse("/releases?error=Release+version+already+exists", status_code=303)

    activated_ids: list[str] = []
    if activate_drafts == "yes":
        if release_type == "technical":
            return RedirectResponse(
                "/releases?error=Technical+Drafts+must+be+approved+through+the+Technical+Systems+workflow+before+release",
                status_code=303,
            )
        activated_ids = _activate_drafts(db, release_type)

    technical_snapshot: TechnicalReleaseSnapshot | None = None
    try:
        if release_type == "technical":
            locked_eligible_variants = _lock_technical_publication_state(
                db,
                publisher_id=user.id,
            )
            previous = _latest_valid_technical_release(db)
            if previous is not None and (
                (previous.source_manifest or {}).get("governance_policy")
                not in GOVERNED_TECHNICAL_RELEASE_POLICIES
            ):
                raise ValueError(
                    "LEGACY_TECHNICAL_RELEASE_REQUIRES_MIGRATION: existing published "
                    "records must be reviewed before a governed release can replace them."
                )
            expected_previous = expected_previous_release_id.strip() or None
            current_previous = previous.id if previous else None
            if expected_previous != current_previous:
                raise ValueError(
                    "TECHNICAL_RELEASE_PREDECESSOR_CHANGED_RETRY: publication state "
                    "changed; refresh and review before retrying."
                )
            technical_snapshot = _technical_release_snapshot(
                db,
                previous,
                eligible_variants=locked_eligible_variants,
                publisher_id=user.id,
            )
            records = technical_snapshot.records
            if any(
                (record.get("approval_binding") or {}).get("decided_by_id") == user.id
                for record in records
            ):
                raise ValueError(
                    "TECHNICAL_RELEASE_INDEPENDENT_PUBLISHER_REQUIRED: the publisher "
                    "cannot be the technical reviewer for a record in the release."
                )
            source_document_ids = {
                str(record.get("technical_document_id") or "")
                for record in records
                if record.get("technical_document_id")
            }
            source_reviewer_ids = set().union(
                *(
                    technical_source_reviewer_ids(db, document_id)
                    for document_id in sorted(source_document_ids)
                )
            ) if source_document_ids else set()
            if user.id in source_reviewer_ids:
                raise ValueError(
                    "TECHNICAL_RELEASE_INDEPENDENT_SOURCE_PUBLISHER_REQUIRED: the "
                    "publisher cannot be a root or related source-document reviewer."
                )
        else:
            previous = _latest_release(db, release_type)
            records = _snapshot_records(db, release_type)
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        if _is_publication_conflict(exc):
            return _publication_conflict_response()
        raise
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/releases?error={quote_plus(str(exc))}",
            status_code=303,
        )
    if not records and not (
        technical_snapshot is not None and technical_snapshot.retired_ids
    ):
        db.rollback()
        return RedirectResponse(
            "/releases?error=No+eligible+records+exist+for+this+release", status_code=303
        )

    publication_timestamp = datetime.now(UTC)
    payload = {
        "release_type": release_type,
        "version": version,
        "created_at": publication_timestamp.isoformat(),
        "created_by_id": user.id,
        "record_count": len(records),
        "activated_draft_ids": activated_ids,
        "previous_release_id": previous.id if previous else None,
        "records": records,
        "notes": notes,
    }
    if technical_snapshot is not None:
        payload.update(
            {
                "governance_policy": GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
                "previous_release": (
                    {
                        "id": previous.id,
                        "hash": previous.release_hash,
                        "policy": (previous.source_manifest or {}).get(
                            "governance_policy"
                        ),
                    }
                    if previous
                    else None
                ),
                "activated_candidate_ids": technical_snapshot.approved_ids,
                "carried_record_ids": technical_snapshot.carried_ids,
                "carried_forward_v2_record_ids": technical_snapshot.carried_v2_ids,
                "superseded_record_ids": technical_snapshot.superseded_ids,
                "retired_record_ids": technical_snapshot.retired_ids,
                "runtime_authority": "release_manifest_membership",
            }
        )
    if technical_snapshot is not None:
        payload['retirement_bindings'] = technical_snapshot.retirement_bindings
    release_hash = _canonical_hash(payload)

    try:
        if previous:
            if release_type == "technical":
                previous_transition = db.execute(
                    update(LibraryRelease)
                    .where(
                        LibraryRelease.id == previous.id,
                        LibraryRelease.status == "active",
                        LibraryRelease.active_publication_slot == "technical",
                    )
                    .values(status="superseded", active_publication_slot=None)
                )
                if getattr(previous_transition, "rowcount", 0) != 1:
                    raise ValueError(
                        "TECHNICAL_RELEASE_PREDECESSOR_CHANGED_RETRY: publication state "
                        "changed; refresh and review before retrying."
                    )
            else:
                previous.status = "superseded"
            db.flush()

        release = LibraryRelease(
            library_type=release_type,
            version=version,
            status="active",
            effective_date=date.today(),
            release_hash=release_hash,
            source_manifest=payload,
            notes=notes,
            created_by_id=user.id,
            approved_by_id=user.id,
            supersedes_release_id=previous.id if previous else None,
            active_publication_slot="technical" if release_type == "technical" else None,
            created_at=publication_timestamp,
            approved_at=publication_timestamp,
        )
        db.add(release)
        db.flush()

        if release_type == 'technical' and technical_snapshot is not None:
            for retirement_binding in technical_snapshot.retirement_bindings:
                request_context = retirement_binding.get('request_context') or {}
                approval_binding = retirement_binding.get('approval_binding') or {}
                retired_id = str(
                    request_context.get('predecessor_record_id') or ''
                )
                retirement = db.execute(
                    update(TechnicalVariant)
                    .where(
                        TechnicalVariant.id == retired_id,
                        TechnicalVariant.status == 'active',
                    )
                    .values(status='retired')
                )
                if getattr(retirement, 'rowcount', 0) != 1:
                    raise ValueError(
                        'TECHNICAL_RELEASE_RETIRED_STATE_CHANGED_RETRY: predecessor '
                        'record changed; refresh and review before retrying.'
                    )
                technical_variant = db.get(TechnicalVariant, retired_id)
                if technical_variant is not None:
                    record_audit(
                        db,
                        actor=user,
                        action='retire_via_technical_release',
                        entity_type='technical_variant',
                        entity_id=retired_id,
                        previous_value={'status': 'active'},
                        new_value={
                            'status': 'retired',
                            'retirement_release_id': release.id,
                            'retirement_approval_id': approval_binding.get('id'),
                        },
                        reason=str(
                            retirement_binding.get('decision_reason')
                            or request_context.get('request_reason')
                            or notes
                        ),
                    )

        # Associate newly activated Draft records with the newly published release.
        if release_type == "pricing":
            for rid in activated_ids:
                pricing_item = db.get(PricingLibraryRecord, rid)
                if pricing_item:
                    pricing_item.release_id = release.id
        elif release_type == "rules":
            for rid in activated_ids:
                rule_item = db.get(EstimatingRule, rid)
                if rule_item:
                    rule_item.release_id = release.id
                    rule_item.approver_id = user.id
        elif release_type == "labour":
            for rid in activated_ids:
                labour_item = db.get(LabourComponent, rid)
                if labour_item:
                    labour_item.release_id = release.id
        elif release_type == "products":
            for rid in activated_ids:
                product_item = db.get(Product, rid)
                if product_item:
                    product_item.release_id = release.id
        elif release_type == "technical" and technical_snapshot is not None:
            for rid in technical_snapshot.approved_ids:
                activation = db.execute(
                    update(TechnicalVariant)
                    .where(
                        TechnicalVariant.id == rid,
                        TechnicalVariant.status == "approved",
                        TechnicalVariant.search_eligibility
                        == APPROVED_RELEASE_CANDIDATE,
                    )
                    .values(status="active")
                )
                if getattr(activation, "rowcount", 0) != 1:
                    raise ValueError(
                        "TECHNICAL_RELEASE_CANDIDATE_STATE_CHANGED_RETRY: publication "
                        "candidate changed; refresh and review before retrying."
                    )
                technical_variant = db.get(TechnicalVariant, rid)
                if technical_variant is not None:
                    record_audit(
                        db,
                        actor=user,
                        action="activate_via_technical_release",
                        entity_type="technical_variant",
                        entity_id=technical_variant.id,
                        previous_value={"status": "approved"},
                        new_value={
                            "status": "active",
                            "published_release_id": release.id,
                            "intake_release_id": technical_variant.release_id,
                        },
                        reason=notes or f"Publish technical release {version}",
                    )
            for rid in technical_snapshot.superseded_ids:
                supersession = db.execute(
                    update(TechnicalVariant)
                    .where(
                        TechnicalVariant.id == rid,
                        TechnicalVariant.status == "active",
                    )
                    .values(status="superseded")
                )
                if getattr(supersession, "rowcount", 0) != 1:
                    raise ValueError(
                        "TECHNICAL_RELEASE_SUPERSEDED_STATE_CHANGED_RETRY: predecessor "
                        "record changed; refresh and review before retrying."
                    )
                technical_variant = db.get(TechnicalVariant, rid)
                if technical_variant is not None:
                    record_audit(
                        db,
                        actor=user,
                        action="supersede_via_technical_release",
                        entity_type="technical_variant",
                        entity_id=technical_variant.id,
                        previous_value={"status": "active"},
                        new_value={
                            "status": "superseded",
                            "replacement_release_id": release.id,
                        },
                        reason=notes or f"Publish technical release {version}",
                    )

        record_audit(
            db,
            actor=user,
            action="publish_release",
            entity_type="library_release",
            entity_id=release.id,
            previous_value={"release_id": previous.id, "version": previous.version}
            if previous
            else None,
            new_value={
                "release_type": release_type,
                "version": version,
                "release_hash": release_hash,
                "record_count": len(records),
                "activated_draft_count": len(activated_ids),
                "activated_candidate_count": (
                    len(technical_snapshot.approved_ids) if technical_snapshot else 0
                ),
                "carried_record_count": (
                    len(technical_snapshot.carried_ids) if technical_snapshot else 0
                ),
            },
            reason=notes or f"Publish {release_type} release {version}",
        )
        db.flush()
        if release_type == "technical":
            published_release_id = release.id
            db.expire_all()
            refreshed_release = db.get(LibraryRelease, published_release_id)
            if refreshed_release is None:
                raise ReleaseScopeError("Published Technical release disappeared before commit.")
            validate_release(db, refreshed_release, "technical", allowed_statuses={"active"})
        db.commit()
    except ReleaseScopeError as exc:
        db.rollback()
        return RedirectResponse(
            f"/releases?error=TECHNICAL_RELEASE_FINAL_VALIDATION_FAILED:+{quote_plus(str(exc))}",
            status_code=303,
        )
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/releases?error={quote_plus(str(exc))}",
            status_code=303,
        )
    except (IntegrityError, OperationalError) as exc:
        db.rollback()
        if _is_publication_conflict(exc):
            return _publication_conflict_response()
        raise
    except BaseException:
        db.rollback()
        raise
    return RedirectResponse(f"/releases/{release.id}?success=Release+published", status_code=303)
