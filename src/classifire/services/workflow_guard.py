from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import Estimate
from .workflow import WorkflowAction, WorkflowTransitionError, blockers_for
from .workflow_db import WorkflowAssessment, assess_estimate_workflow

_PHYSICAL_MUTATING_ACTIONS = {
    WorkflowAction.INGEST_EVIDENCE,
    WorkflowAction.EDIT_PHYSICAL_MODEL,
    WorkflowAction.LOCK_PHYSICAL_MODEL,
}
_EDITABLE_ESTIMATE_STATUSES = {"draft", "in_review"}


@dataclass(frozen=True, slots=True)
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


class PhysicalModelLockRequiredError(RuntimeError):
    """Raised when a downstream estimate action lacks a current Physical Model Lock."""

    def __init__(self) -> None:
        super().__init__(
            "A current active PASS Physical Model Lock is required before downstream "
            "estimate operations."
        )


def _status_blockers(estimate: Estimate, action: WorkflowAction) -> tuple[str, ...]:
    """Keep physical mutations within the estimate's editable lifecycle states."""
    status = (estimate.status or "").strip().lower()
    if action in _PHYSICAL_MUTATING_ACTIONS and status not in _EDITABLE_ESTIMATE_STATUSES:
        return (
            f"estimate status {status or 'unset'!r} does not permit physical-model changes; "
            "a controlled reopen workflow is required",
        )
    return ()


def _assessment_and_blockers(
    db: Session,
    estimate: Estimate,
    action: WorkflowAction,
) -> tuple[WorkflowAssessment, tuple[str, ...]]:
    assessment = assess_estimate_workflow(db, estimate)
    blockers = tuple((*blockers_for(action, assessment.facts), *_status_blockers(estimate, action)))
    return assessment, blockers


def check_estimate_action(
    db: Session,
    estimate: Estimate,
    action: WorkflowAction,
) -> WorkflowGuardReceipt:
    """Return a deterministic, fail-closed preflight receipt for one action."""
    assessment, blockers = _assessment_and_blockers(db, estimate, action)
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
    """Raise unless retained physical state and lifecycle permit the action."""
    assessment, blockers = _assessment_and_blockers(db, estimate, action)
    if blockers:
        raise WorkflowTransitionError(action, blockers)
    return assessment


def require_active_physical_model_lock(
    db: Session,
    estimate: Estimate,
) -> WorkflowAssessment:
    """Raise unless the assessment confirms a current active PASS Physical Model Lock.

    The workflow assessment owns lock-currentness validation, including content
    fingerprint checks. Downstream routes intentionally depend on that one
    fail-closed fact instead of making their own raw lock-table queries.
    """
    assessment = assess_estimate_workflow(db, estimate)
    if not assessment.facts.physical_model_locked:
        raise PhysicalModelLockRequiredError()
    return assessment


__all__ = [
    "PhysicalModelLockRequiredError",
    "WorkflowGuardReceipt",
    "WorkflowTransitionError",
    "check_estimate_action",
    "require_active_physical_model_lock",
    "require_estimate_action",
]
