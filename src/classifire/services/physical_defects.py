from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate
from ..physical_models import Defect


def bind_canonical_defect(
    db: Session,
    estimate: Estimate,
    external_defect_id: str | None,
) -> Defect | None:
    """Resolve or create the canonical Defect for a legacy opening identifier.

    Layer 2 retains the existing string ``Opening.defect_id`` for compatibility,
    but every new nonblank identifier is also deterministically bound to a
    canonical Defect row. The row is intentionally provisional until a later
    evidence/adjudication layer enriches it.
    """
    normalized = (external_defect_id or "").strip()
    if not normalized:
        return None

    defect = db.scalar(
        select(Defect)
        .where(
            Defect.estimate_id == estimate.id,
            Defect.external_defect_id == normalized,
        )
        .order_by(Defect.id)
    )
    if defect:
        return defect

    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id=normalized,
        defect_code=normalized,
        evidence_status="provisional",
        status="draft",
    )
    db.add(defect)
    db.flush()
    return defect


__all__ = ["bind_canonical_defect"]
