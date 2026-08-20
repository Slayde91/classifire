"""The sealed, canonical payload for one initial physical-model submission."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InitialOpening(_StrictPayload):
    opening_code: str = Field(min_length=1, max_length=100)
    canonical_defect_id: str
    location: str | None = None
    substrate_type: str | None = None
    substrate_plane: str | None = None
    substrate_thickness_mm: Decimal | None = None
    orientation: str | None = None
    opening_type: str | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    diameter_mm: Decimal | None = None
    frl: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def require_canonical_defect_identifier(self) -> InitialOpening:
        try:
            UUID(self.canonical_defect_id)
        except ValueError as exc:
            raise ValueError("canonical_defect_id must be a UUID") from exc
        return self


class InitialService(_StrictPayload):
    service_code: str = Field(min_length=1, max_length=100)
    service_type: str = Field(min_length=1, max_length=200)
    material: str | None = None
    nominal_size_mm: Decimal | None = None
    outside_diameter_mm: Decimal | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    insulation_type: str | None = None
    insulation_thickness_mm: Decimal | None = None
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    centre_x_mm: Decimal | None = None
    centre_y_mm: Decimal | None = None
    evidence_status: str = Field(default="provisional", min_length=1, max_length=30)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    notes: str | None = None


class InitialServiceOpeningLink(_StrictPayload):
    service_code: str = Field(min_length=1, max_length=100)
    opening_code: str = Field(min_length=1, max_length=100)
    link_type: str = Field(default="penetrates", min_length=1, max_length=50)
    relationship_status: str = Field(default="confirmed", min_length=1, max_length=30)
    evidence_status: str = Field(default="provisional", min_length=1, max_length=30)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    source_reference: str | None = None
    notes: str | None = None


class InitialCanonicalPhysicalSubmission(_StrictPayload):
    """One complete, explicit initial model; no inferred links or defects."""

    openings: list[InitialOpening] = Field(min_length=1, max_length=500)
    services: list[InitialService] = Field(default_factory=list, max_length=2000)
    service_opening_links: list[InitialServiceOpeningLink] = Field(
        default_factory=list, max_length=4000
    )

    @model_validator(mode="after")
    def validate_complete_references(self) -> InitialCanonicalPhysicalSubmission:
        opening_codes = [item.opening_code for item in self.openings]
        service_codes = [item.service_code for item in self.services]
        if len(opening_codes) != len(set(opening_codes)):
            raise ValueError("opening_code values must be unique")
        if len(service_codes) != len(set(service_codes)):
            raise ValueError("service_code values must be unique")
        pairs = [(item.service_code, item.opening_code) for item in self.service_opening_links]
        if len(pairs) != len(set(pairs)):
            raise ValueError("service-to-opening links must be unique")
        known_openings = set(opening_codes)
        known_services = set(service_codes)
        for service_code, opening_code in pairs:
            if service_code not in known_services or opening_code not in known_openings:
                raise ValueError("every service-to-opening link must reference declared records")
        linked_services = {service_code for service_code, _opening_code in pairs}
        if linked_services != known_services:
            raise ValueError("every declared service must have at least one explicit opening link")
        return self
