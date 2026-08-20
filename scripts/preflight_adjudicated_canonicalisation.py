"""Create one fresh, no-write adjudicated preflight receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.db import SessionLocal
from classifire.services.adjudicated_preflight import (
    AdjudicatedPreflightError,
    build_adjudicated_preflight,
    preflight_receipt_bytes,
)


def _mapping(values: list[str], *, label: str, paths: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    for value in values:
        name, separator, item = value.partition("=")
        if not separator or not name or not item or name in result:
            raise AdjudicatedPreflightError(f"PREFLIGHT_{label}_ARGUMENT_INVALID")
        result[name] = Path(item) if paths else item
    if not result:
        raise AdjudicatedPreflightError(f"PREFLIGHT_{label}_ARGUMENT_INVALID")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument("--submission-payload", type=Path, required=True)
    parser.add_argument("--source-run-id", required=True)
    parser.add_argument("--adjudicated-run-id", required=True)
    parser.add_argument("--artifact", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument("--policy", action="append", default=[], metavar="NAME=VERSION")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise AdjudicatedPreflightError("PREFLIGHT_OUTPUT_EXISTS")
        payload = json.loads(args.submission_payload.read_text(encoding="utf-8"))
        artifact_files = _mapping(args.artifact, label="ARTIFACT", paths=True)
        policy_versions = _mapping(args.policy, label="POLICY", paths=False)
        with SessionLocal() as db:
            receipt = build_adjudicated_preflight(
                db,
                estimate_id=args.estimate_id,
                submission_payload=payload,
                source_run_id=args.source_run_id,
                adjudicated_run_id=args.adjudicated_run_id,
                artifact_files=artifact_files,  # type: ignore[arg-type]
                policy_versions=policy_versions,  # type: ignore[arg-type]
            )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(preflight_receipt_bytes(receipt))
    except (AdjudicatedPreflightError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        code = exc.code if isinstance(exc, AdjudicatedPreflightError) else "PREFLIGHT_INPUT_INVALID"
        print(json.dumps({"status": "BLOCKED", "code": code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {"status": "READY_FOR_EXTERNAL_SIGNATURE", "output": str(args.output)},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
