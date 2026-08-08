from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    item_type: str = Field(default="product", pattern="^(product|material)$")
    category: str | None = None
    manufacturer: str | None = None
    supplier: str | None = None
    unit: str = "each"
    pack_size: Decimal = Decimal("1")
    minimum_order_quantity: Decimal = Decimal("1")
    base_cost: Decimal = Decimal("0")
    currency: str = "AUD"
    tax_treatment: str = "exclusive"
    waste_factor: Decimal = Decimal("0")
    default_markup: Decimal | None = None
    effective_date: date | None = None
    status: str = "draft"
    notes: str | None = None

    @field_validator("waste_factor", "default_markup")
    @classmethod
    def validate_percent(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value < 0 or value > 10):
            raise ValueError("Markup and waste factors must be expressed as decimal fractions")
        return value


class ProductOut(ProductInput, ORMModel):
    id: str
    revision: int
    created_at: datetime
    updated_at: datetime


class LabourInput(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    trade_or_grade: str | None = None
    category: str | None = None
    unit: str = "person_hour"
    base_rate: Decimal = Decimal("0")
    default_hours: Decimal = Decimal("0")
    crew_size: Decimal = Decimal("1")
    default_markup: Decimal | None = None
    productivity_source: str | None = None
    effective_date: date | None = None
    status: str = "draft"
    notes: str | None = None


class LabourOut(LabourInput, ORMModel):
    id: str
    revision: int
    created_at: datetime
    updated_at: datetime


class RuleInput(BaseModel):
    rule_code: str
    name: str
    category: str
    description: str
    conditions: dict[str, Any]
    actions: dict[str, Any]
    severity: str = "warning"
    jurisdiction: str | None = None
    source_reference: str | None = None
    source_page: str | None = None
    priority: int = 100
    status: str = "draft"
    effective_date: date | None = None
    test_cases: list[dict[str, Any]] | None = None


class RuleOut(RuleInput, ORMModel):
    id: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectInput(BaseModel):
    reference: str
    name: str
    site_address: str | None = None
    jurisdiction: str = "NSW/ACT, Australia"
    customer_id: str | None = None
    product_markup_override: Decimal | None = None
    material_markup_override: Decimal | None = None
    labour_markup_override: Decimal | None = None
    notes: str | None = None


class ProjectOut(ProjectInput, ORMModel):
    id: str
    status: str
    created_at: datetime
    updated_at: datetime


class EstimateInput(BaseModel):
    project_id: str
    reference: str
    title: str
    currency: str = "AUD"
    tax_name: str = "GST"
    tax_rate: Decimal = Decimal("0.10")
    product_markup_override: Decimal | None = None
    material_markup_override: Decimal | None = None
    labour_markup_override: Decimal | None = None


class EstimateOut(EstimateInput, ORMModel):
    id: str
    revision: int
    status: str
    subtotal_ex_tax: Decimal
    tax_total: Decimal
    total_incl_tax: Decimal
    snapshot_hash: str | None
    created_at: datetime
    updated_at: datetime


class OpeningInput(BaseModel):
    opening_code: str
    defect_id: str | None = None
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


class ServiceInput(BaseModel):
    service_code: str
    service_type: str
    material: str | None = None
    nominal_size_mm: Decimal | None = None
    outside_diameter_mm: Decimal | None = None
    width_mm: Decimal | None = None
    height_mm: Decimal | None = None
    insulation_type: str | None = None
    insulation_thickness_mm: Decimal | None = None
    quantity: Decimal = Decimal("1")
    centre_x_mm: Decimal | None = None
    centre_y_mm: Decimal | None = None
    evidence_status: str = "provisional"
    confidence: Decimal | None = None
    notes: str | None = None


class EstimateLineInput(BaseModel):
    opening_id: str | None = None
    service_id: str | None = None
    component_type: str
    component_reference: str | None = None
    description: str
    quantity: Decimal = Decimal("1")
    unit: str = "each"
    base_unit_cost: Decimal = Decimal("0")
    waste_factor: Decimal = Decimal("0")
    markup_override: Decimal | None = None
    pricing_method: str = "component_built"
    commercial_recovery_status: str = "separately_priced"
    rate_source: str | None = None
    notes: str | None = None


class ChangeProposalInput(BaseModel):
    entity_type: str
    entity_id: str | None = None
    proposal_type: str
    proposed_data: dict[str, Any]
    reason: str


class TechnicalVariantSearch(BaseModel):
    service_type: str | None = None
    service_material: str | None = None
    substrate: str | None = None
    orientation: str | None = None
    frl: str | None = None
    limit: int = Field(default=20, ge=1, le=100)
