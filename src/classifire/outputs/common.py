from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any

ATTRIBUTION = "CLASSIFIRE is an estimating system produced and developed by Ceasefire PFP."


def d(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def verify_snapshot(snapshot: dict[str, Any]) -> None:
    expected = snapshot.get("snapshot_hash")
    payload = dict(snapshot)
    payload.pop("snapshot_hash", None)
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    if not expected or expected != actual:
        raise ValueError("Snapshot hash is missing or invalid; output generation is blocked")


def logo_path() -> Path | None:
    package_root = Path(__file__).resolve().parents[3]
    candidates = [
        Path(__file__).resolve().parents[1] / "static" / "brand" / "classifire-logo-master.png",
        package_root / "assets" / "brand" / "classifire-logo-master.png",
        Path.cwd() / "assets" / "brand" / "classifire-logo-master.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
