from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import LibraryRelease, TechnicalVariant
from ..services.technical_governance import PENDING_TECHNICAL_REVIEW

TECHNICAL_IMPORT_POLICY = "technical-draft-intake-v1"
PENDING_REVIEW_SEARCH_ELIGIBILITY = PENDING_TECHNICAL_REVIEW
_SOURCE_ACTIVITY_FIELDS = (
    "Variant_Status",
    "Search_Index_Status",
    "Search_Eligibility",
)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "Not stated", "N/A"):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value and value != "Not stated" else None
    except ValueError:
        return None


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_technical_variants(
    db: Session,
    path: Path,
    *,
    version: str | None = None,
    status: str = "draft",
) -> dict[str, Any]:
    """Import source rows as Draft candidates without granting runtime authority."""
    requested_status = status.strip().lower()
    if requested_status != "draft":
        raise ValueError(
            "Technical imports can create Draft candidates only. "
            "Technical approval and release publication are separate gates."
        )

    release_version = version or "source-import"
    release_hash = _hash(path)
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.version == release_version,
        )
    )
    if release:
        manifest = release.source_manifest or {}
        if release.release_hash != release_hash or manifest.get("sha256") != release_hash:
            raise ValueError(
                f"TECHNICAL_IMPORT_VERSION_COLLISION: version {release_version!r} "
                "already exists with different source bytes."
            )
        if release.status != "draft" or manifest.get("import_policy") != TECHNICAL_IMPORT_POLICY:
            raise ValueError(
                "LEGACY_TECHNICAL_IMPORT_REQUIRES_MIGRATION: the matching import "
                "predates the Draft-only intake policy and was left unchanged."
            )
        existing_records = (
            db.scalar(
                select(func.count())
                .select_from(TechnicalVariant)
                .where(TechnicalVariant.release_id == release.id)
            )
            or 0
        )
        return {
            "release_id": release.id,
            "release_version": release.version,
            "release_hash": release.release_hash,
            "release_status": release.status,
            "import_policy": TECHNICAL_IMPORT_POLICY,
            "records_inserted": 0,
            "records_skipped": existing_records,
            "invalid_lines": 0,
        }

    release = LibraryRelease(
        library_type="technical",
        version=release_version,
        status="draft",
        release_hash=release_hash,
        source_manifest={
            "filename": path.name,
            "sha256": release_hash,
            "import_policy": TECHNICAL_IMPORT_POLICY,
            "runtime_eligible": False,
            "source_activity_fields_authoritative": False,
        },
        notes=(
            "Imported as Draft technical candidates. Source-declared status and search eligibility "
            "are retained as provenance only. Technical approval and release publication "
            "remain required."
        ),
    )
    db.add(release)
    db.flush()
    inserted = 0
    skipped = 0
    invalid = 0
    source_activity_rows = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if not isinstance(row, dict):
                invalid += 1
                continue
            variant_id = str(row.get("Variant_ID") or "").strip()
            system_id = str(row.get("System_ID") or "").strip()
            if not variant_id or not system_id:
                invalid += 1
                continue
            row_hash = hashlib.sha256(line.encode("utf-8")).hexdigest()
            existing = db.scalar(
                select(TechnicalVariant).where(TechnicalVariant.variant_id == variant_id)
            )
            if existing:
                if existing.source_hash != row_hash or existing.source_json != row:
                    db.rollback()
                    raise ValueError(
                        f"TECHNICAL_VARIANT_ID_COLLISION: variant {variant_id!r} "
                        "already exists with different source content."
                    )
                skipped += 1
                continue
            if any(row.get(field) not in (None, "") for field in _SOURCE_ACTIVITY_FIELDS):
                source_activity_rows += 1
            record = TechnicalVariant(
                variant_id=variant_id,
                system_id=system_id,
                source_document_reference=row.get("Source_Document_ID"),
                source_page=row.get("Source_Page"),
                source_table=row.get("Source_Table"),
                source_figure=row.get("Source_Figure"),
                manufacturer=row.get("Manufacturer"),
                product_family=row.get("Product_Family"),
                service_type=row.get("Service_Type"),
                service_material=row.get("Service_Material")
                or row.get("Canonical_Service_Material"),
                minimum_service_size_mm=_decimal(row.get("Minimum_Service_Size_mm")),
                maximum_service_size_mm=_decimal(row.get("Maximum_Service_Size_mm")),
                permitted_service_quantity=str(row.get("Permitted_Service_Quantity") or "") or None,
                insulation_type=row.get("Insulation_Type"),
                insulation_thickness_mm=_decimal(row.get("Insulation_Thickness_mm")),
                substrate_type=row.get("Substrate_Type") or row.get("Canonical_Substrate_Family"),
                minimum_substrate_thickness_mm=_decimal(row.get("Minimum_Substrate_Thickness_mm")),
                maximum_substrate_thickness_mm=_decimal(row.get("Maximum_Substrate_Thickness_mm")),
                orientation=row.get("Orientation") or row.get("Canonical_Orientation"),
                installation_face=row.get("Installation_Face"),
                opening_type=row.get("Opening_Type") or row.get("Canonical_Opening_Type"),
                opening_dimensions=row.get("Opening_Dimensions"),
                annular_gap_min_mm=_decimal(row.get("Annular_Gap_Min_mm")),
                annular_gap_max_mm=_decimal(row.get("Annular_Gap_Max_mm")),
                service_spacing_rules=row.get("Service_Spacing_Rules"),
                edge_distance_rules=row.get("Edge_Distance_Rules"),
                support_rules=row.get("Support_Rules"),
                fixing_rules=row.get("Fixing_Rules"),
                component_requirements=row.get("parsed_requirements")
                or row.get("required_component_categories"),
                labour_requirements=row.get("required_labour_activities"),
                hard_exclusions=row.get("Hard_Exclusions"),
                dependencies=row.get("Dependencies"),
                frl=row.get("FRL_Variant"),
                jurisdiction=row.get("Jurisdiction"),
                quality_score=_decimal(row.get("Variant_Quality_Score")),
                confidence_cap=_decimal(row.get("Matching_Confidence_Cap")),
                search_eligibility=PENDING_REVIEW_SEARCH_ELIGIBILITY,
                expert_review_required=True,
                status="draft",
                effective_date=None,
                expiry_date=None,
                source_hash=row_hash,
                source_json=row,
                release_id=release.id,
            )
            db.add(record)
            inserted += 1
            if inserted % 250 == 0:
                db.flush()
    release.source_manifest = {
        **(release.source_manifest or {}),
        "records_inserted": inserted,
        "records_skipped": skipped,
        "invalid_lines": invalid,
        "source_activity_rows": source_activity_rows,
        "source_activity_fields_retained_in_source_json": True,
    }
    db.commit()
    return {
        "release_id": release.id,
        "release_version": release.version,
        "release_hash": release.release_hash,
        "release_status": release.status,
        "import_policy": TECHNICAL_IMPORT_POLICY,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "invalid_lines": invalid,
    }
