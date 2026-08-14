from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_resilient import (  # noqa: E402
    GATEWAY_CALL_PROCESS_TIMEOUT_SECONDS,
    GATEWAY_CALL_TIMEOUT_MS,
    ROLE_SCOPE_CONTRACT,
    ROLE_TOOL_CONTRACT,
)


def test_resilient_runner_does_not_require_tools_effective_rpc() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_resilient.py").read_text(encoding="utf-8")
    assert "tools_effective_rpc_skipped" in source
    assert '"tools.effective"' not in source
    assert "runtime authority enforced on actual invocation" in source


def test_intake_role_contract_is_narrow() -> None:
    assert ROLE_TOOL_CONTRACT["cf-intake-evidence"] == {
        "classifire_register_evidence_observations"
    }
    assert "evidence:write" in ROLE_SCOPE_CONTRACT["cf-intake-evidence"]
    assert "physical:write" not in ROLE_SCOPE_CONTRACT["cf-intake-evidence"]


def test_physical_role_contract_has_visual_evidence_and_no_release_authority() -> None:
    assert ROLE_TOOL_CONTRACT["cf-physical-model"] == {
        "image",
        "classifire_evidence_read",
        "classifire_submit_initial_physical_model",
        "classifire_lock_physical_model",
    }
    scopes = ROLE_SCOPE_CONTRACT["cf-physical-model"]
    assert {"evidence:read", "physical:read", "physical:write", "physical:lock"} <= scopes
    assert "validation:run" not in scopes
    assert "human_release" not in scopes
    assert "estimate:approve" not in scopes

def test_validator_role_contract_is_read_only_for_visual_validation() -> None:
    assert ROLE_TOOL_CONTRACT["cf-validator"] == {
        "image",
        "classifire_evidence_read",
        "classifire_physical_model_read",
        "classifire_run_validation",
    }

    assert ROLE_SCOPE_CONTRACT["cf-validator"] == {
        "evidence:read",
        "physical:read",
        "validation:run",
    }

    assert not (
        ROLE_SCOPE_CONTRACT["cf-validator"]
        & {
            "evidence:write",
            "physical:write",
            "physical:lock",
            "technical:select",
            "technical:lock",
            "commercial:derive",
            "snapshot:lock",
        }
    )


def test_visual_gate_required_tools_fit_governed_role_contracts() -> None:
    from run_classifire_real_uat_fireseals_visualvalidated import (
        PHYSICAL_VISUAL_TOOLS,
        VALIDATOR_VISUAL_TOOLS,
    )

    assert PHYSICAL_VISUAL_TOOLS <= ROLE_TOOL_CONTRACT["cf-physical-model"]
    assert VALIDATOR_VISUAL_TOOLS <= ROLE_TOOL_CONTRACT["cf-validator"]


def test_gateway_calls_get_wider_bounded_timeout() -> None:
    assert GATEWAY_CALL_TIMEOUT_MS == 120_000
    assert GATEWAY_CALL_PROCESS_TIMEOUT_SECONDS == 140
