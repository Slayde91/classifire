from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from sqlalchemy import select

from classifire.auxiliary_runtime_promotion import (
    CONFIRMATION_PHRASE,
    AuxiliaryRuntimePromotionError,
    inspect_auxiliary_runtime_basis,
    promote_auxiliary_runtime_releases,
)
from classifire.config import get_settings
from classifire.db import SessionLocal
from classifire.models import User


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or human-promote the governed CLASSIFIRE v2.13 auxiliary runtime "
            "Rules, Products, Labour and Markups releases."
        )
    )
    parser.add_argument("--inspect", action="store_true", help="Read-only inspection; make no database changes.")
    parser.add_argument("--approver-email", default=settings.admin_email)
    parser.add_argument("--confirm", default="")
    parser.add_argument(
        "--acknowledge-missing-productivity",
        action="store_true",
        help=(
            "Explicitly acknowledge that uncovered Package 15 labour activities remain fail-closed "
            "until approved ProductivitySource records are added."
        ),
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=(
            repo_root()
            / "private-data"
            / "controlled-source"
            / "v2.13"
            / "CLASSIFIRE_V213_AUXILIARY_RUNTIME_PROMOTION.json"
        ),
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.inspect:
            result = inspect_auxiliary_runtime_basis(db)
            print(json.dumps(result, indent=2, default=str))
            return 0

        approver = db.scalar(
            select(User).where(User.email == args.approver_email.lower(), User.is_active.is_(True))
        )
        if approver is None:
            raise AuxiliaryRuntimePromotionError(
                f"Active CLASSIFIRE approver user not found: {args.approver_email}"
            )

        result = promote_auxiliary_runtime_releases(
            db,
            approver=approver,
            confirmation_phrase=args.confirm,
            acknowledge_missing_productivity=args.acknowledge_missing_productivity,
        )

    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    result["receipt_path"] = str(args.receipt.resolve())
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CLASSIFIRE auxiliary runtime promotion failed: {exc}", file=sys.stderr)
        print(f"Required confirmation phrase: {CONFIRMATION_PHRASE}", file=sys.stderr)
        raise SystemExit(1)
