from __future__ import annotations

from copy import deepcopy

import pytest

from classifire.visual_validation import (
    validate_visual_correction_scope,
    validate_visual_validator_payload,
    visual_validator_approved,
)


def _proposal() -> dict:
    return {
        "openings": [
            {"opening_code": "O-A"},
            {"opening_code": "O-B"},
        ],
        "services": [
            {"service_code": "S-A"},
            {"service_code": "S-B"},
            {"service_code": "S-C"},
        ],
    }


def test_approved_visual_receipt_requires_matching_counts_and_no_issues() -> None:
    payload = {
        "verdict": "APPROVED",
        "observed_opening_count": 2,
        "observed_service_group_count": 3,
        "issues": [],
        "limitations": [],
    }
    assert validate_visual_validator_payload(payload, _proposal()) == []
    assert visual_validator_approved(payload, _proposal()) is True


def test_approved_visual_receipt_fails_closed_on_count_contradiction() -> None:
    payload = {
        "verdict": "APPROVED",
        "observed_opening_count": 1,
        "observed_service_group_count": 3,
        "issues": [],
        "limitations": [],
    }
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("count contradiction" in issue for issue in issues)
    assert visual_validator_approved(payload, _proposal()) is False


def test_rejected_visual_receipt_requires_structured_issue() -> None:
    payload = {
        "verdict": "REJECTED",
        "observed_opening_count": 3,
        "observed_service_group_count": 3,
        "issues": [
            {
                "code": "MISSED_OPENING",
                "detail": "A separate blank core hole is visible to the left of the service opening.",
                "evidence_refs": ["P001-I01"],
            }
        ],
        "limitations": [],
    }
    assert validate_visual_validator_payload(payload, _proposal()) == []
    assert visual_validator_approved(payload, _proposal()) is False


def test_unknown_issue_code_cannot_pass_the_gate() -> None:
    payload = {
        "verdict": "REJECTED",
        "issues": [{"code": "MODEL_FEELS_WRONG", "detail": "Unsupported free-form code."}],
    }
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("unsupported code" in issue for issue in issues)


def test_blocked_visual_receipt_must_explain_blocker() -> None:
    payload = {"verdict": "BLOCKED", "issues": [], "limitations": []}
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("must state an issue or limitation" in issue for issue in issues)


def _bounded_proposal() -> dict:
    return {
        "status": "MODEL_SUPPORTED",
        "openings": [
            {
                "opening_code": "O-A",
                "opening_type": "service_penetration",
                "substrate_type": "block wall",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "diameter_mm": 100,
            },
            {
                "opening_code": "O-B",
                "opening_type": "service_penetration",
                "substrate_type": "block wall",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "diameter_mm": 80,
            },
        ],
        "services": [
            {
                "service_code": "S-A",
                "primary_opening_code": "O-A",
                "opening_codes": ["O-A"],
                "service_type": "pipe",
                "material": "PEX",
                "outside_diameter_mm": 25,
                "quantity": 2,
            },
            {
                "service_code": "S-B",
                "primary_opening_code": "O-B",
                "opening_codes": ["O-B"],
                "service_type": "cable_bundle",
                "material": "copper",
                "width_mm": 50,
                "quantity": 1,
            },
        ],
    }


def _validator_issue(*codes: str) -> dict:
    return {
        "verdict": "REJECTED",
        "issues": [
            {
                "code": code,
                "detail": f"test issue {code}",
                "evidence_refs": ["photo-a.png"],
            }
            for code in codes
        ],
        "limitations": [],
    }


def test_v4b_link_only_correction_changes_links_without_changing_entities() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"][0]["primary_opening_code"] = "O-B"
    corrected["services"][0]["opening_codes"] = ["O-B"]

    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_OPENING_LINK"),
    ) == []


def test_v4b_link_only_correction_rejects_same_count_entity_replacement() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"][0]["service_code"] = "S-C"

    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_OPENING_LINK"),
    )

    assert any("added Services: S-C" in error for error in errors)
    assert any("removed Services: S-A" in error for error in errors)


@pytest.mark.parametrize(
    ("issue_code", "collection", "field", "value"),
    [
        ("WRONG_SERVICE_CLASS", "services", "service_type", "conduit"),
        ("UNSUPPORTED_MATERIAL", "services", "material", "PVC"),
        ("UNSUPPORTED_DIMENSION", "openings", "diameter_mm", 120),
    ],
)
def test_v4b_attribute_issue_changes_only_its_named_dimension(
    issue_code: str,
    collection: str,
    field: str,
    value: object,
) -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected[collection][0][field] = value

    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue(issue_code),
    ) == []

    corrected["services"].append(
        {
            "service_code": "S-C",
            "primary_opening_code": "O-A",
            "opening_codes": ["O-A"],
            "service_type": "pipe",
            "quantity": 1,
        }
    )
    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue(issue_code),
    )
    assert any("do not authorize added Services" in error for error in errors)


def test_v4b_invented_service_allows_decrease_but_never_increase() -> None:
    previous = _bounded_proposal()
    decreased = deepcopy(previous)
    decreased["services"].pop()
    assert validate_visual_correction_scope(
        previous,
        decreased,
        _validator_issue("INVENTED_SERVICE"),
    ) == []

    increased = deepcopy(previous)
    increased["services"].append(
        {
            "service_code": "S-C",
            "primary_opening_code": "O-A",
            "opening_codes": ["O-A"],
            "service_type": "pipe",
            "quantity": 1,
        }
    )
    errors = validate_visual_correction_scope(
        previous,
        increased,
        _validator_issue("INVENTED_SERVICE"),
    )
    assert any("do not authorize added Services" in error for error in errors)


def test_v4b_missed_service_allows_increase_without_opening_change() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"].append(
        {
            "service_code": "S-C",
            "primary_opening_code": "O-A",
            "opening_codes": ["O-A"],
            "service_type": "pipe",
            "quantity": 1,
        }
    )
    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("MISSED_SERVICE"),
    ) == []

    corrected["openings"].append(
        {
            "opening_code": "O-C",
            "opening_type": "service_penetration",
        }
    )
    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("MISSED_SERVICE"),
    )
    assert any("do not authorize added Openings" in error for error in errors)


@pytest.mark.parametrize(
    ("issue_code", "operation"),
    [
        ("MISSED_OPENING", "add"),
        ("OVER_MERGED_OPENING", "add"),
        ("DUPLICATED_OPENING", "remove"),
        ("OVER_SPLIT_OPENING", "remove"),
    ],
)
def test_v4b_opening_issue_allows_only_corresponding_direction(
    issue_code: str,
    operation: str,
) -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    if operation == "add":
        corrected["openings"].append(
            {
                "opening_code": "O-C",
                "opening_type": "blank_core_hole",
            }
        )
    else:
        corrected["openings"].pop()
        corrected["services"][1]["primary_opening_code"] = "O-A"
        corrected["services"][1]["opening_codes"] = ["O-A"]

    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue(issue_code),
    ) == []


def test_v4b_grouping_changes_service_groups_but_not_openings() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"].pop()
    corrected["services"][0]["quantity"] = 3
    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_GROUPING"),
    ) == []

    corrected["openings"].pop()
    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_GROUPING"),
    )
    assert any("do not authorize removed Openings" in error for error in errors)


def test_v4b_quantity_issue_changes_quantity_not_group_count() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"][0]["quantity"] = 3
    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_QUANTITY"),
    ) == []

    corrected["services"].pop()
    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("WRONG_SERVICE_QUANTITY"),
    )
    assert any("do not authorize removed Services" in error for error in errors)


def test_v4b_combines_only_permissions_from_multiple_structured_issues() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"].append(
        {
            "service_code": "S-C",
            "primary_opening_code": "O-A",
            "opening_codes": ["O-A"],
            "service_type": "pipe",
            "quantity": 1,
        }
    )
    corrected["services"][0]["material"] = "PVC"

    assert validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("MISSED_SERVICE", "UNSUPPORTED_MATERIAL"),
    ) == []


def test_v4b_no_structured_issue_cannot_replace_proposal() -> None:
    proposal = _bounded_proposal()
    errors = validate_visual_correction_scope(
        proposal,
        deepcopy(proposal),
        {"verdict": "BLOCKED", "issues": [], "limitations": ["unclear"]},
    )
    assert any("requires at least one" in error for error in errors)


def test_v4b_ambiguous_size_or_quantity_issue_cannot_authorize_correction() -> None:
    previous = _bounded_proposal()
    corrected = deepcopy(previous)
    corrected["services"][0]["outside_diameter_mm"] = 32
    corrected["services"][0]["quantity"] = 3

    errors = validate_visual_correction_scope(
        previous,
        corrected,
        _validator_issue("UNSUPPORTED_SIZE_OR_QUANTITY"),
    )

    assert any(
        "is ambiguous" in error
        and "UNSUPPORTED_DIMENSION" in error
        and "WRONG_SERVICE_QUANTITY" in error
        for error in errors
    )
