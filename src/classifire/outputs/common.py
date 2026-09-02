from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

from ..services.snapshot import verify_estimate_snapshot

ATTRIBUTION = "QUANTIFIRE is an estimating system produced and developed by Ceasefire PFP."


def d(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def verify_snapshot(snapshot: dict[str, Any]) -> None:
    verify_estimate_snapshot(snapshot)


def logo_path() -> Path:
    package_root = Path(__file__).resolve().parents[3]
    candidates = [
        Path(__file__).resolve().parents[1] / "static" / "brand" / "quantifire-logo-master.png",
        package_root / "assets" / "brand" / "quantifire-logo-master.png",
        Path.cwd() / "assets" / "brand" / "quantifire-logo-master.png",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Approved QUANTIFIRE logo asset not found")
