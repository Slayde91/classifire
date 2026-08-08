from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import EvidenceSource, PhysicalModelLock, RepairStrategyLock, ServiceOpeningLink
from ..models import Estimate, Opening, Service, StoredFile
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


class PhysicalModelLockError(RuntimeError):
    pass


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _active_locks(db: Session, estimate_id: str) -> list[PhysicalModelLock]:
    return list(
        db.scalars(
            select(PhysicalModelLock).where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ).all()
    )


def _evidence_digest_rows(db: Session, estimate_id: str) -> tuple[list[EvidenceSource], list[dict[str, Any]]]:
    evidence = list(
        db.scalars(select(EvidenceSource).where(EvidenceSource.estimate_id == estimate_id)).all()
    )
    digest_rows: list[dict[str, Any]] = []
    for item in evidence:
        digest = item.sha256
        if not digest and item.stored_file_id:
            stored = db.get(StoredFile, item.stored_file_id)
            digest = stored.sha256 if stored else None
        digest_rows.append(
            {
                "id": item.id,
                "type": item.evidence_type,
                "sha256": digest,
                "source_reference": item.source_reference,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "evidence_class": item.evidence_class,
            }
        )
    return evidence, sorted(digest_rows, key=lambda row: row["id"])


def build_physical_model_lock_payload(db: Session, estimate: Estimate) -> dict[str, Any]:
    """Build the deterministic v2.13 PhysicalModelLock content payload.

    The payload is derived only from retained canonical evidence and physical-model
    records. Commercial records are intentionally excluded.
    """
    require_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)

    openings = list(
        db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)).all()
    )
    opening_ids = sorted(item.id for item in openings)
    links = list(
        db.scalars(
            select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
        ).all()
    ) if opening_ids else []
    service_ids = sorted({item.service_id for item in links})
    services = list(db.scalars(select(Service).where(Service.id.in_(service_ids))).all()) if service_ids else []

    _, evidence_rows = _evidence_digest_rows(db, estimate.id)
    evidence_hashes = sorted({row["sha256"] for row in evidence_rows if row.get("sha256")})
    defect_ids = sorted({item.canonical_defect_id for item in openings if item.canonical_defect_id})

    critical_unknowns: list[str] = []
    missing_material = sorted(item.id for item in services if not item.material)
    if missing_material:
        critical_unknowns.append(
            "Service material unresolved for service IDs: " + ", ".join(missing_material)
        )

    physical_rows = [
        {
            "opening_id": item.id,
            "defect_id": item.canonical_defect_id,
            "substrate_type": item.substrate_type,
            "substrate_plane": item.substrate_plane,
            "substrate_thickness_mm": str(item.substrate_thickness_mm) if item.substrate_thickness_mm is not None else None,
            "orientation": item.orientation,
            "opening_type": item.opening_type,
            "width_mm": str(item.width_mm) if item.width_mm is not None else None,
            "height_mm": str(item.height_mm) if item.height_mm is not None else None,
            "diameter_mm": str(item.diameter_mm) if item.diameter_mm is not None else None,
            "frl": item.frl,
        }
        for item in sorted(openings, key=lambda x: x.id)
    ]
    link_rows = [
        {
            "link_id": item.id,
            "opening_id": item.opening_id,
            "service_id": item.service_id,
            "link_type": item.link_type,
            "relationship_status": item.relationship_status,
            "evidence_status": item.evidence_status,
        }
        for item in sorted(links, key=lambda x: x.id)
    ]

    hash_payload = {
        "schema": "QUANTIFIRE-PhysicalModelLock-v2.13",
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "defect_ids": defect_ids,
        "evidence": evidence_rows,
        "openings": physical_rows,
        "service_opening_links": link_rows,
        "service_ids": service_ids,
        "critical_unknowns": critical_unknowns,
    }
    content_hash = hashlib.sha256(_canonical(hash_payload).encode("utf-8")).hexdigest()

    return {
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "defect_ids": defect_ids,
        "evidence_hashes": evidence_hashes,
        "service_ids": service_ids,
        "opening_ids": opening_ids,
        "service_count_status": "PASS",
        "material_hypothesis_status": "PASS" if not missing_material else "UNRESOLVED",
        "critical_unknowns": critical_unknowns,
        "validator_result": "PASS" if not critical_unknowns else "PROVISIONAL",
        "permitted_classes": ["opening_specific_technical_search"],
        "content_hash": content_hash,
        "signature": None,
    }


def create_physical_model_lock(db: Session, estimate: Estimate) -> tuple[PhysicalModelLock, bool]:
    """Create or idempotently return the active PhysicalModelLock.

    If the physical model changed after a lock but downstream technical records already
    exist, fail closed rather than silently invalidating downstream decisions.
    """
    payload = build_physical_model_lock_payload(db, estimate)
    active = _active_locks(db, estimate.id)
    for item in active:
        if item.content_hash == payload["content_hash"]:
            return item, False

    opening_ids = payload["opening_ids"]
    downstream_lock_exists = False
    if opening_ids:
        downstream_lock_exists = bool(
            db.scalar(
                select(RepairStrategyLock.id).where(
                    RepairStrategyLock.opening_id.in_(opening_ids),
                    RepairStrategyLock.invalidated_at.is_(None),
                ).limit(1)
            )
        )
    if active and downstream_lock_exists:
        raise PhysicalModelLockError(
            "Physical model changed after downstream Repair Strategy Lock creation; "
            "controlled cascade invalidation is required before re-locking."
        )

    now = datetime.now(timezone.utc)
    for item in active:
        item.invalidated_at = now
        item.invalidation_reason = "Superseded by a new Physical Model Lock after physical-model change"

    lock = PhysicalModelLock(**payload)
    db.add(lock)
    db.flush()
    return lock, True


__all__ = [
    "PhysicalModelLockError",
    "build_physical_model_lock_payload",
    "create_physical_model_lock",
]
