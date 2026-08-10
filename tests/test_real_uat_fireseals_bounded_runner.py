from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_bounded import (  # noqa: E402
    BOUNDED_DEFECT_EVIDENCE_CHARS,
    BoundedFireSealFocusedController,
)


def test_measured_real_uat_bundle_fits_revised_budget() -> None:
    assert BOUNDED_DEFECT_EVIDENCE_CHARS == 12_000
    assert 9_923 < BOUNDED_DEFECT_EVIDENCE_CHARS


def test_bounded_runner_overrides_only_defect_bundle_construction() -> None:
    assert "_bundle_for_defect" in BoundedFireSealFocusedController.__dict__
    assert "run" not in BoundedFireSealFocusedController.__dict__


def test_bounded_runner_retains_deterministic_non_reduction_path() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_bounded.py").read_text(
        encoding="utf-8"
    )
    assert "build_bounded_defect_bundle" in source
    assert "max_chars=BOUNDED_DEFECT_EVIDENCE_CHARS" in source
    assert "_reduce_physical_evidence" not in source
    assert "No model was submitted" in source
