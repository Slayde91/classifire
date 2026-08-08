from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import (
    EvidenceSource,
    Package15CandidateRequirement,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from ..commercial_models import (
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    EstimateCertificate,
    GateEvidence,
    LabourActivity,
    PriceAnomalyReview,
    PricingComponent,
    ProductivitySource,
    Quantity,
    QuantityFormulaInput,
)
from ..models import Estimate, Opening, Project, RuleEvaluation, Service
from .validation import latest_passing_gate, validation_state_hashes
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


SNAPSHOT_SCHEMA = "QUANTIFIRE-VALIDATED-ESTIMATE-SNAPSHOT-v2.13"
CERTIFICATE_SCHEMA = "QUANTIFIRE-ESTIMATE-CERTIFICATE-v2.13"
MONEY = Decimal("0.01")


class ValidatedSnapshotError(RuntimeError):
    pass


def _serial(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _serial(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serial(item) for item in value]
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(_serial(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _model_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        payload.append(
            {
                column.name: _serial(getattr(row, column.name))
                for column in row.__table__.columns
            }
        )
    payload.sort(key=lambda item: str(item.get("id") or ""))
    return payload


def _active_records(db: Session, estimate: Estimate) -> dict[str, list[Any]]:
    openings = list(
        db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)).all()
    )
    opening_ids = [item.id for item in openings]
    links = list(
        db.scalars(
            select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
        ).all()
    ) if opening_ids else []
    service_ids = sorted({item.service_id for item in links})
    services = list(
        db.scalars(select(Service).where(Service.id.in_(service_ids))).all()
    ) if service_ids else []
    evidence = list(
        db.scalars(select(EvidenceSource).where(EvidenceSource.estimate_id == estimate.id)).all()
    )
    physical_locks = list(
        db.scalars(
            select(PhysicalModelLock).where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ).all()
    )
    strategies = list(
        db.scalars(
            select(RepairStrategy).where(
                RepairStrategy.opening_id.in_(opening_ids),
                RepairStrategy.status.in_(["candidate_selected", "locked"]),
            )
        ).all()
    ) if opening_ids else []
    strategy_ids = [item.id for item in strategies]
    repair_locks = list(
        db.scalars(
            select(RepairStrategyLock).where(
                RepairStrategyLock.repair_strategy_id.in_(strategy_ids),
                RepairStrategyLock.invalidated_at.is_(None),
            )
        ).all()
    ) if strategy_ids else []
    candidate_requirements = list(
        db.scalars(
            select(Package15CandidateRequirement).where(
                Package15CandidateRequirement.opening_id.in_(opening_ids)
            )
        ).all()
    ) if opening_ids else []
    components = list(
        db.scalars(
            select(SystemRequiredComponent).where(
                SystemRequiredComponent.opening_id.in_(opening_ids)
            )
        ).all()
    ) if opening_ids else []
    component_ids = [item.id for item in components]
    quantities = list(
        db.scalars(
            select(Quantity).where(
                Quantity.required_component_id.in_(component_ids),
                Quantity.status != "superseded",
            )
        ).all()
    ) if component_ids else []
    quantity_ids = [item.id for item in quantities]
    formula_inputs = list(
        db.scalars(
            select(QuantityFormulaInput).where(
                QuantityFormulaInput.quantity_record_id.in_(quantity_ids)
            )
        ).all()
    ) if quantity_ids else []
    labour = list(
        db.scalars(
            select(LabourActivity).where(
                LabourActivity.required_component_id.in_(component_ids),
                LabourActivity.status != "superseded",
            )
        ).all()
    ) if component_ids else []
    productivity_ids = sorted({item.productivity_source_id for item in labour if item.productivity_source_id})
    productivity = list(
        db.scalars(
            select(ProductivitySource).where(ProductivitySource.id.in_(productivity_ids))
        ).all()
    ) if productivity_ids else []
    pricing = list(
        db.scalars(
            select(PricingComponent).where(
                PricingComponent.estimate_id == estimate.id,
                PricingComponent.status != "superseded",
            )
        ).all()
    )
    pricing_ids = [item.id for item in pricing]
    method_locks = list(
        db.scalars(
            select(CommercialMethodLock).where(
                CommercialMethodLock.component_id.in_(pricing_ids)
            )
        ).all()
    ) if pricing_ids else []
    recovery = list(
        db.scalars(
            select(CommercialRecoveryRecord).where(
                CommercialRecoveryRecord.component_id.in_(pricing_ids),
                CommercialRecoveryRecord.active.is_(True),
            )
        ).all()
    ) if pricing_ids else []
    reconciliations = list(
        db.scalars(
            select(ComponentRequirementReconciliation).where(
                ComponentRequirementReconciliation.required_component_id.in_(component_ids)
            )
        ).all()
    ) if component_ids else []
    anomalies = list(
        db.scalars(
            select(PriceAnomalyReview).where(PriceAnomalyReview.estimate_id == estimate.id)
        ).all()
    )
    rules = list(
        db.scalars(select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)).all()
    )
    return {
        "openings": openings,
        "links": links,
        "services": services,
        "evidence": evidence,
        "physical_locks": physical_locks,
        "strategies": strategies,
        "repair_locks": repair_locks,
        "candidate_requirements": candidate_requirements,
        "components": components,
        "quantities": quantities,
        "formula_inputs": formula_inputs,
        "labour": labour,
        "productivity": productivity,
        "pricing": pricing,
        "method_locks": method_locks,
        "recovery": recovery,
        "reconciliations": reconciliations,
        "anomalies": anomalies,
        "rules": rules,
    }


def _commercial_lines(
    estimate: Estimate,
    records: dict[str, list[Any]],
) -> tuple[list[dict[str, Any]], dict[str, Decimal]]:
    quantity_by_id = {item.id: item for item in records["quantities"]}
    method_by_component = {item.component_id: item for item in records["method_locks"]}
    recovery_by_component = {item.component_id: item for item in records["recovery"]}
    lines: list[dict[str, Any]] = []
    subtotal = Decimal("0")
    for index, pricing in enumerate(sorted(records["pricing"], key=lambda item: item.id), 1):
        quantity = quantity_by_id.get(pricing.quantity_id)
        method = method_by_component.get(pricing.id)
        recovery = recovery_by_component.get(pricing.id)
        amount = Decimal(pricing.extended_cost or 0)
        tax = _money(amount * Decimal(estimate.tax_rate or 0))
        subtotal += amount
        lines.append(
            {
                "id": pricing.id,
                "line_number": index,
                "opening_id": pricing.opening_id,
                "service_id": pricing.service_id,
                "required_component_id": pricing.required_component_id,
                "component_type": pricing.component_type,
                "component_reference": pricing.rate_source,
                "description": pricing.scope_description,
                "quantity": str(quantity.numeric_value if quantity and quantity.numeric_value is not None else 0),
                "unit": pricing.unit_basis or (quantity.unit_basis if quantity else "each"),
                "base_unit_cost": str(pricing.unit_rate or 0),
                "waste_factor": "0",
                "applied_markup": "0",
                "markup_source": "contained_in_canonical_commercial_method",
                "unit_sell": str(pricing.unit_rate or 0),
                "subtotal_ex_tax": str(_money(amount)),
                "tax": str(tax),
                "total_incl_tax": str(_money(amount + tax)),
                "pricing_method": method.selected_pricing_method if method else "UNKNOWN",
                "commercial_recovery_status": recovery.recovery_status if recovery else "UNVERIFIED",
                "rate_source": pricing.rate_source,
                "formula_version": "QUANTIFIRE-COMMERCIAL-ENGINE-v1.0",
            }
        )
    subtotal = _money(subtotal)
    tax_total = _money(subtotal * Decimal(estimate.tax_rate or 0))
    return lines, {
        "subtotal_ex_tax": subtotal,
        "tax_total": tax_total,
        "total_incl_tax": _money(subtotal + tax_total),
    }


def _certificate(
    db: Session,
    estimate: Estimate,
    gate: GateEvidence,
    table_hashes: dict[str, str],
    records: dict[str, list[Any]],
) -> EstimateCertificate:
    release_pins = {
        "pricing": estimate.pricing_release_id,
        "technical": estimate.technical_release_id,
        "rules": estimate.rules_release_id,
        "products": estimate.products_release_id,
        "labour": estimate.labour_release_id,
        "markups": estimate.markups_release_id,
        "formulas": estimate.formula_release_id,
        "brand": estimate.brand_release_id,
    }
    gate_payload = _model_rows([gate])[0]
    reconciliation_payload = _model_rows(records["reconciliations"])
    commercial_payload = {
        "pricing_components": _model_rows(records["pricing"]),
        "method_locks": _model_rows(records["method_locks"]),
        "recovery": _model_rows(records["recovery"]),
    }
    cert_payload = {
        "schema": CERTIFICATE_SCHEMA,
        "estimate_id": estimate.id,
        "quantifire_version": "2.13",
        "active_manifest_hash": _hash(release_pins),
        "governed_table_hashes": table_hashes,
        "gate_evidence_hash": _hash(gate_payload),
        "proposal_reconciliation_result_hash": _hash(reconciliation_payload),
        "proposal_commercial_validity_result_hash": _hash(commercial_payload),
        "validator_identity": gate.validator_id,
    }
    final_hash = _hash(cert_payload)
    existing = db.scalar(
        select(EstimateCertificate).where(EstimateCertificate.final_certificate_hash == final_hash)
    )
    if existing:
        return existing
    certificate = EstimateCertificate(
        estimate_id=estimate.id,
        quantifire_version="2.13",
        active_manifest_hash=cert_payload["active_manifest_hash"],
        governed_table_hashes=table_hashes,
        gate_evidence_hash=cert_payload["gate_evidence_hash"],
        workbook_structure_hash=None,
        proposal_reconciliation_result_hash=cert_payload["proposal_reconciliation_result_hash"],
        proposal_commercial_validity_result_hash=cert_payload["proposal_commercial_validity_result_hash"],
        validator_identity=gate.validator_id,
        certificate_schema_version=CERTIFICATE_SCHEMA,
        final_certificate_hash=final_hash,
        signature=None,
    )
    db.add(certificate)
    db.flush()
    return certificate


def build_validated_snapshot(db: Session, estimate: Estimate) -> dict[str, Any]:
    require_estimate_action(db, estimate, WorkflowAction.CREATE_VALIDATED_SNAPSHOT)
    gate = latest_passing_gate(db, estimate)
    table_hashes, _, state_hash = validation_state_hashes(db, estimate)
    records = _active_records(db, estimate)
    certificate = _certificate(db, estimate, gate, table_hashes, records)
    lines, totals = _commercial_lines(estimate, records)

    project = db.get(Project, estimate.project_id)
    if not project:
        raise ValidatedSnapshotError("Estimate project record is missing.")
    customer_name = project.customer.name if project.customer else None

    service_by_id = {item.id: item for item in records["services"]}
    links_by_opening: dict[str, list[ServiceOpeningLink]] = {}
    for link in records["links"]:
        links_by_opening.setdefault(link.opening_id, []).append(link)

    opening_rows: list[dict[str, Any]] = []
    for opening in sorted(records["openings"], key=lambda item: item.id):
        nested_services = []
        for link in sorted(links_by_opening.get(opening.id, []), key=lambda item: item.service_id):
            service = service_by_id.get(link.service_id)
            if not service:
                continue
            nested_services.append(
                {
                    "id": service.id,
                    "service_code": service.service_code,
                    "service_type": service.service_type,
                    "material": service.material,
                    "nominal_size_mm": _serial(service.nominal_size_mm),
                    "outside_diameter_mm": _serial(service.outside_diameter_mm),
                    "width_mm": _serial(service.width_mm),
                    "height_mm": _serial(service.height_mm),
                    "insulation_type": service.insulation_type,
                    "insulation_thickness_mm": _serial(service.insulation_thickness_mm),
                    "quantity": _serial(service.quantity),
                    "centre_x_mm": _serial(service.centre_x_mm),
                    "centre_y_mm": _serial(service.centre_y_mm),
                    "evidence_status": service.evidence_status,
                    "confidence": _serial(service.confidence),
                }
            )
        opening_rows.append(
            {
                "id": opening.id,
                "opening_code": opening.opening_code,
                "defect_id": opening.canonical_defect_id or opening.defect_id,
                "legacy_defect_id": opening.defect_id,
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
                "services": nested_services,
            }
        )

    estimate.subtotal_ex_tax = totals["subtotal_ex_tax"]
    estimate.tax_total = totals["tax_total"]
    estimate.total_incl_tax = totals["total_incl_tax"]

    snapshot: dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "validation_state_hash": state_hash,
        "estimate": {
            "id": estimate.id,
            "reference": estimate.reference,
            "revision": estimate.revision,
            "title": estimate.title,
            "status": "locked",
            "currency": estimate.currency,
            "tax_name": estimate.tax_name,
            "tax_rate": str(estimate.tax_rate),
            "subtotal_ex_tax": str(totals["subtotal_ex_tax"]),
            "tax_total": str(totals["tax_total"]),
            "total_incl_tax": str(totals["total_incl_tax"]),
            "assumptions": estimate.assumptions or [],
            "exclusions": estimate.exclusions or [],
            "qualifications": estimate.qualifications or [],
        },
        "project": {
            "id": project.id,
            "reference": project.reference,
            "name": project.name,
            "site_address": project.site_address,
            "jurisdiction": project.jurisdiction,
            "customer": customer_name,
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
        "independent_validation": _model_rows([gate])[0],
        "estimate_certificate": _model_rows([certificate])[0],
        "governed_table_hashes": table_hashes,
        "openings": opening_rows,
        "lines": lines,
        "rule_evaluations": [
            {
                "rule_id": item.rule_id,
                "rule_version": item.rule_version,
                "opening_id": item.opening_id,
                "result": item.result,
                "severity": item.severity,
                "explanation": item.explanation,
                "inputs": _serial(item.inputs),
                "output": _serial(item.output),
                "source_reference": item.source_reference,
            }
            for item in records["rules"]
        ],
        "canonical": {
            "evidence_sources": _model_rows(records["evidence"]),
            "service_opening_links": _model_rows(records["links"]),
            "physical_model_locks": _model_rows(records["physical_locks"]),
            "repair_strategies": _model_rows(records["strategies"]),
            "repair_strategy_locks": _model_rows(records["repair_locks"]),
            "package15_candidate_requirements": _model_rows(records["candidate_requirements"]),
            "system_required_components": _model_rows(records["components"]),
            "quantities": _model_rows(records["quantities"]),
            "quantity_formula_inputs": _model_rows(records["formula_inputs"]),
            "productivity_sources": _model_rows(records["productivity"]),
            "labour_activities": _model_rows(records["labour"]),
            "pricing_components": _model_rows(records["pricing"]),
            "commercial_method_locks": _model_rows(records["method_locks"]),
            "commercial_recovery_records": _model_rows(records["recovery"]),
            "component_requirement_reconciliations": _model_rows(records["reconciliations"]),
            "price_anomaly_reviews": _model_rows(records["anomalies"]),
        },
    }
    snapshot["snapshot_hash"] = _hash(snapshot)
    return snapshot


def lock_validated_snapshot(db: Session, estimate: Estimate) -> tuple[dict[str, Any], bool]:
    if estimate.snapshot_json and estimate.snapshot_hash:
        existing = dict(estimate.snapshot_json)
        stored_hash = existing.pop("snapshot_hash", None)
        actual_hash = _hash(existing)
        if (
            stored_hash == estimate.snapshot_hash == actual_hash
            and estimate.snapshot_json.get("schema") == SNAPSHOT_SCHEMA
        ):
            return estimate.snapshot_json, False

    snapshot = build_validated_snapshot(db, estimate)
    estimate.snapshot_json = snapshot
    estimate.snapshot_hash = snapshot["snapshot_hash"]
    estimate.locked_at = datetime.now(timezone.utc)
    estimate.status = "locked"
    db.flush()
    return snapshot, True


__all__ = [
    "CERTIFICATE_SCHEMA",
    "SNAPSHOT_SCHEMA",
    "ValidatedSnapshotError",
    "build_validated_snapshot",
    "canonical_json",
    "lock_validated_snapshot",
]
