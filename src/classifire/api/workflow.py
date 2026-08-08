from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Estimate, User
from ..security import require_permission
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1", tags=["CLASSIFIRE Workflow"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/estimates/{estimate_id}/workflow")
def estimate_workflow_status(
    estimate_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("estimate:read"))],
) -> dict[str, Any]:
    """Return deterministic v2.13 workflow facts derived from retained database records."""
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return assess_estimate_workflow(db, estimate).as_dict()
