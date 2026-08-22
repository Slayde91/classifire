from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


from run_classifire_real_uat_assumptionaware import (  # noqa: E402
    AssumptionAwareController,
)
from run_classifire_real_uat_intake import (  # noqa: E402
    ADMISSION_BOUND_CANONICAL_WRITE_STATUS,
    LEGACY_PHYSICAL_MUTATION_RETIREMENT_SCHEMA,
    RETIRED_CF_PHYSICAL_MODEL_MUTATION_TOOLS,
    Controller,
    LegacyPhysicalMutationRetired,
)


def _controller() -> tuple[Controller, dict[str, dict[str, Any]], list[dict[str, Any]]]:
    controller = object.__new__(Controller)
    controller.run_id = "run-test"
    controller.estimate_id = "estimate-test"
    saved: dict[str, dict[str, Any]] = {}
    gateway_calls: list[dict[str, Any]] = []

    def save_json(name: str, payload: dict[str, Any]) -> None:
        saved[name] = payload

    def gateway_call(
        method: str,
        params: dict[str, Any],
        receipt_name: str,
    ) -> dict[str, Any]:
        gateway_calls.append(
            {
                "method": method,
                "params": params,
                "receipt_name": receipt_name,
            }
        )
        return {"ok": True}

    controller.save_json = save_json  # type: ignore[method-assign]
    controller.gateway_call = gateway_call  # type: ignore[method-assign]
    return controller, saved, gateway_calls


@pytest.mark.parametrize("tool_name", sorted(RETIRED_CF_PHYSICAL_MODEL_MUTATION_TOOLS))
def test_base_runner_blocks_retired_mutation_before_gateway_call(
    tool_name: str,
) -> None:
    controller, saved, gateway_calls = _controller()

    with pytest.raises(LegacyPhysicalMutationRetired, match="admission-bound controlled writer"):
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            tool_name,
            {"estimate_id": "estimate-test"},
            "retired-tool.json",
        )

    assert gateway_calls == []
    receipt = saved["retired-tool.json"]
    assert receipt["schema"] == LEGACY_PHYSICAL_MUTATION_RETIREMENT_SCHEMA
    assert receipt["status"] == ADMISSION_BOUND_CANONICAL_WRITE_STATUS
    assert receipt["attempted_tool"] == tool_name
    assert receipt["canonical_write_performed"] is False
    assert receipt["physical_model_lock_created"] is False


def test_assumption_aware_direct_api_runner_inherits_the_same_retirement_guard() -> None:
    controller = object.__new__(AssumptionAwareController)
    controller.run_id = "run-test"
    controller.estimate_id = "estimate-test"
    saved: dict[str, dict[str, Any]] = {}
    controller.save_json = lambda name, payload: saved.setdefault(name, payload)  # type: ignore[method-assign]
    controller._direct_api_request = lambda *args, **kwargs: pytest.fail(  # type: ignore[method-assign]
        "A retired physical mutation must not reach the direct API path"
    )

    with pytest.raises(LegacyPhysicalMutationRetired):
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            "classifire_submit_initial_physical_model",
            {"estimate_id": "estimate-test"},
            "assumption-aware-retired-tool.json",
        )

    assert saved["assumption-aware-retired-tool.json"]["boundary"] == "tools.invoke"


def test_withheld_legacy_proposal_receipt_never_claims_a_canonical_write() -> None:
    controller, saved, _gateway_calls = _controller()
    controller.inspect_state = lambda: {  # type: ignore[method-assign]
        "opening_count": 0,
        "service_count": 0,
        "physical_lock_count": 0,
    }

    state = controller.withhold_legacy_physical_mutation(
        source_stage="unit-test",
        proposal_receipt="20-unit-test-proposal.json",
        proposed_opening_count=2,
        proposed_service_count=3,
        receipt_name="20-unit-test-admission-required.json",
    )

    receipt = saved["20-unit-test-admission-required.json"]
    assert state["canonical_write_withheld"] is True
    assert state["status"] == ADMISSION_BOUND_CANONICAL_WRITE_STATUS
    assert receipt["proposal_receipt"] == "20-unit-test-proposal.json"
    assert receipt["proposed_opening_count"] == 2
    assert receipt["proposed_service_count"] == 3
    assert receipt["canonical_write_performed"] is False
    assert receipt["physical_model_lock_created"] is False
