"""Fail-closed state attestation for a future first canonical-model submission.

This module is deliberately independent of the writer.  A later writer must
call it in the same database transaction immediately before inserting any
opening, service, or link.  It does not write records itself.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, Opening, Service
from ..physical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink

INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION = "CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1"


class CanonicalSubmissionStateError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Canonical submission state check failed: {code}.")


@dataclass(frozen=True)
class InitialSubmissionState:
    estimate_id: str
    fingerprint: str
    counts: dict[str, int]
    snapshot: dict[str, Any]


def initial_submission_state(db: Session, *, estimate_id: str) -> InitialSubmissionState:
    """Return the exact physical/evidence state a preflight must bind.

    All values are deterministic JSON primitives.  Admissions are intentionally
    excluded: registering a valid admission must not itself invalidate the
    preflight it is meant to authorise.
    """
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise CanonicalSubmissionStateError("INITIAL_SUBMISSION_ESTIMATE_MISSING")
    defects = list(
        db.scalars(
            select(Defect).where(Defect.estimate_id == estimate.id).order_by(Defect.id)
        ).all()
    )
    evidence = list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.estimate_id == estimate.id)
            .order_by(EvidenceSource.created_at, EvidenceSource.id)
        ).all()
    )
    openings = list(
        db.scalars(
            select(Opening).where(Opening.estimate_id == estimate.id).order_by(Opening.id)
        ).all()
    )
    opening_ids = [item.id for item in openings]
    services = list(
        db.scalars(
            select(Service).where(Service.opening_id.in_(opening_ids)).order_by(Service.id)
        ).all()
        if opening_ids
        else []
    )
    service_ids = [item.id for item in services]
    links = list(
        db.scalars(
            select(ServiceOpeningLink)
            .where(
                ServiceOpeningLink.opening_id.in_(opening_ids)
                if opening_ids
                else ServiceOpeningLink.service_id.in_(service_ids)
            )
            .order_by(ServiceOpeningLink.id)
        ).all()
        if opening_ids or service_ids
        else []
    )
    locks = list(
        db.scalars(
            select(PhysicalModelLock)
            .where(PhysicalModelLock.estimate_id == estimate.id)
            .order_by(PhysicalModelLock.created_at, PhysicalModelLock.id)
        ).all()
    )
    snapshot = {
        "schema": INITIAL_SUBMISSION_STATE_FINGERPRINT_VERSION,
        "estimate": {
            "id": estimate.id,
            "project_id": estimate.project_id,
            "status": estimate.status,
            "revision": estimate.revision,
        },
        "defects": [
            {
                "id": item.id,
                "external_defect_id": item.external_defect_id,
                "description": item.description,
                "location": item.location,
                "classification": item.classification,
                "evidence_status": item.evidence_status,
                "status": item.status,
                "source_json": item.source_json,
            }
            for item in defects
        ],
        "evidence": [
            {
                "id": item.id,
                "defect_id": item.defect_id,
                "stored_file_id": item.stored_file_id,
                "evidence_type": item.evidence_type,
                "source_reference": item.source_reference,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "sha256": item.sha256,
                "evidence_class": item.evidence_class,
                "confidence": str(item.confidence) if item.confidence is not None else None,
                "status": item.status,
                "source_json": item.source_json,
            }
            for item in evidence
        ],
        "openings": [
            {"id": item.id, "canonical_defect_id": item.canonical_defect_id} for item in openings
        ],
        "services": [{"id": item.id, "opening_id": item.opening_id} for item in services],
        "service_opening_links": [
            {"id": item.id, "service_id": item.service_id, "opening_id": item.opening_id}
            for item in links
        ],
        "physical_model_locks": [
            {
                "id": item.id,
                "content_hash": item.content_hash,
                "validator_result": item.validator_result,
                "invalidated_at": item.invalidated_at.isoformat() if item.invalidated_at else None,
            }
            for item in locks
        ],
    }
    encoded = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    counts = {
        "defect_count": len(defects),
        "evidence_count": len(evidence),
        "opening_count": len(openings),
        "service_count": len(services),
        "service_opening_link_count": len(links),
        "active_physical_model_lock_count": sum(item.invalidated_at is None for item in locks),
    }
    return InitialSubmissionState(
        estimate_id=estimate.id,
        fingerprint=hashlib.sha256(encoded).hexdigest().upper(),
        counts=counts,
        snapshot=snapshot,
    )


def require_initial_submission_state(
    db: Session,
    *,
    estimate_id: str,
    expected_fingerprint: str,
) -> InitialSubmissionState:
    """Fail unless the live state equals the signed preflight and is empty/unlocked."""
    state = initial_submission_state(db, estimate_id=estimate_id)
    if state.fingerprint != expected_fingerprint:
        raise CanonicalSubmissionStateError("INITIAL_SUBMISSION_STATE_CHANGED")
    nonempty = (
        "opening_count",
        "service_count",
        "service_opening_link_count",
        "active_physical_model_lock_count",
    )
    if any(state.counts[name] for name in nonempty):
        raise CanonicalSubmissionStateError("INITIAL_SUBMISSION_STATE_NOT_EMPTY")
    return state
