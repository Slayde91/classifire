from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_blankaware import (  # noqa: E402
    PHYSICAL_SYNTHESIS_POLICY_VERSION,
    BlankAwareFireSealFocusedController,
    _model_completeness_issues,
)


def _opening(opening_type: str) -> dict:
    return {
        "opening_code": "D-O-001",
        "substrate_type": "concrete",
        "substrate_plane": "floor",
        "orientation": "horizontal",
        "opening_type": opening_type,
        "frl": None,
    }


def test_blank_core_hole_does_not_require_placeholder_service() -> None:
    model = {
        "status": "MODEL_SUPPORTED",
        "openings": [_opening("blank_core_hole")],
        "services": [],
    }
    assert _model_completeness_issues(model) == []


def test_blank_opening_alias_is_accepted_without_service() -> None:
    model = {
        "status": "MODEL_SUPPORTED",
        "openings": [_opening("redundant core hole")],
        "services": [],
    }
    assert _model_completeness_issues(model) == []


def test_service_penetration_without_service_is_rejected() -> None:
    model = {
        "status": "MODEL_SUPPORTED",
        "openings": [_opening("service_penetration")],
        "services": [],
    }
    issues = _model_completeness_issues(model)
    assert any("has no Service" in issue for issue in issues)


def test_blank_opening_with_service_is_rejected_as_contradictory() -> None:
    model = {
        "status": "MODEL_SUPPORTED",
        "openings": [_opening("blank_core_hole")],
        "services": [
            {
                "service_code": "D-S-001",
                "primary_opening_code": "D-O-001",
                "opening_codes": ["D-O-001"],
                "service_type": "pipe",
                "quantity": 1,
            }
        ],
    }
    issues = _model_completeness_issues(model)
    assert any("classified blank but has linked Services" in issue for issue in issues)


def test_missing_substrate_fields_trigger_photo_assumption_repair() -> None:
    model = {
        "status": "MODEL_SUPPORTED",
        "openings": [
            {
                "opening_code": "D-O-001",
                "opening_type": "blank_core_hole",
                "substrate_type": None,
                "substrate_plane": None,
                "orientation": None,
            }
        ],
        "services": [],
    }
    issues = _model_completeness_issues(model)
    assert any("substrate_type" in issue for issue in issues)
    assert any("substrate_plane" in issue for issue in issues)
    assert any("orientation" in issue for issue in issues)


def test_blankaware_policy_forces_new_cache_generation() -> None:
    assert "BLANK-OPENING" in PHYSICAL_SYNTHESIS_POLICY_VERSION
    assert "PHOTO-ASSUMPTIONS" in PHYSICAL_SYNTHESIS_POLICY_VERSION


def test_runner_prompt_contains_binding_corrections() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_blankaware.py").read_text(
        encoding="utf-8"
    )
    assert "An Opening does NOT require a Service" in source
    assert "return NO placeholder Service" in source
    assert "use the defect-linked full-page" in source
    assert "`-/120/120`" in source
    assert "technical selection remains" in source
    assert "physical_synthesis_policy_version" in source


def test_runner_overrides_cache_synthesis_prompt_and_remap() -> None:
    for name in (
        "defect_physical_prompt",
        "_save_cache_metadata",
        "_cached_supported_model",
        "_synthesise_defect",
        "_validate_and_remap_defect_model",
    ):
        assert name in BlankAwareFireSealFocusedController.__dict__
