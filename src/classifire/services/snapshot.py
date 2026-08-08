from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, RuleEvaluation
from .calculation import recalculate_estimate


def _serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=_serial, ensure_ascii=False)


def build_estimate_snapshot(db: Session, estimate: Estimate) -> dict[str, Any]:
    recalculate_estimate(db, estimate)
    evaluations = db.scalars(
        select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)
    ).all()
    snapshot = {
        "schema": "QUANTIFIRE-ESTIMATE-SNAPSHOT-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
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
    snapshot["snapshot_hash"] = hashlib.sha256(canonical_json(snapshot).encode("utf-8")).hexdigest()
    return snapshot


def lock_snapshot(db: Session, estimate: Estimate) -> dict[str, Any]:
    snapshot = build_estimate_snapshot(db, estimate)
    estimate.snapshot_json = snapshot
    estimate.snapshot_hash = snapshot["snapshot_hash"]
    estimate.locked_at = datetime.now(timezone.utc)
    estimate.status = "locked"
    return snapshot
