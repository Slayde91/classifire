"""No-write, transaction-ready preflight for a signed Physical Model Lock amendment.

This is not an amendment writer. It locks and rechecks the exact active signed
lock, its approved amendment manifest, lifecycle state, downstream dependencies,
and prospective Defect bindings. It deliberately does not invalidate a lock,
persist an admission/receipt, edit canonical physical records, or create a
replacement lock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, Opening, Service
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from .physical_model_reopen import pretechnical_physical_amendment_dependency_code
from .signed_physical_model_lock_amendment import (
    SignedPhysicalModelLockAmendmentError,
    VerifiedSignedPhysicalModelLockAmendment,
    require_signed_physical_model_lock_amendment,
)

SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA = (
    "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-LOCK-AMENDMENT-PREFLIGHT-v1"
)
_EDITABLE_ESTIMATE_STATUSES = frozenset({"draft", "in_review"})


class SignedPhysicalModelLockAmendmentPreflightError(RuntimeError):
    """Safe-code failure before a future signed amendment transaction."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed Physical Model Lock amendment preflight failed: {code}.")


@dataclass(frozen=True, slots=True)
class SignedPhysicalModelLockAmendmentPreflightReceipt:
    """Facts a future writer must keep inside its one surrounding transaction."""

    amendment_admission_id: str
    project_id: str
    estimate_id: str
    target_lock_id: str
    target_lock_content_hash: str
    amendment_submission_payload_sha256: str
    visual_validation_receipt_sha256: str
    canonical_manifest_sha256: str
    current_opening_count: int
    proposed_opening_count: int
    proposed_service_count: int
    proposed_service_opening_link_count: int
    preflighted_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA,
            "amendment_admission_id": self.amendment_admission_id,
            "project_id": self.project_id,
            "estimate_id": self.estimate_id,
            "target_lock_id": self.target_lock_id,
            "target_lock_content_hash": self.target_lock_content_hash,
            "amendment_submission_payload_sha256": self.amendment_submission_payload_sha256,
            "visual_validation_receipt_sha256": self.visual_validation_receipt_sha256,
            "canonical_manifest_sha256": self.canonical_manifest_sha256,
            "current_opening_count": self.current_opening_count,
            "proposed_opening_count": self.proposed_opening_count,
            "proposed_service_count": self.proposed_service_count,
            "proposed_service_opening_link_count": self.proposed_service_opening_link_count,
            "preflighted_at": self.preflighted_at,
        }


def preflight_signed_physical_model_lock_amendment(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    amendment_submission_payload: object,
    now: datetime | None = None,
) -> SignedPhysicalModelLockAmendmentPreflightReceipt:
    """Recheck a signed amendment immediately before a future write.

    The caller owns the outer database transaction. ``FOR UPDATE`` locks the
    target Estimate and active lock while all checks run. A future writer must
    call this service and perform every canonical mutation plus replacement-lock
    creation before committing that same outer transaction.
    """

    current_time = _normalise_now(now)
    payload = _payload(amendment_submission_payload)
    verified = _require_verified(
        db,
        manifest=manifest,
        pinned_public_key=pinned_public_key,
        expected_issuer=expected_issuer,
        expected_key_id=expected_key_id,
        amendment_submission_payload=payload.model_dump(mode="json"),
        now=current_time,
    )
    estimate = db.scalar(
        select(Estimate).where(Estimate.id == verified.estimate_id).with_for_update()
    )
    if estimate is None or estimate.project_id != verified.project_id:
        raise SignedPhysicalModelLockAmendmentPreflightError(
            "AMENDMENT_ESTIMATE_BINDING_INVALID"
        )
    if (estimate.status or "").strip().lower() not in _EDITABLE_ESTIMATE_STATUSES:
        raise SignedPhysicalModelLockAmendmentPreflightError("AMENDMENT_ESTIMATE_STATUS_INVALID")

    openings = lock_current_physical_model_rows(db, estimate)

    active_locks = list(
        db.scalars(
            select(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .order_by(PhysicalModelLock.created_at, PhysicalModelLock.id)
            .with_for_update()
        ).all()
    )
    if len(active_locks) != 1 or active_locks[0].id != verified.target_lock_id:
        raise SignedPhysicalModelLockAmendmentPreflightError("AMENDMENT_ACTIVE_LOCK_STATE_INVALID")

    # Re-run every signature, current-hash, and visual-receipt check only after
    # the Estimate, physical rows, and target lock have been locked.
    verified = _require_verified(
        db,
        manifest=manifest,
        pinned_public_key=pinned_public_key,
        expected_issuer=expected_issuer,
        expected_key_id=expected_key_id,
        amendment_submission_payload=payload.model_dump(mode="json"),
        now=current_time,
    )
    dependency = pretechnical_physical_amendment_dependency_code(db, estimate, openings)
    if dependency is not None:
        raise SignedPhysicalModelLockAmendmentPreflightError(
            {
                "technical": "AMENDMENT_TECHNICAL_DEPENDENCY_PRESENT",
                "commercial": "AMENDMENT_COMMERCIAL_DEPENDENCY_PRESENT",
                "rule": "AMENDMENT_RULE_DEPENDENCY_PRESENT",
                "snapshot_or_release": "AMENDMENT_SNAPSHOT_OR_RELEASE_PRESENT",
            }[dependency]
        )
    _require_prospective_defects(db, estimate, payload)

    return SignedPhysicalModelLockAmendmentPreflightReceipt(
        amendment_admission_id=verified.amendment_admission_id,
        project_id=verified.project_id,
        estimate_id=verified.estimate_id,
        target_lock_id=verified.target_lock_id,
        target_lock_content_hash=verified.target_lock_content_hash,
        amendment_submission_payload_sha256=verified.amendment_submission_payload_sha256,
        visual_validation_receipt_sha256=verified.visual_validation_receipt_sha256,
        canonical_manifest_sha256=verified.canonical_manifest_sha256,
        current_opening_count=len(openings),
        proposed_opening_count=len(payload.openings),
        proposed_service_count=len(payload.services),
        proposed_service_opening_link_count=len(payload.service_opening_links),
        preflighted_at=current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


def _payload(value: object) -> InitialCanonicalPhysicalSubmission:
    try:
        return InitialCanonicalPhysicalSubmission.model_validate(value)
    except ValidationError as exc:
        raise SignedPhysicalModelLockAmendmentPreflightError("AMENDMENT_PAYLOAD_INVALID") from exc


def _require_verified(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    amendment_submission_payload: object,
    now: datetime,
) -> VerifiedSignedPhysicalModelLockAmendment:
    try:
        return require_signed_physical_model_lock_amendment(
            db,
            manifest=manifest,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            amendment_submission_payload=amendment_submission_payload,
            now=now,
            lock_target=True,
        )
    except SignedPhysicalModelLockAmendmentError as exc:
        raise SignedPhysicalModelLockAmendmentPreflightError(exc.code) from exc


def _require_prospective_defects(
    db: Session,
    estimate: Estimate,
    payload: InitialCanonicalPhysicalSubmission,
) -> None:
    expected_ids = {item.canonical_defect_id for item in payload.openings}
    defects = list(
        db.scalars(
            select(Defect).where(Defect.id.in_(expected_ids)).order_by(Defect.id).with_for_update()
        ).all()
    )
    if {item.id for item in defects} != expected_ids or any(
        item.estimate_id != estimate.id for item in defects
    ):
        raise SignedPhysicalModelLockAmendmentPreflightError(
            "AMENDMENT_PROSPECTIVE_DEFECT_BINDING_INVALID"
        )


def lock_current_physical_model_rows(db: Session, estimate: Estimate) -> list[Opening]:
    """Lock every current row that contributes to the target lock hash."""

    openings = list(
        db.scalars(
            select(Opening)
            .where(Opening.estimate_id == estimate.id)
            .order_by(Opening.created_at, Opening.id)
            .with_for_update()
        ).all()
    )
    opening_ids = [item.id for item in openings]
    links = (
        list(
            db.scalars(
                select(ServiceOpeningLink)
                .where(ServiceOpeningLink.opening_id.in_(opening_ids))
                .order_by(ServiceOpeningLink.id)
                .with_for_update()
            ).all()
        )
        if opening_ids
        else []
    )
    service_ids = sorted({item.service_id for item in links})
    if service_ids:
        list(
            db.scalars(
                select(Service).where(Service.id.in_(service_ids)).with_for_update()
            ).all()
        )
    defect_ids = sorted(
        {item.canonical_defect_id for item in openings if item.canonical_defect_id}
    )
    if defect_ids:
        list(
            db.scalars(select(Defect).where(Defect.id.in_(defect_ids)).with_for_update()).all()
        )
    list(
        db.scalars(
            select(EvidenceSource)
            .where(
                EvidenceSource.estimate_id == estimate.id,
                EvidenceSource.status == "active",
            )
            .with_for_update()
        ).all()
    )
    return openings


def _normalise_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise SignedPhysicalModelLockAmendmentPreflightError("AMENDMENT_TIME_INVALID")
    return current.astimezone(UTC)


__all__ = [
    "SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA",
    "SignedPhysicalModelLockAmendmentPreflightError",
    "SignedPhysicalModelLockAmendmentPreflightReceipt",
    "lock_current_physical_model_rows",
    "preflight_signed_physical_model_lock_amendment",
]
