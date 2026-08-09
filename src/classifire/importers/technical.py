from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LibraryRelease, TechnicalVariant


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


def _row_hash(row: dict[str, Any], line: str) -> str:
    return str(row.get("Variant_Content_Hash") or "").strip() or hashlib.sha256(
        line.encode("utf-8")
    ).hexdigest()


def _collision_variant_id(source_variant_id: str, source_hash: str) -> str:
    return f"{source_variant_id}-QFSRC-{source_hash[:12].upper()}"


def import_technical_variants(
    db: Session,
    path: Path,
    *,
    version: str | None = None,
    status: str = "active",
    allowed_identity_collisions: set[str] | None = None,
) -> dict[str, Any]:
    release_version = version or "source-import"
    release_hash = _hash(path)
    allowed_collisions = set(allowed_identity_collisions or set())
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.version == release_version,
        )
    )
    if not release:
        release = LibraryRelease(
            library_type="technical",
            version=release_version,
            status=status,
            release_hash=release_hash,
            source_manifest={"filename": path.name, "sha256": release_hash},
            notes=(
                "Imported from the supplied Package 15 executable variant index. Active runtime use remains subject "
                "to source-document availability, exact applicability checks, and authorised technical approval."
            ),
        )
        db.add(release)
        db.flush()

    inserted = 0
    skipped = 0
    invalid = 0
    exact_source_duplicates_skipped = 0
    identity_collisions_remapped = 0
    collision_map: list[dict[str, Any]] = []
    seen_source_hashes: dict[str, set[str]] = {}

    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue

            source_variant_id = str(row.get("Variant_ID") or "").strip()
            system_id = str(row.get("System_ID") or "").strip()
            if not source_variant_id or not system_id:
                invalid += 1
                continue

            source_hash = _row_hash(row, line)
            prior_hashes = seen_source_hashes.setdefault(source_variant_id, set())
            if source_hash in prior_hashes:
                skipped += 1
                exact_source_duplicates_skipped += 1
                continue

            resolved_variant_id = source_variant_id
            source_json: dict[str, Any] = dict(row)
            if prior_hashes:
                if source_variant_id not in allowed_collisions:
                    raise ValueError(
                        "Package 17 contains materially different rows with the same Variant_ID "
                        f"{source_variant_id!r}; collision is not authorised for controlled import."
                    )
                resolved_variant_id = _collision_variant_id(source_variant_id, source_hash)
                migration_meta = dict(source_json.get("CLASSIFIRE_Migration") or {})
                migration_meta.update(
                    {
                        "source_variant_id": source_variant_id,
                        "resolved_variant_id": resolved_variant_id,
                        "identity_collision": True,
                        "collision_resolution": "deterministic_content_hash_suffix",
                        "source_line_number": line_number,
                        "source_content_hash": source_hash,
                    }
                )
                source_json["CLASSIFIRE_Migration"] = migration_meta
                identity_collisions_remapped += 1
                collision_map.append(
                    {
                        "source_variant_id": source_variant_id,
                        "resolved_variant_id": resolved_variant_id,
                        "source_line_number": line_number,
                        "source_content_hash": source_hash,
                        "frl": row.get("FRL_Variant"),
                    }
                )
            prior_hashes.add(source_hash)

            existing = db.scalar(
                select(TechnicalVariant).where(
                    TechnicalVariant.variant_id == resolved_variant_id
                )
            )
            if existing:
                if existing.source_hash and existing.source_hash != source_hash:
                    raise ValueError(
                        f"Existing technical variant {resolved_variant_id!r} has source hash "
                        f"{existing.source_hash}, not {source_hash}; refusing identity overwrite."
                    )
                skipped += 1
                continue

            variant_status = str(row.get("Variant_Status") or "DRAFT").lower()
            search_status = str(row.get("Search_Index_Status") or "")
            status_value = (
                "active"
                if variant_status == "active" and search_status == "ACTIVE"
                else "draft"
            )
            record = TechnicalVariant(
                variant_id=resolved_variant_id,
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
                permitted_service_quantity=str(
                    row.get("Permitted_Service_Quantity") or ""
                )
                or None,
                insulation_type=row.get("Insulation_Type"),
                insulation_thickness_mm=_decimal(row.get("Insulation_Thickness_mm")),
                substrate_type=row.get("Substrate_Type")
                or row.get("Canonical_Substrate_Family"),
                minimum_substrate_thickness_mm=_decimal(
                    row.get("Minimum_Substrate_Thickness_mm")
                ),
                maximum_substrate_thickness_mm=_decimal(
                    row.get("Maximum_Substrate_Thickness_mm")
                ),
                orientation=row.get("Orientation") or row.get("Canonical_Orientation"),
                installation_face=row.get("Installation_Face"),
                opening_type=row.get("Opening_Type")
                or row.get("Canonical_Opening_Type"),
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
                search_eligibility=row.get("Search_Eligibility"),
                expert_review_required=(
                    str(row.get("Expert_Review_Trigger_YN") or "YES").upper() == "YES"
                ),
                status=status_value,
                effective_date=_date(row.get("Effective_Date")),
                expiry_date=_date(row.get("Evidence_Expiry_Date")),
                source_hash=source_hash,
                source_json=source_json,
                release_id=release.id,
            )
            db.add(record)
            inserted += 1
            if inserted % 250 == 0:
                db.flush()

    db.commit()
    return {
        "release_id": release.id,
        "release_version": release.version,
        "release_hash": release.release_hash,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "invalid_lines": invalid,
        "exact_source_duplicates_skipped": exact_source_duplicates_skipped,
        "identity_collisions_remapped": identity_collisions_remapped,
        "identity_collision_map": collision_map,
    }
