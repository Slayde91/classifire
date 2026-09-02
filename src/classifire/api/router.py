from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, TypeGuard

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import (
    AuditEvent,
    ChangeProposal,
    Estimate,
    EstimateLine,
    EstimatingRule,
    LabourComponent,
    Opening,
    PricingLibraryRecord,
    Product,
    Project,
    RuleEvaluation,
    Service,
    TechnicalDocument,
    User,
)
from ..outputs import (
    render_desk_quote_pdf,
    render_desk_quote_workbook,
    render_estimate_pdf,
    render_proposal_workbook,
    render_technical_workbook,
)
from ..physical_models import ServiceOpeningLink
from ..schemas import (
    ChangeProposalInput,
    EstimateInput,
    EstimateLineInput,
    EstimateOut,
    LabourInput,
    LabourOut,
    OpeningInput,
    ProductInput,
    ProductOut,
    ProjectInput,
    ProjectOut,
    RuleInput,
    RuleOut,
    ServiceInput,
    TechnicalVariantSearch,
)
from ..security import get_current_user, require_permission
from ..services.calculation import calculate_estimate_line, recalculate_estimate
from ..services.desk_quote import (
    DeskQuoteError,
    DeskQuoteProposal,
    build_desk_quote_snapshot,
    resolve_desk_quote_pricing_bindings,
    resolve_desk_quote_project_evidence,
)
from ..services.initial_canonicalisation_boundary import (
    InitialCanonicalisationAdmissionRequired,
    require_admission_bound_initial_canonicalisation,
)
from ..services.physical_defects import bind_canonical_defect
from ..services.physical_mutation_guard import (
    PhysicalMutationError,
    require_physical_model_mutation,
)
from ..services.rule_engine import evaluate_estimate_rules
from ..services.snapshot import lock_snapshot
from ..services.storage import (
    StoredFileBindingError,
    read_hashed_storage_artifact,
    read_verified_stored_file,
    save_upload,
)
from ..services.technical import (
    build_technical_document_draft_metadata_from_verified_content,
    build_technical_document_extraction_deferred_metadata,
    search_for_opening,
    search_variants,
)
from ..services.workflow import WorkflowAction, WorkflowTransitionError
from ..services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
    require_estimate_action,
)

router = APIRouter(prefix="/api/v1", tags=["QUANTIFIRE API v1"])
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def _get_or_404(db: Session, model: type[Any], entity_id: str, name: str) -> Any:
    record = db.get(model, entity_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return record


@router.get("/health")
def health(db: Db, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    db.execute(select(1))
    return {
        "status": "ok",
        "product": "QUANTIFIRE",
        "version": "0.1.0",
        "environment": settings.env,
        "production_findings": settings.validate_production(),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/products", response_model=list[ProductOut])
def list_products(
    db: Db,
    _user: Annotated[User, Depends(require_permission("library:read"))],
    q: str | None = None,
    item_type: str | None = None,
    record_status: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=1000),
) -> list[Product]:
    stmt = select(Product)
    if q:
        stmt = stmt.where((Product.name.ilike(f"%{q}%")) | (Product.sku.ilike(f"%{q}%")))
    if item_type:
        stmt = stmt.where(Product.item_type == item_type)
    if record_status:
        stmt = stmt.where(Product.status == record_status)
    return list(db.scalars(stmt.order_by(Product.name).limit(limit)).all())


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("pricing:write"))],
) -> Product:
    existing = db.scalar(select(Product).where(Product.sku == payload.sku, Product.revision == 1))
    if existing:
        raise HTTPException(status_code=409, detail="SKU already exists; create a revision instead")
    product = Product(**payload.model_dump(), revision=1)
    db.add(product)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="product",
        entity_id=product.id,
        new_value=payload.model_dump(mode="json"),
        reason="Created through QUANTIFIRE API",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(product)
    return product


@router.post("/products/{product_id}/revise", response_model=ProductOut)
def revise_product(
    product_id: str,
    payload: ProductInput,
    reason: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("pricing:write"))],
) -> Product:
    previous: Product = _get_or_404(db, Product, product_id, "Product")
    latest_revision = (
        db.scalar(
            select(func.max(Product.revision)).where(Product.sku == previous.sku)
        )
        or 0
    )
    revision = Product(
        **payload.model_dump(),
        sku=previous.sku,
        revision=int(latest_revision) + 1,
        status="draft",
        supersedes_id=previous.id,
    )
    db.add(revision)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="revise",
        entity_type="product",
        entity_id=revision.id,
        previous_value=ProductOut.model_validate(previous).model_dump(mode="json"),
        new_value=ProductOut.model_validate(revision).model_dump(mode="json"),
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(revision)
    return revision


@router.get("/labour", response_model=list[LabourOut])
def list_labour(
    db: Db,
    _user: Annotated[User, Depends(require_permission("library:read"))],
    q: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> list[LabourComponent]:
    stmt = select(LabourComponent)
    if q:
        stmt = stmt.where(
            LabourComponent.name.ilike(f"%{q}%") | LabourComponent.code.ilike(f"%{q}%")
        )
    return list(db.scalars(stmt.order_by(LabourComponent.name).limit(limit)).all())


@router.post("/labour", response_model=LabourOut, status_code=status.HTTP_201_CREATED)
def create_labour(
    payload: LabourInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("pricing:write"))],
) -> LabourComponent:
    existing = db.scalar(
        select(LabourComponent).where(
            LabourComponent.code == payload.code,
            LabourComponent.revision == 1,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Labour code already exists; create a revision")
    labour = LabourComponent(**payload.model_dump(), revision=1)
    db.add(labour)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="labour_component",
        entity_id=labour.id,
        new_value=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(labour)
    return labour


@router.get("/pricing-records")
def list_pricing_records(
    db: Db,
    _user: Annotated[User, Depends(require_permission("library:read"))],
    q: str | None = None,
    service_type: str | None = None,
    substrate: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
) -> list[dict[str, Any]]:
    stmt = select(PricingLibraryRecord)
    if q:
        stmt = stmt.where(
            PricingLibraryRecord.description.ilike(f"%{q}%")
            | PricingLibraryRecord.pkb_entry_id.ilike(f"%{q}%")
        )
    if service_type:
        stmt = stmt.where(PricingLibraryRecord.service_type.ilike(f"%{service_type}%"))
    if substrate:
        stmt = stmt.where(PricingLibraryRecord.substrate.ilike(f"%{substrate}%"))
    records = db.scalars(stmt.order_by(PricingLibraryRecord.pkb_entry_id).limit(limit)).all()
    return [
        {
            "id": item.id,
            "pkb_entry_id": item.pkb_entry_id,
            "entry_version": item.entry_version,
            "description": item.description,
            "unit": item.unit,
            "rate_ex_tax": str(item.rate_ex_tax),
            "currency": item.currency,
            "service_type": item.service_type,
            "service_material": item.service_material,
            "substrate": item.substrate,
            "frl": item.frl,
            "manufacturer": item.manufacturer,
            "commercial_confidence": item.commercial_confidence,
            "status": item.status,
            "rate_inclusions": item.rate_inclusions,
            "applicability": item.applicability,
        }
        for item in records
    ]


@router.get("/rules", response_model=list[RuleOut])
def list_rules(
    db: Db,
    _user: Annotated[User, Depends(require_permission("rule:read"))],
    record_status: str | None = Query(None, alias="status"),
) -> list[EstimatingRule]:
    stmt = select(EstimatingRule)
    if record_status:
        stmt = stmt.where(EstimatingRule.status == record_status)
    return list(db.scalars(stmt.order_by(EstimatingRule.priority, EstimatingRule.rule_code)).all())


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: RuleInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("rule:write"))],
) -> EstimatingRule:
    max_version = db.scalar(
        select(func.max(EstimatingRule.version)).where(
            EstimatingRule.rule_code == payload.rule_code
        )
    ) or 0
    rule = EstimatingRule(
        **payload.model_dump(),
        version=int(max_version) + 1,
        status="draft",
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
        new_value=payload.model_dump(mode="json"),
        reason="New rule or rule revision created as Draft",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/rules/{rule_id}/approve", response_model=RuleOut)
def approve_rule(
    rule_id: str,
    reason: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("rule:approve"))],
) -> EstimatingRule:
    rule: EstimatingRule = _get_or_404(db, EstimatingRule, rule_id, "Rule")
    if rule.author_id == user.id and user.role != "administrator":
        raise HTTPException(status_code=409, detail="The author cannot approve their own rule")
    previous = {"status": rule.status}
    rule.status = "active"
    rule.reviewer_id = user.id
    rule.approver_id = user.id
    rule.approved_at = datetime.now(UTC)
    record_audit(
        db,
        actor=user,
        action="approve",
        entity_type="estimating_rule",
        entity_id=rule.id,
        previous_value=previous,
        new_value={"status": rule.status},
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/change-proposals", status_code=status.HTTP_201_CREATED)
def create_change_proposal(
    payload: ChangeProposalInput,
    request: Request,
    db: Db,
    user: CurrentUser,
) -> dict[str, Any]:
    proposal = ChangeProposal(
        **payload.model_dump(),
        source="user",
        status="draft",
        submitted_by_id=user.id,
    )
    db.add(proposal)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="suggest_change",
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        new_value=payload.proposed_data,
        reason=payload.reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": proposal.id, "status": proposal.status, "message": "Suggestion stored as Draft"}


@router.get("/technical/variants/search")
def technical_search(
    db: Db,
    _user: Annotated[User, Depends(require_permission("technical:read"))],
    service_type: str | None = None,
    service_material: str | None = None,
    substrate: str | None = None,
    orientation: str | None = None,
    frl: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    payload = TechnicalVariantSearch(
        service_type=service_type,
        service_material=service_material,
        substrate=substrate,
        orientation=orientation,
        frl=frl,
        limit=limit,
    )
    candidates = search_variants(db, **payload.model_dump())
    return [
        {
            "variant_id": item.variant.variant_id,
            "system_id": item.variant.system_id,
            "score": str(item.score),
            "comparisons": item.comparisons,
            "blockers": item.blockers,
            "manufacturer": item.variant.manufacturer,
            "product_family": item.variant.product_family,
            "frl": item.variant.frl,
            "source_document": item.variant.source_document_reference,
            "source_page": item.variant.source_page,
            "expert_review_required": item.variant.expert_review_required,
        }
        for item in candidates
    ]


@router.post("/technical/documents", status_code=status.HTTP_201_CREATED)
def upload_technical_document(
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_permission("technical:write"))],
    file: UploadFile = File(...),
    document_id: str = Form(...),
    document_type: str = Form(...),
    title: str = Form(...),
    manufacturer: str | None = Form(None),
    reference: str | None = Form(None),
    revision: str | None = Form(None),
    jurisdiction: str | None = Form(None),
) -> dict[str, Any]:
    if db.scalar(select(TechnicalDocument.id).where(TechnicalDocument.document_id == document_id)):
        raise HTTPException(status_code=409, detail="Technical Document ID already exists")
    try:
        stored = save_upload(db, settings, file, purpose="technical_evidence", user=user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        jurisdiction=jurisdiction,
        status="draft",
        extraction_status=metadata.get("extraction_status", "not_started"),
        metadata_json=metadata,
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
            "filename": stored.original_filename,
            "status": "draft",
        },
        reason="Original evidence preserved unchanged; extracted information remains Draft",
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "id": document.id,
        "document_id": document.document_id,
        "status": document.status,
        "file_sha256": stored.sha256,
        "metadata": metadata,
    }


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Db, _user: Annotated[User, Depends(require_permission("project:read"))]
) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.updated_at.desc())).all())


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("project:write"))],
) -> Project:
    if db.scalar(select(Project.id).where(Project.reference == payload.reference)):
        raise HTTPException(status_code=409, detail="Project reference already exists")
    project = Project(**payload.model_dump())
    db.add(project)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="project",
        entity_id=project.id,
        project_id=project.id,
        new_value=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(project)
    return project


@router.post("/estimates", response_model=EstimateOut, status_code=status.HTTP_201_CREATED)
def create_estimate(
    payload: EstimateInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> Estimate:
    project: Project = _get_or_404(db, Project, payload.project_id, "Project")
    revision = (
        db.scalar(
            select(func.max(Estimate.revision)).where(Estimate.project_id == project.id)
        )
        or 0
    )
    estimate = Estimate(**payload.model_dump(), revision=int(revision) + 1, status="draft")
    db.add(estimate)
    db.flush()
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=project.id,
        new_value=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(estimate)
    return estimate


def _load_estimate(db: Session, estimate_id: str) -> Estimate:
    estimate = db.scalar(
        select(Estimate)
        .where(Estimate.id == estimate_id)
        .options(
            selectinload(Estimate.project).selectinload(Project.customer),
            selectinload(Estimate.openings).selectinload(Opening.services),
            selectinload(Estimate.lines),
        )
    )
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


@router.get("/estimates/{estimate_id}", response_model=EstimateOut)
def get_estimate(
    estimate_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("estimate:read"))],
) -> Estimate:
    return _load_estimate(db, estimate_id)


@router.post("/estimates/{estimate_id}/openings", status_code=status.HTTP_201_CREATED)
def add_opening(
    estimate_id: str,
    payload: OpeningInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if not isinstance(settings, Settings):
        settings = get_settings()
    estimate = _load_estimate(db, estimate_id)
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(
            status_code=409,
            detail="Locked or released estimates cannot be modified",
        )
    try:
        require_physical_model_mutation(db, estimate)
        require_admission_bound_initial_canonicalisation(
            db,
            estimate_id=estimate.id,
            enabled=settings.adjudicated_initial_submission_enabled,
        )
    except InitialCanonicalisationAdmissionRequired as exc:
        raise HTTPException(
            status_code=409,
            detail="Initial physical model requires signed admission.",
        ) from exc
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    defect = bind_canonical_defect(db, estimate, payload.defect_id)
    opening = Opening(
        estimate_id=estimate.id,
        canonical_defect_id=defect.id if defect else None,
        **payload.model_dump(),
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
        new_value=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": opening.id, "opening_code": opening.opening_code}


@router.post("/openings/{opening_id}/services", status_code=status.HTTP_201_CREATED)
def add_service(
    opening_id: str,
    payload: ServiceInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    opening: Opening = _get_or_404(db, Opening, opening_id, "Opening")
    if opening.estimate.status not in {"draft", "in_review"}:
        raise HTTPException(
            status_code=409,
            detail="Locked or released estimates cannot be modified",
        )
    try:
        require_physical_model_mutation(db, opening.estimate)
    except (PhysicalMutationError, WorkflowTransitionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    service = Service(opening_id=opening.id, **payload.model_dump())
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
        new_value=payload.model_dump(mode="json"),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"id": service.id, "service_code": service.service_code}


@router.post("/estimates/{estimate_id}/lines", status_code=status.HTTP_201_CREATED)
def add_line(
    estimate_id: str,
    payload: EstimateLineInput,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    estimate = _load_estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(
            status_code=409,
            detail="Locked or released estimates cannot be modified",
        )
    next_number = (
        db.scalar(
            select(func.max(EstimateLine.line_number)).where(
                EstimateLine.estimate_id == estimate.id
            )
        )
        or 0
    ) + 1
    line = EstimateLine(estimate_id=estimate.id, line_number=next_number, **payload.model_dump())
    db.add(line)
    db.flush()
    calculate_estimate_line(db, estimate, line)
    recalculate_estimate(db, estimate)
    record_audit(
        db,
        actor=user,
        action="create",
        entity_type="estimate_line",
        entity_id=line.id,
        project_id=estimate.project_id,
        new_value={
            **payload.model_dump(mode="json"),
            "applied_markup": str(line.applied_markup),
            "markup_source": line.markup_source,
        },
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "id": line.id,
        "line_number": line.line_number,
        "applied_markup": str(line.applied_markup),
        "markup_source": line.markup_source,
        "subtotal_ex_tax": str(line.subtotal_ex_tax),
    }


@router.post("/estimates/{estimate_id}/recalculate")
def recalculate(
    estimate_id: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> dict[str, Any]:
    estimate = _load_estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if estimate.status not in {"draft", "in_review"}:
        raise HTTPException(
            status_code=409,
            detail="Locked or released estimates cannot be recalculated",
        )
    recalculate_estimate(db, estimate)
    record_audit(
        db,
        actor=user,
        action="recalculate",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={
            "subtotal_ex_tax": str(estimate.subtotal_ex_tax),
            "tax_total": str(estimate.tax_total),
            "total_incl_tax": str(estimate.total_incl_tax),
        },
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {
        "subtotal_ex_tax": str(estimate.subtotal_ex_tax),
        "tax_total": str(estimate.tax_total),
        "total_incl_tax": str(estimate.total_incl_tax),
    }


@router.post("/estimates/{estimate_id}/evaluate-rules")
def evaluate_rules(
    estimate_id: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
) -> list[dict[str, Any]]:
    estimate = _load_estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    results = evaluate_estimate_rules(db, estimate)
    record_audit(
        db,
        actor=user,
        action="evaluate_rules",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={"evaluation_count": len(results)},
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return [
        {
            "id": item.id,
            "opening_id": item.opening_id,
            "result": item.result,
            "severity": item.severity,
            "explanation": item.explanation,
            "inputs": item.inputs,
            "output": item.output,
        }
        for item in results
    ]


@router.get("/openings/{opening_id}/technical-search")
def opening_technical_search(
    opening_id: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("technical:read"))],
) -> dict[str, Any]:
    opening = db.scalar(
        select(Opening).where(Opening.id == opening_id).options(selectinload(Opening.services))
    )
    if not opening:
        raise HTTPException(status_code=404, detail="Opening not found")
    try:
        require_estimate_action(db, opening.estimate, WorkflowAction.SEARCH_TECHNICAL)
    except WorkflowTransitionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"action": "search_technical", "blockers": list(exc.blockers)},
        ) from exc
    return search_for_opening(db, opening)


@router.post("/estimates/{estimate_id}/lock")
def lock_estimate(
    estimate_id: str,
    reason: str,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:approve"))],
) -> dict[str, Any]:
    estimate = _load_estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    evaluations = db.scalars(
        select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)
    ).all()
    blocking = [
        item
        for item in evaluations
        if item.result == "BLOCKED" or item.severity == "blocking_error"
    ]
    if blocking:
        raise HTTPException(status_code=409, detail="Estimate has blocking rule results")
    snapshot = lock_snapshot(db, estimate)
    record_audit(
        db,
        actor=user,
        action="lock_snapshot",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=estimate.project_id,
        new_value={"snapshot_hash": snapshot["snapshot_hash"], "status": "locked"},
        reason=reason,
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return {"snapshot_hash": snapshot["snapshot_hash"], "status": estimate.status}


@router.get("/estimates/{estimate_id}/export/{artifact_type}")
def export_estimate(
    estimate_id: str,
    artifact_type: str,
    db: Db,
    _user: Annotated[User, Depends(require_permission("estimate:export"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FileResponse:
    estimate = _load_estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not estimate.snapshot_json or not estimate.snapshot_hash:
        raise HTTPException(status_code=409, detail="Lock the estimate before exporting")
    export_dir = settings.storage_root / "exports" / estimate.id / estimate.snapshot_hash
    export_dir.mkdir(parents=True, exist_ok=True)
    safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in estimate.reference)
    mapping = {
        "technical-xlsx": (
            f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.xlsx",
            render_technical_workbook,
        ),
        "proposal-xlsx": (
            f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Proposal.xlsx",
            render_proposal_workbook,
        ),
        "technical-pdf": (
            f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.pdf",
            lambda snapshot, output: render_estimate_pdf(snapshot, output, proposal=False),
        ),
        "proposal-pdf": (
            f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Proposal.pdf",
            lambda snapshot, output: render_estimate_pdf(snapshot, output, proposal=True),
        ),
    }
    if artifact_type not in mapping:
        raise HTTPException(status_code=404, detail="Unknown artifact type")
    filename, renderer = mapping[artifact_type]
    path = export_dir / filename
    if not path.exists():
        renderer(estimate.snapshot_json, path)
    media_type = (
        "application/pdf"
        if path.suffix == ".pdf"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    return FileResponse(path, filename=filename, media_type=media_type)


def _is_sha256(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in '0123456789abcdef' for character in value.casefold())
    )


def _cached_desk_quote_artifact_binding(
    db: Session,
    *,
    project_id: str,
    snapshot_hash: str,
    artifact_type: str,
) -> tuple[str, int] | None:
    events = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.action == 'render_desk_quote',
            AuditEvent.entity_type == 'desk_quote',
            AuditEvent.entity_id == snapshot_hash,
            AuditEvent.project_id == project_id,
        )
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
    ).all()
    for event in events:
        payload = event.new_value
        if not isinstance(payload, dict) or payload.get('artifact_type') != artifact_type:
            continue
        sha256 = payload.get('artifact_sha256')
        size_bytes = payload.get('artifact_size_bytes')
        if _is_sha256(sha256) and isinstance(size_bytes, int) and size_bytes > 0:
            return sha256.casefold(), size_bytes
        return None
    return None


def _read_desk_quote_artifact(
    *,
    settings: Settings,
    path: Path,
    expected_binding: tuple[str, int] | None = None,
):
    try:
        artifact = read_hashed_storage_artifact(storage_root=settings.storage_root, path=path)
    except StoredFileBindingError as error:
        raise DeskQuoteError(f'desk-quote export bytes cannot be verified: {error.code}') from error
    if expected_binding is not None and (
        artifact.sha256 != expected_binding[0] or artifact.size_bytes != expected_binding[1]
    ):
        raise DeskQuoteError('desk-quote cached export bytes do not match their audit binding')
    return artifact


@router.post("/desk-quotes/export/{artifact_type}")
def export_desk_quote(
    artifact_type: str,
    payload: DeskQuoteProposal,
    request: Request,
    db: Db,
    user: Annotated[User, Depends(require_permission("estimate:write"))],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    """Render a source-linked desk quote without opening the canonical estimate path."""

    mapping = {
        "desk-quote-xlsx": (
            f"CLASSIFIRE_{payload.quote_reference}_Desk_Quote.xlsx",
            render_desk_quote_workbook,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        "desk-quote-pdf": (
            f"CLASSIFIRE_{payload.quote_reference}_Desk_Quote.pdf",
            render_desk_quote_pdf,
            "application/pdf",
        ),
    }
    if artifact_type not in mapping:
        raise HTTPException(status_code=404, detail="Unknown desk-quote artifact type")
    try:
        project = resolve_desk_quote_project_evidence(
            db,
            payload,
            storage_root=settings.storage_root,
        )
        pricing_bindings = resolve_desk_quote_pricing_bindings(db, payload)
        snapshot = build_desk_quote_snapshot(payload, pricing_bindings=pricing_bindings)
    except DeskQuoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    filename, renderer, media_type = mapping[artifact_type]
    safe_filename = "".join(char if char.isalnum() or char in "-_." else "_" for char in filename)
    output_dir = settings.storage_root / "desk-quote-exports" / snapshot["snapshot_hash"]
    output_path = output_dir / safe_filename
    try:
        if output_path.exists():
            cached_binding = _cached_desk_quote_artifact_binding(
                db,
                project_id=project.id,
                snapshot_hash=snapshot["snapshot_hash"],
                artifact_type=artifact_type,
            )
            if cached_binding is None:
                raise DeskQuoteError("desk-quote cached export has no verified audit binding")
            artifact = _read_desk_quote_artifact(
                settings=settings,
                path=output_path,
                expected_binding=cached_binding,
            )
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            temporary_path = output_path.with_name(f".{safe_filename}.tmp")
            try:
                renderer(snapshot, temporary_path)
                artifact = _read_desk_quote_artifact(settings=settings, path=temporary_path)
                temporary_path.replace(output_path)
            finally:
                temporary_path.unlink(missing_ok=True)
    except DeskQuoteError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    record_audit(
        db,
        actor=user,
        action="render_desk_quote",
        entity_type="desk_quote",
        entity_id=snapshot["snapshot_hash"],
        project_id=project.id,
        new_value={
            "artifact_type": artifact_type,
            "artifact_sha256": artifact.sha256,
            "artifact_size_bytes": artifact.size_bytes,
            "document_class": snapshot["document_class"],
            "technical_position": snapshot["technical_position"],
            "quote_reference": payload.quote_reference,
            "project_reference": payload.project_reference,
            "estimate_reference": payload.estimate_reference,
            "pricing_release_id": payload.pricing_release_id,
            "pricing_release_version": snapshot["pricing_bindings"][0]["pricing_release_version"],
            "pricing_release_hash": snapshot["pricing_bindings"][0]["pricing_release_hash"],
            "evidence_source_ids": sorted(
                {
                    locator.evidence_source_id
                    for assumption in payload.assumptions
                    for locator in assumption.evidence_locators
                }
            ),
            "evidence_file_sha256": sorted(
                {
                    locator.file_sha256.lower()
                    for assumption in payload.assumptions
                    for locator in assumption.evidence_locators
                }
            ),
            "snapshot_hash": snapshot["snapshot_hash"],
        },
        reason=(
            "Rendered assumption-led desk quote; no canonical Physical Model or technical "
            "approval created"
        ),
        source_ip=request.client.host if request.client else None,
    )
    db.commit()
    return Response(
        content=artifact.content,
        media_type=media_type,
        headers={"content-disposition": f'attachment; filename="{safe_filename}"'},
    )
