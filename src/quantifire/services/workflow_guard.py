from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import Estimate
from .workflow import WorkflowAction, WorkflowTransitionError, blockers_for, require_action
from .workflow_db import WorkflowAssessment, assess_estimate_workflow


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


def check_estimate_action(
    db: Session,
    estimate: Estimate,
    action: WorkflowAction,
) -> WorkflowGuardReceipt:
    """Return a deterministic, fail-closed preflight receipt for one estimate action."""
    assessment = assess_estimate_workflow(db, estimate)
    blockers = blockers_for(action, assessment.facts)
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
    """Raise WorkflowTransitionError unless the retained database state permits the action."""
    assessment = assess_estimate_workflow(db, estimate)
    require_action(action, assessment.facts)
    return assessment


__all__ = [
    "WorkflowGuardReceipt",
    "WorkflowTransitionError",
    "check_estimate_action",
    "require_estimate_action",
]
