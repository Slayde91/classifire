from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Estimate, Opening, Service, StoredFile
from ..physical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


class PhysicalModelLockError(RuntimeError):
    """Raised when a requested Physical Model Lock cannot be safely created."""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        default=str,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _text(value: object) -> str | None:
    return str(value) if value is not None else None


def _active_locks(db: Session, estimate_id: str) -> list[PhysicalModelLock]:
    return list(
        db.scalars(
            select(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .order_by(PhysicalModelLock.created_at, PhysicalModelLock.id)
        ).all()
    )


def _evidence_digest_rows(
    db: Session,
    estimate_id: str,
) -> tuple[list[EvidenceSource], list[dict[str, Any]]]:
    evidence = list(
        db.scalars(
            select(EvidenceSource)
            .where(
                EvidenceSource.estimate_id == estimate_id,
                EvidenceSource.status == "active",
            )
            .order_by(EvidenceSource.id)
        ).all()
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
                "defect_id": item.defect_id,
                "stored_file_id": item.stored_file_id,
                "evidence_type": item.evidence_type,
                "source_reference": item.source_reference,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "sha256": digest,
                "evidence_class": item.evidence_class,
                "confidence": _text(item.confidence),
                "source_json": item.source_json,
            }
        )
    return evidence, digest_rows


def _opening_rows(openings: list[Opening]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "opening_code": item.opening_code,
            "defect_id": item.defect_id,
            "canonical_defect_id": item.canonical_defect_id,
            "location": item.location,
            "substrate_type": item.substrate_type,
            "substrate_plane": item.substrate_plane,
            "substrate_thickness_mm": _text(item.substrate_thickness_mm),
            "orientation": item.orientation,
            "opening_type": item.opening_type,
            "width_mm": _text(item.width_mm),
            "height_mm": _text(item.height_mm),
            "diameter_mm": _text(item.diameter_mm),
            "frl": item.frl,
            "physical_model_status": item.physical_model_status,
            "notes": item.notes,
        }
        for item in sorted(openings, key=lambda item: item.id)
    ]


def _service_rows(services: list[Service]) -> list[dict[str, Any]]:
    """Return every physical service field that must change the lock hash."""
    return [
        {
            "id": item.id,
            "opening_id": item.opening_id,
            "primary_opening_legacy": item.primary_opening_legacy,
            "service_code": item.service_code,
            "service_type": item.service_type,
            "material": item.material,
            "nominal_size_mm": _text(item.nominal_size_mm),
            "outside_diameter_mm": _text(item.outside_diameter_mm),
            "width_mm": _text(item.width_mm),
            "height_mm": _text(item.height_mm),
            "insulation_type": item.insulation_type,
            "insulation_thickness_mm": _text(item.insulation_thickness_mm),
            "quantity": _text(item.quantity),
            "centre_x_mm": _text(item.centre_x_mm),
            "centre_y_mm": _text(item.centre_y_mm),
            "evidence_status": item.evidence_status,
            "confidence": _text(item.confidence),
            "notes": item.notes,
        }
        for item in sorted(services, key=lambda item: item.id)
    ]


def _service_link_rows(links: list[ServiceOpeningLink]) -> list[dict[str, Any]]:
    return [
        {
            "id": item.id,
            "opening_id": item.opening_id,
            "service_id": item.service_id,
            "link_type": item.link_type,
            "relationship_status": item.relationship_status,
            "evidence_status": item.evidence_status,
            "confidence": _text(item.confidence),
            "source_reference": item.source_reference,
            "notes": item.notes,
        }
        for item in sorted(links, key=lambda item: item.id)
    ]


def _defect_rows(defects: list[Defect]) -> list[dict[str, Any]]:
    """Return every canonical defect field that contributes to the physical model."""
    return [
        {
            "id": item.id,
            "estimate_id": item.estimate_id,
            "external_defect_id": item.external_defect_id,
            "defect_code": item.defect_code,
            "description": item.description,
            "location": item.location,
            "classification": item.classification,
            "evidence_status": item.evidence_status,
            "status": item.status,
            "source_json": item.source_json,
            "record_version": item.record_version,
        }
        for item in sorted(defects, key=lambda item: item.id)
    ]


def _critical_unknowns(
    openings: list[Opening],
    evidence_rows: list[dict[str, Any]],
    services: list[Service],
    legacy_services: list[Service],
    linked_service_opening_pairs: set[tuple[str, str]],
    opening_ids: set[str],
    defects: list[Defect],
    estimate_id: str,
) -> list[str]:
    unknowns: list[str] = []
    missing_evidence_digest_ids = sorted(
        str(item["id"]) for item in evidence_rows if not item.get("sha256")
    )
    if missing_evidence_digest_ids:
        unknowns.append(
            "Active EvidenceSource records lack a retained SHA-256: "
            + ", ".join(missing_evidence_digest_ids)
        )

    missing_canonical_defect_ids = sorted(
        item.id for item in openings if not item.canonical_defect_id
    )
    if missing_canonical_defect_ids:
        unknowns.append(
            "Openings are not bound to canonical Defect records: "
            + ", ".join(missing_canonical_defect_ids)
        )

    expected_defect_ids = {
        item.canonical_defect_id for item in openings if item.canonical_defect_id
    }
    actual_defect_ids = {item.id for item in defects}
    missing_defect_rows = sorted(expected_defect_ids - actual_defect_ids)
    if missing_defect_rows:
        unknowns.append(
            "Canonical Defect records are unavailable: " + ", ".join(missing_defect_rows)
        )
    cross_estimate_defect_ids = sorted(
        item.id for item in defects if item.estimate_id != estimate_id
    )
    if cross_estimate_defect_ids:
        unknowns.append(
            "Canonical Defect records belong to another estimate: "
            + ", ".join(cross_estimate_defect_ids)
        )

    missing_material_ids = sorted(
        item.id for item in services if not item.material or not item.material.strip()
    )
    if missing_material_ids:
        unknowns.append(
            "Service material unresolved for service IDs: " + ", ".join(missing_material_ids)
        )

    legacy_service_opening_pairs = {(item.id, item.opening_id) for item in legacy_services}
    missing_canonical_link_pairs = sorted(
        legacy_service_opening_pairs - linked_service_opening_pairs
    )
    if missing_canonical_link_pairs:
        unknowns.append(
            "Legacy service/opening pairs are not represented by canonical "
            "ServiceOpeningLinks: "
            + ", ".join(
                f"{service_id}->{opening_id}"
                for service_id, opening_id in missing_canonical_link_pairs
            )
        )

    cross_estimate_primary_ids = sorted(
        item.id for item in services if item.opening_id not in opening_ids
    )
    if cross_estimate_primary_ids:
        unknowns.append(
            "Canonical service links reference services whose primary opening is outside "
            "the estimate: " + ", ".join(cross_estimate_primary_ids)
        )
    return unknowns


def build_current_physical_model_lock_payload(
    db: Session,
    estimate: Estimate,
) -> dict[str, Any]:
    """Build the current deterministic payload without making a workflow decision.

    This deliberately unguarded helper is used to verify that an active lock still
    represents the retained physical state. Creation remains guarded by
    :func:`build_physical_model_lock_payload` below.
    """

    openings = list(
        db.scalars(
            select(Opening).where(Opening.estimate_id == estimate.id).order_by(Opening.id)
        ).all()
    )
    opening_ids = [item.id for item in openings]
    opening_id_set = set(opening_ids)
    links = (
        list(
            db.scalars(
                select(ServiceOpeningLink)
                .where(ServiceOpeningLink.opening_id.in_(opening_ids))
                .order_by(ServiceOpeningLink.id)
            ).all()
        )
        if opening_ids
        else []
    )
    service_ids = sorted({item.service_id for item in links})
    services = (
        list(
            db.scalars(
                select(Service).where(Service.id.in_(service_ids)).order_by(Service.id)
            ).all()
        )
        if service_ids
        else []
    )
    legacy_services = (
        list(
            db.scalars(
                select(Service)
                .join(Opening, Service.opening_id == Opening.id)
                .where(Opening.estimate_id == estimate.id)
                .order_by(Service.id)
            ).all()
        )
        if opening_ids
        else []
    )
    _, evidence_rows = _evidence_digest_rows(db, estimate.id)
    evidence_hashes = sorted({str(row["sha256"]) for row in evidence_rows if row.get("sha256")})
    defect_ids = sorted({item.canonical_defect_id for item in openings if item.canonical_defect_id})
    defects = (
        list(db.scalars(select(Defect).where(Defect.id.in_(defect_ids)).order_by(Defect.id)).all())
        if defect_ids
        else []
    )
    critical_unknowns = _critical_unknowns(
        openings,
        evidence_rows,
        services,
        legacy_services,
        {(item.service_id, item.opening_id) for item in links},
        opening_id_set,
        defects,
        estimate.id,
    )

    hash_payload = {
        "schema": "CLASSIFIRE-PhysicalModelLock-v1",
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "defect_ids": defect_ids,
        "defects": _defect_rows(defects),
        "evidence": evidence_rows,
        "openings": _opening_rows(openings),
        "services": _service_rows(services),
        "service_opening_links": _service_link_rows(links),
        "critical_unknowns": critical_unknowns,
    }
    content_hash = hashlib.sha256(_canonical(hash_payload).encode("utf-8")).hexdigest()

    return {
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "defect_ids": defect_ids,
        "evidence_hashes": evidence_hashes,
        "service_ids": service_ids,
        "opening_ids": sorted(opening_ids),
        "service_count_status": "PASS" if not critical_unknowns else "UNRESOLVED",
        "material_hypothesis_status": "PASS" if not critical_unknowns else "UNRESOLVED",
        "critical_unknowns": critical_unknowns,
        "validator_result": "PASS" if not critical_unknowns else "PROVISIONAL",
        "permitted_classes": ["opening_specific_technical_search"],
        "content_hash": content_hash,
        "signature": None,
    }


def build_physical_model_lock_payload(db: Session, estimate: Estimate) -> dict[str, Any]:
    """Build the deterministic, physical-only lock payload for one estimate."""
    require_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)
    return build_current_physical_model_lock_payload(db, estimate)


def create_physical_model_lock(
    db: Session,
    estimate: Estimate,
) -> tuple[PhysicalModelLock, bool]:
    """Create an immutable lock or return the same active lock idempotently.

    Layer 2 never invalidates, replaces, or re-locks a changed physical model. A
    future governed reopen workflow is required before that capability can exist.
    """
    payload = build_physical_model_lock_payload(db, estimate)
    active_locks = _active_locks(db, estimate.id)
    for lock in active_locks:
        if lock.content_hash == payload["content_hash"]:
            return lock, False

    if active_locks:
        raise PhysicalModelLockError(
            "The physical model differs from the active Physical Model Lock. Layer 2 "
            "fails closed; a future governed reopen workflow is required."
        )
    if payload["critical_unknowns"]:
        raise PhysicalModelLockError(
            "Physical Model Lock withheld because critical physical uncertainty remains: "
            + "; ".join(payload["critical_unknowns"])
        )

    existing = db.scalar(
        select(PhysicalModelLock).where(PhysicalModelLock.content_hash == payload["content_hash"])
    )
    if existing:
        raise PhysicalModelLockError(
            "This Physical Model Lock content hash is already retained outside the active "
            "estimate state; a governed reopen workflow is required."
        )

    lock = PhysicalModelLock(**payload)
    try:
        # The partial unique index on active estimate IDs is the durable one-lock
        # invariant. A savepoint lets a concurrent unique violation fail closed
        # without discarding a caller's unrelated transaction state.
        with db.begin_nested():
            db.add(lock)
            db.flush()
    except IntegrityError as exc:
        db.expire_all()
        reloaded_locks = _active_locks(db, estimate.id)
        for existing_lock in reloaded_locks:
            if existing_lock.content_hash == payload["content_hash"]:
                return existing_lock, False
        if reloaded_locks:
            raise PhysicalModelLockError(
                "An active Physical Model Lock was created concurrently. Layer 2 fails "
                "closed; a future governed reopen workflow is required."
            ) from exc
        raise PhysicalModelLockError(
            "The Physical Model Lock could not be created atomically. No lock was created."
        ) from exc
    return lock, True


__all__ = [
    "PhysicalModelLockError",
    "build_current_physical_model_lock_payload",
    "build_physical_model_lock_payload",
    "create_physical_model_lock",
]
