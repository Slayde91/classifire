"""Derive a clean-stack canonical payload from the four approved Phase 8 receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.db import SessionLocal
from classifire.services.adjudicated_preflight import canonical_json_bytes
from classifire.services.phase8_adjudicated_payload import (
    Phase8AdjudicatedPayloadError,
    derive_phase8_adjudicated_payload,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument("--adjudicated-proposal", type=Path, required=True)
    parser.add_argument("--adjudicated-final-state", type=Path, required=True)
    parser.add_argument("--adjudicated-diff", type=Path, required=True)
    parser.add_argument("--human-comparison", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        if args.output is not None and args.output.exists():
            raise Phase8AdjudicatedPayloadError("ADJUDICATED_OUTPUT_EXISTS")
        with SessionLocal() as db:
            result = derive_phase8_adjudicated_payload(
                db,
                estimate_id=args.estimate_id,
                adjudicated_proposal_path=args.adjudicated_proposal,
                adjudicated_final_state_path=args.adjudicated_final_state,
                adjudicated_diff_path=args.adjudicated_diff,
                human_comparison_path=args.human_comparison,
            )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_bytes(canonical_json_bytes(result.payload))
    except (Phase8AdjudicatedPayloadError, OSError) as exc:
        code = (
            exc.code
            if isinstance(exc, Phase8AdjudicatedPayloadError)
            else "ADJUDICATED_OUTPUT_INVALID"
        )
        print(json.dumps({"status": "BLOCKED", "code": code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "status": "VALIDATED",
                "payload_sha256": result.payload_sha256,
                "opening_count": len(result.payload["openings"]),
                "service_count": len(result.payload["services"]),
                "link_count": len(result.payload["service_opening_links"]),
                "source_run_id": result.source_run_id,
                "adjudicated_run_id": result.adjudicated_run_id,
                "output": str(args.output) if args.output is not None else None,
                "database_write_performed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
