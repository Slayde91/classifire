from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


SCRIPTS_DIR = (
    Path(__file__).resolve().parents[1]
    / "scripts"
)

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS_DIR),
    )


from run_classifire_real_uat_fireseals_topologyaware import (  # noqa: E402
    TopologyAwareFireSealController,
)
from run_classifire_real_uat_fireseals_visualvalidated import (  # noqa: E402
    PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS,
    VisualValidatedTopologyController,
)
from run_classifire_real_uat_fireseals_visualvalidated_proposal_only import (  # noqa: E402
    PROPOSAL_RECEIPT,
    PROPOSAL_READY_STATUS,
    WITHHELD_WRITE_RECEIPT,
    ProposalOnlyComplete,
    ProposalOnlyVisualValidatedTopologyController,
    _assert_no_canonical_physical_state,
)


def _controller(
    tmp_path: Path,
) -> tuple[
    ProposalOnlyVisualValidatedTopologyController,
    dict[str, dict[str, Any]],
]:
    controller = object.__new__(
        ProposalOnlyVisualValidatedTopologyController
    )

    controller.receipt_dir = tmp_path
    controller.estimate_id = "estimate-test"
    controller.run_id = "run-test"

    saved: dict[str, dict[str, Any]] = {}

    def save_json(
        name: str,
        payload: dict[str, Any],
    ) -> None:
        saved[name] = payload

    controller.save_json = save_json  # type: ignore[method-assign]

    return controller, saved


@pytest.mark.parametrize(
    "tool_name",
    sorted(
        PHYSICAL_VISUAL_GUARDED_WRITE_TOOLS
    ),
)
def test_proposal_only_withholds_all_physical_writes(
    tmp_path: Path,
    tool_name: str,
) -> None:
    controller, saved = _controller(
        tmp_path
    )

    (
        tmp_path /
        PROPOSAL_RECEIPT
    ).write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(
        ProposalOnlyComplete
    ) as caught:
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            tool_name,
            {
                "estimate_id": "estimate-test",
            },
            "test-receipt.json",
        )

    assert caught.value.tool_name == tool_name

    receipt = saved[
        WITHHELD_WRITE_RECEIPT
    ]

    assert (
        receipt["status"]
        == PROPOSAL_READY_STATUS
    )

    assert (
        receipt["withheld_tool"]
        == tool_name
    )

    assert (
        receipt["canonical_write_performed"]
        is False
    )


def test_proposal_only_fails_closed_without_merged_proposal(
    tmp_path: Path,
) -> None:
    controller, _saved = _controller(
        tmp_path
    )

    with pytest.raises(
        RuntimeError,
        match="merged proposal receipt",
    ):
        controller.invoke_tool(
            "cf-physical-model",
            "agent:cf-physical-model:test",
            "classifire_submit_initial_physical_model",
            {
                "estimate_id": "estimate-test",
            },
            "test-receipt.json",
        )




@pytest.mark.parametrize(
    (
        "opening_count",
        "service_count",
        "physical_lock_count",
    ),
    [
        (1, 0, 0),
        (0, 1, 0),
        (0, 0, 1),
    ],
)
def test_proposal_only_rejects_canonical_physical_mutation(
    tmp_path: Path,
    opening_count: int,
    service_count: int,
    physical_lock_count: int,
) -> None:
    controller, _saved = _controller(
        tmp_path
    )

    state = {
        "opening_count": opening_count,
        "service_count": service_count,
        "physical_lock_count": physical_lock_count,
    }

    with pytest.raises(
        RuntimeError,
        match="canonical Physical state exists",
    ):
        _assert_no_canonical_physical_state(
            controller,
            state,
        )

def test_proposal_only_delegates_non_write_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller, saved = _controller(
        tmp_path
    )

    calls: list[
        tuple[
            tuple[Any, ...],
            dict[str, Any],
        ]
    ] = []

    def fake_invoke_tool(
        self: VisualValidatedTopologyController,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        calls.append(
            (
                args,
                kwargs,
            )
        )

        return {
            "ok": True,
        }

    monkeypatch.setattr(
        VisualValidatedTopologyController,
        "invoke_tool",
        fake_invoke_tool,
    )

    result = controller.invoke_tool(
        "cf-physical-model",
        "agent:cf-physical-model:test",
        "classifire_evidence_read",
        {
            "estimate_id": "estimate-test",
        },
        "test-receipt.json",
    )

    assert result == {
        "ok": True,
    }

    assert len(calls) == 1
    assert saved == {}


@pytest.mark.parametrize(
    (
        "runner_timeout",
        "explicit_timeout",
        "expected_timeout",
    ),
    [
        (1800, None, 1800.0),
        (1800, 900.0, 900.0),
    ],
)
def test_visual_openresponses_timeout_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
    runner_timeout: int,
    explicit_timeout: float | None,
    expected_timeout: float,
) -> None:
    def fake_parent_init(
        self: TopologyAwareFireSealController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        TopologyAwareFireSealController,
        "__init__",
        fake_parent_init,
    )

    kwargs: dict[str, Any] = {
        "timeout_seconds": runner_timeout,
    }

    if explicit_timeout is not None:
        kwargs[
            "openresponses_timeout_seconds"
        ] = explicit_timeout

    controller = VisualValidatedTopologyController(
        **kwargs,
    )

    assert (
        controller._openresponses_timeout_seconds
        == expected_timeout
    )


def test_visual_openresponses_timeout_rejects_nonpositive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_parent_init(
        self: TopologyAwareFireSealController,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        return None

    monkeypatch.setattr(
        TopologyAwareFireSealController,
        "__init__",
        fake_parent_init,
    )

    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        VisualValidatedTopologyController(
            timeout_seconds=0,
        )
