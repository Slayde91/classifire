from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

from classifire.config import get_settings
from classifire.db import SessionLocal
from classifire.mission_control import MissionControlClient
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


def receipt(run_id: str, estimate_id: str) -> int:
    settings = get_settings()
    key = settings.mission_control_api_key
    if not key:
        _print({"ok": False, "error": "Mission Control API key is not configured"})
        return 1

    with SessionLocal() as db:
        inspection = inspect_reference_uat(
            db,
            estimate_id=estimate_id,
            settings=settings,
            expected_stage="human_release",
        )
    if not inspection.get("ok"):
        _print({"ok": False, "error": "UAT is not ready for Mission Control review", "inspection": inspection})
        return 1

    client = MissionControlClient(settings.mission_control_url, key)
    task = client.find_task(task_id="CF-UAT-001")
    if task is None:
        _print({"ok": False, "error": "CF-UAT-001 was not found in Mission Control"})
        return 1
    row_id = task.get("id")
    if not isinstance(row_id, int):
        _print({"ok": False, "error": "CF-UAT-001 has no numeric Mission Control row id"})
        return 1

    resolution = (
        f"CLASSIFIRE OpenClaw reference UAT {run_id} reached human_release with deterministic "
        f"independent validation PASS, immutable snapshot {inspection.get('snapshot_hash')}, and "
        "controlled technical/proposal workbook outputs. Human Release remains unapproved and must "
        "be performed separately by an authorised human."
    )
    updated = client.update_task(row_id, status="review", resolution=resolution)
    _print(
        {
            "ok": True,
            "task_id": "CF-UAT-001",
            "mission_control_id": row_id,
            "status": "review",
            "run_id": run_id,
            "estimate_id": estimate_id,
            "updated": updated,
        }
    )
    return 0


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

    receipt_parser = sub.add_parser(
        "receipt",
        help="Move CF-UAT-001 to Mission Control review after the UAT reaches human_release.",
    )
    receipt_parser.add_argument("--run-id", required=True)
    receipt_parser.add_argument("--estimate-id", required=True)

    args = parser.parse_args()
    if args.command == "prepare":
        return prepare(args.run_id)
    if args.command == "verify":
        return verify(args.estimate_id, args.expect_stage)
    if args.command == "receipt":
        return receipt(args.run_id, args.estimate_id)
    return 2


if __name__ == "__main__":
    sys.exit(main())
