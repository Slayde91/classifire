"""Assess current Phase 8 visual provenance from content-free JSON artefacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.services.phase8_visual_provenance import (
    assess_phase8_visual_provenance_completeness,
)


def _read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linked-visual-run-receipt", type=Path, required=True)
    parser.add_argument("--evidence-family-inventory", type=Path, required=True)
    parser.add_argument("--estimate-id", required=True)
    parser.add_argument("--defect-reference", required=True)
    args = parser.parse_args()
    assessment = assess_phase8_visual_provenance_completeness(
        estimate_id=args.estimate_id,
        defect_reference=args.defect_reference,
        linked_visual_run_receipt=_read_json(args.linked_visual_run_receipt),
        evidence_family_inventory=_read_json(args.evidence_family_inventory),
    )
    print(json.dumps(assessment.as_dict(), indent=2, ensure_ascii=False))
    return 0 if assessment.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
