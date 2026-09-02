from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import record_audit
from .db import get_db
from .models import (
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    PricingLibraryRecord,
    Product,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
)
from .security import verify_csrf
from .services.technical_validity import (
    technical_document_authority_blockers,
    technical_release_source_binding,
    technical_variant_temporal_blockers,
)
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]

SUPPORTED_TYPES = ("pricing", "technical", "rules", "labour", "products", "markups")


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _technical_logical_key(record: TechnicalVariant) -> str:
    source = record.source_json or {}
    original_variant_id = source.get("original_variant_id")
    return str(original_variant_id or record.variant_id.split("-QFREV")[0])


def _latest_release(db: Session, release_type: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease)
        .where(LibraryRelease.library_type == release_type, LibraryRelease.status == "active")
        .order_by(LibraryRelease.created_at.desc())
    )


def _count_status(db: Session, model: Any) -> dict[str, int]:
    return {
        status: count
        for status, count in db.execute(
            select(model.status, func.count()).group_by(model.status)
        ).all()
    }


def _activate_drafts(db: Session, release_type: str) -> list[str]:
    activated_ids: list[str] = []

    if release_type == "pricing":
        pricing_drafts = db.scalars(
            select(PricingLibraryRecord).where(PricingLibraryRecord.status == "draft")
        ).all()
        for pricing_draft in pricing_drafts:
            pricing_prior = db.scalars(
                select(PricingLibraryRecord).where(
                    PricingLibraryRecord.pkb_entry_id == pricing_draft.pkb_entry_id,
                    PricingLibraryRecord.status == "active",
                    PricingLibraryRecord.id != pricing_draft.id,
                )
            ).all()
            for pricing_item in pricing_prior:
                pricing_item.status = "superseded"
            pricing_draft.status = "active"
            pricing_draft.effective_date = pricing_draft.effective_date or date.today()
            activated_ids.append(pricing_draft.id)

    elif release_type == "rules":
        rule_drafts = db.scalars(
            select(EstimatingRule).where(EstimatingRule.status == "draft")
        ).all()
        for rule_draft in rule_drafts:
            rule_prior = db.scalars(
                select(EstimatingRule).where(
                    EstimatingRule.rule_code == rule_draft.rule_code,
                    EstimatingRule.status == "active",
                    EstimatingRule.id != rule_draft.id,
                )
            ).all()
            for rule_item in rule_prior:
                rule_item.status = "superseded"
                rule_item.expiry_date = date.today()
            rule_draft.status = "active"
            rule_draft.effective_date = rule_draft.effective_date or date.today()
            rule_draft.approved_at = rule_draft.approved_at or datetime.now(UTC)
            activated_ids.append(rule_draft.id)

    elif release_type == "labour":
        labour_drafts = db.scalars(
            select(LabourComponent).where(LabourComponent.status == "draft")
        ).all()
        for labour_draft in labour_drafts:
            labour_prior = db.scalars(
                select(LabourComponent).where(
                    LabourComponent.code == labour_draft.code,
                    LabourComponent.status == "active",
                    LabourComponent.id != labour_draft.id,
                )
            ).all()
            for labour_item in labour_prior:
                labour_item.status = "superseded"
                labour_item.expiry_date = date.today()
            labour_draft.status = "active"
            labour_draft.effective_date = labour_draft.effective_date or date.today()
            activated_ids.append(labour_draft.id)

    elif release_type == "products":
        product_drafts = db.scalars(select(Product).where(Product.status == "draft")).all()
        for product_draft in product_drafts:
            product_prior = db.scalars(
                select(Product).where(
                    Product.sku == product_draft.sku,
                    Product.status == "active",
                    Product.id != product_draft.id,
                )
            ).all()
            for product_item in product_prior:
                product_item.status = "superseded"
                product_item.expiry_date = date.today()
            product_draft.status = "active"
            product_draft.effective_date = product_draft.effective_date or date.today()
            activated_ids.append(product_draft.id)

    # Technical records must already have passed their dedicated approval gate.
    # Markup profiles are already activated through the markup workflow.
    return activated_ids


def _snapshot_records(db: Session, release_type: str) -> list[dict[str, Any]]:
    if release_type == "pricing":
        pricing_records = db.scalars(
            select(PricingLibraryRecord)
            .where(PricingLibraryRecord.status == "active")
            .order_by(PricingLibraryRecord.pkb_entry_id, PricingLibraryRecord.created_at.desc())
        ).all()
        pricing_chosen: dict[str, PricingLibraryRecord] = {}
        for pricing_record in pricing_records:
            pricing_chosen.setdefault(pricing_record.pkb_entry_id, pricing_record)
        return [
            {
                "id": pricing_record.id,
                "key": pricing_record.pkb_entry_id,
                "entry_version": pricing_record.entry_version,
                "rate_ex_tax": str(pricing_record.rate_ex_tax),
                "source_hash": pricing_record.source_hash,
                "record_version": pricing_record.record_version,
            }
            for pricing_record in pricing_chosen.values()
        ]

    if release_type == "technical":
        technical_records = db.scalars(
            select(TechnicalVariant)
            .where(TechnicalVariant.status == "active")
            .order_by(TechnicalVariant.variant_id)
        ).all()
        bound_document_ids = {
            technical_record.technical_document_id
            for technical_record in technical_records
            if technical_record.technical_document_id
        }
        documents_by_id: dict[str, TechnicalDocument] = {}
        if bound_document_ids:
            documents_by_id = {
                document.id: document
                for document in db.scalars(
                    select(TechnicalDocument).where(TechnicalDocument.id.in_(bound_document_ids))
                ).all()
            }
        bound_stored_file_ids = {document.stored_file_id for document in documents_by_id.values()}
        stored_files_by_id: dict[str, StoredFile] = {}
        if bound_stored_file_ids:
            stored_files_by_id = {
                stored.id: stored
                for stored in db.scalars(
                    select(StoredFile).where(StoredFile.id.in_(bound_stored_file_ids))
                ).all()
            }
        source_blockers_by_document_id = {
            document.id: technical_document_authority_blockers(
                status=document.status,
                expiry_date=document.expiry_date,
                stored_file_present=(stored := stored_files_by_id.get(document.stored_file_id))
                is not None,
                stored_file_purpose=stored.purpose if stored else None,
                stored_file_scan_status=stored.malware_scan_status if stored else None,
                stored_file_immutable=stored.immutable if stored else None,
            )
            for document in documents_by_id.values()
        }
        def source_binding(technical_record: TechnicalVariant) -> dict[str, Any]:
            document = documents_by_id.get(technical_record.technical_document_id or "")
            stored = stored_files_by_id.get(document.stored_file_id) if document else None
            return technical_release_source_binding(
                technical_document_id=technical_record.technical_document_id,
                technical_document_key=document.document_id if document else None,
                technical_document_reference=document.reference if document else None,
                technical_document_revision=document.revision if document else None,
                stored_file_id=document.stored_file_id if document else None,
                stored_file_sha256=stored.sha256 if stored else None,
                stored_file_size_bytes=stored.size_bytes if stored else None,
                source_document_reference=technical_record.source_document_reference,
                source_page=technical_record.source_page,
                source_table=technical_record.source_table,
                source_figure=technical_record.source_figure,
            )

        technical_chosen: dict[str, TechnicalVariant] = {}
        for technical_record in technical_records:
            if technical_variant_temporal_blockers(
                effective_date=technical_record.effective_date,
                expiry_date=technical_record.expiry_date,
            ):
                continue
            if technical_record.technical_document_id and source_blockers_by_document_id.get(
                technical_record.technical_document_id,
                ("source_document_missing",),
            ):
                continue
            key = _technical_logical_key(technical_record)
            existing = technical_chosen.get(key)
            if existing is None or technical_record.created_at > existing.created_at:
                technical_chosen[key] = technical_record
        return [
            {
                "id": technical_record.id,
                "key": _technical_logical_key(technical_record),
                "variant_id": technical_record.variant_id,
                "system_id": technical_record.system_id,
                "frl": technical_record.frl,
                "source_document_reference": technical_record.source_document_reference,
                "source_page": technical_record.source_page,
                "source_hash": technical_record.source_hash,
                "record_version": technical_record.record_version,
                "source_binding": source_binding(technical_record),
            }
            for technical_record in technical_chosen.values()
        ]

    if release_type == "rules":
        rule_records = db.scalars(
            select(EstimatingRule)
            .where(EstimatingRule.status == "active")
            .order_by(EstimatingRule.rule_code, EstimatingRule.version.desc())
        ).all()
        rule_chosen: dict[str, EstimatingRule] = {}
        for rule_record in rule_records:
            rule_chosen.setdefault(rule_record.rule_code, rule_record)
        return [
            {
                "id": rule_record.id,
                "key": rule_record.rule_code,
                "version": rule_record.version,
                "conditions": rule_record.conditions,
                "actions": rule_record.actions,
                "record_version": rule_record.record_version,
            }
            for rule_record in rule_chosen.values()
        ]

    if release_type == "labour":
        labour_records = db.scalars(
            select(LabourComponent)
            .where(LabourComponent.status == "active")
            .order_by(LabourComponent.code, LabourComponent.revision.desc())
        ).all()
        labour_chosen: dict[str, LabourComponent] = {}
        for labour_record in labour_records:
            labour_chosen.setdefault(labour_record.code, labour_record)
        return [
            {
                "id": labour_record.id,
                "key": labour_record.code,
                "revision": labour_record.revision,
                "base_rate": str(labour_record.base_rate),
                "default_markup": str(labour_record.default_markup or 0),
                "record_version": labour_record.record_version,
            }
            for labour_record in labour_chosen.values()
        ]

    if release_type == "products":
        product_records = db.scalars(
            select(Product)
            .where(Product.status == "active")
            .order_by(Product.sku, Product.revision.desc())
        ).all()
        product_chosen: dict[str, Product] = {}
        for product_record in product_records:
            product_chosen.setdefault(product_record.sku, product_record)
        return [
            {
                "id": product_record.id,
                "key": product_record.sku,
                "revision": product_record.revision,
                "base_cost": str(product_record.base_cost),
                "default_markup": str(product_record.default_markup or 0),
                "record_version": product_record.record_version,
            }
            for product_record in product_chosen.values()
        ]

    if release_type == "markups":
        markup_records = db.scalars(
            select(MarkupProfile)
            .where(MarkupProfile.status == "active")
            .order_by(
                MarkupProfile.scope_type, MarkupProfile.scope_id, MarkupProfile.created_at.desc()
            )
        ).all()
        return [
            {
                "id": markup_record.id,
                "key": f"{markup_record.scope_type}:{markup_record.scope_id or 'global'}",
                "product_markup": str(markup_record.product_markup or 0),
                "material_markup": str(markup_record.material_markup or 0),
                "labour_markup": str(markup_record.labour_markup or 0),
                "record_version": markup_record.record_version,
            }
            for markup_record in markup_records
        ]

    raise ValueError(f"Unsupported release type: {release_type}")


@router.get("/releases", response_class=HTMLResponse)
def releases_page(request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    releases = db.scalars(
        select(LibraryRelease).order_by(LibraryRelease.created_at.desc()).limit(100)
    ).all()
    counts = {
        "pricing": _count_status(db, PricingLibraryRecord),
        "technical": _count_status(db, TechnicalVariant),
        "rules": _count_status(db, EstimatingRule),
        "labour": _count_status(db, LabourComponent),
        "products": _count_status(db, Product),
        "markups": _count_status(db, MarkupProfile),
    }
    latest = {kind: _latest_release(db, kind) for kind in SUPPORTED_TYPES}
    return templates.TemplateResponse(
        request,
        "releases.html",
        _context(
            request,
            db,
            releases=releases,
            counts=counts,
            latest=latest,
            supported_types=SUPPORTED_TYPES,
        ),
    )


@router.get("/releases/{release_id}", response_class=HTMLResponse)
def release_detail(release_id: str, request: Request, db: Db) -> HTMLResponse:
    _require(request, db, "library:read")
    release = db.get(LibraryRelease, release_id)
    if not release:
        raise HTTPException(404, "Release not found")
    manifest = release.source_manifest or {}
    records = manifest.get("records", [])
    return templates.TemplateResponse(
        request,
        "release_detail.html",
        _context(request, db, release=release, manifest=manifest, records=records),
    )


@router.post("/releases/publish")
def publish_release(
    request: Request,
    db: Db,
    csrf_token: Annotated[str, Form()],
    release_type: Annotated[str, Form()],
    version: Annotated[str, Form()],
    notes: Annotated[str, Form()] = "",
    activate_drafts: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    verify_csrf(request, csrf_token)
    user = _require(
        request,
        db,
        "pricing:approve"
        if release_type in {"pricing", "labour", "products", "markups"}
        else "technical:approve"
        if release_type == "technical"
        else "rule:approve",
    )

    if release_type not in SUPPORTED_TYPES:
        raise HTTPException(400, "Unsupported release type")

    existing = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == release_type,
            LibraryRelease.version == version,
        )
    )
    if existing:
        return RedirectResponse("/releases?error=Release+version+already+exists", status_code=303)

    activated_ids: list[str] = []
    if activate_drafts == "yes":
        if release_type == "technical":
            return RedirectResponse(
                "/releases?error=Technical+Drafts+must+be+approved+through+the+Technical+Systems+workflow+before+release",
                status_code=303,
            )
        activated_ids = _activate_drafts(db, release_type)

    records = _snapshot_records(db, release_type)
    if not records:
        return RedirectResponse(
            "/releases?error=No+eligible+records+exist+for+this+release", status_code=303
        )

    previous = _latest_release(db, release_type)
    payload = {
        "release_type": release_type,
        "version": version,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by_id": user.id,
        "record_count": len(records),
        "activated_draft_ids": activated_ids,
        "previous_release_id": previous.id if previous else None,
        "records": records,
        "notes": notes,
    }
    release_hash = _canonical_hash(payload)

    if previous:
        previous.status = "superseded"

    release = LibraryRelease(
        library_type=release_type,
        version=version,
        status="active",
        effective_date=date.today(),
        release_hash=release_hash,
        source_manifest=payload,
        notes=notes,
        created_by_id=user.id,
        approved_by_id=user.id,
        approved_at=datetime.now(UTC),
        supersedes_release_id=previous.id if previous else None,
    )
    db.add(release)
    db.flush()

    # Associate newly activated Draft records with the newly published release.
    if release_type == "pricing":
        for rid in activated_ids:
            pricing_item = db.get(PricingLibraryRecord, rid)
            if pricing_item:
                pricing_item.release_id = release.id
    elif release_type == "rules":
        for rid in activated_ids:
            rule_item = db.get(EstimatingRule, rid)
            if rule_item:
                rule_item.release_id = release.id
                rule_item.approver_id = user.id
    elif release_type == "labour":
        for rid in activated_ids:
            labour_item = db.get(LabourComponent, rid)
            if labour_item:
                labour_item.release_id = release.id
    elif release_type == "products":
        for rid in activated_ids:
            product_item = db.get(Product, rid)
            if product_item:
                product_item.release_id = release.id

    record_audit(
        db,
        actor=user,
        action="publish_release",
        entity_type="library_release",
        entity_id=release.id,
        previous_value={"release_id": previous.id, "version": previous.version}
        if previous
        else None,
        new_value={
            "release_type": release_type,
            "version": version,
            "release_hash": release_hash,
            "record_count": len(records),
            "activated_draft_count": len(activated_ids),
        },
        reason=notes or f"Publish {release_type} release {version}",
    )
    db.commit()
    return RedirectResponse(f"/releases/{release.id}?success=Release+published", status_code=303)
