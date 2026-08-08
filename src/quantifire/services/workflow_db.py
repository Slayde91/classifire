from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..canonical_models import (
    EvidenceSource,
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
    GateEvidence,
    LabourActivity,
    PricingComponent,
    Quantity,
)
from ..models import Approval, AuditEvent, Estimate, Opening
from .workflow import WorkflowFacts, current_stage


_VALID_LOCK_RESULTS = {"PASS", "PROVISIONAL", "CONDITIONED", "PARTIAL"}
_VALID_COMMERCIAL_LOCK_RESULTS = {"PASS", "PROVISIONAL", "NOT PRICED"}
_VALID_RECONCILIATION_RESULTS = {"PASS", "PROVISIONAL"}
_FINAL_VALIDATION_GATE_TYPES = {
    "INDEPENDENT_VALIDATION",
    "FINAL_INDEPENDENT_VALIDATION",
    "MANDATORY_GATES",
}


def _norm(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True)
class WorkflowAssessment:
    facts: WorkflowFacts
    stage: str
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "facts": asdict(self.facts),
            "diagnostics": self.diagnostics,
        }


def assess_estimate_workflow(db: Session, estimate: Estimate) -> WorkflowAssessment:
    """Derive QUANTIFIRE v2.13 workflow facts from canonical persisted records.

    This adapter is intentionally fail-closed. Absence of a required retained record
    produces False rather than inferring completion from narrative text or legacy status.
    """

    evidence_count = db.scalar(
        select(func.count(EvidenceSource.id)).where(EvidenceSource.estimate_id == estimate.id)
    ) or 0
    evidence_intake_complete = evidence_count > 0

    openings = list(
        db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)).all()
    )
    opening_ids = [item.id for item in openings]

    links = []
    if opening_ids:
        links = list(
            db.scalars(
                select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
            ).all()
        )
    link_count_by_opening: dict[str, int] = {opening_id: 0 for opening_id in opening_ids}
    for link in links:
        link_count_by_opening[link.opening_id] = link_count_by_opening.get(link.opening_id, 0) + 1

    required_opening_fields_complete = bool(openings) and all(
        bool(item.substrate_type)
        and bool(item.substrate_plane)
        and bool(item.orientation)
        and bool(item.frl)
        for item in openings
    )
    all_openings_have_services = bool(openings) and all(
        link_count_by_opening.get(item.id, 0) > 0 for item in openings
    )
    physical_model_complete = required_opening_fields_complete and all_openings_have_services

    physical_locks = list(
        db.scalars(
            select(PhysicalModelLock).where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ).all()
    )
    valid_physical_locks = [
        item for item in physical_locks if _norm(item.validator_result) in _VALID_LOCK_RESULTS
    ]
    valid_physical_lock_ids = {item.id for item in valid_physical_locks}
    physical_model_locked = bool(valid_physical_locks)

    strategies = []
    if opening_ids and valid_physical_lock_ids:
        strategies = list(
            db.scalars(
                select(RepairStrategy).where(
                    RepairStrategy.opening_id.in_(opening_ids),
                    RepairStrategy.physical_model_lock_id.in_(valid_physical_lock_ids),
                    RepairStrategy.status.in_(["candidate_selected", "locked"]),
                )
            ).all()
        )
    strategy_opening_ids = {item.opening_id for item in strategies}
    valid_strategy_ids = {item.id for item in strategies}
    technical_search_complete = bool(openings) and all(
        opening_id in strategy_opening_ids for opening_id in opening_ids
    )

    repair_locks = []
    if opening_ids and valid_strategy_ids:
        repair_locks = list(
            db.scalars(
                select(RepairStrategyLock).where(
                    RepairStrategyLock.opening_id.in_(opening_ids),
                    RepairStrategyLock.repair_strategy_id.in_(valid_strategy_ids),
                    RepairStrategyLock.invalidated_at.is_(None),
                )
            ).all()
        )
    valid_repair_locks = [
        item for item in repair_locks if _norm(item.validator_result) in _VALID_LOCK_RESULTS
    ]
    valid_lock_by_opening = {item.opening_id: item for item in valid_repair_locks}
    repair_strategy_locked = bool(openings) and all(
        opening_id in valid_lock_by_opening for opening_id in opening_ids
    )

    components = []
    if opening_ids:
        components = list(
            db.scalars(
                select(SystemRequiredComponent).where(
                    SystemRequiredComponent.opening_id.in_(opening_ids)
                )
            ).all()
        )
    component_ids = {item.id for item in components}
    components_by_opening: dict[str, list[SystemRequiredComponent]] = {
        opening_id: [] for opening_id in opening_ids
    }
    for item in components:
        components_by_opening.setdefault(item.opening_id, []).append(item)

    locks_reference_existing_components = repair_strategy_locked and all(
        bool(lock.required_component_ids)
        and set(lock.required_component_ids).issubset(component_ids)
        for lock in valid_lock_by_opening.values()
    )
    all_openings_have_components = bool(openings) and all(
        bool(components_by_opening.get(opening_id)) for opening_id in opening_ids
    )
    components_derived = locks_reference_existing_components and all_openings_have_components

    quantity_component_ids = set()
    labour_component_ids = set()
    if component_ids:
        quantity_component_ids = set(
            db.scalars(
                select(Quantity.required_component_id).where(
                    Quantity.required_component_id.in_(component_ids)
                )
            ).all()
        )
        labour_component_ids = set(
            db.scalars(
                select(LabourActivity.required_component_id).where(
                    LabourActivity.required_component_id.in_(component_ids)
                )
            ).all()
        )
    required_labour_component_ids = {
        item.id for item in components if bool(item.required_labour_activity_ids)
    }
    quantity_complete = bool(component_ids) and component_ids.issubset(quantity_component_ids)
    labour_complete = required_labour_component_ids.issubset(labour_component_ids)
    quantity_and_labour_complete = components_derived and quantity_complete and labour_complete

    pricing_components = []
    if component_ids:
        pricing_components = list(
            db.scalars(
                select(PricingComponent).where(
                    PricingComponent.required_component_id.in_(component_ids)
                )
            ).all()
        )
    pricing_by_required: dict[str, list[PricingComponent]] = {item: [] for item in component_ids}
    for item in pricing_components:
        if item.required_component_id:
            pricing_by_required.setdefault(item.required_component_id, []).append(item)
    all_required_components_priced = bool(component_ids) and all(
        bool(pricing_by_required.get(component_id)) for component_id in component_ids
    )

    pricing_component_ids = {item.id for item in pricing_components}
    method_locks = []
    recovery_records = []
    if pricing_component_ids:
        method_locks = list(
            db.scalars(
                select(CommercialMethodLock).where(
                    CommercialMethodLock.component_id.in_(pricing_component_ids)
                )
            ).all()
        )
        recovery_records = list(
            db.scalars(
                select(CommercialRecoveryRecord).where(
                    CommercialRecoveryRecord.component_id.in_(pricing_component_ids),
                    CommercialRecoveryRecord.active.is_(True),
                )
            ).all()
        )
    valid_method_component_ids = {
        item.component_id
        for item in method_locks
        if _norm(item.validator_outcome) in {_norm(x) for x in _VALID_COMMERCIAL_LOCK_RESULTS}
    }
    recovered_component_ids = {
        item.component_id
        for item in recovery_records
        if not _norm(item.recovery_status).startswith("REJECTED")
    }

    reconciliations = []
    if component_ids:
        reconciliations = list(
            db.scalars(
                select(ComponentRequirementReconciliation).where(
                    ComponentRequirementReconciliation.required_component_id.in_(component_ids)
                )
            ).all()
        )
    reconciliation_by_required = {item.required_component_id: item for item in reconciliations}
    reconciliation_complete = bool(component_ids) and all(
        component_id in reconciliation_by_required
        and _norm(reconciliation_by_required[component_id].result)
        in {_norm(x) for x in _VALID_RECONCILIATION_RESULTS}
        for component_id in component_ids
    )

    commercial_pricing_and_recovery_complete = (
        quantity_and_labour_complete
        and all_required_components_priced
        and pricing_component_ids.issubset(valid_method_component_ids)
        and pricing_component_ids.issubset(recovered_component_ids)
        and reconciliation_complete
    )

    gate_records = list(
        db.scalars(select(GateEvidence).where(GateEvidence.estimate_id == estimate.id)).all()
    )
    final_validation_records = [
        item
        for item in gate_records
        if _norm(item.gate_type) in _FINAL_VALIDATION_GATE_TYPES
    ]
    independent_validation_passed = any(
        _norm(item.result) == "PASS"
        and (item.exception_count is None or int(item.exception_count) == 0)
        for item in final_validation_records
    )

    validated_snapshot_created = bool(
        independent_validation_passed and estimate.snapshot_json and estimate.snapshot_hash
    )

    output_rendered = bool(
        db.scalar(
            select(func.count(AuditEvent.id)).where(
                AuditEvent.entity_type == "estimate",
                AuditEvent.entity_id == estimate.id,
                AuditEvent.action == "render_output",
            )
        )
        or 0
    )

    human_release_approved = bool(
        db.scalar(
            select(func.count(Approval.id)).where(
                Approval.entity_type == "estimate",
                Approval.entity_id == estimate.id,
                Approval.approval_type.in_(["human_release", "release"]),
                Approval.status == "approved",
            )
        )
        or 0
    )

    facts = WorkflowFacts(
        evidence_intake_complete=evidence_intake_complete,
        physical_model_complete=physical_model_complete,
        physical_model_locked=physical_model_locked,
        technical_search_complete=technical_search_complete,
        repair_strategy_locked=repair_strategy_locked,
        components_derived=components_derived,
        quantity_and_labour_complete=quantity_and_labour_complete,
        commercial_pricing_and_recovery_complete=commercial_pricing_and_recovery_complete,
        independent_validation_passed=independent_validation_passed,
        validated_snapshot_created=validated_snapshot_created,
        output_rendered=output_rendered,
        human_release_approved=human_release_approved,
    )

    diagnostics = {
        "evidence_source_count": int(evidence_count),
        "opening_count": len(openings),
        "service_opening_link_count": len(links),
        "valid_physical_model_lock_count": len(valid_physical_locks),
        "current_repair_strategy_count": len(strategies),
        "valid_repair_strategy_lock_count": len(valid_repair_locks),
        "required_component_count": len(components),
        "quantity_covered_component_count": len(quantity_component_ids & component_ids),
        "labour_required_component_count": len(required_labour_component_ids),
        "labour_covered_component_count": len(labour_component_ids & required_labour_component_ids),
        "pricing_component_count": len(pricing_components),
        "valid_commercial_method_lock_count": len(valid_method_component_ids),
        "active_commercial_recovery_count": len(recovery_records),
        "component_reconciliation_count": len(reconciliations),
        "gate_evidence_count": len(gate_records),
        "final_independent_validation_gate_count": len(final_validation_records),
        "fail_closed_notes": [
            "Only Repair Strategies tied to an active valid Physical Model Lock count as current.",
            "Only Repair Strategy Locks tied to a current Repair Strategy count as valid.",
            "Output rendering is complete only when a render_output audit event is retained.",
            "Human release is complete only when an approved release Approval record is retained.",
            "Narrative or legacy status text is never treated as a lock or validation receipt.",
        ],
    }

    return WorkflowAssessment(
        facts=facts,
        stage=current_stage(facts).value,
        diagnostics=diagnostics,
    )
