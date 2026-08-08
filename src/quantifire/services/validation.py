from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import (
    EvidenceSource,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    SystemRequiredComponent,
)
from ..commercial_models import (
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    GateEvidence,
    LabourActivity,
    PriceAnomalyReview,
    PricingComponent,
    Quantity,
    QuantityFormulaInput,
)
from ..models import Estimate, Opening
from .release_scope import ReleaseScopeError, pinned_release
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


VALIDATOR_ID = "QUANTIFIRE-DETERMINISTIC-INDEPENDENT-VALIDATOR"
VALIDATOR_VERSION = "v2.13.1"
GATE_TYPE = "FINAL_INDEPENDENT_VALIDATION"


class IndependentValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    subject_type: str
    subject_id: str | None
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ValidationResult:
    gate_evidence: GateEvidence
    passed: bool
    issues: tuple[ValidationIssue, ...]
    state_hash: str
    table_hashes: dict[str, str]
    input_record_count: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_evidence_id": self.gate_evidence.id,
            "gate_type": self.gate_evidence.gate_type,
            "validator_id": self.gate_evidence.validator_id,
            "validator_version": self.gate_evidence.validator_version,
            "result": self.gate_evidence.result,
            "passed": self.passed,
            "state_hash": self.state_hash,
            "input_record_count": self.input_record_count,
            "exception_count": len(self.issues),
            "issues": [issue.as_dict() for issue in self.issues],
            "table_hashes": self.table_hashes,
        }


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


def _canonical(value: Any) -> str:
    return json.dumps(_serial(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _norm(value: Any) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _model_rows(rows: Iterable[Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            column.name: _serial(getattr(row, column.name))
            for column in row.__table__.columns
        }
        result.append(payload)
    result.sort(key=lambda item: str(item.get("id") or ""))
    return result


def _table_hash(rows: Iterable[Any]) -> tuple[str, int]:
    payload = _model_rows(rows)
    return _hash(payload), len(payload)


def validation_state_hashes(db: Session, estimate: Estimate) -> tuple[dict[str, str], int, str]:
    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate.id)).all()
    )
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
    anomaly_reviews = list(
        db.scalars(
            select(PriceAnomalyReview).where(PriceAnomalyReview.estimate_id == estimate.id)
        ).all()
    )

    datasets: dict[str, Iterable[Any]] = {
        "evidence_sources": evidence,
        "physical_model_locks": physical_locks,
        "repair_strategies": strategies,
        "repair_strategy_locks": repair_locks,
        "system_required_components": components,
        "quantities": quantities,
        "quantity_formula_inputs": formula_inputs,
        "labour_activities": labour,
        "pricing_components": pricing,
        "commercial_method_locks": method_locks,
        "commercial_recovery_records": recovery,
        "component_requirement_reconciliations": reconciliations,
        "price_anomaly_reviews": anomaly_reviews,
    }
    table_hashes: dict[str, str] = {}
    total = 0
    for name, rows in datasets.items():
        digest, count = _table_hash(rows)
        table_hashes[name] = digest
        total += count

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
    table_hashes["release_pins"] = _hash(release_pins)
    state_hash = _hash({"estimate_id": estimate.id, "table_hashes": table_hashes})
    return table_hashes, total, state_hash


def _active_commercial_records(
    db: Session, estimate: Estimate
) -> tuple[
    list[SystemRequiredComponent],
    list[Quantity],
    list[LabourActivity],
    list[PricingComponent],
    list[CommercialMethodLock],
    list[CommercialRecoveryRecord],
    list[ComponentRequirementReconciliation],
    list[PriceAnomalyReview],
]:
    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate.id)).all()
    )
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
    labour = list(
        db.scalars(
            select(LabourActivity).where(
                LabourActivity.required_component_id.in_(component_ids),
                LabourActivity.status != "superseded",
            )
        ).all()
    ) if component_ids else []
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
    return components, quantities, labour, pricing, method_locks, recovery, reconciliations, anomalies


def _release_issues(db: Session, estimate: Estimate, methods: Iterable[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    required = {"pricing", "technical", "labour"}
    method_set = set(methods)
    if "Component-Built Price" in method_set:
        required.update({"products", "markups"})
    for kind in sorted(required):
        try:
            pinned_release(db, estimate, kind)
        except ReleaseScopeError as exc:
            issues.append(
                ValidationIssue(
                    code="PINNED_RELEASE_INVALID",
                    subject_type="library_release",
                    subject_id=kind,
                    detail=str(exc),
                )
            )
    return issues


def evaluate_independent_validation(db: Session, estimate: Estimate) -> tuple[ValidationIssue, ...]:
    require_estimate_action(db, estimate, WorkflowAction.RUN_INDEPENDENT_VALIDATION)
    (
        components,
        quantities,
        labour,
        pricing,
        method_locks,
        recovery,
        reconciliations,
        anomalies,
    ) = _active_commercial_records(db, estimate)

    issues: list[ValidationIssue] = []
    component_ids = {item.id for item in components}

    quantity_by_component: dict[str, list[Quantity]] = {item: [] for item in component_ids}
    for item in quantities:
        if item.required_component_id:
            quantity_by_component.setdefault(item.required_component_id, []).append(item)
    labour_by_component: dict[str, list[LabourActivity]] = {item: [] for item in component_ids}
    for item in labour:
        if item.required_component_id:
            labour_by_component.setdefault(item.required_component_id, []).append(item)
    pricing_by_component: dict[str, list[PricingComponent]] = {item: [] for item in component_ids}
    for item in pricing:
        if item.required_component_id:
            pricing_by_component.setdefault(item.required_component_id, []).append(item)

    lock_by_pricing: dict[str, list[CommercialMethodLock]] = {item.id: [] for item in pricing}
    for item in method_locks:
        lock_by_pricing.setdefault(item.component_id, []).append(item)
    recovery_by_pricing: dict[str, list[CommercialRecoveryRecord]] = {item.id: [] for item in pricing}
    for item in recovery:
        recovery_by_pricing.setdefault(item.component_id, []).append(item)
    reconciliation_by_component: dict[str, list[ComponentRequirementReconciliation]] = {
        item: [] for item in component_ids
    }
    for item in reconciliations:
        reconciliation_by_component.setdefault(item.required_component_id, []).append(item)

    selected_methods: list[str] = []
    for component in components:
        qrows = quantity_by_component.get(component.id, [])
        validated_q = [item for item in qrows if item.status == "validated" and item.numeric_value is not None]
        if len(validated_q) != 1:
            issues.append(
                ValidationIssue(
                    code="QUANTITY_NOT_UNIQUELY_VALIDATED",
                    subject_type="system_required_component",
                    subject_id=component.id,
                    detail=f"Expected exactly one active validated Quantity; found {len(validated_q)}.",
                )
            )

        required_labour = set(component.required_labour_activity_ids or [])
        validated_labour = {
            item.activity_name
            for item in labour_by_component.get(component.id, [])
            if item.status == "validated"
            and item.labour_quantity_hours is not None
            and item.productivity_source_id
        }
        missing_labour = sorted(required_labour - validated_labour)
        if missing_labour:
            issues.append(
                ValidationIssue(
                    code="LABOUR_NOT_FULLY_VALIDATED",
                    subject_type="system_required_component",
                    subject_id=component.id,
                    detail="Missing validated labour activities: " + ", ".join(missing_labour),
                )
            )

        prows = pricing_by_component.get(component.id, [])
        if len(prows) != 1:
            issues.append(
                ValidationIssue(
                    code="PRICING_COMPONENT_NOT_UNIQUE",
                    subject_type="system_required_component",
                    subject_id=component.id,
                    detail=f"Expected exactly one active PricingComponent; found {len(prows)}.",
                )
            )
            continue
        pricing_row = prows[0]
        if pricing_row.status != "validated":
            issues.append(
                ValidationIssue(
                    code="PRICING_COMPONENT_NOT_VALIDATED",
                    subject_type="pricing_component",
                    subject_id=pricing_row.id,
                    detail=f"PricingComponent status is {pricing_row.status!r}.",
                )
            )

        locks = lock_by_pricing.get(pricing_row.id, [])
        if len(locks) != 1:
            issues.append(
                ValidationIssue(
                    code="COMMERCIAL_METHOD_LOCK_NOT_UNIQUE",
                    subject_type="pricing_component",
                    subject_id=pricing_row.id,
                    detail=f"Expected exactly one CommercialMethodLock; found {len(locks)}.",
                )
            )
        else:
            lock = locks[0]
            selected_methods.append(lock.selected_pricing_method)
            if _norm(lock.validator_outcome) != "PASS":
                issues.append(
                    ValidationIssue(
                        code="COMMERCIAL_METHOD_NOT_FINAL_PASS",
                        subject_type="commercial_method_lock",
                        subject_id=lock.id,
                        detail=(
                            f"Method {lock.selected_pricing_method!r} has validator outcome "
                            f"{lock.validator_outcome!r}; final independent validation requires PASS."
                        ),
                    )
                )
            if lock.selected_pricing_method in {"Expert Estimate", "Not Priced"}:
                issues.append(
                    ValidationIssue(
                        code="NON_FINAL_COMMERCIAL_METHOD",
                        subject_type="commercial_method_lock",
                        subject_id=lock.id,
                        detail=f"{lock.selected_pricing_method} cannot pass final independent validation.",
                    )
                )

        recoveries = recovery_by_pricing.get(pricing_row.id, [])
        if len(recoveries) != 1:
            issues.append(
                ValidationIssue(
                    code="ACTIVE_RECOVERY_NOT_UNIQUE",
                    subject_type="pricing_component",
                    subject_id=pricing_row.id,
                    detail=f"Expected exactly one active CommercialRecoveryRecord; found {len(recoveries)}.",
                )
            )
        else:
            status = _norm(recoveries[0].recovery_status)
            if not (status.startswith("RECOVERED") or status == "VALIDLY_EXCLUDED"):
                issues.append(
                    ValidationIssue(
                        code="COMMERCIAL_RECOVERY_NOT_FINAL",
                        subject_type="commercial_recovery_record",
                        subject_id=recoveries[0].id,
                        detail=f"Recovery status {recoveries[0].recovery_status!r} is not final.",
                    )
                )

        recs = reconciliation_by_component.get(component.id, [])
        if len(recs) != 1 or _norm(recs[0].result if recs else None) != "PASS":
            issues.append(
                ValidationIssue(
                    code="COMPONENT_RECONCILIATION_NOT_PASS",
                    subject_type="system_required_component",
                    subject_id=component.id,
                    detail=(
                        "ComponentRequirementReconciliation must exist exactly once with result PASS."
                    ),
                )
            )

    active_pricing_ids = {item.id for item in pricing}
    for anomaly in anomalies:
        subject_ids = set(anomaly.subject_ids or [])
        if subject_ids and not (subject_ids & active_pricing_ids):
            continue
        if _norm(anomaly.result) == "REVIEW_REQUIRED":
            issues.append(
                ValidationIssue(
                    code="UNRESOLVED_PRICE_ANOMALY",
                    subject_type="price_anomaly_review",
                    subject_id=anomaly.id,
                    detail=anomaly.required_action or "Equal-price anomaly requires review.",
                )
            )

    positive_by_shared_key: dict[str, int] = {}
    for row in recovery:
        if not row.shared_component_key:
            continue
        if row.allocated_amount_aud_ex_gst is not None and Decimal(row.allocated_amount_aud_ex_gst) > 0:
            positive_by_shared_key[row.shared_component_key] = (
                positive_by_shared_key.get(row.shared_component_key, 0) + 1
            )
    for key, count in positive_by_shared_key.items():
        if count > 1:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_SHARED_RECOVERY",
                    subject_type="commercial_recovery_record",
                    subject_id=key,
                    detail=f"Shared recovery key has {count} positive allocations; expected at most one.",
                )
            )

    issues.extend(_release_issues(db, estimate, selected_methods))
    return tuple(issues)


def run_independent_validation(db: Session, estimate: Estimate) -> ValidationResult:
    issues = evaluate_independent_validation(db, estimate)
    table_hashes, record_count, state_hash = validation_state_hashes(db, estimate)
    result = "PASS" if not issues else "FAIL"
    run_id = f"QF-IV:{state_hash}"

    existing = db.scalar(
        select(GateEvidence)
        .where(
            GateEvidence.estimate_id == estimate.id,
            GateEvidence.gate_type == GATE_TYPE,
            GateEvidence.run_id == run_id,
            GateEvidence.result == result,
        )
        .order_by(GateEvidence.created_at.desc())
        .limit(1)
    )
    if existing is None:
        validator_payload = {
            "validator_id": VALIDATOR_ID,
            "validator_version": VALIDATOR_VERSION,
            "estimate_id": estimate.id,
            "state_hash": state_hash,
            "table_hashes": table_hashes,
            "issues": [issue.as_dict() for issue in issues],
            "result": result,
        }
        gate = GateEvidence(
            estimate_id=estimate.id,
            gate_type=GATE_TYPE,
            validator_id=VALIDATOR_ID,
            validator_version=VALIDATOR_VERSION,
            input_record_count=record_count,
            exception_count=len(issues),
            signed_validator_json_hash=_hash(validator_payload),
            result=result,
            required_action=(
                None
                if not issues
                else "Resolve all independent-validation exceptions and rerun the deterministic validator."
            ),
            input_table_hashes=[f"{name}:{digest}" for name, digest in sorted(table_hashes.items())],
            run_id=run_id,
            validation_timestamp=datetime.now(timezone.utc).isoformat(),
        )
        db.add(gate)
        db.flush()
    else:
        gate = existing

    if not issues:
        # This status intentionally blocks the legacy draft/in_review mutation routes
        # between final validation and creation of the immutable validated snapshot.
        estimate.status = "validated_pending_snapshot"
        db.flush()

    return ValidationResult(
        gate_evidence=gate,
        passed=not issues,
        issues=issues,
        state_hash=state_hash,
        table_hashes=table_hashes,
        input_record_count=record_count,
    )


def latest_passing_gate(db: Session, estimate: Estimate) -> GateEvidence:
    gate = db.scalar(
        select(GateEvidence)
        .where(
            GateEvidence.estimate_id == estimate.id,
            GateEvidence.gate_type == GATE_TYPE,
            GateEvidence.result == "PASS",
            GateEvidence.exception_count == 0,
        )
        .order_by(GateEvidence.created_at.desc())
        .limit(1)
    )
    if not gate:
        raise IndependentValidationError("No passing final independent-validation gate exists.")
    table_hashes, _, state_hash = validation_state_hashes(db, estimate)
    if gate.run_id != f"QF-IV:{state_hash}":
        raise IndependentValidationError(
            "The passing independent-validation gate is stale because governed estimate state changed."
        )
    retained = sorted(gate.input_table_hashes or [])
    current = sorted(f"{name}:{digest}" for name, digest in table_hashes.items())
    if retained != current:
        raise IndependentValidationError(
            "The passing independent-validation gate does not match current governed table hashes."
        )
    return gate


__all__ = [
    "GATE_TYPE",
    "VALIDATOR_ID",
    "VALIDATOR_VERSION",
    "IndependentValidationError",
    "ValidationIssue",
    "ValidationResult",
    "evaluate_independent_validation",
    "latest_passing_gate",
    "run_independent_validation",
    "validation_state_hashes",
]
