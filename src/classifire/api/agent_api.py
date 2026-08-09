from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import __version__
from ..agent_security import require_agent_scope
from ..audit import record_audit
from ..canonical_models import EvidenceSource, PhysicalModelLock, SystemRequiredComponent
from ..config import Settings, get_settings
from ..db import get_db
from ..models import AgentServicePrincipal, Estimate, LibraryRelease, Opening, Service
from ..outputs import render_estimate_pdf, render_proposal_workbook, render_technical_workbook
from ..services.commercial_near_matches import recommend_package14_matches
from ..services.technical import search_for_opening
from ..services.validated_snapshot import SNAPSHOT_SCHEMA, ValidatedSnapshotError, lock_validated_snapshot
from ..services.validation import IndependentValidationError, latest_passing_gate, run_independent_validation
from ..services.workflow import WorkflowAction, WorkflowTransitionError
from ..services.workflow_db import assess_estimate_workflow
from ..services.workflow_guard import check_estimate_action, require_estimate_action

router = APIRouter(prefix="/api/v1/agent", tags=["CLASSIFIRE Agent Service API"])
Db = Annotated[Session, Depends(get_db)]


class SnapshotLockInput(BaseModel):
    reason: str = Field(default="Controlled agent snapshot request", min_length=3, max_length=1000)


class RenderOutputInput(BaseModel):
    artifact_type: str = Field(pattern="^(technical-xlsx|proposal-xlsx|technical-pdf|proposal-pdf)$")


def _estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


def _decimal(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@router.get("/health")
def agent_health(
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("health:read"))],
) -> dict[str, Any]:
    return {
        "status": "ok",
        "product": "CLASSIFIRE",
        "version": __version__,
        "agent_id": principal.agent_id,
        "scopes": principal.scopes or [],
        "human_release_exposed": False,
    }


@router.get("/estimates/{estimate_id}/workflow")
def agent_workflow_status(
    estimate_id: str,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("workflow:read"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    assessment = assess_estimate_workflow(db, estimate)
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "estimate_reference": estimate.reference,
        "estimate_status": estimate.status,
        **assessment.as_dict(),
    }


@router.get("/estimates/{estimate_id}/evidence")
def agent_evidence(
    estimate_id: str,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("evidence:read"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    rows = list(
        db.scalars(
            select(EvidenceSource)
            .where(EvidenceSource.estimate_id == estimate.id)
            .order_by(EvidenceSource.created_at, EvidenceSource.id)
        ).all()
    )
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "evidence": [
            {
                "id": row.id,
                "defect_id": row.defect_id,
                "stored_file_id": row.stored_file_id,
                "evidence_type": row.evidence_type,
                "source_reference": row.source_reference,
                "page_number": row.page_number,
                "region_reference": row.region_reference,
                "sha256": row.sha256,
                "evidence_class": row.evidence_class,
                "confidence": _decimal(row.confidence),
                "status": row.status,
            }
            for row in rows
        ],
    }


@router.get("/estimates/{estimate_id}/physical-model")
def agent_physical_model(
    estimate_id: str,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("physical:read"))],
) -> dict[str, Any]:
    estimate = db.scalar(
        select(Estimate)
        .where(Estimate.id == estimate_id)
        .options(selectinload(Estimate.openings).selectinload(Opening.services))
    )
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    locks = list(
        db.scalars(
            select(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .order_by(PhysicalModelLock.created_at.desc())
        ).all()
    )
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "openings": [
            {
                "id": opening.id,
                "opening_code": opening.opening_code,
                "defect_id": opening.defect_id,
                "canonical_defect_id": opening.canonical_defect_id,
                "location": opening.location,
                "substrate_type": opening.substrate_type,
                "substrate_plane": opening.substrate_plane,
                "substrate_thickness_mm": _decimal(opening.substrate_thickness_mm),
                "orientation": opening.orientation,
                "opening_type": opening.opening_type,
                "width_mm": _decimal(opening.width_mm),
                "height_mm": _decimal(opening.height_mm),
                "diameter_mm": _decimal(opening.diameter_mm),
                "frl": opening.frl,
                "physical_model_status": opening.physical_model_status,
                "technical_status": opening.technical_status,
                "selected_technical_variant_id": opening.selected_technical_variant_id,
                "services": [
                    {
                        "id": service.id,
                        "service_code": service.service_code,
                        "service_type": service.service_type,
                        "material": service.material,
                        "nominal_size_mm": _decimal(service.nominal_size_mm),
                        "outside_diameter_mm": _decimal(service.outside_diameter_mm),
                        "width_mm": _decimal(service.width_mm),
                        "height_mm": _decimal(service.height_mm),
                        "insulation_type": service.insulation_type,
                        "insulation_thickness_mm": _decimal(service.insulation_thickness_mm),
                        "quantity": _decimal(service.quantity),
                        "centre_x_mm": _decimal(service.centre_x_mm),
                        "centre_y_mm": _decimal(service.centre_y_mm),
                        "evidence_status": service.evidence_status,
                        "confidence": _decimal(service.confidence),
                    }
                    for service in opening.services
                ],
            }
            for opening in estimate.openings
        ],
        "active_physical_model_locks": [
            {
                "id": lock.id,
                "validator_result": lock.validator_result,
                "content_hash": lock.content_hash,
                "opening_ids": lock.opening_ids,
                "service_ids": lock.service_ids,
                "critical_unknowns": lock.critical_unknowns or [],
            }
            for lock in locks
        ],
    }


@router.get("/openings/{opening_id}/technical-search")
def agent_technical_search(
    opening_id: str,
    db: Db,
    _principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("technical:search"))
    ],
) -> dict[str, Any]:
    opening = db.scalar(
        select(Opening)
        .where(Opening.id == opening_id)
        .options(selectinload(Opening.services), selectinload(Opening.estimate))
    )
    if opening is None:
        raise HTTPException(status_code=404, detail="Opening not found")
    receipt = check_estimate_action(db, opening.estimate, WorkflowAction.SEARCH_TECHNICAL)
    if not receipt.allowed:
        raise HTTPException(status_code=409, detail=receipt.as_dict())
    return search_for_opening(db, opening)


@router.get("/required-components/{component_id}/package14-recommendation")
def agent_package14_recommendation(
    component_id: str,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("commercial:recommend"))
    ],
) -> dict[str, Any]:
    component = db.get(SystemRequiredComponent, component_id)
    if component is None:
        raise HTTPException(status_code=404, detail="Required component not found")
    opening = db.get(Opening, component.opening_id)
    if opening is None:
        raise HTTPException(status_code=409, detail="Required component opening is missing")
    estimate = db.get(Estimate, opening.estimate_id)
    if estimate is None:
        raise HTTPException(status_code=409, detail="Required component estimate is missing")
    service = db.get(Service, component.service_id) if component.service_id else None
    recommendation = recommend_package14_matches(
        db,
        estimate,
        opening=opening,
        service=service,
    )
    return {
        "agent_id": principal.agent_id,
        "required_component_id": component.id,
        "opening_id": component.opening_id,
        "service_id": component.service_id,
        "recommendation": recommendation.as_dict(),
    }


@router.post("/estimates/{estimate_id}/independent-validation")
def agent_independent_validation(
    estimate_id: str,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("validation:run"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        result = run_independent_validation(db, estimate)
    except WorkflowTransitionError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record_audit(
        db,
        actor=None,
        actor_type="agent",
        actor_name=principal.agent_id,
        action="agent_independent_validation",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "gate_evidence_id": result.gate_evidence.id,
            "result": result.gate_evidence.result,
            "state_hash": result.state_hash,
            "exception_count": len(result.issues),
        },
        reason="Role-limited cf-validator deterministic validation request",
    )
    db.commit()
    return result.as_dict()


@router.post("/estimates/{estimate_id}/lock")
def agent_lock_validated_snapshot(
    estimate_id: str,
    payload: SnapshotLockInput,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("snapshot:lock"))],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        gate = latest_passing_gate(db, estimate)
        snapshot, created = lock_validated_snapshot(db, estimate)
    except (WorkflowTransitionError, IndependentValidationError, ValidatedSnapshotError) as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    certificate_hash = (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash")
    record_audit(
        db,
        actor=None,
        actor_type="agent",
        actor_name=principal.agent_id,
        action="agent_lock_validated_snapshot",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "snapshot_hash": snapshot["snapshot_hash"],
            "validation_gate_id": gate.id,
            "certificate_hash": certificate_hash,
            "created": created,
        },
        reason=payload.reason,
    )
    db.commit()
    return {
        "estimate_id": estimate.id,
        "snapshot_hash": snapshot["snapshot_hash"],
        "validation_gate_id": gate.id,
        "certificate_hash": certificate_hash,
        "created": created,
        "status": estimate.status,
    }


@router.post("/estimates/{estimate_id}/render")
def agent_render_output(
    estimate_id: str,
    payload: RenderOutputInput,
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("output:render"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        require_estimate_action(db, estimate, WorkflowAction.RENDER_OUTPUT)
        gate = latest_passing_gate(db, estimate)
    except (WorkflowTransitionError, IndependentValidationError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    snapshot = estimate.snapshot_json
    if not snapshot or not estimate.snapshot_hash:
        raise HTTPException(status_code=409, detail="Validated snapshot is missing")
    if snapshot.get("schema") != SNAPSHOT_SCHEMA:
        raise HTTPException(status_code=409, detail="Only the canonical v2.13 validated snapshot may be rendered")
    certificate_hash = (snapshot.get("estimate_certificate") or {}).get("final_certificate_hash")
    if not certificate_hash:
        raise HTTPException(status_code=409, detail="Validated snapshot has no EstimateCertificate hash")
    if snapshot.get("validation_state_hash") != str(gate.run_id or "").removeprefix("QF-IV:"):
        raise HTTPException(
            status_code=409,
            detail="Validated snapshot does not match current independent-validation state hash",
        )

    export_dir = settings.storage_root / "exports" / estimate.id / estimate.snapshot_hash
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in estimate.reference)
    mapping = {
        "technical-xlsx": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.xlsx",
            render_technical_workbook,
        ),
        "proposal-xlsx": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Proposal.xlsx",
            render_proposal_workbook,
        ),
        "technical-pdf": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.pdf",
            lambda s, p: render_estimate_pdf(s, p, proposal=False),
        ),
        "proposal-pdf": (
            f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Proposal.pdf",
            lambda s, p: render_estimate_pdf(s, p, proposal=True),
        ),
    }
    filename, renderer = mapping[payload.artifact_type]
    path = export_dir / filename
    if not path.exists():
        renderer(snapshot, path)
    artifact_hash = _file_sha256(path)
    record_audit(
        db,
        actor=None,
        actor_type="agent",
        actor_name=principal.agent_id,
        action="render_output",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "artifact_type": payload.artifact_type,
            "filename": filename,
            "artifact_sha256": artifact_hash,
            "snapshot_hash": estimate.snapshot_hash,
            "validation_gate_id": gate.id,
            "certificate_hash": certificate_hash,
        },
        reason="Role-limited cf-output render from immutable validated snapshot",
    )
    db.commit()
    return {
        "estimate_id": estimate.id,
        "artifact_type": payload.artifact_type,
        "filename": filename,
        "artifact_sha256": artifact_hash,
        "snapshot_hash": estimate.snapshot_hash,
        "validation_gate_id": gate.id,
        "certificate_hash": certificate_hash,
        "workflow_stage": assess_estimate_workflow(db, estimate).stage,
    }


@router.get("/library/releases")
def agent_library_releases(
    db: Db,
    principal: Annotated[AgentServicePrincipal, Depends(require_agent_scope("library:read"))],
) -> dict[str, Any]:
    rows = list(
        db.scalars(select(LibraryRelease).order_by(LibraryRelease.library_type, LibraryRelease.created_at.desc())).all()
    )
    return {
        "agent_id": principal.agent_id,
        "releases": [
            {
                "id": row.id,
                "library_type": row.library_type,
                "version": row.version,
                "status": row.status,
                "effective_date": row.effective_date.isoformat() if row.effective_date else None,
                "release_hash": row.release_hash,
                "approved_at": row.approved_at.isoformat() if row.approved_at else None,
                "supersedes_release_id": row.supersedes_release_id,
            }
            for row in rows
        ],
    }
