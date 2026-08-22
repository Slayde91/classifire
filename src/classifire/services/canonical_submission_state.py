"""Shared fail-closed current-state guard for an initial physical submission.

Both the no-write adjudication preflight and the eventual controlled writer use
this module.  Keeping the database-state checks here prevents the writer from
drifting into a weaker interpretation of an empty, unlocked estimate.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..canonical_models import (
    Defect,
    EvidenceSource,
    Package15CandidateRequirement,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceMaterialHypothesis,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from ..commercial_models import (
    AuditTrail,
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    EstimateCertificate,
    GateEvidence,
    LabourActivity,
    PriceAnomalyReview,
    PricingComponent,
    Quantity,
    QuantityFormulaInput,
)
from ..models import Approval, AuditEvent, Estimate, EstimateLine, Opening, RuleEvaluation, Service
from .protected_state_fingerprint import (
    PROTECTED_STATE_FINGERPRINT_VERSION,
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)
from .workflow import WorkflowAction
from .workflow_guard import check_estimate_action

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class CanonicalSubmissionStateError(RuntimeError):
    """The live canonical state is no longer safe for a one-shot submission."""


def _count(db: Session, model: type[Any], *conditions: Any) -> int:
    statement = select(func.count()).select_from(model)
    if conditions:
        statement = statement.where(*conditions)
    return int(db.scalar(statement) or 0)


def _require_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CanonicalSubmissionStateError(f"{label} is not a valid SHA-256 fingerprint.")
    return value


def _historical_snapshot_ids(lock: PhysicalModelLock, *, field: str) -> set[str]:
    value = getattr(lock, field)
    if not isinstance(value, list):
        raise CanonicalSubmissionStateError(
            f"Historical Physical Model Lock {lock.id} has malformed {field}."
        )
    identifiers: set[str] = set()
    for index, item in enumerate(value, start=1):
        if not isinstance(item, str) or not item.strip():
            raise CanonicalSubmissionStateError(
                f"Historical Physical Model Lock {lock.id} has malformed {field}[{index}]."
            )
        identifiers.add(item.strip())
    return identifiers


def _historical_physical_descendant_counts(
    db: Session,
    *,
    estimate_id: str,
) -> dict[str, int]:
    """Find descendants that remain after an invalidated physical-model lock.

    The current model can be empty while a removed historical opening/service
    still has technical or commercial descendants.  Persisted lock snapshots
    are therefore deliberately traversed regardless of invalidation state.
    """

    locks = list(
        db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate_id)
        ).all()
    )
    names = (
        "historical_lock_repair_strategy_count",
        "historical_lock_repair_strategy_lock_count",
        "historical_lock_system_required_component_count",
        "historical_lock_candidate_requirement_count",
        "historical_lock_service_material_hypothesis_count",
        "historical_lock_service_count",
        "historical_lock_service_opening_link_count",
        "historical_lock_quantity_count",
        "historical_lock_quantity_formula_input_count",
        "historical_lock_labour_activity_count",
        "historical_lock_pricing_component_count",
        "historical_lock_commercial_method_lock_count",
        "historical_lock_commercial_recovery_record_count",
        "historical_lock_component_reconciliation_count",
    )
    if not locks:
        return dict.fromkeys(names, 0)

    lock_ids = {lock.id for lock in locks}
    historical_opening_ids: set[str] = set()
    historical_service_ids: set[str] = set()
    for lock in locks:
        historical_opening_ids.update(_historical_snapshot_ids(lock, field="opening_ids"))
        historical_service_ids.update(_historical_snapshot_ids(lock, field="service_ids"))

    strategy_conditions = [RepairStrategy.physical_model_lock_id.in_(lock_ids)]
    if historical_opening_ids:
        strategy_conditions.append(RepairStrategy.opening_id.in_(historical_opening_ids))
    strategies = list(db.scalars(select(RepairStrategy).where(or_(*strategy_conditions))).all())
    strategy_ids = {strategy.id for strategy in strategies}

    repair_lock_conditions = []
    if strategy_ids:
        repair_lock_conditions.append(RepairStrategyLock.repair_strategy_id.in_(strategy_ids))
    if historical_opening_ids:
        repair_lock_conditions.append(RepairStrategyLock.opening_id.in_(historical_opening_ids))

    component_conditions = []
    if historical_opening_ids:
        component_conditions.append(SystemRequiredComponent.opening_id.in_(historical_opening_ids))
    if historical_service_ids:
        component_conditions.append(SystemRequiredComponent.service_id.in_(historical_service_ids))
    components = (
        list(db.scalars(select(SystemRequiredComponent).where(or_(*component_conditions))).all())
        if component_conditions
        else []
    )
    component_ids = {component.id for component in components}

    service_conditions = []
    if historical_opening_ids:
        service_conditions.append(Service.opening_id.in_(historical_opening_ids))
    if historical_service_ids:
        service_conditions.append(Service.id.in_(historical_service_ids))
    services = (
        list(db.scalars(select(Service).where(or_(*service_conditions))).all())
        if service_conditions
        else []
    )
    service_ids = historical_service_ids | {service.id for service in services}

    link_conditions = []
    if historical_opening_ids:
        link_conditions.append(ServiceOpeningLink.opening_id.in_(historical_opening_ids))
    if service_ids:
        link_conditions.append(ServiceOpeningLink.service_id.in_(service_ids))

    quantities = (
        list(
            db.scalars(
                select(Quantity).where(Quantity.required_component_id.in_(component_ids))
            ).all()
        )
        if component_ids
        else []
    )
    quantity_ids = {quantity.id for quantity in quantities}
    pricing_components = (
        list(
            db.scalars(
                select(PricingComponent).where(
                    or_(
                        PricingComponent.required_component_id.in_(component_ids),
                        PricingComponent.opening_id.in_(historical_opening_ids),
                        PricingComponent.service_id.in_(service_ids),
                    )
                )
            ).all()
        )
        if component_ids or historical_opening_ids or service_ids
        else []
    )
    pricing_component_ids = {component.id for component in pricing_components}
    reconciliation_conditions = []
    if component_ids:
        reconciliation_conditions.append(
            ComponentRequirementReconciliation.required_component_id.in_(component_ids)
        )
    if historical_opening_ids:
        reconciliation_conditions.append(
            ComponentRequirementReconciliation.opening_id.in_(historical_opening_ids)
        )

    return {
        "historical_lock_repair_strategy_count": len(strategies),
        "historical_lock_repair_strategy_lock_count": _count(
            db, RepairStrategyLock, or_(*repair_lock_conditions)
        )
        if repair_lock_conditions
        else 0,
        "historical_lock_system_required_component_count": len(components),
        "historical_lock_candidate_requirement_count": _count(
            db,
            Package15CandidateRequirement,
            Package15CandidateRequirement.opening_id.in_(historical_opening_ids),
        )
        if historical_opening_ids
        else 0,
        "historical_lock_service_material_hypothesis_count": _count(
            db,
            ServiceMaterialHypothesis,
            ServiceMaterialHypothesis.service_id.in_(service_ids),
        )
        if service_ids
        else 0,
        "historical_lock_service_count": len(services),
        "historical_lock_service_opening_link_count": _count(
            db, ServiceOpeningLink, or_(*link_conditions)
        )
        if link_conditions
        else 0,
        "historical_lock_quantity_count": len(quantities),
        "historical_lock_quantity_formula_input_count": _count(
            db, QuantityFormulaInput, QuantityFormulaInput.quantity_record_id.in_(quantity_ids)
        )
        if quantity_ids
        else 0,
        "historical_lock_labour_activity_count": _count(
            db, LabourActivity, LabourActivity.required_component_id.in_(component_ids)
        )
        if component_ids
        else 0,
        "historical_lock_pricing_component_count": len(pricing_components),
        "historical_lock_commercial_method_lock_count": _count(
            db, CommercialMethodLock, CommercialMethodLock.component_id.in_(pricing_component_ids)
        )
        if pricing_component_ids
        else 0,
        "historical_lock_commercial_recovery_record_count": _count(
            db,
            CommercialRecoveryRecord,
            CommercialRecoveryRecord.component_id.in_(pricing_component_ids),
        )
        if pricing_component_ids
        else 0,
        "historical_lock_component_reconciliation_count": _count(
            db, ComponentRequirementReconciliation, or_(*reconciliation_conditions)
        )
        if reconciliation_conditions
        else 0,
    }


def assess_empty_initial_submission_state(
    db: Session,
    *,
    estimate_id: str,
    expected_fingerprint: str,
    expected_component_fingerprints: dict[str, str],
    expected_counts: dict[str, int],
) -> dict[str, Any]:
    """Recheck the exact preflight baseline immediately before an initial write."""

    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise CanonicalSubmissionStateError("Requested estimate no longer exists.")
    if (estimate.status or "").strip().lower() not in {"draft", "in_review"}:
        raise CanonicalSubmissionStateError("Requested estimate is no longer editable.")

    snapshot = protected_state_snapshot_from_session(db, estimate_id)
    fingerprint = protected_state_fingerprint(snapshot)
    components = protected_component_fingerprints(snapshot)
    counts = protected_state_counts(snapshot)
    if snapshot.get("fingerprint_version") != PROTECTED_STATE_FINGERPRINT_VERSION:
        raise CanonicalSubmissionStateError("Protected-state fingerprint version is unsupported.")
    if fingerprint != _require_sha256(
        expected_fingerprint, label="Expected protected-state fingerprint"
    ):
        raise CanonicalSubmissionStateError(
            "Current protected-state fingerprint no longer matches the signed admission."
        )
    if not isinstance(expected_component_fingerprints, dict) or not isinstance(
        expected_counts, dict
    ):
        raise CanonicalSubmissionStateError(
            "Signed admission lacks protected-state component/count evidence."
        )
    expected_components = {
        key: _require_sha256(value, label=f"Protected component {key}")
        for key, value in expected_component_fingerprints.items()
    }
    if expected_components != components:
        raise CanonicalSubmissionStateError(
            "Current protected-state component fingerprints no longer match the signed admission."
        )
    if expected_counts != counts:
        raise CanonicalSubmissionStateError(
            "Current protected-state component counts no longer match the signed admission."
        )

    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate_id)).all()
    )
    opening_count = len(opening_ids)
    service_count = _count(db, Service, Service.opening_id.in_(opening_ids)) if opening_ids else 0
    link_count = (
        _count(db, ServiceOpeningLink, ServiceOpeningLink.opening_id.in_(opening_ids))
        if opening_ids
        else 0
    )
    active_lock_count = _count(
        db,
        PhysicalModelLock,
        PhysicalModelLock.estimate_id == estimate_id,
        PhysicalModelLock.invalidated_at.is_(None),
    )
    if opening_count or service_count or link_count or active_lock_count:
        raise CanonicalSubmissionStateError(
            "Canonical Physical Model is no longer empty and unlocked for one-shot "
            "initial submission."
        )

    evidence_count = _count(db, EvidenceSource, EvidenceSource.estimate_id == estimate_id)
    defect_count = _count(db, Defect, Defect.estimate_id == estimate_id)
    if evidence_count <= 0 or defect_count <= 0:
        raise CanonicalSubmissionStateError(
            "Retained evidence or defects are missing from the canonical estimate."
        )

    required_component_ids: list[str] = []
    pricing_component_ids = list(
        db.scalars(
            select(PricingComponent.id).where(PricingComponent.estimate_id == estimate_id)
        ).all()
    )
    historical_descendants = _historical_physical_descendant_counts(db, estimate_id=estimate_id)
    downstream = {
        "repair_strategy_count": 0,
        "repair_strategy_lock_count": 0,
        "system_required_component_count": 0,
        "estimate_line_count": _count(db, EstimateLine, EstimateLine.estimate_id == estimate_id),
        "quantity_count": _count(db, Quantity, Quantity.estimate_id == estimate_id),
        "labour_activity_count": _count(
            db, LabourActivity, LabourActivity.estimate_id == estimate_id
        ),
        "pricing_component_count": _count(
            db, PricingComponent, PricingComponent.estimate_id == estimate_id
        ),
        "commercial_method_lock_count": _count(
            db, CommercialMethodLock, CommercialMethodLock.component_id.in_(pricing_component_ids)
        )
        if pricing_component_ids
        else 0,
        "commercial_recovery_record_count": _count(
            db,
            CommercialRecoveryRecord,
            CommercialRecoveryRecord.component_id.in_(pricing_component_ids),
        )
        if pricing_component_ids
        else 0,
        "component_requirement_reconciliation_count": _count(
            db,
            ComponentRequirementReconciliation,
            ComponentRequirementReconciliation.required_component_id.in_(required_component_ids),
        )
        if required_component_ids
        else 0,
        "gate_evidence_count": _count(db, GateEvidence, GateEvidence.estimate_id == estimate_id),
        "rule_evaluation_count": _count(
            db, RuleEvaluation, RuleEvaluation.estimate_id == estimate_id
        ),
        "price_anomaly_review_count": _count(
            db, PriceAnomalyReview, PriceAnomalyReview.estimate_id == estimate_id
        ),
        "estimate_certificate_count": _count(
            db, EstimateCertificate, EstimateCertificate.estimate_id == estimate_id
        ),
        "audit_trail_count": _count(db, AuditTrail, AuditTrail.estimate_id == estimate_id),
        "approval_count": _count(
            db, Approval, Approval.entity_type == "estimate", Approval.entity_id == estimate_id
        ),
        "render_output_audit_event_count": _count(
            db,
            AuditEvent,
            AuditEvent.entity_type == "estimate",
            AuditEvent.entity_id == estimate_id,
            AuditEvent.action == "render_output",
        ),
        "snapshot_present": estimate.snapshot_hash is not None
        or estimate.snapshot_json is not None,
        "estimate_locked_or_approved": bool(estimate.locked_at or estimate.approved_at),
        **historical_descendants,
    }
    blockers = sorted(
        key
        for key, value in downstream.items()
        if (isinstance(value, int) and value > 0) or (isinstance(value, bool) and value)
    )
    if blockers:
        raise CanonicalSubmissionStateError(
            "Downstream estimate records would be invalidated: " + ", ".join(blockers)
        )

    edit_guard = check_estimate_action(db, estimate, WorkflowAction.EDIT_PHYSICAL_MODEL)
    if not edit_guard.allowed:
        raise CanonicalSubmissionStateError(
            "Workflow does not permit physical-model editing: " + "; ".join(edit_guard.blockers)
        )
    return {
        "protected_state": {
            "fingerprint_version": PROTECTED_STATE_FINGERPRINT_VERSION,
            "fingerprint": fingerprint,
            "component_fingerprints": components,
            "counts": counts,
        },
        "canonical_counts": {
            "openings": opening_count,
            "services": service_count,
            "service_opening_links": link_count,
            "active_physical_model_locks": active_lock_count,
            "historical_physical_model_locks": _count(
                db, PhysicalModelLock, PhysicalModelLock.estimate_id == estimate_id
            ),
            "evidence_sources": evidence_count,
            "defects": defect_count,
        },
        "downstream": downstream,
        "workflow_edit_physical_model": edit_guard.as_dict(),
    }


__all__ = [
    "CanonicalSubmissionStateError",
    "assess_empty_initial_submission_state",
]
