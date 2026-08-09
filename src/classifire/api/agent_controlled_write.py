from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..agent_security import require_agent_scope
from ..audit import record_audit
from ..canonical_models import SystemRequiredComponent
from ..db import get_db
from ..models import AgentServicePrincipal, Estimate, Opening
from ..services.commercial import CommercialPricingError, derive_commercial_pricing
from ..services.quantity_labour import QuantityLabourError
from ..services.quantity_labour_runtime import derive_quantity_and_labour_runtime
from ..services.release_scope import ReleaseScopeError
from ..services.repair_strategy import (
    RepairStrategyError,
    create_repair_strategy_lock,
    select_repair_strategy,
)
from ..services.workflow import WorkflowTransitionError
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1/agent", tags=["CLASSIFIRE Controlled Agent Writes"])
Db = Annotated[Session, Depends(get_db)]


class AgentRepairStrategySelectionInput(BaseModel):
    variant_id: str = Field(min_length=1, max_length=300)
    match_classification: str = Field(default="opening_specific_candidate", max_length=100)
    treatment_description: str | None = None
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentQuantityLabourDeriveInput(BaseModel):
    component_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    labour_adjustments: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentCommercialDeriveInput(BaseModel):
    library_selections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parameterised_selections: dict[str, dict[str, Any]] = Field(default_factory=dict)
    component_builds: dict[str, dict[str, Any]] = Field(default_factory=dict)
    expert_estimates: dict[str, dict[str, Any]] = Field(default_factory=dict)


def _estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _opening(db: Session, opening_id: str) -> Opening:
    opening = db.scalar(
        select(Opening)
        .where(Opening.id == opening_id)
        .options(selectinload(Opening.services), selectinload(Opening.estimate))
    )
    if opening is None:
        raise HTTPException(status_code=404, detail="Opening not found")
    return opening


def _agent_audit(
    db: Session,
    *,
    principal: AgentServicePrincipal,
    action: str,
    entity_type: str,
    entity_id: str,
    project_id: str | None,
    new_value: dict[str, Any],
    reason: str,
) -> None:
    record_audit(
        db,
        actor=None,
        actor_type="agent",
        actor_name=principal.agent_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        new_value=new_value,
        reason=reason,
    )


@router.post("/openings/{opening_id}/repair-strategy")
def agent_select_repair_strategy(
    opening_id: str,
    payload: AgentRepairStrategySelectionInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("technical:select"))
    ],
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
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _agent_audit(
        db,
        principal=principal,
        action="agent_select_repair_strategy",
        entity_type="repair_strategy",
        entity_id=strategy.id,
        project_id=opening.estimate.project_id,
        new_value={
            "opening_id": opening.id,
            "variant_id": payload.variant_id,
            "candidate_id": strategy.candidate_id,
            "status": strategy.status,
        },
        reason="Role-limited cf-technical-system Package 15 candidate selection",
    )
    db.commit()
    db.refresh(strategy)
    return {
        "agent_id": principal.agent_id,
        "repair_strategy_id": strategy.id,
        "opening_id": strategy.opening_id,
        "candidate_id": strategy.candidate_id,
        "status": strategy.status,
        "technical_basis": strategy.technical_basis,
    }


@router.post("/openings/{opening_id}/repair-strategy/lock")
def agent_lock_repair_strategy(
    opening_id: str,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("technical:lock"))
    ],
) -> dict[str, Any]:
    opening = _opening(db, opening_id)
    try:
        lock, created, components = create_repair_strategy_lock(db, opening)
    except (WorkflowTransitionError, RepairStrategyError, ReleaseScopeError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    _agent_audit(
        db,
        principal=principal,
        action="agent_lock_repair_strategy",
        entity_type="repair_strategy_lock",
        entity_id=lock.id,
        project_id=opening.estimate.project_id,
        new_value={
            "opening_id": opening.id,
            "candidate_id": lock.candidate_id,
            "validator_result": lock.validator_result,
            "required_component_ids": lock.required_component_ids,
            "content_hash": lock.content_hash,
            "created": created,
        },
        reason="Role-limited cf-technical-system deterministic RepairStrategyLock request",
    )
    db.commit()
    db.refresh(lock)
    return {
        "agent_id": principal.agent_id,
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
                "service_id": component.service_id,
                "category": component.category,
                "description": component.description,
                "technical_requirement_id": component.technical_requirement_id,
                "quantity_formula_id": component.quantity_formula_id,
                "required_labour_activity_ids": component.required_labour_activity_ids or [],
                "candidate_status": component.candidate_status,
            }
            for component in components
        ],
    }


@router.post("/estimates/{estimate_id}/quantity-labour/derive")
def agent_derive_quantity_labour(
    estimate_id: str,
    payload: AgentQuantityLabourDeriveInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("quantity:derive"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
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
    _agent_audit(
        db,
        principal=principal,
        action="agent_derive_quantity_and_labour",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "quantity_record_ids": [item.id for item in result.quantities],
            "labour_activity_ids": [item.id for item in result.labour_activities],
            "workflow_stage": assessment.stage,
        },
        reason="Role-limited cf-physical-model deterministic quantity/person-hour derivation",
    )
    db.commit()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "workflow_stage": assessment.stage,
        "quantities": [
            {
                "id": item.id,
                "required_component_id": item.required_component_id,
                "formula_id": item.formula_id,
                "numeric_value": str(item.numeric_value) if item.numeric_value is not None else None,
                "unit_basis": item.unit_basis,
                "status": item.status,
            }
            for item in result.quantities
        ],
        "labour_activities": [
            {
                "id": item.id,
                "required_component_id": item.required_component_id,
                "activity_name": item.activity_name,
                "person_hours": (
                    str(item.labour_quantity_hours)
                    if item.labour_quantity_hours is not None
                    else None
                ),
                "status": item.status,
            }
            for item in result.labour_activities
        ],
    }


@router.get("/estimates/{estimate_id}/required-components")
def agent_required_components(
    estimate_id: str,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("commercial:components"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    rows = list(
        db.scalars(
            select(SystemRequiredComponent)
            .join(Opening, Opening.id == SystemRequiredComponent.opening_id)
            .where(Opening.estimate_id == estimate.id)
            .order_by(SystemRequiredComponent.opening_id, SystemRequiredComponent.service_id, SystemRequiredComponent.id)
        ).all()
    )
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "required_components": [
            {
                "id": row.id,
                "opening_id": row.opening_id,
                "service_id": row.service_id,
                "candidate_id": row.candidate_id,
                "category": row.category,
                "description": row.description,
                "technical_requirement_id": row.technical_requirement_id,
                "quantity_formula_id": row.quantity_formula_id,
                "required_labour_activity_ids": row.required_labour_activity_ids or [],
                "candidate_status": row.candidate_status,
                "mandatory": row.mandatory,
            }
            for row in rows
        ],
    }


@router.post("/estimates/{estimate_id}/commercial/derive")
def agent_derive_commercial(
    estimate_id: str,
    payload: AgentCommercialDeriveInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("commercial:derive"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        result = derive_commercial_pricing(
            db,
            estimate,
            library_selections=payload.library_selections,
            parameterised_selections=payload.parameterised_selections,
            component_builds=payload.component_builds,
            expert_estimates=payload.expert_estimates,
        )
    except (WorkflowTransitionError, CommercialPricingError, ReleaseScopeError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    assessment = assess_estimate_workflow(db, estimate)
    subtotal = sum(
        (
            item.extended_cost
            for item in result.pricing_components
            if item.extended_cost is not None and item.status != "superseded"
        ),
        0,
    )
    _agent_audit(
        db,
        principal=principal,
        action="agent_derive_commercial_pricing",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "pricing_component_ids": [item.id for item in result.pricing_components],
            "commercial_method_lock_ids": [item.id for item in result.method_locks],
            "commercial_recovery_ids": [item.id for item in result.recovery_records],
            "component_reconciliation_ids": [item.id for item in result.reconciliations],
            "price_anomaly_review_ids": [item.id for item in result.anomaly_reviews],
            "canonical_commercial_subtotal_ex_tax": str(subtotal),
            "workflow_stage": assessment.stage,
        },
        reason="Role-limited cf-commercial-engine controlled commercial hierarchy derivation",
    )
    db.commit()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "workflow_stage": assessment.stage,
        "canonical_commercial_subtotal_ex_tax": str(subtotal),
        "pricing_components": [
            {
                "id": item.id,
                "required_component_id": item.required_component_id,
                "component_type": item.component_type,
                "rate_source": item.rate_source,
                "unit_rate": str(item.unit_rate) if item.unit_rate is not None else None,
                "extended_cost": str(item.extended_cost) if item.extended_cost is not None else None,
                "status": item.status,
                "confidence": item.confidence,
                "risk_status": item.risk_status,
            }
            for item in result.pricing_components
        ],
        "method_locks": [
            {
                "id": item.id,
                "pricing_component_id": item.component_id,
                "selected_pricing_method": item.selected_pricing_method,
                "rate_applicability_result": item.rate_applicability_result,
                "recovery_status": item.recovery_status,
                "anomaly_result": item.anomaly_result,
                "validator_outcome": item.validator_outcome,
            }
            for item in result.method_locks
        ],
        "anomaly_reviews": [
            {
                "id": item.id,
                "result": item.result,
                "subject_ids": item.subject_ids or [],
                "required_action": item.required_action,
            }
            for item in result.anomaly_reviews
        ],
    }
