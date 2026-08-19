"""Strict schemas shared by preflight and controlled physical-model submission.

These payloads deliberately live outside an API router so the no-write
preflight and the admission-bound writer validate exactly the same topology.
They describe a physical model only; they do not grant authority to persist it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentOpeningInput(_StrictModel):
    opening_code: str = Field(min_length=1, max_length=100)
    external_defect_id: str | None = Field(default=None, max_length=150)
    location: str | None = None
    substrate_type: str | None = Field(default=None, max_length=200)
    substrate_plane: str | None = Field(default=None, max_length=50)
    substrate_thickness_mm: Decimal | None = Field(default=None, gt=0)
    orientation: str | None = Field(default=None, max_length=100)
    opening_type: str | None = Field(default=None, max_length=100)
    width_mm: Decimal | None = Field(default=None, gt=0)
    height_mm: Decimal | None = Field(default=None, gt=0)
    diameter_mm: Decimal | None = Field(default=None, gt=0)
    frl: str | None = Field(default=None, max_length=100)
    notes: str | None = None

    @field_validator("opening_code", "external_defect_id")
    @classmethod
    def _nonblank_identifier(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("identifier must not be blank")
        return value


class AgentServiceInput(_StrictModel):
    service_code: str = Field(min_length=1, max_length=100)
    primary_opening_code: str = Field(min_length=1, max_length=100)
    opening_codes: list[str] = Field(min_length=1, max_length=50)
    service_type: str = Field(min_length=1, max_length=200)
    material: str | None = Field(default=None, max_length=200)
    nominal_size_mm: Decimal | None = Field(default=None, gt=0)
    outside_diameter_mm: Decimal | None = Field(default=None, gt=0)
    width_mm: Decimal | None = Field(default=None, gt=0)
    height_mm: Decimal | None = Field(default=None, gt=0)
    insulation_type: str | None = Field(default=None, max_length=200)
    insulation_thickness_mm: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal = Field(gt=0)
    centre_x_mm: Decimal | None = None
    centre_y_mm: Decimal | None = None
    evidence_status: str = Field(default="provisional", max_length=30)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    relationship_status: str = Field(default="confirmed", max_length=30)
    link_type: str = Field(default="penetrates", max_length=50)
    source_reference: str | None = None
    notes: str | None = None

    @field_validator("service_code", "primary_opening_code", "service_type")
    @classmethod
    def _nonblank_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value

    @field_validator("opening_codes")
    @classmethod
    def _nonblank_opening_codes(cls, values: list[str]) -> list[str]:
        if any(not item.strip() for item in values):
            raise ValueError("opening_codes must not contain blank values")
        if len(set(values)) != len(values):
            raise ValueError("opening_codes must be unique")
        return values


class AgentInitialPhysicalModelInput(_StrictModel):
    openings: list[AgentOpeningInput] = Field(min_length=1, max_length=5000)
    services: list[AgentServiceInput] = Field(min_length=0, max_length=10000)


class AgentAdjudicatedInitialPhysicalSubmissionRequest(_StrictModel):
    admission_id: str = Field(min_length=36, max_length=100)
    idempotency_key: str = Field(min_length=16, max_length=200)

    @field_validator("admission_id", "idempotency_key")
    @classmethod
    def _nonblank_request_identifier(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identifier must not be blank")
        return value


__all__ = [
    "AgentAdjudicatedInitialPhysicalSubmissionRequest",
    "AgentInitialPhysicalModelInput",
    "AgentOpeningInput",
    "AgentServiceInput",
]
