"""One-time local service for consuming a recorded admission.

No HTTP route imports this module in this checkpoint.  Callers must provide a
database transaction; the service verifies the recorded payload and current
state before inserting the model, then consumes the admission.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import Opening, Service
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import (
    Defect,
    PhysicalModelAdmission,
    PhysicalModelSubmissionReceipt,
    ServiceOpeningLink,
)
from .adjudicated_admission import normalised_submission_payload_sha256
from .canonical_submission_state import (
    CanonicalSubmissionStateError,
    require_initial_submission_state,
)

CONTROLLED_CANONICAL_WRITER_POLICY_VERSION = "CLASSIFIRE-ADJUDICATED-CANONICAL-WRITER-v1"


class ControlledPhysicalSubmissionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Controlled physical submission failed: {code}.")


def submit_recorded_initial_physical_model(
    db: Session, *, admission_id: str, now: datetime | None = None
) -> dict[str, int | str | bool]:
    """Consume one registered admission and insert only its sealed payload."""
    admission = db.scalar(
        select(PhysicalModelAdmission).where(PhysicalModelAdmission.admission_id == admission_id)
    )
    if admission is None:
        raise ControlledPhysicalSubmissionError("ADMISSION_NOT_FOUND")
    if admission.state != "issued":
        raise ControlledPhysicalSubmissionError("ADMISSION_NOT_AVAILABLE")
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        raise ControlledPhysicalSubmissionError("ADMISSION_TIME_INVALID")
    current_time = current_time.astimezone(UTC)
    expires_at = admission.expires_at
    if expires_at.tzinfo is None:
        # SQLite does not round-trip timezone metadata. Registration accepts
        # only verified UTC timestamps, so a persisted naive value is UTC.
        expires_at = expires_at.replace(tzinfo=UTC)
    else:
        expires_at = expires_at.astimezone(UTC)
    if expires_at <= current_time:
        raise ControlledPhysicalSubmissionError("ADMISSION_EXPIRED")
    try:
        require_initial_submission_state(
            db,
            estimate_id=admission.estimate_id,
            expected_fingerprint=admission.protected_state_fingerprint,
        )
        payload = InitialCanonicalPhysicalSubmission.model_validate_json(
            admission.normalised_submission_payload_json
        )
    except CanonicalSubmissionStateError as exc:
        raise ControlledPhysicalSubmissionError(exc.code) from exc
    except ValueError as exc:
        raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_INVALID") from exc

    payload_sha256 = normalised_submission_payload_sha256(payload.model_dump(mode="json"))
    if payload_sha256 != admission.normalised_submission_payload_sha256:
        raise ControlledPhysicalSubmissionError("ADMISSION_PAYLOAD_HASH_MISMATCH")

    defects = {
        defect.id: defect
        for defect in db.scalars(
            select(Defect).where(Defect.estimate_id == admission.estimate_id)
        ).all()
    }
    if any(opening_item.canonical_defect_id not in defects for opening_item in payload.openings):
        raise ControlledPhysicalSubmissionError("ADMISSION_DEFECT_BINDING_INVALID")

    receipt_payload: dict[str, int | str | bool] = {
        "schema": "CLASSIFIRE-INITIAL-PHYSICAL-SUBMISSION-RECEIPT-v1",
        "admission_id": admission.admission_id,
        "project_id": admission.project_id,
        "estimate_id": admission.estimate_id,
        "normalised_submission_payload_sha256": payload_sha256,
        "protected_state_fingerprint_before": admission.protected_state_fingerprint,
        "opening_count": len(payload.openings),
        "service_count": len(payload.services),
        "service_opening_link_count": len(payload.service_opening_links),
        "state_fingerprint": admission.protected_state_fingerprint,
        "canonical_write_performed": True,
        "physical_model_lock_created": False,
        "submitted_at": current_time.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    receipt_json = json.dumps(
        receipt_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    receipt_sha256 = hashlib.sha256(receipt_json.encode("utf-8")).hexdigest().upper()

    try:
        with db.begin_nested():
            openings: dict[str, Opening] = {}
            for opening_item in payload.openings:
                opening = Opening(
                    estimate_id=admission.estimate_id,
                    opening_code=opening_item.opening_code,
                    canonical_defect_id=opening_item.canonical_defect_id,
                    location=opening_item.location,
                    substrate_type=opening_item.substrate_type,
                    substrate_plane=opening_item.substrate_plane,
                    substrate_thickness_mm=opening_item.substrate_thickness_mm,
                    orientation=opening_item.orientation,
                    opening_type=opening_item.opening_type,
                    width_mm=opening_item.width_mm,
                    height_mm=opening_item.height_mm,
                    diameter_mm=opening_item.diameter_mm,
                    frl=opening_item.frl,
                    notes=opening_item.notes,
                )
                db.add(opening)
                openings[opening_item.opening_code] = opening
            db.flush()
            services: dict[str, Service] = {}
            for service_item in payload.services:
                first_link = next(
                    link
                    for link in payload.service_opening_links
                    if link.service_code == service_item.service_code
                )
                service = Service(
                    opening_id=openings[first_link.opening_code].id,
                    service_code=service_item.service_code,
                    service_type=service_item.service_type,
                    material=service_item.material,
                    nominal_size_mm=service_item.nominal_size_mm,
                    outside_diameter_mm=service_item.outside_diameter_mm,
                    width_mm=service_item.width_mm,
                    height_mm=service_item.height_mm,
                    insulation_type=service_item.insulation_type,
                    insulation_thickness_mm=service_item.insulation_thickness_mm,
                    quantity=service_item.quantity,
                    centre_x_mm=service_item.centre_x_mm,
                    centre_y_mm=service_item.centre_y_mm,
                    evidence_status=service_item.evidence_status,
                    confidence=service_item.confidence,
                    notes=service_item.notes,
                )
                db.add(service)
                services[service_item.service_code] = service
            db.flush()
            for link_item in payload.service_opening_links:
                db.add(
                    ServiceOpeningLink(
                        service_id=services[link_item.service_code].id,
                        opening_id=openings[link_item.opening_code].id,
                        link_type=link_item.link_type,
                        relationship_status=link_item.relationship_status,
                        evidence_status=link_item.evidence_status,
                        confidence=link_item.confidence,
                        source_reference=link_item.source_reference,
                        notes=link_item.notes,
                    )
                )
            db.add(
                PhysicalModelSubmissionReceipt(
                    admission_record_id=admission.id,
                    admission_id=admission.admission_id,
                    project_id=admission.project_id,
                    estimate_id=admission.estimate_id,
                    normalised_submission_payload_sha256=payload_sha256,
                    protected_state_fingerprint_before=admission.protected_state_fingerprint,
                    opening_count=len(payload.openings),
                    service_count=len(payload.services),
                    service_opening_link_count=len(payload.service_opening_links),
                    canonical_write_performed=True,
                    physical_model_lock_created=False,
                    receipt_json=receipt_json,
                    receipt_sha256=receipt_sha256,
                )
            )
            admission.state = "consumed"
            admission.updated_at = current_time
            admission.record_version += 1
            db.flush()
    except SQLAlchemyError as exc:
        raise ControlledPhysicalSubmissionError("ADMISSION_WRITE_FAILED") from exc

    return {**receipt_payload, "receipt_sha256": receipt_sha256}
