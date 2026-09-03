from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .audit import record_audit
from .config import get_settings
from .db import get_db
from .importers.technical import PENDING_REVIEW_SEARCH_ELIGIBILITY
from .models import Approval, StoredFile, TechnicalDocument, TechnicalVariant
from .security import verify_csrf
from .services.calculation import D
from .services.storage import StoredFileBindingError, read_verified_stored_file
from .services.technical import build_technical_document_draft_metadata_from_verified_content
from .services.technical_document_lineage import technical_document_lineage_state
from .services.technical_validity import (
    technical_document_authority_blockers,
    technical_document_temporal_blockers,
    technical_variant_temporal_blockers,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    return Decimal(D(value))


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


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


def _optional_text(value: str | None) -> str | None:
    return (value or "").strip() or None


def _optional_component_requirements(value: str | None) -> dict[str, Any] | list[Any] | None:
    if not value or not value.strip():
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, (dict, list)):
        raise ValueError("Component requirements must be a JSON object or array")
    return parsed


def _optional_labour_requirements(value: str | None) -> list[str] | None:
    if not value or not value.strip():
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
        raise ValueError("Labour requirements must be a JSON array of strings")
    return parsed


def _source_locator_is_complete(
    source_document_reference: str | None,
    source_page: str | None,
) -> bool:
    return bool((source_document_reference or "").strip() and (source_page or "").strip())


def _technical_document_source_is_reviewable(db: Session, document: TechnicalDocument) -> bool:
    stored = db.get(StoredFile, document.stored_file_id)
    if not stored:
        return False
    try:
        read_verified_stored_file(
            stored,
            storage_root=get_settings().storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError:
        return False
    return True


_SOURCE_AUTHORITY_MESSAGES = {
    "source_document_missing": "The bound source document record is missing.",
    "source_document_not_approved": "The source document is not approved.",
    "source_document_expired": "The source document has expired.",
    "source_file_missing": "The retained source file record is missing.",
    "source_file_wrong_purpose": "The retained file is not registered as technical evidence.",
    "source_file_not_immutable": "The retained file is not marked immutable.",
    "source_file_not_clean": "The retained file does not have a clean scan state.",
}


def _technical_document_source_authority(
    db: Session,
    document: TechnicalDocument,
) -> tuple[str, tuple[str, ...]]:
    """Return the read-only current-authority display state for one document.

    This reuses the current metadata guard without reading source bytes or
    changing a document, variant, approval, or release state.
    """
    stored_file = db.get(StoredFile, document.stored_file_id)
    blockers = technical_document_authority_blockers(
        status=document.status,
        expiry_date=document.expiry_date,
        stored_file_present=stored_file is not None,
        stored_file_purpose=stored_file.purpose if stored_file else None,
        stored_file_scan_status=stored_file.malware_scan_status if stored_file else None,
        stored_file_immutable=stored_file.immutable if stored_file else None,
    )
    return ("blocked" if blockers else "current"), blockers


def _technical_variant_source_authority(
    db: Session,
    variant: TechnicalVariant,
    linked_document: TechnicalDocument | None,
) -> tuple[str, tuple[str, ...]]:
    """Return the read-only current-authority display state for one variant.

    This reuses the current metadata guard without reading source bytes or
    changing a document, variant, approval, or release state.
    """
    if not variant.technical_document_id:
        return "unbound", ()
    if not linked_document:
        return "blocked", ("source_document_missing",)
    return _technical_document_source_authority(db, linked_document)


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
    counts: dict[str, int] = {}
    for row in db.execute(
        select(TechnicalVariant.status, func.count()).group_by(TechnicalVariant.status)
    ).all():
        counts[row[0]] = row[1]
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
    original_variant_id = (variant.source_json or {}).get("original_variant_id")
    root_id = original_variant_id or variant.variant_id.split("-QFREV")[0]
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
    history_document_ids = {
        row.technical_document_id for row in history if row.technical_document_id
    }
    history_documents_by_id: dict[str, TechnicalDocument] = {}
    if history_document_ids:
        history_documents_by_id = {
            document.id: document
            for document in db.scalars(
                select(TechnicalDocument).where(
                    TechnicalDocument.id.in_(history_document_ids)
                )
            ).all()
        }
    approvals = db.scalars(
        select(Approval)
        .where(Approval.entity_type == "technical_variant", Approval.entity_id == variant.id)
        .order_by(Approval.created_at.desc())
    ).all()
    linked_document = (
        db.get(TechnicalDocument, variant.technical_document_id)
        if variant.technical_document_id
        else None
    )
    source_authority_state, source_authority_blockers = _technical_variant_source_authority(
        db,
        variant,
        linked_document,
    )
    source_document_reference = (variant.source_document_reference or "").strip()
    matching_document = (
        db.scalar(
            select(TechnicalDocument).where(
                TechnicalDocument.document_id == source_document_reference
            )
        )
        if not linked_document and source_document_reference
        else None
    )
    return templates.TemplateResponse(
        request,
        "technical_variant_detail.html",
        _context(
            request,
            db,
            variant=variant,
            history=history,
            history_documents_by_id=history_documents_by_id,
            approvals=approvals,
            linked_document=linked_document,
            matching_document=matching_document,
            source_authority_state=source_authority_state,
            source_authority_messages=tuple(
                _SOURCE_AUTHORITY_MESSAGES.get(
                    blocker,
                    "The bound source is not currently eligible.",
                )
                for blocker in source_authority_blockers
            ),
        ),
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
            component_json=(
                json.dumps(variant.component_requirements, indent=2, ensure_ascii=False)
                if variant.component_requirements is not None
                else ""
            ),
            labour_json=(
                json.dumps(variant.labour_requirements, indent=2, ensure_ascii=False)
                if variant.labour_requirements is not None
                else ""
            ),
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
        component_requirements = _json_or_existing(
            component_requirements_json,
            old.component_requirements,
        )
        labour_requirements = _json_or_existing(
            labour_requirements_json,
            old.labour_requirements,
        )
    except json.JSONDecodeError:
        return RedirectResponse(
            f"/technical/variants/{variant_db_id}/revise?error="
            "Component+and+labour+requirements+must+be+valid+JSON",
            status_code=303,
        )

    source_document_reference = (source_document_reference or "").strip() or None
    source_page = (source_page or "").strip() or None
    if not _source_locator_is_complete(source_document_reference, source_page):
        return RedirectResponse(
            f"/technical/variants/{variant_db_id}/revise?error="
            "Source+document+reference+and+source+page+are+required+to+create+a+revision",
            status_code=303,
        )
    new_variant_id = _next_revision_id(db, old)
    inherited_document = (
        db.get(TechnicalDocument, old.technical_document_id)
        if old.technical_document_id
        else None
    )
    inherited_document_id = (
        inherited_document.id
        if inherited_document
        and inherited_document.document_id == source_document_reference
        else None
    )
    preserve_document_binding = inherited_document_id is not None
    source_json = copy.deepcopy(old.source_json or {})
    source_json.update(
        {
            "original_variant_id": (
                (old.source_json or {}).get("original_variant_id")
                or old.variant_id.split("-QFREV")[0]
            ),
            "user_revision": True,
            "revision_reason": reason,
            "supersedes_record_id": old.id,
            "source_authority_preserved": True,
            "technical_document_binding": {
                "previous_document_id": old.technical_document_id,
                "inherited": preserve_document_binding,
                "requires_exact_rebinding": bool(old.technical_document_id)
                and not preserve_document_binding,
            },
        }
    )
    new = TechnicalVariant(
        variant_id=new_variant_id,
        system_id=old.system_id,
        technical_document_id=inherited_document_id,
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
        decision_reason=(
            "Draft technical revision requires authorised technical review before activation."
        ),
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
    return RedirectResponse(
        f"/technical/variants/{new.id}?success=Draft+technical+revision+created",
        status_code=303,
    )


@router.post("/technical/variants/{variant_db_id}/bind-source-document")
def technical_variant_bind_source_document(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Bind exact retained technical source document",
) -> RedirectResponse:
    """Bind a Draft candidate to its exact retained source without approving it."""
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    if variant.status not in {"draft", "rejected"}:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Only+Draft+or+Rejected+variants+can+bind+a+source+document",
            status_code=303,
        )
    if variant.technical_document_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Technical+variant+already+has+a+bound+source+document",
            status_code=303,
        )
    source_document_reference = (variant.source_document_reference or "").strip()
    if not source_document_reference:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Source+document+reference+is+required+before+binding",
            status_code=303,
        )
    document = db.scalar(
        select(TechnicalDocument).where(TechnicalDocument.document_id == source_document_reference)
    )
    if not document:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Exact+retained+technical+source+document+was+not+found",
            status_code=303,
        )
    if not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Exact+technical+source+file+must+be+clean+and+unchanged+before+binding",
            status_code=303,
        )
    stored = db.get(StoredFile, document.stored_file_id)
    if not stored:
        raise RuntimeError("Verified technical document unexpectedly has no stored file")
    variant.technical_document_id = document.id
    record_audit(
        db,
        actor=user,
        action="bind_source_document",
        entity_type="technical_variant",
        entity_id=variant.id,
        previous_value={
            "technical_document_id": None,
            "source_document_reference": source_document_reference,
        },
        new_value={
            "technical_document_id": document.id,
            "document_id": document.document_id,
            "stored_file_sha256": stored.sha256,
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Exact+technical+source+document+bound",
        status_code=303,
    )


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
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Only+Draft+or+Rejected+variants+can+be+submitted",
            status_code=303,
        )
    if not _source_locator_is_complete(
        variant.source_document_reference,
        variant.source_page,
    ):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Source+document+reference+and+source+page+are+required+before+review",
            status_code=303,
        )
    if not variant.technical_document_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Exact+retained+technical+source+document+must+be+bound+before+review",
            status_code=303,
        )
    document = db.get(TechnicalDocument, variant.technical_document_id)
    if not document or not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Bound+technical+source+file+must+be+clean+and+unchanged+before+review",
            status_code=303,
        )
    if (variant.source_document_reference or "").strip() != document.document_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Bound+technical+source+document+must+match+the+source+document+reference",
            status_code=303,
        )
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
        approval.requested_at = datetime.now(UTC)
        approval.decision_reason = reason
    else:
        db.add(
            Approval(
                entity_type="technical_variant",
                entity_id=variant.id,
                approval_type="technical_activation",
                status="pending",
                requested_by_id=user.id,
                decision_reason=reason,
            )
        )
    record_audit(
        db,
        actor=user,
        action="submit_review",
        entity_type="technical_variant",
        entity_id=variant.id,
        previous_value={"status": "draft"},
        new_value={"status": "in_review"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Submitted+for+technical+review",
        status_code=303,
    )


@router.post("/technical/variants/{variant_db_id}/approve")
def technical_variant_approve(
    variant_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Technical review completed and approved",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    if variant.status != "in_review":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Only+In+Review+variants+can+be+approved",
            status_code=303,
        )
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
            Approval.approval_type == "technical_activation",
        )
        .order_by(Approval.created_at.desc())
    )
    if not approval or approval.status != "pending" or not approval.requested_by_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Pending+technical+approval+request+required",
            status_code=303,
        )
    if approval.requested_by_id == user.id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Technical+requester+and+approver+must+be+different+users",
            status_code=303,
        )
    if not _source_locator_is_complete(
        variant.source_document_reference,
        variant.source_page,
    ):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Source+document+reference+and+source+page+are+required+before+approval",
            status_code=303,
        )
    if not variant.technical_document_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Technical+variant+must+be+bound+to+an+approved+technical+document",
            status_code=303,
        )
    document = db.get(TechnicalDocument, variant.technical_document_id)
    if not document or document.status != "approved":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Linked+technical+document+must+be+approved",
            status_code=303,
        )
    if technical_document_temporal_blockers(expiry_date=document.expiry_date):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Linked+technical+document+has+expired",
            status_code=303,
        )
    if not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Linked+technical+document+source+must+be+clean+and+unchanged",
            status_code=303,
        )
    if (variant.source_document_reference or "").strip() != document.document_id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error="
            "Linked+technical+document+must+match+the+source+document+reference",
            status_code=303,
        )
    temporal_blockers = technical_variant_temporal_blockers(
        effective_date=variant.effective_date,
        expiry_date=variant.expiry_date,
    )
    if "not_yet_effective" in temporal_blockers:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Technical+variant+is+not+yet+effective",
            status_code=303,
        )
    if "expired" in temporal_blockers:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Technical+variant+has+expired",
            status_code=303,
        )
    previous_status = variant.status
    if variant.supersedes_id:
        prior = db.get(TechnicalVariant, variant.supersedes_id)
        if prior and prior.status == "active":
            prior.status = "superseded"
    variant.status = "active"
    variant.expert_review_required = False
    variant.effective_date = variant.effective_date or date.today()
    approval.status = "approved"
    approval.decided_by_id = user.id
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = reason
    record_audit(
        db,
        actor=user,
        action="approve",
        entity_type="technical_variant",
        entity_id=variant.id,
        previous_value={"status": previous_status},
        new_value={"status": "active"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Technical+variant+approved+and+activated",
        status_code=303,
    )


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
        approval.status = "rejected"
        approval.decided_by_id = user.id
        approval.decided_at = datetime.now(UTC)
        approval.decision_reason = reason
    record_audit(
        db,
        actor=user,
        action="reject",
        entity_type="technical_variant",
        entity_id=variant.id,
        previous_value={"status": previous},
        new_value={"status": "rejected"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Technical+variant+rejected",
        status_code=303,
    )


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
    record_audit(
        db,
        actor=user,
        action="retire",
        entity_type="technical_variant",
        entity_id=variant.id,
        previous_value={"status": previous},
        new_value={"status": "retired"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Technical+variant+retired",
        status_code=303,
    )


@router.get("/technical/documents/{document_db_id}", response_class=HTMLResponse)
def technical_document_detail(document_db_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "technical:read")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    source_authority_state, source_authority_blockers = _technical_document_source_authority(
        db,
        document,
    )
    source_lineage_state, source_lineage = technical_document_lineage_state(document)
    predecessor = (
        db.get(TechnicalDocument, document.supersedes_document_id)
        if source_lineage_state == "verified" and document.supersedes_document_id
        else None
    )
    linked = db.scalars(
        select(TechnicalVariant)
        .where(TechnicalVariant.technical_document_id == document.id)
        .order_by(TechnicalVariant.variant_id)
    ).all()
    approvals = db.scalars(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == "technical_document_review",
        )
        .order_by(Approval.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "technical_document_detail.html",
        _context(
            request,
            db,
            document=document,
            linked=linked,
            approvals=approvals,
            source_authority_state=source_authority_state,
            source_lineage_state=source_lineage_state,
            source_lineage=source_lineage,
            predecessor=predecessor,
            source_authority_messages=tuple(
                _SOURCE_AUTHORITY_MESSAGES.get(
                    blocker,
                    "The source document is not currently eligible.",
                )
                for blocker in source_authority_blockers
            ),
        ),
    )


@router.post("/technical/documents/{document_db_id}/refresh-draft-metadata")
def technical_document_refresh_draft_metadata(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Refresh Draft candidate metadata from clean retained source",
) -> RedirectResponse:
    """Refresh Draft-only candidate metadata from verified retained bytes.

    This deliberately does not change document review, variant eligibility, or
    technical release authority.
    """
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    destination = f"/technical/documents/{document.id}"
    if document.status != "draft":
        return RedirectResponse(
            f"{destination}?error=Only+Draft+technical+documents+can+refresh+candidate+metadata",
            status_code=303,
        )
    stored = db.get(StoredFile, document.stored_file_id)
    if not stored:
        return RedirectResponse(
            f"{destination}?error=Technical+source+file+is+missing",
            status_code=303,
        )
    try:
        verified = read_verified_stored_file(
            stored,
            storage_root=get_settings().storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError:
        return RedirectResponse(
            f"{destination}?error=Technical+source+file+must+be+clean+and+unchanged",
            status_code=303,
        )
    previous_status = document.extraction_status
    metadata = build_technical_document_draft_metadata_from_verified_content(
        content=verified.content,
        filename=stored.original_filename,
    )
    document.metadata_json = metadata
    document.extraction_status = metadata.get("extraction_status", "not_started")
    record_audit(
        db,
        actor=user,
        action="refresh_draft_metadata",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"extraction_status": previous_status},
        new_value={
            "extraction_status": document.extraction_status,
            "source_sha256": verified.sha256,
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"{destination}?success=Draft+candidate+metadata+refreshed+from+clean+retained+source",
        status_code=303,
    )


@router.get("/technical/documents/{document_db_id}/materialise", response_class=HTMLResponse)
def technical_document_materialisation_page(
    document_db_id: str,
    request: Request,
    db: Db,
) -> HTMLResponse:
    _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    if document.status not in {"draft", "approved"}:
        raise HTTPException(
            409,
            "Only Draft or approved technical documents can materialise Draft variants",
        )
    if not _technical_document_source_is_reviewable(db, document):
        raise HTTPException(409, "Technical source file must be clean and unchanged")
    return templates.TemplateResponse(
        request,
        "technical_document_materialisation.html",
        _context(request, db, document=document),
    )


@router.post("/technical/documents/{document_db_id}/materialise")
def technical_document_materialise(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    variant_id: Annotated[str, Form()],
    system_id: Annotated[str, Form()],
    source_page: Annotated[str, Form()],
    manufacturer: Annotated[str | None, Form()] = None,
    product_family: Annotated[str | None, Form()] = None,
    service_type: Annotated[str | None, Form()] = None,
    service_material: Annotated[str | None, Form()] = None,
    minimum_service_size_mm: Annotated[str | None, Form()] = None,
    maximum_service_size_mm: Annotated[str | None, Form()] = None,
    permitted_service_quantity: Annotated[str | None, Form()] = None,
    insulation_type: Annotated[str | None, Form()] = None,
    insulation_thickness_mm: Annotated[str | None, Form()] = None,
    substrate_type: Annotated[str | None, Form()] = None,
    minimum_substrate_thickness_mm: Annotated[str | None, Form()] = None,
    maximum_substrate_thickness_mm: Annotated[str | None, Form()] = None,
    orientation: Annotated[str | None, Form()] = None,
    installation_face: Annotated[str | None, Form()] = None,
    opening_type: Annotated[str | None, Form()] = None,
    opening_dimensions: Annotated[str | None, Form()] = None,
    annular_gap_min_mm: Annotated[str | None, Form()] = None,
    annular_gap_max_mm: Annotated[str | None, Form()] = None,
    service_spacing_rules: Annotated[str | None, Form()] = None,
    edge_distance_rules: Annotated[str | None, Form()] = None,
    support_rules: Annotated[str | None, Form()] = None,
    fixing_rules: Annotated[str | None, Form()] = None,
    component_requirements_json: Annotated[str | None, Form()] = None,
    labour_requirements_json: Annotated[str | None, Form()] = None,
    hard_exclusions: Annotated[str | None, Form()] = None,
    dependencies: Annotated[str | None, Form()] = None,
    frl: Annotated[str | None, Form()] = None,
    jurisdiction: Annotated[str | None, Form()] = None,
    source_table: Annotated[str | None, Form()] = None,
    source_figure: Annotated[str | None, Form()] = None,
    reason: Annotated[str, Form()] = "Materialise retained technical source as Draft candidate",
) -> RedirectResponse:
    """Create a source-bound Draft candidate without granting technical authority."""
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    destination = f"/technical/documents/{document.id}/materialise"
    if document.status not in {"draft", "approved"}:
        return RedirectResponse(
            f"{destination}?error=Only+Draft+or+approved+technical+documents+can+materialise+Draft+variants",
            status_code=303,
        )
    if not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"{destination}?error=Technical+source+file+must+be+clean+and+unchanged",
            status_code=303,
        )
    materialised_variant_id = _optional_text(variant_id)
    materialised_system_id = _optional_text(system_id)
    materialised_source_page = _optional_text(source_page)
    if not materialised_variant_id or not materialised_system_id or not materialised_source_page:
        return RedirectResponse(
            f"{destination}?error=Variant+ID,+system+ID,+and+source+page+are+required",
            status_code=303,
        )
    if db.scalar(
        select(TechnicalVariant.id).where(
            TechnicalVariant.variant_id == materialised_variant_id
        )
    ):
        return RedirectResponse(
            f"{destination}?error=Technical+variant+ID+already+exists",
            status_code=303,
        )
    try:
        component_requirements = _optional_component_requirements(component_requirements_json)
        labour_requirements = _optional_labour_requirements(labour_requirements_json)
        numeric_fields = {
            "minimum_service_size_mm": _decimal_or_none(minimum_service_size_mm),
            "maximum_service_size_mm": _decimal_or_none(maximum_service_size_mm),
            "insulation_thickness_mm": _decimal_or_none(insulation_thickness_mm),
            "minimum_substrate_thickness_mm": _decimal_or_none(
                minimum_substrate_thickness_mm
            ),
            "maximum_substrate_thickness_mm": _decimal_or_none(
                maximum_substrate_thickness_mm
            ),
            "annular_gap_min_mm": _decimal_or_none(annular_gap_min_mm),
            "annular_gap_max_mm": _decimal_or_none(annular_gap_max_mm),
        }
    except (ArithmeticError, json.JSONDecodeError, ValueError):
        return RedirectResponse(
            f"{destination}?error=Numeric+fields+must+be+valid+and+requirements+must+use+the+documented+JSON+shapes",
            status_code=303,
        )
    stored = db.get(StoredFile, document.stored_file_id)
    if not stored:
        raise RuntimeError("Verified technical document unexpectedly has no stored file")
    source_table = _optional_text(source_table)
    source_figure = _optional_text(source_figure)
    variant = TechnicalVariant(
        variant_id=materialised_variant_id,
        system_id=materialised_system_id,
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page=materialised_source_page,
        source_table=source_table,
        source_figure=source_figure,
        manufacturer=_optional_text(manufacturer) or document.manufacturer,
        product_family=_optional_text(product_family),
        service_type=_optional_text(service_type),
        service_material=_optional_text(service_material),
        minimum_service_size_mm=numeric_fields["minimum_service_size_mm"],
        maximum_service_size_mm=numeric_fields["maximum_service_size_mm"],
        permitted_service_quantity=_optional_text(permitted_service_quantity),
        insulation_type=_optional_text(insulation_type),
        insulation_thickness_mm=numeric_fields["insulation_thickness_mm"],
        substrate_type=_optional_text(substrate_type),
        minimum_substrate_thickness_mm=numeric_fields["minimum_substrate_thickness_mm"],
        maximum_substrate_thickness_mm=numeric_fields["maximum_substrate_thickness_mm"],
        orientation=_optional_text(orientation),
        installation_face=_optional_text(installation_face),
        opening_type=_optional_text(opening_type),
        opening_dimensions=_optional_text(opening_dimensions),
        annular_gap_min_mm=numeric_fields["annular_gap_min_mm"],
        annular_gap_max_mm=numeric_fields["annular_gap_max_mm"],
        service_spacing_rules=_optional_text(service_spacing_rules),
        edge_distance_rules=_optional_text(edge_distance_rules),
        support_rules=_optional_text(support_rules),
        fixing_rules=_optional_text(fixing_rules),
        component_requirements=component_requirements,
        labour_requirements=labour_requirements,
        hard_exclusions=_optional_text(hard_exclusions),
        dependencies=_optional_text(dependencies),
        frl=_optional_text(frl),
        jurisdiction=_optional_text(jurisdiction),
        search_eligibility=PENDING_REVIEW_SEARCH_ELIGIBILITY,
        expert_review_required=True,
        status="draft",
        source_hash=stored.sha256,
        source_json={
            "intake_policy": "technical-document-draft-materialisation-v1",
            "source_kind": "manual_transcription_from_retained_technical_document",
            "technical_document": {
                "id": document.id,
                "document_id": document.document_id,
                "stored_file_id": stored.id,
                "sha256": stored.sha256,
                "size_bytes": stored.size_bytes,
            },
            "source_locator": {
                "page": materialised_source_page,
                "table": source_table,
                "figure": source_figure,
            },
        },
    )
    db.add(variant)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"{destination}?error=Technical+variant+ID+already+exists",
            status_code=303,
        )
    record_audit(
        db,
        actor=user,
        action="materialise_draft",
        entity_type="technical_variant",
        entity_id=variant.id,
        new_value={
            "variant_id": variant.variant_id,
            "system_id": variant.system_id,
            "status": variant.status,
            "technical_document_id": document.id,
            "source_document_reference": document.document_id,
            "source_page": materialised_source_page,
            "source_sha256": stored.sha256,
            "search_eligibility": variant.search_eligibility,
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Source-bound+Draft+technical+variant+created",
        status_code=303,
    )

@router.post("/technical/documents/{document_db_id}/submit-review")
def technical_document_submit_review(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Submit technical source document for review",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    if document.status not in {"draft", "rejected"}:
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Only+Draft+or+Rejected+documents+can+be+submitted",
            status_code=303,
        )
    if not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Technical+source+file+must+be+clean+and+unchanged+before+review",
            status_code=303,
        )
    previous_status = document.status
    document.status = "in_review"
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == "technical_document_review",
        )
        .order_by(Approval.created_at.desc())
    )
    if approval:
        approval.status = "pending"
        approval.requested_by_id = user.id
        approval.requested_at = datetime.now(UTC)
        approval.decided_by_id = None
        approval.decided_at = None
        approval.decision_reason = reason
    else:
        db.add(
            Approval(
                entity_type="technical_document",
                entity_id=document.id,
                approval_type="technical_document_review",
                status="pending",
                requested_by_id=user.id,
                decision_reason=reason,
            )
        )
    record_audit(
        db,
        actor=user,
        action="submit_review",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": previous_status},
        new_value={"status": "in_review"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/documents/{document.id}?success=Submitted+for+technical+review",
        status_code=303,
    )


@router.post("/technical/documents/{document_db_id}/approve")
def technical_document_approve(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Technical source document reviewed",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    if document.status != "in_review":
        return RedirectResponse(
            f"/technical/documents/{document.id}?error=Only+In+Review+documents+can+be+approved",
            status_code=303,
        )
    if technical_document_temporal_blockers(expiry_date=document.expiry_date):
        return RedirectResponse(
            f"/technical/documents/{document.id}?error=Technical+source+document+has+expired",
            status_code=303,
        )
    if not _technical_document_source_is_reviewable(db, document):
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Technical+source+file+must+be+clean+and+unchanged+before+review",
            status_code=303,
        )
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == "technical_document_review",
        )
        .order_by(Approval.created_at.desc())
    )
    if not approval or approval.status != "pending" or not approval.requested_by_id:
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Pending+technical+document+review+required",
            status_code=303,
        )
    if approval.requested_by_id == user.id:
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Technical+document+requester+and+approver+must+be+different+users",
            status_code=303,
        )
    previous = document.status
    document.status = "approved"
    document.reviewed_by_id = user.id
    document.approved_by_id = user.id
    document.approved_at = datetime.now(UTC)
    approval.status = "approved"
    approval.decided_by_id = user.id
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = reason
    record_audit(
        db,
        actor=user,
        action="approve",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": previous},
        new_value={"status": "approved"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/documents/{document.id}?success=Technical+source+document+approved",
        status_code=303,
    )


@router.post("/technical/documents/{document_db_id}/reject")
def technical_document_reject(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    if document.status != "in_review":
        return RedirectResponse(
            f"/technical/documents/{document.id}?error=Only+In+Review+documents+can+be+rejected",
            status_code=303,
        )
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == "technical_document_review",
        )
        .order_by(Approval.created_at.desc())
    )
    if not approval or approval.status != "pending" or not approval.requested_by_id:
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Pending+technical+document+review+required",
            status_code=303,
        )
    if approval.requested_by_id == user.id:
        return RedirectResponse(
            f"/technical/documents/{document.id}?error="
            "Technical+document+requester+and+approver+must+be+different+users",
            status_code=303,
        )
    previous = document.status
    document.status = "rejected"
    document.reviewed_by_id = user.id
    document.approved_by_id = None
    document.approved_at = None
    approval.status = "rejected"
    approval.decided_by_id = user.id
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = reason
    record_audit(
        db,
        actor=user,
        action="reject",
        entity_type="technical_document",
        entity_id=document.id,
        previous_value={"status": previous},
        new_value={"status": "rejected"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/documents/{document.id}?success=Technical+source+document+rejected",
        status_code=303,
    )
