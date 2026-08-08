from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..canonical_models import SystemRequiredComponent
from ..db import get_db
from ..models import Estimate, Opening, Service, User
from ..security import require_permission
from ..services.commercial import (
    CommercialPricingError,
    derive_commercial_pricing,
    search_package14_candidates,
)
from ..services.commercial_near_matches import recommend_package14_matches
from ..services.release_scope import ReleaseScopeError
from ..services.workflow import WorkflowTransitionError
from ..services.workflow_db import assess_estimate_workflow

router = APIRouter(prefix="/api/v1", tags=["QUANTIFIRE Commercial"])
Db = Annotated[Session, Depends(get_db)]


class RateQuantityInput(BaseModel):
    value: Any
    unit: str = Field(min_length=1, max_length=80)
    validator_status: str = Field(default="PASS", max_length=30)
    evidence_ids: list[str] = Field(default_factory=list)


class LibraryRateSelectionInput(BaseModel):
    pkb_entry_id: str = Field(min_length=1, max_length=100)
    anchor_required_component_id: str | None = None
    included_required_component_ids: list[str] | None = None
    rate_quantity: RateQuantityInput | None = None
    reconciliation_proof: str | None = None


class ParameterisedRateSelectionInput(BaseModel):
    pkb_entry_id: str = Field(min_length=1, max_length=100)
    unit_rate: Any
    parameterisation_formula_id: str = Field(min_length=1, max_length=300)
    approval_reference: str = Field(min_length=1, max_length=300)
    validator_status: str = Field(default="PASS", max_length=30)
    anchor_required_component_id: str | None = None
    included_required_component_ids: list[str] | None = None
    rate_quantity: RateQuantityInput | None = None
    reconciliation_proof: str | None = None


class ComponentBuildInput(BaseModel):
    product_sku: str | None = None
    labour_codes: dict[str, str] = Field(default_factory=dict)
    validator_status: str = Field(default="PASS", max_length=30)
    proof_reference: str | None = None


class ExpertEstimateInput(BaseModel):
    unit_rate: Any
    rationale: str = Field(min_length=1)
    evidence_reference: str = Field(min_length=1, max_length=500)
    validator_status: str = Field(default="PASS", max_length=30)


class CommercialDeriveInput(BaseModel):
    # Scope keys are service:<service_id>. Opening-shared components are recovered
    # through an inclusion ledger or priced independently by the lower hierarchy.
    library_selections: dict[str, LibraryRateSelectionInput] = Field(default_factory=dict)
    parameterised_selections: dict[str, ParameterisedRateSelectionInput] = Field(default_factory=dict)
    component_builds: dict[str, ComponentBuildInput] = Field(default_factory=dict)
    expert_estimates: dict[str, ExpertEstimateInput] = Field(default_factory=dict)


def _dump_mapping(mapping: dict[str, BaseModel]) -> dict[str, dict[str, Any]]:
    return {key: value.model_dump(mode="json", exclude_none=True) for key, value in mapping.items()}


@router.get("/required-components/{component_id}/package14-candidates")
def package14_candidates(
    component_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("estimate:read"))],
) -> dict[str, Any]:
    component = db.get(SystemRequiredComponent, component_id)
    if not component:
        raise HTTPException(status_code=404, detail="Required component not found")
    opening = db.get(Opening, component.opening_id)
    if not opening:
        raise HTTPException(status_code=409, detail="Required component opening is missing")
    estimate = db.get(Estimate, opening.estimate_id)
    if not estimate:
        raise HTTPException(status_code=409, detail="Required component estimate is missing")
    service = db.get(Service, component.service_id) if component.service_id else None
    try:
        candidates = search_package14_candidates(
            db,
            estimate,
            opening=opening,
            service=service,
            limit=50,
        )
        recommendation = recommend_package14_matches(
            db,
            estimate,
            opening=opening,
            service=service,
        )
    except (CommercialPricingError, ReleaseScopeError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "required_component_id": component.id,
        "opening_id": component.opening_id,
        "service_id": component.service_id,
        "candidate_id": component.candidate_id,
        "candidates": [item.as_dict() for item in candidates],
        "recommendation": recommendation.as_dict(),
    }


@router.post("/estimates/{estimate_id}/commercial/derive")
def derive_estimate_commercial(
    estimate_id: str,
    payload: CommercialDeriveInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    estimate = db.get(Estimate, estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    try:
        result = derive_commercial_pricing(
            db,
            estimate,
            library_selections=_dump_mapping(payload.library_selections),
            parameterised_selections=_dump_mapping(payload.parameterised_selections),
            component_builds=_dump_mapping(payload.component_builds),
            expert_estimates=_dump_mapping(payload.expert_estimates),
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
    record_audit(
        db,
        actor=user,
        action="derive_commercial_pricing",
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
        reason="QUANTIFIRE v2.13 controlled Package 14 commercial hierarchy",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
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
