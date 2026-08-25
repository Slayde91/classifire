from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import Estimate, StoredFile, User
from ..physical_models import Defect, EvidenceSource
from ..security import require_permission
from ..services.physical_model import PhysicalModelLockError, create_physical_model_lock
from ..services.physical_mutation_guard import PhysicalMutationError, require_evidence_mutation
from ..services.workflow import WorkflowTransitionError

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Physical Model"])
Db = Annotated[Session, Depends(get_db)]
_ADMISSIBLE_EVIDENCE_FILE_PURPOSES = frozenset({"technical_evidence"})
_ADMISSIBLE_EVIDENCE_SCAN_STATUSES = frozenset({"clean", "not_configured"})
_SITE_OBSERVATION_EVIDENCE_TYPE = "site_observation"


class _StrictSiteEvidencePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SiteObservationFact(_StrictSiteEvidencePayload):
    """One field observation; it records uncertainty rather than filling gaps."""

    observation_id: str = Field(min_length=1, max_length=100)
    subject_kind: Literal["defect", "opening", "service", "substrate_plane", "interface"]
    subject_reference: str = Field(min_length=1, max_length=300)
    evidence_locator: str = Field(min_length=1, max_length=500)
    fact_type: Literal[
        "opening_dimensions",
        "opening_depth_or_boundary",
        "substrate",
        "service_identification",
        "service_material",
        "opposite_face_continuity",
    ]
    status: Literal["confirmed", "inferred", "provisional", "unresolved", "contradicted"]
    value: str | None = Field(default=None, max_length=1000)
    unit: str | None = Field(default=None, max_length=50)
    limitation: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_fact_status(self) -> SiteObservationFact:
        if self.status == "unresolved":
            if self.value is not None:
                raise ValueError("unresolved site observations must not provide a value")
            if not self.limitation:
                raise ValueError("unresolved site observations require a limitation")
        elif self.status == "contradicted":
            if not self.value:
                raise ValueError("contradicted site observations require a value")
            if not self.limitation:
                raise ValueError("contradicted site observations require a limitation")
        elif not self.value:
            raise ValueError("resolved site observations require a value")
        return self


class SiteObservationEvidencePayload(_StrictSiteEvidencePayload):
    """Provenance contract for bounded, defect-level governed site evidence."""

    schema_version: Literal["CLASSIFIRE_SITE_OBSERVATION_EVIDENCE_V1"]
    captured_at: datetime
    collected_by: str = Field(min_length=1, max_length=300)
    collection_method: Literal[
        "site_visit",
        "remote_supervised_inspection",
        "documentary_follow_up",
    ]
    governance_reference: str = Field(min_length=1, max_length=300)
    location_reference: str = Field(min_length=1, max_length=500)
    observations: list[SiteObservationFact] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_capture_and_observations(self) -> SiteObservationEvidencePayload:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("captured_at must include a timezone offset")
        observation_ids = [item.observation_id for item in self.observations]
        if len(observation_ids) != len(set(observation_ids)):
            raise ValueError("site observation IDs must be unique")
        return self


class EvidenceSourceInput(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=100)
    defect_id: str | None = None
    stored_file_id: str | None = None
    source_reference: str | None = None
    page_number: str | None = None
    region_reference: str | None = None
    evidence_class: str = Field(default="observed", max_length=50)
    confidence: Decimal | None = None
    source_json: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_site_observation_payload(self) -> EvidenceSourceInput:
        if _normalise_token(self.evidence_type) != _SITE_OBSERVATION_EVIDENCE_TYPE:
            return self
        if not self.defect_id:
            raise ValueError("site_observation evidence must bind to one defect")
        if _normalise_token(self.evidence_class) != "observed":
            raise ValueError("site_observation evidence_class must be observed")
        if self.source_json is None:
            raise ValueError("site_observation evidence requires source_json provenance")
        payload = SiteObservationEvidencePayload.model_validate(self.source_json)
        self.evidence_type = _SITE_OBSERVATION_EVIDENCE_TYPE
        self.evidence_class = "observed"
        self.source_json = payload.model_dump(mode="json", exclude_none=True)
        return self


class PhysicalModelLockRequest(BaseModel):
    reason: str = Field(default="Physical model reviewed and locked", min_length=1, max_length=2000)


def _estimate_or_404(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _normalise_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _site_observation_payload_sha256(value: dict[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _require_admissible_evidence_file(stored: StoredFile) -> None:
    """Accept only immutable, technical-evidence files with a safe scan state.

    StoredFile has no estimate ownership relation in this foundation layer, so the
    endpoint deliberately accepts only the narrow, immutable technical-evidence
    class. A later scoped report-evidence relation can tighten ownership further.
    """
    if _normalise_token(stored.purpose) not in _ADMISSIBLE_EVIDENCE_FILE_PURPOSES:
        raise HTTPException(
            status_code=409,
            detail="Stored evidence file is not an immutable technical-evidence file",
        )
    if not stored.immutable:
        raise HTTPException(
            status_code=409,
            detail="Stored evidence file must be immutable before it can support a physical model",
        )
    if _normalise_token(stored.malware_scan_status) not in _ADMISSIBLE_EVIDENCE_SCAN_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Stored evidence file does not have an admissible malware scan status",
        )


@router.post("/estimates/{estimate_id}/evidence-sources", status_code=status.HTTP_201_CREATED)
def register_evidence_source(
    estimate_id: str,
    payload: EvidenceSourceInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    """Register retained evidence before the physical model is locked."""
    estimate = _estimate_or_404(db, estimate_id)
    try:
        require_evidence_mutation(db, estimate)
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if payload.defect_id:
        defect = db.get(Defect, payload.defect_id)
        if not defect or defect.estimate_id != estimate.id:
            raise HTTPException(
                status_code=400, detail="Evidence defect must belong to this estimate"
            )

    if not payload.stored_file_id:
        raise HTTPException(
            status_code=422,
            detail="Evidence registration requires an immutable technical-evidence file",
        )

    sha256 = None
    stored = db.get(StoredFile, payload.stored_file_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Stored evidence file not found")
    _require_admissible_evidence_file(stored)
    sha256 = stored.sha256

    evidence = EvidenceSource(
        estimate_id=estimate.id,
        defect_id=payload.defect_id,
        stored_file_id=payload.stored_file_id,
        evidence_type=payload.evidence_type,
        source_reference=payload.source_reference,
        page_number=payload.page_number,
        region_reference=payload.region_reference,
        sha256=sha256,
        evidence_class=payload.evidence_class,
        confidence=payload.confidence,
        status="active",
        source_json=payload.source_json,
    )
    db.add(evidence)
    db.flush()
    audit_value: dict[str, Any] = {
        "estimate_id": estimate.id,
        "defect_id": evidence.defect_id,
        "evidence_type": evidence.evidence_type,
        "stored_file_id": evidence.stored_file_id,
        "sha256": evidence.sha256,
        "source_reference": evidence.source_reference,
        "page_number": evidence.page_number,
        "region_reference": evidence.region_reference,
        "evidence_class": evidence.evidence_class,
    }
    if (
        evidence.evidence_type == _SITE_OBSERVATION_EVIDENCE_TYPE
        and evidence.source_json is not None
    ):
        audit_value["source_json_sha256"] = _site_observation_payload_sha256(evidence.source_json)
    record_audit(
        db,
        actor=user,
        action="register_evidence_source",
        entity_type="evidence_source",
        entity_id=evidence.id,
        project_id=estimate.project_id,
        new_value=audit_value,
        reason="Evidence registered for the CLASSIFIRE physical-model foundation.",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "id": evidence.id,
        "estimate_id": estimate.id,
        "sha256": evidence.sha256,
        "status": evidence.status,
    }


@router.post("/estimates/{estimate_id}/physical-model/lock")
def lock_physical_model(
    estimate_id: str,
    payload: PhysicalModelLockRequest,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Create one deterministic physical lock or return an identical active one."""
    if not isinstance(settings, Settings):
        settings = get_settings()
    estimate = _estimate_or_404(db, estimate_id)
    if settings.adjudicated_initial_submission_enabled:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                "Generic Physical Model Lock creation is disabled while signed "
                "adjudicated canonicalisation is enabled. A separate signed "
                "lock-admission boundary is required."
            ),
        )
    try:
        lock, created = create_physical_model_lock(db, estimate)
    except (WorkflowTransitionError, PhysicalModelLockError) as exc:
        blockers = list(exc.blockers) if isinstance(exc, WorkflowTransitionError) else [str(exc)]
        raise HTTPException(
            status_code=409,
            detail={"action": "lock_physical_model", "allowed": False, "blockers": blockers},
        ) from exc

    if created:
        record_audit(
            db,
            actor=user,
            action="lock_physical_model",
            entity_type="physical_model_lock",
            entity_id=lock.id,
            project_id=estimate.project_id,
            new_value={
                "estimate_id": estimate.id,
                "content_hash": lock.content_hash,
                "validator_result": lock.validator_result,
                "opening_ids": lock.opening_ids,
                "service_ids": lock.service_ids,
                "critical_unknowns": lock.critical_unknowns or [],
            },
            reason=payload.reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    else:
        db.rollback()

    return {
        "lock_id": lock.id,
        "created": created,
        "content_hash": lock.content_hash,
        "validator_result": lock.validator_result,
        "critical_unknowns": lock.critical_unknowns or [],
        "permitted_classes": lock.permitted_classes or [],
    }
