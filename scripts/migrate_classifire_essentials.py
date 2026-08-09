from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sqlalchemy import func, select

from classifire.config import get_settings
from classifire.db import Base, SessionLocal, engine
from classifire.importers import import_pricing_library, import_technical_variants, seed_database
from classifire.knowledge_migration import StagedEssentials, sha256_file, stage_essentials_archive
from classifire.models import LibraryRelease, PricingLibraryRecord, TechnicalVariant

EXPECTED_PRICING_ROWS = 897
EXPECTED_TECHNICAL_LINES = 2861
EXPECTED_UNIQUE_VARIANTS = 2860
KNOWN_DUPLICATE_VARIANT_ID = "TSL-FF-FAS190236-RIR1-25A-V211-VAR01"
RELEASE_VERSION = "2.13"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def validate_source_shape(staged: StagedEssentials) -> dict[str, object]:
    pricing_rows = 0
    pricing_ids = 0
    with staged.pricing_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            pricing_rows += 1
            if (row.get("PKB_Entry_ID") or "").strip():
                pricing_ids += 1

    technical_lines = 0
    variant_ids: list[str] = []
    invalid_json = 0
    with staged.technical_variants_path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            technical_lines += 1
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                invalid_json += 1
                continue
            variant_ids.append(str(row.get("Variant_ID") or "").strip())

    counts = Counter(value for value in variant_ids if value)
    unique_ids = set(counts)
    duplicates = sorted(value for value, count in counts.items() if count > 1)
    errors: list[str] = []
    if pricing_rows != EXPECTED_PRICING_ROWS or pricing_ids != EXPECTED_PRICING_ROWS:
        errors.append(
            f"Package 14 expected {EXPECTED_PRICING_ROWS} rows with PKB IDs; "
            f"found {pricing_rows} rows / {pricing_ids} IDs."
        )
    if technical_lines != EXPECTED_TECHNICAL_LINES:
        errors.append(
            f"Package 17 expected {EXPECTED_TECHNICAL_LINES} non-empty lines; "
            f"found {technical_lines}."
        )
    if invalid_json:
        errors.append(f"Package 17 contains {invalid_json} invalid JSON lines.")
    if len(unique_ids) != EXPECTED_UNIQUE_VARIANTS:
        errors.append(
            f"Package 17 expected {EXPECTED_UNIQUE_VARIANTS} unique Variant_ID values; "
            f"found {len(unique_ids)}."
        )
    if duplicates != [KNOWN_DUPLICATE_VARIANT_ID]:
        errors.append(
            "Package 17 duplicate Variant_ID set differs from the authorised source: "
            f"{duplicates}."
        )
    if errors:
        raise RuntimeError("Controlled source shape validation failed: " + " ".join(errors))

    return {
        "pricing_rows": pricing_rows,
        "pricing_pkb_ids": pricing_ids,
        "technical_lines": technical_lines,
        "unique_variant_ids": len(unique_ids),
        "known_duplicate_variant_id": KNOWN_DUPLICATE_VARIANT_ID,
    }


def assert_release_hash(
    library_type: str,
    version: str,
    expected_hash: str,
) -> None:
    with SessionLocal() as db:
        release = db.scalar(
            select(LibraryRelease).where(
                LibraryRelease.library_type == library_type,
                LibraryRelease.version == version,
            )
        )
        if release and release.release_hash and release.release_hash != expected_hash:
            raise RuntimeError(
                f"Existing {library_type} release {version} has source hash "
                f"{release.release_hash}, not {expected_hash}. Refusing same-version overwrite."
            )


def import_libraries(staged: StagedEssentials) -> dict[str, object]:
    pricing_hash = sha256_file(staged.pricing_path)
    technical_source_hash = sha256_file(staged.technical_library_path)
    technical_variants_hash = sha256_file(staged.technical_variants_path)
    assert_release_hash("pricing", RELEASE_VERSION, pricing_hash)
    assert_release_hash("technical", RELEASE_VERSION, technical_variants_hash)

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db, get_settings())
        pricing_result = import_pricing_library(
            db,
            staged.pricing_path,
            version=RELEASE_VERSION,
            status="draft",
        )
    with SessionLocal() as db:
        technical_result = import_technical_variants(
            db,
            staged.technical_variants_path,
            version=RELEASE_VERSION,
            status="draft",
        )

    with SessionLocal() as db:
        pricing_release = db.scalar(
            select(LibraryRelease).where(
                LibraryRelease.library_type == "pricing",
                LibraryRelease.version == RELEASE_VERSION,
            )
        )
        technical_release = db.scalar(
            select(LibraryRelease).where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.version == RELEASE_VERSION,
            )
        )
        if pricing_release is None or technical_release is None:
            raise RuntimeError("Expected imported pricing and technical releases were not found.")

        pricing_release.notes = (
            "Controlled CLASSIFIRE Package 14 pricing library v2.13 staged from the "
            "reviewed OpenClaw + Mission Control essentials migration payload."
        )
        pricing_release.source_manifest = {
            "package_id": staged.package_id,
            "filename": staged.pricing_path.name,
            "sha256": pricing_hash,
        }
        technical_release.notes = (
            "Controlled CLASSIFIRE Package 17 executable technical variants v2.13. "
            "Package 15 technical source authority is retained in the same controlled "
            "source stage. Runtime use remains subject to release approval and fail-closed "
            "applicability/expert-review gates."
        )
        technical_release.source_manifest = {
            "package_id": staged.package_id,
            "package_15_source_filename": staged.technical_library_path.name,
            "package_15_source_sha256": technical_source_hash,
            "package_17_variants_filename": staged.technical_variants_path.name,
            "package_17_variants_sha256": technical_variants_hash,
        }
        db.commit()

        pricing_count = db.scalar(
            select(func.count()).select_from(PricingLibraryRecord).where(
                PricingLibraryRecord.release_id == pricing_release.id
            )
        ) or 0
        technical_count = db.scalar(
            select(func.count()).select_from(TechnicalVariant).where(
                TechnicalVariant.release_id == technical_release.id
            )
        ) or 0
        technical_variant_rows_active = db.scalar(
            select(func.count()).select_from(TechnicalVariant).where(
                TechnicalVariant.release_id == technical_release.id,
                TechnicalVariant.status == "active",
            )
        ) or 0

    if pricing_count != EXPECTED_PRICING_ROWS:
        raise RuntimeError(
            f"Imported Package 14 release contains {pricing_count} rows; "
            f"expected {EXPECTED_PRICING_ROWS}."
        )
    if technical_count != EXPECTED_UNIQUE_VARIANTS:
        raise RuntimeError(
            f"Imported Package 17 release contains {technical_count} unique variants; "
            f"expected {EXPECTED_UNIQUE_VARIANTS}."
        )

    return {
        "pricing": pricing_result,
        "technical": technical_result,
        "post_import": {
            "pricing_records": pricing_count,
            "technical_variants": technical_count,
            "technical_variant_rows_active": technical_variant_rows_active,
            "pricing_release_id": pricing_release.id,
            "pricing_release_status": pricing_release.status,
            "technical_release_id": technical_release.id,
            "technical_release_status": technical_release.status,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage and import the controlled CLASSIFIRE migration essentials archive."
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--destination",
        type=Path,
        default=repo_root() / "private-data" / "controlled-source" / "v2.13",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--stage-only", action="store_true")
    args = parser.parse_args()

    staged = stage_essentials_archive(
        args.archive,
        args.destination,
        overwrite=args.overwrite,
    )
    source_shape = validate_source_shape(staged)
    result: dict[str, object] = {
        "ok": True,
        "staged": staged.as_dict(),
        "source_shape": source_shape,
        "database_imported": False,
    }
    if not args.stage_only:
        result["import"] = import_libraries(staged)
        result["database_imported"] = True

    receipt = {
        **result,
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    receipt_path = staged.source_root / "CLASSIFIRE_KNOWLEDGE_MIGRATION_RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, default=str), encoding="utf-8")
    print(json.dumps(receipt, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CLASSIFIRE knowledge migration failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
