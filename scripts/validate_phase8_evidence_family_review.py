"""Validate a declaration-only Phase 8 evidence-family review record."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from classifire.services.phase8_evidence_family_review import (
    validate_phase8_evidence_family_review,
)


def _read_json(path: Path) -> object:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    args = parser.parse_args()
    result = validate_phase8_evidence_family_review(
        evidence_family_inventory=_read_json(args.inventory),
        review=_read_json(args.review),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
