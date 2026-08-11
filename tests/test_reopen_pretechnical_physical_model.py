from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reopen_pretechnical_physical_model.py"


def test_reopen_script_is_fail_closed_for_downstream_work() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "RepairStrategy" in source
    assert "RepairStrategyLock" in source
    assert "SystemRequiredComponent" in source
    assert "Controlled cascade invalidation is required" in source


def test_reopen_script_invalidates_lock_before_removing_physical_rows() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "lock.invalidated_at = now" in source
    assert "lock.invalidation_reason = reason" in source
    assert "delete(ServiceOpeningLink)" in source
    assert "delete(Service)" in source
    assert "delete(Opening)" in source
    assert "reopen_pretechnical_physical_model" in source


def test_reopen_preserves_evidence_and_defects() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "delete(EvidenceSource)" not in source
    assert "delete(Defect)" not in source
    assert "CLASSIFIRE controlled UAT topology correction" in source
