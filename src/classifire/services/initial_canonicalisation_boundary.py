"""Fail-closed guard for an estimate's first canonical Opening."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opening


class InitialCanonicalisationAdmissionRequired(RuntimeError):
    """Raised when a generic route attempts an admission-controlled first write."""


def require_admission_bound_initial_canonicalisation(
    db: Session,
    *,
    estimate_id: str,
    enabled: bool,
) -> None:
    """Allow legacy edits, but reserve an empty estimate's first Opening for the writer."""

    if not enabled:
        return
    existing_opening_id = db.scalar(
        select(Opening.id).where(Opening.estimate_id == estimate_id).limit(1)
    )
    if existing_opening_id is not None:
        return
    raise InitialCanonicalisationAdmissionRequired(
        "Initial canonical physical model requires a signed admission-bound submission."
    )


__all__ = [
    "InitialCanonicalisationAdmissionRequired",
    "require_admission_bound_initial_canonicalisation",
]
