from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace

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


from classifire.blind_visual_inventory import (  # noqa: E402
    BLIND_INVENTORY_BLOCKED,
    BLIND_INVENTORY_COMPLETE,
    blind_inventory_approval_errors,
    validate_blind_visual_inventory_payload,
)
from run_classifire_real_uat_fireseals_visualvalidated import (  # noqa: E402
    VISUAL_GATE_POLICY_VERSION,
    VisualValidatedTopologyController,
)


def _inventory(
    *,
    opening_count: int = 1,
    service_count: int = 2,
    status: str = BLIND_INVENTORY_COMPLETE,
    unresolved: list[dict] | None = None,
    blank: bool = False,
) -> dict:
    openings = [
        {
            "candidate_id":
                f"V-O-{index + 1:03d}",
            "blank":
                (
                    blank
                    if index == 0
                    else False
                ),
            "detail":
                "candidate opening",
            "evidence_refs":
                ["P001-I01"],
        }
        for index in range(
            opening_count
        )
    ]

    services = []

    for index in range(
        service_count
    ):
        if openings:
            opening_id = (
                openings[
                    min(
                        index,
                        len(openings) - 1,
                    )
                ][
                    "candidate_id"
                ]
            )

            if (
                opening_id
                == "V-O-001"
                and blank
            ):
                nonblank = [
                    item[
                        "candidate_id"
                    ]
                    for item in openings
                    if not item[
                        "blank"
                    ]
                ]

                opening_links = (
                    [nonblank[0]]
                    if nonblank
                    else []
                )
            else:
                opening_links = [
                    opening_id
                ]
        else:
            opening_links = []

        services.append(
            {
                "candidate_id":
                    f"V-S-{index + 1:03d}",
                "service_type":
                    "unknown",
                "material":
                    None,
                "quantity":
                    1,
                "candidate_opening_ids":
                    opening_links,
                "detail":
                    "candidate service group",
                "evidence_refs":
                    ["P001-I01"],
            }
        )

    return {
        "status":
            status,
        "observed_opening_count":
            opening_count,
        "observed_service_group_count":
            service_count,
        "candidate_openings":
            openings,
        "candidate_services":
            services,
        "unresolved_candidates":
            (
                unresolved
                if unresolved
                is not None
                else []
            ),
        "limitations":
            [],
    }


def _proposal(
    *,
    opening_count: int = 1,
    service_count: int = 2,
    blank: bool = False,
) -> dict:
    openings = []

    for index in range(
        opening_count
    ):
        openings.append(
            {
                "opening_code":
                    f"D-O-{index + 1:03d}",
                "opening_type":
                    (
                        "blank_core_hole"
                        if (
                            index == 0
                            and blank
                        )
                        else "service_penetration"
                    ),
            }
        )

    return {
        "status":
            "MODEL_SUPPORTED",
        "limitations":
            [],
        "openings":
            openings,
        "services": [
            {
                "service_code":
                    f"D-S-{index + 1:03d}",
            }
            for index in range(
                service_count
            )
        ],
    }


def test_complete_blind_inventory_is_valid() -> None:
    assert (
        validate_blind_visual_inventory_payload(
            _inventory()
        )
        == []
    )


def test_complete_inventory_rejects_unresolved_candidate() -> None:
    inventory = _inventory(
        unresolved=[
            {
                "kind":
                    "service",
                "detail":
                    "possible additional service",
                "evidence_refs":
                    ["P001-I02"],
            }
        ]
    )

    errors = (
        validate_blind_visual_inventory_payload(
            inventory
        )
    )

    assert any(
        (
            "cannot contain unresolved candidates"
            in error
        )
        for error in errors
    )


def test_blocked_inventory_requires_reason() -> None:
    inventory = _inventory(
        status=BLIND_INVENTORY_BLOCKED,
    )

    inventory[
        "limitations"
    ] = []

    errors = (
        validate_blind_visual_inventory_payload(
            inventory
        )
    )

    assert any(
        (
            "must state an unresolved candidate or limitation"
            in error
        )
        for error in errors
    )


def test_unknown_opening_link_is_invalid() -> None:
    inventory = _inventory()

    inventory[
        "candidate_services"
    ][0][
        "candidate_opening_ids"
    ] = [
        "V-O-NOT-REAL"
    ]

    errors = (
        validate_blind_visual_inventory_payload(
            inventory
        )
    )

    assert any(
        (
            "references unknown opening"
            in error
        )
        for error in errors
    )


def test_blind_service_count_mismatch_blocks_approval() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=3,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=2,
    )

    errors = (
        blind_inventory_approval_errors(
            inventory,
            proposal,
        )
    )

    assert any(
        (
            "Service-group count contradiction"
            in error
        )
        for error in errors
    )


def test_blind_opening_count_mismatch_blocks_approval() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=2,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=2,
    )

    errors = (
        blind_inventory_approval_errors(
            inventory,
            proposal,
        )
    )

    assert any(
        (
            "Opening count contradiction"
            in error
        )
        for error in errors
    )


def test_blind_blank_opening_mismatch_blocks_approval() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=1,
        blank=True,
    )

    proposal = _proposal(
        opening_count=2,
        service_count=1,
        blank=False,
    )

    errors = (
        blind_inventory_approval_errors(
            inventory,
            proposal,
        )
    )

    assert any(
        (
            "blank-Opening count contradiction"
            in error
        )
        for error in errors
    )


def test_matching_complete_blind_inventory_allows_comparison() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=3,
    )

    proposal = _proposal(
        opening_count=2,
        service_count=3,
    )

    assert (
        blind_inventory_approval_errors(
            inventory,
            proposal,
        )
        == []
    )


def test_blocked_blind_inventory_cannot_be_approved() -> None:
    inventory = _inventory(
        status=BLIND_INVENTORY_BLOCKED,
        unresolved=[
            {
                "kind":
                    "service",
                "detail":
                    "possible additional service",
                "evidence_refs":
                    ["P001-I02"],
            }
        ],
    )

    proposal = _proposal()

    errors = (
        blind_inventory_approval_errors(
            inventory,
            proposal,
        )
    )

    assert any(
        (
            "requires a COMPLETE blind inventory"
            in error
        )
        for error in errors
    )


def test_blind_prompt_has_no_physical_proposal_or_human_fixture() -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )

    defect = SimpleNamespace(
        external_defect_id=
            "test-defect",
        defect_code=
            "test-defect",
        id=
            "test-id",
    )

    prompt = (
        controller
        ._blind_validator_inventory_prompt(
            defect,
            "DIRECT-EVIDENCE",
        )
    )

    assert (
        "DIRECT-EVIDENCE"
        in prompt
    )

    assert (
        "Draft physical topology"
        not in prompt
    )

    assert (
        "17 Openings"
        not in prompt
    )

    assert (
        "22 Service"
        not in prompt
    )


def test_blind_inventory_runs_before_physical_draft() -> None:
    source = inspect.getsource(
        VisualValidatedTopologyController
        ._synthesise_defect
    )

    blind_index = source.index(
        "self._blind_validator_inventory("
    )

    physical_index = source.index(
        "proposal = ("
    )

    assert (
        blind_index
        < physical_index
    )

    assert (
        "blind_inventory_approval_errors("
        in source
    )


def test_blind_inventory_is_part_of_visual_cache_key() -> None:
    controller = object.__new__(
        VisualValidatedTopologyController
    )

    controller._visual_cache_key = (
        lambda _bundle, _files: {
            "base": True,
        }
    )

    inventory = _inventory()

    controller._current_blind_inventory = (
        inventory
    )

    key = (
        controller._visual_gate_cache_key(
            "bundle",
            [],
        )
    )

    assert (
        key["blind_inventory"]
        == inventory
    )

    assert (
        key[
            "visual_gate_policy_version"
        ]
        == VISUAL_GATE_POLICY_VERSION
    )


def test_visual_policy_version_invalidates_v1_cache() -> None:
    assert (
        VISUAL_GATE_POLICY_VERSION
        == "CLASSIFIRE-FIRESEAL-VISUAL-GATE-v2"
    )
