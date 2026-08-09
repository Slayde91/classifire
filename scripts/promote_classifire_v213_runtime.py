from __future__ import annotations

import argparse
from getpass import getpass
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sqlalchemy import select

from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.db import SessionLocal
from classifire.models import User
from classifire.security import verify_password
from classifire.v213_release_promotion import (
    RUNTIME_VERSION,
    V213PromotionError,
    promote_v213_runtime_releases,
)
from classifire.v213_release_validation import validate_v213_releases


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_receipt(path: Path) -> dict:
    if not path.is_file():
        raise V213PromotionError(f"Validation receipt not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise V213PromotionError(f"Validation receipt is invalid JSON: {path}") from exc
    if payload.get("schema") != "CLASSIFIRE-V213-RELEASE-VALIDATION-v1":
        raise V213PromotionError("Validation receipt schema is not recognised.")
    if not payload.get("hard_gates_passed"):
        raise V213PromotionError("Validation receipt does not show passing hard gates.")
    if not payload.get("approval_token"):
        raise V213PromotionError("Validation receipt has no approval token.")
    return payload


def _authenticate(db, email: str, label: str) -> User:
    user = db.scalar(
        select(User).where(User.email == email.strip().lower(), User.is_active.is_(True))
    )
    if user is None:
        raise V213PromotionError(f"{label} user not found or inactive: {email}")
    password = getpass(f"Password for {user.email} ({label}): ")
    if not verify_password(password, user.password_hash):
        raise V213PromotionError(f"Authentication failed for {label}: {user.email}")
    return user


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Human-controlled promotion of validated CLASSIFIRE v2.13 Package 14 and "
            "Package 15/17 source releases into source-scoped immutable runtime releases."
        )
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=repo_root() / "private-data" / "controlled-source" / "v2.13",
    )
    parser.add_argument(
        "--validation-receipt",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--runtime-version",
        default=RUNTIME_VERSION,
    )
    args = parser.parse_args()

    source_root = args.source_root.expanduser().resolve()
    validation_receipt_path = args.validation_receipt or (
        source_root / "CLASSIFIRE_V213_RELEASE_VALIDATION.json"
    )
    receipt = _load_receipt(validation_receipt_path)

    with SessionLocal() as db:
        live = validate_v213_releases(db, source_root)
        receipt_token = str(receipt.get("approval_token") or "")
        live_token = str(live.get("approval_token") or "")
        if not live.get("hard_gates_passed"):
            raise V213PromotionError("Live validation no longer passes; promotion is blocked.")
        if receipt_token != live_token:
            raise V213PromotionError(
                "Validation approval token changed since the receipt was generated. "
                "Run validate_classifire_v213_releases.py again before approval."
            )

        print("CLASSIFIRE v2.13 controlled runtime promotion")
        print(f"Readiness: {live.get('readiness')}")
        print(f"Approval token: {live_token}")
        print(f"Runtime version: {args.runtime_version}")
        print()
        print("This action will create new active runtime releases scoped only to the validated")
        print("v2.13 source record IDs. The imported v2.13 source releases remain draft evidence.")
        print()

        acknowledgements: set[str] = set()
        conditions = list(live.get("conditions") or [])
        if conditions:
            print("The following validation conditions require explicit human acknowledgement:")
            for item in conditions:
                condition_id = str(item.get("condition_id") or "")
                print()
                print(f"[{condition_id}]")
                print(json.dumps(item.get("detail"), indent=2, default=str))
                print(str(item.get("required_acknowledgement") or ""))
                response = input("Type ACKNOWLEDGE to accept this condition: ").strip()
                if response != "ACKNOWLEDGE":
                    raise V213PromotionError(
                        f"Condition {condition_id} was not acknowledged; promotion cancelled."
                    )
                acknowledgements.add(condition_id)

        print()
        pricing_email = input("Pricing approver email: ").strip().lower()
        technical_email = input("Technical approver email: ").strip().lower()
        if not pricing_email or not technical_email:
            raise V213PromotionError("Both pricing and technical approver emails are required.")

        if pricing_email == technical_email:
            shared = _authenticate(db, pricing_email, "pricing + technical approval")
            pricing_approver = shared
            technical_approver = shared
        else:
            pricing_approver = _authenticate(db, pricing_email, "pricing approval")
            technical_approver = _authenticate(db, technical_email, "technical approval")

        print()
        print("Final confirmation will activate new Pricing and Technical runtime releases.")
        confirm = input("Type PROMOTE CLASSIFIRE V2.13 to continue: ").strip()
        if confirm != "PROMOTE CLASSIFIRE V2.13":
            raise V213PromotionError("Final confirmation phrase did not match; promotion cancelled.")

        result = promote_v213_runtime_releases(
            db,
            source_root,
            approval_token=live_token,
            acknowledged_condition_ids=acknowledgements,
            pricing_approver=pricing_approver,
            technical_approver=technical_approver,
            runtime_version=args.runtime_version,
        )

    result["promoted_utc"] = datetime.now(timezone.utc).isoformat()
    result["validation_receipt"] = str(validation_receipt_path)
    promotion_receipt = source_root / "CLASSIFIRE_V213_RUNTIME_PROMOTION.json"
    promotion_receipt.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print()
    print(json.dumps(result, indent=2, default=str))
    print(f"Promotion receipt: {promotion_receipt}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Promotion cancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"CLASSIFIRE v2.13 runtime promotion failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
