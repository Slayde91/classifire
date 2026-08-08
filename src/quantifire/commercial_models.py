from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .canonical_models import CanonicalV213RecordMixin
from .db import Base


class Quantity(CanonicalV213RecordMixin, Base):
    """Canonical QUANTIFIRE v2.13 Quantity (Package 02, Chapter 99)."""

    __tablename__ = "quantities"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    required_component_id: Mapped[str | None] = mapped_column(
        ForeignKey("system_required_components.id"), index=True
    )
    quantity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(100))
    purpose: Mapped[str | None] = mapped_column(Text)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    range_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    range_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    unit_basis: Mapped[str] = mapped_column(String(80), nullable=False)
    source_method: Mapped[str | None] = mapped_column(String(150))
    formula_id: Mapped[str | None] = mapped_column(String(300))
    precision_digits: Mapped[int | None] = mapped_column()
    rounding_method: Mapped[str | None] = mapped_column(String(80))
    waste_factor: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    conversion_factor: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    epistemic_type: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[str | None] = mapped_column(String(80))
    risk_status: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class QuantityFormulaInput(CanonicalV213RecordMixin, Base):
    """Package 18 QuantityFormulaInput runtime contract."""

    __tablename__ = "quantity_formula_inputs"

    quantity_record_id: Mapped[str] = mapped_column(ForeignKey("quantities.id"), index=True, nullable=False)
    input_name: Mapped[str] = mapped_column(String(200), nullable=False)
    input_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_class: Mapped[str | None] = mapped_column(String(80))
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    assumption_id: Mapped[str | None] = mapped_column(String(100))
    validator_status: Mapped[str] = mapped_column(String(30), nullable=False)


class ProductivitySource(CanonicalV213RecordMixin, Base):
    """Package 18 ProductivitySource runtime contract."""

    __tablename__ = "productivity_sources"

    activity: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(80), nullable=False)
    base_hours_per_unit: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(100))
    source_quantity: Mapped[str | None] = mapped_column(String(200))
    source_crew: Mapped[str | None] = mapped_column(String(200))
    source_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    decomposition_formula: Mapped[str | None] = mapped_column(Text)
    adjustment_formula: Mapped[str | None] = mapped_column(Text)
    executable_formula_id: Mapped[str] = mapped_column(String(300), nullable=False)
    evidence_class: Mapped[str | None] = mapped_column(String(80))
    confidence: Mapped[str | None] = mapped_column(String(80))
    approval_status: Mapped[str | None] = mapped_column(String(80))


class LabourActivity(CanonicalV213RecordMixin, Base):
    """Canonical QUANTIFIRE v2.13 Labour Activity (Package 02, Chapter 101)."""

    __tablename__ = "labour_activities"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    required_component_id: Mapped[str | None] = mapped_column(
        ForeignKey("system_required_components.id"), index=True
    )
    productivity_source_id: Mapped[str | None] = mapped_column(ForeignKey("productivity_sources.id"))
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    activity_name: Mapped[str] = mapped_column(String(300), nullable=False)
    scope_output: Mapped[str | None] = mapped_column(Text)
    trade_or_grade: Mapped[str | None] = mapped_column(String(150))
    competence: Mapped[str | None] = mapped_column(String(200))
    crew_size: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    labour_quantity_hours: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    working_conditions: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    rate_source: Mapped[str | None] = mapped_column(String(300))
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    extended_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    included_tools_and_incidentals: Mapped[list[str] | dict[str, Any] | None] = mapped_column(JSON)
    confidence: Mapped[str | None] = mapped_column(String(80))
    risk_status: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class PricingComponent(CanonicalV213RecordMixin, Base):
    """Canonical QUANTIFIRE v2.13 Pricing Component (Package 02, Chapter 98)."""

    __tablename__ = "pricing_components"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"))
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"))
    required_component_id: Mapped[str | None] = mapped_column(
        ForeignKey("system_required_components.id"), index=True
    )
    parent_estimate_line_id: Mapped[str | None] = mapped_column(ForeignKey("estimate_lines.id"))
    quantity_id: Mapped[str | None] = mapped_column(ForeignKey("quantities.id"))
    component_type: Mapped[str] = mapped_column(String(100), nullable=False)
    scope_description: Mapped[str] = mapped_column(Text, nullable=False)
    unit_basis: Mapped[str | None] = mapped_column(String(80))
    rate_source: Mapped[str | None] = mapped_column(String(300))
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    extended_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    inclusions: Mapped[list[str] | dict[str, Any] | None] = mapped_column(JSON)
    exclusions: Mapped[list[str] | dict[str, Any] | None] = mapped_column(JSON)
    confidence: Mapped[str | None] = mapped_column(String(80))
    risk_status: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(50), default="draft", nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CommercialMethodLock(CanonicalV213RecordMixin, Base):
    """Package 18 CommercialMethodLock runtime contract."""

    __tablename__ = "commercial_method_locks"

    component_id: Mapped[str] = mapped_column(ForeignKey("pricing_components.id"), index=True, nullable=False)
    library_search_completed: Mapped[bool | None] = mapped_column(Boolean)
    exact_library_match_found: Mapped[bool | None] = mapped_column(Boolean)
    parameterised_rate_found: Mapped[bool | None] = mapped_column(Boolean)
    component_build_completed: Mapped[bool | None] = mapped_column(Boolean)
    expert_estimate_required: Mapped[bool | None] = mapped_column(Boolean)
    selected_pricing_method: Mapped[str] = mapped_column(String(100), nullable=False)
    rejected_rate_candidates: Mapped[list[Any] | None] = mapped_column(JSON)
    package15_basis: Mapped[str | None] = mapped_column(String(300))
    rate_applicability_result: Mapped[str | None] = mapped_column(String(100))
    quantity_formula_result: Mapped[str | None] = mapped_column(String(100))
    labour_build_result: Mapped[str | None] = mapped_column(String(100))
    recovery_status: Mapped[str | None] = mapped_column(String(150))
    provisional_status: Mapped[str | None] = mapped_column(String(100))
    anomaly_result: Mapped[str | None] = mapped_column(String(150))
    validator_outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)


class CommercialRecoveryRecord(CanonicalV213RecordMixin, Base):
    """Package 18 CommercialRecoveryRecord runtime contract."""

    __tablename__ = "commercial_recovery_records"

    component_id: Mapped[str] = mapped_column(ForeignKey("pricing_components.id"), index=True, nullable=False)
    pricing_line_id: Mapped[str | None] = mapped_column(ForeignKey("estimate_lines.id"))
    recovery_status: Mapped[str] = mapped_column(String(180), nullable=False)
    economic_activity_key: Mapped[str | None] = mapped_column(String(200))
    shared_component_key: Mapped[str | None] = mapped_column(String(200), index=True)
    recovery_location: Mapped[str | None] = mapped_column(String(300))
    allocated_amount_aud_ex_gst: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    provenance: Mapped[str | None] = mapped_column(Text)
    proof_record_id: Mapped[str | None] = mapped_column(String(200))


class ComponentRequirementReconciliation(CanonicalV213RecordMixin, Base):
    """Package 18 reconciliation between required, generated, quantified and recovered scope."""

    __tablename__ = "component_requirement_reconciliations"

    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"))
    required_component_id: Mapped[str] = mapped_column(
        ForeignKey("system_required_components.id"), index=True, nullable=False
    )
    generated_component_id: Mapped[str | None] = mapped_column(ForeignKey("pricing_components.id"))
    quantity_record_id: Mapped[str | None] = mapped_column(ForeignKey("quantities.id"))
    pricing_line_id: Mapped[str | None] = mapped_column(ForeignKey("estimate_lines.id"))
    labour_activity_ids: Mapped[list[str] | None] = mapped_column(JSON)
    recovery_status: Mapped[str | None] = mapped_column(String(180))
    missing_status: Mapped[str | None] = mapped_column(String(180))
    assumption_ids: Mapped[list[str] | None] = mapped_column(JSON)
    technical_consequence: Mapped[str | None] = mapped_column(Text)
    commercial_consequence: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(120), nullable=False)


class PriceAnomalyReview(CanonicalV213RecordMixin, Base):
    """Package 18 duplicate/suspicious price anomaly review."""

    __tablename__ = "price_anomaly_reviews"

    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("estimates.id"), index=True)
    comparison_type: Mapped[str] = mapped_column(String(120), nullable=False)
    subject_ids: Mapped[list[str] | None] = mapped_column(JSON)
    canonical_signatures: Mapped[list[str] | None] = mapped_column(JSON)
    prices: Mapped[list[Any] | None] = mapped_column(JSON)
    physical_differences: Mapped[list[Any] | None] = mapped_column(JSON)
    documented_fixed_reason: Mapped[str | None] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(180), nullable=False)
    required_action: Mapped[str | None] = mapped_column(Text)


class GateEvidence(CanonicalV213RecordMixin, Base):
    """Package 18 validator gate-evidence contract."""

    __tablename__ = "gate_evidence"

    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("estimates.id"), index=True)
    gate_type: Mapped[str] = mapped_column(String(150), index=True, nullable=False)
    validator_id: Mapped[str] = mapped_column(String(200), nullable=False)
    validator_version: Mapped[str | None] = mapped_column(String(100))
    input_record_count: Mapped[Decimal | None] = mapped_column(Numeric(18, 0))
    exception_count: Mapped[Decimal | None] = mapped_column(Numeric(18, 0))
    signed_validator_json_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[str] = mapped_column(String(100), nullable=False)
    required_action: Mapped[str | None] = mapped_column(Text)
    input_table_hashes: Mapped[list[str] | None] = mapped_column(JSON)
    run_id: Mapped[str | None] = mapped_column(String(200))
    validation_timestamp: Mapped[str | None] = mapped_column(String(100))


class EstimateCertificate(CanonicalV213RecordMixin, Base):
    """Package 18 tamper-evident estimate certificate contract."""

    __tablename__ = "estimate_certificates"

    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("estimates.id"), index=True)
    quantifire_version: Mapped[str] = mapped_column(String(100), nullable=False)
    active_manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    governed_table_hashes: Mapped[dict[str, str] | None] = mapped_column(JSON)
    gate_evidence_hash: Mapped[str | None] = mapped_column(String(64))
    workbook_structure_hash: Mapped[str | None] = mapped_column(String(64))
    proposal_reconciliation_result_hash: Mapped[str | None] = mapped_column(String(64))
    proposal_commercial_validity_result_hash: Mapped[str | None] = mapped_column(String(64))
    validator_identity: Mapped[str | None] = mapped_column(String(300))
    certificate_schema_version: Mapped[str | None] = mapped_column(String(100))
    final_certificate_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text)


class AuditTrail(CanonicalV213RecordMixin, Base):
    """Package 02 Chapter 147 Audit Trail identity; AuditEvent remains the append-only event row."""

    __tablename__ = "audit_trails"

    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"), index=True)
    estimate_id: Mapped[str | None] = mapped_column(ForeignKey("estimates.id"), index=True)
    trail_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(100))
    subject_version: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    security_classification: Mapped[str | None] = mapped_column(String(80))
    retention_status: Mapped[str | None] = mapped_column(String(80))
    integrity_proof: Mapped[str | None] = mapped_column(String(128))
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
