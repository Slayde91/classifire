from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _new_id() -> str:
    return str(uuid.uuid4())


def _now_utc() -> datetime:
    return datetime.now(UTC)


class PhysicalRecordMixin:
    """Shared immutable-identification fields for physical-model records."""

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
    record_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class Defect(PhysicalRecordMixin, Base):
    """Canonical physical defect, kept separate from a legacy opening identifier."""

    __tablename__ = "defects"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    external_defect_id: Mapped[str | None] = mapped_column(String(150), index=True)
    defect_code: Mapped[str | None] = mapped_column(String(150), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(100), index=True)
    evidence_status: Mapped[str] = mapped_column(
        String(30), default="provisional", index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True, nullable=False)
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    __table_args__ = (
        UniqueConstraint("estimate_id", "external_defect_id", name="uq_defect_estimate_external"),
    )


class EvidenceSource(PhysicalRecordMixin, Base):
    """Evidence provenance used to establish a physical model."""

    __tablename__ = "evidence_sources"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    defect_id: Mapped[str | None] = mapped_column(ForeignKey("defects.id"), index=True)
    stored_file_id: Mapped[str | None] = mapped_column(ForeignKey("stored_files.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[str | None] = mapped_column(String(100))
    region_reference: Mapped[str | None] = mapped_column(String(300))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    evidence_class: Mapped[str] = mapped_column(
        String(50), default="observed", index=True, nullable=False
    )
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    status: Mapped[str] = mapped_column(String(30), default="active", index=True, nullable=False)
    source_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class ServiceOpeningLink(PhysicalRecordMixin, Base):
    """Many-to-many physical relationship between a service and an opening."""

    __tablename__ = "service_opening_links"

    service_id: Mapped[str] = mapped_column(ForeignKey("services.id"), index=True, nullable=False)
    opening_id: Mapped[str] = mapped_column(ForeignKey("openings.id"), index=True, nullable=False)
    link_type: Mapped[str] = mapped_column(String(50), default="penetrates", nullable=False)
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


class PhysicalModelLock(PhysicalRecordMixin, Base):
    """Immutable physical-model lock metadata; lock/reopen policy lives in services."""

    __tablename__ = "physical_model_locks"

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    defect_ids: Mapped[list[str] | None] = mapped_column(JSON)
    evidence_hashes: Mapped[list[str] | None] = mapped_column(JSON)
    service_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    opening_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    service_count_status: Mapped[str | None] = mapped_column(String(50))
    material_hypothesis_status: Mapped[str | None] = mapped_column(String(50))
    critical_unknowns: Mapped[list[str] | None] = mapped_column(JSON)
    validator_result: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    permitted_classes: Mapped[list[str] | None] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    signature: Mapped[str | None] = mapped_column(Text)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_physical_model_locks_active_estimate",
            "estimate_id",
            unique=True,
            sqlite_where=text("invalidated_at IS NULL"),
            postgresql_where=text("invalidated_at IS NULL"),
        ),
    )


class PhysicalModelAdmission(PhysicalRecordMixin, Base):
    """An externally signed, one-time admission recorded before any submission.

    Layer 4 records this evidence only.  It does not create an initial physical
    model and does not represent a Physical Model Lock.
    """

    __tablename__ = "physical_model_admissions"

    admission_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    preflight_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalised_submission_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    normalised_submission_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    protected_state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    protected_state_fingerprint_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    adjudicated_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    artifact_digests: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    policy_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    admission_envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    admission_envelope_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issuer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default="issued", index=True, nullable=False)

    __table_args__ = (Index("ix_physical_model_admission_estimate_state", "estimate_id", "state"),)


class PhysicalModelSubmissionReceipt(Base):
    """Immutable proof of one successful admission-bound canonical write."""

    __tablename__ = "physical_model_submission_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    admission_record_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_admissions.id"), unique=True, index=True, nullable=False
    )
    admission_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    normalised_submission_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    protected_state_fingerprint_before: Mapped[str] = mapped_column(String(64), nullable=False)
    opening_count: Mapped[int] = mapped_column(Integer, nullable=False)
    service_count: Mapped[int] = mapped_column(Integer, nullable=False)
    service_opening_link_count: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_write_performed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    physical_model_lock_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)


class VisualValidationReceipt(Base):
    """Immutable semantic-review evidence for a future Physical Model Lock.

    Recording this evidence is deliberately separate from canonical submission,
    admission consumption, and Physical Model Lock creation. A later signed lock
    boundary must revalidate every stored binding before it can rely on a receipt.
    """

    __tablename__ = "visual_validation_receipts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    receipt_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    source_run_id: Mapped[str] = mapped_column(String(160), nullable=False)
    candidate_submission_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    controller_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_family_inventory_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_family_review_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    human_review_request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    human_review_response_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    unresolved_items: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    implementation_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)

    __table_args__ = (
        Index("ix_visual_validation_receipt_estimate_status", "estimate_id", "status"),
    )


class PhysicalModelLockAmendmentAdmission(Base):
    """Immutable journal record for a verified signed lock-amendment candidate.

    Recording an amendment admission is deliberately not amendment execution:
    it cannot invalidate a Physical Model Lock, change canonical physical rows,
    create a replacement lock, or confer downstream authority. A later writer
    must have its own separately authorised, transactional design.
    """

    __tablename__ = "physical_model_lock_amendment_admissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    amendment_admission_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    target_lock_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_locks.id"), index=True, nullable=False
    )
    target_lock_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_lock_signature_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    current_physical_model_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amendment_submission_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    amendment_submission_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    visual_validation_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    amendment_reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    amendment_envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    amendment_envelope_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    issuer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    preflight_receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    preflight_receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    __table_args__ = (
        Index(
            "ix_physical_model_lock_amendment_admission_estimate_created",
            "estimate_id",
            "created_at",
        ),
    )


class PhysicalModelLockAmendmentOutcome(Base):
    """Immutable proof of one admission-bound signed lock amendment."""

    __tablename__ = "physical_model_lock_amendment_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    admission_record_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_lock_amendment_admissions.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    amendment_admission_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    target_lock_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_locks.id"), unique=True, index=True, nullable=False
    )
    target_lock_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amendment_envelope_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    amendment_submission_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pre_physical_model_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    pre_physical_model_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    post_physical_model_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    post_physical_model_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_identity_map_json: Mapped[str] = mapped_column(Text, nullable=False)
    row_identity_map_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    executed_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    physical_model_lock_invalidated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    replacement_lock_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    downstream_authority_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    execution_receipt_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )


class PhysicalModelLockReplacementAdmission(Base):
    """Immutable journal record for one verified replacement-lock approval.

    This record preserves eligibility evidence only. It cannot create a
    Physical Model Lock or grant any downstream authority.
    """

    __tablename__ = "physical_model_lock_replacement_admissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    replacement_lock_admission_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    amendment_outcome_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_lock_amendment_outcomes.id"),
        index=True,
        nullable=False,
    )
    amendment_admission_id: Mapped[str] = mapped_column(String(36), nullable=False)
    amendment_envelope_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    amendment_execution_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    visual_validation_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    superseded_lock_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_locks.id"), index=True, nullable=False
    )
    superseded_lock_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    replacement_lock_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    replacement_lock_reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    replacement_lock_envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    replacement_lock_envelope_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    issuer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signing_key_id: Mapped[str] = mapped_column(String(200), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(80), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    preflight_receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    preflight_receipt_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    __table_args__ = (
        Index(
            "ix_physical_model_lock_replacement_admission_estimate_created",
            "estimate_id",
            "created_at",
        ),
    )


class PhysicalModelLockReplacementOutcome(Base):
    """Immutable proof that one signed admission created one replacement lock."""

    __tablename__ = "physical_model_lock_replacement_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, nullable=False
    )
    admission_record_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_lock_replacement_admissions.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    replacement_lock_admission_id: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    amendment_outcome_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_lock_amendment_outcomes.id"),
        unique=True,
        index=True,
        nullable=False,
    )
    superseded_lock_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_locks.id"), unique=True, index=True, nullable=False
    )
    replacement_lock_id: Mapped[str] = mapped_column(
        ForeignKey("physical_model_locks.id"), unique=True, index=True, nullable=False
    )
    replacement_lock_content_hash: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    replacement_lock_envelope_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False
    )
    preflight_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    physical_model_lock_created: Mapped[bool] = mapped_column(Boolean, nullable=False)
    downstream_authority_granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    execution_receipt_json: Mapped[str] = mapped_column(Text, nullable=False)
    execution_receipt_sha256: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
