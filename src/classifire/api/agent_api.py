from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import __version__
from ..agent_security import require_agent_scope
from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import AgentServicePrincipal, AuditEvent, Estimate, Opening
from ..physical_models import (
    EvidenceSource,
    PhysicalModelAdmission,
    PhysicalModelLock,
    PhysicalModelSubmissionReceipt,
    ServiceOpeningLink,
)
from ..services.adjudicated_physical_submission import (
    ControlledPhysicalSubmissionError,
    submit_recorded_initial_physical_model,
)
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1/agent", tags=["CLASSIFIRE Agent Read API"])
Db = Annotated[Session, Depends(get_db)]


class InitialPhysicalModelSubmissionRequest(BaseModel):
    admission_id: str = Field(min_length=36, max_length=100)
    idempotency_key: str = Field(min_length=16, max_length=200)


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _estimate_or_404(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


@router.get("/health")
def agent_health(
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("health:read"))],
) -> dict[str, Any]:
    scopes = set(principal.scopes or [])
    return {
        "status": "ok",
        "product": "CLASSIFIRE",
        "version": __version__,
        "agent_id": principal.agent_id,
        "scopes": sorted(principal.scopes or []),
        "physical_mutation_exposed": "physical:adjudicated:submit" in scopes,
        "adjudicated_submission_exposed": "physical:adjudicated:submit" in scopes,
        "physical_lock_exposed": False,
    }


@router.get("/estimates/{estimate_id}/workflow")
def agent_workflow_status(
    estimate_id: str,
    db: Db,
    _principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("workflow:read"))],
) -> dict[str, Any]:
    estimate = _estimate_or_404(db, estimate_id)
    return {
        "estimate_id": estimate.id,
        "estimate_reference": estimate.reference,
        "estimate_status": estimate.status,
        **assess_estimate_workflow(db, estimate).as_dict(),
    }


@router.get("/estimates/{estimate_id}/evidence")
def agent_evidence(
    estimate_id: str,
    db: Db,
    _principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("evidence:read"))],
) -> dict[str, Any]:
    estimate = _estimate_or_404(db, estimate_id)
    evidence = list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.estimate_id == estimate.id)
            .order_by(EvidenceSource.created_at, EvidenceSource.id)
        ).all()
    )
    return {
        "estimate_id": estimate.id,
        "evidence": [
            {
                "id": item.id,
                "defect_id": item.defect_id,
                "evidence_type": item.evidence_type,
                "source_reference": item.source_reference,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "sha256": item.sha256,
                "evidence_class": item.evidence_class,
                "confidence": _decimal(item.confidence),
                "status": item.status,
            }
            for item in evidence
        ],
    }


@router.get("/estimates/{estimate_id}/physical-model")
def agent_physical_model(
    estimate_id: str,
    db: Db,
    _principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("physical:read"))],
) -> dict[str, Any]:
    estimate = db.scalar(
        select(Estimate)
        .where(Estimate.id == estimate_id)
        .options(selectinload(Estimate.openings).selectinload(Opening.services))
    )
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    links = list(
        db.scalars(
            select(ServiceOpeningLink)
            .join_from(ServiceOpeningLink, Opening)
            .where(Opening.estimate_id == estimate.id)
            .order_by(ServiceOpeningLink.created_at, ServiceOpeningLink.id)
        ).all()
    )
    locks = list(
        db.scalars(
            select(PhysicalModelLock)
            .where(PhysicalModelLock.estimate_id == estimate.id)
            .order_by(PhysicalModelLock.created_at.desc())
        ).all()
    )
    return {
        "estimate_id": estimate.id,
        "openings": [
            {
                "id": opening.id,
                "opening_code": opening.opening_code,
                "canonical_defect_id": opening.canonical_defect_id,
                "opening_type": opening.opening_type,
                "location": opening.location,
                "substrate_type": opening.substrate_type,
                "substrate_plane": opening.substrate_plane,
                "frl": opening.frl,
                "services": [
                    {
                        "id": service.id,
                        "service_code": service.service_code,
                        "service_type": service.service_type,
                        "material": service.material,
                        "quantity": _decimal(service.quantity),
                    }
                    for service in opening.services
                ],
            }
            for opening in estimate.openings
        ],
        "service_opening_links": [
            {
                "service_id": link.service_id,
                "opening_id": link.opening_id,
                "link_type": link.link_type,
                "relationship_status": link.relationship_status,
                "evidence_status": link.evidence_status,
            }
            for link in links
        ],
        "physical_model_locks": [
            {
                "id": lock.id,
                "validator_result": lock.validator_result,
                "content_hash": lock.content_hash,
                "invalidated_at": lock.invalidated_at.isoformat() if lock.invalidated_at else None,
                "critical_unknowns": lock.critical_unknowns or [],
            }
            for lock in locks
        ],
    }


@router.post("/physical-model/initial")
def agent_submit_initial_physical_model(
    payload: InitialPhysicalModelSubmissionRequest,
    request: Request,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal,
        Depends(require_agent_scope("physical:adjudicated:submit")),
    ],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Consume one sealed admission without accepting physical-model content."""
    if not isinstance(settings, Settings):
        settings = get_settings()
    if not settings.adjudicated_initial_submission_enabled:
        raise HTTPException(status_code=503, detail={"code": "ADJUDICATED_SUBMISSION_DISABLED"})
    idempotency_key_sha256 = hashlib.sha256(payload.idempotency_key.encode("utf-8")).hexdigest()
    admission = db.scalar(
        select(PhysicalModelAdmission).where(
            PhysicalModelAdmission.admission_id == payload.admission_id
        )
    )
    if admission is None:
        raise HTTPException(status_code=404, detail={"code": "ADMISSION_NOT_FOUND"})

    if admission.state == "consumed":
        receipt = db.scalar(
            select(PhysicalModelSubmissionReceipt).where(
                PhysicalModelSubmissionReceipt.admission_record_id == admission.id
            )
        )
        if receipt is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "ADMISSION_CONSUMED_RECEIPT_MISSING"},
            )
        submission_audit = db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "submit_adjudicated_initial_physical_model",
                AuditEvent.entity_type == "physical_model_submission_receipt",
                AuditEvent.entity_id == receipt.id,
            )
        )
        if submission_audit is None or not hmac.compare_digest(
            submission_audit.correlation_id or "",
            idempotency_key_sha256,
        ):
            raise HTTPException(
                status_code=409,
                detail={"code": "ADMISSION_IDEMPOTENCY_KEY_MISMATCH"},
            )
        return {
            **json.loads(receipt.receipt_json),
            "receipt_sha256": receipt.receipt_sha256,
            "idempotent_replay": True,
        }

    try:
        result = submit_recorded_initial_physical_model(
            db,
            admission_id=payload.admission_id,
        )
    except ControlledPhysicalSubmissionError as exc:
        db.rollback()
        response_status = 500 if exc.code == "ADMISSION_WRITE_FAILED" else 409
        raise HTTPException(status_code=response_status, detail={"code": exc.code}) from exc

    receipt = db.scalar(
        select(PhysicalModelSubmissionReceipt).where(
            PhysicalModelSubmissionReceipt.admission_record_id == admission.id
        )
    )
    if receipt is None:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": "ADMISSION_RECEIPT_NOT_PERSISTED"},
        )

    record_audit(
        db,
        actor=None,
        actor_type="agent_service_principal",
        actor_name=principal.agent_id,
        action="submit_adjudicated_initial_physical_model",
        entity_type="physical_model_submission_receipt",
        entity_id=receipt.id,
        project_id=admission.project_id,
        new_value={
            "admission_id": admission.admission_id,
            "receipt_sha256": receipt.receipt_sha256,
            "canonical_write_performed": True,
            "physical_model_lock_created": False,
        },
        reason="Consumed one pre-registered signed admission through the dedicated writer.",
        source_ip=request.client.host if request.client else None,
        correlation_id=idempotency_key_sha256,
    )
    db.commit()
    return {**result, "idempotent_replay": False}
