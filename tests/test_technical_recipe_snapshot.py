from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest

from classifire.services.technical_recipe_snapshot import (
    TechnicalRecipeSnapshotError,
    technical_recipe_snapshot,
    validate_technical_recipe_snapshot,
)


def _variant(*, components=None, labour=None):
    return SimpleNamespace(component_requirements=components, labour_requirements=labour)


def test_recipe_snapshot_is_deterministic_bounded_and_individually_addressable() -> None:
    first = technical_recipe_snapshot(
        _variant(
            components={"sealant": {"unit": "cartridge"}, "backing/rod": "source-cited"},
            labour=["Install sealant"],
        )
    )
    second = technical_recipe_snapshot(
        _variant(
            components={"backing/rod": "source-cited", "sealant": {"unit": "cartridge"}},
            labour=["Install sealant"],
        )
    )
    assert first == second
    assert first["availability"] == "available"
    assert [item["kind"] for item in first["requirements"]] == [
        "component",
        "component",
        "activity",
    ]
    assert first["requirements"][0]["path"] == "/component_requirements/backing~1rod"
    assert validate_technical_recipe_snapshot(first) == first


def test_recipe_snapshot_detects_change_and_tampering() -> None:
    before = technical_recipe_snapshot(_variant(components={"sealant": "one"}, labour=[]))
    after = technical_recipe_snapshot(_variant(components={"sealant": "two"}, labour=[]))
    assert before["sha256"] != after["sha256"]
    tampered = copy.deepcopy(before)
    tampered["requirements"][0]["label"] = "changed"
    with pytest.raises(TechnicalRecipeSnapshotError):
        validate_technical_recipe_snapshot(tampered)


@pytest.mark.parametrize(
    ("components", "labour"),
    [
        ("bad", []),
        ({}, "bad"),
        ({}, [""]),
        ({1: "bad"}, []),
        (list(range(101)), []),
        ({}, ["Install"] * 101),
    ],
)
def test_recipe_snapshot_rejects_unbounded_or_ambiguous_shapes(components, labour) -> None:
    with pytest.raises(TechnicalRecipeSnapshotError):
        technical_recipe_snapshot(_variant(components=components, labour=labour))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_recipe_snapshot_rejects_nonfinite_numbers(value: float) -> None:
    with pytest.raises(TechnicalRecipeSnapshotError, match="canonical JSON"):
        technical_recipe_snapshot(_variant(components={"sealant": value}, labour=[]))
