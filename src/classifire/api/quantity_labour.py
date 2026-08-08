from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..db import get_db
from ..models import Estimate, User
from ..security import require_permission
from ..services.quantity_labour import QuantityLabourError
from ..services.quantity_labour_runtime import derive_quantity_and_labour_runtime
from ..services.release_scope import ReleaseScopeError
from ..services.workflow import WorkflowTransitionError
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Quantity and Labour"])
Db = Annotated[Session, Depends(get_db)]


class QuantityLabourDeriveInput(BaseModel):
    component_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    labour_adjustments: dict[str, dict[str, Any]] = Field(default_factory=dict)


@router.post("/estimates/{estimate_id}/quantity-labour/derive")
def derive_estimate_quantity_and_labour(
    estimate_id: str,
    payload: QuantityLabourDeriveInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        result = derive_quantity_and_labour_runtime(
            db,
            estimate,
            component_inputs=payload.component_inputs,
            labour_adjustments=payload.labour_adjustments,
        )
    except (WorkflowTransitionError, QuantityLabourError, ReleaseScopeError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    assessment = assess_estimate_workflow(db, estimate)
    record_audit(
        db,
        actor=user,
        action="derive_quantity_and_labour",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "labour_release_id": estimate.labour_release_id,
            "quantity_record_ids": [item.id for item in result.quantities],
            "labour_activity_ids": [item.id for item in result.labour_activities],
            "workflow_stage": assessment.stage,
        },
        reason="Deterministic v2.13 quantity and pinned-productivity person-hour derivation",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "estimate_id": estimate.id,
        "labour_release_id": estimate.labour_release_id,
        "workflow_stage": assessment.stage,
        "quantities": [
            {
                "id": item.id,
                "required_component_id": item.required_component_id,
                "formula_id": item.formula_id,
                "numeric_value": str(item.numeric_value) if item.numeric_value is not None else None,
                "unit_basis": item.unit_basis,
                "status": item.status,
                "record_version": item.record_version,
            }
            for item in result.quantities
        ],
        "labour_activities": [
            {
                "id": item.id,
                "required_component_id": item.required_component_id,
                "activity_name": item.activity_name,
                "productivity_source_id": item.productivity_source_id,
                "person_hours": (
                    str(item.labour_quantity_hours)
                    if item.labour_quantity_hours is not None
                    else None
                ),
                "status": item.status,
                "unit_rate": None,
                "extended_cost": None,
            }
            for item in result.labour_activities
        ],
    }
