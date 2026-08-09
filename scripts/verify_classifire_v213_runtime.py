from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sqlalchemy import select

from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.db import SessionLocal
from classifire.models import Approval, LibraryRelease, PricingLibraryRecord, TechnicalVariant
from classifire.services.release_pinning import active_release
from classifire.services.release_scope import _manifest_hash


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _gate(gates: list[dict], gate_id: str, passed: bool, detail) -> None:
    gates.append({"gate_id": gate_id, "passed": bool(passed), "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify CLASSIFIRE v2.13 source-scoped runtime Pricing and Technical releases."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=repo_root() / "private-data" / "controlled-source" / "v2.13",
    )
    parser.add_argument("--promotion-receipt", type=Path, default=None)
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    promotion_path = args.promotion_receipt or (
        source_root / "CLASSIFIRE_V213_RUNTIME_PROMOTION.json"
    )
    if not promotion_path.is_file():
        raise RuntimeError(f"Promotion receipt not found: {promotion_path}")
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    if promotion.get("schema") != "CLASSIFIRE-V213-RUNTIME-PROMOTION-RECEIPT-v1":
        raise RuntimeError("Promotion receipt schema is not recognised.")

    pricing_id = str((promotion.get("pricing_runtime_release") or {}).get("release_id") or "")
    technical_id = str((promotion.get("technical_runtime_release") or {}).get("release_id") or "")
    validation_token = str(promotion.get("validation_approval_token") or "")
    gates: list[dict] = []

    with SessionLocal() as db:
        pricing = db.get(LibraryRelease, pricing_id) if pricing_id else None
        technical = db.get(LibraryRelease, technical_id) if technical_id else None
        _gate(gates, "PRICING_RUNTIME_RELEASE_PRESENT", pricing is not None, pricing_id)
        _gate(gates, "TECHNICAL_RUNTIME_RELEASE_PRESENT", technical is not None, technical_id)
        if pricing is None or technical is None:
            result = {"ok": False, "gates": gates}
        else:
            _gate(gates, "PRICING_RUNTIME_ACTIVE", pricing.status == "active", pricing.status)
            _gate(gates, "TECHNICAL_RUNTIME_ACTIVE", technical.status == "active", technical.status)
            _gate(gates, "PRICING_RUNTIME_TYPE", pricing.library_type == "pricing", pricing.library_type)
            _gate(gates, "TECHNICAL_RUNTIME_TYPE", technical.library_type == "technical", technical.library_type)
            _gate(
                gates,
                "RUNTIME_VERSION_MATCH",
                pricing.version == promotion.get("runtime_version")
                and technical.version == promotion.get("runtime_version"),
                {"pricing": pricing.version, "technical": technical.version},
            )

            pricing_manifest = pricing.source_manifest or {}
            technical_manifest = technical.source_manifest or {}
            _gate(
                gates,
                "PRICING_MANIFEST_HASH_VALID",
                _manifest_hash(pricing_manifest) == pricing.release_hash,
                pricing.release_hash,
            )
            _gate(
                gates,
                "TECHNICAL_MANIFEST_HASH_VALID",
                _manifest_hash(technical_manifest) == technical.release_hash,
                technical.release_hash,
            )
            _gate(
                gates,
                "VALIDATION_TOKEN_BOUND",
                pricing_manifest.get("validation_approval_token") == validation_token
                and technical_manifest.get("validation_approval_token") == validation_token,
                validation_token,
            )

            pricing_source_id = str(pricing_manifest.get("source_release_id") or "")
            technical_source_id = str(technical_manifest.get("source_release_id") or "")
            pricing_source = db.get(LibraryRelease, pricing_source_id) if pricing_source_id else None
            technical_source = db.get(LibraryRelease, technical_source_id) if technical_source_id else None
            _gate(
                gates,
                "SOURCE_RELEASES_REMAIN_DRAFT",
                pricing_source is not None
                and technical_source is not None
                and pricing_source.status == "draft"
                and technical_source.status == "draft",
                {
                    "pricing": pricing_source.status if pricing_source else None,
                    "technical": technical_source.status if technical_source else None,
                },
            )

            pricing_source_ids = set(
                db.scalars(
                    select(PricingLibraryRecord.id).where(
                        PricingLibraryRecord.release_id == pricing_source_id
                    )
                ).all()
            )
            technical_source_records = list(
                db.scalars(
                    select(TechnicalVariant).where(
                        TechnicalVariant.release_id == technical_source_id
                    )
                ).all()
            )
            technical_active_ids = {
                item.id for item in technical_source_records if item.status == "active"
            }
            technical_inactive_ids = {
                item.id for item in technical_source_records if item.status != "active"
            }
            pricing_runtime_ids = {
                str(item.get("id"))
                for item in pricing_manifest.get("records", [])
                if isinstance(item, dict) and item.get("id")
            }
            technical_runtime_ids = {
                str(item.get("id"))
                for item in technical_manifest.get("records", [])
                if isinstance(item, dict) and item.get("id")
            }
            _gate(
                gates,
                "PRICING_RUNTIME_EXACT_SOURCE_SCOPE",
                len(pricing_runtime_ids) == 897 and pricing_runtime_ids == pricing_source_ids,
                {"runtime": len(pricing_runtime_ids), "source": len(pricing_source_ids)},
            )
            _gate(
                gates,
                "TECHNICAL_RUNTIME_EXACT_ACTIVE_SOURCE_SCOPE",
                len(technical_runtime_ids) == 2860
                and technical_runtime_ids == technical_active_ids,
                {"runtime": len(technical_runtime_ids), "active_source": len(technical_active_ids)},
            )
            _gate(
                gates,
                "TECHNICAL_INACTIVE_SOURCE_EXCLUDED",
                len(technical_inactive_ids) == 1
                and technical_runtime_ids.isdisjoint(technical_inactive_ids),
                {"inactive_source": len(technical_inactive_ids)},
            )

            pricing_approvals = list(
                db.scalars(
                    select(Approval).where(
                        Approval.entity_type == "library_release",
                        Approval.entity_id == pricing.id,
                        Approval.approval_type == "pricing_runtime_release_activation",
                        Approval.status == "approved",
                    )
                ).all()
            )
            technical_approvals = list(
                db.scalars(
                    select(Approval).where(
                        Approval.entity_type == "library_release",
                        Approval.entity_id == technical.id,
                        Approval.approval_type == "technical_runtime_release_activation",
                        Approval.status == "approved",
                    )
                ).all()
            )
            _gate(
                gates,
                "PRICING_HUMAN_APPROVAL_RECORDED",
                len(pricing_approvals) == 1
                and pricing_approvals[0].decided_by_id == pricing.approved_by_id
                and pricing_approvals[0].snapshot_hash == pricing.release_hash,
                len(pricing_approvals),
            )
            _gate(
                gates,
                "TECHNICAL_HUMAN_APPROVAL_RECORDED",
                len(technical_approvals) == 1
                and technical_approvals[0].decided_by_id == technical.approved_by_id
                and technical_approvals[0].snapshot_hash == technical.release_hash,
                len(technical_approvals),
            )

            latest_pricing = active_release(db, "pricing")
            latest_technical = active_release(db, "technical")
            _gate(
                gates,
                "RUNTIME_RELEASES_ARE_CURRENT_ACTIVE_BASIS",
                latest_pricing is not None
                and latest_technical is not None
                and latest_pricing.id == pricing.id
                and latest_technical.id == technical.id,
                {
                    "pricing": latest_pricing.id if latest_pricing else None,
                    "technical": latest_technical.id if latest_technical else None,
                },
            )
            result = {
                "ok": all(item["passed"] for item in gates),
                "runtime_version": promotion.get("runtime_version"),
                "pricing_runtime_release_id": pricing.id,
                "technical_runtime_release_id": technical.id,
                "pricing_record_count": len(pricing_runtime_ids),
                "technical_record_count": len(technical_runtime_ids),
                "validation_approval_token": validation_token,
                "gates": gates,
            }

    result["verified_utc"] = datetime.now(timezone.utc).isoformat()
    receipt = source_root / "CLASSIFIRE_V213_RUNTIME_VERIFICATION.json"
    receipt.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"Runtime verification receipt: {receipt}", file=sys.stderr)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"CLASSIFIRE v2.13 runtime verification failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
