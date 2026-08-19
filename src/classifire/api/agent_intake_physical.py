from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent_security import require_agent_scope
from ..audit import record_audit
from ..canonical_models import Defect, EvidenceSource, PhysicalModelLock
from ..config import Settings, get_settings
from ..db import get_db
from ..models import AgentServicePrincipal, Estimate, StoredFile
from ..physical_model_submission_schema import AgentAdjudicatedInitialPhysicalSubmissionRequest
from ..services.adjudicated_physical_submission import (
    ControlledPhysicalSubmissionError,
    execute_adjudicated_initial_submission,
)

router = APIRouter(prefix="/api/v1/agent", tags=["CLASSIFIRE Controlled Intake and Physical Model"])
Db = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


class AgentEvidenceObservation(BaseModel):
    stored_file_id: str = Field(min_length=1, max_length=36)
    evidence_type: str = Field(min_length=1, max_length=100)
    external_defect_id: str | None = Field(default=None, max_length=150)
    defect_code: str | None = Field(default=None, max_length=150)
    defect_description: str | None = None
    defect_location: str | None = None
    defect_classification: str | None = Field(default=None, max_length=100)
    source_reference: str | None = None
    page_number: str | None = Field(default=None, max_length=100)
    region_reference: str | None = Field(default=None, max_length=300)
    evidence_class: str = Field(default="observed", max_length=50)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source_json: dict[str, Any] | None = None


class AgentEvidenceBatchInput(BaseModel):
    observations: list[AgentEvidenceObservation] = Field(min_length=1, max_length=5000)


class AgentPhysicalModelLockInput(BaseModel):
    reason: str = Field(
        default="Controlled cf-physical-model lock request",
        min_length=3,
        max_length=2000,
    )


def _estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(status_code=409, detail="Estimate is no longer editable")
    return estimate


def _active_physical_lock_exists(db: Session, estimate_id: str) -> bool:
    return bool(
        db.scalar(
            select(PhysicalModelLock.id)
            .where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .limit(1)
        )
    )


def _require_unlocked(db: Session, estimate: Estimate) -> None:
    if _active_physical_lock_exists(db, estimate.id):
        raise HTTPException(
            status_code=409,
            detail=(
                "Physical Model Lock already exists; controlled invalidation is required "
                "before upstream changes."
            ),
        )


def _defect_for_external_id(
    db: Session,
    estimate: Estimate,
    external_defect_id: str | None,
    *,
    defect_code: str | None = None,
    description: str | None = None,
    location: str | None = None,
    classification: str | None = None,
) -> Defect | None:
    if not external_defect_id:
        return None
    defect = db.scalar(
        select(Defect).where(
            Defect.estimate_id == estimate.id,
            Defect.external_defect_id == external_defect_id,
        )
    )
    if defect is None:
        defect = Defect(
            estimate_id=estimate.id,
            external_defect_id=external_defect_id,
            defect_code=defect_code or external_defect_id,
            description=description,
            location=location,
            classification=classification,
            evidence_status="provisional",
            status="draft",
        )
        db.add(defect)
        db.flush()
        return defect

    comparisons = {
        "defect_code": defect_code,
        "description": description,
        "location": location,
        "classification": classification,
    }
    for field_name, proposed in comparisons.items():
        current = getattr(defect, field_name)
        if proposed is None:
            continue
        if current not in (None, "") and str(current).strip() != str(proposed).strip():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Conflicting evidence for defect {external_defect_id}: {field_name} already "
                    "contains a different retained value. Resolve the conflict before continuing."
                ),
            )
        if current in (None, ""):
            setattr(defect, field_name, proposed)
    return defect


def _agent_audit(
    db: Session,
    *,
    principal: AgentServicePrincipal,
    action: str,
    entity_type: str,
    entity_id: str,
    estimate: Estimate,
    new_value: dict[str, Any],
    reason: str,
) -> None:
    record_audit(
        db,
        actor=None,
        actor_type="agent",
        actor_name=principal.agent_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=estimate.project_id,
        new_value=new_value,
        reason=reason,
    )


@router.post("/estimates/{estimate_id}/evidence/register")
def agent_register_evidence(
    estimate_id: str,
    payload: AgentEvidenceBatchInput,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("evidence:write"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    _require_unlocked(db, estimate)
    registered: list[dict[str, Any]] = []

    for item in payload.observations:
        stored = db.get(StoredFile, item.stored_file_id)
        if stored is None:
            db.rollback()
            raise HTTPException(
                status_code=404,
                detail=f"Stored evidence file not found: {item.stored_file_id}",
            )
        defect = _defect_for_external_id(
            db,
            estimate,
            item.external_defect_id,
            defect_code=item.defect_code,
            description=item.defect_description,
            location=item.defect_location,
            classification=item.defect_classification,
        )
        defect_id = defect.id if defect else None
        existing = db.scalar(
            select(EvidenceSource).where(
                EvidenceSource.estimate_id == estimate.id,
                EvidenceSource.defect_id == defect_id,
                EvidenceSource.stored_file_id == stored.id,
                EvidenceSource.evidence_type == item.evidence_type,
                EvidenceSource.source_reference == item.source_reference,
                EvidenceSource.page_number == item.page_number,
                EvidenceSource.region_reference == item.region_reference,
            )
        )
        if existing is not None:
            registered.append({"id": existing.id, "created": False, "defect_id": defect_id})
            continue

        evidence = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect_id,
            stored_file_id=stored.id,
            evidence_type=item.evidence_type,
            source_reference=item.source_reference,
            page_number=item.page_number,
            region_reference=item.region_reference,
            sha256=stored.sha256,
            evidence_class=item.evidence_class,
            confidence=item.confidence,
            status="active",
            source_json=item.source_json,
        )
        db.add(evidence)
        db.flush()
        _agent_audit(
            db,
            principal=principal,
            action="agent_register_evidence",
            entity_type="evidence_source",
            entity_id=evidence.id,
            estimate=estimate,
            new_value={
                "stored_file_id": stored.id,
                "sha256": stored.sha256,
                "defect_id": defect_id,
                "evidence_type": item.evidence_type,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "evidence_class": item.evidence_class,
            },
            reason="Role-limited cf-intake-evidence source-preserving evidence registration",
        )
        registered.append({"id": evidence.id, "created": True, "defect_id": defect_id})

    db.commit()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "registered": registered,
        "count": len(registered),
    }


@router.post("/estimates/{estimate_id}/physical-model/initial")
def agent_submit_initial_physical_model(
    estimate_id: str,
    payload: AgentAdjudicatedInitialPhysicalSubmissionRequest,
    db: Db,
    settings: SettingsDep,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("physical:adjudicated:submit"))
    ],
) -> dict[str, Any]:
    if not settings.adjudicated_initial_submission_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signed adjudicated initial submission is disabled.",
        )
    if (
        not settings.adjudicated_admission_public_keys
        or not settings.adjudicated_admission_issuer_key_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Signed adjudicated initial submission is not securely configured.",
        )

    # Authentication reads through this session. Release that read transaction
    # before the service obtains SQLite's BEGIN IMMEDIATE / PostgreSQL serializable
    # transaction. Capture scalars first so no lazy ORM access reopens it.
    principal_id = principal.id
    principal_agent_id = principal.agent_id
    db.rollback()
    try:
        result = execute_adjudicated_initial_submission(
            db,
            estimate_id=estimate_id,
            admission_id=payload.admission_id,
            idempotency_key=payload.idempotency_key,
            principal_id=principal_id,
            principal_agent_id=principal_agent_id,
            pinned_public_keys=settings.adjudicated_admission_public_keys,
            issuer_key_ids=settings.adjudicated_admission_issuer_key_ids,
            max_admission_ttl_seconds=settings.adjudicated_admission_max_ttl_seconds,
        )
    except ControlledPhysicalSubmissionError as exc:
        if exc.code in {"ADMISSION_NOT_FOUND", "ESTIMATE_NOT_FOUND"}:
            status_code = status.HTTP_404_NOT_FOUND
        elif exc.code in {
            "PREFLIGHT_RECEIPT_INVALID",
            "PREFLIGHT_PAYLOAD_INVALID",
            "ADMISSION_MANIFEST_INVALID",
            "ADMISSION_PAYLOAD_INVALID",
            "IDEMPOTENCY_KEY_INVALID",
        }:
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        elif exc.code in {
            "ADMISSION_KEY_UNTRUSTED",
            "ADMISSION_ISSUER_UNTRUSTED",
            "ADMISSION_SIGNER_UNTRUSTED",
            "ADMISSION_VERIFIER_UNAVAILABLE",
            "ADMISSION_PINNED_KEY_INVALID",
        }:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            status_code = status.HTTP_409_CONFLICT
        raise HTTPException(status_code=status_code, detail={"code": exc.code}) from exc
    return {
        "agent_id": principal_agent_id,
        "estimate_id": result.estimate_id,
        "admission_id": result.admission_id,
        "submission_id": result.submission_id,
        "replayed": result.replayed,
        "receipt": result.receipt,
    }


@router.post("/estimates/{estimate_id}/physical-model/lock")
def agent_lock_physical_model(
    estimate_id: str,
    payload: AgentPhysicalModelLockInput,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("physical:lock"))],
) -> dict[str, Any]:
    del estimate_id, payload, db, principal
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "Generic agent Physical Model Lock requests are disabled. "
            "A separate signed lock-admission boundary is required."
        ),
    )
