from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Estimate, Opening
from ..physical_models import EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from .physical_scope import assess_physical_model_completeness
from .workflow import WorkflowFacts, current_stage

_VALID_PHYSICAL_MODEL_LOCK_RESULTS = {"PASS"}


def _norm(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", "_").replace(" ", "_")


@dataclass(frozen=True, slots=True)
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
    """Derive Layer 2 workflow facts from retained physical records.

    This adapter is intentionally fail-closed. Only active evidence, a complete
    physical model, and an active PASS Physical Model Lock establish completion.
    Narrative status text and later-stage records are not treated as substitutes.
    """
    evidence_count = (
        db.scalar(
            select(func.count(EvidenceSource.id)).where(
                EvidenceSource.estimate_id == estimate.id,
                EvidenceSource.status == "active",
            )
        )
        or 0
    )
    physical_completeness = assess_physical_model_completeness(db, estimate.id)
    service_opening_link_count = (
        db.scalar(
            select(func.count(ServiceOpeningLink.id))
            .join_from(ServiceOpeningLink, Opening)
            .where(Opening.estimate_id == estimate.id)
        )
        or 0
    )
    active_locks = list(
        db.scalars(
            select(PhysicalModelLock).where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ).all()
    )
    current_content_hash: str | None = None
    current_payload_is_pass = False
    current_lock_evaluation = "verified"
    try:
        # Import locally to avoid the physical-model creation guard importing this
        # workflow adapter during module initialisation. This is deliberately the
        # unguarded payload helper: we are checking whether an existing lock still
        # represents retained state, not attempting to create a replacement lock.
        from .physical_model import build_current_physical_model_lock_payload

        current_payload = build_current_physical_model_lock_payload(db, estimate)
        current_content_hash = str(current_payload["content_hash"])
        current_payload_is_pass = current_payload.get("validator_result") == "PASS"
    except Exception:  # noqa: BLE001 - inability to prove freshness must fail closed.
        current_lock_evaluation = "unavailable"

    valid_locks = [
        item
        for item in active_locks
        if (
            _norm(item.validator_result) in _VALID_PHYSICAL_MODEL_LOCK_RESULTS
            and current_payload_is_pass
            and current_content_hash is not None
            and item.content_hash == current_content_hash
        )
    ]
    stale_active_lock_count = len(active_locks) - len(valid_locks)

    facts = WorkflowFacts(
        evidence_intake_complete=bool(evidence_count),
        physical_model_complete=physical_completeness.complete,
        physical_model_locked=bool(valid_locks),
        technical_search_complete=False,
    )
    diagnostics = {
        "evidence_source_count": int(evidence_count),
        "opening_count": physical_completeness.opening_count,
        "service_opening_link_count": int(service_opening_link_count),
        "active_physical_model_lock_count": len(active_locks),
        "valid_physical_model_lock_count": len(valid_locks),
        "stale_or_unverifiable_active_physical_model_lock_count": stale_active_lock_count,
        "current_physical_model_content_hash": current_content_hash,
        "current_physical_model_lock_evaluation": current_lock_evaluation,
        "scope_aware_physical_completeness": physical_completeness.as_dict(),
        "fail_closed_notes": [
            "Only active EvidenceSource records count as evidence intake.",
            "A blank opening with a service link is inconsistent and incomplete.",
            "A non-blank opening requires at least one canonical ServiceOpeningLink.",
            "Only an active PASS Physical Model Lock permits opening-specific technical search.",
            (
                "An active lock is valid only when its content hash matches the current "
                "physical model."
            ),
            (
                "Later technical, commercial, validation, and release stages are outside "
                "this Layer 2 foundation."
            ),
        ],
    }
    return WorkflowAssessment(
        facts=facts,
        stage=current_stage(facts).value,
        diagnostics=diagnostics,
    )


__all__ = ["WorkflowAssessment", "assess_estimate_workflow"]
