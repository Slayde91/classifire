from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate
from ..physical_models import PhysicalModelLock
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


class PhysicalMutationError(RuntimeError):
    """Raised when a physical-model mutation would violate the active lock."""


def _active_physical_lock_exists(db: Session, estimate_id: str) -> bool:
    return bool(
        db.scalar(
            select(PhysicalModelLock.id)
            .where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .limit(1)
        )
    )


def _require_no_active_physical_lock(db: Session, estimate: Estimate) -> None:
    if _active_physical_lock_exists(db, estimate.id):
        raise PhysicalMutationError(
            "An active Physical Model Lock exists. Physical changes require a future "
            "governed reopen workflow; Layer 2 never invalidates or replaces a lock."
        )


def require_evidence_intake(db: Session, estimate: Estimate) -> None:
    """Require that new evidence is admissible before an immutable lock exists."""
    _require_no_active_physical_lock(db, estimate)
    require_estimate_action(db, estimate, WorkflowAction.INGEST_EVIDENCE)


def require_evidence_mutation(db: Session, estimate: Estimate) -> None:
    """Compatibility name for the evidence-registration API boundary."""
    require_evidence_intake(db, estimate)


def require_physical_edit(db: Session, estimate: Estimate) -> None:
    """Require evidence-first physical editing before an immutable lock exists."""
    _require_no_active_physical_lock(db, estimate)
    require_estimate_action(db, estimate, WorkflowAction.EDIT_PHYSICAL_MODEL)


def require_physical_model_mutation(db: Session, estimate: Estimate) -> None:
    """Compatibility name for callers that do not distinguish edit operation types."""
    require_physical_edit(db, estimate)


__all__ = [
    "PhysicalMutationError",
    "require_evidence_intake",
    "require_evidence_mutation",
    "require_physical_edit",
    "require_physical_model_mutation",
]
