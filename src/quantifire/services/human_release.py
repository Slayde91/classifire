from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..commercial_models import GateEvidence
from ..models import Approval, Estimate, User
from .validated_snapshot import SNAPSHOT_SCHEMA
from .validation import latest_passing_gate
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


class HumanReleaseError(RuntimeError):
    pass


@dataclass(frozen=True)
class HumanReleaseReceipt:
    approval: Approval
    validation_gate: GateEvidence
    created: bool
    snapshot_hash: str
    certificate_hash: str

    def as_dict(self) -> dict[str, str | bool]:
        return {
            "approval_id": self.approval.id,
            "validation_gate_id": self.validation_gate.id,
            "created": self.created,
            "snapshot_hash": self.snapshot_hash,
            "certificate_hash": self.certificate_hash,
            "status": "released",
        }


def release_estimate(
    db: Session,
    estimate: Estimate,
    *,
    approver: User,
    reason: str,
) -> HumanReleaseReceipt:
    """Record the authorised human release of the current validated/rendered snapshot."""
    reason = reason.strip()
    if not reason:
        raise HumanReleaseError("A human release reason/decision note is required.")

    require_estimate_action(db, estimate, WorkflowAction.HUMAN_RELEASE)
    gate = latest_passing_gate(db, estimate)

    snapshot = estimate.snapshot_json or {}
    snapshot_hash = str(estimate.snapshot_hash or "")
    if not snapshot_hash or snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise HumanReleaseError("Current estimate does not contain a valid v2.13 validated snapshot.")
    if snapshot.get("snapshot_hash") != snapshot_hash:
        raise HumanReleaseError("Stored snapshot hash does not match the current estimate snapshot hash.")
    certificate_hash = str(
        (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash") or ""
    )
    if not certificate_hash:
        raise HumanReleaseError("Validated snapshot is missing its EstimateCertificate hash.")

    existing = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "estimate",
            Approval.entity_id == estimate.id,
            Approval.approval_type == "human_release",
            Approval.status == "approved",
            Approval.snapshot_hash == snapshot_hash,
        )
        .order_by(Approval.decided_at.desc())
        .limit(1)
    )
    if existing is not None:
        return HumanReleaseReceipt(
            approval=existing,
            validation_gate=gate,
            created=False,
            snapshot_hash=snapshot_hash,
            certificate_hash=certificate_hash,
        )

    now = datetime.now(timezone.utc)
    approval = Approval(
        entity_type="estimate",
        entity_id=estimate.id,
        approval_type="human_release",
        status="approved",
        requested_by_id=approver.id,
        decided_by_id=approver.id,
        requested_at=now,
        decided_at=now,
        decision_reason=reason,
        snapshot_hash=snapshot_hash,
    )
    db.add(approval)
    estimate.status = "released"
    estimate.approved_at = now
    estimate.approved_by_id = approver.id
    db.flush()

    return HumanReleaseReceipt(
        approval=approval,
        validation_gate=gate,
        created=True,
        snapshot_hash=snapshot_hash,
        certificate_hash=certificate_hash,
    )


__all__ = [
    "HumanReleaseError",
    "HumanReleaseReceipt",
    "release_estimate",
]
