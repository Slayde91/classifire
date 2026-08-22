from __future__ import annotations

from classifire.blind_visual_inventory import (
    BLIND_INVENTORY_BLOCKED,
    BLIND_INVENTORY_COMPLETE,
    blind_hard_topology_observation_catalog,
    blind_observation_catalog,
    validate_blind_reconciliation_payload,
    validate_blind_visual_inventory_payload,
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
            "candidate_id": f"V-O-{index + 1:03d}",
            "blank": (blank if index == 0 else False),
            "detail": "candidate opening",
            "evidence_refs": ["P001-I01"],
        }
        for index in range(opening_count)
    ]

    services = []

    for index in range(service_count):
        if openings:
            opening_id = openings[
                min(
                    index,
                    len(openings) - 1,
                )
            ]["candidate_id"]

            if opening_id == "V-O-001" and blank:
                nonblank = [item["candidate_id"] for item in openings if not item["blank"]]

                opening_links = [nonblank[0]] if nonblank else []
            else:
                opening_links = [opening_id]
        else:
            opening_links = []

        services.append(
            {
                "candidate_id": f"V-S-{index + 1:03d}",
                "service_type": "unknown",
                "material": None,
                "quantity": 1,
                "candidate_opening_ids": opening_links,
                "detail": "candidate service group",
                "evidence_refs": ["P001-I01"],
            }
        )

    return {
        "status": status,
        "observed_opening_count": opening_count,
        "observed_service_group_count": service_count,
        "candidate_openings": openings,
        "candidate_services": services,
        "unresolved_candidates": (unresolved if unresolved is not None else []),
        "limitations": [],
    }


def _proposal(
    *,
    opening_count: int = 1,
    service_count: int = 2,
    blank: bool = False,
) -> dict:
    openings = []

    for index in range(opening_count):
        openings.append(
            {
                "opening_code": f"D-O-{index + 1:03d}",
                "opening_type": (
                    "blank_core_hole" if (index == 0 and blank) else "service_penetration"
                ),
            }
        )

    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": openings,
        "services": [
            {
                "service_code": f"D-S-{index + 1:03d}",
            }
            for index in range(service_count)
        ],
    }


def test_complete_blind_inventory_is_valid() -> None:
    assert validate_blind_visual_inventory_payload(_inventory()) == []


def test_complete_inventory_rejects_unresolved_candidate() -> None:
    inventory = _inventory(
        unresolved=[
            {
                "kind": "service",
                "detail": "possible additional service",
                "evidence_refs": ["P001-I02"],
            }
        ]
    )

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any(("cannot contain unresolved candidates" in error) for error in errors)


def test_blocked_inventory_requires_reason() -> None:
    inventory = _inventory(
        status=BLIND_INVENTORY_BLOCKED,
    )

    inventory["limitations"] = []

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any(("must state an unresolved candidate or limitation" in error) for error in errors)


def test_unknown_opening_link_is_invalid() -> None:
    inventory = _inventory()

    inventory["candidate_services"][0]["candidate_opening_ids"] = ["V-O-NOT-REAL"]

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any(("references unknown opening" in error) for error in errors)


def _ledger_entry(
    blind_candidate_id: str,
    disposition: str,
    proposal_refs: list[str],
) -> dict:
    return {
        "blind_candidate_id": blind_candidate_id,
        "disposition": disposition,
        "proposal_refs": proposal_refs,
        "detail": "evidence-backed reconciliation",
        "evidence_refs": ["P001-I01"],
    }


def _validator_receipt(
    proposal: dict,
    ledger: list[dict],
) -> dict:
    return {
        "verdict": "APPROVED",
        "observed_opening_count": len(proposal.get("openings") or []),
        "observed_service_group_count": len(proposal.get("services") or []),
        "issues": [],
        "limitations": [],
        "blind_reconciliation": ledger,
    }


def test_v3_blocked_blind_inventory_can_be_reconciled_with_different_counts() -> None:
    inventory = _inventory(
        opening_count=2,
        service_count=3,
        status=BLIND_INVENTORY_BLOCKED,
        unresolved=[
            {
                "candidate_id": "V-U-001",
                "kind": "opening",
                "detail": "possible shadow or additional opening",
                "evidence_refs": ["P001-I02"],
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

    errors = validate_blind_reconciliation_payload(
        inventory,
        proposal,
        validator,
    )

    assert any(("V-S-002" in error and "no reconciliation" in error) for error in errors)


def test_v4_unresolved_hard_topology_disposition_blocks_approved_validator() -> None:
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

    errors = validate_blind_reconciliation_payload(
        inventory,
        proposal,
        validator,
    )

    assert any(("cannot leave hard topology observations UNRESOLVED" in error) for error in errors)


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

    errors = validate_blind_reconciliation_payload(
        inventory,
        proposal,
        validator,
    )

    assert any(("unknown proposal item" in error) for error in errors)


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

    bad_errors = validate_blind_reconciliation_payload(
        inventory,
        proposal,
        bad_validator,
    )

    assert any(("exactly one must be ACCOUNTED_FOR" in error) for error in bad_errors)

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
                "candidate_id": "V-U-001",
                "kind": "classification",
                "detail": "pipe versus conduit classification",
                "evidence_refs": ["P001-I02"],
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

    inventory["limitations"] = ["image crop prevents dimensional confirmation"]

    catalog = blind_observation_catalog(inventory)

    assert catalog["V-L-001"] == "limitation"


def test_v4_hard_topology_catalog_only_promotes_openings_and_linked_services():

    inventory = {
        "status": "BLOCKED",
        "observed_opening_count": 1,
        "observed_service_group_count": 2,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "visible opening candidate",
                "evidence_refs": ["P001"],
            },
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": None,
                "quantity": 1,
                "candidate_opening_ids": ["V-O-001"],
                "detail": "linked service candidate",
                "evidence_refs": ["P001"],
            },
            {
                "candidate_id": "V-S-002",
                "service_type": "unknown",
                "material": None,
                "quantity": 1,
                "candidate_opening_ids": [],
                "detail": "visible but unlinked service candidate",
                "evidence_refs": ["P001"],
            },
        ],
        "unresolved_candidates": [
            {
                "candidate_id": "V-U-001",
                "kind": "classification",
                "detail": "classification remains uncertain",
                "evidence_refs": ["P001"],
            },
        ],
        "limitations": [
            "image resolution is limited",
        ],
    }

    assert blind_hard_topology_observation_catalog(inventory) == {
        "V-O-001": "opening",
        "V-S-001": "service",
    }


def test_v4_approved_reconciliation_allows_unresolved_advisory_service():
    from classifire.blind_visual_inventory import (
        validate_blind_reconciliation_payload,
    )

    inventory = {
        "status": "BLOCKED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": True,
                "detail": "blank opening candidate",
                "evidence_refs": ["P001"],
            },
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "unknown",
                "material": None,
                "quantity": 1,
                "candidate_opening_ids": [],
                "detail": "visible but unlinked service candidate",
                "evidence_refs": ["P001"],
            },
        ],
        "unresolved_candidates": [
            {
                "candidate_id": "V-U-001",
                "kind": "classification",
                "detail": "classification remains uncertain",
                "evidence_refs": ["P001"],
            },
        ],
        "limitations": [],
    }

    proposal = {
        "status": "MODEL_SUPPORTED",
        "openings": [
            {
                "opening_code": "D-O-001",
            },
        ],
        "services": [],
    }

    validator = {
        "verdict": "APPROVED",
        "blind_reconciliation": [
            {
                "blind_candidate_id": "V-O-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["D-O-001"],
                "detail": "proposal represents the opening",
                "evidence_refs": ["P001"],
            },
            {
                "blind_candidate_id": "V-S-001",
                "disposition": "UNRESOLVED",
                "proposal_refs": [],
                "detail": ("visible object cannot be established as a penetrating Service"),
                "evidence_refs": ["P001"],
            },
            {
                "blind_candidate_id": "V-U-001",
                "disposition": "RESOLVED_NONSTRUCTURAL",
                "proposal_refs": [],
                "detail": "classification does not alter topology",
                "evidence_refs": ["P001"],
            },
        ],
    }

    assert (
        validate_blind_reconciliation_payload(
            inventory,
            proposal,
            validator,
        )
        == []
    )


def test_v4_approved_reconciliation_rejects_unresolved_linked_service():
    from classifire.blind_visual_inventory import (
        validate_blind_reconciliation_payload,
    )

    inventory = {
        "status": "BLOCKED",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "opening candidate",
                "evidence_refs": ["P001"],
            },
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": None,
                "quantity": 1,
                "candidate_opening_ids": ["V-O-001"],
                "detail": ("service candidate explicitly linked to opening candidate"),
                "evidence_refs": ["P001"],
            },
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }

    proposal = {
        "status": "MODEL_SUPPORTED",
        "openings": [
            {
                "opening_code": "D-O-001",
            },
        ],
        "services": [],
    }

    validator = {
        "verdict": "APPROVED",
        "blind_reconciliation": [
            {
                "blind_candidate_id": "V-O-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["D-O-001"],
                "detail": "proposal represents the opening",
                "evidence_refs": ["P001"],
            },
            {
                "blind_candidate_id": "V-S-001",
                "disposition": "UNRESOLVED",
                "proposal_refs": [],
                "detail": "linked Service remains unresolved",
                "evidence_refs": ["P001"],
            },
        ],
    }

    errors = validate_blind_reconciliation_payload(
        inventory,
        proposal,
        validator,
    )

    assert any(("hard topology" in error and "V-S-001" in error) for error in errors)


def test_complete_blank_opening_cannot_have_service_links() -> None:
    inventory = _inventory(opening_count=1, service_count=1, blank=True)
    inventory["candidate_services"][0]["candidate_opening_ids"] = ["V-O-001"]

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any("is blank but has Service links" in error for error in errors)


def test_complete_occupied_opening_requires_a_service_group() -> None:
    inventory = _inventory(opening_count=1, service_count=0)

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any("occupied opening V-O-001 has no Service group" in error for error in errors)


def test_candidate_id_cannot_be_reused_across_opening_and_service_kinds() -> None:
    inventory = _inventory(opening_count=1, service_count=1)
    inventory["candidate_services"][0]["candidate_id"] = "V-O-001"

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any("reused across candidate kinds: V-O-001" in error for error in errors)


def test_explicit_and_synthetic_unresolved_ids_must_be_globally_unique() -> None:
    inventory = _inventory(
        opening_count=0,
        service_count=0,
        status=BLIND_INVENTORY_BLOCKED,
        unresolved=[
            {
                "candidate_id": "V-U-002",
                "kind": "classification",
                "detail": "first uncertainty",
                "evidence_refs": ["P001"],
            },
            {
                "kind": "classification",
                "detail": "second uncertainty",
                "evidence_refs": ["P001"],
            },
        ],
    )

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any("duplicate blind observation id V-U-002" in error for error in errors)


def test_generated_limitation_id_cannot_collide_with_candidate_id() -> None:
    inventory = _inventory(
        opening_count=1,
        service_count=0,
        status=BLIND_INVENTORY_BLOCKED,
    )
    inventory["candidate_openings"][0]["candidate_id"] = "V-L-001"
    inventory["limitations"] = ["image resolution is limited"]

    errors = validate_blind_visual_inventory_payload(inventory)

    assert any("duplicate blind observation id V-L-001" in error for error in errors)


def test_reconciliation_rejects_non_object_inventory_without_raising() -> None:
    errors = validate_blind_reconciliation_payload([], {}, {})

    assert errors == ["blind inventory invalid: blind validator inventory must be an object"]


def test_reconciliation_rejects_non_object_proposal_and_validator_without_raising() -> None:
    inventory = _inventory(opening_count=0, service_count=0)

    errors = validate_blind_reconciliation_payload(inventory, [], [])

    assert "proposal must be an object" in errors
    assert "validator receipt must be an object" in errors
