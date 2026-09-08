from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest

from classifire.services.draft_pricing_recipe_contract import (
    recipe_link_definition,
    recipe_link_envelope,
    validate_recipe_link_envelope,
)
from classifire.services.draft_system_match_contract import digest


def _observation(
    kind: str = "material",
    unit: str = "each",
    evidence_state: str = "confirmed",
) -> dict[str, object]:
    return {
        "id": "observation-1",
        "sha256": "a" * 64,
        "dataset_id": "dataset-1",
        "dataset_version": 1,
        "source_sha256": "b" * 64,
        "profile_sha256": "c" * 64,
        "decision_sha256": "d" * 64,
        "row_sha256": "e" * 64,
        "item_kind": kind,
        "normalized_reference": "SEALANT-01",
        "evidence_state": evidence_state,
        "unit": unit,
    }


def _definition(**changes):
    values = {
        "draft_scope_id": "draft-1",
        "technical_release": {"id": "release-1", "version": "v4", "sha256": "1" * 64},
        "technical_target": {
            "id": "variant-1",
            "snapshot_sha256": "2" * 64,
            "recipe_snapshot_sha256": "3" * 64,
        },
        "requirement": {
            "id": "4" * 64,
            "kind": "component",
            "path": "/component_requirements/sealant",
            "label": "sealant",
            "source_value": {"unit": "cartridge"},
            "source_value_sha256": digest({"unit": "cartridge"}),
        },
        "observations": [_observation()],
        "status": "linked",
        "unit": "each",
        "quantity_basis": "One cartridge per opening",
        "yield_basis": "Source stated",
        "productivity_basis": None,
        "recovery_boundary": "Material only",
        "evidence_state": "confirmed",
        "review_reason": "Reviewed source row",
        "unresolved_fields": [],
    }
    values.update(changes)
    return recipe_link_definition(**values)


def test_complete_component_link_round_trips_with_zero_authority() -> None:
    definition = _definition()
    envelope = recipe_link_envelope(
        definition,
        link_id="link-1",
        reviewed_by_id="reviewer-1",
        reviewed_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    validate_recipe_link_envelope(envelope)
    assert not any(envelope["definition"]["effects"].values())


def test_unresolved_outcome_requires_reasoned_missing_fields_and_no_observations() -> None:
    value = _definition(
        observations=[],
        status="unresolved",
        unit=None,
        quantity_basis=None,
        yield_basis=None,
        recovery_boundary=None,
        evidence_state="unresolved",
        unresolved_fields=["observation", "unit"],
    )
    assert value["interpretation"]["status"] == "unresolved"


@pytest.mark.parametrize(
    "changes",
    [
        {"observations": [], "status": "linked"},
        {"unit": "m"},
        {"yield_basis": None, "unresolved_fields": []},
        {"evidence_state": "confirmed", "unresolved_fields": ["yield_basis"]},
        {"observations": [_observation(kind="labour")]},
        {"observations": [_observation(evidence_state="provisional")]},
    ],
)
def test_component_link_fails_closed_for_incomplete_or_incompatible_input(changes) -> None:
    with pytest.raises(ValueError):
        _definition(**changes)


def test_envelope_detects_tampering() -> None:
    envelope = recipe_link_envelope(
        _definition(),
        link_id="link-1",
        reviewed_by_id="reviewer-1",
        reviewed_at=datetime(2026, 9, 8, tzinfo=UTC),
    )
    tampered = copy.deepcopy(envelope)
    tampered["definition"]["interpretation"]["review_reason"] = "Changed"
    with pytest.raises(ValueError):
        validate_recipe_link_envelope(tampered)


def test_effect_tampering_is_rejected_without_mutating_the_contract() -> None:
    tampered = _definition()
    tampered["effects"]["price_calculated"] = True
    with pytest.raises(ValueError):
        validate_recipe_link_envelope(
            recipe_link_envelope(
                tampered,
                link_id="link-1",
                reviewed_by_id="reviewer-1",
                reviewed_at=datetime(2026, 9, 8, tzinfo=UTC),
            )
        )
    assert not any(_definition()["effects"].values())


def test_envelope_rejects_naive_review_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone"):
        recipe_link_envelope(
            _definition(),
            link_id="link-1",
            reviewed_by_id="reviewer-1",
            reviewed_at=datetime(2026, 9, 8),
        )
