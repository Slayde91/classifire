from __future__ import annotations

from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LibraryRelease, PricingLibraryRecord, TechnicalVariant

SOURCE_VERSION = "2.13"
EXPECTED_PRICING_ROWS = 897
EXPECTED_TECHNICAL_ROWS = 2861
EXPECTED_SOURCE_UNIQUE_VARIANTS = 2860
EXPECTED_ACTIVE_TECHNICAL_ROWS = 2860
EXPECTED_INACTIVE_TECHNICAL_ROWS = 1
EXPECTED_TOTAL_SYSTEM_IDS = 2182
EXPECTED_ACTIVE_SYSTEM_IDS = 2181
EXPECTED_INACTIVE_SYSTEM_IDS = 1
KNOWN_COLLISION_ID = "TSL-FF-FAS190236-RIR1-25A-V211-VAR01"

PRICING_RELATIVE = Path("knowledge/libraries/CLASSIFIRE_14_Pricing_Library_v2.13.csv")
P15_RELATIVE = Path("knowledge/libraries/CLASSIFIRE_15_Technical_System_Library_v2.13.txt")
P17_RELATIVE = Path("knowledge/libraries/CLASSIFIRE_17_Technical_System_Variants_v2.13.jsonl")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(payload: Any) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _gate(gates: list[dict[str, Any]], gate_id: str, passed: bool, detail: Any) -> None:
    gates.append({"gate_id": gate_id, "passed": bool(passed), "detail": detail})


def _condition(
    conditions: list[dict[str, Any]], condition_id: str, detail: Any, acknowledgement: str
) -> None:
    conditions.append(
        {
            "condition_id": condition_id,
            "detail": detail,
            "required_acknowledgement": acknowledgement,
        }
    )


def _release(db: Session, library_type: str) -> LibraryRelease | None:
    return db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == library_type,
            LibraryRelease.version == SOURCE_VERSION,
        )
    )


def _p15_field(text: str, label: str) -> str | None:
    match = re.search(rf"(?mi)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text)
    return match.group(1).strip() if match else None


def _int_field(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\d[\d,]*", value)
    return int(match.group(0).replace(",", "")) if match else None


def _source_pricing(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    ids = [str(row.get("PKB_Entry_ID") or "").strip() for row in rows]
    statuses = Counter(str(row.get("Entry_Status") or "").strip().upper() for row in rows)
    critical = Counter(
        str(row.get("Critical_Fields_Complete_YN") or "").strip().upper() for row in rows
    )
    exact = Counter(
        str(row.get("Exact_Match_Eligible_YN") or "").strip().upper() for row in rows
    )
    proxy = Counter(str(row.get("Proxy_Eligible_YN") or "").strip().upper() for row in rows)
    rates: list[float] = []
    missing_rate = 0
    for row in rows:
        raw = row.get("Calculated_Unit_Rate_AUD_EX_GST") or row.get("Base_Unit_Rate_AUD_EX_GST")
        try:
            rates.append(float(str(raw).replace("$", "").replace(",", "").strip()))
        except (TypeError, ValueError):
            missing_rate += 1
    return {
        "rows": len(rows),
        "unique_pkb_ids": len(set(ids)),
        "missing_pkb_ids": sum(not value for value in ids),
        "status_counts": dict(statuses),
        "critical_fields_counts": dict(critical),
        "exact_match_counts": dict(exact),
        "proxy_counts": dict(proxy),
        "missing_rate_count": missing_rate,
        "zero_or_negative_rate_count": sum(value <= 0 for value in rates),
        "minimum_rate": min(rates) if rates else None,
        "maximum_rate": max(rates) if rates else None,
    }


def _source_technical(path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    invalid_json = 0
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                invalid_json += 1

    variant_ids = [str(row.get("Variant_ID") or "").strip() for row in rows]
    variant_counts = Counter(value for value in variant_ids if value)
    collisions = sorted(value for value, count in variant_counts.items() if count > 1)
    active_rows = [
        row
        for row in rows
        if str(row.get("Variant_Status") or "").strip().upper() == "ACTIVE"
        and str(row.get("Search_Index_Status") or "").strip().upper() == "ACTIVE"
    ]
    inactive_rows = [row for row in rows if row not in active_rows]
    active_system_ids = {str(row.get("System_ID") or "").strip() for row in active_rows}
    inactive_system_ids = {str(row.get("System_ID") or "").strip() for row in inactive_rows}
    all_system_ids = {str(row.get("System_ID") or "").strip() for row in rows}
    required_fields = (
        "System_ID",
        "Variant_ID",
        "Source_Document_ID",
        "Source_Page",
        "Manufacturer",
        "Service_Type",
        "Substrate_Type",
        "Orientation",
        "FRL_Variant",
    )
    required_missing = {
        field: sum(row.get(field) in (None, "") for row in rows) for field in required_fields
    }
    parsed_missing = 0
    parsed_incomplete = 0
    for row in rows:
        parsed = row.get("parsed_requirements")
        if not isinstance(parsed, dict):
            parsed_missing += 1
            continue
        if not parsed.get("requirements") or not parsed.get("required_component_categories") or not parsed.get("required_labour_activities"):
            parsed_incomplete += 1
    return {
        "rows": len(rows),
        "invalid_json": invalid_json,
        "unique_source_variant_ids": len(set(value for value in variant_ids if value)),
        "colliding_source_variant_ids": collisions,
        "active_rows": len(active_rows),
        "inactive_rows": len(inactive_rows),
        "total_system_ids": len(all_system_ids),
        "active_system_ids": len(active_system_ids),
        "inactive_system_ids": len(inactive_system_ids),
        "inactive_system_id_values": sorted(inactive_system_ids),
        "required_field_missing": required_missing,
        "parsed_requirements_missing": parsed_missing,
        "parsed_requirements_incomplete": parsed_incomplete,
    }


def validate_v213_releases(db: Session, source_root: Path) -> dict[str, Any]:
    source_root = source_root.expanduser().resolve()
    pricing_path = source_root / PRICING_RELATIVE
    p15_path = source_root / P15_RELATIVE
    p17_path = source_root / P17_RELATIVE
    gates: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []

    for gate_id, path in (
        ("SOURCE_PACKAGE14_PRESENT", pricing_path),
        ("SOURCE_PACKAGE15_PRESENT", p15_path),
        ("SOURCE_PACKAGE17_PRESENT", p17_path),
    ):
        _gate(gates, gate_id, path.is_file(), str(path))

    if not all(path.is_file() for path in (pricing_path, p15_path, p17_path)):
        return _finalise(gates, conditions, {}, {}, {}, None, None)

    pricing_hash = sha256_file(pricing_path)
    p15_hash = sha256_file(p15_path)
    p17_hash = sha256_file(p17_path)
    pricing_release = _release(db, "pricing")
    technical_release = _release(db, "technical")
    _gate(gates, "DB_PRICING_SOURCE_RELEASE_PRESENT", pricing_release is not None, SOURCE_VERSION)
    _gate(gates, "DB_TECHNICAL_SOURCE_RELEASE_PRESENT", technical_release is not None, SOURCE_VERSION)
    if pricing_release is None or technical_release is None:
        return _finalise(gates, conditions, {}, {}, {}, pricing_release, technical_release)

    _gate(gates, "PRICING_SOURCE_RELEASE_REMAINS_DRAFT", pricing_release.status == "draft", pricing_release.status)
    _gate(gates, "TECHNICAL_SOURCE_RELEASE_REMAINS_DRAFT", technical_release.status == "draft", technical_release.status)
    _gate(gates, "PACKAGE14_FILE_HASH_MATCH", pricing_release.release_hash == pricing_hash, {"db": pricing_release.release_hash, "file": pricing_hash})
    _gate(gates, "PACKAGE17_FILE_HASH_MATCH", technical_release.release_hash == p17_hash, {"db": technical_release.release_hash, "file": p17_hash})
    technical_manifest = technical_release.source_manifest or {}
    _gate(gates, "PACKAGE15_MANIFEST_HASH_MATCH", technical_manifest.get("package_15_source_sha256") == p15_hash, {"db": technical_manifest.get("package_15_source_sha256"), "file": p15_hash})
    _gate(gates, "PACKAGE17_MANIFEST_HASH_MATCH", technical_manifest.get("package_17_variants_sha256") == p17_hash, {"db": technical_manifest.get("package_17_variants_sha256"), "file": p17_hash})

    source_pricing = _source_pricing(pricing_path)
    _gate(gates, "PACKAGE14_ROW_COUNT", source_pricing["rows"] == EXPECTED_PRICING_ROWS, source_pricing["rows"])
    _gate(gates, "PACKAGE14_UNIQUE_PKB_IDS", source_pricing["unique_pkb_ids"] == EXPECTED_PRICING_ROWS and source_pricing["missing_pkb_ids"] == 0, source_pricing)
    _gate(gates, "PACKAGE14_SOURCE_STATUS_ACTIVE", source_pricing["status_counts"] == {"ACTIVE": EXPECTED_PRICING_ROWS}, source_pricing["status_counts"])
    _gate(gates, "PACKAGE14_CRITICAL_FIELDS_COMPLETE", source_pricing["critical_fields_counts"] == {"YES": EXPECTED_PRICING_ROWS}, source_pricing["critical_fields_counts"])
    _gate(gates, "PACKAGE14_EXACT_MATCH_ELIGIBLE", source_pricing["exact_match_counts"] == {"YES": EXPECTED_PRICING_ROWS}, source_pricing["exact_match_counts"])
    _gate(gates, "PACKAGE14_RATES_POSITIVE", source_pricing["missing_rate_count"] == 0 and source_pricing["zero_or_negative_rate_count"] == 0, {"missing": source_pricing["missing_rate_count"], "zero_or_negative": source_pricing["zero_or_negative_rate_count"]})

    pricing_records = list(db.scalars(select(PricingLibraryRecord).where(PricingLibraryRecord.release_id == pricing_release.id)).all())
    _gate(gates, "PACKAGE14_DATABASE_COUNT", len(pricing_records) == EXPECTED_PRICING_ROWS, len(pricing_records))
    _gate(gates, "PACKAGE14_DATABASE_UNIQUE_PKB_IDS", len({record.pkb_entry_id for record in pricing_records}) == EXPECTED_PRICING_ROWS, len({record.pkb_entry_id for record in pricing_records}))

    source_technical = _source_technical(p17_path)
    _gate(gates, "PACKAGE17_ROW_COUNT", source_technical["rows"] == EXPECTED_TECHNICAL_ROWS, source_technical["rows"])
    _gate(gates, "PACKAGE17_JSON_VALID", source_technical["invalid_json"] == 0, source_technical["invalid_json"])
    _gate(gates, "PACKAGE17_SOURCE_UNIQUE_VARIANTS", source_technical["unique_source_variant_ids"] == EXPECTED_SOURCE_UNIQUE_VARIANTS, source_technical["unique_source_variant_ids"])
    _gate(gates, "PACKAGE17_KNOWN_COLLISION_ONLY", source_technical["colliding_source_variant_ids"] == [KNOWN_COLLISION_ID], source_technical["colliding_source_variant_ids"])
    _gate(gates, "PACKAGE17_ACTIVE_INACTIVE_ROWS", source_technical["active_rows"] == EXPECTED_ACTIVE_TECHNICAL_ROWS and source_technical["inactive_rows"] == EXPECTED_INACTIVE_TECHNICAL_ROWS, {"active": source_technical["active_rows"], "inactive": source_technical["inactive_rows"]})
    _gate(gates, "PACKAGE17_REQUIRED_FIELDS", all(value == 0 for value in source_technical["required_field_missing"].values()), source_technical["required_field_missing"])
    _gate(gates, "PACKAGE17_PARSED_REQUIREMENTS", source_technical["parsed_requirements_missing"] == 0 and source_technical["parsed_requirements_incomplete"] == 0, {"missing": source_technical["parsed_requirements_missing"], "incomplete": source_technical["parsed_requirements_incomplete"]})

    technical_records = list(db.scalars(select(TechnicalVariant).where(TechnicalVariant.release_id == technical_release.id)).all())
    db_active = [record for record in technical_records if record.status == "active"]
    db_inactive = [record for record in technical_records if record.status != "active"]
    collision_rows = []
    for record in technical_records:
        migration = (record.source_json or {}).get("CLASSIFIRE_Migration") or {}
        if migration.get("identity_collision") is True:
            collision_rows.append({"variant_id": record.variant_id, "migration": migration})
    _gate(gates, "PACKAGE17_DATABASE_COUNT", len(technical_records) == EXPECTED_TECHNICAL_ROWS, len(technical_records))
    _gate(gates, "PACKAGE17_DATABASE_VARIANT_IDS_UNIQUE", len({record.variant_id for record in technical_records}) == EXPECTED_TECHNICAL_ROWS, len({record.variant_id for record in technical_records}))
    _gate(gates, "PACKAGE17_DATABASE_ACTIVE_INACTIVE", len(db_active) == EXPECTED_ACTIVE_TECHNICAL_ROWS and len(db_inactive) == EXPECTED_INACTIVE_TECHNICAL_ROWS, {"active": len(db_active), "inactive": len(db_inactive)})
    _gate(gates, "PACKAGE17_COLLISION_PROVENANCE", len(collision_rows) == 1 and collision_rows[0]["migration"].get("source_variant_id") == KNOWN_COLLISION_ID, collision_rows)

    p15_text = p15_path.read_text(encoding="utf-8-sig", errors="replace")
    header_match = re.search(r"(?mi)^Version\s+([^\r\n]+)$", p15_text)
    p15_meta = {
        "header_version": header_match.group(1).strip() if header_match else None,
        "manifest_version": _p15_field(p15_text, "Version"),
        "document_status": _p15_field(p15_text, "Status"),
        "release_status": _p15_field(p15_text, "Release status"),
        "manifest_populated_system_count": _int_field(_p15_field(p15_text, "Populated system count")),
        "manifest_active_system_count": _int_field(_p15_field(p15_text, "Active system count")),
        "manifest_inactive_system_count": _int_field(_p15_field(p15_text, "Inactive system count")),
        "package17_total_system_ids": source_technical["total_system_ids"],
        "package17_active_system_ids": source_technical["active_system_ids"],
        "package17_inactive_system_ids": source_technical["inactive_system_ids"],
    }
    _gate(gates, "PACKAGE17_SYSTEM_ID_TOTAL", source_technical["total_system_ids"] == EXPECTED_TOTAL_SYSTEM_IDS, source_technical["total_system_ids"])
    _gate(gates, "PACKAGE17_ACTIVE_SYSTEM_ID_TOTAL", source_technical["active_system_ids"] == EXPECTED_ACTIVE_SYSTEM_IDS, source_technical["active_system_ids"])
    _gate(gates, "PACKAGE17_INACTIVE_SYSTEM_ID_TOTAL", source_technical["inactive_system_ids"] == EXPECTED_INACTIVE_SYSTEM_IDS, source_technical["inactive_system_ids"])

    if p15_meta["header_version"] != p15_meta["manifest_version"]:
        _condition(
            conditions,
            "P15_INTERNAL_VERSION_DECLARATION_MISMATCH",
            {"header_version": p15_meta["header_version"], "manifest_version": p15_meta["manifest_version"]},
            "A competent human technical approver must acknowledge that the retained Package 15 source carries inconsistent internal version labels; no label is silently rewritten during migration.",
        )
    if (
        p15_meta["manifest_populated_system_count"] != source_technical["total_system_ids"]
        or p15_meta["manifest_active_system_count"] != source_technical["active_system_ids"]
        or p15_meta["manifest_inactive_system_count"] != source_technical["inactive_system_ids"]
    ):
        _condition(
            conditions,
            "P15_MANIFEST_SYSTEM_COUNT_OFFSET",
            p15_meta,
            "A competent human technical approver must acknowledge the Package 15 manifest count offset and approve runtime scoping from the verified Package 17 executable record set instead of silently editing the retained source.",
        )
    document_status = str(p15_meta.get("document_status") or "").upper()
    release_status = str(p15_meta.get("release_status") or "").upper()
    if "ACTIVE" in document_status and ("CANDIDATE" in release_status or "REQUIRE" in release_status):
        _condition(
            conditions,
            "P15_STATUS_DECLARATION_REQUIRES_HUMAN_DECISION",
            {"document_status": p15_meta["document_status"], "release_status": p15_meta["release_status"]},
            "A competent human technical approver must explicitly approve the migrated runtime Technical release; source status wording alone is insufficient.",
        )

    return _finalise(
        gates,
        conditions,
        source_pricing,
        source_technical,
        p15_meta,
        pricing_release,
        technical_release,
        source_hashes={"package14": pricing_hash, "package15": p15_hash, "package17": p17_hash},
    )


def _finalise(
    gates: list[dict[str, Any]],
    conditions: list[dict[str, Any]],
    source_pricing: dict[str, Any],
    source_technical: dict[str, Any],
    p15_meta: dict[str, Any],
    pricing_release: LibraryRelease | None,
    technical_release: LibraryRelease | None,
    *,
    source_hashes: dict[str, str] | None = None,
) -> dict[str, Any]:
    hard_gates_passed = all(item["passed"] for item in gates)
    readiness = (
        "BLOCKED"
        if not hard_gates_passed
        else "CONDITIONAL_HUMAN_APPROVAL_REQUIRED"
        if conditions
        else "READY_FOR_HUMAN_APPROVAL"
    )
    approval_basis = {
        "schema": "CLASSIFIRE-V213-RELEASE-VALIDATION-v1",
        "source_version": SOURCE_VERSION,
        "pricing_source_release_id": pricing_release.id if pricing_release else None,
        "technical_source_release_id": technical_release.id if technical_release else None,
        "source_hashes": source_hashes or {},
        "hard_gates_passed": hard_gates_passed,
        "condition_ids": [item["condition_id"] for item in conditions],
        "pricing_record_count": source_pricing.get("rows"),
        "technical_record_count": source_technical.get("rows"),
        "technical_active_record_count": source_technical.get("active_rows"),
    }
    approval_token = canonical_hash(approval_basis) if hard_gates_passed else None
    return {
        "schema": "CLASSIFIRE-V213-RELEASE-VALIDATION-v1",
        "readiness": readiness,
        "hard_gates_passed": hard_gates_passed,
        "gates": gates,
        "conditions": conditions,
        "source_pricing": source_pricing,
        "source_technical": source_technical,
        "package15_metadata": p15_meta,
        "approval_basis": approval_basis,
        "approval_token": approval_token,
    }
