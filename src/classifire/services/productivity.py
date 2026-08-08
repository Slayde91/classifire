from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..commercial_models import ProductivitySource


SUPPORTED_PRODUCTIVITY_FORMULAS = {"QF-LABOUR-ACTIVITY"}
APPROVED_STATUSES = {"APPROVED", "ACTIVE", "CURRENT"}
TOLERANCE = Decimal("0.000001")


class ProductivitySourceError(ValueError):
    pass


def _d(value: object) -> Decimal:
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ProductivitySourceError(f"Value {value!r} is not numeric.") from exc


def create_productivity_source(
    db: Session,
    *,
    activity: str,
    quantity_unit: str,
    base_hours_per_unit: Decimal,
    source_record_id: str,
    source_version: str,
    executable_formula_id: str = "QF-LABOUR-ACTIVITY",
    source_quantity: str | None = None,
    source_crew: str | None = None,
    source_hours: Decimal | None = None,
    decomposition_formula: str | None = None,
    adjustment_formula: str | None = None,
    evidence_class: str | None = None,
    confidence: str | None = None,
) -> ProductivitySource:
    activity = activity.strip()
    quantity_unit = quantity_unit.strip()
    source_record_id = source_record_id.strip()
    source_version = source_version.strip()
    executable_formula_id = executable_formula_id.strip()
    if not activity or not quantity_unit or not source_record_id or not source_version:
        raise ProductivitySourceError(
            "activity, quantity_unit, source_record_id and source_version are required."
        )
    if executable_formula_id not in SUPPORTED_PRODUCTIVITY_FORMULAS:
        raise ProductivitySourceError(
            f"Unsupported productivity executable formula: {executable_formula_id}."
        )
    base = _d(base_hours_per_unit)
    if base <= 0:
        raise ProductivitySourceError("base_hours_per_unit must be greater than zero.")

    duplicate = db.scalar(
        select(ProductivitySource.id).where(
            ProductivitySource.source_record_id == source_record_id,
            ProductivitySource.source_version == source_version,
        )
    )
    if duplicate:
        raise ProductivitySourceError(
            f"Productivity source {source_record_id} version {source_version} already exists."
        )

    if source_hours is not None:
        if source_quantity is None:
            raise ProductivitySourceError(
                "source_quantity is required when source_hours is supplied."
            )
        source_qty = _d(source_quantity)
        source_hrs = _d(source_hours)
        if source_qty <= 0 or source_hrs <= 0:
            raise ProductivitySourceError("source_quantity and source_hours must be positive.")
        derived = source_hrs / source_qty
        if abs(derived - base) > TOLERANCE:
            raise ProductivitySourceError(
                "base_hours_per_unit does not reconcile to source_hours / source_quantity."
            )

    record = ProductivitySource(
        activity=activity,
        quantity_unit=quantity_unit,
        base_hours_per_unit=base,
        source_record_id=source_record_id,
        source_version=source_version,
        source_quantity=source_quantity,
        source_crew=source_crew,
        source_hours=source_hours,
        decomposition_formula=decomposition_formula,
        adjustment_formula=adjustment_formula,
        executable_formula_id=executable_formula_id,
        evidence_class=evidence_class,
        confidence=confidence,
        approval_status="DRAFT",
    )
    db.add(record)
    db.flush()
    return record


def approve_productivity_source(
    db: Session,
    source: ProductivitySource,
) -> tuple[ProductivitySource, bool]:
    status = (source.approval_status or "").strip().upper()
    if status == "APPROVED":
        return source, False
    if status not in {"DRAFT", "IN_REVIEW", "SUPERSEDED"}:
        raise ProductivitySourceError(
            f"Productivity source cannot be approved from status {source.approval_status!r}."
        )
    if not source.source_version:
        raise ProductivitySourceError("A versioned productivity source is required for approval.")
    if not source.evidence_class or not source.confidence:
        raise ProductivitySourceError(
            "evidence_class and confidence are required before productivity approval."
        )
    if source.executable_formula_id not in SUPPORTED_PRODUCTIVITY_FORMULAS:
        raise ProductivitySourceError("Productivity source executable formula is not approved.")
    if _d(source.base_hours_per_unit) <= 0:
        raise ProductivitySourceError("base_hours_per_unit must be greater than zero.")

    prior = list(
        db.scalars(
            select(ProductivitySource).where(
                ProductivitySource.activity == source.activity,
                ProductivitySource.id != source.id,
            )
        ).all()
    )
    for item in prior:
        if (item.approval_status or "").strip().upper() in APPROVED_STATUSES:
            item.approval_status = "SUPERSEDED"

    source.approval_status = "APPROVED"
    db.flush()
    return source, True


def approved_productivity_manifest_rows(db: Session) -> list[dict[str, str]]:
    records = list(
        db.scalars(
            select(ProductivitySource)
            .where(ProductivitySource.approval_status == "APPROVED")
            .order_by(ProductivitySource.activity, ProductivitySource.created_at.desc())
        ).all()
    )
    chosen: dict[str, ProductivitySource] = {}
    for record in records:
        chosen.setdefault(record.activity, record)
    return [
        {
            "id": record.id,
            "record_type": "productivity_source",
            "key": record.activity,
            "activity": record.activity,
            "quantity_unit": record.quantity_unit,
            "base_hours_per_unit": str(record.base_hours_per_unit),
            "source_record_id": record.source_record_id,
            "source_version": record.source_version or "",
            "executable_formula_id": record.executable_formula_id,
            "record_version": str(record.record_version),
        }
        for record in chosen.values()
    ]


__all__ = [
    "APPROVED_STATUSES",
    "ProductivitySourceError",
    "SUPPORTED_PRODUCTIVITY_FORMULAS",
    "approve_productivity_source",
    "approved_productivity_manifest_rows",
    "create_productivity_source",
]
