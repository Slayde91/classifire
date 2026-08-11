from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from sqlalchemy.orm import Session

from ..models import Estimate
from .physical_scope import assess_physical_model_completeness
from .workflow import (
    WorkflowAction,
    WorkflowTransitionError,
    blockers_for,
    current_stage,
    require_action,
)
from .workflow_db import WorkflowAssessment, assess_estimate_workflow


_UPSTREAM_MUTATING_ACTIONS = {
    WorkflowAction.INGEST_EVIDENCE,
    WorkflowAction.EDIT_PHYSICAL_MODEL,
    WorkflowAction.LOCK_PHYSICAL_MODEL,
    WorkflowAction.SEARCH_TECHNICAL,
    WorkflowAction.LOCK_REPAIR_STRATEGY,
    WorkflowAction.DERIVE_COMPONENTS,
    WorkflowAction.CALCULATE_QUANTITY_AND_LABOUR,
    WorkflowAction.PRICE_AND_RECOVER,
}
_LOCKED_STAGE_ACTIONS = _UPSTREAM_MUTATING_ACTIONS | {
    WorkflowAction.RUN_INDEPENDENT_VALIDATION,
    WorkflowAction.CREATE_VALIDATED_SNAPSHOT,
}


@dataclass(frozen=True)
class WorkflowGuardReceipt:
    action: WorkflowAction
    allowed: bool
    stage: str
    blockers: tuple[str, ...]
    diagnostics: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "stage": self.stage,
            "blockers": list(self.blockers),
            "diagnostics": self.diagnostics,
        }


def _status_blockers(estimate: Estimate, action: WorkflowAction) -> tuple[str, ...]:
    status = (estimate.status or "").strip().lower()
    if status == "validated_pending_snapshot" and action in _UPSTREAM_MUTATING_ACTIONS:
        return (
            "estimate is frozen after passing independent validation; controlled validation invalidation is required before upstream changes",
        )
    if status in {"locked", "released", "approved"} and action in _LOCKED_STAGE_ACTIONS:
        return (
            f"estimate status {status!r} freezes upstream workflow actions; use the controlled release workflow",
        )
    return ()


def _with_scope_aware_physical_completeness(
    db: Session,
    estimate: Estimate,
    assessment: WorkflowAssessment,
) -> WorkflowAssessment:
    """Apply the current CLASSIFIRE physical-scope completeness policy.

    The original v2.13 database adapter assumed that every Opening required at
    least one ServiceOpeningLink. That is incorrect for a blank aperture or an
    empty/redundant core hole that itself requires sealing. A service-free Opening
    is complete only when it is explicitly classified as a governed blank Opening;
    ordinary service penetrations still require at least one canonical Service link.
    """

    physical = assess_physical_model_completeness(db, estimate.id)
    facts = assessment.facts
    if facts.physical_model_complete != physical.complete:
        facts = replace(facts, physical_model_complete=physical.complete)

    diagnostics = dict(assessment.diagnostics)
    diagnostics["scope_aware_physical_completeness"] = physical.as_dict()
    return WorkflowAssessment(
        facts=facts,
        stage=current_stage(facts).value,
        diagnostics=diagnostics,
    )


def check_estimate_action(
    db: Session,
    estimate: Estimate,
    action: WorkflowAction,
) -> WorkflowGuardReceipt:
    """Return a deterministic, fail-closed preflight receipt for one estimate action."""
    assessment = _with_scope_aware_physical_completeness(
        db,
        estimate,
        assess_estimate_workflow(db, estimate),
    )
    blockers = tuple((*blockers_for(action, assessment.facts), *_status_blockers(estimate, action)))
    return WorkflowGuardReceipt(
        action=action,
        allowed=not blockers,
        stage=assessment.stage,
        blockers=blockers,
        diagnostics=assessment.diagnostics,
    )


def require_estimate_action(
    db: Session,
    estimate: Estimate,
    action: WorkflowAction,
) -> WorkflowAssessment:
    """Raise WorkflowTransitionError unless retained database state and estimate status permit the action."""
    assessment = _with_scope_aware_physical_completeness(
        db,
        estimate,
        assess_estimate_workflow(db, estimate),
    )
    status_blockers = _status_blockers(estimate, action)
    if status_blockers:
        raise WorkflowTransitionError(action, status_blockers)
    require_action(action, assessment.facts)
    return assessment


__all__ = [
    "WorkflowGuardReceipt",
    "WorkflowTransitionError",
    "check_estimate_action",
    "require_estimate_action",
]
