"""Controlled reopening of an unsigned, pre-technical Physical Model Lock.

The service intentionally invalidates a generic legacy lock without deleting or
rewriting its physical evidence, defect, Opening, Service, or
ServiceOpeningLink records.  A later edit therefore starts from retained facts,
while the invalidated lock and an audit event preserve the exact reopening
decision.  Signed lock-admission reopening is a separate future boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate, EstimateLine, Opening, RuleEvaluation, Service, User
from ..physical_models import PhysicalModelLock, ServiceOpeningLink
from .physical_model import build_current_physical_model_lock_payload

_EDITABLE_ESTIMATE_STATUSES = frozenset({"draft", "in_review"})
_UNASSESSED_TECHNICAL_STATUSES = frozenset({"", "not_assessed"})


class PhysicalModelReopenError(RuntimeError):
    """Safe-code failure for a governed pre-technical reopening request."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Physical model reopen failed: {code}.")


@dataclass(frozen=True, slots=True)
class PhysicalModelReopenReceipt:
    """Deterministic summary of one successful unlock-for-amendment decision."""

    estimate_id: str
    audit_event_id: str
    invalidated_lock_ids: tuple[str, ...]
    prior_content_hashes: tuple[str, ...]
    current_content_hash: str
    opening_count: int
    service_count: int
    service_opening_link_count: int
    reopened_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "estimate_id": self.estimate_id,
            "audit_event_id": self.audit_event_id,
            "invalidated_lock_ids": list(self.invalidated_lock_ids),
            "prior_content_hashes": list(self.prior_content_hashes),
            "current_content_hash": self.current_content_hash,
            "opening_count": self.opening_count,
            "service_count": self.service_count,
            "service_opening_link_count": self.service_opening_link_count,
            "reopened_at": self.reopened_at,
        }


def _normalise_reason(reason: object) -> str:
    if not isinstance(reason, str):
        raise PhysicalModelReopenError("REOPEN_REASON_INVALID")
    cleaned = reason.strip()
    if not cleaned or len(cleaned) > 2000:
        raise PhysicalModelReopenError("REOPEN_REASON_INVALID")
    return cleaned


def _normalise_now(now: datetime | None) -> datetime:
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise PhysicalModelReopenError("REOPEN_TIME_INVALID")
    return current_time.astimezone(UTC)


def _require_actor(actor: User | None) -> User:
    if actor is None or not actor.id or not actor.is_active:
        raise PhysicalModelReopenError("REOPEN_ACTOR_INVALID")
    return actor


def _active_locks(db: Session, estimate_id: str) -> list[PhysicalModelLock]:
    return list(
        db.scalars(
            select(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .order_by(PhysicalModelLock.created_at, PhysicalModelLock.id)
        .with_for_update()
        ).all()
    )


def _physical_counts(db: Session, estimate_id: str, openings: list[Opening]) -> tuple[int, int]:
    opening_ids = [item.id for item in openings]
    if not opening_ids:
        return 0, 0
    service_count = int(
        db.scalar(
            select(func.count(Service.id))
            .join(Opening, Service.opening_id == Opening.id)
            .where(Opening.estimate_id == estimate_id)
        )
        or 0
    )
    link_count = int(
        db.scalar(
            select(func.count(ServiceOpeningLink.id)).where(
                ServiceOpeningLink.opening_id.in_(opening_ids)
            )
        )
        or 0
    )
    return service_count, link_count


def pretechnical_physical_amendment_dependency_code(
    db: Session, estimate: Estimate, openings: list[Opening]
) -> str | None:
    """Return the first downstream dependency that makes an amendment unsafe.

    Both the unsigned reopen path and a future signed-amendment writer must
    reject the same technical, commercial, validation, snapshot, and release
    dependencies. Returning a neutral token keeps their public safe-code
    vocabularies separate without letting the checks drift apart.
    """
    technical_opening_ids = [
        item.id
        for item in openings
        if item.selected_technical_variant_id
        or (item.technical_status or "").strip().lower() not in _UNASSESSED_TECHNICAL_STATUSES
    ]
    if technical_opening_ids:
        return "technical"
    if db.scalar(select(EstimateLine.id).where(EstimateLine.estimate_id == estimate.id).limit(1)):
        return "commercial"
    if db.scalar(
        select(RuleEvaluation.id).where(RuleEvaluation.estimate_id == estimate.id).limit(1)
    ):
        return "rule"
    if estimate.snapshot_hash or estimate.locked_at or estimate.approved_at:
        return "snapshot_or_release"
    return None


def _require_pretechnical_dependencies_absent(
    db: Session, estimate: Estimate, openings: list[Opening]
) -> None:
    dependency = pretechnical_physical_amendment_dependency_code(db, estimate, openings)
    if dependency is not None:
        raise PhysicalModelReopenError(
            {
                "technical": "REOPEN_TECHNICAL_DEPENDENCY_PRESENT",
                "commercial": "REOPEN_COMMERCIAL_DEPENDENCY_PRESENT",
                "rule": "REOPEN_RULE_DEPENDENCY_PRESENT",
                "snapshot_or_release": "REOPEN_SNAPSHOT_OR_RELEASE_PRESENT",
            }[dependency]
        )


def reopen_pretechnical_physical_model(
    db: Session,
    estimate: Estimate,
    *,
    actor: User | None,
    reason: str,
    now: datetime | None = None,
    source_ip: str | None = None,
) -> PhysicalModelReopenReceipt:
    """Invalidate only an unsigned pre-technical lock and preserve physical state.

    The caller owns the surrounding transaction.  A successful call does not
    delete physical rows and does not create a replacement lock; it merely opens
    the already-retained model for a controlled amendment before technical,
    commercial, validation, snapshot, or release records can depend on it.
    """

    actor = _require_actor(actor)
    cleaned_reason = _normalise_reason(reason)
    current_time = _normalise_now(now)
    status = (estimate.status or "").strip().lower()
    if status not in _EDITABLE_ESTIMATE_STATUSES:
        raise PhysicalModelReopenError("REOPEN_ESTIMATE_STATUS_INVALID")

    openings = list(
        db.scalars(
            select(Opening)
            .where(Opening.estimate_id == estimate.id)
            .order_by(Opening.created_at, Opening.id)
        ).all()
    )
    if not openings:
        raise PhysicalModelReopenError("REOPEN_PHYSICAL_MODEL_MISSING")
    active_locks = _active_locks(db, estimate.id)
    if not active_locks:
        raise PhysicalModelReopenError("REOPEN_ACTIVE_LOCK_REQUIRED")
    if any(lock.signature for lock in active_locks):
        raise PhysicalModelReopenError("REOPEN_SIGNED_LOCK_UNSUPPORTED")
    _require_pretechnical_dependencies_absent(db, estimate, openings)

    current_payload = build_current_physical_model_lock_payload(db, estimate)
    current_content_hash = str(current_payload["content_hash"])
    service_count, link_count = _physical_counts(db, estimate.id, openings)
    previous_value: dict[str, Any] = {
        "active_lock_ids": [lock.id for lock in active_locks],
        "active_lock_content_hashes": [lock.content_hash for lock in active_locks],
        "current_content_hash": current_content_hash,
        "opening_count": len(openings),
        "service_count": service_count,
        "service_opening_link_count": link_count,
    }

    try:
        with db.begin_nested():
            for lock in active_locks:
                lock.invalidated_at = current_time
                lock.invalidation_reason = cleaned_reason
                lock.record_version += 1
            audit = record_audit(
                db,
                actor=actor,
                action="reopen_pretechnical_physical_model",
                entity_type="physical_model_lock",
                entity_id=active_locks[0].id,
                project_id=estimate.project_id,
                previous_value=previous_value,
                new_value={
                    "active_lock_ids": [],
                    "physical_model_preserved": True,
                    "amendment_state": "unlocked_pretechnical",
                },
                reason=cleaned_reason,
                source_ip=source_ip,
            )
            db.flush()
    except SQLAlchemyError as exc:
        raise PhysicalModelReopenError("REOPEN_WRITE_FAILED") from exc

    return PhysicalModelReopenReceipt(
        estimate_id=estimate.id,
        audit_event_id=audit.id,
        invalidated_lock_ids=tuple(lock.id for lock in active_locks),
        prior_content_hashes=tuple(lock.content_hash for lock in active_locks),
        current_content_hash=current_content_hash,
        opening_count=len(openings),
        service_count=service_count,
        service_opening_link_count=link_count,
        reopened_at=current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


__all__ = [
    "PhysicalModelReopenError",
    "PhysicalModelReopenReceipt",
    "pretechnical_physical_amendment_dependency_code",
    "reopen_pretechnical_physical_model",
]
