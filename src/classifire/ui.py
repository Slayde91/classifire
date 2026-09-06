from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .audit import record_audit
from .config import Settings, get_settings
from .db import get_db
from .models import (
    AuditEvent,
    ChangeProposal,
    Estimate,
    EstimateLine,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    Opening,
    PricingLibraryRecord,
    Product,
    Project,
    RuleEvaluation,
    Service,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from .outputs.common import ATTRIBUTION
from .outputs.draft_scope import _page_reference_fields
from .physical_models import ServiceOpeningLink
from .security import (
    authenticate_user,
    create_csrf_token,
    has_permission,
    resolve_session_user,
    verify_csrf,
)
from .services.calculation import D, calculate_estimate_line, recalculate_estimate
from .services.draft_scope_evidence import reference_label, reference_status
from .services.initial_canonicalisation_boundary import (
    InitialCanonicalisationAdmissionRequired,
    require_admission_bound_initial_canonicalisation,
)
from .services.physical_defects import bind_canonical_defect
from .services.physical_mutation_guard import PhysicalMutationError, require_physical_model_mutation
from .services.release_pinning import (
    pin_current_releases,
    release_basis_for_estimate,
    validate_estimate_release_basis,
)
from .services.rule_engine import evaluate_estimate_rules
from .services.snapshot import lock_snapshot
from .services.storage import StoredFileBindingError, read_verified_stored_file, save_upload
from .services.technical import (
    build_technical_document_draft_metadata_from_verified_content,
    build_technical_document_extraction_deferred_metadata,
)
from .services.technical_document_lineage import (
    TechnicalDocumentLineageError,
    prepare_technical_document_supersession,
)
from .services.workflow import WorkflowTransitionError
from .services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
# Pure saved-claim display, shared by report/import/client review templates.
templates.env.globals.update(
    scope_reference_label=reference_label,
    scope_reference_status=reference_status,
    scope_reference_fields=_page_reference_fields,
)
Db = Annotated[Session, Depends(get_db)]


def _user(request: Request, db: Session) -> User | None:
    return resolve_session_user(request, db)


def _require(request: Request, db: Session, permission: str) -> User:
    user = _user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    if not has_permission(user, permission):
        raise HTTPException(status_code=403, detail="Permission denied")
    return user


def _context(request: Request, db: Session, **values: Any) -> dict[str, Any]:
    user = _user(request, db)
    return {
        "request": request,
        "user": user,
        "csrf_token": create_csrf_token(request),
        "attribution": ATTRIBUTION,
        "has_permission": lambda permission: bool(user and has_permission(user, permission)),
        **values,
    }


def _review_return_path(value: str | None) -> str:
    prefix = "/client-requests/"
    if value and value.startswith(prefix):
        identifier = value[len(prefix):]
        try:
            if str(UUID(identifier)) == identifier:
                return value
        except ValueError:
            pass
    return "/"


@router.get("/login", response_class=HTMLResponse, response_model=None)
def login_page(
    request: Request, db: Db, error: str | None = None
) -> HTMLResponse | RedirectResponse:
    return_to = _review_return_path(request.query_params.get("next"))
    if _user(request, db):
        return RedirectResponse(return_to, status_code=303)
    return templates.TemplateResponse(
        request, "login.html", _context(request, db, error=error, return_to=return_to)
    )


@router.post("/login")
def login_submit(
    request: Request,
    db: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
    return_to: Annotated[str, Form()] = "/",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    return_to = _review_return_path(return_to)
    user = authenticate_user(db, email, password)
    if not user:
        return RedirectResponse(
            "/login?error=Invalid+email+or+password&next=" + return_to, status_code=303
        )
    request.session.clear()
    request.session["user_id"] = user.id
    create_csrf_token(request)
    return RedirectResponse(return_to, status_code=303)


@router.post("/logout")
def logout(request: Request, csrf_token: Annotated[str, Form()]) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "project:read")
    counts = {
        "projects": db.scalar(select(func.count()).select_from(Project)) or 0,
        "estimates": db.scalar(select(func.count()).select_from(Estimate)) or 0,
        "products": db.scalar(select(func.count()).select_from(Product)) or 0,
        "pricing_records": db.scalar(select(func.count()).select_from(PricingLibraryRecord)) or 0,
        "technical_variants": db.scalar(select(func.count()).select_from(TechnicalVariant)) or 0,
        "rules": db.scalar(select(func.count()).select_from(EstimatingRule)) or 0,
    }
    recent_estimates = db.scalars(
        select(Estimate)
        .options(selectinload(Estimate.project))
        .order_by(Estimate.updated_at.desc())
        .limit(8)
    ).all()
    releases = db.scalars(
        select(LibraryRelease).order_by(LibraryRelease.created_at.desc()).limit(12)
    ).all()
    open_changes = db.scalars(
        select(ChangeProposal)
        .where(ChangeProposal.status.in_(["draft", "in_review"]))
        .order_by(ChangeProposal.updated_at.desc())
        .limit(8)
    ).all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        _context(
            request,
            db,
            counts=counts,
            recent_estimates=recent_estimates,
            releases=releases,
            open_changes=open_changes,
        ),
    )


@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request, db: Db, q: str | None = None) -> HTMLResponse:
    _require(request, db, "library:read")
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%") | Product.sku.ilike(f"%{q}%"))
    products = db.scalars(stmt.order_by(Product.name).limit(500)).all()
    return templates.TemplateResponse(
        request, "products.html", _context(request, db, products=products, q=q or "")
    )


@router.post("/products")
def products_create(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    sku: Annotated[str, Form()],
    name: Annotated[str, Form()],
    item_type: Annotated[str, Form()],
    category: Annotated[str | None, Form()] = None,
    unit: Annotated[str, Form()] = "each",
    base_cost: Annotated[str, Form()] = "0",
    default_markup_percent: Annotated[str, Form()] = "30",
    reason: Annotated[str, Form()] = "New library item",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    if db.scalar(select(Product.id).where(Product.sku == sku, Product.revision == 1)):
        return RedirectResponse("/products?error=SKU+already+exists", status_code=303)
    product = Product(
        sku=sku,
        revision=1,
        name=name,
        item_type=item_type,
        category=category,
        unit=unit,
        base_cost=D(base_cost),
        default_markup=D(default_markup_percent) / Decimal("100"),
        currency="AUD",
        status="draft",
        effective_date=date.today(),
    )
    db.add(product)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="product",
        entity_id=product.id,
        new_value={"sku": sku, "name": name},
        reason=reason,
    )
    db.commit()
    return RedirectResponse("/products", status_code=303)


@router.get("/labour", response_class=HTMLResponse)
def labour_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    labour = db.scalars(select(LabourComponent).order_by(LabourComponent.name).limit(500)).all()
    return templates.TemplateResponse(request, "labour.html", _context(request, db, labour=labour))


@router.post("/labour")
def labour_create(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    code: Annotated[str, Form()],
    name: Annotated[str, Form()],
    base_rate: Annotated[str, Form()],
    default_markup_percent: Annotated[str, Form()] = "0",
    category: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "New labour component",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "pricing:write")
    component = LabourComponent(
        code=code,
        revision=1,
        name=name,
        category=category,
        unit="person_hour",
        base_rate=D(base_rate),
        default_markup=D(default_markup_percent) / Decimal("100"),
        status="draft",
        effective_date=date.today(),
    )
    db.add(component)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="labour_component",
        entity_id=component.id,
        new_value={"code": code, "name": name},
        reason=reason,
    )
    db.commit()
    return RedirectResponse("/labour", status_code=303)


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "rule:read")
    rules = db.scalars(
        select(EstimatingRule).order_by(EstimatingRule.priority, EstimatingRule.rule_code)
    ).all()
    return templates.TemplateResponse(request, "rules.html", _context(request, db, rules=rules))


@router.post("/rules")
def rule_create(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    rule_code: Annotated[str, Form()],
    name: Annotated[str, Form()],
    category: Annotated[str, Form()],
    description: Annotated[str, Form()],
    severity: Annotated[str, Form()],
    conditions_json: Annotated[str, Form()],
    actions_json: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "User-suggested estimating rule",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "rule:write")
    try:
        conditions = json.loads(conditions_json)
        actions = json.loads(actions_json)
    except json.JSONDecodeError:
        return RedirectResponse(
            "/rules?error=Conditions+and+actions+must+be+valid+JSON", status_code=303
        )
    version = (
        db.scalar(
            select(func.max(EstimatingRule.version)).where(EstimatingRule.rule_code == rule_code)
        )
        or 0
    ) + 1
    rule = EstimatingRule(
        rule_code=rule_code,
        version=version,
        name=name,
        category=category,
        description=description,
        conditions=conditions,
        actions=actions,
        severity=severity,
        jurisdiction=get_settings().jurisdiction,
        status="draft",
        priority=100,
        author_id=user.id,
    )
    db.add(rule)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create_revision",
        entity_type="estimating_rule",
        entity_id=rule.id,
        new_value={"rule_code": rule_code, "version": version},
        reason=reason,
    )
    db.commit()
    return RedirectResponse("/rules", status_code=303)


@router.get("/technical", response_class=HTMLResponse)
def technical_page(request: Request, db: Db, q: str | None = None) -> HTMLResponse:
    _require(request, db, "technical:read")
    docs = db.scalars(
        select(TechnicalDocument).order_by(TechnicalDocument.updated_at.desc()).limit(100)
    ).all()
    approved_documents = [document for document in docs if document.status == "approved"]
    stmt = select(TechnicalVariant)
    if q:
        stmt = stmt.where(
            TechnicalVariant.variant_id.ilike(f"%{q}%")
            | TechnicalVariant.product_family.ilike(f"%{q}%")
            | TechnicalVariant.service_type.ilike(f"%{q}%")
        )
    variants = db.scalars(stmt.order_by(TechnicalVariant.variant_id).limit(200)).all()
    return templates.TemplateResponse(
        request,
        "technical.html",
        _context(
            request,
            db,
            documents=docs,
            approved_documents=approved_documents,
            variants=variants,
            q=q or "",
        ),
    )


@router.post("/technical/upload")
def technical_upload(
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    csrf_token: Annotated[str, Form()],
    file: UploadFile,
    document_id: Annotated[str, Form()],
    document_type: Annotated[str, Form()],
    title: Annotated[str, Form()],
    manufacturer: Annotated[str | None, Form()] = None,
    reference: Annotated[str | None, Form()] = None,
    revision: Annotated[str | None, Form()] = None,
    supersedes_document_id: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    try:
        supersedes_document_id, source_lineage_json, source_lineage_sha256 = (
            prepare_technical_document_supersession(
                db,
                supersedes_document_id=supersedes_document_id,
                storage_root=settings.storage_root,
            )
        )
    except TechnicalDocumentLineageError as exc:
        return RedirectResponse(f"/technical?error={str(exc)}", status_code=303)
    try:
        stored = save_upload(db, settings, file, purpose="technical_evidence", user=user)
    except ValueError as exc:
        return RedirectResponse(f"/technical?error={str(exc).replace(' ', '+')}", status_code=303)
    try:
        verified = read_verified_stored_file(
            stored,
            storage_root=settings.storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError:
        metadata = build_technical_document_extraction_deferred_metadata()
    else:
        metadata = build_technical_document_draft_metadata_from_verified_content(
            content=verified.content,
            filename=stored.original_filename,
        )
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type=document_type,
        manufacturer=manufacturer,
        title=title,
        reference=reference,
        revision=revision,
        jurisdiction=settings.jurisdiction,
        status="draft",
        extraction_status=metadata.get("extraction_status", "not_started"),
        metadata_json=metadata,
        supersedes_document_id=supersedes_document_id,
        source_lineage_json=source_lineage_json,
        source_lineage_sha256=source_lineage_sha256,
    )
    db.add(document)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="upload",
        entity_type="technical_document",
        entity_id=document.id,
        new_value={
            "document_id": document_id,
            "sha256": stored.sha256,
            "status": "draft",
            "supersedes_document_id": supersedes_document_id,
            "source_lineage_sha256": source_lineage_sha256,
        },
        reason="Immutable evidence uploaded; extraction remains Draft",
    )
    db.commit()
    return RedirectResponse("/technical", status_code=303)


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "project:read")
    projects = db.scalars(
        select(Project).options(selectinload(Project.estimates)).order_by(Project.updated_at.desc())
    ).all()
    return templates.TemplateResponse(
        request, "projects.html", _context(request, db, projects=projects)
    )


@router.post("/projects")
def project_create(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reference: Annotated[str, Form()],
    name: Annotated[str, Form()],
    site_address: Annotated[str | None, Form()] = None,
    jurisdiction: Annotated[str, Form()] = "NSW/ACT, Australia",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "project:write")
    project = Project(
        reference=reference, name=name, site_address=site_address, jurisdiction=jurisdiction
    )
    db.add(project)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        new_value={"reference": reference, "name": name},
    )
    db.commit()
    return RedirectResponse("/projects", status_code=303)


@router.post("/projects/{project_id}/estimates")
def estimate_create(
    project_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reference: Annotated[str, Form()],
    title: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    revision = (
        db.scalar(select(func.max(Estimate.revision)).where(Estimate.project_id == project.id)) or 0
    ) + 1
    estimate = Estimate(
        project_id=project.id,
        revision=revision,
        reference=reference,
        title=title,
        status="draft",
        currency=get_settings().currency,
        tax_name=get_settings().tax_name,
        tax_rate=D(get_settings().tax_rate),
    )
    db.add(estimate)
    db.flush()
    try:
        pin_current_releases(db, estimate)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(
            f"/projects?error={str(exc).replace(chr(32), chr(43))}", status_code=303
        )
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=project.id,
        new_value={"reference": reference, "revision": revision},
    )
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


def _estimate(db: Session, estimate_id: str) -> Estimate:
    item = db.scalar(
        select(Estimate)
        .where(Estimate.id == estimate_id)
        .options(
            selectinload(Estimate.project),
            selectinload(Estimate.openings).selectinload(Opening.services),
            selectinload(Estimate.lines),
        )
    )
    if not item:
        raise HTTPException(404, "Estimate not found")
    return item


@router.get("/estimates/{estimate_id}", response_class=HTMLResponse)
def estimate_page(estimate_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "estimate:read")
    estimate = _estimate(db, estimate_id)
    evaluations = db.scalars(
        select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)
    ).all()
    release_basis = release_basis_for_estimate(db, estimate)
    return templates.TemplateResponse(
        request,
        "estimate.html",
        _context(
            request, db, estimate=estimate, evaluations=evaluations, release_basis=release_basis
        ),
    )


@router.post("/estimates/{estimate_id}/openings")
def estimate_add_opening(
    estimate_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    opening_code: Annotated[str, Form()],
    settings: Settings = Depends(get_settings),
    defect_id: Annotated[str | None, Form()] = None,
    location: Annotated[str | None, Form()] = None,
    substrate_type: Annotated[str | None, Form()] = None,
    substrate_plane: Annotated[str | None, Form()] = None,
    orientation: Annotated[str | None, Form()] = None,
    frl: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    if not isinstance(settings, Settings):
        settings = get_settings()
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    estimate = _estimate(db, estimate_id)
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(409, "Locked or released estimates cannot be modified")
    try:
        require_physical_model_mutation(db, estimate)
        require_admission_bound_initial_canonicalisation(
            db,
            estimate_id=estimate.id,
            enabled=settings.adjudicated_initial_submission_enabled,
        )
    except InitialCanonicalisationAdmissionRequired as exc:
        raise HTTPException(409, "Initial physical model requires signed admission.") from exc
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise HTTPException(409, str(exc)) from exc
    defect = bind_canonical_defect(db, estimate, defect_id)
    opening = Opening(
        estimate_id=estimate.id,
        opening_code=opening_code,
        defect_id=defect_id,
        canonical_defect_id=defect.id if defect else None,
        location=location,
        substrate_type=substrate_type,
        substrate_plane=substrate_plane,
        orientation=orientation,
        frl=frl,
    )
    db.add(opening)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="opening",
        entity_id=opening.id,
        project_id=estimate.project_id,
        new_value={"opening_code": opening_code},
    )
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.post("/openings/{opening_id}/services")
def opening_add_service(
    opening_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    service_code: Annotated[str, Form()],
    service_type: Annotated[str, Form()],
    material: Annotated[str | None, Form()] = None,
    outside_diameter_mm: Annotated[str | None, Form()] = None,
    centre_x_mm: Annotated[str | None, Form()] = None,
    centre_y_mm: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    opening = db.get(Opening, opening_id)
    if not opening:
        raise HTTPException(404, "Opening not found")
    if opening.estimate.status not in {"draft", "in_review"}:
        raise HTTPException(409, "Locked or released estimates cannot be modified")
    try:
        require_physical_model_mutation(db, opening.estimate)
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise HTTPException(409, str(exc)) from exc
    service = Service(
        opening_id=opening.id,
        service_code=service_code,
        service_type=service_type,
        material=material,
        outside_diameter_mm=D(outside_diameter_mm) if outside_diameter_mm else None,
        centre_x_mm=D(centre_x_mm) if centre_x_mm else None,
        centre_y_mm=D(centre_y_mm) if centre_y_mm else None,
        evidence_status="provisional",
    )
    db.add(service)
    db.flush()
    db.add(
        ServiceOpeningLink(
            service_id=service.id,
            opening_id=opening.id,
            evidence_status=service.evidence_status,
            confidence=service.confidence,
        )
    )
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="service",
        entity_id=service.id,
        project_id=opening.estimate.project_id,
        new_value={"service_code": service_code, "service_type": service_type},
    )
    db.commit()
    return RedirectResponse(f"/estimates/{opening.estimate_id}", status_code=303)


@router.post("/estimates/{estimate_id}/lines")
def estimate_add_line(
    estimate_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    component_type: Annotated[str, Form()],
    description: Annotated[str, Form()],
    quantity: Annotated[str, Form()],
    unit: Annotated[str, Form()],
    base_unit_cost: Annotated[str, Form()],
    markup_override_percent: Annotated[str | None, Form()] = None,
    opening_id: Annotated[str | None, Form()] = None,
    service_id: Annotated[str | None, Form()] = None,
    component_reference: Annotated[str | None, Form()] = None,
    pricing_method: Annotated[str, Form()] = "component_built",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    estimate = _estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(409, str(exc)) from exc
    line_number = (
        db.scalar(
            select(func.max(EstimateLine.line_number)).where(
                EstimateLine.estimate_id == estimate.id
            )
        )
        or 0
    ) + 1
    line = EstimateLine(
        estimate_id=estimate.id,
        line_number=line_number,
        opening_id=opening_id or None,
        service_id=service_id or None,
        component_type=component_type,
        component_reference=component_reference or None,
        description=description,
        quantity=D(quantity),
        unit=unit,
        base_unit_cost=D(base_unit_cost),
        markup_override=(
            D(markup_override_percent) / Decimal("100") if markup_override_percent else None
        ),
        pricing_method=pricing_method,
        commercial_recovery_status="separately_priced",
    )
    db.add(line)
    db.flush()
    try:
        calculate_estimate_line(db, estimate, line)
        recalculate_estimate(db, estimate)
    except ValueError as exc:
        db.rollback()
        message = str(exc).replace(" ", "+")
        return RedirectResponse(f"/estimates/{estimate.id}?error={message}", status_code=303)
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="estimate_line",
        entity_id=line.id,
        project_id=estimate.project_id,
        new_value={
            "description": description,
            "applied_markup": str(line.applied_markup),
            "markup_source": line.markup_source,
        },
    )
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.post("/estimates/{estimate_id}/evaluate")
def estimate_evaluate(
    estimate_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    estimate = _estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(409, str(exc)) from exc
    results = evaluate_estimate_rules(db, estimate)
    record_audit(
        db,
        actor=user,
        action="evaluate_rules",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={"count": len(results)},
    )
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.post("/estimates/{estimate_id}/lock")
def estimate_lock(
    estimate_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:approve")
    estimate = _estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(409, str(exc)) from exc
    basis_errors = validate_estimate_release_basis(db, estimate)
    if basis_errors:
        message = ("Release basis incomplete: " + "; ".join(basis_errors)).replace(" ", "+")
        return RedirectResponse(f"/estimates/{estimate.id}?error={message}", status_code=303)
    blockers = db.scalars(
        select(RuleEvaluation).where(
            RuleEvaluation.estimate_id == estimate.id,
            RuleEvaluation.result == "BLOCKED",
        )
    ).all()
    if blockers:
        return RedirectResponse(
            f"/estimates/{estimate.id}?error=Blocking+rule+results+must+be+resolved",
            status_code=303,
        )
    try:
        snapshot = lock_snapshot(db, estimate)
    except ValueError as exc:
        db.rollback()
        message = str(exc).replace(" ", "+")
        return RedirectResponse(f"/estimates/{estimate.id}?error={message}", status_code=303)
    record_audit(
        db,
        actor=user,
        action="lock_snapshot",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={"snapshot_hash": snapshot["snapshot_hash"]},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "audit:read")
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)).all()
    return templates.TemplateResponse(request, "audit.html", _context(request, db, events=events))
