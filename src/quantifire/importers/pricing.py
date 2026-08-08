from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import LibraryRelease, PricingLibraryRecord, Product


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "Not stated", "N/A"):
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    if text.endswith("%"):
        text = text[:-1]
        try:
            return Decimal(text) / Decimal("100")
        except InvalidOperation:
            return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _slug(text: str) -> str:
    token = re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")[:50]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:10].upper()
    return f"QF-{token}-{digest}" if token else f"QF-PRODUCT-{digest}"


def _release_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def import_pricing_library(
    db: Session,
    path: Path,
    *,
    version: str | None = None,
    status: str = "active",
    derive_products: bool = True,
) -> dict[str, Any]:
    release_version = version or "source-import"
    release_hash = _release_hash(path)
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == "pricing",
            LibraryRelease.version == release_version,
        )
    )
    if not release:
        release = LibraryRelease(
            library_type="pricing",
            version=release_version,
            status=status,
            release_hash=release_hash,
            source_manifest={"filename": path.name, "sha256": release_hash},
            notes="Imported from the supplied QUANTIFIRE Package 14 source library.",
        )
        db.add(release)
        db.flush()

    inserted = 0
    skipped = 0
    product_candidates: dict[str, dict[str, Any]] = {}
    product_fields = [
        ("Product_Board_Batt_Source", "Board_Unit_Price_AUD_EX_GST", "material", "board_batt"),
        ("Product_Collar_Source", "Collar_Unit_Price_AUD_EX_GST", "product", "collar"),
        ("Product_Mastic_Source", "Mastic_Unit_Price_AUD_EX_GST", "material", "mastic"),
        ("Product_Framing_Source", "Framing_Unit_Price_AUD_EX_GST", "material", "framing"),
        ("Product_Wrap_Source", "Wrap_Unit_Price_AUD_EX_GST", "product", "wrap"),
        ("Product_Other_Material_Source", "Other_Material_Unit_Price_AUD_EX_GST", "material", "other"),
    ]
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            entry_id = (row.get("PKB_Entry_ID") or "").strip()
            if not entry_id:
                skipped += 1
                continue
            entry_version = (row.get("Entry_Version") or "").strip() or None
            exists = db.scalar(
                select(PricingLibraryRecord.id).where(
                    PricingLibraryRecord.pkb_entry_id == entry_id,
                    PricingLibraryRecord.entry_version == entry_version,
                    PricingLibraryRecord.release_id == release.id,
                )
            )
            if exists:
                skipped += 1
                continue
            inclusions = {
                key: row.get(key)
                for key in row
                if key.startswith("Rate_Includes_") or key in {"Separate_Batt_Combination_Status"}
            }
            applicability = {
                key: row.get(key)
                for key in row
                if key.endswith("_Parsed")
                or key.startswith("Package15_")
                or key in {
                    "Opening_Level_Reconciliation_Required_YN",
                    "Duplicate_Recovery_Risk_Class",
                    "Critical_Fields_Complete_YN",
                    "Exact_Match_Eligible_YN",
                    "Proxy_Eligible_YN",
                }
            }
            rate_value = (
                _decimal(row.get("Calculated_Unit_Rate_AUD_EX_GST"))
                or _decimal(row.get("Base_Unit_Rate_AUD_EX_GST"))
                or Decimal("0")
            )
            record = PricingLibraryRecord(
                pkb_entry_id=entry_id,
                entry_version=entry_version,
                description=row.get("Source_Item_Description") or entry_id,
                system_description=row.get("Source_System_Description"),
                unit=row.get("Unit_Basis") or "each",
                rate_ex_tax=rate_value,
                direct_labour_cost=_decimal(row.get("Direct_Labour_Cost_AUD_EX_GST")),
                direct_material_cost=_decimal(row.get("Direct_Material_Cost_AUD_EX_GST")),
                material_markup=_decimal(row.get("Material_Markup_Percent")),
                currency=(row.get("Currency") or "AUD")[:3],
                tax_basis=row.get("Tax_Basis") or "GST Exclusive",
                service_type=row.get("Service_Type_Source"),
                service_class=row.get("Service_Class_Normalised"),
                service_material=row.get("Service_Material_Normalised"),
                substrate=row.get("Substrate_Material_Normalised") or row.get("Substrate_Source"),
                substrate_plane=row.get("Substrate_Plane_Normalised"),
                orientation=row.get("Orientation_Source"),
                frl=row.get("FRL_Normalised") or row.get("FRL_Source"),
                manufacturer=row.get("Manufacturer_Source"),
                repair_family=row.get("Repair_Family_Normalised"),
                rate_inclusions=inclusions,
                rate_exclusions={"migration_warnings": row.get("Migration_Warnings")},
                applicability=applicability,
                commercial_confidence=row.get("Commercial_Confidence"),
                technical_status=row.get("Technical_Evidence_Status"),
                status="active" if (row.get("Entry_Status") or "").lower() == "active" else "draft",
                effective_date=_date(row.get("Rate_Date") or row.get("Library_Effective_Date")),
                source_hash=hashlib.sha256(
                    json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")
                ).hexdigest(),
                source_json=row,
                release_id=release.id,
            )
            db.add(record)
            inserted += 1

            if derive_products:
                for name_field, price_field, item_type, category in product_fields:
                    name = (row.get(name_field) or "").strip()
                    price = _decimal(row.get(price_field))
                    if name and price is not None and price >= 0:
                        current = product_candidates.get(name)
                        if not current or price > current["base_cost"]:
                            product_candidates[name] = {
                                "name": name,
                                "base_cost": price,
                                "item_type": item_type,
                                "category": category,
                                "manufacturer": row.get("Manufacturer_Source"),
                            }
    products_inserted = 0
    if derive_products:
        for name, values in product_candidates.items():
            sku = _slug(name)
            exists = db.scalar(select(Product.id).where(Product.sku == sku, Product.revision == 1))
            if exists:
                continue
            db.add(
                Product(
                    sku=sku,
                    revision=1,
                    name=name,
                    item_type=values["item_type"],
                    category=values["category"],
                    manufacturer=values["manufacturer"],
                    unit="each",
                    base_cost=values["base_cost"],
                    currency="AUD",
                    tax_treatment="exclusive",
                    default_markup=Decimal("0.30") if values["item_type"] in {"product", "material"} else None,
                    status="active",
                    effective_date=release.effective_date,
                    source_reference=f"Derived from {path.name}",
                    source_json={"derived_from_pricing_release": release.id},
                    release_id=release.id,
                )
            )
            products_inserted += 1
    db.commit()
    return {
        "release_id": release.id,
        "release_version": release.version,
        "release_hash": release.release_hash,
        "records_inserted": inserted,
        "records_skipped": skipped,
        "products_derived": products_inserted,
    }
