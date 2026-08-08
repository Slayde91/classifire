from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False
    )
    record_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class User(RecordMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="estimator", index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentServicePrincipal(RecordMixin, Base):
    """Machine credential for one role-limited CLASSIFIRE OpenClaw agent.

    Only a SHA-256 digest of the high-entropy bearer token is persisted. Scopes
    are explicit and independent of human User roles so an agent can never gain
    human approval authority by reusing a human session or role.
    """

    __tablename__ = "agent_service_principals"

    agent_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(RecordMixin, Base):
    __tablename__ = "audit_events"

    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    actor_type: Mapped[str] = mapped_column(String(30), default="user", nullable=False)
    actor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    previous_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(String(100))
    correlation_id: Mapped[str | None] = mapped_column(String(100), index=True)
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class LibraryRelease(RecordMixin, Base):
    __tablename__ = "library_releases"
    __table_args__ = (UniqueConstraint("library_type", "version", name="uq_library_release_type_version"),)

    library_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    release_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    source_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    supersedes_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))


class MarkupProfile(RecordMixin, Base):
    __tablename__ = "markup_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(100), index=True)
    product_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class Product(RecordMixin, Base):
    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("sku", "revision", name="uq_product_sku_revision"),)

    sku: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    item_type: Mapped[str] = mapped_column(String(30), default="product", index=True, nullable=False)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    supplier: Mapped[str | None] = mapped_column(String(200), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="each", nullable=False)
    pack_size: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"), nullable=False)
    minimum_order_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("1"), nullable=False
    )
    base_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_treatment: Mapped[str] = mapped_column(String(30), default="exclusive", nullable=False)
    waste_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"), nullable=False)
    default_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    regional_pricing: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_reference: Mapped[str | None] = mapped_column(Text)
    supporting_attachment_id: Mapped[str | None] = mapped_column(String(36))
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"))


class LabourComponent(RecordMixin, Base):
    __tablename__ = "labour_components"
    __table_args__ = (UniqueConstraint("code", "revision", name="uq_labour_code_revision"),)

    code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    trade_or_grade: Mapped[str | None] = mapped_column(String(150), index=True)
    category: Mapped[str | None] = mapped_column(String(150), index=True)
    unit: Mapped[str] = mapped_column(String(30), default="person_hour", nullable=False)
    base_rate: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    default_hours: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"), nullable=False)
    crew_size: Mapped[Decimal] = mapped_column(Numeric(9, 3), default=Decimal("1"), nullable=False)
    default_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    productivity_source: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("labour_components.id"))


class PricingLibraryRecord(RecordMixin, Base):
    __tablename__ = "pricing_library_records"

    pkb_entry_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entry_version: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    system_description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(100), default="each", nullable=False)
    rate_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    direct_labour_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    direct_material_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    material_markup: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_basis: Mapped[str] = mapped_column(String(50), default="GST Exclusive", nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(200), index=True)
    service_class: Mapped[str | None] = mapped_column(String(200), index=True)
    service_material: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_plane: Mapped[str | None] = mapped_column(String(100), index=True)
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    repair_family: Mapped[str | None] = mapped_column(String(300), index=True)
    rate_inclusions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    rate_exclusions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    applicability: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    commercial_confidence: Mapped[str | None] = mapped_column(String(100))
    technical_status: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_library_records.id"))

    __table_args__ = (
        UniqueConstraint("pkb_entry_id", "entry_version", "release_id", name="uq_pkb_entry_release"),
        Index("ix_pricing_search", "service_type", "service_material", "substrate", "frl"),
    )


class StoredFile(RecordMixin, Base):
    __tablename__ = "stored_files"

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str | None] = mapped_column(String(200))
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    purpose: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    malware_scan_status: Mapped[str] = mapped_column(String(30), default="not_configured")
    uploaded_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TechnicalDocument(RecordMixin, Base):
    __tablename__ = "technical_documents"

    document_id: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    source_file_id: Mapped[str] = mapped_column(ForeignKey("stored_files.id"), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    revision: Mapped[str | None] = mapped_column(String(100))
    document_date: Mapped[date | None] = mapped_column(Date)
    document_type: Mapped[str | None] = mapped_column(String(100), index=True)
    authority_status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extraction_status: Mapped[str] = mapped_column(String(50), default="not_started")
    extracted_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)


class TechnicalVariant(RecordMixin, Base):
    __tablename__ = "technical_variants"

    variant_id: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    system_id: Mapped[str | None] = mapped_column(String(200), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    service_type: Mapped[str | None] = mapped_column(String(200), index=True)
    service_material: Mapped[str | None] = mapped_column(String(200), index=True)
    service_size_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    service_size_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    insulation_type: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_type: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_thickness_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    substrate_thickness_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    opening_shape: Mapped[str | None] = mapped_column(String(100), index=True)
    opening_width_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    opening_height_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    annular_gap_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    annular_gap_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    spacing_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    component_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    installation_requirements: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    limitations: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_refs: Mapped[list[str] | None] = mapped_column(JSON)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    expert_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("technical_variants.id"))

    source_document: Mapped[TechnicalDocument | None] = relationship("TechnicalDocument")


class Project(RecordMixin, Base):
    __tablename__ = "projects"

    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    customer: Mapped[str | None] = mapped_column(String(300))
    site_address: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str | None] = mapped_column(String(200))
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_name: Mapped[str] = mapped_column(String(50), default="GST", nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0.10"), nullable=False)
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True, nullable=False)


class Estimate(RecordMixin, Base):
    __tablename__ = "estimates"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reference: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AUD", nullable=False)
    tax_name: Mapped[str] = mapped_column(String(50), default="GST", nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0.10"), nullable=False)
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    pricing_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    technical_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    rules_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    products_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    labour_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    markups_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    formula_release_id: Mapped[str | None] = mapped_column(String(36), index=True)
    brand_release_id: Mapped[str | None] = mapped_column(String(36), index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text)

    project: Mapped[Project] = relationship("Project")
    openings: Mapped[list[Opening]] = relationship("Opening", back_populates="estimate", cascade="all, delete-orphan")
    lines: Mapped[list[EstimateLine]] = relationship("EstimateLine", back_populates="estimate", cascade="all, delete-orphan")


class Opening(RecordMixin, Base):
    __tablename__ = "openings"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_code: Mapped[str | None] = mapped_column(String(100), index=True)
    location: Mapped[str | None] = mapped_column(Text)
    substrate_type: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_plane: Mapped[str | None] = mapped_column(String(100), index=True)
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    opening_type: Mapped[str | None] = mapped_column(String(100), index=True)
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    depth_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    access_condition: Mapped[str | None] = mapped_column(String(100))
    complexity: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_links: Mapped[list[str] | None] = mapped_column(JSON)

    estimate: Mapped[Estimate] = relationship("Estimate", back_populates="openings")
    services: Mapped[list[Service]] = relationship("Service", back_populates="opening", cascade="all, delete-orphan")


class Service(RecordMixin, Base):
    __tablename__ = "services"

    opening_id: Mapped[str] = mapped_column(ForeignKey("openings.id"), index=True, nullable=False)
    service_code: Mapped[str | None] = mapped_column(String(100), index=True)
    service_type: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    material: Mapped[str | None] = mapped_column(String(200), index=True)
    nominal_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    outside_diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    insulation_type: Mapped[str | None] = mapped_column(String(200))
    insulation_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_links: Mapped[list[str] | None] = mapped_column(JSON)

    opening: Mapped[Opening] = relationship("Opening", back_populates="services")


class EstimateLine(RecordMixin, Base):
    __tablename__ = "estimate_lines"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), index=True)
    labour_component_id: Mapped[str | None] = mapped_column(ForeignKey("labour_components.id"), index=True)
    source_rate_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_library_records.id"), index=True)
    source_system_id: Mapped[str | None] = mapped_column(ForeignKey("technical_variants.id"), index=True)
    base_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    markup_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"), nullable=False)
    unit_sell: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"), nullable=False)
    pricing_method: Mapped[str | None] = mapped_column(String(100))
    confidence: Mapped[str | None] = mapped_column(String(50))
    source_reference: Mapped[str | None] = mapped_column(Text)
    assumptions: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    exclusion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provisional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    estimate: Mapped[Estimate] = relationship("Estimate", back_populates="lines")


class Approval(RecordMixin, Base):
    __tablename__ = "approvals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    approval_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), index=True)


class ChangeProposal(RecordMixin, Base):
    __tablename__ = "change_proposals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    proposed_change: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    proposed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_notes: Mapped[str | None] = mapped_column(Text)


class BackgroundJob(RecordMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(200))
    last_error: Mapped[str | None] = mapped_column(Text)


class RuleRecord(RecordMixin, Base):
    __tablename__ = "rule_records"

    rule_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    action: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="warning", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True, nullable=False)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_reference: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("rule_records.id"))

    __table_args__ = (UniqueConstraint("rule_code", "revision", name="uq_rule_code_revision"),)


class RuleEvaluation(RecordMixin, Base):
    __tablename__ = "rule_evaluations"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("rule_records.id"))
    rule_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class AuditTrail(RecordMixin, Base):
    __tablename__ = "audit_trails"

    project_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    event_ids: Mapped[list[str] | None] = mapped_column(JSON)
    source_receipt_ids: Mapped[list[str] | None] = mapped_column(JSON)
    validation_receipt_ids: Mapped[list[str] | None] = mapped_column(JSON)
    summary_hash: Mapped[str | None] = mapped_column(String(64))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
