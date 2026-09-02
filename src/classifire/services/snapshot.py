from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, RuleEvaluation
from .calculation import recalculate_estimate

LEGACY_ESTIMATE_SNAPSHOT_SCHEMA = "QUANTIFIRE-ESTIMATE-SNAPSHOT-v1"
ESTIMATE_SNAPSHOT_SCHEMA = "QUANTIFIRE-ESTIMATE-SNAPSHOT-v2"
SNAPSHOT_HASH_FIELD = "snapshot_hash"
SNAPSHOT_DOCUMENT_HASH_FIELD = "snapshot_document_hash"


def _serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=_serial, ensure_ascii=False
    )


def _snapshot_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _snapshot_schema(snapshot: dict[str, Any]) -> str:
    schema = snapshot.get("schema")
    if not isinstance(schema, str) or schema not in {
        LEGACY_ESTIMATE_SNAPSHOT_SCHEMA,
        ESTIMATE_SNAPSHOT_SCHEMA,
    }:
        raise ValueError("Snapshot schema is unsupported; output generation is blocked")
    return schema


def _without_fields(snapshot: dict[str, Any], *fields: str) -> dict[str, Any]:
    payload = dict(snapshot)
    for field in fields:
        payload.pop(field, None)
    return payload


def calculate_snapshot_hash(snapshot: dict[str, Any]) -> str:
    """Return the versioned semantic identity for an estimate snapshot."""
    schema = _snapshot_schema(snapshot)
    if schema == LEGACY_ESTIMATE_SNAPSHOT_SCHEMA:
        return _snapshot_digest(_without_fields(snapshot, SNAPSHOT_HASH_FIELD))
    return _snapshot_digest(
        _without_fields(
            snapshot,
            SNAPSHOT_HASH_FIELD,
            SNAPSHOT_DOCUMENT_HASH_FIELD,
            "generated_utc",
        )
    )


def calculate_snapshot_document_hash(snapshot: dict[str, Any]) -> str:
    """Return the full-payload integrity hash for a version 2 snapshot."""
    if _snapshot_schema(snapshot) != ESTIMATE_SNAPSHOT_SCHEMA:
        raise ValueError("Snapshot document hashes require the version 2 schema")
    return _snapshot_digest(_without_fields(snapshot, SNAPSHOT_DOCUMENT_HASH_FIELD))


def verify_estimate_snapshot(snapshot: dict[str, Any]) -> None:
    """Fail closed unless the snapshot matches its schema-specific integrity contract."""
    schema = _snapshot_schema(snapshot)
    expected = snapshot.get(SNAPSHOT_HASH_FIELD)
    if not isinstance(expected, str) or expected != calculate_snapshot_hash(snapshot):
        raise ValueError("Snapshot hash is missing or invalid; output generation is blocked")

    if schema == ESTIMATE_SNAPSHOT_SCHEMA:
        expected_document_hash = snapshot.get(SNAPSHOT_DOCUMENT_HASH_FIELD)
        if not isinstance(
            expected_document_hash, str
        ) or expected_document_hash != calculate_snapshot_document_hash(snapshot):
            raise ValueError(
                "Snapshot document hash is missing or invalid; output generation is blocked"
            )


def build_estimate_snapshot(
    db: Session,
    estimate: Estimate,
    *,
    generated_utc: datetime | None = None,
) -> dict[str, Any]:
    generated_at = generated_utc or datetime.now(UTC)
    if generated_at.tzinfo is None:
        raise ValueError("generated_utc must be timezone-aware")
    recalculate_estimate(db, estimate)
    evaluations = db.scalars(
        select(RuleEvaluation)
        .where(RuleEvaluation.estimate_id == estimate.id)
        .order_by(RuleEvaluation.created_at, RuleEvaluation.id)
    ).all()
    snapshot = {
        "schema": ESTIMATE_SNAPSHOT_SCHEMA,
        "generated_utc": generated_at.astimezone(UTC).isoformat(),
        "estimate": {
            "id": estimate.id,
            "reference": estimate.reference,
            "revision": estimate.revision,
            "title": estimate.title,
            "status": estimate.status,
            "currency": estimate.currency,
            "tax_name": estimate.tax_name,
            "tax_rate": str(estimate.tax_rate),
            "subtotal_ex_tax": str(estimate.subtotal_ex_tax),
            "tax_total": str(estimate.tax_total),
            "total_incl_tax": str(estimate.total_incl_tax),
            "assumptions": estimate.assumptions or [],
            "exclusions": estimate.exclusions or [],
            "qualifications": estimate.qualifications or [],
        },
        "project": {
            "id": estimate.project.id,
            "reference": estimate.project.reference,
            "name": estimate.project.name,
            "site_address": estimate.project.site_address,
            "jurisdiction": estimate.project.jurisdiction,
            "customer": estimate.project.customer.name if estimate.project.customer else None,
        },
        "release_pins": {
            "pricing": estimate.pricing_release_id,
            "technical": estimate.technical_release_id,
            "rules": estimate.rules_release_id,
            "products": estimate.products_release_id,
            "labour": estimate.labour_release_id,
            "markups": estimate.markups_release_id,
            "formulas": estimate.formula_release_id,
            "brand": estimate.brand_release_id,
        },
        "openings": [
            {
                "id": opening.id,
                "opening_code": opening.opening_code,
                "defect_id": opening.defect_id,
                "location": opening.location,
                "substrate_type": opening.substrate_type,
                "substrate_plane": opening.substrate_plane,
                "substrate_thickness_mm": _serial(opening.substrate_thickness_mm),
                "orientation": opening.orientation,
                "opening_type": opening.opening_type,
                "width_mm": _serial(opening.width_mm),
                "height_mm": _serial(opening.height_mm),
                "diameter_mm": _serial(opening.diameter_mm),
                "frl": opening.frl,
                "physical_model_status": opening.physical_model_status,
                "technical_status": opening.technical_status,
                "selected_technical_variant_id": opening.selected_technical_variant_id,
                "services": [
                    {
                        "id": service.id,
                        "service_code": service.service_code,
                        "service_type": service.service_type,
                        "material": service.material,
                        "nominal_size_mm": _serial(service.nominal_size_mm),
                        "outside_diameter_mm": _serial(service.outside_diameter_mm),
                        "quantity": _serial(service.quantity),
                        "centre_x_mm": _serial(service.centre_x_mm),
                        "centre_y_mm": _serial(service.centre_y_mm),
                        "evidence_status": service.evidence_status,
                    }
                    for service in opening.services
                ],
            }
            for opening in estimate.openings
        ],
        "lines": [
            {
                "id": line.id,
                "line_number": line.line_number,
                "opening_id": line.opening_id,
                "service_id": line.service_id,
                "component_type": line.component_type,
                "component_reference": line.component_reference,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit": line.unit,
                "base_unit_cost": str(line.base_unit_cost),
                "waste_factor": str(line.waste_factor),
                "applied_markup": str(line.applied_markup),
                "markup_source": line.markup_source,
                "unit_sell": str(line.unit_sell),
                "subtotal_ex_tax": str(line.subtotal_ex_tax),
                "tax": str(line.tax),
                "total_incl_tax": str(line.total_incl_tax),
                "pricing_method": line.pricing_method,
                "commercial_recovery_status": line.commercial_recovery_status,
                "rate_source": line.rate_source,
                "formula_version": line.formula_version,
            }
            for line in estimate.lines
        ],
        "rule_evaluations": [
            {
                "rule_id": item.rule_id,
                "rule_version": item.rule_version,
                "opening_id": item.opening_id,
                "result": item.result,
                "severity": item.severity,
                "explanation": item.explanation,
                "inputs": item.inputs,
                "output": item.output,
                "source_reference": item.source_reference,
            }
            for item in evaluations
        ],
    }
    snapshot[SNAPSHOT_HASH_FIELD] = calculate_snapshot_hash(snapshot)
    snapshot[SNAPSHOT_DOCUMENT_HASH_FIELD] = calculate_snapshot_document_hash(snapshot)
    return snapshot


def lock_snapshot(db: Session, estimate: Estimate) -> dict[str, Any]:
    snapshot = build_estimate_snapshot(db, estimate)
    estimate.snapshot_json = snapshot
    estimate.snapshot_hash = snapshot["snapshot_hash"]
    estimate.locked_at = datetime.now(UTC)
    estimate.status = "locked"
    return snapshot
