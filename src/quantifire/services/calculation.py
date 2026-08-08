from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from math import ceil
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate, EstimateLine, MarkupProfile, Product, Project

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
    db: Session, scope_type: str, scope_id: str | None, component_type: str
) -> MarkupDecision | None:
    query = select(MarkupProfile).where(
        MarkupProfile.scope_type == scope_type,
        MarkupProfile.scope_id == scope_id,
        MarkupProfile.status == "active",
    )
    profile = db.scalar(query.order_by(MarkupProfile.effective_date.desc().nullslast()))
    if not profile:
        return None
    attr = {
        "product": "product_markup",
        "material": "material_markup",
        "labour": "labour_markup",
    }.get(component_type, "material_markup")
    value = getattr(profile, attr)
    return MarkupDecision(D(value), f"{scope_type}:{scope_id or 'default'}") if value is not None else None


def resolve_markup(
    db: Session,
    *,
    estimate: Estimate,
    component_type: str,
    line_override: Decimal | None = None,
    item: Product | None = None,
    category: str | None = None,
) -> MarkupDecision:
    """Resolve markup with the approved precedence model.

    estimate-line override > estimate override > project override > item/category > global.
    Values are decimal fractions, so 0.30 means 30% markup on cost.
    """
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

    if item and item.default_markup is not None:
        return MarkupDecision(rate(D(item.default_markup)), f"item:{item.sku}")

    if item:
        decision = _scope_profile(db, "item", item.id, component_type)
        if decision:
            return decision
    if category:
        decision = _scope_profile(db, "category", category, component_type)
        if decision:
            return decision

    decision = _scope_profile(db, "global", None, component_type)
    if decision:
        return decision
    return MarkupDecision(Decimal("0"), "fallback_zero")


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


def calculate_estimate_line(db: Session, estimate: Estimate, line: EstimateLine) -> EstimateLine:
    item: Product | None = None
    category: str | None = None
    if line.component_reference:
        item = db.scalar(
            select(Product)
            .where(Product.sku == line.component_reference, Product.status == "active")
            .order_by(Product.revision.desc())
        )
        category = item.category if item else None
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
    return line


def recalculate_estimate(db: Session, estimate: Estimate) -> Estimate:
    for line in estimate.lines:
        calculate_estimate_line(db, estimate, line)
    estimate.subtotal_ex_tax = money(sum((D(x.subtotal_ex_tax) for x in estimate.lines), Decimal("0")))
    estimate.tax_total = money(sum((D(x.tax) for x in estimate.lines), Decimal("0")))
    estimate.total_incl_tax = money(estimate.subtotal_ex_tax + estimate.tax_total)
    return estimate


def sum_money(values: Iterable[Decimal]) -> Decimal:
    return money(sum(values, Decimal("0")))
