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
from sqlalchemy.orm import Session

from ..models import Opening, Service
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import Defect, PhysicalModelAdmission, ServiceOpeningLink
from .canonical_submission_state import (
    CanonicalSubmissionStateError,
    require_initial_submission_state,
)


class ControlledPhysicalSubmissionError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Controlled physical submission failed: {code}.")


def submit_recorded_initial_physical_model(
    db: Session, *, admission_id: str, now: datetime | None = None
) -> dict[str, int | str]:
    """Consume one registered admission and insert only its sealed payload."""
    admission = db.scalar(
        select(PhysicalModelAdmission).where(PhysicalModelAdmission.admission_id == admission_id)
    )
    if admission is None:
        raise ControlledPhysicalSubmissionError("ADMISSION_NOT_FOUND")
    if admission.state != "issued":
        raise ControlledPhysicalSubmissionError("ADMISSION_NOT_AVAILABLE")
    current_time = now or datetime.now(UTC)
    if admission.expires_at <= current_time:
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

    defects = {
        item.id: item
        for item in db.scalars(
            select(Defect).where(Defect.estimate_id == admission.estimate_id)
        ).all()
    }
    openings: dict[str, Opening] = {}
    for item in payload.openings:
        if item.canonical_defect_id not in defects:
            raise ControlledPhysicalSubmissionError("ADMISSION_DEFECT_BINDING_INVALID")
        opening = Opening(
            estimate_id=admission.estimate_id,
            opening_code=item.opening_code,
            canonical_defect_id=item.canonical_defect_id,
            location=item.location,
            substrate_type=item.substrate_type,
            substrate_plane=item.substrate_plane,
            substrate_thickness_mm=item.substrate_thickness_mm,
            orientation=item.orientation,
            opening_type=item.opening_type,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            diameter_mm=item.diameter_mm,
            frl=item.frl,
            notes=item.notes,
        )
        db.add(opening)
        openings[item.opening_code] = opening
    db.flush()
    services: dict[str, Service] = {}
    for item in payload.services:
        first_link = next(
            link for link in payload.service_opening_links if link.service_code == item.service_code
        )
        service = Service(
            opening_id=openings[first_link.opening_code].id,
            service_code=item.service_code,
            service_type=item.service_type,
            material=item.material,
            nominal_size_mm=item.nominal_size_mm,
            outside_diameter_mm=item.outside_diameter_mm,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            insulation_type=item.insulation_type,
            insulation_thickness_mm=item.insulation_thickness_mm,
            quantity=item.quantity,
            centre_x_mm=item.centre_x_mm,
            centre_y_mm=item.centre_y_mm,
            evidence_status=item.evidence_status,
            confidence=item.confidence,
            notes=item.notes,
        )
        db.add(service)
        services[item.service_code] = service
    db.flush()
    for item in payload.service_opening_links:
        db.add(
            ServiceOpeningLink(
                service_id=services[item.service_code].id,
                opening_id=openings[item.opening_code].id,
                link_type=item.link_type,
                relationship_status=item.relationship_status,
                evidence_status=item.evidence_status,
                confidence=item.confidence,
                source_reference=item.source_reference,
                notes=item.notes,
            )
        )
    admission.state = "consumed"
    admission.updated_at = current_time
    admission.record_version += 1
    db.flush()
    receipt: dict[str, int | str | bool] = {
        "admission_id": admission.admission_id,
        "opening_count": len(openings),
        "service_count": len(services),
        "service_opening_link_count": len(payload.service_opening_links),
        "state_fingerprint": admission.protected_state_fingerprint,
        "canonical_write_performed": True,
        "physical_model_lock_created": False,
    }
    receipt["receipt_sha256"] = (
        hashlib.sha256(json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        .hexdigest()
        .upper()
    )
    return receipt
