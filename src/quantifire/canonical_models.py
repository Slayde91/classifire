from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
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
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class CanonicalV213RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
    record_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Defect(CanonicalV213RecordMixin, Base):
    """Canonical defect entity from QUANTIFIRE v2.13 Package 02."""

    __tablename__ = "defects"

    estimate_id: Mapped[str] = mapped_column(
        ForeignKey("estimates.id"), index=True, nullable=False
    )
    external_defect_id: Mapped[str | None] = mapped_column(String(150), index=True)
    defect_code: Mapped[str | None] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(100), index=True)
    evidence_status: Mapped[str] = mapped_column(
        String(30), default="provisional", index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="draft", index=True, nullable=False
    )
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "estimate_id", "external_defect_id", name="uq_defect_estimate_external"
        ),
    )


class EvidenceSource(CanonicalV213RecordMixin, Base):
    """Evidence provenance remains independent of conclusions and commercial records."""

    __tablename__ = "evidence_sources"

    estimate_id: Mapped[str] = mapped_column(
        ForeignKey("estimates.id"), index=True, nullable=False
    )
    defect_id: Mapped[str | None] = mapped_column(
        ForeignKey("defects.id"), index=True
    )
    stored_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("stored_files.id"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[str | None] = mapped_column(String(100))
    region_reference: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    evidence_class: Mapped[str] = mapped_column(
        String(50), default="observed", index=True, nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(
        String(30), default="active", index=True, nullable=False
    )
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ServiceOpeningLink(CanonicalV213RecordMixin, Base):
    """Many-to-many physical relation between canonical Services and Openings."""

    __tablename__ = "service_opening_links"

    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id"), index=True, nullable=False
    )
    opening_id: Mapped[str] = mapped_column(
        ForeignKey("openings.id"), index=True, nullable=False
    )
    link_type: Mapped[str] = mapped_column(
        String(50), default="penetrates", nullable=False
    )
    relationship_status: Mapped[str] = mapped_column(
        String(30), default="confirmed", index=True, nullable=False
    )
    evidence_status: Mapped[str] = mapped_column(
        String(30), default="provisional", index=True, nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    source_reference: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("service_id", "opening_id", name="uq_service_opening_link"),
        Index("ix_service_opening_pair", "opening_id", "service_id"),
    )


class ServiceMaterialHypothesis(CanonicalV213RecordMixin, Base):
    __tablename__ = "service_material_hypotheses"

    service_id: Mapped[str] = mapped_column(
        ForeignKey("services.id"), index=True, nullable=False
    )
    material: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    evidence_status: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence_ids: Mapped[list[str] | None] = mapped_column(JSON)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    technical_consequence: Mapped[str | None] = mapped_column(Text)
    pricing_consequence: Mapped[str | None] = mapped_column(Text)
    final_status: Mapped[str] = mapped_column(
        String(50), default="provisional", index=True, nullable=False
    )


class PhysicalModelLock(CanonicalV213RecordMixin, Base):
    __tablename__ = "physical_model_locks"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    estimate_id: Mapped[str | None] = mapped_column(
        ForeignKey("estimates.id"), index=True
    )
    defect_ids: Mapped[list[str] | None] = mapped_column(JSON)
    evidence_hashes: Mapped[list[str] | None] = mapped_column(JSON)
    service_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    opening_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    service_count_status: Mapped[str | None] = mapped_column(String(50))
    material_hypothesis_status: Mapped[str | None] = mapped_column(String(50))
    critical_unknowns: Mapped[list[str] | None] = mapped_column(JSON)
    validator_result: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    permitted_classes: Mapped[list[str] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    signature: Mapped[str | None] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)


class RepairStrategy(CanonicalV213RecordMixin, Base):
    __tablename__ = "repair_strategies"

    opening_id: Mapped[str] = mapped_column(
        ForeignKey("openings.id"), index=True, nullable=False
    )
    physical_model_lock_id: Mapped[str | None] = mapped_column(
        ForeignKey("physical_model_locks.id"), index=True
    )
    candidate_id: Mapped[str | None] = mapped_column(String(300), index=True)
    selected_technical_variant_id: Mapped[str | None] = mapped_column(
        ForeignKey("technical_variants.id"), index=True
    )
    package15_release_id: Mapped[str | None] = mapped_column(
        ForeignKey("library_releases.id"), index=True
    )
    match_classification: Mapped[str | None] = mapped_column(String(100), index=True)
    treatment_description: Mapped[str | None] = mapped_column(Text)
    technical_basis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    assumptions: Mapped[list[str] | None] = mapped_column(JSON)
    limitations: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(30), default="draft", index=True, nullable=False
    )


class Package15CandidateRequirement(CanonicalV213RecordMixin, Base):
    __tablename__ = "package15_candidate_requirements"

    opening_id: Mapped[str | None] = mapped_column(
        ForeignKey("openings.id"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    source_field: Mapped[str | None] = mapped_column(String(300))
    source_document_id: Mapped[str | None] = mapped_column(String(300), index=True)
    source_page: Mapped[str | None] = mapped_column(String(100))
    source_row: Mapped[str | None] = mapped_column(String(150))
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    exclusion: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SystemRequiredComponent(CanonicalV213RecordMixin, Base):
    __tablename__ = "system_required_components"

    opening_id: Mapped[str] = mapped_column(
        ForeignKey("openings.id"), index=True, nullable=False
    )
    service_id: Mapped[str | None] = mapped_column(
        ForeignKey("services.id"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    technical_requirement_id: Mapped[str | None] = mapped_column(String(300), index=True)
    quantity_formula_id: Mapped[str | None] = mapped_column(String(300), index=True)
    required_labour_activity_ids: Mapped[list[str] | None] = mapped_column(JSON)
    candidate_status: Mapped[str | None] = mapped_column(String(100), index=True)
    mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RepairStrategyLock(CanonicalV213RecordMixin, Base):
    __tablename__ = "repair_strategy_locks"

    opening_id: Mapped[str] = mapped_column(
        ForeignKey("openings.id"), index=True, nullable=False
    )
    repair_strategy_id: Mapped[str | None] = mapped_column(
        ForeignKey("repair_strategies.id"), index=True
    )
    candidate_id: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(100), nullable=False)
    required_component_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dependencies: Mapped[list[str] | None] = mapped_column(JSON)
    mismatches: Mapped[list[str] | None] = mapped_column(JSON)
    assumptions: Mapped[list[str] | None] = mapped_column(JSON)
    validator_result: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    permitted_classes: Mapped[list[str] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    signature: Mapped[str | None] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
