"""Compare a completed Phase 8 proposal with a validation-only reference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.services.phase8_human_reference_comparison import (
    compare_phase8_human_reference,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--proposal", type=Path, required=True)
    parser.add_argument("--controller-receipt", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--evidence-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = compare_phase8_human_reference(
        proposal_path=args.proposal,
        controller_receipt_path=args.controller_receipt,
        reference_path=args.reference,
        evidence_manifest_path=args.evidence_manifest,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output is not None:
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
