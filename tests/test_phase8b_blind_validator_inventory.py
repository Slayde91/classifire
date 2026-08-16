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
    blind_observation_catalog,
    validate_blind_reconciliation_payload,
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
        "validate_blind_reconciliation_payload("
        in source
    )

    assert (
        "blind_inventory_approval_errors("
        not in source
    )

    assert (
        "blind_inventory_block_reasons("
        not in source
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


def test_visual_policy_version_invalidates_v2_cache() -> None:
    assert (
        VISUAL_GATE_POLICY_VERSION
        == "CLASSIFIRE-FIRESEAL-VISUAL-GATE-v3"
    )


def _visual_session_probe():
    controller = object.__new__(
        VisualValidatedTopologyController
    )

    controller._visual_physical_session = None
    controller._visual_validator_session = None
    controller.estimate_id = "estimate-test"

    calls = []

    def initialize_session(
        agent_id,
        stage,
    ):
        calls.append(
            (
                agent_id,
                stage,
            )
        )

        return (
            f"agent:{agent_id}:{stage}"
        )

    controller.initialize_session = (
        initialize_session
    )

    controller.require_tools = (
        lambda *_args, **_kwargs: None
    )

    controller._assert_physical_visual_readonly = (
        lambda *_args, **_kwargs: None
    )

    controller.invoke_tool = (
        lambda *_args, **_kwargs: {}
    )

    return controller, calls


def test_visual_sessions_are_fresh_per_controller_execution() -> None:
    first, first_calls = (
        _visual_session_probe()
    )

    first_keys = (
        first._ensure_visual_sessions()
    )

    repeated_keys = (
        first._ensure_visual_sessions()
    )

    assert repeated_keys == first_keys
    assert len(first_calls) == 2

    first_physical_stage = (
        first_calls[0][1]
    )

    first_validator_stage = (
        first_calls[1][1]
    )

    physical_prefix = (
        "21-visual-physical-"
    )

    validator_prefix = (
        "21-visual-validator-"
    )

    assert first_physical_stage.startswith(
        physical_prefix
    )

    assert first_validator_stage.startswith(
        validator_prefix
    )

    first_physical_nonce = (
        first_physical_stage[
            len(physical_prefix):
        ]
    )

    first_validator_nonce = (
        first_validator_stage[
            len(validator_prefix):
        ]
    )

    assert first_physical_nonce
    assert (
        first_physical_nonce
        == first_validator_nonce
    )

    second, second_calls = (
        _visual_session_probe()
    )

    second_keys = (
        second._ensure_visual_sessions()
    )

    assert len(second_calls) == 2

    second_nonce = (
        second_calls[0][1][
            len(physical_prefix):
        ]
    )

    assert second_nonce
    assert (
        second_nonce
        != first_physical_nonce
    )

    assert (
        second_keys
        != first_keys
    )

def _ledger_entry(
    blind_candidate_id: str,
    disposition: str,
    proposal_refs: list[str],
) -> dict:
    return {
        "blind_candidate_id":
            blind_candidate_id,
        "disposition":
            disposition,
        "proposal_refs":
            proposal_refs,
        "detail":
            "evidence-backed reconciliation",
        "evidence_refs":
            ["P001-I01"],
    }


def _validator_receipt(
    proposal: dict,
    ledger: list[dict],
) -> dict:
    return {
        "verdict":
            "APPROVED",
        "observed_opening_count":
            len(
                proposal.get(
                    "openings"
                )
                or []
            ),
        "observed_service_group_count":
            len(
                proposal.get(
                    "services"
                )
                or []
            ),
        "issues":
            [],
        "limitations":
            [],
        "blind_reconciliation":
            ledger,
    }


def test_v3_blocked_blind_inventory_can_be_reconciled_with_different_counts() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=3,
        status=BLIND_INVENTORY_BLOCKED,
        unresolved=[
            {
                "candidate_id":
                    "V-U-001",
                "kind":
                    "opening",
                "detail":
                    "possible shadow or additional opening",
                "evidence_refs":
                    ["P001-I02"],
            }
        ],
    )

    proposal = _proposal(
        opening_count=1,
        service_count=2,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-O-002",
                "DUPLICATE_OR_SAME_ITEM",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
            _ledger_entry(
                "V-S-002",
                "ACCOUNTED_FOR",
                ["D-S-002"],
            ),
            _ledger_entry(
                "V-S-003",
                "DUPLICATE_OR_SAME_ITEM",
                ["D-S-002"],
            ),
            _ledger_entry(
                "V-U-001",
                "NOT_TOPOLOGY",
                [],
            ),
        ],
    )

    assert (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
        == []
    )


def test_v3_blind_undercount_does_not_force_physical_to_undercount() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=1,
    )

    proposal = _proposal(
        opening_count=2,
        service_count=3,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
        ],
    )

    assert (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
        == []
    )


def test_v3_missing_blind_disposition_blocks_approval() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=2,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=2,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
        ],
    )

    errors = (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
    )

    assert any(
        (
            "V-S-002"
            in error
            and "no reconciliation"
            in error
        )
        for error in errors
    )


def test_v3_unresolved_disposition_blocks_approved_validator() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=1,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=1,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "UNRESOLVED",
                [],
            ),
        ],
    )

    errors = (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
    )

    assert any(
        (
            "cannot leave blind observations UNRESOLVED"
            in error
        )
        for error in errors
    )


def test_v3_unknown_proposal_reference_blocks_approval() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=1,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=1,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-NOT-REAL"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
        ],
    )

    errors = (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
    )

    assert any(
        (
            "unknown proposal item"
            in error
        )
        for error in errors
    )


def test_v3_duplicate_collapse_requires_explicit_duplicate_disposition() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=2,
    )

    proposal = _proposal(
        opening_count=1,
        service_count=2,
    )

    bad_validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-O-002",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
            _ledger_entry(
                "V-S-002",
                "ACCOUNTED_FOR",
                ["D-S-002"],
            ),
        ],
    )

    bad_errors = (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            bad_validator,
        )
    )

    assert any(
        (
            "exactly one must be ACCOUNTED_FOR"
            in error
        )
        for error in bad_errors
    )

    good_validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-O-002",
                "DUPLICATE_OR_SAME_ITEM",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
            _ledger_entry(
                "V-S-002",
                "ACCOUNTED_FOR",
                ["D-S-002"],
            ),
        ],
    )

    assert (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            good_validator,
        )
        == []
    )


def test_v3_nonstructural_classification_uncertainty_can_be_resolved() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=1,
        status=BLIND_INVENTORY_BLOCKED,
        unresolved=[
            {
                "candidate_id":
                    "V-U-001",
                "kind":
                    "classification",
                "detail":
                    "pipe versus conduit classification",
                "evidence_refs":
                    ["P001-I02"],
            }
        ],
    )

    proposal = _proposal(
        opening_count=1,
        service_count=1,
    )

    validator = _validator_receipt(
        proposal,
        [
            _ledger_entry(
                "V-O-001",
                "ACCOUNTED_FOR",
                ["D-O-001"],
            ),
            _ledger_entry(
                "V-S-001",
                "ACCOUNTED_FOR",
                ["D-S-001"],
            ),
            _ledger_entry(
                "V-U-001",
                "RESOLVED_NONSTRUCTURAL",
                [],
            ),
        ],
    )

    assert (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
        == []
    )


def test_v3_observation_catalog_includes_limitations() -> None:
    inventory = _inventory()

    inventory[
        "limitations"
    ] = [
        "image crop prevents dimensional confirmation"
    ]

    catalog = (
        blind_observation_catalog(
            inventory
        )
    )

    assert (
        catalog["V-L-001"]
        == "limitation"
    )


def test_v3_blocked_inventory_no_longer_short_circuits_physical() -> None:
    source = inspect.getsource(
        VisualValidatedTopologyController
        ._synthesise_defect
    )

    assert (
        "BLIND_INVENTORY_BLOCKED"
        not in source
    )

    assert (
        "blind_inventory_block_reasons"
        not in source
    )

    assert (
        "Policy v3"
        in source
    )
