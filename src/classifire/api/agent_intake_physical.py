from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent_security import require_agent_scope
from ..audit import record_audit
from ..canonical_models import Defect, EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from ..db import get_db
from ..models import AgentServicePrincipal, Estimate, Opening, Service, StoredFile
from ..services.physical_model import PhysicalModelLockError, create_physical_model_lock
from ..services.workflow import WorkflowTransitionError

router = APIRouter(prefix="/api/v1/agent", tags=["CLASSIFIRE Controlled Intake and Physical Model"])
Db = Annotated[Session, Depends(get_db)]


class AgentEvidenceObservation(BaseModel):
    stored_file_id: str = Field(min_length=1, max_length=36)
    evidence_type: str = Field(min_length=1, max_length=100)
    external_defect_id: str | None = Field(default=None, max_length=150)
    defect_code: str | None = Field(default=None, max_length=150)
    defect_description: str | None = None
    defect_location: str | None = None
    defect_classification: str | None = Field(default=None, max_length=100)
    source_reference: str | None = None
    page_number: str | None = Field(default=None, max_length=100)
    region_reference: str | None = Field(default=None, max_length=300)
    evidence_class: str = Field(default="observed", max_length=50)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source_json: dict[str, Any] | None = None


class AgentEvidenceBatchInput(BaseModel):
    observations: list[AgentEvidenceObservation] = Field(min_length=1, max_length=5000)


class AgentOpeningInput(BaseModel):
    opening_code: str = Field(min_length=1, max_length=100)
    external_defect_id: str | None = Field(default=None, max_length=150)
    location: str | None = None
    substrate_type: str | None = Field(default=None, max_length=200)
    substrate_plane: str | None = Field(default=None, max_length=50)
    substrate_thickness_mm: Decimal | None = Field(default=None, gt=0)
    orientation: str | None = Field(default=None, max_length=100)
    opening_type: str | None = Field(default=None, max_length=100)
    width_mm: Decimal | None = Field(default=None, gt=0)
    height_mm: Decimal | None = Field(default=None, gt=0)
    diameter_mm: Decimal | None = Field(default=None, gt=0)
    frl: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class AgentServiceInput(BaseModel):
    service_code: str = Field(min_length=1, max_length=100)
    primary_opening_code: str = Field(min_length=1, max_length=100)
    opening_codes: list[str] = Field(min_length=1, max_length=50)
    service_type: str = Field(min_length=1, max_length=200)
    material: str | None = Field(default=None, max_length=200)
    nominal_size_mm: Decimal | None = Field(default=None, gt=0)
    outside_diameter_mm: Decimal | None = Field(default=None, gt=0)
    width_mm: Decimal | None = Field(default=None, gt=0)
    height_mm: Decimal | None = Field(default=None, gt=0)
    insulation_type: str | None = Field(default=None, max_length=200)
    insulation_thickness_mm: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal = Field(gt=0)
    centre_x_mm: Decimal | None = None
    centre_y_mm: Decimal | None = None
    evidence_status: str = Field(default="provisional", max_length=30)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    relationship_status: str = Field(default="confirmed", max_length=30)
    link_type: str = Field(default="penetrates", max_length=50)
    source_reference: str | None = None
    notes: str | None = None


class AgentInitialPhysicalModelInput(BaseModel):
    openings: list[AgentOpeningInput] = Field(min_length=1, max_length=5000)
    services: list[AgentServiceInput] = Field(min_length=1, max_length=10000)


class AgentPhysicalModelLockInput(BaseModel):
    reason: str = Field(default="Controlled cf-physical-model lock request", min_length=3, max_length=2000)


def _estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        raise HTTPException(status_code=404, detail="Estimate not found")
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(status_code=409, detail="Estimate is no longer editable")
    return estimate


def _active_physical_lock_exists(db: Session, estimate_id: str) -> bool:
    return bool(
        db.scalar(
            select(PhysicalModelLock.id).where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            ).limit(1)
        )
    )


def _require_unlocked(db: Session, estimate: Estimate) -> None:
    if _active_physical_lock_exists(db, estimate.id):
        raise HTTPException(
            status_code=409,
            detail="Physical Model Lock already exists; controlled invalidation is required before upstream changes.",
        )


def _defect_for_external_id(
    db: Session,
    estimate: Estimate,
    external_defect_id: str | None,
    *,
    defect_code: str | None = None,
    description: str | None = None,
    location: str | None = None,
    classification: str | None = None,
) -> Defect | None:
    if not external_defect_id:
        return None
    defect = db.scalar(
        select(Defect).where(
            Defect.estimate_id == estimate.id,
            Defect.external_defect_id == external_defect_id,
        )
    )
    if defect is None:
        defect = Defect(
            estimate_id=estimate.id,
            external_defect_id=external_defect_id,
            defect_code=defect_code or external_defect_id,
            description=description,
            location=location,
            classification=classification,
            evidence_status="provisional",
            status="draft",
        )
        db.add(defect)
        db.flush()
        return defect

    comparisons = {
        "defect_code": defect_code,
        "description": description,
        "location": location,
        "classification": classification,
    }
    for field_name, proposed in comparisons.items():
        current = getattr(defect, field_name)
        if proposed is None:
            continue
        if current not in (None, "") and str(current).strip() != str(proposed).strip():
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Conflicting evidence for defect {external_defect_id}: {field_name} already "
                    "contains a different retained value. Resolve the conflict before continuing."
                ),
            )
        if current in (None, ""):
            setattr(defect, field_name, proposed)
    return defect


def _agent_audit(
    db: Session,
    *,
    principal: AgentServicePrincipal,
    action: str,
    entity_type: str,
    entity_id: str,
    estimate: Estimate,
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
        project_id=estimate.project_id,
        new_value=new_value,
        reason=reason,
    )


@router.post("/estimates/{estimate_id}/evidence/register")
def agent_register_evidence(
    estimate_id: str,
    payload: AgentEvidenceBatchInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("evidence:write"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    _require_unlocked(db, estimate)
    registered: list[dict[str, Any]] = []

    for item in payload.observations:
        stored = db.get(StoredFile, item.stored_file_id)
        if stored is None:
            db.rollback()
            raise HTTPException(status_code=404, detail=f"Stored evidence file not found: {item.stored_file_id}")
        defect = _defect_for_external_id(
            db,
            estimate,
            item.external_defect_id,
            defect_code=item.defect_code,
            description=item.defect_description,
            location=item.defect_location,
            classification=item.defect_classification,
        )
        defect_id = defect.id if defect else None
        existing = db.scalar(
            select(EvidenceSource).where(
                EvidenceSource.estimate_id == estimate.id,
                EvidenceSource.defect_id == defect_id,
                EvidenceSource.stored_file_id == stored.id,
                EvidenceSource.evidence_type == item.evidence_type,
                EvidenceSource.source_reference == item.source_reference,
                EvidenceSource.page_number == item.page_number,
                EvidenceSource.region_reference == item.region_reference,
            )
        )
        if existing is not None:
            registered.append({"id": existing.id, "created": False, "defect_id": defect_id})
            continue

        evidence = EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect_id,
            stored_file_id=stored.id,
            evidence_type=item.evidence_type,
            source_reference=item.source_reference,
            page_number=item.page_number,
            region_reference=item.region_reference,
            sha256=stored.sha256,
            evidence_class=item.evidence_class,
            confidence=item.confidence,
            status="active",
            source_json=item.source_json,
        )
        db.add(evidence)
        db.flush()
        _agent_audit(
            db,
            principal=principal,
            action="agent_register_evidence",
            entity_type="evidence_source",
            entity_id=evidence.id,
            estimate=estimate,
            new_value={
                "stored_file_id": stored.id,
                "sha256": stored.sha256,
                "defect_id": defect_id,
                "evidence_type": item.evidence_type,
                "page_number": item.page_number,
                "region_reference": item.region_reference,
                "evidence_class": item.evidence_class,
            },
            reason="Role-limited cf-intake-evidence source-preserving evidence registration",
        )
        registered.append({"id": evidence.id, "created": True, "defect_id": defect_id})

    db.commit()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "registered": registered,
        "count": len(registered),
    }


@router.post("/estimates/{estimate_id}/physical-model/initial")
def agent_submit_initial_physical_model(
    estimate_id: str,
    payload: AgentInitialPhysicalModelInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("physical:write"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    _require_unlocked(db, estimate)
    existing_opening = db.scalar(select(Opening.id).where(Opening.estimate_id == estimate.id).limit(1))
    if existing_opening:
        raise HTTPException(
            status_code=409,
            detail=(
                "Initial physical model already exists for this estimate. This endpoint is intentionally "
                "one-shot; use a controlled amendment workflow rather than silently replacing retained scope."
            ),
        )

    opening_codes = [item.opening_code for item in payload.openings]
    if len(set(opening_codes)) != len(opening_codes):
        raise HTTPException(status_code=422, detail="Opening codes must be unique within the submitted model")
    opening_by_code: dict[str, Opening] = {}

    for item in payload.openings:
        defect = _defect_for_external_id(db, estimate, item.external_defect_id)
        opening = Opening(
            estimate_id=estimate.id,
            defect_id=item.external_defect_id,
            canonical_defect_id=defect.id if defect else None,
            opening_code=item.opening_code,
            location=item.location,
            substrate_type=item.substrate_type,
            substrate_plane=item.substrate_plane,
            substrate_thickness_mm=item.substrate_thickness_mm,
            orientation=item.orientation,
            opening_type=item.opening_type,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            diameter_mm=item.diameter_mm,
            frl=item.frl,
            physical_model_status="modelled",
            technical_status="not_assessed",
            notes=item.notes,
        )
        db.add(opening)
        db.flush()
        opening_by_code[item.opening_code] = opening

    created_services: list[Service] = []
    created_links: list[ServiceOpeningLink] = []
    for item in payload.services:
        if item.primary_opening_code not in opening_by_code:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Unknown primary opening code for service {item.service_code}: {item.primary_opening_code}",
            )
        requested_codes = list(dict.fromkeys(item.opening_codes))
        if item.primary_opening_code not in requested_codes:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Service {item.service_code} must include its primary opening in opening_codes",
            )
        unknown_codes = sorted(set(requested_codes) - set(opening_by_code))
        if unknown_codes:
            db.rollback()
            raise HTTPException(
                status_code=422,
                detail=f"Unknown opening codes for service {item.service_code}: {', '.join(unknown_codes)}",
            )
        primary = opening_by_code[item.primary_opening_code]
        service = Service(
            opening_id=primary.id,
            service_code=item.service_code,
            service_type=item.service_type,
            material=item.material,
            nominal_size_mm=item.nominal_size_mm,
            outside_diameter_mm=item.outside_diameter_mm,
            width_mm=item.width_mm,
            height_mm=item.height_mm,
            insulation_type=item.insulation_type,
            insulation_thickness_mm=item.insulation_thickness_mm,
            quantity=item.quantity,
            centre_x_mm=item.centre_x_mm,
            centre_y_mm=item.centre_y_mm,
            evidence_status=item.evidence_status,
            confidence=item.confidence,
            notes=item.notes,
        )
        db.add(service)
        db.flush()
        created_services.append(service)
        for opening_code in requested_codes:
            opening = opening_by_code[opening_code]
            link = ServiceOpeningLink(
                service_id=service.id,
                opening_id=opening.id,
                link_type=item.link_type,
                relationship_status=item.relationship_status,
                evidence_status=item.evidence_status,
                confidence=item.confidence,
                source_reference=item.source_reference,
                notes=item.notes,
            )
            db.add(link)
            created_links.append(link)

    db.flush()
    _agent_audit(
        db,
        principal=principal,
        action="agent_submit_initial_physical_model",
        entity_type="estimate",
        entity_id=estimate.id,
        estimate=estimate,
        new_value={
            "opening_ids": sorted(opening.id for opening in opening_by_code.values()),
            "service_ids": sorted(service.id for service in created_services),
            "service_opening_link_count": len(created_links),
            "explicit_service_quantities": {service.id: str(service.quantity) for service in created_services},
        },
        reason="Role-limited cf-physical-model initial canonical physical-scope submission",
    )
    db.commit()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "openings": [
            {"id": opening.id, "opening_code": opening.opening_code, "canonical_defect_id": opening.canonical_defect_id}
            for opening in opening_by_code.values()
        ],
        "services": [
            {"id": service.id, "service_code": service.service_code, "quantity": str(service.quantity)}
            for service in created_services
        ],
        "service_opening_link_count": len(created_links),
    }


@router.post("/estimates/{estimate_id}/physical-model/lock")
def agent_lock_physical_model(
    estimate_id: str,
    payload: AgentPhysicalModelLockInput,
    db: Db,
    principal: Annotated[
        AgentServicePrincipal, Depends(require_agent_scope("physical:lock"))
    ],
) -> dict[str, Any]:
    estimate = _estimate(db, estimate_id)
    try:
        lock, created = create_physical_model_lock(db, estimate)
    except (WorkflowTransitionError, PhysicalModelLockError) as exc:
        db.rollback()
        blockers = list(exc.blockers) if isinstance(exc, WorkflowTransitionError) else [str(exc)]
        raise HTTPException(
            status_code=409,
            detail={"action": "lock_physical_model", "allowed": False, "blockers": blockers},
        ) from exc

    _agent_audit(
        db,
        principal=principal,
        action="agent_lock_physical_model",
        entity_type="physical_model_lock",
        entity_id=lock.id,
        estimate=estimate,
        new_value={
            "content_hash": lock.content_hash,
            "validator_result": lock.validator_result,
            "opening_ids": lock.opening_ids,
            "service_ids": lock.service_ids,
            "critical_unknowns": lock.critical_unknowns or [],
            "created": created,
        },
        reason=payload.reason,
    )
    if created:
        db.commit()
    else:
        db.rollback()
    return {
        "agent_id": principal.agent_id,
        "estimate_id": estimate.id,
        "lock_id": lock.id,
        "created": created,
        "content_hash": lock.content_hash,
        "validator_result": lock.validator_result,
        "critical_unknowns": lock.critical_unknowns or [],
        "permitted_classes": lock.permitted_classes or [],
    }
