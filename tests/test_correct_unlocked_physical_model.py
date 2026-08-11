from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from correct_unlocked_physical_model import correct_unlocked_physical_model  # noqa: E402,F401
from classifire.db import Base  # noqa: E402


def test_physical_correction_loads_audit_trail_metadata() -> None:
    """Regression for AuditEvent.audit_trail_id mapper configuration failure."""
    assert "audit_trails" in Base.metadata.tables
    assert "audit_events" in Base.metadata.tables
