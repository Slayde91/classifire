from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Estimate,
    EstimatingRule,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    PricingLibraryRecord,
    Product,
)

PIN_FIELDS = {
    "pricing": "pricing_release_id",
    "technical": "technical_release_id",
    "rules": "rules_release_id",
    "products": "products_release_id",
    "labour": "labour_release_id",
    "markups": "markups_release_id",
}


class ReleaseScopeError(ValueError):
    pass


def _manifest_hash(manifest: dict[str, Any]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def pinned_release(db: Session, estimate: Estimate, library_type: str) -> LibraryRelease:
    field = PIN_FIELDS.get(library_type)
    if not field:
        raise ReleaseScopeError(f"Unsupported pinned library type: {library_type}")
    release_id = getattr(estimate, field, None)
    if not release_id:
        raise ReleaseScopeError(f"Estimate has no pinned {library_type} release.")
    release = db.get(LibraryRelease, release_id)
    if not release:
        raise ReleaseScopeError(f"Pinned {library_type} release record is missing.")
    if release.library_type != library_type:
        raise ReleaseScopeError(f"Pinned release type mismatch for {library_type}.")
    if not release.release_hash or not release.source_manifest:
        raise ReleaseScopeError(f"Pinned {library_type} release is not immutable.")
    if _manifest_hash(release.source_manifest) != release.release_hash:
        raise ReleaseScopeError(f"Pinned {library_type} release hash does not match its manifest.")
    return release


def release_record_ids(db: Session, estimate: Estimate, library_type: str) -> set[str]:
    release = pinned_release(db, estimate, library_type)
    records = (release.source_manifest or {}).get("records", [])
    ids = {str(item["id"]) for item in records if isinstance(item, dict) and item.get("id")}
    if not ids:
        raise ReleaseScopeError(f"Pinned {library_type} release contains no record identifiers.")
    return ids


def pinned_product(db: Session, estimate: Estimate, sku: str) -> Product:
    ids = release_record_ids(db, estimate, "products")
    item = db.scalar(select(Product).where(Product.id.in_(ids), Product.sku == sku))
    if not item:
        raise ReleaseScopeError(f"Product/material {sku!r} is not present in the pinned Products release.")
    return item


def pinned_labour(db: Session, estimate: Estimate, code: str) -> LabourComponent:
    ids = release_record_ids(db, estimate, "labour")
    item = db.scalar(select(LabourComponent).where(LabourComponent.id.in_(ids), LabourComponent.code == code))
    if not item:
        raise ReleaseScopeError(f"Labour component {code!r} is not present in the pinned Labour release.")
    return item


def pinned_pricing_record(db: Session, estimate: Estimate, pkb_entry_id: str) -> PricingLibraryRecord:
    ids = release_record_ids(db, estimate, "pricing")
    item = db.scalar(select(PricingLibraryRecord).where(PricingLibraryRecord.id.in_(ids), PricingLibraryRecord.pkb_entry_id == pkb_entry_id))
    if not item:
        raise ReleaseScopeError(f"Pricing record {pkb_entry_id!r} is not present in the pinned Pricing release.")
    return item


def pinned_markup_profiles(db: Session, estimate: Estimate) -> list[MarkupProfile]:
    ids = release_record_ids(db, estimate, "markups")
    return list(db.scalars(select(MarkupProfile).where(MarkupProfile.id.in_(ids))).all())


def pinned_technical_ids(db: Session, estimate: Estimate) -> set[str]:
    release = pinned_release(db, estimate, "technical")
    if release.status != "active":
        raise ReleaseScopeError("Pinned technical release is not active.")
    return release_record_ids(db, estimate, "technical")


def pinned_rule_ids(db: Session, estimate: Estimate) -> set[str]:
    return release_record_ids(db, estimate, "rules")


def pinned_rules(db: Session, estimate: Estimate) -> list[EstimatingRule]:
    ids = pinned_rule_ids(db, estimate)
    return list(db.scalars(select(EstimatingRule).where(EstimatingRule.id.in_(ids)).order_by(EstimatingRule.priority.asc(), EstimatingRule.rule_code.asc())).all())


def validate_runtime_scope(db: Session, estimate: Estimate) -> list[str]:
    errors: list[str] = []
    technical_ids: set[str] | None = None
    for kind in PIN_FIELDS:
        try:
            if kind == "technical":
                technical_ids = pinned_technical_ids(db, estimate)
            else:
                release_record_ids(db, estimate, kind)
        except ReleaseScopeError as exc:
            errors.append(str(exc))
    if technical_ids is not None:
        for opening in estimate.openings:
            if (
                opening.selected_technical_variant_id
                and opening.selected_technical_variant_id not in technical_ids
            ):
                errors.append(
                    f"Opening {opening.opening_code}: selected technical variant is not in "
                    "the pinned Technical release."
                )
    return errors
