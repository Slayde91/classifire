from __future__ import annotations

import copy
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .config import Settings, get_settings
from .db import get_db
from .models import Approval, StoredFile, TechnicalDocument, TechnicalVariant
from .security import verify_csrf
from .services.calculation import D
from .services.storage import StoredFileSecurityError, require_clean_stored_file
from .services.technical import governed_unlinked_technical_source
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    return D(value)


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _require_clean_technical_source(
    db: Session,
    settings: Settings,
    document: TechnicalDocument,
    *,
    require_approved: bool,
    error_code: str,
) -> StoredFile:
    if require_approved and document.status != "approved":
        raise HTTPException(409, error_code)
    stored = db.get(StoredFile, document.stored_file_id)
    if stored is None:
        raise HTTPException(409, error_code)
    try:
        require_clean_stored_file(
            settings.storage_root,
            stored,
            allowed_purposes={"technical_evidence"},
        )
    except StoredFileSecurityError:
        raise HTTPException(409, error_code) from None
    return stored


def _next_revision_id(db: Session, original: TechnicalVariant) -> str:
    base = original.variant_id.split("-QFREV")[0]
    existing = db.scalars(
        select(TechnicalVariant.variant_id).where(TechnicalVariant.variant_id.like(f"{base}-QFREV%"))
    ).all()
    numbers: list[int] = []
    for item in existing:
        try:
            numbers.append(int(item.rsplit("QFREV", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{base}-QFREV{(max(numbers) if numbers else 0) + 1:02d}"


def _json_or_existing(value: str | None, existing: Any) -> Any:
    if value is None or value.strip() == "":
        return copy.deepcopy(existing)
    return json.loads(value)


@router.get("/technical/variants", response_class=HTMLResponse)
def technical_variants_manager(
    request: Request,
    db: Db,
    q: str | None = None,
    status: str | None = None,
) -> HTMLResponse:
    _require(request, db, "technical:read")
    stmt = select(TechnicalVariant)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                TechnicalVariant.variant_id.ilike(like),
                TechnicalVariant.system_id.ilike(like),
                TechnicalVariant.product_family.ilike(like),
                TechnicalVariant.service_type.ilike(like),
                TechnicalVariant.service_material.ilike(like),
                TechnicalVariant.substrate_type.ilike(like),
                TechnicalVariant.frl.ilike(like),
                TechnicalVariant.source_document_reference.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(TechnicalVariant.status == status)
    variants = db.scalars(stmt.order_by(TechnicalVariant.variant_id).limit(500)).all()
    counts = dict(
        db.execute(
            select(TechnicalVariant.status, func.count())
            .group_by(TechnicalVariant.status)
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "technical_variants_manager.html",
        _context(request, db, variants=variants, q=q or "", status=status or "", counts=counts),
    )


@router.get("/technical/variants/{variant_db_id}", response_class=HTMLResponse)
def technical_variant_detail(variant_db_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "technical:read")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    root_id = (variant.source_json or {}).get("original_variant_id") or variant.variant_id.split("-QFREV")[0]
    history = db.scalars(
        select(TechnicalVariant)
        .where(
            or_(
                TechnicalVariant.variant_id == root_id,
                TechnicalVariant.variant_id.like(f"{root_id}-QFREV%"),
            )
        )
        .order_by(TechnicalVariant.created_at.desc())
    ).all()
    approvals = db.scalars(
        select(Approval)
        .where(Approval.entity_type == "technical_variant", Approval.entity_id == variant.id)
        .order_by(Approval.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "technical_variant_detail.html",
        _context(request, db, variant=variant, history=history, approvals=approvals),
    )


@router.get("/technical/variants/{variant_db_id}/revise", response_class=HTMLResponse)
def technical_variant_revision_page(variant_db_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "technical:write")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    return templates.TemplateResponse(
        request,
        "technical_variant_edit.html",
        _context(
            request,
            db,
            variant=variant,
            component_json=json.dumps(variant.component_requirements, indent=2, ensure_ascii=False) if variant.component_requirements is not None else "",
            labour_json=json.dumps(variant.labour_requirements, indent=2, ensure_ascii=False) if variant.labour_requirements is not None else "",
        ),
    )


@router.post("/technical/variants/{variant_db_id}/revision")
def technical_variant_revision(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    manufacturer: Annotated[str | None, Form()] = None,
    product_family: Annotated[str | None, Form()] = None,
    service_type: Annotated[str | None, Form()] = None,
    service_material: Annotated[str | None, Form()] = None,
    minimum_service_size_mm: Annotated[str | None, Form()] = None,
    maximum_service_size_mm: Annotated[str | None, Form()] = None,
    substrate_type: Annotated[str | None, Form()] = None,
    minimum_substrate_thickness_mm: Annotated[str | None, Form()] = None,
    maximum_substrate_thickness_mm: Annotated[str | None, Form()] = None,
    orientation: Annotated[str | None, Form()] = None,
    opening_type: Annotated[str | None, Form()] = None,
    opening_dimensions: Annotated[str | None, Form()] = None,
    annular_gap_min_mm: Annotated[str | None, Form()] = None,
    annular_gap_max_mm: Annotated[str | None, Form()] = None,
    service_spacing_rules: Annotated[str | None, Form()] = None,
    edge_distance_rules: Annotated[str | None, Form()] = None,
    support_rules: Annotated[str | None, Form()] = None,
    fixing_rules: Annotated[str | None, Form()] = None,
    frl: Annotated[str | None, Form()] = None,
    jurisdiction: Annotated[str | None, Form()] = None,
    search_eligibility: Annotated[str | None, Form()] = None,
    component_requirements_json: Annotated[str | None, Form()] = None,
    labour_requirements_json: Annotated[str | None, Form()] = None,
    hard_exclusions: Annotated[str | None, Form()] = None,
    dependencies: Annotated[str | None, Form()] = None,
    source_document_reference: Annotated[str | None, Form()] = None,
    source_page: Annotated[str | None, Form()] = None,
    source_table: Annotated[str | None, Form()] = None,
    source_figure: Annotated[str | None, Form()] = None,
    effective_date: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Technical variant revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    old = db.get(TechnicalVariant, variant_db_id)
    if not old:
        raise HTTPException(404, "Technical variant not found")
    try:
        component_requirements = _json_or_existing(component_requirements_json, old.component_requirements)
        labour_requirements = _json_or_existing(labour_requirements_json, old.labour_requirements)
    except json.JSONDecodeError:
        return RedirectResponse(f"/technical/variants/{variant_db_id}/revise?error=Component+and+labour+requirements+must+be+valid+JSON", status_code=303)

    new_variant_id = _next_revision_id(db, old)
    source_json = copy.deepcopy(old.source_json or {})
    source_json.update(
        {
            "original_variant_id": (old.source_json or {}).get("original_variant_id") or old.variant_id.split("-QFREV")[0],
            "user_revision": True,
            "revision_reason": reason,
            "supersedes_record_id": old.id,
            "source_authority_preserved": True,
        }
    )
    new = TechnicalVariant(
        variant_id=new_variant_id,
        system_id=old.system_id,
        technical_document_id=old.technical_document_id,
        source_document_reference=source_document_reference,
        source_page=source_page,
        source_table=source_table,
        source_figure=source_figure,
        manufacturer=manufacturer,
        product_family=product_family,
        service_type=service_type,
        service_material=service_material,
        minimum_service_size_mm=_decimal_or_none(minimum_service_size_mm),
        maximum_service_size_mm=_decimal_or_none(maximum_service_size_mm),
        permitted_service_quantity=old.permitted_service_quantity,
        insulation_type=old.insulation_type,
        insulation_thickness_mm=old.insulation_thickness_mm,
        substrate_type=substrate_type,
        minimum_substrate_thickness_mm=_decimal_or_none(minimum_substrate_thickness_mm),
        maximum_substrate_thickness_mm=_decimal_or_none(maximum_substrate_thickness_mm),
        orientation=orientation,
        installation_face=old.installation_face,
        opening_type=opening_type,
        opening_dimensions=opening_dimensions,
        annular_gap_min_mm=_decimal_or_none(annular_gap_min_mm),
        annular_gap_max_mm=_decimal_or_none(annular_gap_max_mm),
        service_spacing_rules=service_spacing_rules,
        edge_distance_rules=edge_distance_rules,
        support_rules=support_rules,
        fixing_rules=fixing_rules,
        component_requirements=component_requirements,
        labour_requirements=labour_requirements,
        hard_exclusions=hard_exclusions,
        dependencies=dependencies,
        frl=frl,
        jurisdiction=jurisdiction,
        quality_score=old.quality_score,
        confidence_cap=old.confidence_cap,
        search_eligibility=search_eligibility,
        expert_review_required=True,
        status="draft",
        effective_date=_date_or_none(effective_date),
        expiry_date=None,
        source_hash=old.source_hash,
        source_json=source_json,
        release_id=None,
        supersedes_id=old.id,
    )
    db.add(new)
    db.flush()
    approval = Approval(
        entity_type="technical_variant",
        entity_id=new.id,
        approval_type="technical_activation",
        status="pending",
        requested_by_id=user.id,
        decision_reason="Draft technical revision requires authorised technical review before activation.",
    )
    db.add(approval)
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="technical_variant",
        entity_id=new.id,
        previous_value={"id": old.id, "variant_id": old.variant_id, "status": old.status},
        new_value={"id": new.id, "variant_id": new.variant_id, "status": "draft"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(f"/technical/variants/{new.id}?success=Draft+technical+revision+created", status_code=303)


@router.post("/technical/variants/{variant_db_id}/submit-review")
def technical_variant_submit_review(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Submit technical variant for review",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    if variant.status not in {"draft", "rejected"}:
        return RedirectResponse(f"/technical/variants/{variant.id}?error=Only+Draft+or+Rejected+variants+can+be+submitted", status_code=303)
    variant.status = "in_review"
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
            Approval.approval_type == "technical_activation",
        )
        .order_by(Approval.created_at.desc())
    )
    if approval:
        approval.status = "pending"
        approval.requested_by_id = user.id
        approval.requested_at = datetime.now(timezone.utc)
        approval.decision_reason = reason
    else:
        db.add(Approval(entity_type="technical_variant", entity_id=variant.id, approval_type="technical_activation", status="pending", requested_by_id=user.id, decision_reason=reason))
    record_audit(db, actor=user, action="submit_review", entity_type="technical_variant", entity_id=variant.id, previous_value={"status": "draft"}, new_value={"status": "in_review"}, reason=reason)
    db.commit()
    return RedirectResponse(f"/technical/variants/{variant.id}?success=Submitted+for+technical+review", status_code=303)


@router.post("/technical/variants/{variant_db_id}/approve")
def technical_variant_approve(
    variant_db_id: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Technical review completed and approved",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    if variant.status not in {"draft", "in_review"}:
        return RedirectResponse(f"/technical/variants/{variant.id}?error=Only+Draft+or+In+Review+variants+can+be+approved", status_code=303)
    if not variant.source_document_reference or not variant.source_page:
        return RedirectResponse(f"/technical/variants/{variant.id}?error=Source+document+reference+and+source+page+are+required+before+approval", status_code=303)
    if variant.technical_document_id is None:
        if not governed_unlinked_technical_source(db, variant):
            raise HTTPException(409, "TECHNICAL_VARIANT_SOURCE_NOT_APPROVED_OR_CLEAN")
    else:
        source_document = db.get(TechnicalDocument, variant.technical_document_id)
        if source_document is None:
            raise HTTPException(409, "TECHNICAL_VARIANT_SOURCE_NOT_APPROVED_OR_CLEAN")
        _require_clean_technical_source(
            db,
            settings,
            source_document,
            require_approved=True,
            error_code="TECHNICAL_VARIANT_SOURCE_NOT_APPROVED_OR_CLEAN",
        )
    previous_status = variant.status
    if variant.supersedes_id:
        prior = db.get(TechnicalVariant, variant.supersedes_id)
        if prior and prior.status == "active":
            prior.status = "superseded"
    variant.status = "active"
    variant.expert_review_required = False
    variant.effective_date = variant.effective_date or date.today()
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
            Approval.approval_type == "technical_activation",
        )
        .order_by(Approval.created_at.desc())
    )
    if approval:
        approval.status = "approved"
        approval.decided_by_id = user.id
        approval.decided_at = datetime.now(timezone.utc)
        approval.decision_reason = reason
    else:
        db.add(Approval(entity_type="technical_variant", entity_id=variant.id, approval_type="technical_activation", status="approved", requested_by_id=user.id, decided_by_id=user.id, decided_at=datetime.now(timezone.utc), decision_reason=reason))
    record_audit(db, actor=user, action="approve", entity_type="technical_variant", entity_id=variant.id, previous_value={"status": previous_status}, new_value={"status": "active"}, reason=reason)
    db.commit()
    return RedirectResponse(f"/technical/variants/{variant.id}?success=Technical+variant+approved+and+activated", status_code=303)


@router.post("/technical/variants/{variant_db_id}/reject")
def technical_variant_reject(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    previous = variant.status
    variant.status = "rejected"
    approval = db.scalar(select(Approval).where(Approval.entity_type == "technical_variant", Approval.entity_id == variant.id, Approval.approval_type == "technical_activation").order_by(Approval.created_at.desc()))
    if approval:
        approval.status = "rejected"
        approval.decided_by_id = user.id
        approval.decided_at = datetime.now(timezone.utc)
        approval.decision_reason = reason
    record_audit(db, actor=user, action="reject", entity_type="technical_variant", entity_id=variant.id, previous_value={"status": previous}, new_value={"status": "rejected"}, reason=reason)
    db.commit()
    return RedirectResponse(f"/technical/variants/{variant.id}?success=Technical+variant+rejected", status_code=303)


@router.post("/technical/variants/{variant_db_id}/retire")
def technical_variant_retire(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    previous = variant.status
    variant.status = "retired"
    variant.expiry_date = date.today()
    record_audit(db, actor=user, action="retire", entity_type="technical_variant", entity_id=variant.id, previous_value={"status": previous}, new_value={"status": "retired"}, reason=reason)
    db.commit()
    return RedirectResponse(f"/technical/variants/{variant.id}?success=Technical+variant+retired", status_code=303)


@router.get("/technical/documents/{document_db_id}", response_class=HTMLResponse)
def technical_document_detail(document_db_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "technical:read")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    linked = db.scalars(select(TechnicalVariant).where(TechnicalVariant.technical_document_id == document.id).order_by(TechnicalVariant.variant_id)).all()
    return templates.TemplateResponse(request, "technical_document_detail.html", _context(request, db, document=document, linked=linked))


@router.post("/technical/documents/{document_db_id}/approve")
def technical_document_approve(
    document_db_id: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Technical source document reviewed",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    _require_clean_technical_source(
        db,
        settings,
        document,
        require_approved=False,
        error_code="TECHNICAL_DOCUMENT_STORED_FILE_NOT_CLEAN",
    )
    previous = document.status
    document.status = "approved"
    document.reviewed_by_id = user.id
    document.approved_by_id = user.id
    document.approved_at = datetime.now(timezone.utc)
    record_audit(db, actor=user, action="approve", entity_type="technical_document", entity_id=document.id, previous_value={"status": previous}, new_value={"status": "approved"}, reason=reason)
    db.commit()
    return RedirectResponse(f"/technical/documents/{document.id}?success=Technical+source+document+approved", status_code=303)
