"""Deterministic protected-state fingerprints used by proposal-only safety gates.

The fingerprint deliberately covers canonical records whose mutation would change
the physical-model workflow. It is read-only: callers supply an existing SQLAlchemy
session and this module never adds, flushes, commits, or rolls back rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelLock,
    ServiceMaterialHypothesis,
    ServiceOpeningLink,
)
from ..models import Estimate, Opening, Service
from .workflow_db import assess_estimate_workflow

PROTECTED_STATE_FINGERPRINT_VERSION = "CLASSIFIRE-PROTECTED-CANONICAL-STATE-v1"

PROTECTED_STATE_COLUMN_MANIFEST: dict[str, tuple[str, ...]] = {
    "estimate": (
        "project_id",
        "revision",
        "reference",
        "title",
        "status",
        "currency",
        "tax_name",
        "tax_rate",
        "product_markup_override",
        "material_markup_override",
        "labour_markup_override",
        "assumptions",
        "exclusions",
        "qualifications",
        "pricing_release_id",
        "technical_release_id",
        "rules_release_id",
        "products_release_id",
        "labour_release_id",
        "markups_release_id",
        "formula_release_id",
        "brand_release_id",
        "subtotal_ex_tax",
        "tax_total",
        "total_incl_tax",
        "snapshot_json",
        "snapshot_hash",
        "locked_at",
        "approved_at",
        "approved_by_id",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "defects": (
        "estimate_id",
        "external_defect_id",
        "defect_code",
        "description",
        "location",
        "classification",
        "evidence_status",
        "status",
        "source_json",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "evidence_sources": (
        "estimate_id",
        "defect_id",
        "stored_file_id",
        "evidence_type",
        "source_reference",
        "page_number",
        "region_reference",
        "sha256",
        "evidence_class",
        "confidence",
        "status",
        "source_json",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "openings": (
        "estimate_id",
        "defect_id",
        "canonical_defect_id",
        "opening_code",
        "location",
        "substrate_type",
        "substrate_plane",
        "substrate_thickness_mm",
        "orientation",
        "opening_type",
        "width_mm",
        "height_mm",
        "diameter_mm",
        "frl",
        "physical_model_status",
        "technical_status",
        "selected_technical_variant_id",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "services": (
        "opening_id",
        "primary_opening_legacy",
        "service_code",
        "service_type",
        "material",
        "nominal_size_mm",
        "outside_diameter_mm",
        "width_mm",
        "height_mm",
        "insulation_type",
        "insulation_thickness_mm",
        "quantity",
        "centre_x_mm",
        "centre_y_mm",
        "evidence_status",
        "confidence",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "service_opening_links": (
        "service_id",
        "opening_id",
        "link_type",
        "relationship_status",
        "evidence_status",
        "confidence",
        "source_reference",
        "notes",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "service_material_hypotheses": (
        "service_id",
        "material",
        "evidence_status",
        "evidence_ids",
        "confidence",
        "technical_consequence",
        "pricing_consequence",
        "final_status",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
    "physical_model_locks": (
        "project_id",
        "estimate_id",
        "defect_ids",
        "evidence_hashes",
        "service_ids",
        "opening_ids",
        "service_count_status",
        "material_hypothesis_status",
        "critical_unknowns",
        "validator_result",
        "permitted_classes",
        "content_hash",
        "signature",
        "invalidated_at",
        "invalidation_reason",
        "id",
        "created_at",
        "updated_at",
        "record_version",
    ),
}

PROTECTED_WORKFLOW_FACT_FIELDS = (
    "evidence_intake_complete",
    "physical_model_complete",
    "physical_model_locked",
    "technical_search_complete",
    "repair_strategy_locked",
    "components_derived",
    "quantity_and_labour_complete",
    "commercial_pricing_and_recovery_complete",
    "independent_validation_passed",
    "validated_snapshot_created",
    "output_rendered",
    "human_release_approved",
)

PROTECTED_STATE_COMPONENTS = (
    "estimate",
    "workflow",
    "defects",
    "evidence_sources",
    "openings",
    "services",
    "service_opening_links",
    "service_material_hypotheses",
    "physical_model_locks",
)

_MODEL_BY_COMPONENT = {
    "estimate": Estimate,
    "defects": Defect,
    "evidence_sources": EvidenceSource,
    "openings": Opening,
    "services": Service,
    "service_opening_links": ServiceOpeningLink,
    "service_material_hypotheses": ServiceMaterialHypothesis,
    "physical_model_locks": PhysicalModelLock,
}


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        values = [_canonical_value(item) for item in value]
        return sorted(
            values,
            key=lambda item: json.dumps(
                item, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    if isinstance(value, bytes):
        return value.hex()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Protected-state fingerprint cannot canonicalize {type(value).__name__}.")


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        _canonical_value(value),
        allow_nan=False,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _row_payload(row: Any, component: str) -> dict[str, Any]:
    return {
        column: _canonical_value(getattr(row, column))
        for column in PROTECTED_STATE_COLUMN_MANIFEST[component]
    }


def _rows_payload(rows: list[Any], component: str) -> list[dict[str, Any]]:
    values = [_row_payload(row, component) for row in rows]
    return sorted(
        values,
        key=lambda item: (
            str(item.get("id") or ""),
            json.dumps(
                item, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        ),
    )


def _validate_schema() -> None:
    for component, model in _MODEL_BY_COMPONENT.items():
        expected = PROTECTED_STATE_COLUMN_MANIFEST[component]
        actual = tuple(column.key for column in model.__table__.columns)
        if actual != expected:
            raise RuntimeError(
                "Protected-state fingerprint schema drift detected for "
                f"{component}; bump {PROTECTED_STATE_FINGERPRINT_VERSION} and "
                "update its explicit manifest."
            )


def protected_state_snapshot_from_session(db: Session, estimate_id: str) -> dict[str, Any]:
    """Snapshot exactly the canonical components protected during proposal-only work."""

    _validate_schema()
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise RuntimeError(
            "Protected-state fingerprint failed: estimate disappeared from the database."
        )
    defects = list(db.scalars(select(Defect).where(Defect.estimate_id == estimate_id)).all())
    evidence_sources = list(
        db.scalars(select(EvidenceSource).where(EvidenceSource.estimate_id == estimate_id)).all()
    )
    openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate_id)).all())
    opening_ids = {row.id for row in openings}
    services = (
        list(db.scalars(select(Service).where(Service.opening_id.in_(opening_ids))).all())
        if opening_ids
        else []
    )
    service_ids = {row.id for row in services}
    first_links = (
        list(
            db.scalars(
                select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
            ).all()
        )
        if opening_ids
        else []
    )
    missing_service_ids = {row.service_id for row in first_links} - service_ids
    if missing_service_ids:
        services.extend(
            list(db.scalars(select(Service).where(Service.id.in_(missing_service_ids))).all())
        )
        service_ids.update(missing_service_ids)
    links = (
        list(
            db.scalars(
                select(ServiceOpeningLink).where(
                    or_(
                        ServiceOpeningLink.opening_id.in_(opening_ids),
                        ServiceOpeningLink.service_id.in_(service_ids),
                    )
                )
            ).all()
        )
        if opening_ids or service_ids
        else []
    )
    material_hypotheses = (
        list(
            db.scalars(
                select(ServiceMaterialHypothesis).where(
                    ServiceMaterialHypothesis.service_id.in_(service_ids)
                )
            ).all()
        )
        if service_ids
        else []
    )
    locks = list(
        db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate_id)
        ).all()
    )
    workflow_assessment = assess_estimate_workflow(db, estimate)
    workflow_facts = asdict(workflow_assessment.facts)
    if tuple(workflow_facts) != PROTECTED_WORKFLOW_FACT_FIELDS:
        raise RuntimeError(
            "Protected-state fingerprint workflow schema drift detected; bump "
            f"{PROTECTED_STATE_FINGERPRINT_VERSION} and update its fact manifest."
        )
    return {
        "fingerprint_version": PROTECTED_STATE_FINGERPRINT_VERSION,
        "estimate_id": estimate_id,
        "estimate": _row_payload(estimate, "estimate"),
        "workflow": {"stage": workflow_assessment.stage, "facts": workflow_facts},
        "defects": _rows_payload(defects, "defects"),
        "evidence_sources": _rows_payload(evidence_sources, "evidence_sources"),
        "openings": _rows_payload(openings, "openings"),
        "services": _rows_payload(services, "services"),
        "service_opening_links": _rows_payload(links, "service_opening_links"),
        "service_material_hypotheses": _rows_payload(
            material_hypotheses, "service_material_hypotheses"
        ),
        "physical_model_locks": _rows_payload(locks, "physical_model_locks"),
    }


def protected_state_fingerprint(snapshot: dict[str, Any]) -> str:
    return canonical_sha256(snapshot)


def protected_component_fingerprints(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        component: canonical_sha256(snapshot.get(component))
        for component in PROTECTED_STATE_COMPONENTS
    }


def protected_state_counts(snapshot: dict[str, Any]) -> dict[str, int]:
    return {
        component: 1
        if component in {"estimate", "workflow"} and isinstance(snapshot.get(component), dict)
        else len(snapshot.get(component) or [])
        for component in PROTECTED_STATE_COMPONENTS
    }


__all__ = [
    "PROTECTED_STATE_FINGERPRINT_VERSION",
    "PROTECTED_STATE_COMPONENTS",
    "PROTECTED_STATE_COLUMN_MANIFEST",
    "canonical_sha256",
    "protected_component_fingerprints",
    "protected_state_counts",
    "protected_state_fingerprint",
    "protected_state_snapshot_from_session",
]
