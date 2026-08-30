"""Validate a hash-bound Phase 8 human-adjudicated proposal without writing state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.services.phase8_human_adjudicated_proposal import (
    validate_phase8_human_adjudicated_proposal,
    validate_phase8_human_adjudicated_proposal_with_visual_provenance,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-proposal", type=Path, required=True)
    parser.add_argument("--source-controller-receipt", type=Path, required=True)
    parser.add_argument("--source-evidence-manifest", type=Path)
    parser.add_argument("--human-review-response", type=Path, required=True)
    parser.add_argument("--human-review-request", type=Path, required=True)
    parser.add_argument("--revised-proposal", type=Path, required=True)
    parser.add_argument("--linked-visual-run-receipt", type=Path)
    parser.add_argument("--evidence-family-inventory", type=Path)
    args = parser.parse_args()

    if bool(args.linked_visual_run_receipt) != bool(args.evidence_family_inventory):
        parser.error(
            "--linked-visual-run-receipt and --evidence-family-inventory must be supplied together"
        )
    common = {
        "source_proposal_path": args.source_proposal,
        "source_controller_receipt_path": args.source_controller_receipt,
        "source_evidence_manifest_path": args.source_evidence_manifest,
        "human_review_response_path": args.human_review_response,
        "human_review_request_path": args.human_review_request,
        "revised_proposal_path": args.revised_proposal,
    }
    if args.linked_visual_run_receipt:
        result = validate_phase8_human_adjudicated_proposal_with_visual_provenance(
            **common,
            linked_visual_run_receipt_path=args.linked_visual_run_receipt,
            evidence_family_inventory_path=args.evidence_family_inventory,
        )
    else:
        result = validate_phase8_human_adjudicated_proposal(**common)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
