from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Estimate, User
from ..security import require_permission
from ..services.workflow import WorkflowAction
from ..services.workflow_guard import check_estimate_action

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Workflow"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/estimates/{estimate_id}/workflow/actions/{action}")
def estimate_workflow_action_preflight(
    estimate_id: str,
    action: WorkflowAction,
    db: Db,
    _user: Annotated[User, Depends(require_permission("estimate:read"))],
) -> dict[str, Any]:
    """Return whether one v2.13 workflow action is legal for the retained estimate state."""
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return check_estimate_action(db, estimate, action).as_dict()
