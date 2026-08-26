from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import Estimate, StoredFile, User
from ..physical_models import Defect, EvidenceSource
from ..security import require_permission
from ..services.physical_model import PhysicalModelLockError, create_physical_model_lock
from ..services.physical_mutation_guard import PhysicalMutationError, require_evidence_mutation
from ..services.storage import (
    StoredFileSecurityError,
    require_clean_stored_file_for_session,
)
from ..services.workflow import WorkflowTransitionError

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Physical Model"])
Db = Annotated[Session, Depends(get_db)]
_ADMISSIBLE_EVIDENCE_FILE_PURPOSES = frozenset({"technical_evidence"})


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


class PhysicalModelLockRequest(BaseModel):
    reason: str = Field(default="Physical model reviewed and locked", min_length=1, max_length=2000)


def _estimate_or_404(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _normalise_token(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _require_admissible_evidence_file(stored: StoredFile) -> None:
    """Accept the narrow immutable technical-evidence class.

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


@router.post("/estimates/{estimate_id}/evidence-sources", status_code=status.HTTP_201_CREATED)
def register_evidence_source(
    estimate_id: str,
    payload: EvidenceSourceInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
    settings: Annotated[Settings, Depends(get_settings)],
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
    try:
        require_clean_stored_file_for_session(
            db,
            stored,
            storage_root=settings.storage_root,
            allowed_purposes={"technical_evidence"},
        )
    except StoredFileSecurityError as exc:
        raise HTTPException(
            status_code=409,
            detail=exc.code,
        ) from exc
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
    record_audit(
        db,
        actor=user,
        action="register_evidence_source",
        entity_type="evidence_source",
        entity_id=evidence.id,
        project_id=estimate.project_id,
        new_value={
            "estimate_id": estimate.id,
            "defect_id": evidence.defect_id,
            "evidence_type": evidence.evidence_type,
            "stored_file_id": evidence.stored_file_id,
            "sha256": evidence.sha256,
            "source_reference": evidence.source_reference,
            "page_number": evidence.page_number,
            "region_reference": evidence.region_reference,
            "evidence_class": evidence.evidence_class,
        },
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
        lock, created = create_physical_model_lock(
            db,
            estimate,
            storage_root=settings.storage_root,
        )
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
