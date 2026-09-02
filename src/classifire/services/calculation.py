from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import ceil

from sqlalchemy.orm import Session

from ..models import Estimate, EstimateLine, MarkupProfile, Product, Project
from .release_scope import (
    ReleaseScopeError,
    pinned_labour,
    pinned_markup_profiles,
    pinned_pricing_record,
    pinned_product,
    pinned_release,
)

MONEY = Decimal("0.01")
RATE = Decimal("0.000001")
QTY = Decimal("0.000001")


def D(value: object | None, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value).replace("%", "").strip())


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def rate(value: Decimal) -> Decimal:
    return value.quantize(RATE, rounding=ROUND_HALF_UP)


def quantity(value: Decimal) -> Decimal:
    return value.quantize(QTY, rounding=ROUND_HALF_UP)


def markup_to_margin(markup: Decimal) -> Decimal:
    if markup <= Decimal("-1"):
        raise ValueError("Markup must be greater than -100%")
    return rate(markup / (Decimal("1") + markup))


def margin_to_markup(margin: Decimal) -> Decimal:
    if margin >= Decimal("1"):
        raise ValueError("Gross margin must be less than 100%")
    return rate(margin / (Decimal("1") - margin))


def sell_from_markup(cost: Decimal, markup: Decimal) -> Decimal:
    return money(cost * (Decimal("1") + markup))


def sell_from_margin(cost: Decimal, margin: Decimal) -> Decimal:
    if margin >= Decimal("1"):
        raise ValueError("Gross margin must be less than 100%")
    return money(cost / (Decimal("1") - margin))


def apply_waste(quantity_value: Decimal, waste_factor: Decimal) -> Decimal:
    return quantity(quantity_value * (Decimal("1") + waste_factor))


def round_to_pack(quantity_value: Decimal, pack_size: Decimal, minimum_order: Decimal) -> Decimal:
    if pack_size <= 0:
        raise ValueError("Pack size must be positive")
    requested = max(quantity_value, minimum_order)
    packs = ceil(requested / pack_size)
    return quantity(Decimal(packs) * pack_size)


@dataclass(frozen=True)
class MarkupDecision:
    value: Decimal
    source: str


def _scope_profile(
    db: Session, estimate: Estimate, scope_type: str, scope_id: str | None, component_type: str
) -> MarkupDecision | None:
    profiles = pinned_markup_profiles(db, estimate)
    matching = [p for p in profiles if p.scope_type == scope_type and p.scope_id == scope_id]
    matching.sort(
        key=lambda p: (p.effective_date is not None, p.effective_date, p.created_at), reverse=True
    )
    if not matching:
        return None
    profile: MarkupProfile = matching[0]
    attr = {
        "product": "product_markup",
        "material": "material_markup",
        "labour": "labour_markup",
    }.get(component_type, "material_markup")
    value = getattr(profile, attr)
    release = pinned_release(db, estimate, "markups")
    return (
        MarkupDecision(
            D(value), f"markups_release:{release.version}:{scope_type}:{scope_id or 'default'}"
        )
        if value is not None
        else None
    )


def resolve_markup(
    db: Session,
    *,
    estimate: Estimate,
    component_type: str,
    line_override: Decimal | None = None,
    item: Product | None = None,
    category: str | None = None,
) -> MarkupDecision:
    if line_override is not None:
        return MarkupDecision(rate(D(line_override)), "estimate_line_override")

    attr = {
        "product": "product_markup_override",
        "material": "material_markup_override",
        "labour": "labour_markup_override",
    }.get(component_type, "material_markup_override")

    estimate_value = getattr(estimate, attr)
    if estimate_value is not None:
        return MarkupDecision(rate(D(estimate_value)), "estimate_override")

    project: Project = estimate.project
    project_value = getattr(project, attr)
    if project_value is not None:
        return MarkupDecision(rate(D(project_value)), "project_override")

    # Explicit MarkupProfile overrides are authoritative before legacy
    # Product.default_markup. Imported Package 14-derived products were seeded
    # with a 30% default markup, which is a fallback rather than an intentional
    # per-item override.
    if item:
        decision = _scope_profile(db, estimate, "item", item.id, component_type)
        if decision:
            return decision

    if category:
        decision = _scope_profile(db, estimate, "category", category, component_type)
        if decision:
            return decision

    decision = _scope_profile(db, estimate, "global", None, component_type)
    if decision:
        return decision

    # Compatibility fallback for legacy/imported product defaults when no
    # MarkupProfile exists in the estimate's pinned Markups release.
    if item and item.default_markup is not None:
        release = pinned_release(db, estimate, "products")
        return MarkupDecision(
            rate(D(item.default_markup)),
            f"products_release:{release.version}:legacy_item_fallback:{item.sku}",
        )

    release = pinned_release(db, estimate, "markups")
    return MarkupDecision(
        Decimal("0"),
        f"markups_release:{release.version}:fallback_zero",
    )


def calculate_line(
    *,
    quantity_value: Decimal,
    base_unit_cost: Decimal,
    waste_factor: Decimal,
    markup: Decimal,
    tax_rate: Decimal,
) -> dict[str, Decimal]:
    q_with_waste = apply_waste(D(quantity_value), D(waste_factor))
    unit_sell = sell_from_markup(D(base_unit_cost), D(markup))
    subtotal = money(q_with_waste * unit_sell)
    tax = money(subtotal * D(tax_rate))
    return {
        "quantity_with_waste": q_with_waste,
        "unit_sell": unit_sell,
        "subtotal_ex_tax": subtotal,
        "tax": tax,
        "total_incl_tax": money(subtotal + tax),
    }


def _library_rate_line(db: Session, estimate: Estimate, line: EstimateLine) -> EstimateLine:
    if not line.component_reference:
        raise ReleaseScopeError("A Package 14 PKB Entry ID is required for library-rate pricing.")
    record = pinned_pricing_record(db, estimate, line.component_reference)
    release = pinned_release(db, estimate, "pricing")
    values = calculate_line(
        quantity_value=D(line.quantity),
        base_unit_cost=D(record.rate_ex_tax),
        waste_factor=D(line.waste_factor),
        markup=Decimal("0"),
        tax_rate=D(estimate.tax_rate),
    )
    line.base_unit_cost = D(record.rate_ex_tax)
    line.applied_markup = Decimal("0")
    line.markup_source = "included_in_pinned_library_rate"
    line.unit_sell = values["unit_sell"]
    line.subtotal_ex_tax = values["subtotal_ex_tax"]
    line.tax = values["tax"]
    line.total_incl_tax = values["total_incl_tax"]
    line.rate_source = (
        f"pricing_release:{release.version}:{record.pkb_entry_id}:"
        f"{record.entry_version or 'unversioned'}"
    )
    line.formula_version = "QF-LIBRARY-RATE-1"
    return line


def calculate_estimate_line(db: Session, estimate: Estimate, line: EstimateLine) -> EstimateLine:
    if line.pricing_method == "library_rate":
        return _library_rate_line(db, estimate, line)

    item: Product | None = None
    category: str | None = None
    if line.pricing_method == "expert_estimate":
        line.rate_source = "expert_estimate:user_input"
    elif line.component_type in {"product", "material"}:
        if not line.component_reference:
            raise ReleaseScopeError(
                "Product/material component-built pricing requires a reference from "
                "the pinned Products release."
            )
        item = pinned_product(db, estimate, line.component_reference)
        category = item.category
        line.base_unit_cost = D(item.base_cost)
        line.waste_factor = D(item.waste_factor)
        release = pinned_release(db, estimate, "products")
        line.rate_source = f"products_release:{release.version}:{item.sku}:r{item.revision}"
    elif line.component_type == "labour":
        if not line.component_reference:
            raise ReleaseScopeError(
                "Labour component-built pricing requires a code from the pinned Labour release."
            )
        labour = pinned_labour(db, estimate, line.component_reference)
        line.base_unit_cost = D(labour.base_rate)
        release = pinned_release(db, estimate, "labour")
        line.rate_source = f"labour_release:{release.version}:{labour.code}:r{labour.revision}"
    else:
        line.rate_source = f"{line.component_type}:user_input"

    decision = resolve_markup(
        db,
        estimate=estimate,
        component_type=line.component_type,
        line_override=D(line.markup_override) if line.markup_override is not None else None,
        item=item,
        category=category,
    )
    values = calculate_line(
        quantity_value=D(line.quantity),
        base_unit_cost=D(line.base_unit_cost),
        waste_factor=D(line.waste_factor),
        markup=decision.value,
        tax_rate=D(estimate.tax_rate),
    )
    line.applied_markup = decision.value
    line.markup_source = decision.source
    line.unit_sell = values["unit_sell"]
    line.subtotal_ex_tax = values["subtotal_ex_tax"]
    line.tax = values["tax"]
    line.total_incl_tax = values["total_incl_tax"]
    line.formula_version = "QF-CALC-1"
    return line


def recalculate_estimate(db: Session, estimate: Estimate) -> Estimate:
    for line in estimate.lines:
        calculate_estimate_line(db, estimate, line)
    estimate.subtotal_ex_tax = money(
        sum((D(x.subtotal_ex_tax) for x in estimate.lines), Decimal("0"))
    )
    estimate.tax_total = money(sum((D(x.tax) for x in estimate.lines), Decimal("0")))
    estimate.total_incl_tax = money(estimate.subtotal_ex_tax + estimate.tax_total)
    return estimate


def sum_money(values: Iterable[Decimal]) -> Decimal:
    return money(sum(values, Decimal("0")))
