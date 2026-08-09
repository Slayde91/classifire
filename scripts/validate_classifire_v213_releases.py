from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from classifire import canonical_models as _canonical_models  # noqa: F401
from classifire import commercial_models as _commercial_models  # noqa: F401
from classifire.db import SessionLocal
from classifire.v213_release_validation import validate_v213_releases


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate imported CLASSIFIRE v2.13 Package 14/15/17 source releases without activating them."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=repo_root() / "private-data" / "controlled-source" / "v2.13",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        default=None,
        help="Optional validation receipt path. Defaults inside the controlled source root.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        result = validate_v213_releases(db, args.source_root)

    result["validated_utc"] = datetime.now(timezone.utc).isoformat()
    receipt = args.receipt or (
        args.source_root / "CLASSIFIRE_V213_RELEASE_VALIDATION.json"
    )
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, default=str))
    print(f"Validation receipt: {receipt}", file=sys.stderr)
    return 0 if result.get("hard_gates_passed") else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"CLASSIFIRE v2.13 release validation failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
