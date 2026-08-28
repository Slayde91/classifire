from __future__ import annotations

import copy
import json
import secrets
from collections.abc import Iterator
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any
from urllib.parse import quote, quote_plus

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from .audit import record_audit
from .config import Settings, get_settings
from .db import get_db
from .models import (
    Approval,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
    User,
)
from .security import has_permission, verify_csrf
from .services.calculation import D
from .services.storage import (
    StoredFileBindingError,
    VerifiedStoredFileStream,
    open_verified_stored_file,
)
from .services.technical_document_lineage import (
    TECHNICAL_DOCUMENT_RELATIONSHIP_LABELS,
    TechnicalDocumentLineageError,
    create_technical_document_relationship,
)
from .services.technical_document_metadata import (
    TechnicalDocumentMetadataError,
    normalize_technical_source_registration,
    technical_current_standards_advisory,
    update_technical_document_draft_metadata,
)
from .services.technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
    TechnicalDocumentReviewError,
    approve_technical_document_review,
    reject_technical_document_review,
    request_technical_document_review_changes,
    submit_technical_document_review,
    technical_document_review_reasons,
)
from .services.technical_governance import (
    APPROVED_RELEASE_CANDIDATE,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    PENDING_TECHNICAL_REVIEW,
    TECHNICAL_REVIEW_APPROVAL_TYPE,
    TECHNICAL_REVIEW_POLICY_V3,
    TECHNICAL_VARIANT_UI_INTAKE_POLICY,
    TechnicalGovernanceError,
    latest_technical_review,
    require_technical_source_binding,
    technical_review_snapshot_hash,
    technical_variant_author_id,
)
from .services.technical_intake import TECHNICAL_DOCUMENT_TYPE_LABELS
from .services.technical_intake_draft import (
    TECHNICAL_INTAKE_EVIDENCE_ROLES,
    TECHNICAL_INTAKE_FIELD_KEYS,
    TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES,
    TECHNICAL_INTAKE_SEMANTICS,
    TECHNICAL_INTAKE_VISUAL_VERIFICATION_STATES,
    TechnicalIntakeDraftError,
    get_owned_technical_intake_draft,
    list_owned_technical_intake_drafts,
    save_technical_intake_draft,
    start_or_resume_technical_intake_draft,
)
from .services.technical_pdf_preview import (
    TECHNICAL_PDF_PREVIEW_MAX_PAGES,
    TechnicalPdfPreviewError,
    render_technical_pdf_preview_from_factory,
)
from .services.technical_retirement import (
    TechnicalRetirementError,
    current_technical_retirement,
    latest_technical_retirement,
    technical_release_record,
    technical_retirement_decision,
)
from .services.technical_variant_intake import (
    TechnicalVariantDraftInput,
    TechnicalVariantIntakeError,
    create_initial_technical_variant_draft,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]

_PREVIEW_HTTP_STATUS = {
    "PREVIEW_BUSY": 503,
    "PREVIEW_DOCUMENT_ENCRYPTED": 422,
    "PREVIEW_DOCUMENT_INVALID": 422,
    "PREVIEW_FILE_TYPE_UNSUPPORTED": 415,
    "PREVIEW_INPUT_INVALID": 422,
    "PREVIEW_OUTPUT_TOO_LARGE": 413,
    "PREVIEW_PAGE_COUNT_INVALID": 413,
    "PREVIEW_PAGE_DIMENSIONS_INVALID": 413,
    "PREVIEW_PAGE_NOT_FOUND": 404,
    "PREVIEW_RENDER_FAILED": 422,
    "PREVIEW_RENDERER_UNAVAILABLE": 503,
    "PREVIEW_SOURCE_BINDING_MISMATCH": 409,
    "PREVIEW_SOURCE_INVALID": 409,
    "PREVIEW_SOURCE_TOO_LARGE": 413,
    "PREVIEW_TIMEOUT": 504,
    "PREVIEW_WORKER_OUTPUT_INVALID": 503,
}


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value.strip() == "":
        return None
    return D(value)


def _date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _download_content_disposition(filename: str, suffix: str) -> str:
    leaf = str(filename or "").replace(chr(92), "/").rsplit("/", 1)[-1]
    leaf = "".join(character for character in leaf if 32 <= ord(character) != 127)
    leaf = leaf.strip(" .")
    if not leaf or leaf in {".", ".."}:
        leaf = f"technical-source{suffix}"
    if len(leaf) > 180:
        stem = leaf[: -len(suffix)] if suffix and leaf.lower().endswith(suffix) else leaf
        leaf = f"{stem[: max(1, 180 - len(suffix))]}{suffix}"
    fallback = "".join(
        character
        if character.isascii() and (character.isalnum() or character in "._-")
        else "_"
        for character in leaf
    ).strip("._")
    if not fallback:
        fallback = f"technical-source{suffix}"
    return (
        f'attachment; filename="{fallback}"; '
        f"filename*=UTF-8''{quote(leaf, safe='')}"
    )


def _technical_source_delivery_session(bind: Any) -> Session:
    """Own the row lock for one streamed technical-source response."""

    return Session(bind=bind, autoflush=False, expire_on_commit=False)


def _release_technical_source_delivery(
    stream: VerifiedStoredFileStream | None,
    delivery_db: Session,
) -> None:
    if delivery_db.info.get("technical_source_delivery_released") is True:
        return
    delivery_db.info["technical_source_delivery_released"] = True
    try:
        if stream is not None:
            stream.close()
    finally:
        try:
            delivery_db.rollback()
        except SQLAlchemyError:
            pass
        finally:
            delivery_db.close()


def _technical_source_delivery_chunks(
    stream: VerifiedStoredFileStream,
    delivery_db: Session,
) -> Iterator[bytes]:
    try:
        yield from stream
    finally:
        _release_technical_source_delivery(stream, delivery_db)


def _updated_exactly_one(result: Any) -> bool:
    return getattr(result, "rowcount", 0) == 1


def _technical_variant_requires_field_level_intake(
    variant: TechnicalVariant,
) -> bool:
    source = variant.source_json
    return (
        isinstance(source, dict)
        and source.get("intake_policy") == TECHNICAL_VARIANT_UI_INTAKE_POLICY
    )


def _next_revision_id(db: Session, original: TechnicalVariant) -> str:
    base = original.variant_id.split("-QFREV")[0]
    existing = db.scalars(
        select(TechnicalVariant.variant_id).where(
            TechnicalVariant.variant_id.like(f"{base}-QFREV%")
        )
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


def _json_or_none(value: str | None) -> Any:
    if value is None or value.strip() == "":
        return None
    return json.loads(value)


def _technical_intake_draft_not_found() -> HTTPException:
    return HTTPException(404, "Technical intake Draft not found")


_TECHNICAL_INTAKE_DRAFT_SAVE_ERROR_MESSAGES = {
    "TECHNICAL_INTAKE_DRAFT_STALE": (
        "This save came from an older copy of the Draft. Nothing was saved. "
        "Copy the rejected payload below, reopen the current Draft, and "
        "reconcile the changes."
    ),
    "TECHNICAL_INTAKE_DRAFT_PAYLOAD_TOO_LARGE": (
        "The submitted payload exceeded the Draft size limit. Nothing was "
        "saved, and the oversized content is not displayed."
    ),
    "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT": (
        "CLASSIFIRE could not safely complete this save. Nothing was saved. "
        "Copy the rejected payload below before reopening the current Draft."
    ),
}
_TECHNICAL_INTAKE_DRAFT_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
}


def _technical_intake_draft_save_recovery(
    request: Request,
    db: Session,
    *,
    draft_id: str,
    error_code: str,
    status_code: int,
    payload_json: str,
) -> HTMLResponse:
    try:
        encoded_payload = payload_json.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        rejected_payload = None
        payload_omitted_message = (
            "The rejected payload could not be safely encoded as UTF-8, so "
            "CLASSIFIRE will not echo it into this page."
        )
    else:
        rejected_payload = (
            payload_json
            if len(encoded_payload) <= TECHNICAL_INTAKE_PAYLOAD_MAX_BYTES
            else None
        )
        payload_omitted_message = (
            "The rejected payload was larger than the safe display limit, so "
            "CLASSIFIRE will not echo it into this page."
        )
    message = _TECHNICAL_INTAKE_DRAFT_SAVE_ERROR_MESSAGES.get(
        error_code,
        (
            "CLASSIFIRE rejected this save. Nothing was saved. Copy the "
            "rejected payload below before reopening the current Draft."
        ),
    )
    return templates.TemplateResponse(
        request,
        "technical_intake_draft_save_recovery.html",
        _context(
            request,
            db,
            draft_id=draft_id,
            error_code=error_code,
            error_message=message,
            payload_omitted_message=payload_omitted_message,
            rejected_payload=rejected_payload,
        ),
        status_code=status_code,
        headers=_TECHNICAL_INTAKE_DRAFT_PRIVATE_HEADERS,
    )


@router.post("/technical/documents/{document_db_id}/intake-draft")
def technical_intake_draft_start(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    target = f"/technical/documents/{document_db_id}"
    try:
        result = start_or_resume_technical_intake_draft(
            db,
            actor=user,
            technical_document_id=document_db_id,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalIntakeDraftError as exc:
        db.rollback()
        if exc.status_code == 404:
            raise HTTPException(404, "Technical document not found") from None
        return RedirectResponse(
            f"{target}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            f"{target}?error=TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
            status_code=303,
        )
    outcome = "resumed" if result.resumed else "started"
    return RedirectResponse(
        f"/technical/intake-drafts/{result.draft.id}?success=Draft+{outcome}",
        status_code=303,
    )


@router.get("/technical/intake-drafts/{draft_id}", response_class=HTMLResponse)
def technical_intake_draft_editor(
    draft_id: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    user = _require(request, db, "technical:write")
    try:
        draft = get_owned_technical_intake_draft(
            db,
            actor=user,
            draft_id=draft_id,
        )
    except TechnicalIntakeDraftError as exc:
        if exc.code == "TECHNICAL_INTAKE_DRAFT_NOT_FOUND":
            raise _technical_intake_draft_not_found() from None
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    document = db.get(TechnicalDocument, draft.technical_document_id)
    stored_file = db.get(StoredFile, draft.source_stored_file_id)
    if (
        document is None
        or stored_file is None
        or document.stored_file_id != stored_file.id
        or stored_file.sha256 != draft.source_sha256
        or stored_file.size_bytes != draft.source_size_bytes
    ):
        raise HTTPException(
            503,
            "TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
        )
    preview_supported = bool(
        settings.technical_pdf_preview_runtime_allowed
        and stored_file.immutable is True
        and stored_file.malware_scan_status == "clean"
        and stored_file.original_filename.casefold().endswith(".pdf")
    )
    return templates.TemplateResponse(
        request,
        "technical_intake_draft.html",
        _context(
            request,
            db,
            document=document,
            draft=draft,
            stored_file=stored_file,
            evidence_roles=sorted(TECHNICAL_INTAKE_EVIDENCE_ROLES),
            fact_states=("Provisional", "Inferred", "Unresolved"),
            field_keys=sorted(TECHNICAL_INTAKE_FIELD_KEYS),
            preview_max_pages=TECHNICAL_PDF_PREVIEW_MAX_PAGES,
            preview_runtime_enabled=settings.technical_pdf_preview_runtime_allowed,
            preview_supported=preview_supported,
            semantics=sorted(TECHNICAL_INTAKE_SEMANTICS),
            visual_verification_states=sorted(
                TECHNICAL_INTAKE_VISUAL_VERIFICATION_STATES
            ),
        ),
        headers=_TECHNICAL_INTAKE_DRAFT_PRIVATE_HEADERS,
    )


@router.post("/technical/intake-drafts/{draft_id}")
def technical_intake_draft_save(
    draft_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    expected_record_version: Annotated[str, Form()],
    payload_json: Annotated[str, Form()],
    reason: Annotated[str, Form()],
) -> Response:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    target = f"/technical/intake-drafts/{draft_id}"
    try:
        get_owned_technical_intake_draft(
            db,
            actor=user,
            draft_id=draft_id,
        )
    except TechnicalIntakeDraftError as exc:
        if exc.code == "TECHNICAL_INTAKE_DRAFT_NOT_FOUND":
            raise _technical_intake_draft_not_found() from None
        raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
    if (
        not expected_record_version.isascii()
        or not expected_record_version.isdecimal()
        or expected_record_version.startswith("0")
    ):
        return _technical_intake_draft_save_recovery(
            request,
            db,
            draft_id=draft_id,
            error_code="TECHNICAL_INTAKE_DRAFT_STALE",
            status_code=409,
            payload_json=payload_json,
        )
    try:
        result = save_technical_intake_draft(
            db,
            actor=user,
            draft_id=draft_id,
            expected_record_version=int(expected_record_version),
            payload_json=payload_json,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalIntakeDraftError as exc:
        db.rollback()
        if exc.code == "TECHNICAL_INTAKE_DRAFT_NOT_FOUND":
            raise _technical_intake_draft_not_found() from None
        return _technical_intake_draft_save_recovery(
            request,
            db,
            draft_id=draft_id,
            error_code=exc.code,
            status_code=exc.status_code,
            payload_json=payload_json,
        )
    except SQLAlchemyError:
        db.rollback()
        return _technical_intake_draft_save_recovery(
            request,
            db,
            draft_id=draft_id,
            error_code="TECHNICAL_INTAKE_DRAFT_PERSISTENCE_CONFLICT",
            status_code=503,
            payload_json=payload_json,
        )
    message = "Draft+already+saved" if result.idempotent_replay else "Draft+saved"
    return RedirectResponse(f"{target}?success={message}", status_code=303)


@router.get(
    "/technical/documents/{document_db_id}/variants/new",
    response_class=HTMLResponse,
)
def technical_variant_create_page(
    document_db_id: str,
    request: Request,
    db: Db,
) -> HTMLResponse:
    _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    stored_file = db.get(StoredFile, document.stored_file_id)
    return templates.TemplateResponse(
        request,
        "technical_variant_create.html",
        _context(
            request,
            db,
            document=document,
            stored_file=stored_file,
        ),
    )


@router.post("/technical/documents/{document_db_id}/variants")
def technical_variant_create(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    variant_id: Annotated[str, Form()],
    system_id: Annotated[str, Form()],
    source_page: Annotated[str, Form()],
    reason: Annotated[str, Form()],
    source_table: Annotated[str | None, Form()] = None,
    source_figure: Annotated[str | None, Form()] = None,
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
    effective_date: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    target = f"/technical/documents/{document_db_id}/variants/new"
    try:
        component_requirements = _json_or_none(component_requirements_json)
        labour_requirements = _json_or_none(labour_requirements_json)
    except json.JSONDecodeError:
        db.rollback()
        return RedirectResponse(
            f"{target}?error=TECHNICAL_DRAFT_JSON_INVALID",
            status_code=303,
        )
    try:
        values = TechnicalVariantDraftInput(
            variant_id=variant_id,
            system_id=system_id,
            source_page=source_page,
            reason=reason,
            source_table=source_table,
            source_figure=source_figure,
            manufacturer=manufacturer,
            product_family=product_family,
            service_type=service_type,
            service_material=service_material,
            minimum_service_size_mm=_decimal_or_none(minimum_service_size_mm),
            maximum_service_size_mm=_decimal_or_none(maximum_service_size_mm),
            permitted_service_quantity=permitted_service_quantity,
            insulation_type=insulation_type,
            insulation_thickness_mm=_decimal_or_none(insulation_thickness_mm),
            substrate_type=substrate_type,
            minimum_substrate_thickness_mm=_decimal_or_none(
                minimum_substrate_thickness_mm
            ),
            maximum_substrate_thickness_mm=_decimal_or_none(
                maximum_substrate_thickness_mm
            ),
            orientation=orientation,
            installation_face=installation_face,
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
            effective_date=_date_or_none(effective_date),
        )
    except (ArithmeticError, ValueError):
        db.rollback()
        return RedirectResponse(
            f"{target}?error=TECHNICAL_DRAFT_FORM_INVALID",
            status_code=303,
        )
    try:
        variant = create_initial_technical_variant_draft(
            db,
            actor=user,
            technical_document_id=document_db_id,
            values=values,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalVariantIntakeError as exc:
        db.rollback()
        return RedirectResponse(
            f"{target}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"{target}?error=TECHNICAL_DRAFT_VARIANT_ID_CONFLICT",
            status_code=303,
        )
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(
            f"{target}?error=TECHNICAL_DRAFT_PERSISTENCE_CONFLICT",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/variants/{variant.id}?success=Draft+technical+configuration+created",
        status_code=303,
    )


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
    counts: dict[str, int] = {
        status: count
        for status, count in db.execute(
            select(TechnicalVariant.status, func.count()).group_by(TechnicalVariant.status)
        )
    }
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
    root_id = (variant.source_json or {}).get("original_variant_id") or variant.variant_id.split(
        "-QFREV"
    )[0]
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
    retirement_review = latest_technical_retirement(db, variant.id)
    retirement_request: dict[str, Any] | None = None
    retirement_decision_reason: str | None = None
    retirement_receipt_invalid = False
    if variant.status == "active":
        active_technical_release = db.scalar(
            select(LibraryRelease).where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.status == "active",
                LibraryRelease.active_publication_slot == "technical",
            )
        )
        if active_technical_release is not None:
            try:
                current_retirement = current_technical_retirement(
                    db,
                    active_technical_release,
                    technical_release_record(active_technical_release, variant.id),
                    variant,
                )
                if current_retirement is not None:
                    retirement_review = current_retirement
            except TechnicalRetirementError:
                retirement_receipt_invalid = True
    if retirement_review is not None:
        try:
            retirement_request, retirement_decision_reason = (
                technical_retirement_decision(retirement_review)
            )
        except TechnicalRetirementError:
            retirement_receipt_invalid = True
    return templates.TemplateResponse(
        request,
        "technical_variant_detail.html",
        _context(
            request,
            db,
            variant=variant,
            history=history,
            approvals=approvals,
            retirement_review=retirement_review,
            retirement_request=retirement_request,
            retirement_decision_reason=retirement_decision_reason,
            retirement_receipt_invalid=retirement_receipt_invalid,
            field_level_intake_required=(
                _technical_variant_requires_field_level_intake(variant)
            ),
        ),
    )


@router.get("/technical/variants/{variant_db_id}/revise", response_class=HTMLResponse)
def technical_variant_revision_page(variant_db_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "technical:write")
    variant = db.get(TechnicalVariant, variant_db_id)
    if not variant:
        raise HTTPException(404, "Technical variant not found")
    documents = db.scalars(
        select(TechnicalDocument).order_by(
            TechnicalDocument.document_id,
            TechnicalDocument.created_at.desc(),
        )
    ).all()
    return templates.TemplateResponse(
        request,
        "technical_variant_edit.html",
        _context(
            request,
            db,
            variant=variant,
            documents=documents,
            component_json=json.dumps(variant.component_requirements, indent=2, ensure_ascii=False)
            if variant.component_requirements is not None
            else "",
            labour_json=json.dumps(variant.labour_requirements, indent=2, ensure_ascii=False)
            if variant.labour_requirements is not None
            else "",
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
    component_requirements_json: Annotated[str | None, Form()] = None,
    labour_requirements_json: Annotated[str | None, Form()] = None,
    hard_exclusions: Annotated[str | None, Form()] = None,
    dependencies: Annotated[str | None, Form()] = None,
    technical_document_id: Annotated[str | None, Form()] = None,
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
    if technical_document_id and not db.get(TechnicalDocument, technical_document_id):
        return RedirectResponse(
            f"/technical/variants/{variant_db_id}/revise?error=Selected+technical+document+does+not+exist",
            status_code=303,
        )
    try:
        component_requirements = _json_or_existing(
            component_requirements_json, old.component_requirements
        )
        labour_requirements = _json_or_existing(labour_requirements_json, old.labour_requirements)
    except json.JSONDecodeError:
        return RedirectResponse(
            f"/technical/variants/{variant_db_id}/revise?error=Component+and+labour+requirements+must+be+valid+JSON",
            status_code=303,
        )

    new_variant_id = _next_revision_id(db, old)
    source_json = copy.deepcopy(old.source_json or {})
    source_json.update(
        {
            "original_variant_id": (old.source_json or {}).get("original_variant_id")
            or old.variant_id.split("-QFREV")[0],
            "revision_created_by_id": user.id,
            "user_revision": True,
            "revision_reason": reason,
            "supersedes_record_id": old.id,
            "source_authority_preserved": True,
        }
    )
    new = TechnicalVariant(
        variant_id=new_variant_id,
        system_id=old.system_id,
        technical_document_id=technical_document_id or None,
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
        search_eligibility=PENDING_TECHNICAL_REVIEW,
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
        f"/technical/variants/{new.id}?success=Draft+technical+revision+created", status_code=303
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
            f"/technical/variants/{variant.id}?error=Only+Draft+or+Rejected+variants+can+be+submitted",
            status_code=303,
        )
    if _technical_variant_requires_field_level_intake(variant):
        return RedirectResponse(
            f"/technical/variants/{variant.id}"
            "?error=TECHNICAL_VARIANT_FIELD_INTAKE_REQUIRED",
            status_code=303,
        )
    variant_id = variant.id
    previous_status = variant.status
    transition = db.execute(
        update(TechnicalVariant)
        .where(
            TechnicalVariant.id == variant_id,
            TechnicalVariant.status == previous_status,
        )
        .values(status="in_review")
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(transition):
        db.rollback()
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+variant+state+changed;+refresh+before+retrying",
            status_code=303,
        )
    db.add(
        Approval(
            entity_type="technical_variant",
            entity_id=variant_id,
            approval_type=TECHNICAL_REVIEW_APPROVAL_TYPE,
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
        entity_id=variant_id,
        previous_value={"status": previous_status},
        new_value={"status": "in_review"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant_id}?success=Submitted+for+technical+review", status_code=303
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
            f"/technical/variants/{variant.id}?error=Only+submitted+In+Review+variants+can+be+approved",
            status_code=303,
        )
    if not variant.source_document_reference or not variant.source_page:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Source+document+reference+and+source+page+are+required+before+approval",
            status_code=303,
        )
    if technical_variant_author_id(variant) == user.id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=The+Draft+author+cannot+approve+their+own+candidate",
            status_code=303,
        )
    try:
        source_binding = require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
        )
    except TechnicalGovernanceError as exc:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Technical+source+evidence+blocked:+{quote_plus(exc.code)}",
            status_code=303,
        )
    approval = latest_technical_review(db, variant.id)
    if approval is None or approval.status != "pending":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=A+pending+technical+review+request+is+required",
            status_code=303,
        )
    if approval.requested_by_id == user.id:
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=The+review+requester+cannot+approve+their+own+candidate",
            status_code=303,
        )
    variant_id = variant.id
    previous_status = variant.status
    transition = db.execute(
        update(TechnicalVariant)
        .where(
            TechnicalVariant.id == variant_id,
            TechnicalVariant.status == "in_review",
        )
        .values(
            status="approved",
            search_eligibility=APPROVED_RELEASE_CANDIDATE,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(transition):
        db.rollback()
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+variant+state+changed;+refresh+before+retrying",
            status_code=303,
        )
    db.expire(variant)
    db.refresh(variant)
    snapshot_hash = technical_review_snapshot_hash(
        variant,
        source_binding,
        review_policy=TECHNICAL_REVIEW_POLICY_V3,
    )
    decided_at = datetime.now(UTC)
    approval_transition = db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "pending",
        )
        .values(
            status="approved",
            decided_by_id=user.id,
            decided_at=decided_at,
            decision_reason=reason,
            snapshot_hash=snapshot_hash,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(approval_transition):
        db.rollback()
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+review+decision+changed;+refresh+before+retrying",
            status_code=303,
        )
    record_audit(
        db,
        actor=user,
        action="approve_release_candidate",
        entity_type="technical_variant",
        entity_id=variant_id,
        previous_value={"status": previous_status},
        new_value={
            "status": "approved",
            "runtime_eligible": False,
            "approval_snapshot_hash": snapshot_hash,
            "review_policy": TECHNICAL_REVIEW_POLICY_V3,
        },
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant_id}?success=Technical+variant+approved+for+a+future+release",
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
    if variant.status != "in_review":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Only+In+Review+variants+can+be+rejected",
            status_code=303,
        )
    approval = latest_technical_review(db, variant.id)
    if approval is None or approval.status != "pending":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=A+pending+technical+review+request+is+required",
            status_code=303,
        )
    variant_id = variant.id
    previous = variant.status
    transition = db.execute(
        update(TechnicalVariant)
        .where(
            TechnicalVariant.id == variant_id,
            TechnicalVariant.status == "in_review",
        )
        .values(status="rejected")
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(transition):
        db.rollback()
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+variant+state+changed;+refresh+before+retrying",
            status_code=303,
        )
    approval_transition = db.execute(
        update(Approval)
        .where(
            Approval.id == approval.id,
            Approval.status == "pending",
        )
        .values(
            status="rejected",
            decided_by_id=user.id,
            decided_at=datetime.now(UTC),
            decision_reason=reason,
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(approval_transition):
        db.rollback()
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+review+decision+changed;+refresh+before+retrying",
            status_code=303,
        )
    record_audit(
        db,
        actor=user,
        action="reject",
        entity_type="technical_variant",
        entity_id=variant_id,
        previous_value={"status": previous},
        new_value={"status": "rejected"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant_id}?success=Technical+variant+rejected", status_code=303
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
    if variant.status == "active":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Active+variants+can+only+be+removed+through+a+governed+Technical+Authority+Registry+release",
            status_code=303,
        )
    if variant.status != "approved":
        return RedirectResponse(
            f"/technical/variants/{variant.id}?error=Only+unpublished+Approved+variants+can+be+retired",
            status_code=303,
        )
    variant_id = variant.id
    previous = variant.status
    transition = db.execute(
        update(TechnicalVariant)
        .where(
            TechnicalVariant.id == variant_id,
            TechnicalVariant.status == "approved",
        )
        .values(
            status="retired",
            expiry_date=date.today(),
        )
        .execution_options(synchronize_session=False)
    )
    if not _updated_exactly_one(transition):
        db.rollback()
        current = db.get(TechnicalVariant, variant_id)
        if current is not None and current.status == "active":
            return RedirectResponse(
                f"/technical/variants/{variant_id}?error=Active+variants+can+only+be+removed+through+a+governed+Technical+Authority+Registry+release",
                status_code=303,
            )
        return RedirectResponse(
            f"/technical/variants/{variant_id}?error=Technical+variant+state+changed;+refresh+before+retrying",
            status_code=303,
        )
    record_audit(
        db,
        actor=user,
        action="retire",
        entity_type="technical_variant",
        entity_id=variant_id,
        previous_value={"status": previous},
        new_value={"status": "retired"},
        reason=reason,
    )
    db.commit()
    return RedirectResponse(
        f"/technical/variants/{variant_id}?success=Technical+variant+retired", status_code=303
    )


@router.get("/technical/documents/{document_db_id}", response_class=HTMLResponse)
def technical_document_detail(
    document_db_id: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    user = _require(request, db, "technical:read")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    stored_file = db.get(StoredFile, document.stored_file_id)
    standards_advisory = technical_current_standards_advisory(
        document.standards
    )
    current_intake_draft = None
    if has_permission(user, "technical:write"):
        try:
            own_document_drafts = list_owned_technical_intake_drafts(
                db,
                actor=user,
                technical_document_id=document.id,
            )
        except TechnicalIntakeDraftError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.code) from None
        current_intake_draft = next(
            (
                draft
                for draft in own_document_drafts
                if stored_file is not None
                and draft.source_stored_file_id == stored_file.id
                and draft.source_sha256 == stored_file.sha256
                and draft.source_size_bytes == stored_file.size_bytes
            ),
            None,
        )
    linked = db.scalars(
        select(TechnicalVariant)
        .where(TechnicalVariant.technical_document_id == document.id)
        .order_by(TechnicalVariant.variant_id)
    ).all()
    outgoing_relationships = db.scalars(
        select(TechnicalDocumentRelationship)
        .where(TechnicalDocumentRelationship.document_id == document.id)
        .order_by(
            TechnicalDocumentRelationship.created_at,
            TechnicalDocumentRelationship.id,
        )
    ).all()
    incoming_relationships = db.scalars(
        select(TechnicalDocumentRelationship)
        .where(TechnicalDocumentRelationship.related_document_id == document.id)
        .order_by(
            TechnicalDocumentRelationship.created_at,
            TechnicalDocumentRelationship.id,
        )
    ).all()
    lineage_document_ids = {
        relationship.related_document_id for relationship in outgoing_relationships
    } | {relationship.document_id for relationship in incoming_relationships}
    lineage_documents = {
        item.id: item
        for item in db.scalars(
            select(TechnicalDocument)
            .where(TechnicalDocument.id.in_(lineage_document_ids))
            .order_by(TechnicalDocument.document_id)
        ).all()
    } if lineage_document_ids else {}
    lineage_stored_file_ids = {
        item.stored_file_id for item in lineage_documents.values()
    }
    lineage_stored_files = {
        item.id: item
        for item in db.scalars(
            select(StoredFile).where(StoredFile.id.in_(lineage_stored_file_ids))
        ).all()
    } if lineage_stored_file_ids else {}
    available_related_documents = db.scalars(
        select(TechnicalDocument)
        .where(TechnicalDocument.id != document.id)
        .order_by(TechnicalDocument.document_id)
    ).all()
    exact_content_duplicates = db.scalars(
        select(TechnicalDocument)
        .where(
            TechnicalDocument.stored_file_id == document.stored_file_id,
            TechnicalDocument.id != document.id,
        )
        .order_by(TechnicalDocument.document_id)
    ).all()
    approvals = db.scalars(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    ).all()
    approval_user_ids = {
        user_id
        for approval in approvals
        for user_id in (approval.requested_by_id, approval.decided_by_id)
        if user_id
    }
    approval_users = (
        {
            item.id: item
            for item in db.scalars(
                select(User).where(User.id.in_(approval_user_ids)).order_by(User.email)
            ).all()
        }
        if approval_user_ids
        else {}
    )
    approval_reasons: dict[str, dict[str, str | None]] = {}
    for approval in approvals:
        try:
            approval_reasons[approval.id] = technical_document_review_reasons(approval)
        except TechnicalDocumentReviewError:
            approval_reasons[approval.id] = {
                "request_reason": "Invalid retained review rationale",
                "decision_reason": None,
            }
    return templates.TemplateResponse(
        request,
        "technical_document_detail.html",
        _context(
            request,
            db,
            document=document,
            document_type_label=TECHNICAL_DOCUMENT_TYPE_LABELS.get(
                document.document_type,
                document.document_type,
            ),
            standards_advisory=standards_advisory,
            stored_file=stored_file,
            current_intake_draft=current_intake_draft,
            intake_draft_available=bool(
                document.status in {"approved", "draft", "in_review"}
                and stored_file
                and stored_file.immutable is True
                and stored_file.malware_scan_status == "clean"
                and stored_file.purpose == "technical_evidence"
                and stored_file.original_filename.casefold().endswith(".pdf")
            ),
            linked=linked,
            outgoing_relationships=outgoing_relationships,
            incoming_relationships=incoming_relationships,
            lineage_documents=lineage_documents,
            lineage_stored_files=lineage_stored_files,
            relationship_labels=TECHNICAL_DOCUMENT_RELATIONSHIP_LABELS,
            available_related_documents=available_related_documents,
            exact_content_duplicates=exact_content_duplicates,
            approvals=approvals,
            approval_users=approval_users,
            approval_reasons=approval_reasons,
            preview_supported=bool(
                settings.technical_pdf_preview_runtime_allowed
                and stored_file
                and stored_file.immutable is True
                and stored_file.malware_scan_status == "clean"
                and stored_file.original_filename.casefold().endswith(".pdf")
            ),
            preview_runtime_enabled=settings.technical_pdf_preview_runtime_allowed,
            preview_max_pages=TECHNICAL_PDF_PREVIEW_MAX_PAGES,
        ),
    )


@router.post("/technical/documents/{document_db_id}/metadata")
def technical_document_metadata_update(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    expected_record_version: Annotated[int, Form()],
    declared_source_role: Annotated[str, Form()],
    artifact_provenance_status: Annotated[str, Form()],
    evidence_scope: Annotated[str, Form()],
    reason: Annotated[str, Form()],
    sponsor_organisation: Annotated[str | None, Form()] = None,
    artifact_provenance_note: Annotated[str | None, Form()] = None,
    evidence_limitations: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "TECHNICAL_DOCUMENT_NOT_FOUND")
    try:
        registration = normalize_technical_source_registration(
            document_type=document.document_type,
            declared_source_role=declared_source_role,
            sponsor_organisation=sponsor_organisation,
            artifact_provenance_status=artifact_provenance_status,
            artifact_provenance_note=artifact_provenance_note,
            evidence_scope=evidence_scope,
            evidence_limitations=evidence_limitations,
        )
        update_technical_document_draft_metadata(
            db,
            actor=user,
            document_id=document.id,
            expected_record_version=expected_record_version,
            registration=registration,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalDocumentMetadataError as exc:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except OperationalError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=SOURCE_METADATA_STALE",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Source+classification+updated",
        status_code=303,
    )


@router.get("/technical/documents/{document_db_id}/download")
def technical_document_download(
    document_db_id: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    _require(request, db, "technical:read")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "TECHNICAL_DOCUMENT_NOT_FOUND")
    stored_file = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == document.stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not stored_file:
        raise HTTPException(409, "SOURCE_FILE_INVALID")
    if stored_file.malware_scan_status != "clean":
        raise HTTPException(409, "SOURCE_FILE_INVALID")

    stored_file_id = stored_file.id
    delivery_bind = db.get_bind()
    try:
        # Release the request-session preflight lock before a dedicated
        # response-lifetime Session reacquires it. The dedicated lock keeps
        # containment and streamed delivery linearisable even if dependency
        # cleanup timing changes between FastAPI versions.
        db.rollback()
    except SQLAlchemyError:
        raise HTTPException(503, "SOURCE_FILE_UNAVAILABLE") from None

    delivery_db = _technical_source_delivery_session(delivery_bind)
    stream: VerifiedStoredFileStream | None = None
    try:
        stored_file = delivery_db.scalar(
            select(StoredFile)
            .where(StoredFile.id == stored_file_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if stored_file is None:
            raise HTTPException(409, "SOURCE_FILE_INVALID")
        locked_document = delivery_db.scalar(
            select(TechnicalDocument)
            .where(TechnicalDocument.id == document_db_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            locked_document is None
            or locked_document.stored_file_id != stored_file.id
        ):
            raise HTTPException(409, "SOURCE_FILE_INVALID")
        stream = open_verified_stored_file(
            stored_file,
            storage_root=settings.storage_root,
            required_purpose="technical_evidence",
        )
    except StoredFileBindingError:
        _release_technical_source_delivery(stream, delivery_db)
        raise HTTPException(409, "SOURCE_FILE_INVALID") from None
    except HTTPException:
        _release_technical_source_delivery(stream, delivery_db)
        raise
    except SQLAlchemyError:
        _release_technical_source_delivery(stream, delivery_db)
        raise HTTPException(503, "SOURCE_FILE_UNAVAILABLE") from None

    headers = {
        "Cache-Control": "private, no-store",
        "Content-Disposition": _download_content_disposition(
            stored_file.original_filename,
            stream.binding.suffix,
        ),
        "Content-Length": str(stream.binding.size_bytes),
        "X-Content-Type-Options": "nosniff",
    }
    try:
        return StreamingResponse(
            _technical_source_delivery_chunks(stream, delivery_db),
            media_type="application/octet-stream",
            headers=headers,
            background=BackgroundTask(
                _release_technical_source_delivery,
                stream,
                delivery_db,
            ),
        )
    except BaseException:
        _release_technical_source_delivery(stream, delivery_db)
        raise


@router.get(
    "/technical/documents/{document_db_id}/preview/{source_sha256}/pages/{page_number}"
)
def technical_document_preview(
    document_db_id: str,
    source_sha256: str,
    page_number: str,
    request: Request,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    _require(request, db, "technical:read")
    if not settings.technical_pdf_preview_runtime_allowed:
        raise HTTPException(503, "PREVIEW_DISABLED")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "TECHNICAL_DOCUMENT_NOT_FOUND")
    stored_file = db.scalar(
        select(StoredFile)
        .where(StoredFile.id == document.stored_file_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not stored_file:
        raise HTTPException(409, "SOURCE_FILE_INVALID")
    if (
        len(source_sha256) != 64
        or not source_sha256.isascii()
        or not secrets.compare_digest(source_sha256, stored_file.sha256)
    ):
        raise HTTPException(409, "PREVIEW_SOURCE_BINDING_CHANGED")
    if (
        not isinstance(page_number, str)
        or not page_number.isascii()
        or not page_number.isdigit()
        or len(page_number) > 3
    ):
        raise HTTPException(404, "PREVIEW_PAGE_NOT_FOUND")
    parsed_page_number = int(page_number)
    if not 1 <= parsed_page_number <= TECHNICAL_PDF_PREVIEW_MAX_PAGES:
        raise HTTPException(404, "PREVIEW_PAGE_NOT_FOUND")
    if request.headers.get("range") is not None:
        raise HTTPException(
            416,
            "PREVIEW_RANGES_NOT_SUPPORTED",
            headers={"Accept-Ranges": "none", "Cache-Control": "private, no-store"},
        )
    try:
        preview = render_technical_pdf_preview_from_factory(
            lambda: open_verified_stored_file(
                stored_file,
                storage_root=settings.storage_root,
                required_purpose="technical_evidence",
            ),
            page_number=parsed_page_number,
        )
    except StoredFileBindingError:
        raise HTTPException(409, "SOURCE_FILE_INVALID") from None
    except TechnicalPdfPreviewError as exc:
        raise HTTPException(_PREVIEW_HTTP_STATUS.get(exc.code, 503), exc.code) from None
    headers = {
        "Accept-Ranges": "none",
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Disposition": (
            f'inline; filename="preview-page-{parsed_page_number:04d}.png"'
        ),
        "Content-Length": str(len(preview.png_bytes)),
        "Content-Security-Policy": "default-src 'none'; sandbox; frame-ancestors 'none'",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Classifire-Preview-Binding-SHA256": preview.binding_sha256,
        "X-Classifire-Preview-Height": str(preview.height_pixels),
        "X-Classifire-Preview-Page": str(preview.page_number),
        "X-Classifire-Preview-Page-Count": str(preview.page_count),
        "X-Classifire-Preview-PNG-SHA256": preview.png_sha256,
        "X-Classifire-Preview-Policy": preview.policy_version,
        "X-Classifire-Preview-Renderer": (
            f"{preview.renderer}/{preview.renderer_version}"
        ),
        "X-Classifire-Preview-Width": str(preview.width_pixels),
        "X-Classifire-Source-SHA256": preview.source_sha256,
        "X-Classifire-Source-Size": str(preview.source_size_bytes),
        "X-Content-Type-Options": "nosniff",
    }
    return Response(content=preview.png_bytes, media_type="image/png", headers=headers)


@router.post("/technical/documents/{document_db_id}/relationships")
def technical_document_relationship_create(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    relationship_type: Annotated[str, Form()],
    related_document_id: Annotated[str, Form()],
    reason: Annotated[str, Form()],
    scope: Annotated[str | None, Form()] = None,
    effective_date: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:write")
    # The lineage service acquires source and target locks together in global
    # document-ID order. Do not pre-lock only the source here.
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    try:
        parsed_effective_date = _date_or_none(effective_date)
        create_technical_document_relationship(
            db,
            actor=user,
            document=document,
            related_document_id=related_document_id,
            relationship_type=relationship_type,
            reason=reason,
            scope=scope,
            effective_date=parsed_effective_date,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except (TechnicalDocumentLineageError, ValueError) as exc:
        db.rollback()
        code = (
            exc.code
            if isinstance(exc, TechnicalDocumentLineageError)
            else "RELATIONSHIP_EFFECTIVE_DATE_INVALID"
        )
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(code)}",
            status_code=303,
        )
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=RELATIONSHIP_ALREADY_EXISTS",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Source+relationship+recorded",
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
    try:
        submit_technical_document_review(
            db,
            actor=user,
            document_id=document.id,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalDocumentReviewError as exc:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except OperationalError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=SOURCE_DOCUMENT_STATE_CHANGED",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Submitted+for+independent+source+review",
        status_code=303,
    )


@router.post("/technical/documents/{document_db_id}/approve")
def technical_document_approve(
    document_db_id: str,
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "Technical source review completed and approved",
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(request, db, "technical:approve")
    document = db.get(TechnicalDocument, document_db_id)
    if not document:
        raise HTTPException(404, "Technical document not found")
    try:
        approve_technical_document_review(
            db,
            actor=user,
            document_id=document.id,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalDocumentReviewError as exc:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except OperationalError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=SOURCE_REVIEW_DECISION_CHANGED",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Technical+source+document+approved",
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
    try:
        reject_technical_document_review(
            db,
            actor=user,
            document_id=document.id,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalDocumentReviewError as exc:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except OperationalError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=SOURCE_REVIEW_DECISION_CHANGED",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Technical+source+document+rejected",
        status_code=303,
    )


@router.post("/technical/documents/{document_db_id}/request-changes")
def technical_document_request_changes(
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
    try:
        request_technical_document_review_changes(
            db,
            actor=user,
            document_id=document.id,
            reason=reason,
            source_ip=request.client.host if request.client else None,
        )
        db.commit()
    except TechnicalDocumentReviewError as exc:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error={quote_plus(exc.code)}",
            status_code=303,
        )
    except OperationalError:
        db.rollback()
        return RedirectResponse(
            f"/technical/documents/{document_db_id}?error=SOURCE_REVIEW_DECISION_CHANGED",
            status_code=303,
        )
    return RedirectResponse(
        f"/technical/documents/{document_db_id}?success=Source+changes+requested",
        status_code=303,
    )
