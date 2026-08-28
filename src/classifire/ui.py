from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

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
from .physical_models import ServiceOpeningLink
from .security import (
    authenticate_user,
    create_csrf_token,
    has_permission,
    resolve_session_user,
    verify_csrf,
)
from .services.calculation import D, calculate_estimate_line, recalculate_estimate
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
from .services.technical_document_metadata import (
    technical_current_standards_advisory,
)
from .services.technical_intake import (
    TECHNICAL_DOCUMENT_TYPE_LABELS,
    TECHNICAL_DOCUMENT_TYPE_OPTIONS,
    TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS,
    TechnicalIntakeError,
    create_technical_document_draft,
)
from .services.technical_intake_batch import (
    TechnicalIntakeBatchError,
    claim_technical_intake_batch_item,
)
from .services.technical_intake_draft import (
    TechnicalIntakeDraftError,
    list_owned_technical_intake_drafts,
)
from .services.technical_upload_preflight import (
    TechnicalUploadPreflightError,
    preflight_technical_upload,
    require_matching_technical_upload_identity,
)
from .services.workflow import WorkflowTransitionError
from .services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
)
from .upload_ingress import TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
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
        "attribution": "QUANTIFIRE is an estimating system produced and developed by Ceasefire PFP.",
        "has_permission": lambda permission: bool(user and has_permission(user, permission)),
        **values,
    }


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Db, error: str | None = None) -> Response:
    if _user(request, db):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", _context(request, db, error=error))


@router.post("/login")
def login_submit(
    request: Request,
    db: Db,
    email: Annotated[str, Form()],
    password: Annotated[str, Form()],
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = authenticate_user(db, email, password)
    if not user:
        return RedirectResponse("/login?error=Invalid+email+or+password", status_code=303)
    request.session.clear()
    request.session["user_id"] = user.id
    create_csrf_token(request)
    return RedirectResponse("/", status_code=303)


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
    releases = db.scalars(select(LibraryRelease).order_by(LibraryRelease.created_at.desc()).limit(12)).all()
    open_changes = db.scalars(
        select(ChangeProposal).where(ChangeProposal.status.in_(["draft", "in_review"])).order_by(ChangeProposal.updated_at.desc()).limit(8)
    ).all()
    return templates.TemplateResponse(request, "dashboard.html",
        _context(request, db, counts=counts, recent_estimates=recent_estimates, releases=releases, open_changes=open_changes),
    )


@router.get("/products", response_class=HTMLResponse)
def products_page(request: Request, db: Db, q: str | None = None) -> HTMLResponse:
    _require(request, db, "library:read")
    stmt = select(Product)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%") | Product.sku.ilike(f"%{q}%"))
    products = db.scalars(stmt.order_by(Product.name).limit(500)).all()
    return templates.TemplateResponse(request, "products.html", _context(request, db, products=products, q=q or ""))


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
    record_audit(db, actor=user, action="create", entity_type="product", entity_id=product.id, new_value={"sku": sku, "name": name}, reason=reason)
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
    record_audit(db, actor=user, action="create", entity_type="labour_component", entity_id=component.id, new_value={"code": code, "name": name}, reason=reason)
    db.commit()
    return RedirectResponse("/labour", status_code=303)


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "rule:read")
    rules = db.scalars(select(EstimatingRule).order_by(EstimatingRule.priority, EstimatingRule.rule_code)).all()
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
        return RedirectResponse("/rules?error=Conditions+and+actions+must+be+valid+JSON", status_code=303)
    version = (db.scalar(select(func.max(EstimatingRule.version)).where(EstimatingRule.rule_code == rule_code)) or 0) + 1
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
    record_audit(db, actor=user, action="create_revision", entity_type="estimating_rule", entity_id=rule.id, new_value={"rule_code": rule_code, "version": version}, reason=reason)
    db.commit()
    return RedirectResponse("/rules", status_code=303)


@router.get("/technical", response_class=HTMLResponse)
def technical_page(request: Request, db: Db, q: str | None = None) -> HTMLResponse:
    user = _require(request, db, "technical:read")
    docs = db.scalars(select(TechnicalDocument).order_by(TechnicalDocument.updated_at.desc()).limit(100)).all()
    standards_advisories = {
        document.id: technical_current_standards_advisory(document.standards)
        for document in docs
    }
    try:
        own_intake_drafts = list_owned_technical_intake_drafts(
            db,
            actor=user,
        )[:100]
    except TechnicalIntakeDraftError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    intake_document_ids = {
        draft.technical_document_id for draft in own_intake_drafts
    }
    intake_draft_documents = (
        {
            document.id: document
            for document in db.scalars(
                select(TechnicalDocument).where(
                    TechnicalDocument.id.in_(intake_document_ids)
                )
            ).all()
        }
        if intake_document_ids
        else {}
    )
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
            standards_advisories=standards_advisories,
            technical_document_type_labels=TECHNICAL_DOCUMENT_TYPE_LABELS,
            technical_document_type_options=TECHNICAL_DOCUMENT_TYPE_OPTIONS,
            technical_legacy_document_type_labels=(
                TECHNICAL_LEGACY_DOCUMENT_TYPE_LABELS
            ),
            own_intake_drafts=own_intake_drafts,
            intake_draft_documents=intake_draft_documents,
            variants=variants,
            q=q or "",
            jurisdiction=get_settings().jurisdiction,
        ),
    )


_TECHNICAL_UPLOAD_FORM_FIELDS = frozenset(
    {
        "artifact_provenance_note",
        "artifact_provenance_status",
        "batch_id",
        "declared_source_role",
        "document_id",
        "document_type",
        "evidence_limitations",
        "evidence_scope",
        "expiry_date",
        "file",
        "issuing_organisation",
        "item_id",
        "jurisdiction",
        "manufacturer",
        "publication_date",
        "reference",
        "related_document_id",
        "relationship_effective_date",
        "relationship_reason",
        "relationship_scope",
        "relationship_type",
        "review_date",
        "revision",
        "sponsor_organisation",
        "standards",
        "title",
    }
)


def _technical_upload_form_failure(*, wants_json: bool) -> Response:
    if wants_json:
        return JSONResponse(
            {
                "ok": False,
                "code": "TECHNICAL_UPLOAD_FORM_INVALID",
                "retryable": False,
                "fatal": True,
            },
            status_code=422,
        )
    raise HTTPException(status_code=422, detail="TECHNICAL_UPLOAD_FORM_INVALID")


def _technical_upload_preflight_failure(
    error: TechnicalUploadPreflightError,
    *,
    wants_json: bool,
) -> Response:
    if wants_json:
        return JSONResponse(
            {
                "ok": False,
                "code": error.code,
                "retryable": error.retryable,
                "fatal": error.fatal,
            },
            status_code=error.status_code,
        )
    raise HTTPException(status_code=error.status_code, detail=error.code)


def _technical_upload_text(
    form: FormData,
    name: str,
    *,
    required: bool = False,
) -> str | None:
    values = form.getlist(name)
    if not values:
        if required:
            raise ValueError("Missing required technical upload field")
        return None
    if len(values) != 1 or not isinstance(values[0], str):
        raise ValueError("Invalid technical upload field")
    if required and not values[0].strip():
        raise ValueError("Empty required technical upload field")
    return values[0]


@router.post("/technical/upload")
async def technical_upload(
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    wants_json = "application/json" in request.headers.get("accept", "").lower()
    try:
        user = _require(request, db, "technical:write")
    except HTTPException as exc:
        if wants_json and exc.status_code in {401, 403}:
            code = (
                "AUTHENTICATION_REQUIRED"
                if exc.status_code == 401
                else "PERMISSION_DENIED"
            )
            return JSONResponse(
                {
                    "ok": False,
                    "code": code,
                    "retryable": False,
                    "fatal": True,
                },
                status_code=exc.status_code,
            )
        raise

    csrf_values = request.headers.getlist("x-csrf-token")
    try:
        verify_csrf(request, csrf_values[0] if len(csrf_values) == 1 else None)
    except HTTPException:
        if wants_json:
            return JSONResponse(
                {
                    "ok": False,
                    "code": "CSRF_INVALID",
                    "retryable": False,
                    "fatal": True,
                },
                status_code=403,
            )
        raise

    content_types = request.headers.getlist("content-type")
    if (
        len(content_types) != 1
        or content_types[0].split(";", 1)[0].strip().lower() != "multipart/form-data"
    ):
        return _technical_upload_form_failure(wants_json=wants_json)
    try:
        preflight = preflight_technical_upload(
            request,
            db,
            settings,
            actor=user,
        )
    except TechnicalUploadPreflightError as exc:
        return _technical_upload_preflight_failure(exc, wants_json=wants_json)
    form: FormData | None = None
    try:
        form = await request.form(
            max_files=1,
            max_fields=25,
            max_part_size=TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES,
        )
        if any(name not in _TECHNICAL_UPLOAD_FORM_FIELDS for name, _value in form.multi_items()):
            raise ValueError("Unexpected technical upload field")
        files = form.getlist("file")
        if len(files) != 1 or not isinstance(files[0], StarletteUploadFile):
            raise ValueError("Exactly one technical upload file is required")
        file = cast(UploadFile, files[0])
        document_id = cast(
            str,
            _technical_upload_text(form, "document_id", required=True),
        )
        document_type = cast(
            str,
            _technical_upload_text(form, "document_type", required=True),
        )
        declared_source_role = cast(
            str,
            _technical_upload_text(form, "declared_source_role", required=True),
        )
        artifact_provenance_status = cast(
            str,
            _technical_upload_text(
                form,
                "artifact_provenance_status",
                required=True,
            ),
        )
        evidence_scope = cast(
            str,
            _technical_upload_text(form, "evidence_scope", required=True),
        )
        title = cast(str, _technical_upload_text(form, "title", required=True))
        manufacturer = _technical_upload_text(form, "manufacturer")
        reference = _technical_upload_text(form, "reference")
        revision = _technical_upload_text(form, "revision")
        sponsor_organisation = _technical_upload_text(form, "sponsor_organisation")
        issuing_organisation = _technical_upload_text(form, "issuing_organisation")
        publication_date = _technical_upload_text(form, "publication_date")
        review_date = _technical_upload_text(form, "review_date")
        expiry_date = _technical_upload_text(form, "expiry_date")
        jurisdiction = _technical_upload_text(form, "jurisdiction")
        standards = _technical_upload_text(form, "standards")
        artifact_provenance_note = _technical_upload_text(
            form,
            "artifact_provenance_note",
        )
        evidence_limitations = _technical_upload_text(form, "evidence_limitations")
        relationship_type = _technical_upload_text(form, "relationship_type")
        related_document_id = _technical_upload_text(form, "related_document_id")
        relationship_reason = _technical_upload_text(form, "relationship_reason")
        relationship_scope = _technical_upload_text(form, "relationship_scope")
        relationship_effective_date = _technical_upload_text(
            form,
            "relationship_effective_date",
        )
        batch_id = _technical_upload_text(form, "batch_id")
        item_id = _technical_upload_text(form, "item_id")
    except (MultiPartException, StarletteHTTPException, RuntimeError, ValueError):
        if form is not None:
            await form.close()
        return _technical_upload_form_failure(wants_json=wants_json)

    try:
        batch_claim = None
        if (batch_id is None) != (item_id is None):
            raise TechnicalIntakeBatchError(
                "INTAKE_BATCH_ID_INVALID"
                if batch_id is None
                else "INTAKE_BATCH_ITEM_ID_INVALID"
            )
        require_matching_technical_upload_identity(
            preflight,
            batch_id=batch_id,
            item_id=item_id,
        )
        if item_id is not None:
            batch_claim = claim_technical_intake_batch_item(
                db,
                actor=user,
                batch_id=batch_id,
                item_id=item_id,
                filename=file.filename or "unnamed",
                registration_snapshot={
                    "artifact_provenance_note": artifact_provenance_note,
                    "artifact_provenance_status": (
                        artifact_provenance_status
                    ),
                    "declared_source_role": declared_source_role,
                    "document_id": document_id,
                    "document_type": document_type,
                    "evidence_limitations": evidence_limitations,
                    "evidence_scope": evidence_scope,
                    "expiry_date": expiry_date,
                    "issuing_organisation": issuing_organisation,
                    "jurisdiction": jurisdiction,
                    "manufacturer": manufacturer,
                    "publication_date": publication_date,
                    "reference": reference,
                    "related_document_id": related_document_id,
                    "relationship_effective_date": (
                        relationship_effective_date
                    ),
                    "relationship_reason": relationship_reason,
                    "relationship_scope": relationship_scope,
                    "relationship_type": relationship_type,
                    "review_date": review_date,
                    "revision": revision,
                    "sponsor_organisation": sponsor_organisation,
                    "standards": standards,
                    "title": title,
                },
            )
        result = create_technical_document_draft(
            db,
            settings,
            actor=user,
            upload=file,
            document_id=document_id,
            document_type=document_type,
            declared_source_role=declared_source_role,
            artifact_provenance_status=artifact_provenance_status,
            evidence_scope=evidence_scope,
            title=title,
            manufacturer=manufacturer,
            reference=reference,
            revision=revision,
            sponsor_organisation=sponsor_organisation,
            issuing_organisation=issuing_organisation,
            publication_date=publication_date,
            review_date=review_date,
            expiry_date=expiry_date,
            jurisdiction=jurisdiction,
            standards=standards,
            artifact_provenance_note=artifact_provenance_note,
            evidence_limitations=evidence_limitations,
            relationship_type=relationship_type,
            related_document_id=related_document_id,
            relationship_reason=relationship_reason,
            relationship_scope=relationship_scope,
            relationship_effective_date=relationship_effective_date,
            correlation_id=batch_id,
            source_ip=request.client.host if request.client else None,
            batch_claim=batch_claim,
        )
    except TechnicalIntakeError as exc:
        if wants_json:
            return JSONResponse(
                {
                    "ok": False,
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "fatal": exc.fatal,
                },
                status_code=exc.status_code,
            )
        return RedirectResponse(f"/technical?error={exc.code}", status_code=303)
    except TechnicalIntakeBatchError as exc:
        if wants_json:
            return JSONResponse(
                {
                    "ok": False,
                    "code": exc.code,
                    "retryable": exc.retryable,
                    "fatal": exc.fatal,
                },
                status_code=exc.status_code,
            )
        return RedirectResponse(f"/technical?error={exc.code}", status_code=303)
    except TechnicalUploadPreflightError as exc:
        return _technical_upload_preflight_failure(exc, wants_json=wants_json)
    finally:
        if form is not None:
            await form.close()
    if wants_json:
        receipt = result.receipt if isinstance(result.receipt, dict) else None
        if result.batch_item_id is not None and receipt is None:
            raise HTTPException(
                status_code=500,
                detail="TECHNICAL_UPLOAD_RECEIPT_INVALID",
            )
        relationship = None
        if receipt is not None:
            relationship = receipt.get("relationship")
        elif result.relationship is not None:
            related = db.get(
                TechnicalDocument,
                result.relationship.related_document_id,
            )
            if related is None:
                raise HTTPException(
                    status_code=500,
                    detail="TECHNICAL_UPLOAD_RECEIPT_INVALID",
                )
            relationship = {
                "relationship_type": result.relationship.relationship_type,
                "related_document_id": related.document_id,
            }
        payload: dict[str, Any] = {
            "ok": True,
            "id": result.document.id,
            "document_id": result.document.document_id,
            "document_type": result.document.document_type,
            "declared_source_role": result.document.declared_source_role,
            "artifact_provenance_status": (
                result.document.artifact_provenance_status
            ),
            "evidence_scope": result.document.evidence_scope,
            "status": result.document.status,
            "file_sha256": result.stored_file.sha256,
            "malware_scan_status": result.stored_file.malware_scan_status,
            "extraction_status": result.document.extraction_status,
            "batch_id": result.correlation_id,
            "item_id": result.batch_item_id,
            "idempotent_replay": result.idempotent_replay,
            "receipt_sha256": result.receipt_sha256,
            "status_url": receipt.get("status_url") if receipt else None,
            "relationship": relationship,
            "exact_content_duplicate_document_ids": list(
                result.exact_content_duplicate_document_ids
            ),
        }
        if receipt is not None:
            payload.update(
                {
                    "id": receipt["id"],
                    "document_id": receipt["document_id"],
                    "document_type": receipt["document_type"],
                    "declared_source_role": receipt["declared_source_role"],
                    "artifact_provenance_status": (
                        receipt["artifact_provenance_status"]
                    ),
                    "evidence_scope": receipt["evidence_scope"],
                    "status": receipt["status"],
                    "file_sha256": receipt["file_sha256"],
                    "malware_scan_status": receipt["malware_scan_status"],
                    "extraction_status": receipt["extraction_status"],
                    "batch_id": receipt["batch_id"],
                    "item_id": receipt["item_id"],
                    "status_url": receipt["status_url"],
                    "relationship": receipt["relationship"],
                    "exact_content_duplicate_document_ids": list(
                        receipt["exact_content_duplicate_document_ids"]
                    ),
                }
            )
        return JSONResponse(
            payload,
            status_code=200 if result.idempotent_replay else 201,
        )
    return RedirectResponse(
        "/technical?success=Technical+evidence+uploaded+as+Draft",
        status_code=303,
    )


@router.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "project:read")
    projects = db.scalars(select(Project).options(selectinload(Project.estimates)).order_by(Project.updated_at.desc())).all()
    return templates.TemplateResponse(request, "projects.html", _context(request, db, projects=projects))


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
    project = Project(reference=reference, name=name, site_address=site_address, jurisdiction=jurisdiction)
    db.add(project)
    db.flush()
    record_audit(db, actor=user, action="create", entity_type="project", entity_id=project.id, project_id=project.id, new_value={"reference": reference, "name": name})
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
    revision = (db.scalar(select(func.max(Estimate.revision)).where(Estimate.project_id == project.id)) or 0) + 1
    estimate = Estimate(project_id=project.id, revision=revision, reference=reference, title=title, status="draft", currency=get_settings().currency, tax_name=get_settings().tax_name, tax_rate=D(get_settings().tax_rate))
    db.add(estimate)
    db.flush()
    try:
        pin_current_releases(db, estimate)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"/projects?error={str(exc).replace(chr(32), chr(43))}", status_code=303)
    record_audit(db, actor=user, action="create", entity_type="estimate", entity_id=estimate.id, project_id=project.id, new_value={"reference": reference, "revision": revision})
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
    evaluations = db.scalars(select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)).all()
    release_basis = release_basis_for_estimate(db, estimate)
    return templates.TemplateResponse(request, "estimate.html", _context(request, db, estimate=estimate, evaluations=evaluations, release_basis=release_basis))


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
    record_audit(db, actor=user, action="create", entity_type="opening", entity_id=opening.id, project_id=estimate.project_id, new_value={"opening_code": opening_code})
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
    service = Service(opening_id=opening.id, service_code=service_code, service_type=service_type, material=material, outside_diameter_mm=D(outside_diameter_mm) if outside_diameter_mm else None, centre_x_mm=D(centre_x_mm) if centre_x_mm else None, centre_y_mm=D(centre_y_mm) if centre_y_mm else None, evidence_status="provisional")
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
    record_audit(db, actor=user, action="create", entity_type="service", entity_id=service.id, project_id=opening.estimate.project_id, new_value={"service_code": service_code, "service_type": service_type})
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
    line_number = (db.scalar(select(func.max(EstimateLine.line_number)).where(EstimateLine.estimate_id == estimate.id)) or 0) + 1
    line = EstimateLine(estimate_id=estimate.id, line_number=line_number, opening_id=opening_id or None, service_id=service_id or None, component_type=component_type, component_reference=component_reference or None, description=description, quantity=D(quantity), unit=unit, base_unit_cost=D(base_unit_cost), markup_override=(D(markup_override_percent) / Decimal("100") if markup_override_percent else None), pricing_method=pricing_method, commercial_recovery_status="separately_priced")
    db.add(line)
    db.flush()
    try:
        calculate_estimate_line(db, estimate, line)
        recalculate_estimate(db, estimate)
    except ValueError as exc:
        db.rollback()
        message = str(exc).replace(" ", "+")
        return RedirectResponse(f"/estimates/{estimate.id}?error={message}", status_code=303)
    record_audit(db, actor=user, action="create", entity_type="estimate_line", entity_id=line.id, project_id=estimate.project_id, new_value={"description": description, "applied_markup": str(line.applied_markup), "markup_source": line.markup_source})
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.post("/estimates/{estimate_id}/evaluate")
def estimate_evaluate(estimate_id: str, request: Request, db: Db, csrf_token: Annotated[str, Form()]) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "estimate:write")
    estimate = _estimate(db, estimate_id)
    try:
        require_active_physical_model_lock(db, estimate)
    except PhysicalModelLockRequiredError as exc:
        raise HTTPException(409, str(exc)) from exc
    results = evaluate_estimate_rules(db, estimate)
    record_audit(db, actor=user, action="evaluate_rules", entity_type="estimate", entity_id=estimate.id, project_id=estimate.project_id, new_value={"count": len(results)})
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.post("/estimates/{estimate_id}/lock")
def estimate_lock(estimate_id: str, request: Request, db: Db, csrf_token: Annotated[str, Form()], reason: Annotated[str, Form()]) -> RedirectResponse:
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
    blockers = db.scalars(select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id, RuleEvaluation.result == "BLOCKED")).all()
    if blockers:
        return RedirectResponse(f"/estimates/{estimate.id}?error=Blocking+rule+results+must+be+resolved", status_code=303)
    try:
        snapshot = lock_snapshot(db, estimate)
    except ValueError as exc:
        db.rollback()
        message = str(exc).replace(" ", "+")
        return RedirectResponse(f"/estimates/{estimate.id}?error={message}", status_code=303)
    record_audit(db, actor=user, action="lock_snapshot", entity_type="estimate", entity_id=estimate.id, project_id=estimate.project_id, new_value={"snapshot_hash": snapshot["snapshot_hash"]}, reason=reason)
    db.commit()
    return RedirectResponse(f"/estimates/{estimate.id}", status_code=303)


@router.get("/audit", response_class=HTMLResponse)
def audit_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "audit:read")
    events = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(500)).all()
    return templates.TemplateResponse(request, "audit.html", _context(request, db, events=events))
