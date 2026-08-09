from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .commercial_models import ProductivitySource
from .models import (
    Approval,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    Product,
    TechnicalVariant,
    User,
)
from .security import has_permission

RUNTIME_VERSION = "2.13-runtime"
CONFIRMATION_PHRASE = "PROMOTE CLASSIFIRE AUXILIARY V2.13 RUNTIME"
EXPECTED_PRICING_RECORDS = 897
EXPECTED_TECHNICAL_RECORDS = 2860
AUXILIARY_TYPES = ("rules", "products", "labour", "markups")


class AuxiliaryRuntimePromotionError(RuntimeError):
    pass


def _canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _active_runtime_release(db: Session, library_type: str) -> LibraryRelease:
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.version == RUNTIME_VERSION,
            LibraryRelease.status == "active",
        )
    )
    if release is None:
        raise AuxiliaryRuntimePromotionError(
            f"Active {library_type} {RUNTIME_VERSION} release is required before auxiliary promotion."
        )
    manifest = release.source_manifest or {}
    if not release.release_hash or _canonical_hash(manifest) != release.release_hash:
        raise AuxiliaryRuntimePromotionError(
            f"Active {library_type} {RUNTIME_VERSION} release manifest/hash is invalid."
        )
    return release


def _core_runtime_basis(db: Session) -> dict[str, Any]:
    pricing = _active_runtime_release(db, "pricing")
    technical = _active_runtime_release(db, "technical")
    pricing_records = (pricing.source_manifest or {}).get("records") or []
    technical_records = (technical.source_manifest or {}).get("records") or []
    if len(pricing_records) != EXPECTED_PRICING_RECORDS:
        raise AuxiliaryRuntimePromotionError(
            f"Pricing runtime record count changed: {len(pricing_records)}; expected {EXPECTED_PRICING_RECORDS}."
        )
    if len(technical_records) != EXPECTED_TECHNICAL_RECORDS:
        raise AuxiliaryRuntimePromotionError(
            f"Technical runtime record count changed: {len(technical_records)}; expected {EXPECTED_TECHNICAL_RECORDS}."
        )
    return {
        "pricing_release_id": pricing.id,
        "pricing_release_hash": pricing.release_hash,
        "pricing_record_count": len(pricing_records),
        "technical_release_id": technical.id,
        "technical_release_hash": technical.release_hash,
        "technical_record_count": len(technical_records),
    }


def _latest_per_key(records: list[Any], key_name: str, revision_name: str) -> list[Any]:
    chosen: dict[str, Any] = {}
    for record in records:
        key = str(getattr(record, key_name))
        current = chosen.get(key)
        if current is None or getattr(record, revision_name) > getattr(current, revision_name):
            chosen[key] = record
    return [chosen[key] for key in sorted(chosen)]


def _rule_records(db: Session) -> list[EstimatingRule]:
    records = list(
        db.scalars(
            select(EstimatingRule)
            .where(EstimatingRule.status == "active")
            .order_by(EstimatingRule.rule_code, EstimatingRule.version.desc())
        ).all()
    )
    chosen: dict[str, EstimatingRule] = {}
    for record in records:
        chosen.setdefault(record.rule_code, record)
    result = list(chosen.values())
    if not result:
        raise AuxiliaryRuntimePromotionError("No active Rules records exist for auxiliary runtime promotion.")
    return result


def _product_records(db: Session) -> list[Product]:
    records = list(
        db.scalars(
            select(Product)
            .where(Product.status == "active")
            .order_by(Product.sku, Product.revision.desc())
        ).all()
    )
    records = [record for record in records if not record.sku.upper().startswith("UAT-")]
    result = _latest_per_key(records, "sku", "revision")
    if not result:
        raise AuxiliaryRuntimePromotionError("No non-UAT active Product records exist for auxiliary runtime promotion.")
    return result


def _labour_records(db: Session) -> list[LabourComponent]:
    records = list(
        db.scalars(
            select(LabourComponent)
            .where(LabourComponent.status == "active")
            .order_by(LabourComponent.code, LabourComponent.revision.desc())
        ).all()
    )
    records = [record for record in records if not record.code.upper().startswith("UAT-LAB-")]
    result = _latest_per_key(records, "code", "revision")
    if not result:
        raise AuxiliaryRuntimePromotionError("No non-UAT active Labour records exist for auxiliary runtime promotion.")
    return result


def _markup_records(db: Session) -> list[MarkupProfile]:
    records = list(
        db.scalars(
            select(MarkupProfile)
            .where(MarkupProfile.status == "active")
            .order_by(MarkupProfile.scope_type, MarkupProfile.scope_id, MarkupProfile.created_at.desc())
        ).all()
    )
    if not records:
        raise AuxiliaryRuntimePromotionError("No active Markup profiles exist for auxiliary runtime promotion.")
    return records


def _approved_productivity(db: Session) -> list[ProductivitySource]:
    records = list(
        db.scalars(
            select(ProductivitySource)
            .where(ProductivitySource.approval_status == "APPROVED")
            .order_by(ProductivitySource.activity, ProductivitySource.created_at.desc())
        ).all()
    )
    chosen: dict[str, ProductivitySource] = {}
    for record in records:
        chosen.setdefault(record.activity, record)
    return list(chosen.values())


def _activity_name(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, dict):
        for key in ("activity", "activity_id", "labour_activity_id", "code", "id"):
            raw = value.get(key)
            if raw is not None and str(raw).strip():
                return str(raw).strip()
        return None
    raw = str(value).strip()
    return raw or None


def _required_labour_activities(db: Session, technical_release: LibraryRelease) -> list[str]:
    record_ids = [
        str(row.get("id"))
        for row in ((technical_release.source_manifest or {}).get("records") or [])
        if isinstance(row, dict) and row.get("id")
    ]
    variants = list(
        db.scalars(select(TechnicalVariant).where(TechnicalVariant.id.in_(record_ids))).all()
    )
    if len(variants) != EXPECTED_TECHNICAL_RECORDS:
        raise AuxiliaryRuntimePromotionError(
            f"Technical runtime manifest resolves to {len(variants)} records; expected {EXPECTED_TECHNICAL_RECORDS}."
        )

    activities: set[str] = set()
    for variant in variants:
        for value in variant.labour_requirements or []:
            name = _activity_name(value)
            if name:
                activities.add(name)

        source = variant.source_json or {}
        parsed = source.get("parsed_requirements") or {}
        for value in parsed.get("required_labour_activities") or []:
            name = _activity_name(value)
            if name:
                activities.add(name)

        components = variant.component_requirements
        if isinstance(components, dict):
            for value in components.get("required_labour_activities") or []:
                name = _activity_name(value)
                if name:
                    activities.add(name)

    return sorted(activities)


def _rule_manifest(records: list[EstimatingRule]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "record_type": "estimating_rule",
            "key": record.rule_code,
            "version": record.version,
            "conditions": record.conditions,
            "actions": record.actions,
            "record_version": record.record_version,
        }
        for record in records
    ]


def _product_manifest(records: list[Product]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "record_type": "product",
            "key": record.sku,
            "revision": record.revision,
            "base_cost": str(record.base_cost),
            "default_markup": str(record.default_markup or 0),
            "source_reference": record.source_reference,
            "record_version": record.record_version,
        }
        for record in records
    ]


def _labour_manifest(
    labour_records: list[LabourComponent],
    productivity_records: list[ProductivitySource],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "id": record.id,
            "record_type": "labour_component",
            "key": record.code,
            "revision": record.revision,
            "base_rate": str(record.base_rate),
            "default_hours": str(record.default_hours),
            "productivity_source": record.productivity_source,
            "default_markup": str(record.default_markup or 0),
            "record_version": record.record_version,
        }
        for record in labour_records
    ]
    rows.extend(
        {
            "id": record.id,
            "record_type": "productivity_source",
            "key": record.activity,
            "activity": record.activity,
            "quantity_unit": record.quantity_unit,
            "base_hours_per_unit": str(record.base_hours_per_unit),
            "source_record_id": record.source_record_id,
            "source_version": record.source_version or "",
            "executable_formula_id": record.executable_formula_id,
            "record_version": record.record_version,
        }
        for record in productivity_records
    )
    return rows


def _markup_manifest(records: list[MarkupProfile]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "record_type": "markup_profile",
            "key": f"{record.scope_type}:{record.scope_id or 'global'}",
            "product_markup": str(record.product_markup or 0),
            "material_markup": str(record.material_markup or 0),
            "labour_markup": str(record.labour_markup or 0),
            "record_version": record.record_version,
        }
        for record in records
    ]


def inspect_auxiliary_runtime_basis(db: Session) -> dict[str, Any]:
    core = _core_runtime_basis(db)
    technical = _active_runtime_release(db, "technical")
    rules = _rule_records(db)
    products = _product_records(db)
    labour = _labour_records(db)
    markups = _markup_records(db)
    productivity = _approved_productivity(db)
    required = _required_labour_activities(db, technical)
    covered = sorted({row.activity for row in productivity} & set(required))
    missing = sorted(set(required) - set(covered))
    excluded_uat_labour_count = len(
        list(
            db.scalars(
                select(LabourComponent).where(
                    LabourComponent.status == "active",
                    LabourComponent.code.like("UAT-LAB-%"),
                )
            ).all()
        )
    )
    return {
        "schema": "CLASSIFIRE-AUXILIARY-RUNTIME-INSPECTION-v1",
        "runtime_version": RUNTIME_VERSION,
        "core_runtime_basis": core,
        "counts": {
            "rules": len(rules),
            "products": len(products),
            "labour_components": len(labour),
            "markups": len(markups),
            "approved_productivity_sources": len(productivity),
            "required_labour_activities": len(required),
            "covered_labour_activities": len(covered),
            "missing_labour_activities": len(missing),
            "excluded_active_uat_labour_anchors": excluded_uat_labour_count,
        },
        "required_labour_activities": required,
        "covered_labour_activities": covered,
        "missing_labour_activities": missing,
        "production_labour_codes": [row.code for row in labour],
        "product_skus": [row.sku for row in products],
        "markup_keys": [f"{row.scope_type}:{row.scope_id or 'global'}" for row in markups],
        "fail_closed_productivity_limitation": bool(missing),
    }


def _existing_runtime_release(
    db: Session,
    library_type: str,
    runtime_version: str,
) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.version == runtime_version,
        )
    )


def _latest_active_release(db: Session, library_type: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease)
        .where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.status == "active",
        )
        .order_by(LibraryRelease.created_at.desc())
    )


def _create_release(
    db: Session,
    *,
    library_type: str,
    approver: User,
    records: list[dict[str, Any]],
    core_basis: dict[str, Any],
    productivity_coverage: dict[str, Any] | None = None,
) -> LibraryRelease:
    manifest: dict[str, Any] = {
        "schema": "CLASSIFIRE-V213-AUXILIARY-RUNTIME-RELEASE-v1",
        "release_type": library_type,
        "version": RUNTIME_VERSION,
        "core_runtime_basis": core_basis,
        "approved_by_id": approver.id,
        "approved_by_email": approver.email,
        "record_count": len(records),
        "records": records,
    }
    if productivity_coverage is not None:
        manifest["productivity_coverage"] = productivity_coverage
    release_hash = _canonical_hash(manifest)

    existing = _existing_runtime_release(db, library_type, RUNTIME_VERSION)
    if existing is not None:
        if (
            existing.status == "active"
            and existing.release_hash == release_hash
            and existing.source_manifest == manifest
        ):
            return existing
        raise AuxiliaryRuntimePromotionError(
            f"A {library_type} {RUNTIME_VERSION!r} release already exists with different content or status."
        )

    previous = _latest_active_release(db, library_type)
    if previous is not None:
        previous.status = "superseded"

    release = LibraryRelease(
        library_type=library_type,
        version=RUNTIME_VERSION,
        status="active",
        effective_date=date.today(),
        release_hash=release_hash,
        source_manifest=manifest,
        notes=(
            "Human-approved CLASSIFIRE v2.13 auxiliary runtime release. "
            "Record IDs are pinned for deterministic estimate execution."
        ),
        created_by_id=approver.id,
        approved_by_id=approver.id,
        approved_at=datetime.now(timezone.utc),
        supersedes_release_id=previous.id if previous else None,
    )
    db.add(release)
    db.flush()

    approval = Approval(
        entity_type="library_release",
        entity_id=release.id,
        approval_type=f"{library_type}_auxiliary_runtime_release_activation",
        status="approved",
        requested_by_id=approver.id,
        decided_by_id=approver.id,
        requested_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc),
        decision_reason=(
            f"Human approval of CLASSIFIRE v2.13 auxiliary runtime {library_type} release. "
            "Missing productivity coverage, where present, remains a fail-closed runtime limitation."
        ),
        snapshot_hash=release_hash,
    )
    db.add(approval)

    record_audit(
        db,
        actor=approver,
        action="promote_v213_auxiliary_runtime_release",
        entity_type="library_release",
        entity_id=release.id,
        previous_value={
            "previous_active_release_id": previous.id if previous else None,
        },
        new_value={
            "library_type": library_type,
            "runtime_version": RUNTIME_VERSION,
            "release_hash": release_hash,
            "record_count": len(records),
            "productivity_coverage": productivity_coverage,
        },
        reason="Controlled human promotion of CLASSIFIRE v2.13 auxiliary runtime release",
        correlation_id="CLASSIFIRE-V213-AUXILIARY-RUNTIME",
    )
    return release


def promote_auxiliary_runtime_releases(
    db: Session,
    *,
    approver: User,
    confirmation_phrase: str,
    acknowledge_missing_productivity: bool,
) -> dict[str, Any]:
    if confirmation_phrase != CONFIRMATION_PHRASE:
        raise AuxiliaryRuntimePromotionError(
            f"Exact confirmation phrase required: {CONFIRMATION_PHRASE}"
        )
    if not approver.is_active:
        raise AuxiliaryRuntimePromotionError("Auxiliary runtime approver is inactive.")
    if not has_permission(approver, "pricing:approve"):
        raise AuxiliaryRuntimePromotionError(
            f"Approver {approver.email!r} lacks pricing:approve authority."
        )
    if not has_permission(approver, "rule:approve"):
        raise AuxiliaryRuntimePromotionError(
            f"Approver {approver.email!r} lacks rule:approve authority."
        )

    inspection = inspect_auxiliary_runtime_basis(db)
    missing = inspection["missing_labour_activities"]
    if missing and not acknowledge_missing_productivity:
        raise AuxiliaryRuntimePromotionError(
            "Package 15 labour productivity coverage is incomplete. Explicit acknowledgement is required; "
            "runtime quantity/labour derivation will fail closed for any selected system that requires an "
            "uncovered labour activity."
        )

    core = inspection["core_runtime_basis"]
    technical = _active_runtime_release(db, "technical")
    rules = _rule_records(db)
    products = _product_records(db)
    labour = _labour_records(db)
    markups = _markup_records(db)
    productivity = _approved_productivity(db)
    required = _required_labour_activities(db, technical)
    covered = sorted({row.activity for row in productivity} & set(required))
    missing = sorted(set(required) - set(covered))
    productivity_coverage = {
        "required_activity_count": len(required),
        "approved_source_count": len(productivity),
        "covered_activity_count": len(covered),
        "missing_activity_count": len(missing),
        "covered_activities": covered,
        "missing_activities": missing,
        "human_acknowledged_incomplete_coverage": bool(missing),
        "runtime_behavior": (
            "FAIL_CLOSED_ON_SELECTED_VARIANT_REQUIRING_UNCOVERED_ACTIVITY"
            if missing
            else "FULL_PRODUCTIVITY_COVERAGE"
        ),
    }

    releases = {
        "rules": _create_release(
            db,
            library_type="rules",
            approver=approver,
            records=_rule_manifest(rules),
            core_basis=core,
        ),
        "products": _create_release(
            db,
            library_type="products",
            approver=approver,
            records=_product_manifest(products),
            core_basis=core,
        ),
        "labour": _create_release(
            db,
            library_type="labour",
            approver=approver,
            records=_labour_manifest(labour, productivity),
            core_basis=core,
            productivity_coverage=productivity_coverage,
        ),
        "markups": _create_release(
            db,
            library_type="markups",
            approver=approver,
            records=_markup_manifest(markups),
            core_basis=core,
        ),
    }
    db.commit()

    return {
        "schema": "CLASSIFIRE-V213-AUXILIARY-RUNTIME-PROMOTION-RECEIPT-v1",
        "ok": True,
        "runtime_version": RUNTIME_VERSION,
        "approver_email": approver.email,
        "core_runtime_basis": core,
        "releases": {
            library_type: {
                "release_id": release.id,
                "release_hash": release.release_hash,
                "record_count": len((release.source_manifest or {}).get("records") or []),
            }
            for library_type, release in releases.items()
        },
        "productivity_coverage": productivity_coverage,
        "excluded_active_uat_labour_anchors": inspection["counts"]["excluded_active_uat_labour_anchors"],
    }


__all__ = [
    "AUXILIARY_TYPES",
    "AuxiliaryRuntimePromotionError",
    "CONFIRMATION_PHRASE",
    "RUNTIME_VERSION",
    "inspect_auxiliary_runtime_basis",
    "promote_auxiliary_runtime_releases",
]
