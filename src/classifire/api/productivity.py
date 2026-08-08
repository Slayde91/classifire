from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..commercial_models import ProductivitySource
from ..db import get_db
from ..models import AuditEvent, User
from ..security import require_permission
from ..services.productivity import (
    ProductivitySourceError,
    approve_productivity_source,
    create_productivity_source,
)

router = APIRouter(prefix="/api/v1", tags=["QUANTIFIRE Productivity"])
Db = Annotated[Session, Depends(get_db)]


class ProductivitySourceInput(BaseModel):
    activity: str = Field(min_length=1, max_length=200)
    quantity_unit: str = Field(min_length=1, max_length=80)
    base_hours_per_unit: Decimal = Field(gt=0)
    source_record_id: str = Field(min_length=1, max_length=200)
    source_version: str = Field(min_length=1, max_length=100)
    source_quantity: str | None = Field(default=None, max_length=200)
    source_crew: str | None = Field(default=None, max_length=200)
    source_hours: Decimal | None = Field(default=None, gt=0)
    decomposition_formula: str | None = None
    adjustment_formula: str | None = None
    executable_formula_id: str = Field(default="QF-LABOUR-ACTIVITY", max_length=300)
    evidence_class: str | None = Field(default=None, max_length=80)
    confidence: str | None = Field(default=None, max_length=80)


@router.get("/productivity-sources")
def list_productivity_sources(
    db: Db,
    _user: Annotated[User, Depends(require_permission("library:read"))],
    activity: str | None = None,
    approval_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict[str, Any]]:
    stmt = select(ProductivitySource)
    if activity:
        stmt = stmt.where(ProductivitySource.activity.ilike(f"%{activity}%"))
    if approval_status:
        stmt = stmt.where(ProductivitySource.approval_status == approval_status.upper())
    rows = db.scalars(
        stmt.order_by(ProductivitySource.activity, ProductivitySource.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "id": row.id,
            "activity": row.activity,
            "quantity_unit": row.quantity_unit,
            "base_hours_per_unit": str(row.base_hours_per_unit),
            "source_record_id": row.source_record_id,
            "source_version": row.source_version,
            "source_quantity": row.source_quantity,
            "source_crew": row.source_crew,
            "source_hours": str(row.source_hours) if row.source_hours is not None else None,
            "executable_formula_id": row.executable_formula_id,
            "evidence_class": row.evidence_class,
            "confidence": row.confidence,
            "approval_status": row.approval_status,
        }
        for row in rows
    ]


@router.post("/productivity-sources", status_code=status.HTTP_201_CREATED)
def create_productivity_source_endpoint(
    payload: ProductivitySourceInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("pricing:write"))],
) -> dict[str, Any]:
    try:
        record = create_productivity_source(db, **payload.model_dump())
    except ProductivitySourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(
        db,
        actor=user,
        action="create_productivity_source",
        entity_type="productivity_source",
        entity_id=record.id,
        new_value={
            "activity": record.activity,
            "quantity_unit": record.quantity_unit,
            "base_hours_per_unit": str(record.base_hours_per_unit),
            "source_record_id": record.source_record_id,
            "source_version": record.source_version,
            "approval_status": record.approval_status,
        },
        reason="Created as Draft productivity evidence record",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(record)
    return {"id": record.id, "status": record.approval_status}


@router.post("/productivity-sources/{source_id}/approve")
def approve_productivity_source_endpoint(
    source_id: str,
    reason: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("pricing:approve"))],
) -> dict[str, Any]:
    source = db.get(ProductivitySource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Productivity source not found")

    creator_id = db.scalar(
        select(AuditEvent.actor_user_id)
        .where(
            AuditEvent.entity_type == "productivity_source",
            AuditEvent.entity_id == source.id,
            AuditEvent.action == "create_productivity_source",
        )
        .order_by(AuditEvent.created_at.asc())
        .limit(1)
    )
    if creator_id == user.id and user.role != "administrator":
        raise HTTPException(
            status_code=409,
            detail="The creator cannot approve their own productivity source.",
        )

    previous = {"approval_status": source.approval_status}
    try:
        source, changed = approve_productivity_source(db, source)
    except ProductivitySourceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    record_audit(
        db,
        actor=user,
        action="approve_productivity_source",
        entity_type="productivity_source",
        entity_id=source.id,
        previous_value=previous,
        new_value={"approval_status": source.approval_status},
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": source.id, "status": source.approval_status, "changed": changed}
