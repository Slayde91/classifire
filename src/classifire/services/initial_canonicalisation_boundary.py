"""Shared guard for the first persisted canonical physical model.

When signed adjudicated submission is enabled, a normal human CRUD request may
continue an older populated model but must never create an empty estimate's
first Opening.  The dedicated controlled writer is the only supported path for
that transition because it records the signed admission and submission journal
in the same transaction as the canonical rows.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opening


class InitialCanonicalisationAdmissionRequired(RuntimeError):
    """Raised when generic CRUD attempts to create an initial physical model."""


def require_admission_bound_initial_canonicalisation(
    db: Session,
    *,
    estimate_id: str,
    enabled: bool,
) -> None:
    """Fail closed before generic CRUD creates an empty estimate's first Opening.

    Existing populated estimates remain editable through their established human
    workflow.  A historic submission journal never acts as reusable authority:
    if all current Openings are gone, a new signed admission is required.  The
    guard intentionally has no side effects.
    """

    if not enabled:
        return
    has_existing_opening = db.scalar(
        select(Opening.id).where(Opening.estimate_id == estimate_id).limit(1)
    )
    if has_existing_opening is not None:
        return
    raise InitialCanonicalisationAdmissionRequired(
        "Initial canonical physical model requires a signed admission-bound submission."
    )


__all__ = [
    "InitialCanonicalisationAdmissionRequired",
    "require_admission_bound_initial_canonicalisation",
]
