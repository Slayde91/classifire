from __future__ import annotations

import hashlib
import json
import sys

from sqlalchemy import select

from classifire.auxiliary_runtime_promotion import RUNTIME_VERSION
from classifire.db import SessionLocal
from classifire.models import LibraryRelease


def canonical_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    required = ("pricing", "technical", "rules", "products", "labour", "markups")
    errors: list[str] = []
    payload: dict[str, object] = {
        "schema": "CLASSIFIRE-V213-COMPLETE-RUNTIME-VERIFICATION-v1",
        "ok": False,
        "runtime_version": RUNTIME_VERSION,
        "releases": {},
    }

    with SessionLocal() as db:
        for library_type in required:
            release = db.scalar(
                select(LibraryRelease).where(
                    LibraryRelease.library_type == library_type,
                    LibraryRelease.version == RUNTIME_VERSION,
                    LibraryRelease.status == "active",
                )
            )
            if release is None:
                errors.append(f"{library_type}: active {RUNTIME_VERSION} release missing")
                continue

            manifest = release.source_manifest or {}
            records = manifest.get("records") or []
            if not release.release_hash or canonical_hash(manifest) != release.release_hash:
                errors.append(f"{library_type}: release manifest/hash mismatch")
            if not records:
                errors.append(f"{library_type}: release contains no record identifiers")

            payload["releases"][library_type] = {
                "release_id": release.id,
                "release_hash": release.release_hash,
                "record_count": len(records),
                "status": release.status,
            }

            if library_type == "pricing" and len(records) != 897:
                errors.append(f"pricing: expected 897 runtime records, found {len(records)}")
            if library_type == "technical" and len(records) != 2860:
                errors.append(f"technical: expected 2860 runtime records, found {len(records)}")
            if library_type == "labour":
                uat_keys = [
                    str(row.get("key"))
                    for row in records
                    if isinstance(row, dict) and str(row.get("key") or "").upper().startswith("UAT-LAB-")
                ]
                if uat_keys:
                    errors.append("labour: UAT-only labour anchors leaked into runtime release: " + ", ".join(uat_keys))
                coverage = manifest.get("productivity_coverage") or {}
                payload["productivity_coverage"] = coverage
                missing = int(coverage.get("missing_activity_count") or 0)
                if missing and not coverage.get("human_acknowledged_incomplete_coverage"):
                    errors.append("labour: incomplete productivity coverage was not explicitly acknowledged")
                if missing and coverage.get("runtime_behavior") != "FAIL_CLOSED_ON_SELECTED_VARIANT_REQUIRING_UNCOVERED_ACTIVITY":
                    errors.append("labour: incomplete productivity coverage is not marked fail-closed")

    payload["errors"] = errors
    payload["ok"] = not errors
    print(json.dumps(payload, indent=2, default=str))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
