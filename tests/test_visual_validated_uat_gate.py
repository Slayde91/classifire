from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_visualvalidated import (  # noqa: E402
    VisualValidatedTopologyController,
)


def _proposal() -> dict:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": [
            {
                "opening_code": "O-A",
                "opening_type": "service_penetration",
                "substrate_type": "block wall",
                "substrate_plane": "wall",
                "orientation": "vertical",
            }
        ],
        "services": [
            {
                "service_code": "S-A",
                "primary_opening_code": "O-A",
                "opening_codes": ["O-A"],
                "service_type": "pipe",
                "material": "PEX",
                "quantity": 2,
            }
        ],
    }


def _approved() -> dict:
    return {
        "verdict": "APPROVED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "issues": [],
        "limitations": [],
    }


def _rejected() -> dict:
    return {
        "verdict": "REJECTED",
        "observed_opening_count": 2,
        "observed_service_group_count": 1,
        "issues": [
            {
                "code": "MISSED_OPENING",
                "detail": "A second distinct core hole is visible.",
                "evidence_refs": ["photo-a.png"],
            }
        ],
        "limitations": [],
    }


def _bare_controller(tmp_path: Path, responses: list[dict]) -> VisualValidatedTopologyController:
    controller = object.__new__(VisualValidatedTopologyController)
    controller.receipt_dir = tmp_path
    controller.run_id = "test-run"
    controller.estimate_id = "estimate-test"
    controller._visual_physical_session = "physical-session"
    controller._visual_validator_session = "validator-session"

    image_path = tmp_path / "photo-a.png"
    image_path.write_bytes(b"not-a-real-image-needed-for-unit-test")

    controller._ensure_visual_sessions = lambda: ("physical-session", "validator-session")
    controller._visual_files_for_defect = lambda _i, _d: (
        [image_path],
        [{"role": "defect_photo", "path": str(image_path)}],
    )
    controller._cached_visual_approved_model = lambda _i, _b, _f: None
    controller._visual_gate_cache_key = lambda _b, _f: {"test": True}
    controller._invoke_image_tool_json = lambda **_kwargs: responses.pop(0)
    return controller


def test_visual_gate_returns_supported_model_only_after_validator_approval(tmp_path: Path) -> None:
    proposal = _proposal()
    controller = _bare_controller(tmp_path, [proposal, _approved()])
    defect = SimpleNamespace(id="d1", external_defect_id="147031", defect_code="147031")

    result = controller._synthesise_defect(1, defect, "{}")

    assert result == proposal
    assert (tmp_path / "21-visual-defect-001-approved-model.json").is_file()
    assert (tmp_path / "21-visual-defect-001-approved-validator.json").is_file()


def test_visual_gate_repeated_rejection_returns_insufficient_evidence(tmp_path: Path) -> None:
    proposal = _proposal()
    controller = _bare_controller(
        tmp_path,
        [
            proposal,
            _rejected(),
            proposal,
            _rejected(),
            proposal,
            _rejected(),
        ],
    )
    defect = SimpleNamespace(id="d1", external_defect_id="147038", defect_code="147038")

    result = controller._synthesise_defect(1, defect, "{}")

    assert result["status"] == "INSUFFICIENT_EVIDENCE"
    assert result["openings"] == []
    assert result["services"] == []
    assert any("remained REJECTED" in item for item in result["limitations"])
    assert not (tmp_path / "21-visual-defect-001-approved-model.json").exists()
