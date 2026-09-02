from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import (
    EstimatingRule,
    LabourComponent,
    MarkupProfile,
    PricingLibraryRecord,
    Product,
)
from .security import verify_csrf
from .services.calculation import D
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _next_pricing_version(db: Session, record: PricingLibraryRecord) -> str:
    count = (
        db.scalar(
            select(func.count())
            .select_from(PricingLibraryRecord)
            .where(PricingLibraryRecord.pkb_entry_id == record.pkb_entry_id)
        )
        or 0
    )
    return f"user-r{count + 1}"


@router.get("/pricing", response_class=HTMLResponse)
def pricing_library(
    request: Request,
    db: Db,
    q: str | None = None,
    status: str | None = None,
) -> HTMLResponse:
    _require(request, db, "library:read")
    stmt = select(PricingLibraryRecord)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                PricingLibraryRecord.pkb_entry_id.ilike(like),
                PricingLibraryRecord.description.ilike(like),
                PricingLibraryRecord.service_type.ilike(like),
                PricingLibraryRecord.service_material.ilike(like),
                PricingLibraryRecord.substrate.ilike(like),
                PricingLibraryRecord.frl.ilike(like),
                PricingLibraryRecord.manufacturer.ilike(like),
            )
        )
    if status:
        stmt = stmt.where(PricingLibraryRecord.status == status)
    records = db.scalars(
        stmt.order_by(
            PricingLibraryRecord.pkb_entry_id, PricingLibraryRecord.created_at.desc()
        ).limit(897)
    ).all()
    return templates.TemplateResponse(
        request,
        "pricing.html",
        _context(request, db, records=records, q=q or "", status=status or ""),
    )


@router.get("/pricing/{record_id}", response_class=HTMLResponse)
def pricing_record_page(record_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    record = db.get(PricingLibraryRecord, record_id)
    if not record:
        raise HTTPException(404, "Pricing record not found")
    history = db.scalars(
        select(PricingLibraryRecord)
        .where(PricingLibraryRecord.pkb_entry_id == record.pkb_entry_id)
        .order_by(PricingLibraryRecord.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "pricing_edit.html",
        _context(request, db, record=record, history=history),
    )


@router.post("/pricing/{record_id}/revision")
def pricing_record_revision(
    record_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    rate_ex_tax: Annotated[str, Form()],
    direct_labour_cost: Annotated[str | None, Form()] = None,
    direct_material_cost: Annotated[str | None, Form()] = None,
    material_markup_percent: Annotated[str | None, Form()] = None,
    effective_date: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Pricing revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    original = db.get(PricingLibraryRecord, record_id)
    if not original:
        raise HTTPException(404, "Pricing record not found")

    revision = PricingLibraryRecord(
        pkb_entry_id=original.pkb_entry_id,
        entry_version=_next_pricing_version(db, original),
        description=original.description,
        system_description=original.system_description,
        unit=original.unit,
        rate_ex_tax=D(rate_ex_tax),
        direct_labour_cost=D(direct_labour_cost) if direct_labour_cost else None,
        direct_material_cost=D(direct_material_cost) if direct_material_cost else None,
        material_markup=(D(material_markup_percent) / Decimal("100"))
        if material_markup_percent
        else None,
        currency=original.currency,
        tax_basis=original.tax_basis,
        service_type=original.service_type,
        service_class=original.service_class,
        service_material=original.service_material,
        substrate=original.substrate,
        substrate_plane=original.substrate_plane,
        orientation=original.orientation,
        frl=original.frl,
        manufacturer=original.manufacturer,
        repair_family=original.repair_family,
        rate_inclusions=original.rate_inclusions,
        rate_exclusions=original.rate_exclusions,
        applicability=original.applicability,
        commercial_confidence=original.commercial_confidence,
        technical_status=original.technical_status,
        status="draft",
        effective_date=_date_or_none(effective_date),
        expiry_date=None,
        source_hash=original.source_hash,
        source_json={
            **(original.source_json or {}),
            "user_revision": True,
            "reason": reason,
            "supersedes_record_id": original.id,
        },
        release_id=None,
        supersedes_id=original.id,
    )
    db.add(revision)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="pricing_library_record",
        entity_id=revision.id,
        previous_value={"record_id": original.id, "rate_ex_tax": str(original.rate_ex_tax)},
        new_value={
            "record_id": revision.id,
            "rate_ex_tax": str(revision.rate_ex_tax),
            "status": "draft",
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/pricing/{revision.id}?success=Draft+revision+created", status_code=303
    )


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
def product_edit_page(product_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Product not found")
    history = db.scalars(
        select(Product).where(Product.sku == product.sku).order_by(Product.revision.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "product_edit.html",
        _context(request, db, product=product, history=history),
    )


@router.post("/products/{product_id}/revision")
def product_revision(
    product_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    name: Annotated[str, Form()],
    category: Annotated[str | None, Form()] = None,
    manufacturer: Annotated[str | None, Form()] = None,
    supplier: Annotated[str | None, Form()] = None,
    unit: Annotated[str, Form()] = "each",
    base_cost: Annotated[str, Form()] = "0",
    default_markup_percent: Annotated[str, Form()] = "30",
    waste_percent: Annotated[str, Form()] = "0",
    pack_size: Annotated[str, Form()] = "1",
    minimum_order_quantity: Annotated[str, Form()] = "1",
    effective_date: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Product/material revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    old = db.get(Product, product_id)
    if not old:
        raise HTTPException(404, "Product not found")
    next_revision = (
        db.scalar(select(func.max(Product.revision)).where(Product.sku == old.sku)) or 0
    ) + 1
    new = Product(
        sku=old.sku,
        revision=next_revision,
        name=name,
        item_type=old.item_type,
        category=category,
        manufacturer=manufacturer,
        supplier=supplier,
        unit=unit,
        pack_size=D(pack_size),
        minimum_order_quantity=D(minimum_order_quantity),
        base_cost=D(base_cost),
        currency=old.currency,
        tax_treatment=old.tax_treatment,
        waste_factor=D(waste_percent) / Decimal("100"),
        default_markup=D(default_markup_percent) / Decimal("100"),
        regional_pricing=old.regional_pricing,
        source_reference=old.source_reference,
        supporting_attachment_id=old.supporting_attachment_id,
        effective_date=_date_or_none(effective_date),
        expiry_date=None,
        status="draft",
        notes=old.notes,
        source_json={**(old.source_json or {}), "user_revision": True, "reason": reason},
        release_id=None,
        supersedes_id=old.id,
    )
    db.add(new)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="product",
        entity_id=new.id,
        previous_value={"id": old.id, "revision": old.revision, "base_cost": str(old.base_cost)},
        new_value={
            "id": new.id,
            "revision": new.revision,
            "base_cost": str(new.base_cost),
            "status": "draft",
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/products/{new.id}/edit?success=Draft+revision+created", status_code=303
    )


@router.get("/labour/{labour_id}/edit", response_class=HTMLResponse)
def labour_edit_page(labour_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    item = db.get(LabourComponent, labour_id)
    if not item:
        raise HTTPException(404, "Labour component not found")
    history = db.scalars(
        select(LabourComponent)
        .where(LabourComponent.code == item.code)
        .order_by(LabourComponent.revision.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "labour_edit.html",
        _context(request, db, item=item, history=history),
    )


@router.post("/labour/{labour_id}/revision")
def labour_revision(
    labour_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    name: Annotated[str, Form()],
    trade_or_grade: Annotated[str | None, Form()] = None,
    category: Annotated[str | None, Form()] = None,
    base_rate: Annotated[str, Form()] = "0",
    default_hours: Annotated[str, Form()] = "1",
    crew_size: Annotated[str, Form()] = "1",
    default_markup_percent: Annotated[str, Form()] = "0",
    productivity_source: Annotated[str | None, Form()] = None,
    effective_date: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Labour revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    old = db.get(LabourComponent, labour_id)
    if not old:
        raise HTTPException(404, "Labour component not found")
    next_revision = (
        db.scalar(
            select(func.max(LabourComponent.revision)).where(LabourComponent.code == old.code)
        )
        or 0
    ) + 1
    new = LabourComponent(
        code=old.code,
        revision=next_revision,
        name=name,
        trade_or_grade=trade_or_grade,
        category=category,
        unit=old.unit,
        base_rate=D(base_rate),
        default_hours=D(default_hours),
        crew_size=D(crew_size),
        default_markup=D(default_markup_percent) / Decimal("100"),
        productivity_source=productivity_source,
        effective_date=_date_or_none(effective_date),
        expiry_date=None,
        status="draft",
        notes=old.notes,
        release_id=None,
        supersedes_id=old.id,
    )
    db.add(new)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="labour_component",
        entity_id=new.id,
        previous_value={"id": old.id, "revision": old.revision, "base_rate": str(old.base_rate)},
        new_value={
            "id": new.id,
            "revision": new.revision,
            "base_rate": str(new.base_rate),
            "status": "draft",
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/labour/{new.id}/edit?success=Draft+revision+created", status_code=303
    )


@router.get("/rules/{rule_id}/edit", response_class=HTMLResponse)
def rule_edit_page(rule_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "rule:read")
    rule = db.get(EstimatingRule, rule_id)
    if not rule:
        raise HTTPException(404, "Rule not found")
    history = db.scalars(
        select(EstimatingRule)
        .where(EstimatingRule.rule_code == rule.rule_code)
        .order_by(EstimatingRule.version.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "rule_edit.html",
        _context(
            request,
            db,
            rule=rule,
            history=history,
            conditions_json=json.dumps(rule.conditions, indent=2),
            actions_json=json.dumps(rule.actions, indent=2),
        ),
    )


@router.post("/rules/{rule_id}/revision")
def rule_revision(
    rule_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    name: Annotated[str, Form()],
    category: Annotated[str, Form()],
    description: Annotated[str, Form()],
    severity: Annotated[str, Form()],
    conditions_json: Annotated[str, Form()],
    actions_json: Annotated[str, Form()],
    priority: Annotated[int, Form()] = 100,
    source_reference: Annotated[str | None, Form()] = None,
    source_page: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Rule revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "rule:write")
    old = db.get(EstimatingRule, rule_id)
    if not old:
        raise HTTPException(404, "Rule not found")
    try:
        conditions = json.loads(conditions_json)
        actions = json.loads(actions_json)
    except json.JSONDecodeError:
        return RedirectResponse(
            f"/rules/{rule_id}/edit?error=Conditions+and+actions+must+be+valid+JSON",
            status_code=303,
        )
    next_version = (
        db.scalar(
            select(func.max(EstimatingRule.version)).where(
                EstimatingRule.rule_code == old.rule_code
            )
        )
        or 0
    ) + 1
    new = EstimatingRule(
        rule_code=old.rule_code,
        version=next_version,
        name=name,
        category=category,
        description=description,
        conditions=conditions,
        actions=actions,
        severity=severity,
        jurisdiction=old.jurisdiction,
        source_reference=source_reference,
        source_page=source_page,
        priority=priority,
        conflict_resolution=old.conflict_resolution,
        status="draft",
        effective_date=None,
        expiry_date=None,
        test_cases=old.test_cases,
        author_id=user.id,
        reviewer_id=None,
        approver_id=None,
        approved_at=None,
        release_id=None,
        supersedes_id=old.id,
    )
    db.add(new)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="estimating_rule",
        entity_id=new.id,
        previous_value={"id": old.id, "version": old.version},
        new_value={"id": new.id, "version": new.version, "status": "draft"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(f"/rules/{new.id}/edit?success=Draft+revision+created", status_code=303)


@router.get("/markups", response_class=HTMLResponse)
def markup_settings(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    profiles = db.scalars(select(MarkupProfile).order_by(MarkupProfile.created_at.desc())).all()
    active_global = db.scalar(
        select(MarkupProfile)
        .where(MarkupProfile.scope_type == "global", MarkupProfile.status == "active")
        .order_by(MarkupProfile.created_at.desc())
    )
    return templates.TemplateResponse(
        request,
        "markups.html",
        _context(request, db, profiles=profiles, active_global=active_global),
    )


@router.post("/markups/global")
def markup_settings_revision(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    product_markup_percent: Annotated[str, Form()],
    material_markup_percent: Annotated[str, Form()],
    labour_markup_percent: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Global markup revision",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    old_profiles = db.scalars(
        select(MarkupProfile).where(
            MarkupProfile.scope_type == "global",
            MarkupProfile.status == "active",
        )
    ).all()
    for old in old_profiles:
        old.status = "superseded"
    new = MarkupProfile(
        name=f"Global markups {date.today().isoformat()}",
        scope_type="global",
        scope_id=None,
        product_markup=D(product_markup_percent) / Decimal("100"),
        material_markup=D(material_markup_percent) / Decimal("100"),
        labour_markup=D(labour_markup_percent) / Decimal("100"),
        status="active",
        effective_date=date.today(),
        created_by_id=user.id,
        approved_by_id=user.id,
    )
    db.add(new)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="revise",
        entity_type="markup_profile",
        entity_id=new.id,
        previous_value={"active_profiles": [p.id for p in old_profiles]},
        new_value={
            "product_markup": str(new.product_markup),
            "material_markup": str(new.material_markup),
            "labour_markup": str(new.labour_markup),
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse("/markups?success=Global+markup+settings+updated", status_code=303)
