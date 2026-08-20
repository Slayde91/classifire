from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import Estimate
from .security import verify_csrf
from .services.release_pinning import pin_current_releases
from .services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
)
from .ui import _require

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


@router.post("/estimates/{estimate_id}/release-basis/refresh")
def refresh(
    estimate_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Refresh estimate release basis",
):
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(404, "Estimate not found")
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(409, str(exc)) from exc
    previous = {
        k: getattr(estimate, f, None)
        for k, f in {
            "pricing": "pricing_release_id",
            "technical": "technical_release_id",
            "rules": "rules_release_id",
            "products": "products_release_id",
            "labour": "labour_release_id",
            "markups": "markups_release_id",
        }.items()
    }
    try:
        basis = pin_current_releases(db, estimate)
    except ValueError as exc:
        return RedirectResponse(
            f"/estimates/{estimate.id}?error={str(exc).replace(' ', '+')}", status_code=303
        )
    record_audit(
        db,
        actor=user,
        action="refresh_release_basis",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        previous_value=previous,
        new_value={k: v["release_id"] for k, v in basis.items()},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/estimates/{estimate.id}?success=Release+basis+refreshed", status_code=303
    )
