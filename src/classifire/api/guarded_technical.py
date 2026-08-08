from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Opening, User
from ..security import require_permission
from ..services.technical import search_for_opening
from ..services.workflow import WorkflowAction
from ..services.workflow_guard import check_estimate_action

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Technical Guarded"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/openings/{opening_id}/technical-search")
def guarded_opening_technical_search(
    opening_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("technical:read"))],
) -> dict[str, Any]:
    opening = db.scalar(
        select(Opening)
        .where(Opening.id == opening_id)
        .options(selectinload(Opening.services), selectinload(Opening.estimate))
    )
    if not opening:
        raise HTTPException(status_code=404, detail="Opening not found")

    receipt = check_estimate_action(db, opening.estimate, WorkflowAction.SEARCH_TECHNICAL)
    if not receipt.allowed:
        raise HTTPException(status_code=409, detail=receipt.as_dict())
    return search_for_opening(db, opening)
