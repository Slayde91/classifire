from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Opening, User
from ..security import require_permission
from ..services.release_scope import ReleaseScopeError
from ..services.repair_strategy import (
    RepairStrategyError,
    create_repair_strategy_lock,
    select_repair_strategy,
)
from ..services.workflow import WorkflowTransitionError

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Repair Strategy"])
Db = Annotated[Session, Depends(get_db)]


class RepairStrategySelectionInput(BaseModel):
    variant_id: str = Field(min_length=1, max_length=300)
    match_classification: str = Field(default="opening_specific_candidate", max_length=100)
    treatment_description: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _opening(db: Session, opening_id: str) -> Opening:
    opening = db.scalar(
        select(Opening)
        .where(Opening.id == opening_id)
        .options(selectinload(Opening.services), selectinload(Opening.estimate))
    )
    if not opening:
        raise HTTPException(status_code=404, detail="Opening not found")
    return opening


@router.post("/openings/{opening_id}/repair-strategy")
def choose_repair_strategy(
    opening_id: str,
    payload: RepairStrategySelectionInput,
    db: Db,
    _user: Annotated[User, Depends(require_permission("technical:write"))],
) -> dict[str, Any]:
    opening = _opening(db, opening_id)
    try:
        strategy = select_repair_strategy(
            db,
            opening,
            variant_id=payload.variant_id,
            match_classification=payload.match_classification,
            treatment_description=payload.treatment_description,
            assumptions=payload.assumptions,
            limitations=payload.limitations,
        )
    except (WorkflowTransitionError, RepairStrategyError, ReleaseScopeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(strategy)
    return {
        "repair_strategy_id": strategy.id,
        "opening_id": strategy.opening_id,
        "candidate_id": strategy.candidate_id,
        "status": strategy.status,
        "technical_basis": strategy.technical_basis,
    }


@router.post("/openings/{opening_id}/repair-strategy/lock")
def lock_repair_strategy(
    opening_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("technical:approve"))],
) -> dict[str, Any]:
    opening = _opening(db, opening_id)
    try:
        lock, created, components = create_repair_strategy_lock(db, opening)
    except (WorkflowTransitionError, RepairStrategyError, ReleaseScopeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(lock)
    return {
        "repair_strategy_lock_id": lock.id,
        "opening_id": lock.opening_id,
        "candidate_id": lock.candidate_id,
        "created": created,
        "validator_result": lock.validator_result,
        "content_hash": lock.content_hash,
        "required_component_ids": lock.required_component_ids,
        "components": [
            {
                "id": component.id,
                "category": component.category,
                "description": component.description,
                "required_labour_activity_ids": component.required_labour_activity_ids or [],
                "candidate_status": component.candidate_status,
            }
            for component in components
        ],
    }
