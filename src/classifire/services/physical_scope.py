from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Opening
from ..physical_models import ServiceOpeningLink

CANONICAL_BLANK_OPENING_TYPES = frozenset({"blank_opening", "blank_core_hole"})

_BLANK_OPENING_ALIASES = {
    "blank": "blank_opening",
    "blank opening": "blank_opening",
    "blank opening seal": "blank_opening",
    "blank aperture": "blank_opening",
    "aperture seal": "blank_opening",
    "empty opening": "blank_opening",
    "blank_opening": "blank_opening",
    "blank core": "blank_core_hole",
    "blank core hole": "blank_core_hole",
    "empty core": "blank_core_hole",
    "empty core hole": "blank_core_hole",
    "redundant core": "blank_core_hole",
    "redundant core hole": "blank_core_hole",
    "blank_core_hole": "blank_core_hole",
    "empty_core_hole": "blank_core_hole",
    "redundant_core_hole": "blank_core_hole",
}


def canonical_opening_type(value: object) -> str | None:
    """Normalize only governed blank-opening aliases without guessing other types."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.lower().replace("-", " ").replace("_", " ")
    normalized = " ".join(normalized.split())
    return _BLANK_OPENING_ALIASES.get(normalized, raw)


def is_blank_opening_type(value: object) -> bool:
    return canonical_opening_type(value) in CANONICAL_BLANK_OPENING_TYPES


@dataclass(frozen=True, slots=True)
class OpeningCompleteness:
    opening_id: str
    opening_code: str
    opening_type: str | None
    service_link_count: int
    missing_fields: tuple[str, ...]
    blank_opening: bool
    service_relationship_complete: bool

    @property
    def complete(self) -> bool:
        return not self.missing_fields and self.service_relationship_complete

    def as_dict(self) -> dict[str, Any]:
        return {
            "opening_id": self.opening_id,
            "opening_code": self.opening_code,
            "opening_type": self.opening_type,
            "service_link_count": self.service_link_count,
            "blank_opening": self.blank_opening,
            "service_relationship_complete": self.service_relationship_complete,
            "missing_fields": list(self.missing_fields),
            "complete": self.complete,
        }


@dataclass(frozen=True, slots=True)
class PhysicalModelCompleteness:
    estimate_id: str
    opening_count: int
    complete: bool
    openings: tuple[OpeningCompleteness, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimate_id": self.estimate_id,
            "opening_count": self.opening_count,
            "complete": self.complete,
            "openings": [row.as_dict() for row in self.openings],
        }


def assess_physical_model_completeness(
    db: Session,
    estimate_id: str,
) -> PhysicalModelCompleteness:
    """Assess the physical model without inferring service relationships.

    A service-free opening is valid only where it is explicitly classified as a
    governed blank opening or blank core hole. Conversely, a blank opening with
    any service link is internally inconsistent and remains incomplete. Multiple
    canonical service links on a non-blank opening are valid.
    """
    openings = list(
        db.scalars(
            select(Opening)
            .where(Opening.estimate_id == estimate_id)
            .order_by(Opening.created_at, Opening.id)
        ).all()
    )
    opening_ids = [item.id for item in openings]
    links = (
        list(
            db.scalars(
                select(ServiceOpeningLink).where(ServiceOpeningLink.opening_id.in_(opening_ids))
            ).all()
        )
        if opening_ids
        else []
    )
    link_counts = {opening_id: 0 for opening_id in opening_ids}
    for link in links:
        link_counts[link.opening_id] = link_counts.get(link.opening_id, 0) + 1

    rows: list[OpeningCompleteness] = []
    for opening in openings:
        missing: list[str] = []
        for field_name in ("substrate_type", "substrate_plane", "orientation", "frl"):
            value = getattr(opening, field_name)
            if value is None or not str(value).strip():
                missing.append(field_name)

        opening_type = canonical_opening_type(opening.opening_type)
        blank_opening = is_blank_opening_type(opening_type)
        service_link_count = link_counts.get(opening.id, 0)
        if blank_opening:
            service_relationship_complete = service_link_count == 0
            if service_link_count:
                missing.append("blank_opening_must_not_have_service_links")
        else:
            service_relationship_complete = service_link_count > 0
            if not service_relationship_complete:
                missing.append("service_opening_link_or_blank_opening_classification")

        rows.append(
            OpeningCompleteness(
                opening_id=opening.id,
                opening_code=opening.opening_code,
                opening_type=opening_type,
                service_link_count=service_link_count,
                missing_fields=tuple(missing),
                blank_opening=blank_opening,
                service_relationship_complete=service_relationship_complete,
            )
        )

    return PhysicalModelCompleteness(
        estimate_id=estimate_id,
        opening_count=len(rows),
        complete=bool(rows) and all(row.complete for row in rows),
        openings=tuple(rows),
    )


__all__ = [
    "CANONICAL_BLANK_OPENING_TYPES",
    "OpeningCompleteness",
    "PhysicalModelCompleteness",
    "assess_physical_model_completeness",
    "canonical_opening_type",
    "is_blank_opening_type",
]
