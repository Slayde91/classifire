from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_assumptionaware import (  # noqa: E402
    AssumptionAwareController,
    DEFAULT_ASSUMED_FRL,
    DEFAULT_ASSUMED_FRL_NOTE,
)


def test_missing_frl_is_defaulted_and_annotated() -> None:
    controller = object.__new__(AssumptionAwareController)
    model = {
        "openings": [
            {"opening_code": "D-O-001", "frl": None, "notes": None},
            {"opening_code": "D-O-002", "frl": "-/90/90", "notes": "source stated"},
        ],
        "services": [],
    }
    result = controller._apply_estimation_defaults(model)
    assert result["openings"][0]["frl"] == DEFAULT_ASSUMED_FRL == "-/120/120"
    assert "FRL not provided" in result["openings"][0]["notes"]
    assert "estimating only" in result["openings"][0]["notes"]
    assert result["openings"][1]["frl"] == "-/90/90"
    assert result["openings"][1]["notes"] == "source stated"
    assert "Verify the required FRL" in DEFAULT_ASSUMED_FRL_NOTE


def test_ai_best_estimate_policy_for_size_and_quantity_is_explicit() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_assumptionaware.py").read_text(
        encoding="utf-8"
    )
    for required in (
        "combined AI best estimate",
        "Missing exact service SIZE is NOT by itself a reason to stop",
        "Missing exact service QUANTITY is NOT by itself a reason to stop",
        "Never use photograph count as",
        "never default to quantity 1 merely because there is one defect row",
        "clearly labelled provisional estimate",
    ):
        assert required in source


def test_missing_frl_does_not_force_source_limitation() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_assumptionaware.py").read_text(
        encoding="utf-8"
    )
    assert "Missing FRL alone is never a reason to return INSUFFICIENT_EVIDENCE" in source
    assert 'DEFAULT_ASSUMED_FRL = "-/120/120"' in source


def test_real_uat_canonical_transport_uses_role_scoped_loopback_api() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_assumptionaware.py").read_text(
        encoding="utf-8"
    )
    assert "direct_classifire_api" in source
    assert '"X-Classifire-Agent-ID": agent_id' in source
    assert '"Authorization": f"Bearer {token}"' in source
    assert "/evidence/register" in source
    assert "/physical-model/initial" in source
    assert "/physical-model/lock" in source


def test_estimated_service_is_provisional_when_marked_as_estimated() -> None:
    controller = object.__new__(AssumptionAwareController)
    model = {
        "openings": [],
        "services": [
            {
                "service_code": "D-S-001",
                "quantity": 3,
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "notes": "AI-estimated quantity from reconciled photographs",
            }
        ],
    }
    result = controller._apply_estimation_defaults(model)
    assert result["services"][0]["evidence_status"] == "provisional"
    assert result["services"][0]["relationship_status"] == "provisional"
