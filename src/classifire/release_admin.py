from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
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
    TechnicalVariant,
)
from .security import verify_csrf
from .services.productivity import approved_productivity_manifest_rows
from .ui import _context, _require, templates

router = APIRouter(include_in_schema=False)
Db = Annotated[Session, Depends(get_db)]

SUPPORTED_TYPES = ("pricing", "technical", "rules", "labour", "products", "markups")


def _canonical_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _logical_key(record: Any, release_type: str) -> str:
    if release_type == "pricing":
        return record.pkb_entry_id
    if release_type == "rules":
        return record.rule_code
    if release_type == "labour":
        return record.code
    if release_type == "products":
        return record.sku
    if release_type == "technical":
        source = record.source_json or {}
        return source.get("original_variant_id") or record.variant_id.split("-QFREV")[0]
    return record.id


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
        drafts = db.scalars(select(PricingLibraryRecord).where(PricingLibraryRecord.status == "draft")).all()
        for draft in drafts:
            prior = db.scalars(
                select(PricingLibraryRecord).where(
                    PricingLibraryRecord.pkb_entry_id == draft.pkb_entry_id,
                    PricingLibraryRecord.status == "active",
                    PricingLibraryRecord.id != draft.id,
                )
            ).all()
            for item in prior:
                item.status = "superseded"
            draft.status = "active"
            draft.effective_date = draft.effective_date or date.today()
            activated_ids.append(draft.id)

    elif release_type == "rules":
        drafts = db.scalars(select(EstimatingRule).where(EstimatingRule.status == "draft")).all()
        for draft in drafts:
            prior = db.scalars(
                select(EstimatingRule).where(
                    EstimatingRule.rule_code == draft.rule_code,
                    EstimatingRule.status == "active",
                    EstimatingRule.id != draft.id,
                )
            ).all()
            for item in prior:
                item.status = "superseded"
                item.expiry_date = date.today()
            draft.status = "active"
            draft.effective_date = draft.effective_date or date.today()
            draft.approved_at = draft.approved_at or datetime.now(timezone.utc)
            activated_ids.append(draft.id)

    elif release_type == "labour":
        drafts = db.scalars(select(LabourComponent).where(LabourComponent.status == "draft")).all()
        for draft in drafts:
            prior = db.scalars(
                select(LabourComponent).where(
                    LabourComponent.code == draft.code,
                    LabourComponent.status == "active",
                    LabourComponent.id != draft.id,
                )
            ).all()
            for item in prior:
                item.status = "superseded"
                item.expiry_date = date.today()
            draft.status = "active"
            draft.effective_date = draft.effective_date or date.today()
            activated_ids.append(draft.id)

    elif release_type == "products":
        drafts = db.scalars(select(Product).where(Product.status == "draft")).all()
        for draft in drafts:
            prior = db.scalars(
                select(Product).where(
                    Product.sku == draft.sku,
                    Product.status == "active",
                    Product.id != draft.id,
                )
            ).all()
            for item in prior:
                item.status = "superseded"
                item.expiry_date = date.today()
            draft.status = "active"
            draft.effective_date = draft.effective_date or date.today()
            activated_ids.append(draft.id)

    # Technical records must already have passed their dedicated approval gate.
    # ProductivitySource records are approved through their dedicated API and are
    # snapshotted into Labour releases without applying a monetary rate.
    # Markup profiles are already activated through the markup workflow.
    return activated_ids


def _snapshot_records(db: Session, release_type: str) -> list[dict[str, Any]]:
    if release_type == "pricing":
        records = db.scalars(
            select(PricingLibraryRecord).where(PricingLibraryRecord.status == "active")
            .order_by(PricingLibraryRecord.pkb_entry_id, PricingLibraryRecord.created_at.desc())
        ).all()
        chosen: dict[str, PricingLibraryRecord] = {}
        for r in records:
            chosen.setdefault(r.pkb_entry_id, r)
        return [
            {
                "id": r.id,
                "key": r.pkb_entry_id,
                "entry_version": r.entry_version,
                "rate_ex_tax": str(r.rate_ex_tax),
                "source_hash": r.source_hash,
                "record_version": r.record_version,
            }
            for r in chosen.values()
        ]

    if release_type == "technical":
        records = db.scalars(
            select(TechnicalVariant).where(TechnicalVariant.status == "active")
            .order_by(TechnicalVariant.variant_id)
        ).all()
        chosen: dict[str, TechnicalVariant] = {}
        for r in records:
            key = _logical_key(r, release_type)
            existing = chosen.get(key)
            if existing is None or r.created_at > existing.created_at:
                chosen[key] = r
        return [
            {
                "id": r.id,
                "key": _logical_key(r, release_type),
                "variant_id": r.variant_id,
                "system_id": r.system_id,
                "frl": r.frl,
                "source_document_reference": r.source_document_reference,
                "source_page": r.source_page,
                "source_hash": r.source_hash,
                "record_version": r.record_version,
            }
            for r in chosen.values()
        ]

    if release_type == "rules":
        records = db.scalars(
            select(EstimatingRule).where(EstimatingRule.status == "active")
            .order_by(EstimatingRule.rule_code, EstimatingRule.version.desc())
        ).all()
        chosen: dict[str, EstimatingRule] = {}
        for r in records:
            chosen.setdefault(r.rule_code, r)
        return [
            {
                "id": r.id,
                "key": r.rule_code,
                "version": r.version,
                "conditions": r.conditions,
                "actions": r.actions,
                "record_version": r.record_version,
            }
            for r in chosen.values()
        ]

    if release_type == "labour":
        records = db.scalars(
            select(LabourComponent).where(LabourComponent.status == "active")
            .order_by(LabourComponent.code, LabourComponent.revision.desc())
        ).all()
        chosen: dict[str, LabourComponent] = {}
        for r in records:
            chosen.setdefault(r.code, r)
        labour_rows = [
            {
                "id": r.id,
                "record_type": "labour_component",
                "key": r.code,
                "revision": r.revision,
                "base_rate": str(r.base_rate),
                "default_markup": str(r.default_markup or 0),
                "record_version": r.record_version,
            }
            for r in chosen.values()
        ]
        return labour_rows + approved_productivity_manifest_rows(db)

    if release_type == "products":
        records = db.scalars(
            select(Product).where(Product.status == "active")
            .order_by(Product.sku, Product.revision.desc())
        ).all()
        chosen: dict[str, Product] = {}
        for r in records:
            chosen.setdefault(r.sku, r)
        return [
            {
                "id": r.id,
                "key": r.sku,
                "revision": r.revision,
                "base_cost": str(r.base_cost),
                "default_markup": str(r.default_markup or 0),
                "record_version": r.record_version,
            }
            for r in chosen.values()
        ]

    if release_type == "markups":
        records = db.scalars(
            select(MarkupProfile).where(MarkupProfile.status == "active")
            .order_by(MarkupProfile.scope_type, MarkupProfile.scope_id, MarkupProfile.created_at.desc())
        ).all()
        return [
            {
                "id": r.id,
                "key": f"{r.scope_type}:{r.scope_id or 'global'}",
                "product_markup": str(r.product_markup or 0),
                "material_markup": str(r.material_markup or 0),
                "labour_markup": str(r.labour_markup or 0),
                "record_version": r.record_version,
            }
            for r in records
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
    user = _require(request, db, "pricing:approve" if release_type in {"pricing", "labour", "products", "markups"} else "technical:approve" if release_type == "technical" else "rule:approve")

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
            return RedirectResponse("/releases?error=Technical+Drafts+must+be+approved+through+the+Technical+Systems+workflow+before+release", status_code=303)
        activated_ids = _activate_drafts(db, release_type)

    records = _snapshot_records(db, release_type)
    if not records:
        return RedirectResponse("/releases?error=No+eligible+records+exist+for+this+release", status_code=303)

    previous = _latest_release(db, release_type)
    payload = {
        "release_type": release_type,
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
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
        approved_at=datetime.now(timezone.utc),
        supersedes_release_id=previous.id if previous else None,
    )
    db.add(release)
    db.flush()

    # Associate newly activated Draft records with the newly published release.
    if release_type == "pricing":
        for rid in activated_ids:
            item = db.get(PricingLibraryRecord, rid)
            if item:
                item.release_id = release.id
    elif release_type == "rules":
        for rid in activated_ids:
            item = db.get(EstimatingRule, rid)
            if item:
                item.release_id = release.id
                item.approver_id = user.id
    elif release_type == "labour":
        for rid in activated_ids:
            item = db.get(LabourComponent, rid)
            if item:
                item.release_id = release.id
    elif release_type == "products":
        for rid in activated_ids:
            item = db.get(Product, rid)
            if item:
                item.release_id = release.id

    record_audit(
        db,
        actor=user,
        action="publish_release",
        entity_type="library_release",
        entity_id=release.id,
        previous_value={"release_id": previous.id, "version": previous.version} if previous else None,
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
