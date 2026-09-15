"""Arithmetic regression tests; governed access remains covered by integration tests."""

from decimal import localcontext
from types import SimpleNamespace

import pytest

from classifire.services import draft_pricing_bottom_up as bottom_up
from classifire.services.draft_estimate_contract import decimal_string, line_amount
from classifire.services.draft_system_match_contract import digest


def _exact_cents(quantity, rate):
    # Independent integer oracle: six decimal places per accepted input, half up.
    def millionths(value):
        whole, _, fraction = value.partition(".")
        return int(whole) * 1_000_000 + int(fraction.ljust(6, "0"))

    product = millionths(quantity) * millionths(rate)
    cents = (product + 5_000_000_000) // 10_000_000_000
    return f"{cents // 100}.{cents % 100:02d}"


def _context(monkeypatch, quantity, rate):
    requirements = [{"id": "material"}, {"id": "activity"}]
    links, bases, rows = [], {}, {}
    for requirement, qty, unit_rate in zip(
        requirements, (quantity, "1"), (rate, "0.01"), strict=True
    ):
        key = requirement["id"]
        observation = {"id": key, "sha256": "a" * 64}
        links.append(
            {
                "id": key,
                "current": True,
                "value": {
                    "definition": {
                        "requirement": requirement,
                        "interpretation": {
                            "status": "linked",
                            "evidence_state": "confirmed",
                            "unresolved_fields": [],
                            "unit": "m",
                        },
                        "observations": [observation],
                    }
                },
            }
        )
        bases[key] = {
            "id": key,
            "sha256": "b" * 64,
            "value": {
                "definition_sha256": "c" * 64,
                "definition": {
                    "scope": {"revision": 1},
                    "recipe_link": {"id": key},
                    "quantity_basis": {"quantity": qty, "unit": "m"},
                },
            },
        }
        rows[key] = SimpleNamespace(
            observation_sha256="a" * 64,
            value={
                "definition": {
                    "profile": {"price_meaning": "sell_price"},
                    "row": {
                        "values": {
                            "rate": unit_rate,
                            "unit": "m",
                            "currency": "AUD",
                            "tax_basis": "excluded",
                        }
                    },
                }
            },
        )
    monkeypatch.setattr(
        bottom_up,
        "preview_coverage",
        lambda *args, **kwargs: {
            "targets": [{"technical_target": {"id": "target"}, "status": "bottom_up_a_support"}],
            "technical_release": {"id": "release"},
            "coverage_sha256": "d" * 64,
        },
    )
    monkeypatch.setattr(
        bottom_up,
        "recipe_review_context",
        lambda *args, **kwargs: {
            "requirements": requirements,
            "links": links,
        },
    )
    monkeypatch.setattr(bottom_up, "current_quantity_bases", lambda *args, **kwargs: bases)
    monkeypatch.setattr(bottom_up, "_row_observation_value", lambda row: row.value)
    return SimpleNamespace(get=lambda model, key: rows[key])


@pytest.mark.parametrize(
    "quantity,rate",
    [
        ("2", "300"),
        ("999999999.999999", "999995000.000001"),
        ("0.005", "1"),
        ("12345.678901", "98765.432109"),
    ],
)
@pytest.mark.parametrize("precision", [12, 28, 60])
@pytest.mark.parametrize("source", ["governed", "manual_preview"])
def test_preview_preserves_exact_inputs_and_rounds_once(
    monkeypatch, quantity, rate, precision, source
):
    assert decimal_string(quantity, unit="m") == quantity
    assert decimal_string(rate) == rate
    db = _context(monkeypatch, quantity, rate)
    with localcontext() as context:
        context.prec = precision
        result = bottom_up.preview_bottom_up(
            db,
            None,
            "draft",
            "release",
            "target",
            {"material": quantity, "activity": "1"} if source == "manual_preview" else None,
            settings=None,
            quantity_source=source,
        )
        assert context.prec == precision
    expected = _exact_cents(quantity, rate)
    assert (
        line_amount({"status": "active", "quantity": quantity, "unit_sell_rate": rate})[0]
        == expected
    )
    assert result["status"] == "calculated"
    first = result["lines"][0]["calculation"]
    assert first["quantity"] == quantity
    assert first["amount_ex_tax"] == expected
    assert first["withheld_reasons"] == []
    assert result["lines"][1]["calculation"]["amount_ex_tax"] == "0.01"
    cents = int(expected.replace(".", "")) + 1
    assert result["total_ex_tax"] == f"{cents // 100}.{cents % 100:02d}"
    assert result["proposal_sha256"] == digest(
        {key: value for key, value in result.items() if key != "proposal_sha256"}
    )
    assert not any(value for key, value in result["effects"].items() if key != "price_calculated")
