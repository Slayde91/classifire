from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import RepairStrategyLock, SystemRequiredComponent
from ..commercial_models import ProductivitySource
from ..models import Estimate, Opening
from .quantity_labour import (
    QuantityLabourDerivation,
    QuantityLabourError,
    _persist_labour_activity,
    _persist_quantity,
    _resolve_formula,
)
from .release_scope import pinned_productivity_source
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


def derive_quantity_and_labour_runtime(
    db: Session,
    estimate: Estimate,
    *,
    component_inputs: dict[str, dict[str, Any]] | None = None,
    labour_adjustments: dict[str, dict[str, Any]] | None = None,
) -> QuantityLabourDerivation:
    """Production runtime wrapper for deterministic quantity/person-hour derivation.

    Formula execution remains in quantity_labour.py. This wrapper adds immutable
    release scoping: every ProductivitySource must be present in the estimate's
    pinned Labour release. Commercial labour rates are intentionally not applied.
    """
    require_estimate_action(db, estimate, WorkflowAction.CALCULATE_QUANTITY_AND_LABOUR)
    component_inputs = component_inputs or {}
    labour_adjustments = labour_adjustments or {}

    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate.id)).all()
    )
    if not opening_ids:
        raise QuantityLabourError("Estimate has no Openings for quantity derivation.")

    components = list(
        db.scalars(
            select(SystemRequiredComponent)
            .where(SystemRequiredComponent.opening_id.in_(opening_ids))
            .order_by(SystemRequiredComponent.opening_id, SystemRequiredComponent.id)
        ).all()
    )
    if not components:
        raise QuantityLabourError("Estimate has no SystemRequiredComponent records.")

    active_locks = list(
        db.scalars(
            select(RepairStrategyLock).where(
                RepairStrategyLock.opening_id.in_(opening_ids),
                RepairStrategyLock.invalidated_at.is_(None),
            )
        ).all()
    )
    locked_component_ids = {
        component_id
        for lock in active_locks
        for component_id in (lock.required_component_ids or [])
    }
    component_ids = {component.id for component in components}
    if not component_ids.issubset(locked_component_ids):
        missing = sorted(component_ids - locked_component_ids)
        raise QuantityLabourError(
            "SystemRequiredComponent records are not fully covered by active Repair Strategy Locks: "
            + ", ".join(missing)
        )

    # Resolve every formula and every pinned productivity source before writing
    # anything. This preserves fail-closed, no-partial-write behaviour.
    planned_formulas = {}
    planned_productivity: dict[tuple[str, str], ProductivitySource] = {}
    errors: list[str] = []
    for component in components:
        try:
            planned_formulas[component.id] = _resolve_formula(
                db, component, component_inputs.get(component.id, {})
            )
        except QuantityLabourError as exc:
            errors.append(f"{component.id}: {exc}")
        for activity in component.required_labour_activity_ids or []:
            try:
                productivity = pinned_productivity_source(db, estimate, activity)
                if productivity.executable_formula_id != "QF-LABOUR-ACTIVITY":
                    raise QuantityLabourError(
                        f"Pinned ProductivitySource {productivity.id} for {activity} uses unsupported "
                        f"formula {productivity.executable_formula_id!r}."
                    )
                planned_productivity[(component.id, activity)] = productivity
            except Exception as exc:
                errors.append(f"{component.id}/{activity}: {exc}")
    if errors:
        raise QuantityLabourError("; ".join(sorted(set(errors))))

    quantities = []
    quantity_by_component = {}
    for component in components:
        quantity = _persist_quantity(db, estimate, component, planned_formulas[component.id])
        quantities.append(quantity)
        quantity_by_component[component.id] = quantity

    labour_rows = []
    for component in components:
        quantity = quantity_by_component[component.id]
        for activity in component.required_labour_activity_ids or []:
            adjustment = (
                labour_adjustments.get(f"{component.id}:{activity}")
                or labour_adjustments.get(activity)
                or {}
            )
            labour_rows.append(
                _persist_labour_activity(
                    db,
                    estimate,
                    component,
                    quantity,
                    activity,
                    planned_productivity[(component.id, activity)],
                    adjustment,
                )
            )

    db.flush()
    return QuantityLabourDerivation(
        quantities=tuple(quantities),
        labour_activities=tuple(labour_rows),
    )


__all__ = ["derive_quantity_and_labour_runtime"]
