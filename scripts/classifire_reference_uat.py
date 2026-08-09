from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from classifire.config import get_settings
from classifire.db import SessionLocal
from classifire.uat_reference import inspect_reference_uat, prepare_reference_uat


def _default_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


def prepare(run_id: str) -> int:
    with SessionLocal() as db:
        try:
            fixture = prepare_reference_uat(db, run_id=run_id)
            db.commit()
        except Exception as exc:
            db.rollback()
            _print({"ok": False, "error": str(exc), "run_id": run_id})
            return 1
    _print({"ok": True, **fixture.as_dict()})
    return 0


def verify(estimate_id: str, expected_stage: str | None) -> int:
    with SessionLocal() as db:
        payload = inspect_reference_uat(
            db,
            estimate_id=estimate_id,
            settings=get_settings(),
            expected_stage=expected_stage,
        )
    _print(payload)
    return 0 if payload.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare and verify the synthetic governed CLASSIFIRE OpenClaw reference UAT."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare_parser = sub.add_parser("prepare", help="Create a fresh reference UAT estimate.")
    prepare_parser.add_argument("--run-id", default=_default_run_id())

    verify_parser = sub.add_parser("verify", help="Verify retained UAT state and optional workflow stage.")
    verify_parser.add_argument("--estimate-id", required=True)
    verify_parser.add_argument("--expect-stage")

    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args.run_id)
    if args.command == "verify":
        return verify(args.estimate_id, args.expect_stage)
    return 2


if __name__ == "__main__":
    sys.exit(main())
