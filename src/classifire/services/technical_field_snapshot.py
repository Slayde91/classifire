"""Explicit public technical fields shared by release publication and Draft review."""

from __future__ import annotations

from ..models import TechnicalVariant

FIELD_NAMES = (
    "manufacturer",
    "product_family",
    "service_type",
    "service_material",
    "minimum_service_size_mm",
    "maximum_service_size_mm",
    "permitted_service_quantity",
    "insulation_type",
    "insulation_thickness_mm",
    "substrate_type",
    "minimum_substrate_thickness_mm",
    "maximum_substrate_thickness_mm",
    "orientation",
    "installation_face",
    "opening_type",
    "opening_dimensions",
    "annular_gap_min_mm",
    "annular_gap_max_mm",
    "service_spacing_rules",
    "edge_distance_rules",
    "support_rules",
    "fixing_rules",
    "hard_exclusions",
    "dependencies",
    "frl",
    "jurisdiction",
    "quality_score",
    "confidence_cap",
    "search_eligibility",
    "expert_review_required",
    "effective_date",
    "expiry_date",
)


def technical_fields(variant: TechnicalVariant) -> dict[str, str | bool | None]:
    return {
        key: value if key == "expert_review_required" else str(value) if value is not None else None
        for key in FIELD_NAMES
        for value in (getattr(variant, key),)
    }
