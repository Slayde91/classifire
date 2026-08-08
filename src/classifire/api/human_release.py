from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..db import get_db
from ..models import Estimate, User
from ..security import require_permission
from ..services.human_release import HumanReleaseError, release_estimate
from ..services.validation import IndependentValidationError
from ..services.workflow import WorkflowTransitionError
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Human Release"])
Db = Annotated[Session, Depends(get_db)]


class HumanReleaseInput(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


@router.post("/estimates/{estimate_id}/release")
def human_release_estimate(
    estimate_id: str,
    payload: HumanReleaseInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:approve"))],
) -> dict[str, Any]:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    try:
        receipt = release_estimate(
            db,
            estimate,
            approver=user,
            reason=payload.reason,
        )
    except (WorkflowTransitionError, HumanReleaseError, IndependentValidationError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    assessment = assess_estimate_workflow(db, estimate)
    record_audit(
        db,
        actor=user,
        action="human_release",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "approval_id": receipt.approval.id,
            "snapshot_hash": receipt.snapshot_hash,
            "validation_gate_id": receipt.validation_gate.id,
            "certificate_hash": receipt.certificate_hash,
            "created": receipt.created,
            "workflow_stage": assessment.stage,
        },
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()

    return {
        **receipt.as_dict(),
        "workflow_stage": assessment.stage,
        "approved_by_user_id": user.id,
        "approved_by": user.full_name,
    }
