from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..canonical_models import EvidenceSource, PhysicalModelLock
from ..db import get_db
from ..models import Estimate, StoredFile, User
from ..security import require_permission
from ..services.physical_model import PhysicalModelLockError, create_physical_model_lock
from ..services.workflow import WorkflowTransitionError

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Physical Model"])
Db = Annotated[Session, Depends(get_db)]


class EvidenceSourceInput(BaseModel):
    evidence_type: str = Field(min_length=1, max_length=100)
    stored_file_id: str | None = None
    source_reference: str | None = None
    page_number: str | None = None
    region_reference: str | None = None
    evidence_class: str = Field(default="observed", max_length=50)
    confidence: Decimal | None = None
    source_json: dict[str, Any] | None = None


class PhysicalModelLockRequest(BaseModel):
    reason: str = Field(default="Physical model reviewed and locked", min_length=1, max_length=2000)


def _estimate_or_404(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _active_physical_lock_exists(db: Session, estimate_id: str) -> bool:
    return bool(
        db.scalar(
            select(PhysicalModelLock.id).where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            ).limit(1)
        )
    )


@router.post(
    "/estimates/{estimate_id}/evidence-sources",
    status_code=status.HTTP_201_CREATED,
)
def register_evidence_source(
    estimate_id: str,
    payload: EvidenceSourceInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    estimate = _estimate_or_404(db, estimate_id)
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot accept new evidence")
    if _active_physical_lock_exists(db, estimate.id):
        raise HTTPException(
            status_code=409,
            detail=(
                "Physical Model Lock already exists. Evidence changes require a controlled "
                "lock invalidation/reopen workflow before new evidence can be added."
            ),
        )

    sha256 = None
    if payload.stored_file_id:
        stored = db.get(StoredFile, payload.stored_file_id)
        if not stored:
            raise HTTPException(status_code=404, detail="Stored evidence file not found")
        sha256 = stored.sha256

    evidence = EvidenceSource(
        estimate_id=estimate.id,
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
    record_audit(
        db,
        actor=user,
        action="register_evidence_source",
        entity_type="evidence_source",
        entity_id=evidence.id,
        project_id=estimate.project_id,
        new_value={
            "estimate_id": estimate.id,
            "evidence_type": evidence.evidence_type,
            "stored_file_id": evidence.stored_file_id,
            "sha256": evidence.sha256,
            "source_reference": evidence.source_reference,
            "page_number": evidence.page_number,
            "region_reference": evidence.region_reference,
            "evidence_class": evidence.evidence_class,
        },
        reason="Evidence registered for CLASSIFIRE physical-model workflow (QUANTIFIRE v2.13 lineage)",
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
) -> dict[str, Any]:
    estimate = _estimate_or_404(db, estimate_id)
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot change physical-model state")
    try:
        lock, created = create_physical_model_lock(db, estimate)
    except (WorkflowTransitionError, PhysicalModelLockError) as exc:
        blockers = list(exc.blockers) if isinstance(exc, WorkflowTransitionError) else [str(exc)]
        raise HTTPException(
            status_code=409,
            detail={
                "action": "lock_physical_model",
                "allowed": False,
                "blockers": blockers,
            },
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
