from __future__ import annotations

from datetime import date


def technical_variant_temporal_blockers(
    *,
    effective_date: date | None,
    expiry_date: date | None,
    as_of: date | None = None,
) -> tuple[str, ...]:
    """Return safe reasons a technical variant is not currently usable.

    An expiry date remains usable on that date. A future effective date is not
    usable until the stated day arrives.
    """
    current_day = as_of or date.today()
    blockers: list[str] = []
    if effective_date and effective_date > current_day:
        blockers.append("not_yet_effective")
    if expiry_date and expiry_date < current_day:
        blockers.append("expired")
    return tuple(blockers)
