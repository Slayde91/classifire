from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest

from classifire.models import Service
from classifire.services.rule_engine import _condition, edge_gap_mm


def _service(**values: object) -> Service:
    defaults: dict[str, object] = {
        "centre_x_mm": None,
        "centre_y_mm": None,
        "outside_diameter_mm": None,
        "nominal_size_mm": None,
        "width_mm": None,
        "height_mm": None,
    }
    defaults.update(values)
    return cast(Service, SimpleNamespace(**defaults))


def test_edge_gap_uses_service_radii_after_geometry_is_confirmed() -> None:
    first = _service(centre_x_mm="0", centre_y_mm="0", outside_diameter_mm="20")
    second = _service(centre_x_mm="50", centre_y_mm="0", outside_diameter_mm="10")

    assert edge_gap_mm(first, second) == Decimal("35.0")


def test_edge_gap_is_unresolved_when_a_service_has_no_confirmed_radius() -> None:
    first = _service(centre_x_mm="0", centre_y_mm="0", outside_diameter_mm="20")
    second = _service(centre_x_mm="50", centre_y_mm="0", width_mm="10")

    assert edge_gap_mm(first, second) is None


def test_rule_condition_returns_bool_for_scalar_and_numeric_comparisons() -> None:
    context = {"opening": {"service_count": 2, "classification": "confirmed"}}

    assert (
        _condition({"field": "opening.service_count", "operator": "gte", "value": 2}, context)
        is True
    )
    assert (
        _condition(
            {"field": "opening.classification", "operator": "eq", "value": "confirmed"}, context
        )
        is True
    )
    assert (
        _condition(
            {"field": "opening.classification", "operator": "neq", "value": "provisional"},
            context,
        )
        is True
    )


def test_rule_condition_rejects_a_non_text_operator() -> None:
    with pytest.raises(ValueError, match="Rule operator must be text"):
        _condition({"field": "opening.service_count", "operator": ["gte"], "value": 2}, {})
