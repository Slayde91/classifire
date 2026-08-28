from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, Any, cast

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse
from multipart.exceptions import MultipartParseError  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData, UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import MultiPartException

if TYPE_CHECKING:
    from fastapi import UploadFile as FastAPIUploadFile

from ..audit import record_audit
from ..config import Settings, get_settings
from ..db import get_db
from ..models import (
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
from ..outputs import render_estimate_pdf, render_proposal_workbook, render_technical_workbook
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
from ..security import get_current_user, require_permission, verify_csrf
from ..services.calculation import calculate_estimate_line, recalculate_estimate
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
from ..services.technical import search_for_opening, search_variants
from ..services.technical_intake import (
    TechnicalIntakeError,
    create_technical_document_draft,
)
from ..services.technical_intake_batch import (
    TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES,
    TECHNICAL_INTAKE_REGISTRATION_FIELDS,
    TechnicalIntakeBatchError,
    claim_technical_intake_batch_item,
    create_technical_intake_batch,
    get_owned_technical_intake_batch,
    get_owned_technical_intake_batch_by_client_request,
    serialize_technical_intake_batch,
)
from ..services.technical_upload_preflight import (
    TechnicalUploadPreflightError,
    preflight_technical_upload,
    require_matching_technical_upload_identity,
)
from ..services.workflow import WorkflowAction, WorkflowTransitionError
from ..services.workflow_guard import (
    PhysicalModelLockRequiredError,
    require_active_physical_model_lock,
    require_estimate_action,
)
from ..upload_ingress import TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES

router = APIRouter(prefix="/api/v1", tags=["QUANTIFIRE API v1"])
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

_TECHNICAL_UPLOAD_ALLOWED_FIELDS = frozenset(
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
_TECHNICAL_UPLOAD_MAX_FILES = 1
_TECHNICAL_UPLOAD_MAX_FIELDS = 25
_TECHNICAL_BATCH_CACHE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Pragma": "no-cache",
}


class _TechnicalUploadFormError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _technical_upload_failure(
    response: Response,
    *,
    code: str,
    status_code: int,
    retryable: bool,
    fatal: bool,
) -> dict[str, Any]:
    response.status_code = status_code
    return {
        "ok": False,
        "code": code,
        "retryable": retryable,
        "fatal": fatal,
    }


@dataclass(frozen=True, slots=True)
class _TechnicalUploadFields:
    file: UploadFile
    document_id: str
    document_type: str
    declared_source_role: str
    artifact_provenance_status: str
    evidence_scope: str
    title: str
    manufacturer: str | None
    reference: str | None
    revision: str | None
    sponsor_organisation: str | None
    issuing_organisation: str | None
    publication_date: str | None
    review_date: str | None
    expiry_date: str | None
    standards: str | None
    artifact_provenance_note: str | None
    evidence_limitations: str | None
    relationship_type: str | None
    related_document_id: str | None
    relationship_reason: str | None
    relationship_scope: str | None
    relationship_effective_date: str | None
    jurisdiction: str | None
    batch_id: str | None
    item_id: str | None


def _required_upload_text(form: FormData, name: str, *, code: str) -> str:
    values = form.getlist(name)
    if len(values) != 1 or not isinstance(values[0], str) or not values[0].strip():
        raise _TechnicalUploadFormError(code)
    return values[0]


def _optional_upload_text(form: FormData, name: str, *, code: str) -> str | None:
    values = form.getlist(name)
    if not values:
        return None
    if len(values) != 1 or not isinstance(values[0], str):
        raise _TechnicalUploadFormError(code)
    return values[0]


def _extract_technical_upload_fields(form: FormData) -> _TechnicalUploadFields:
    if any(name not in _TECHNICAL_UPLOAD_ALLOWED_FIELDS for name in form):
        raise _TechnicalUploadFormError("TECHNICAL_UPLOAD_FORM_INVALID")

    document_id = _required_upload_text(form, "document_id", code="DOCUMENT_ID_INVALID")
    document_type = _required_upload_text(
        form,
        "document_type",
        code="DOCUMENT_TYPE_INVALID",
    )
    declared_source_role = _required_upload_text(
        form,
        "declared_source_role",
        code="INTAKE_FIELD_INVALID",
    )
    artifact_provenance_status = _required_upload_text(
        form,
        "artifact_provenance_status",
        code="INTAKE_FIELD_INVALID",
    )
    evidence_scope = _required_upload_text(
        form,
        "evidence_scope",
        code="INTAKE_FIELD_INVALID",
    )
    title = _required_upload_text(form, "title", code="INTAKE_FIELD_INVALID")
    manufacturer = _optional_upload_text(
        form,
        "manufacturer",
        code="INTAKE_FIELD_INVALID",
    )
    reference = _optional_upload_text(form, "reference", code="INTAKE_FIELD_INVALID")
    revision = _optional_upload_text(form, "revision", code="INTAKE_FIELD_INVALID")
    sponsor_organisation = _optional_upload_text(
        form,
        "sponsor_organisation",
        code="INTAKE_FIELD_INVALID",
    )
    issuing_organisation = _optional_upload_text(
        form,
        "issuing_organisation",
        code="INTAKE_FIELD_INVALID",
    )
    publication_date = _optional_upload_text(
        form,
        "publication_date",
        code="INTAKE_FIELD_INVALID",
    )
    review_date = _optional_upload_text(
        form,
        "review_date",
        code="INTAKE_FIELD_INVALID",
    )
    expiry_date = _optional_upload_text(
        form,
        "expiry_date",
        code="INTAKE_FIELD_INVALID",
    )
    standards = _optional_upload_text(
        form,
        "standards",
        code="INTAKE_FIELD_INVALID",
    )
    artifact_provenance_note = _optional_upload_text(
        form,
        "artifact_provenance_note",
        code="INTAKE_FIELD_INVALID",
    )
    evidence_limitations = _optional_upload_text(
        form,
        "evidence_limitations",
        code="INTAKE_FIELD_INVALID",
    )
    relationship_type = _optional_upload_text(
        form,
        "relationship_type",
        code="INTAKE_FIELD_INVALID",
    )
    related_document_id = _optional_upload_text(
        form,
        "related_document_id",
        code="INTAKE_FIELD_INVALID",
    )
    relationship_reason = _optional_upload_text(
        form,
        "relationship_reason",
        code="INTAKE_FIELD_INVALID",
    )
    relationship_scope = _optional_upload_text(
        form,
        "relationship_scope",
        code="INTAKE_FIELD_INVALID",
    )
    relationship_effective_date = _optional_upload_text(
        form,
        "relationship_effective_date",
        code="INTAKE_FIELD_INVALID",
    )
    jurisdiction = _optional_upload_text(
        form,
        "jurisdiction",
        code="INTAKE_FIELD_INVALID",
    )
    batch_id = _optional_upload_text(
        form,
        "batch_id",
        code="INTAKE_BATCH_ID_INVALID",
    )
    item_id = _optional_upload_text(
        form,
        "item_id",
        code="INTAKE_BATCH_ITEM_ID_INVALID",
    )
    files = form.getlist("file")
    if len(files) != 1 or not isinstance(files[0], UploadFile):
        raise _TechnicalUploadFormError("UPLOAD_STREAM_INVALID")
    return _TechnicalUploadFields(
        file=files[0],
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
        standards=standards,
        artifact_provenance_note=artifact_provenance_note,
        evidence_limitations=evidence_limitations,
        relationship_type=relationship_type,
        related_document_id=related_document_id,
        relationship_reason=relationship_reason,
        relationship_scope=relationship_scope,
        relationship_effective_date=relationship_effective_date,
        jurisdiction=jurisdiction,
        batch_id=batch_id,
        item_id=item_id,
    )


def _technical_upload_registration(
    fields: _TechnicalUploadFields,
) -> dict[str, object]:
    return {
        name: getattr(fields, name)
        for name in TECHNICAL_INTAKE_REGISTRATION_FIELDS
    }


def _technical_intake_batch_error(code: str) -> TechnicalIntakeBatchError:
    return TechnicalIntakeBatchError(code)


def _strict_json_value_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON object key")
        value[key] = item
    return value


async def _read_technical_intake_batch_payload(request: Request) -> dict[str, Any]:
    content_types = request.headers.getlist("content-type")
    if len(content_types) != 1 or content_types[0].strip().lower() != "application/json":
        raise _technical_intake_batch_error("INTAKE_BATCH_CONTENT_TYPE_INVALID")

    content_lengths = request.headers.getlist("content-length")
    if len(content_lengths) != 1:
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
    raw_length = content_lengths[0]
    if not raw_length or any(character not in "0123456789" for character in raw_length):
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
    significant_length = raw_length.lstrip("0") or "0"
    if len(significant_length) > len(str(TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES)):
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
    declared_length = int(significant_length)
    if not 0 < declared_length <= TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES:
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")

    chunks: list[bytes] = []
    received_length = 0
    try:
        async for chunk in request.stream():
            if not isinstance(chunk, bytes):
                raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
            received_length += len(chunk)
            if (
                received_length > declared_length
                or received_length > TECHNICAL_INTAKE_BATCH_MAX_BODY_BYTES
            ):
                raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
            chunks.append(chunk)
    except TechnicalIntakeBatchError:
        raise
    except RuntimeError:
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID") from None
    if received_length != declared_length:
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")

    def reject_non_finite(_value: str) -> None:
        raise ValueError("Non-finite JSON number")

    try:
        payload = json.loads(
            b"".join(chunks).decode("utf-8"),
            object_pairs_hook=_strict_json_value_pairs,
            parse_constant=reject_non_finite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID") from None
    if not isinstance(payload, dict) or set(payload) != {"client_request_id", "items"}:
        raise _technical_intake_batch_error("INTAKE_BATCH_BODY_INVALID")
    return payload


def _get_or_404(db: Session, model: type[Any], entity_id: str, name: str) -> Any:
    record = db.get(model, entity_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return record


@router.get("/health", deprecated=True)
def health(db: Db, settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, Any]:
    """Deprecated legacy diagnostic contract; deployment probes must use /readyz."""

    db.execute(select(1))
    return {
        "status": "ok",
        "product": "QUANTIFIRE",
        "version": "0.1.0",
        "environment": settings.env,
        "production_findings": settings.validate_production(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    latest_revision = db.scalar(select(func.max(Product.revision)).where(Product.sku == previous.sku)) or 0
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
        select(LabourComponent).where(LabourComponent.code == payload.code, LabourComponent.revision == 1)
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
        select(func.max(EstimatingRule.version)).where(EstimatingRule.rule_code == payload.rule_code)
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
    rule.approved_at = datetime.now(timezone.utc)
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


@router.post("/technical/upload-batches", status_code=status.HTTP_201_CREATED)
async def create_technical_upload_batch(
    request: Request,
    response: Response,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_permission("technical:write"))],
) -> dict[str, Any]:
    response.headers.update(_TECHNICAL_BATCH_CACHE_HEADERS)
    csrf_values = request.headers.getlist("x-csrf-token")
    try:
        verify_csrf(request, csrf_values[0] if len(csrf_values) == 1 else None)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF_INVALID",
            headers=_TECHNICAL_BATCH_CACHE_HEADERS,
        ) from None

    try:
        payload = await _read_technical_intake_batch_payload(request)
        result = create_technical_intake_batch(
            db,
            settings,
            actor=user,
            client_request_id=payload["client_request_id"],
            items=payload["items"],
            source_ip=request.client.host if request.client else None,
        )
    except TechnicalIntakeBatchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.code,
            headers=_TECHNICAL_BATCH_CACHE_HEADERS,
        ) from None
    response.status_code = (
        status.HTTP_200_OK
        if result.idempotent_replay
        else status.HTTP_201_CREATED
    )
    return serialize_technical_intake_batch(
        result.batch,
        result.items,
        idempotent_replay=result.idempotent_replay,
    )


@router.get(
    "/technical/upload-batches/by-client-request/{client_request_id}"
)
def get_technical_upload_batch_by_client_request(
    client_request_id: str,
    response: Response,
    db: Db,
    user: Annotated[User, Depends(require_permission("technical:write"))],
) -> dict[str, Any]:
    response.headers.update(_TECHNICAL_BATCH_CACHE_HEADERS)
    try:
        batch, items = get_owned_technical_intake_batch_by_client_request(
            db,
            actor=user,
            client_request_id=client_request_id,
        )
    except TechnicalIntakeBatchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.code,
            headers=_TECHNICAL_BATCH_CACHE_HEADERS,
        ) from None
    return serialize_technical_intake_batch(batch, items)


@router.get("/technical/upload-batches/{batch_id}")
def get_technical_upload_batch(
    batch_id: str,
    response: Response,
    db: Db,
    user: Annotated[User, Depends(require_permission("technical:write"))],
) -> dict[str, Any]:
    response.headers.update(_TECHNICAL_BATCH_CACHE_HEADERS)
    try:
        batch, items = get_owned_technical_intake_batch(
            db,
            actor=user,
            batch_id=batch_id,
        )
    except TechnicalIntakeBatchError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.code,
            headers=_TECHNICAL_BATCH_CACHE_HEADERS,
        ) from None
    return serialize_technical_intake_batch(batch, items)


@router.post("/technical/documents", status_code=status.HTTP_201_CREATED)
async def upload_technical_document(
    request: Request,
    response: Response,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    user: Annotated[User, Depends(require_permission("technical:write"))],
) -> dict[str, Any]:
    csrf_values = request.headers.getlist("x-csrf-token")
    try:
        verify_csrf(request, csrf_values[0] if len(csrf_values) == 1 else None)
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF_INVALID",
        ) from None
    content_types = request.headers.getlist("content-type")
    if (
        len(content_types) != 1
        or content_types[0].partition(";")[0].strip().lower() != "multipart/form-data"
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="TECHNICAL_UPLOAD_FORM_INVALID",
        )
    try:
        preflight = preflight_technical_upload(
            request,
            db,
            settings,
            actor=user,
        )
    except TechnicalUploadPreflightError as exc:
        if exc.batch_request:
            return _technical_upload_failure(
                response,
                code=exc.code,
                status_code=exc.status_code,
                retryable=exc.retryable,
                fatal=exc.fatal,
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    is_batch_upload = preflight.is_batch
    try:
        async with request.form(
            max_files=_TECHNICAL_UPLOAD_MAX_FILES,
            max_fields=_TECHNICAL_UPLOAD_MAX_FIELDS,
            max_part_size=TECHNICAL_UPLOAD_MAX_TEXT_PART_BYTES,
        ) as form:
            fields = _extract_technical_upload_fields(form)
            batch_claim = None
            if (fields.batch_id is None) != (fields.item_id is None):
                raise _TechnicalUploadFormError(
                    "INTAKE_BATCH_ID_INVALID"
                    if fields.batch_id is None
                    else "INTAKE_BATCH_ITEM_ID_INVALID"
                )
            require_matching_technical_upload_identity(
                preflight,
                batch_id=fields.batch_id,
                item_id=fields.item_id,
            )
            if fields.item_id is not None:
                if fields.batch_id is None:
                    raise _TechnicalUploadFormError(
                        "INTAKE_BATCH_ID_INVALID"
                    )
                batch_claim = claim_technical_intake_batch_item(
                    db,
                    actor=user,
                    batch_id=fields.batch_id,
                    item_id=fields.item_id,
                    filename=fields.file.filename or "unnamed",
                    registration_snapshot=_technical_upload_registration(
                        fields
                    ),
                )
            result = create_technical_document_draft(
                db,
                settings,
                actor=user,
                upload=cast("FastAPIUploadFile", fields.file),
                document_id=fields.document_id,
                document_type=fields.document_type,
                declared_source_role=fields.declared_source_role,
                artifact_provenance_status=fields.artifact_provenance_status,
                evidence_scope=fields.evidence_scope,
                title=fields.title,
                manufacturer=fields.manufacturer,
                reference=fields.reference,
                revision=fields.revision,
                sponsor_organisation=fields.sponsor_organisation,
                issuing_organisation=fields.issuing_organisation,
                publication_date=fields.publication_date,
                review_date=fields.review_date,
                expiry_date=fields.expiry_date,
                standards=fields.standards,
                artifact_provenance_note=fields.artifact_provenance_note,
                evidence_limitations=fields.evidence_limitations,
                relationship_type=fields.relationship_type,
                related_document_id=fields.related_document_id,
                relationship_reason=fields.relationship_reason,
                relationship_scope=fields.relationship_scope,
                relationship_effective_date=fields.relationship_effective_date,
                jurisdiction=fields.jurisdiction,
                correlation_id=fields.batch_id,
                source_ip=request.client.host if request.client else None,
                batch_claim=batch_claim,
            )
    except _TechnicalUploadFormError as exc:
        if is_batch_upload:
            return _technical_upload_failure(
                response,
                code=exc.code,
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                retryable=False,
                fatal=True,
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=exc.code,
        ) from None
    except TechnicalIntakeError as exc:
        if is_batch_upload:
            return _technical_upload_failure(
                response,
                code=exc.code,
                status_code=exc.status_code,
                retryable=exc.retryable,
                fatal=exc.fatal,
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    except TechnicalIntakeBatchError as exc:
        if is_batch_upload:
            return _technical_upload_failure(
                response,
                code=exc.code,
                status_code=exc.status_code,
                retryable=exc.retryable,
                fatal=exc.fatal,
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    except TechnicalUploadPreflightError as exc:
        if exc.batch_request:
            return _technical_upload_failure(
                response,
                code=exc.code,
                status_code=exc.status_code,
                retryable=exc.retryable,
                fatal=exc.fatal,
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    except (StarletteHTTPException, MultiPartException, MultipartParseError):
        if is_batch_upload:
            return _technical_upload_failure(
                response,
                code="TECHNICAL_UPLOAD_FORM_INVALID",
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                retryable=False,
                fatal=True,
            )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="TECHNICAL_UPLOAD_FORM_INVALID",
        ) from None
    document = result.document
    stored = result.stored_file
    receipt = result.receipt if isinstance(result.receipt, dict) else None
    if result.batch_item_id is not None and receipt is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TECHNICAL_UPLOAD_RECEIPT_INVALID",
        )
    relationship = None
    if receipt is not None:
        relationship = receipt.get("relationship")
    elif result.relationship is not None:
        related = db.get(TechnicalDocument, result.relationship.related_document_id)
        if related is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="TECHNICAL_UPLOAD_RECEIPT_INVALID",
            )
        relationship = {
            "relationship_type": result.relationship.relationship_type,
            "related_document_id": related.document_id,
        }
    response.status_code = (
        status.HTTP_200_OK
        if result.idempotent_replay
        else status.HTTP_201_CREATED
    )
    payload: dict[str, Any] = {
        "id": document.id,
        "document_id": document.document_id,
        "document_type": document.document_type,
        "declared_source_role": document.declared_source_role,
        "artifact_provenance_status": document.artifact_provenance_status,
        "evidence_scope": document.evidence_scope,
        "status": document.status,
        "file_sha256": stored.sha256,
        "malware_scan_status": stored.malware_scan_status,
        "extraction_status": document.extraction_status,
        "batch_id": result.correlation_id,
        "item_id": result.batch_item_id,
        "idempotent_replay": result.idempotent_replay,
        "receipt_sha256": result.receipt_sha256,
        "status_url": receipt.get("status_url") if receipt else None,
        "metadata": document.metadata_json,
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
    return payload


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
    revision = db.scalar(select(func.max(Estimate.revision)).where(Estimate.project_id == project.id)) or 0
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
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot be modified")
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
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot be modified")
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
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot be modified")
    next_number = (db.scalar(select(func.max(EstimateLine.line_number)).where(EstimateLine.estimate_id == estimate.id)) or 0) + 1
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
        new_value={**payload.model_dump(mode="json"), "applied_markup": str(line.applied_markup), "markup_source": line.markup_source},
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
        raise HTTPException(status_code=409, detail="Locked or released estimates cannot be recalculated")
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
        raise HTTPException(status_code=409, detail={"action": "search_technical", "blockers": list(exc.blockers)}) from exc
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
    evaluations = db.scalars(select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)).all()
    blocking = [item for item in evaluations if item.result == "BLOCKED" or item.severity == "blocking_error"]
    if blocking:
        raise HTTPException(status_code=409, detail="Estimate has blocking rule results")
    try:
        snapshot = lock_snapshot(db, estimate)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
        "technical-xlsx": (f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.xlsx", render_technical_workbook),
        "proposal-xlsx": (f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Proposal.xlsx", render_proposal_workbook),
        "technical-pdf": (f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.pdf", lambda s, p: render_estimate_pdf(s, p, proposal=False)),
        "proposal-pdf": (f"QUANTIFIRE_{safe_ref}_R{estimate.revision}_Proposal.pdf", lambda s, p: render_estimate_pdf(s, p, proposal=True)),
    }
    if artifact_type not in mapping:
        raise HTTPException(status_code=404, detail="Unknown artifact type")
    filename, renderer = mapping[artifact_type]
    path = export_dir / filename
    if not path.exists():
        renderer(estimate.snapshot_json, path)
    media_type = "application/pdf" if path.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(path, filename=filename, media_type=media_type)
