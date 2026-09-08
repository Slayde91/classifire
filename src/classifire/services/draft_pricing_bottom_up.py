"""Deterministic, read-only bottom-up price proposal preview."""

from __future__ import annotations

import hashlib
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal, cast

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftPricingRowObservation, User
from .draft_pricing_coverage import preview_coverage
from .draft_pricing_intake import _row_observation_value
from .draft_pricing_quantities import current_quantity_bases
from .draft_pricing_recipes import recipe_review_context
from .draft_scope import DraftScopeError
from .draft_system_match_contract import canonical, digest

SCHEMA = "CLASSIFIRE-DRAFT-BOTTOM-UP-PROPOSAL-v1"
ALLOWED_PRICE_MEANINGS = ("sell_price",)
EFFECTS = {
    "price_calculated": False,
    "proposal_created": False,
    "pricing_library_activated": False,
    "technical_approval_granted": False,
    "technical_applicability_assessed": False,
    "system_match_changed": False,
    "estimate_changed": False,
    "evaluation_performed": False,
    "release_performed": False,
}


def _quantity(value: str | None, unit: str) -> str | None:
    if value is None or not value.strip():
        return None
    try:
        number = Decimal(value.strip())
    except (InvalidOperation, ValueError) as exc:
        raise DraftScopeError("BOTTOM_UP_QUANTITY_INVALID", 422) from exc
    if not number.is_finite() or number <= 0 or number > Decimal("1000000000"):
        raise DraftScopeError("BOTTOM_UP_QUANTITY_INVALID", 422)
    if unit == "each" and number != number.to_integral_value():
        raise DraftScopeError("BOTTOM_UP_QUANTITY_INVALID", 422)
    return format(number.normalize(), "f")


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f")


def preview_bottom_up(
    db: Session,
    actor: User,
    draft_id: str,
    technical_release_id: str,
    technical_target_id: str,
    quantities: dict[str, str] | None = None,
    *,
    settings: Settings,
    quantity_source: Literal["governed", "manual_preview"] = "governed",
) -> dict[str, Any]:
    """Calculate a transparent proposal from exact governed recipe dependencies.

    Governed mode reads only current immutable Scope-bound quantity records.
    Manual mode preserves the earlier explicit, read-only prototype for tests
    and comparison. Neither mode infers values from notes or changes the database.
    """

    coverage = preview_coverage(db, actor, draft_id, technical_release_id, settings=settings)
    target = next(
        (
            item
            for item in coverage["targets"]
            if item["technical_target"]["id"] == technical_target_id
        ),
        None,
    )
    if target is None:
        raise DraftScopeError("BOTTOM_UP_TARGET_NOT_FOUND", 404)
    context = recipe_review_context(
        db,
        actor,
        draft_id,
        technical_release_id,
        technical_target_id,
        settings=settings,
    )
    latest: dict[str, dict[str, Any]] = {}
    for link in context["links"]:
        requirement_id = link["value"]["definition"]["requirement"]["id"]
        latest[requirement_id] = link
    submitted = quantities or {}
    requirement_ids = {item["id"] for item in context["requirements"]}
    unknown = sorted(set(submitted) - requirement_ids)
    if unknown:
        raise DraftScopeError("BOTTOM_UP_QUANTITY_REQUIREMENT_UNKNOWN", 422)
    governed = (
        current_quantity_bases(
            db,
            actor,
            draft_id,
            technical_release_id,
            technical_target_id,
            settings=settings,
        )
        if quantity_source == "governed"
        else {}
    )

    lines: list[dict[str, Any]] = []
    for requirement in context["requirements"]:
        requirement_id = requirement["id"]
        link = latest.get(requirement_id)
        saved_basis = governed.get(requirement_id)
        quantity_basis = (
            {
                "id": saved_basis["id"],
                "sha256": saved_basis["sha256"],
                "definition_sha256": saved_basis["value"]["definition_sha256"],
                "scope": saved_basis["value"]["definition"]["scope"],
                "recipe_link": saved_basis["value"]["definition"]["recipe_link"],
                "quantity_basis": saved_basis["value"]["definition"]["quantity_basis"],
            }
            if saved_basis is not None
            else None
        )
        if link is None:
            lines.append(
                {
                    "requirement": requirement,
                    "recipe_link": None,
                    "quantity_basis": quantity_basis,
                    "observation": None,
                    "calculation": {
                        "status": "withheld",
                        "quantity": (
                            quantity_basis["quantity_basis"]["quantity"]
                            if quantity_basis is not None
                            else _quantity(submitted.get(requirement_id), "")
                        ),
                        "unit": None,
                        "unit_rate": None,
                        "currency": None,
                        "price_meaning": None,
                        "tax_basis": None,
                        "formula": "quantity_x_unit_rate_round_half_up_2dp",
                        "amount_ex_tax": None,
                        "withheld_reasons": ["recipe_link_required"],
                    },
                }
            )
            continue
        definition = link["value"]["definition"]
        interpretation = definition["interpretation"]
        reasons: list[str] = []
        observations = definition["observations"]
        if target["status"] != "bottom_up_a_support":
            reasons.append("target_not_ready_for_bottom_up")
        if not link["current"]:
            reasons.append("recipe_link_stale")
        if interpretation["status"] != "linked":
            reasons.append("recipe_requirement_unresolved")
        if interpretation["evidence_state"] != "confirmed":
            reasons.append("recipe_evidence_not_confirmed")
        if interpretation["unresolved_fields"]:
            reasons.append("recipe_fields_unresolved")
        if len(observations) != 1:
            reasons.append("prototype_requires_one_observation_per_requirement")

        observation_value = None
        row_values: dict[str, Any] = {}
        if len(observations) == 1:
            observation = observations[0]
            row = db.get(DraftPricingRowObservation, observation["id"])
            if row is None:
                reasons.append("observation_missing")
            else:
                observation_value = _row_observation_value(row)
                if row.observation_sha256 != observation["sha256"]:
                    reasons.append("observation_hash_changed")
                row_values = observation_value["definition"]["row"]["values"]
                price_meaning = observation_value["definition"]["profile"]["price_meaning"]
                if price_meaning not in ALLOWED_PRICE_MEANINGS:
                    reasons.append("price_meaning_not_sell_ready")
                if row_values.get("currency") != "AUD":
                    reasons.append("currency_not_supported")
                if row_values.get("tax_basis") not in ("excluded", "GST Exclusive"):
                    reasons.append("tax_basis_not_gst_exclusive")
                if row_values.get("unit") != interpretation["unit"]:
                    reasons.append("unit_mismatch")

        if quantity_source == "governed":
            if quantity_basis is None:
                quantity = None
                reasons.append("project_quantity_basis_required")
            else:
                saved = quantity_basis["quantity_basis"]
                quantity = _quantity(saved["quantity"], saved["unit"])
                if saved["unit"] != interpretation["unit"]:
                    reasons.append("project_quantity_unit_mismatch")
        else:
            quantity = _quantity(submitted.get(requirement_id), interpretation["unit"] or "")
            if quantity is None:
                reasons.append("quantity_required")
        rate = row_values.get("rate")
        amount = None
        if not reasons and rate is not None and quantity is not None:
            try:
                amount = _money(Decimal(quantity) * Decimal(rate))
            except (InvalidOperation, ValueError):
                reasons.append("rate_invalid")
        lines.append(
            {
                "requirement": requirement,
                "recipe_link": {
                    "id": link["id"],
                    "sha256": hashlib.sha256(canonical(link["value"])).hexdigest(),
                },
                "quantity_basis": quantity_basis,
                "observation": observations[0] if len(observations) == 1 else None,
                "calculation": {
                    "status": "calculated" if amount is not None else "withheld",
                    "quantity": quantity,
                    "unit": interpretation["unit"],
                    "unit_rate": rate,
                    "currency": row_values.get("currency"),
                    "price_meaning": (
                        observation_value["definition"]["profile"]["price_meaning"]
                        if observation_value is not None
                        else None
                    ),
                    "tax_basis": row_values.get("tax_basis"),
                    "formula": "quantity_x_unit_rate_round_half_up_2dp",
                    "amount_ex_tax": amount,
                    "withheld_reasons": reasons,
                },
            }
        )

    calculated = bool(lines) and all(
        line["calculation"]["status"] == "calculated" for line in lines
    )
    total = (
        _money(sum((Decimal(line["calculation"]["amount_ex_tax"]) for line in lines), Decimal("0")))
        if calculated
        else None
    )
    result = {
        "schema_version": SCHEMA,
        "draft_scope_id": draft_id,
        "technical_release": coverage["technical_release"],
        "technical_target": target["technical_target"],
        "coverage_sha256": coverage["coverage_sha256"],
        "method": "component_activity_recipe",
        "status": "calculated" if calculated else "withheld",
        "currency": "AUD" if calculated else None,
        "total_ex_tax": total,
        "lines": lines,
        "limitations": [
            (
                "quantities_are_current_saved_scope_service_bases"
                if quantity_source == "governed"
                else "quantities_are_explicit_preview_only_inputs"
            ),
            "one_reviewed_observation_per_requirement_is_supported_in_this_prototype",
            "preview_does_not_prove_project_specific_technical_applicability",
            "preview_does_not_create_or_change_an_estimate",
        ],
        "effects": {**EFFECTS, "price_calculated": calculated},
    }
    result["proposal_sha256"] = digest(result)
    return cast(dict[str, Any], result)


__all__ = ["ALLOWED_PRICE_MEANINGS", "EFFECTS", "SCHEMA", "preview_bottom_up"]
