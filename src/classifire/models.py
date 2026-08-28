from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return str(uuid.uuid4())


def now_utc() -> datetime:
    return datetime.now(UTC)


def _canonical_uuid4_check(column: str) -> str:
    without_hyphens = f"replace({column}, '-', '')"
    unsupported = without_hyphens
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return (
        f"length({column}) = 36 "
        f"AND substr({column}, 9, 1) = '-' "
        f"AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' "
        f"AND substr({column}, 24, 1) = '-' "
        f"AND substr({column}, 15, 1) = '4' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b') "
        f"AND {column} = lower({column}) "
        f"AND length({without_hyphens}) = 32 "
        f"AND length({unsupported}) = 0"
    )


def _canonical_sha256_check(column: str) -> str:
    unsupported = column
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return f"length({column}) = 64 AND {column} = lower({column}) AND length({unsupported}) = 0"


def _technical_intake_filename_check(column: str) -> str:
    safe_characters = " AND ".join(
        f"replace({column}, '{character}', '') = {column}" for character in '<>:"/\\|?*'
    )
    return (
        f"length({column}) BETWEEN 1 AND 500 "
        f"AND {column} = trim({column}) "
        f"AND {safe_characters} "
        f"AND (lower({column}) LIKE '_%.pdf' "
        f"OR lower({column}) LIKE '_%.docx' "
        f"OR lower({column}) LIKE '_%.xlsx' "
        f"OR lower({column}) LIKE '_%.xlsb')"
    )


class RecordMixin:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, nullable=False
    )
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


class AgentServicePrincipal(RecordMixin, Base):
    """A least-privilege, non-human service identity for a CLASSIFIRE agent.

    Plaintext credentials are never stored.  The server-side scope map remains
    authoritative; the persisted scope list provides an auditable second gate.
    """

    __tablename__ = "agent_service_principals"

    agent_id: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    token_hint: Mapped[str] = mapped_column(String(16), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LibraryRelease(RecordMixin, Base):
    __tablename__ = "library_releases"
    __table_args__ = (
        UniqueConstraint("library_type", "version", name="uq_library_release_type_version"),
        Index(
            "uq_library_release_active_publication_slot",
            "active_publication_slot",
            unique=True,
        ),
    )

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
    active_publication_slot: Mapped[str | None] = mapped_column(String(50))


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
    item_type: Mapped[str] = mapped_column(
        String(30), default="product", index=True, nullable=False
    )
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
    waste_factor: Mapped[Decimal] = mapped_column(
        Numeric(9, 6), default=Decimal("0"), nullable=False
    )
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
    default_hours: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), nullable=False
    )
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
    rate_ex_tax: Mapped[Decimal] = mapped_column(
        Numeric(18, 4), default=Decimal("0"), nullable=False
    )
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
        UniqueConstraint(
            "pkb_entry_id", "entry_version", "release_id", name="uq_pkb_entry_release"
        ),
        Index("ix_pricing_search", "service_type", "service_material", "substrate", "frl"),
    )


class StoredFile(RecordMixin, Base):
    __tablename__ = "stored_files"
    __table_args__ = (
        Index(
            "uq_stored_file_extraction_source_identity",
            "id",
            "sha256",
            "size_bytes",
            unique=True,
        ),
    )

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
    __table_args__ = (
        CheckConstraint(
            "declared_source_role IS NULL OR declared_source_role IN ("
            "'primary_test', 'assessment', 'regulatory_summary', "
            "'supporting_reference', 'manufacturer_information', "
            "'administrative_notice'"
            ")",
            name="ck_technical_document_declared_source_role",
        ),
        CheckConstraint(
            "artifact_provenance_status IS NULL OR artifact_provenance_status IN ("
            "'issuer_original', 'issuer_copy', 'transformed_derivative', 'unknown'"
            ")",
            name="ck_technical_document_artifact_provenance_status",
        ),
        CheckConstraint(
            "evidence_scope IS NULL OR evidence_scope IN ("
            "'full_source', 'summary_only', 'bibliographic_only'"
            ")",
            name="ck_technical_document_evidence_scope",
        ),
        Index(
            "ix_technical_documents_declared_source_role",
            "declared_source_role",
        ),
        Index(
            "ix_technical_documents_artifact_provenance_status",
            "artifact_provenance_status",
        ),
        Index("ix_technical_documents_evidence_scope", "evidence_scope"),
        Index(
            "uq_technical_document_stored_file_binding",
            "id",
            "stored_file_id",
            unique=True,
        ),
        Index("ix_technical_documents_stored_file_id", "stored_file_id"),
    )

    document_id: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    stored_file_id: Mapped[str] = mapped_column(ForeignKey("stored_files.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    declared_source_role: Mapped[str | None] = mapped_column(String(50))
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    sponsor_organisation: Mapped[str | None] = mapped_column(String(300))
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(300), index=True)
    revision: Mapped[str | None] = mapped_column(String(100))
    issuing_organisation: Mapped[str | None] = mapped_column(String(300))
    artifact_provenance_status: Mapped[str | None] = mapped_column(String(50))
    artifact_provenance_note: Mapped[str | None] = mapped_column(Text)
    publication_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    standards: Mapped[list[str] | None] = mapped_column(JSON)
    evidence_scope: Mapped[str | None] = mapped_column(String(50))
    evidence_limitations: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    extraction_status: Mapped[str] = mapped_column(String(50), default="not_started")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    supersedes_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TechnicalDocumentRelationship(RecordMixin, Base):
    # Provenance rows are append-only; lifecycle services must never rewrite an edge.
    __tablename__ = "technical_document_relationships"
    __table_args__ = (
        CheckConstraint(
            "relationship_type IN ("
            "'revision_of', 'assessment_of', 'amendment_to', 'replaces', "
            "'retirement_notice_for', 'summary_of'"
            ")",
            name="ck_technical_document_relationship_type",
        ),
        CheckConstraint(
            "document_id <> related_document_id",
            name="ck_technical_document_relationship_not_self",
        ),
        UniqueConstraint(
            "document_id",
            "related_document_id",
            "relationship_type",
            name="uq_technical_document_relationship_edge",
        ),
        Index("ix_technical_document_relationship_document_id", "document_id"),
        Index("ix_technical_document_relationship_related_id", "related_document_id"),
        Index("ix_technical_document_relationship_type", "relationship_type"),
        Index("ix_technical_document_relationship_created_by_id", "created_by_id"),
    )

    document_id: Mapped[str] = mapped_column(ForeignKey("technical_documents.id"), nullable=False)
    related_document_id: Mapped[str] = mapped_column(
        ForeignKey("technical_documents.id"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class TechnicalIntakeDraft(RecordMixin, Base):
    """An owner-bound Draft payload pinned to exact retained technical source bytes."""

    __tablename__ = "technical_intake_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["technical_document_id", "source_stored_file_id"],
            ["technical_documents.id", "technical_documents.stored_file_id"],
            name="fk_technical_intake_draft_document_source",
        ),
        ForeignKeyConstraint(
            ["source_stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_technical_intake_draft_source_bytes",
        ),
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_draft_id",
        ),
        CheckConstraint(
            "draft_schema = 'technical-intake-draft-v1'",
            name="ck_technical_intake_draft_schema",
        ),
        CheckConstraint(
            _canonical_sha256_check("source_sha256"),
            name="ck_technical_intake_draft_source_sha256",
        ),
        CheckConstraint(
            "source_size_bytes BETWEEN 1 AND 1073741824",
            name="ck_technical_intake_draft_source_size",
        ),
        CheckConstraint(
            "status = 'draft'",
            name="ck_technical_intake_draft_status",
        ),
        CheckConstraint(
            _canonical_sha256_check("payload_sha256"),
            name="ck_technical_intake_draft_payload_sha256",
        ),
        CheckConstraint(
            "record_version >= 1",
            name="ck_technical_intake_draft_record_version",
        ),
        UniqueConstraint(
            "owner_id",
            "technical_document_id",
            "source_sha256",
            name="uq_technical_intake_draft_owner_document_source",
        ),
        Index(
            "ix_technical_intake_drafts_owner_status_updated",
            "owner_id",
            "status",
            "updated_at",
        ),
        Index(
            "ix_technical_intake_drafts_document",
            "technical_document_id",
        ),
    )

    draft_schema: Mapped[str] = mapped_column(
        String(100), default="technical-intake-draft-v1", nullable=False
    )
    technical_document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="fk_technical_intake_draft_owner"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class TechnicalIntakeBatch(RecordMixin, Base):
    """A durable, user-owned manifest for one multi-report intake request."""

    __tablename__ = "technical_intake_batches"
    __table_args__ = (
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_batch_id",
        ),
        CheckConstraint(
            "batch_schema = 'technical-intake-batch-v1'",
            name="ck_technical_intake_batch_schema",
        ),
        CheckConstraint(
            "status IN ("
            "'open', 'in_progress', 'completed', "
            "'completed_with_rejections', 'needs_attention'"
            ")",
            name="ck_technical_intake_batch_status",
        ),
        CheckConstraint(
            "expected_item_count BETWEEN 1 AND 20",
            name="ck_technical_intake_batch_item_count",
        ),
        CheckConstraint(
            _canonical_uuid4_check("client_request_id"),
            name="ck_technical_intake_batch_client_request_id",
        ),
        CheckConstraint(
            _canonical_sha256_check("manifest_sha256"),
            name="ck_technical_intake_batch_manifest_sha256",
        ),
        CheckConstraint(
            "(status IN ('completed', 'completed_with_rejections') "
            "AND completed_at IS NOT NULL) OR "
            "(status NOT IN ('completed', 'completed_with_rejections') "
            "AND completed_at IS NULL)",
            name="ck_technical_intake_batch_completion",
        ),
        UniqueConstraint(
            "created_by_id",
            "client_request_id",
            name="uq_technical_intake_batch_creator_request",
        ),
        Index(
            "ix_technical_intake_batches_creator_status_created",
            "created_by_id",
            "status",
            "created_at",
        ),
    )

    batch_schema: Mapped[str] = mapped_column(
        String(100), default="technical-intake-batch-v1", nullable=False
    )
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expected_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    items: Mapped[list[TechnicalIntakeBatchItem]] = relationship(
        back_populates="batch",
        order_by="TechnicalIntakeBatchItem.ordinal",
    )


class TechnicalIntakeBatchItem(RecordMixin, Base):
    """One claimable, idempotent file slot in a technical intake batch."""

    __tablename__ = "technical_intake_batch_items"
    __table_args__ = (
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_batch_item_id",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'accepted', 'rejected', 'needs_attention')",
            name="ck_technical_intake_batch_item_status",
        ),
        CheckConstraint(
            "ordinal BETWEEN 1 AND 20",
            name="ck_technical_intake_batch_item_ordinal",
        ),
        CheckConstraint(
            "declared_size_bytes > 0",
            name="ck_technical_intake_batch_item_size",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_intake_batch_item_attempt_count",
        ),
        CheckConstraint(
            _canonical_uuid4_check("client_item_id"),
            name="ck_technical_intake_batch_item_client_id",
        ),
        CheckConstraint(
            _technical_intake_filename_check("original_filename"),
            name="ck_technical_intake_batch_item_filename",
        ),
        CheckConstraint(
            "length(trim(declared_document_id)) BETWEEN 1 AND 200",
            name="ck_technical_intake_batch_item_document_id",
        ),
        CheckConstraint(
            "registration_schema = 'technical-source-registration-v1'",
            name="ck_technical_intake_batch_item_registration_schema",
        ),
        CheckConstraint(
            _canonical_sha256_check("registration_sha256"),
            name="ck_technical_intake_batch_item_registration_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("expected_sha256"),
            name="ck_technical_intake_batch_item_expected_sha256",
        ),
        CheckConstraint(
            "retained_file_sha256 IS NULL OR ("
            + _canonical_sha256_check("retained_file_sha256")
            + ")",
            name="ck_technical_intake_batch_item_file_sha256",
        ),
        CheckConstraint(
            "receipt_sha256 IS NULL OR (" + _canonical_sha256_check("receipt_sha256") + ")",
            name="ck_technical_intake_batch_item_receipt_sha256",
        ),
        CheckConstraint(
            "attempt_token IS NULL OR (" + _canonical_uuid4_check("attempt_token") + ")",
            name="ck_technical_intake_batch_item_attempt_token",
        ),
        CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_intake_batch_item_claim",
        ),
        CheckConstraint(
            "(status = 'pending' "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND receipt_schema IS NULL "
            "AND receipt_json IS NULL "
            "AND receipt_sha256 IS NULL) OR "
            "(status = 'processing' AND (("
            "outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND receipt_schema IS NULL "
            "AND receipt_json IS NULL "
            "AND receipt_sha256 IS NULL) OR ("
            "outcome_code IS NOT NULL "
            "AND outcome_retryable IS NOT NULL "
            "AND outcome_retryable = true "
            "AND last_outcome_at IS NOT NULL "
            "AND receipt_schema IS NOT NULL "
            "AND receipt_schema = 'technical-intake-item-receipt-v1' "
            "AND receipt_json IS NOT NULL "
            "AND receipt_sha256 IS NOT NULL))) OR "
            "(status IN ('accepted', 'rejected', 'needs_attention') "
            "AND attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_retryable IS NOT NULL "
            "AND last_outcome_at IS NOT NULL "
            "AND receipt_schema IS NOT NULL "
            "AND receipt_schema = 'technical-intake-item-receipt-v1' "
            "AND receipt_json IS NOT NULL "
            "AND receipt_sha256 IS NOT NULL)",
            name="ck_technical_intake_batch_item_outcome",
        ),
        CheckConstraint(
            "(status = 'accepted' "
            "AND technical_document_id IS NOT NULL "
            "AND retained_file_sha256 IS NOT NULL "
            "AND retained_file_sha256 = expected_sha256 "
            "AND outcome_retryable = false) OR "
            "(status = 'needs_attention' "
            "AND outcome_code IN ("
            "'MALWARE_DETECTED', 'STORED_FILE_CONTENT_COLLISION', "
            "'STORED_FILE_CONTEXT_CONFLICT', "
            "'UPLOAD_CONTENT_SIGNATURE_INVALID', 'UPLOAD_STAGED_BYTES_CHANGED'"
            ") "
            "AND technical_document_id IS NOT NULL "
            "AND retained_file_sha256 IS NOT NULL "
            "AND retained_file_sha256 = expected_sha256 "
            "AND outcome_retryable = false) OR "
            "(status <> 'accepted' "
            "AND technical_document_id IS NULL "
            "AND retained_file_sha256 IS NULL)",
            name="ck_technical_intake_batch_item_acceptance",
        ),
        CheckConstraint(
            "(status <> 'accepted' OR ("
            "outcome_code = 'ACCEPTED' "
            "AND outcome_retryable = false)) "
            "AND (status <> 'rejected' OR outcome_code <> 'ACCEPTED') "
            "AND (status <> 'needs_attention' OR outcome_retryable = false)",
            name="ck_technical_intake_batch_item_terminal_semantics",
        ),
        UniqueConstraint(
            "batch_id",
            "client_item_id",
            name="uq_technical_intake_batch_item_client_id",
        ),
        UniqueConstraint(
            "batch_id",
            "ordinal",
            name="uq_technical_intake_batch_item_ordinal",
        ),
        UniqueConstraint(
            "batch_id",
            "declared_document_id",
            name="uq_technical_intake_batch_item_document_id",
        ),
        UniqueConstraint(
            "technical_document_id",
            name="uq_technical_intake_batch_item_technical_document",
        ),
        UniqueConstraint(
            "attempt_token",
            name="uq_technical_intake_batch_item_attempt_token",
        ),
        Index(
            "ix_technical_intake_batch_items_batch_status_ordinal",
            "batch_id",
            "status",
            "ordinal",
        ),
        Index("ix_technical_intake_batch_items_status", "status"),
        Index(
            "ix_intake_items_retained_sha_status_batch",
            "retained_file_sha256",
            "status",
            "batch_id",
        ),
    )

    batch_id: Mapped[str] = mapped_column(ForeignKey("technical_intake_batches.id"), nullable=False)
    client_item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    declared_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    declared_document_id: Mapped[str] = mapped_column(String(200), nullable=False)
    registration_schema: Mapped[str] = mapped_column(
        String(100), default="technical-source-registration-v1", nullable=False
    )
    registration_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    registration_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    attempt_token: Mapped[str | None] = mapped_column(String(36))
    attempt_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    technical_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    retained_file_sha256: Mapped[str | None] = mapped_column(String(64))
    outcome_code: Mapped[str | None] = mapped_column(String(100))
    outcome_retryable: Mapped[bool | None] = mapped_column(Boolean)
    last_outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    receipt_schema: Mapped[str | None] = mapped_column(String(100))
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    receipt_sha256: Mapped[str | None] = mapped_column(String(64))

    batch: Mapped[TechnicalIntakeBatch] = relationship(back_populates="items")
    technical_document: Mapped[TechnicalDocument | None] = relationship()


class TechnicalExtractionRun(RecordMixin, Base):
    """One idempotent Draft extraction of exact retained source bytes."""

    __tablename__ = "technical_extraction_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["technical_document_id", "source_stored_file_id"],
            ["technical_documents.id", "technical_documents.stored_file_id"],
            name="fk_technical_extraction_run_document_source",
        ),
        ForeignKeyConstraint(
            ["source_stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_technical_extraction_run_source_bytes",
        ),
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_extraction_run_id",
        ),
        CheckConstraint(
            "run_schema IN ('technical-extraction-run-v1', 'technical-extraction-run-v2')",
            name="ck_technical_extraction_run_schema",
        ),
        CheckConstraint(
            _canonical_sha256_check("source_sha256"),
            name="ck_technical_extraction_run_source_sha256",
        ),
        CheckConstraint(
            "source_size_bytes BETWEEN 1 AND 1073741824",
            name="ck_technical_extraction_run_source_size",
        ),
        CheckConstraint(
            "length(extraction_policy) BETWEEN 1 AND 100 "
            "AND extraction_policy = trim(extraction_policy)",
            name="ck_technical_extraction_run_policy",
        ),
        CheckConstraint(
            _canonical_sha256_check("extraction_policy_sha256"),
            name="ck_technical_extraction_run_policy_sha256",
        ),
        CheckConstraint(
            "ocr_low_confidence_threshold BETWEEN 0 AND 100",
            name="ck_technical_extraction_run_ocr_threshold",
        ),
        CheckConstraint(
            _canonical_sha256_check("worker_image_digest"),
            name="ck_technical_extraction_run_worker_digest",
        ),
        CheckConstraint(
            "runtime_profile_sha256 IS NULL OR ("
            + _canonical_sha256_check("runtime_profile_sha256")
            + ")",
            name="ck_technical_extraction_run_runtime_profile_sha256",
        ),
        CheckConstraint(
            "runtime_attestation_sha256 IS NULL OR ("
            + _canonical_sha256_check("runtime_attestation_sha256")
            + ")",
            name="ck_technical_extraction_run_runtime_attestation_sha256",
        ),
        CheckConstraint(
            "layout_invocation_id IS NULL OR ("
            + _canonical_uuid4_check("layout_invocation_id")
            + ")",
            name="ck_technical_extraction_run_layout_invocation_id",
        ),
        CheckConstraint(
            "(run_schema = 'technical-extraction-run-v1' "
            "AND runtime_profile_sha256 IS NULL "
            "AND runtime_attestation_sha256 IS NULL "
            "AND layout_invocation_id IS NULL) OR "
            "(run_schema = 'technical-extraction-run-v2' "
            "AND runtime_profile_sha256 IS NOT NULL "
            "AND ((page_count IS NULL AND layout_invocation_id IS NULL) OR "
            "(page_count IS NOT NULL "
            "AND runtime_attestation_sha256 IS NOT NULL "
            "AND layout_invocation_id IS NOT NULL)))",
            name="ck_technical_extraction_run_runtime_provenance",
        ),
        CheckConstraint(
            "page_evidence_schema = 'technical-page-evidence-v1'",
            name="ck_technical_extraction_run_evidence_schema",
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_attention', 'failed')",
            name="ck_technical_extraction_run_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_extraction_run_attempt_count",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count BETWEEN 1 AND 500",
            name="ck_technical_extraction_run_page_count",
        ),
        CheckConstraint(
            "(page_count IS NULL "
            "AND layout_schema IS NULL "
            "AND layout_sha256 IS NULL "
            "AND layout_size_bytes IS NULL) OR "
            "(page_count BETWEEN 1 AND 500 "
            "AND layout_schema = 'technical-parser-layout-v1' "
            "AND layout_sha256 IS NOT NULL "
            "AND layout_size_bytes BETWEEN 1 AND 131072)",
            name="ck_technical_extraction_run_layout_binding",
        ),
        CheckConstraint(
            "layout_sha256 IS NULL OR (" + _canonical_sha256_check("layout_sha256") + ")",
            name="ck_technical_extraction_run_layout_sha256",
        ),
        CheckConstraint(
            "attempt_token IS NULL OR (" + _canonical_uuid4_check("attempt_token") + ")",
            name="ck_technical_extraction_run_attempt_token",
        ),
        CheckConstraint(
            "manifest_sha256 IS NULL OR (" + _canonical_sha256_check("manifest_sha256") + ")",
            name="ck_technical_extraction_run_manifest_sha256",
        ),
        CheckConstraint(
            "outcome_code IS NULL OR ("
            "length(outcome_code) BETWEEN 1 AND 100 "
            "AND outcome_code = trim(outcome_code))",
            name="ck_technical_extraction_run_outcome_code",
        ),
        CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_extraction_run_claim",
        ),
        CheckConstraint(
            "(status = 'queued' "
            "AND completed_at IS NULL "
            "AND manifest_sha256 IS NULL "
            "AND ((attempt_count = 0 "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL) OR "
            "(attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'EXTRACTION_COMPLETE', 'EXTRACTION_COMPLETE_WITH_ATTENTION'"
            ") "
            "AND outcome_retryable = true "
            "AND last_outcome_at IS NOT NULL))) OR "
            "(status = 'processing' "
            "AND completed_at IS NULL "
            "AND manifest_sha256 IS NULL "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL) OR "
            "(status = 'completed' "
            "AND completed_at IS NOT NULL "
            "AND page_count IS NOT NULL "
            "AND manifest_sha256 IS NOT NULL "
            "AND outcome_code = 'EXTRACTION_COMPLETE' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status = 'completed_with_attention' "
            "AND completed_at IS NOT NULL "
            "AND page_count IS NOT NULL "
            "AND manifest_sha256 IS NOT NULL "
            "AND outcome_code = 'EXTRACTION_COMPLETE_WITH_ATTENTION' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status = 'failed' "
            "AND completed_at IS NOT NULL "
            "AND manifest_sha256 IS NULL "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'EXTRACTION_COMPLETE', 'EXTRACTION_COMPLETE_WITH_ATTENTION'"
            ") "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0)",
            name="ck_technical_extraction_run_terminal_state",
        ),
        Index(
            "uq_technical_extraction_run_identity_v1",
            "technical_document_id",
            "source_stored_file_id",
            "source_sha256",
            "source_size_bytes",
            "extraction_policy_sha256",
            "ocr_low_confidence_threshold",
            "worker_image_digest",
            unique=True,
            sqlite_where=text("run_schema = 'technical-extraction-run-v1'"),
            postgresql_where=text("run_schema = 'technical-extraction-run-v1'"),
        ),
        Index(
            "uq_technical_extraction_run_identity_v2",
            "technical_document_id",
            "source_stored_file_id",
            "source_sha256",
            "source_size_bytes",
            "extraction_policy_sha256",
            "ocr_low_confidence_threshold",
            "worker_image_digest",
            "runtime_profile_sha256",
            unique=True,
            sqlite_where=text("run_schema = 'technical-extraction-run-v2'"),
            postgresql_where=text("run_schema = 'technical-extraction-run-v2'"),
        ),
        UniqueConstraint(
            "id",
            "runtime_profile_sha256",
            "worker_image_digest",
            "runtime_attestation_sha256",
            name="uq_technical_extraction_run_runtime_binding",
        ),
        UniqueConstraint(
            "attempt_token",
            name="uq_technical_extraction_run_attempt_token",
        ),
        UniqueConstraint(
            "id",
            "page_count",
            name="uq_technical_extraction_run_page_count_binding",
        ),
        UniqueConstraint(
            "id",
            "layout_sha256",
            name="uq_technical_extraction_run_layout_binding",
        ),
        UniqueConstraint(
            "id",
            "ocr_low_confidence_threshold",
            name="uq_technical_extraction_run_ocr_threshold_binding",
        ),
        Index(
            "ix_technical_extraction_runs_status_created",
            "status",
            "created_at",
        ),
        Index(
            "ix_technical_extraction_runs_source_sha256",
            "source_sha256",
        ),
    )

    run_schema: Mapped[str] = mapped_column(
        String(100), default="technical-extraction-run-v1", nullable=False
    )
    source_stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    technical_document_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_policy: Mapped[str] = mapped_column(String(100), nullable=False)
    extraction_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ocr_low_confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    worker_image_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_profile_sha256: Mapped[str | None] = mapped_column(String(64))
    runtime_attestation_sha256: Mapped[str | None] = mapped_column(String(64))
    page_evidence_schema: Mapped[str] = mapped_column(
        String(100), default="technical-page-evidence-v1", nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True, nullable=False)
    attempt_token: Mapped[str | None] = mapped_column(String(36))
    attempt_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    layout_schema: Mapped[str | None] = mapped_column(String(100))
    layout_sha256: Mapped[str | None] = mapped_column(String(64))
    layout_size_bytes: Mapped[int | None] = mapped_column(Integer)
    layout_invocation_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "technical_parser_invocation_receipts.invocation_id",
            name="fk_technical_extraction_run_layout_invocation",
            use_alter=True,
        )
    )
    manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    outcome_code: Mapped[str | None] = mapped_column(String(100))
    outcome_retryable: Mapped[bool | None] = mapped_column(Boolean)
    last_outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    source_stored_file: Mapped[StoredFile] = relationship(viewonly=True)
    technical_document: Mapped[TechnicalDocument] = relationship(viewonly=True)
    requested_by: Mapped[User | None] = relationship()
    artifacts: Mapped[list[TechnicalDerivedArtifact]] = relationship(
        back_populates="run",
        order_by="TechnicalDerivedArtifact.page_number, TechnicalDerivedArtifact.artifact_kind",
    )
    pages: Mapped[list[TechnicalExtractionPage]] = relationship(
        back_populates="run",
        foreign_keys="TechnicalExtractionPage.run_id",
        order_by="TechnicalExtractionPage.page_number",
        primaryjoin="TechnicalExtractionRun.id == TechnicalExtractionPage.run_id",
    )


class TechnicalParserInvocation(RecordMixin, Base):
    """Immutable reservation for one exact isolated-parser invocation."""

    __tablename__ = "technical_parser_invocations"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "run_id",
                "runtime_profile_sha256",
                "worker_image_digest",
                "runtime_attestation_sha256",
            ],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.runtime_profile_sha256",
                "technical_extraction_runs.worker_image_digest",
                "technical_extraction_runs.runtime_attestation_sha256",
            ],
            name="fk_technical_parser_invocation_run_runtime",
        ),
        ForeignKeyConstraint(
            ["page_id", "run_id", "page_number"],
            [
                "technical_extraction_pages.id",
                "technical_extraction_pages.run_id",
                "technical_extraction_pages.page_number",
            ],
            name="fk_technical_parser_invocation_page",
            use_alter=True,
        ),
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_parser_invocation_id",
        ),
        CheckConstraint(
            "invocation_schema = 'technical-parser-invocation-v1'",
            name="ck_technical_parser_invocation_schema",
        ),
        CheckConstraint(
            _canonical_uuid4_check("run_attempt_token"),
            name="ck_technical_parser_invocation_run_attempt_token",
        ),
        CheckConstraint(
            "run_attempt_count > 0",
            name="ck_technical_parser_invocation_run_attempt_count",
        ),
        CheckConstraint(
            _canonical_uuid4_check("attempt_token"),
            name="ck_technical_parser_invocation_attempt_token",
        ),
        CheckConstraint(
            "attempt_count > 0",
            name="ck_technical_parser_invocation_attempt_count",
        ),
        CheckConstraint(
            "page_id IS NULL OR (" + _canonical_uuid4_check("page_id") + ")",
            name="ck_technical_parser_invocation_page_id",
        ),
        CheckConstraint(
            "page_attempt_token IS NULL OR (" + _canonical_uuid4_check("page_attempt_token") + ")",
            name="ck_technical_parser_invocation_page_attempt_token",
        ),
        CheckConstraint(
            "(operation = 'layout' "
            "AND page_number = 0 "
            "AND page_id IS NULL "
            "AND page_attempt_token IS NULL "
            "AND page_attempt_count IS NULL "
            "AND attempt_token = run_attempt_token "
            "AND attempt_count = run_attempt_count) OR "
            "(operation = 'page' "
            "AND page_number BETWEEN 1 AND 500 "
            "AND page_id IS NOT NULL "
            "AND page_attempt_token IS NOT NULL "
            "AND page_attempt_count > 0 "
            "AND attempt_token = page_attempt_token "
            "AND attempt_count = page_attempt_count)",
            name="ck_technical_parser_invocation_operation",
        ),
        CheckConstraint(
            _canonical_sha256_check("request_sha256"),
            name="ck_technical_parser_invocation_request_sha256",
        ),
        CheckConstraint(
            "request_size_bytes BETWEEN 1 AND 4096",
            name="ck_technical_parser_invocation_request_size",
        ),
        CheckConstraint(
            "length(extraction_policy) BETWEEN 1 AND 100 "
            "AND extraction_policy = trim(extraction_policy)",
            name="ck_technical_parser_invocation_policy",
        ),
        CheckConstraint(
            _canonical_sha256_check("extraction_policy_sha256"),
            name="ck_technical_parser_invocation_policy_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("worker_image_digest"),
            name="ck_technical_parser_invocation_worker_digest",
        ),
        CheckConstraint(
            "oci_profile_schema = 'technical-parser-oci-profile-v1'",
            name="ck_technical_parser_invocation_oci_profile_schema",
        ),
        CheckConstraint(
            "transport_schema = 'technical-parser-stdin-frame-v1'",
            name="ck_technical_parser_invocation_transport_schema",
        ),
        CheckConstraint(
            "length(image_reference) BETWEEN 73 AND 500 "
            "AND image_reference = trim(image_reference) "
            "AND substr(image_reference, length(image_reference) - 71, 72) = "
            "('@sha256:' || worker_image_digest)",
            name="ck_technical_parser_invocation_image_reference",
        ),
        CheckConstraint(
            "length(image_id) = 71 "
            "AND substr(image_id, 1, 7) = 'sha256:' "
            "AND " + _canonical_sha256_check("substr(image_id, 8, 64)"),
            name="ck_technical_parser_invocation_image_id",
        ),
        CheckConstraint(
            "platform IN ('linux/amd64', 'linux/arm64')",
            name="ck_technical_parser_invocation_platform",
        ),
        CheckConstraint(
            "length(runtime_host) BETWEEN 30 AND 500 "
            "AND runtime_host = trim(runtime_host) "
            "AND runtime_host LIKE 'unix:///run/user/%/docker.sock'",
            name="ck_technical_parser_invocation_runtime_host",
        ),
        CheckConstraint(
            _canonical_sha256_check("runtime_executable_sha256"),
            name="ck_technical_parser_invocation_runtime_executable_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("seccomp_profile_sha256"),
            name="ck_technical_parser_invocation_seccomp_profile_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("runtime_profile_sha256"),
            name="ck_technical_parser_invocation_runtime_profile_sha256",
        ),
        CheckConstraint(
            "runtime_attestation_schema IN ("
            "'technical-parser-runtime-attestation-v1', "
            "'technical-parser-runtime-attestation-v2')",
            name="ck_technical_parser_invocation_runtime_attestation_schema",
        ),
        CheckConstraint(
            _canonical_sha256_check("runtime_attestation_sha256"),
            name="ck_technical_parser_invocation_runtime_attestation_sha256",
        ),
        CheckConstraint(
            "immutable = true",
            name="ck_technical_parser_invocation_immutable",
        ),
        UniqueConstraint(
            "attempt_token",
            name="uq_technical_parser_invocation_attempt_token",
        ),
        UniqueConstraint(
            "id",
            "run_id",
            "operation",
            "page_number",
            "request_sha256",
            "runtime_attestation_sha256",
            name="uq_technical_parser_invocation_receipt_binding",
        ),
        Index(
            "ix_technical_parser_invocations_run_created",
            "run_id",
            "created_at",
        ),
        Index(
            "ix_technical_parser_invocations_run_operation_page",
            "run_id",
            "operation",
            "page_number",
        ),
    )

    invocation_schema: Mapped[str] = mapped_column(
        String(100), default="technical-parser-invocation-v1", nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    run_attempt_token: Mapped[str] = mapped_column(String(36), nullable=False)
    run_attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    page_id: Mapped[str | None] = mapped_column(String(36))
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_attempt_token: Mapped[str | None] = mapped_column(String(36))
    page_attempt_count: Mapped[int | None] = mapped_column(Integer)
    attempt_token: Mapped[str] = mapped_column(String(36), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    extraction_policy: Mapped[str] = mapped_column(String(100), nullable=False)
    extraction_policy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    worker_image_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    oci_profile_schema: Mapped[str] = mapped_column(
        String(100), default="technical-parser-oci-profile-v1", nullable=False
    )
    transport_schema: Mapped[str] = mapped_column(
        String(100), default="technical-parser-stdin-frame-v1", nullable=False
    )
    image_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    image_id: Mapped[str] = mapped_column(String(71), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    runtime_host: Mapped[str] = mapped_column(String(500), nullable=False)
    runtime_executable_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    seccomp_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_attestation_schema: Mapped[str] = mapped_column(
        String(100), default="technical-parser-runtime-attestation-v1", nullable=False
    )
    runtime_attestation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    runtime_attestation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TechnicalParserInvocationReceipt(Base):
    """Append-only terminal receipt for one reserved parser invocation."""

    __tablename__ = "technical_parser_invocation_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            [
                "invocation_id",
                "run_id",
                "operation",
                "page_number",
                "request_sha256",
                "runtime_attestation_sha256",
            ],
            [
                "technical_parser_invocations.id",
                "technical_parser_invocations.run_id",
                "technical_parser_invocations.operation",
                "technical_parser_invocations.page_number",
                "technical_parser_invocations.request_sha256",
                "technical_parser_invocations.runtime_attestation_sha256",
            ],
            name="fk_technical_parser_invocation_receipt_reservation",
        ),
        CheckConstraint(
            _canonical_uuid4_check("invocation_id"),
            name="ck_technical_parser_invocation_receipt_invocation_id",
        ),
        CheckConstraint(
            "receipt_schema = 'technical-parser-invocation-receipt-v1'",
            name="ck_technical_parser_invocation_receipt_schema",
        ),
        CheckConstraint(
            "operation IN ('layout', 'page') "
            "AND ((operation = 'layout' AND page_number = 0) OR "
            "(operation = 'page' AND page_number BETWEEN 1 AND 500))",
            name="ck_technical_parser_invocation_receipt_operation",
        ),
        CheckConstraint(
            _canonical_sha256_check("request_sha256"),
            name="ck_technical_parser_invocation_receipt_request_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("runtime_attestation_sha256"),
            name="ck_technical_parser_receipt_runtime_attestation_sha256",
        ),
        CheckConstraint(
            "execution_state IN ("
            "'not_started', 'succeeded', 'failed', "
            "'execution_unknown', 'containment_lost')",
            name="ck_technical_parser_invocation_receipt_state",
        ),
        CheckConstraint(
            "length(outcome_code) BETWEEN 1 AND 100 AND outcome_code = trim(outcome_code)",
            name="ck_technical_parser_invocation_receipt_outcome",
        ),
        CheckConstraint(
            "container_id IS NULL OR (" + _canonical_sha256_check("container_id") + ")",
            name="ck_technical_parser_invocation_receipt_container_id",
        ),
        CheckConstraint(
            "exit_code IS NULL OR exit_code BETWEEN 0 AND 255",
            name="ck_technical_parser_invocation_receipt_exit_code",
        ),
        CheckConstraint(
            "(stdout_sha256 IS NULL AND stdout_size_bytes IS NULL) OR "
            "(stdout_sha256 IS NOT NULL "
            "AND stdout_size_bytes BETWEEN 0 AND 30412804)",
            name="ck_technical_parser_invocation_receipt_stdout_binding",
        ),
        CheckConstraint(
            "stdout_sha256 IS NULL OR (" + _canonical_sha256_check("stdout_sha256") + ")",
            name="ck_technical_parser_invocation_receipt_stdout_sha256",
        ),
        CheckConstraint(
            "started_at IS NULL OR completed_at >= started_at",
            name="ck_technical_parser_invocation_receipt_timing",
        ),
        CheckConstraint(
            "(execution_state = 'not_started' "
            "AND outcome_code IN ("
            "'PARSER_EXECUTION_CONTAINMENT_LOST', "
            "'PARSER_EXECUTION_FAILED', "
            "'PARSER_EXECUTION_OUTPUT_OVERFLOW', "
            "'PARSER_EXECUTION_SOURCE_INVALID', "
            "'PARSER_EXECUTION_TIMEOUT', "
            "'PARSER_EXECUTION_UNAVAILABLE') "
            "AND container_id IS NULL "
            "AND started_at IS NULL "
            "AND exit_code IS NULL "
            "AND stdout_sha256 IS NULL "
            "AND stdout_size_bytes IS NULL "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'succeeded' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND exit_code = 0 "
            "AND stdout_sha256 IS NOT NULL "
            "AND stdout_size_bytes BETWEEN 1 AND 30412804 "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'failed' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND cleanup_confirmed = true) OR "
            # Keep the migration-0015 shape for immutable historical rows.
            # Canonical receipt construction applies the narrower new-write rules.
            "(execution_state = 'execution_unknown' "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'containment_lost' "
            "AND cleanup_confirmed = false)",
            name="ck_technical_parser_invocation_receipt_lifecycle",
        ),
        CheckConstraint(
            _canonical_sha256_check("receipt_sha256"),
            name="ck_technical_parser_invocation_receipt_sha256",
        ),
        CheckConstraint(
            "immutable = true",
            name="ck_technical_parser_invocation_receipt_immutable",
        ),
        Index(
            "ix_technical_parser_invocation_receipts_run_created",
            "run_id",
            "created_at",
        ),
        Index(
            "ix_technical_parser_invocation_receipts_state",
            "execution_state",
        ),
    )

    invocation_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, nullable=False
    )
    receipt_schema: Mapped[str] = mapped_column(
        String(100), default="technical-parser-invocation-receipt-v1", nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_attestation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    execution_state: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome_code: Mapped[str] = mapped_column(String(100), nullable=False)
    container_id: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_sha256: Mapped[str | None] = mapped_column(String(64))
    stdout_size_bytes: Mapped[int | None] = mapped_column(Integer)
    cleanup_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    receipt_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TechnicalDerivedArtifact(RecordMixin, Base):
    """Immutable validated output bytes derived from one extraction page."""

    __tablename__ = "technical_derived_artifacts"
    __table_args__ = (
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_derived_artifact_id",
        ),
        CheckConstraint(
            "artifact_schema = 'technical-derived-artifact-v1'",
            name="ck_technical_derived_artifact_schema",
        ),
        CheckConstraint(
            "page_number BETWEEN 1 AND 500",
            name="ck_technical_derived_artifact_page",
        ),
        CheckConstraint(
            "artifact_kind IN ('page_evidence_json', 'page_image_png')",
            name="ck_technical_derived_artifact_kind",
        ),
        CheckConstraint(
            "(artifact_kind = 'page_evidence_json' "
            "AND media_type = 'application/json') OR "
            "(artifact_kind = 'page_image_png' "
            "AND media_type = 'image/png')",
            name="ck_technical_derived_artifact_media_type",
        ),
        CheckConstraint(
            _canonical_sha256_check("sha256"),
            name="ck_technical_derived_artifact_sha256",
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 26214400",
            name="ck_technical_derived_artifact_size",
        ),
        CheckConstraint(
            "length(storage_path) BETWEEN 1 AND 1000 AND storage_path = trim(storage_path)",
            name="ck_technical_derived_artifact_storage_path",
        ),
        CheckConstraint(
            "validation_policy = 'technical-page-evidence-validator-v1'",
            name="ck_technical_derived_artifact_validation_policy",
        ),
        CheckConstraint(
            "immutable = true",
            name="ck_technical_derived_artifact_immutable",
        ),
        UniqueConstraint(
            "run_id",
            "page_number",
            "artifact_kind",
            name="uq_technical_derived_artifact_run_page_kind",
        ),
        UniqueConstraint(
            "id",
            "run_id",
            "page_number",
            "artifact_kind",
            "sha256",
            "size_bytes",
            name="uq_technical_derived_artifact_page_binding",
        ),
        Index(
            "ix_technical_derived_artifacts_run_page",
            "run_id",
            "page_number",
        ),
        Index("ix_technical_derived_artifacts_sha256", "sha256"),
    )

    artifact_schema: Mapped[str] = mapped_column(
        String(100), default="technical-derived-artifact-v1", nullable=False
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("technical_extraction_runs.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    validation_policy: Mapped[str] = mapped_column(
        String(100), default="technical-page-evidence-validator-v1", nullable=False
    )
    immutable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    run: Mapped[TechnicalExtractionRun] = relationship(back_populates="artifacts")


class TechnicalExtractionPage(RecordMixin, Base):
    """One independently validated page packet from an extraction run."""

    __tablename__ = "technical_extraction_pages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["run_id", "page_count"],
            ["technical_extraction_runs.id", "technical_extraction_runs.page_count"],
            name="fk_technical_extraction_page_run_page_count",
        ),
        ForeignKeyConstraint(
            ["run_id", "ocr_low_confidence_threshold"],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.ocr_low_confidence_threshold",
            ],
            name="fk_technical_extraction_page_run_ocr_threshold",
        ),
        ForeignKeyConstraint(
            ["run_id", "layout_sha256"],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.layout_sha256",
            ],
            name="fk_technical_extraction_page_run_layout",
        ),
        ForeignKeyConstraint(
            [
                "packet_artifact_id",
                "run_id",
                "page_number",
                "packet_artifact_kind",
                "packet_sha256",
                "packet_size_bytes",
            ],
            [
                "technical_derived_artifacts.id",
                "technical_derived_artifacts.run_id",
                "technical_derived_artifacts.page_number",
                "technical_derived_artifacts.artifact_kind",
                "technical_derived_artifacts.sha256",
                "technical_derived_artifacts.size_bytes",
            ],
            name="fk_technical_extraction_page_packet_binding",
        ),
        ForeignKeyConstraint(
            [
                "page_image_artifact_id",
                "run_id",
                "page_number",
                "page_image_artifact_kind",
                "page_image_sha256",
                "page_image_size_bytes",
            ],
            [
                "technical_derived_artifacts.id",
                "technical_derived_artifacts.run_id",
                "technical_derived_artifacts.page_number",
                "technical_derived_artifacts.artifact_kind",
                "technical_derived_artifacts.sha256",
                "technical_derived_artifacts.size_bytes",
            ],
            name="fk_technical_extraction_page_image_binding",
        ),
        CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_extraction_page_id",
        ),
        CheckConstraint(
            "page_schema IN ('technical-extraction-page-v1', 'technical-extraction-page-v2')",
            name="ck_technical_extraction_page_schema",
        ),
        CheckConstraint(
            "evidence_schema = 'technical-page-evidence-v1'",
            name="ck_technical_extraction_page_evidence_schema",
        ),
        CheckConstraint(
            "validator_policy = 'technical-page-evidence-validator-v1'",
            name="ck_technical_extraction_page_validator_policy",
        ),
        CheckConstraint(
            "status IN ("
            "'pending', 'processing', 'completed', 'needs_attention', 'failed', 'cancelled'"
            ")",
            name="ck_technical_extraction_page_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_extraction_page_attempt_count",
        ),
        CheckConstraint(
            "attempt_token IS NULL OR (" + _canonical_uuid4_check("attempt_token") + ")",
            name="ck_technical_extraction_page_attempt_token",
        ),
        CheckConstraint(
            "parser_invocation_id IS NULL OR ("
            + _canonical_uuid4_check("parser_invocation_id")
            + ")",
            name="ck_technical_extraction_page_parser_invocation_id",
        ),
        CheckConstraint(
            "(page_schema = 'technical-extraction-page-v1' "
            "AND parser_invocation_id IS NULL) OR "
            "(page_schema = 'technical-extraction-page-v2' "
            "AND ((status IN ('completed', 'needs_attention') "
            "AND parser_invocation_id IS NOT NULL) OR "
            "(status NOT IN ('completed', 'needs_attention') "
            "AND parser_invocation_id IS NULL)))",
            name="ck_technical_extraction_page_parser_provenance",
        ),
        CheckConstraint(
            "outcome_code IS NULL OR ("
            "length(outcome_code) BETWEEN 1 AND 100 "
            "AND outcome_code = trim(outcome_code))",
            name="ck_technical_extraction_page_outcome_code",
        ),
        CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_extraction_page_claim",
        ),
        CheckConstraint(
            "(status = 'pending' "
            "AND attempt_count = 0 "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'processing' "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'completed' "
            "AND attempt_count > 0 "
            "AND outcome_code = 'PAGE_EXTRACTION_COMPLETE' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'needs_attention' "
            "AND attempt_count > 0 "
            "AND outcome_code = 'PAGE_EXTRACTION_NEEDS_ATTENTION' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'failed' "
            "AND attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'PAGE_EXTRACTION_COMPLETE', 'PAGE_EXTRACTION_NEEDS_ATTENTION'"
            ") "
            "AND outcome_retryable IS NOT NULL "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'cancelled' "
            "AND outcome_code = 'PAGE_EXTRACTION_CANCELLED' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_technical_extraction_page_lifecycle",
        ),
        CheckConstraint(
            "page_number BETWEEN 1 AND 500 "
            "AND page_count BETWEEN 1 AND 500 "
            "AND page_number <= page_count",
            name="ck_technical_extraction_page_number",
        ),
        CheckConstraint(
            _canonical_sha256_check("layout_sha256"),
            name="ck_technical_extraction_page_layout_sha256",
        ),
        CheckConstraint(
            "layout_page_width_points > 0 "
            "AND layout_page_width_points <= 20000 "
            "AND layout_page_height_points > 0 "
            "AND layout_page_height_points <= 20000",
            name="ck_technical_extraction_page_layout_dimensions",
        ),
        CheckConstraint(
            "packet_artifact_kind IS NULL OR packet_artifact_kind = 'page_evidence_json'",
            name="ck_technical_extraction_page_packet_kind",
        ),
        CheckConstraint(
            "page_image_artifact_kind IS NULL OR page_image_artifact_kind = 'page_image_png'",
            name="ck_technical_extraction_page_image_kind",
        ),
        CheckConstraint(
            "packet_size_bytes IS NULL OR packet_size_bytes BETWEEN 1 AND 4194304",
            name="ck_technical_extraction_page_packet_size",
        ),
        CheckConstraint(
            "page_image_size_bytes IS NULL OR page_image_size_bytes BETWEEN 1 AND 26214400",
            name="ck_technical_extraction_page_image_size",
        ),
        CheckConstraint(
            "ocr_status IS NULL OR ocr_status IN ("
            "'ocr_not_required', 'ocr_completed', 'low_confidence', 'unreadable'"
            ")",
            name="ck_technical_extraction_page_ocr_status",
        ),
        CheckConstraint(
            "ocr_low_confidence_threshold IS NULL OR "
            "ocr_low_confidence_threshold BETWEEN 0 AND 100",
            name="ck_technical_extraction_page_ocr_threshold",
        ),
        CheckConstraint(
            _canonical_sha256_check("packet_sha256"),
            name="ck_technical_extraction_page_packet_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("page_image_sha256"),
            name="ck_technical_extraction_page_image_sha256",
        ),
        CheckConstraint(
            _canonical_sha256_check("binding_sha256"),
            name="ck_technical_extraction_page_binding_sha256",
        ),
        CheckConstraint(
            "page_width_points > 0 AND page_width_points <= 20000 "
            "AND page_height_points > 0 AND page_height_points <= 20000",
            name="ck_technical_extraction_page_dimensions",
        ),
        CheckConstraint(
            "page_width_points IS NULL OR ("
            "page_width_points = layout_page_width_points "
            "AND page_height_points = layout_page_height_points)",
            name="ck_technical_extraction_page_output_layout_dimensions",
        ),
        CheckConstraint(
            "image_width_pixels BETWEEN 1 AND 4096 "
            "AND image_height_pixels BETWEEN 1 AND 4096 "
            "AND image_width_pixels * image_height_pixels <= 8000000",
            name="ck_technical_extraction_page_image_dimensions",
        ),
        CheckConstraint(
            "extraction_mode IN ('native_text', 'ocr', 'hybrid', 'unreadable')",
            name="ck_technical_extraction_page_mode",
        ),
        CheckConstraint(
            "native_block_count BETWEEN 0 AND 10000 "
            "AND ocr_block_count BETWEEN 0 AND 10000 "
            "AND native_block_count + ocr_block_count <= 10000",
            name="ck_technical_extraction_page_block_counts",
        ),
        CheckConstraint(
            "(extraction_mode = 'native_text' "
            "AND native_block_count > 0 AND ocr_block_count = 0) OR "
            "(extraction_mode = 'ocr' "
            "AND native_block_count = 0 AND ocr_block_count > 0) OR "
            "(extraction_mode = 'hybrid' "
            "AND native_block_count > 0 AND ocr_block_count > 0) OR "
            "(extraction_mode = 'unreadable' "
            "AND native_block_count = 0 AND ocr_block_count = 0 "
            "AND human_review_required = true)",
            name="ck_technical_extraction_page_mode_counts",
        ),
        CheckConstraint(
            "(ocr_block_count = 0 AND minimum_ocr_confidence IS NULL) OR "
            "(ocr_block_count > 0 "
            "AND minimum_ocr_confidence BETWEEN 0 AND 100)",
            name="ck_technical_extraction_page_ocr_confidence",
        ),
        CheckConstraint(
            "packet_artifact_id <> page_image_artifact_id",
            name="ck_technical_extraction_page_distinct_artifacts",
        ),
        CheckConstraint(
            "(status IN ('completed', 'needs_attention') "
            "AND packet_artifact_id IS NOT NULL "
            "AND packet_artifact_kind = 'page_evidence_json' "
            "AND packet_size_bytes IS NOT NULL "
            "AND page_image_artifact_id IS NOT NULL "
            "AND page_image_artifact_kind = 'page_image_png' "
            "AND page_image_size_bytes IS NOT NULL "
            "AND packet_sha256 IS NOT NULL "
            "AND page_image_sha256 IS NOT NULL "
            "AND binding_sha256 IS NOT NULL "
            "AND page_width_points IS NOT NULL "
            "AND page_height_points IS NOT NULL "
            "AND image_width_pixels IS NOT NULL "
            "AND image_height_pixels IS NOT NULL "
            "AND extraction_mode IS NOT NULL "
            "AND native_block_count IS NOT NULL "
            "AND ocr_block_count IS NOT NULL "
            "AND ocr_status IS NOT NULL "
            "AND ocr_low_confidence_threshold IS NOT NULL "
            "AND human_review_required IS NOT NULL) OR "
            "(status NOT IN ('completed', 'needs_attention') "
            "AND packet_artifact_id IS NULL "
            "AND packet_artifact_kind IS NULL "
            "AND packet_size_bytes IS NULL "
            "AND page_image_artifact_id IS NULL "
            "AND page_image_artifact_kind IS NULL "
            "AND page_image_size_bytes IS NULL "
            "AND packet_sha256 IS NULL "
            "AND page_image_sha256 IS NULL "
            "AND binding_sha256 IS NULL "
            "AND page_width_points IS NULL "
            "AND page_height_points IS NULL "
            "AND image_width_pixels IS NULL "
            "AND image_height_pixels IS NULL "
            "AND extraction_mode IS NULL "
            "AND native_block_count IS NULL "
            "AND ocr_block_count IS NULL "
            "AND minimum_ocr_confidence IS NULL "
            "AND ocr_status IS NULL "
            "AND ocr_low_confidence_threshold IS NULL "
            "AND human_review_required IS NULL)",
            name="ck_technical_extraction_page_output_presence",
        ),
        CheckConstraint(
            "(status = 'completed' AND human_review_required = false) OR "
            "(status = 'needs_attention' AND human_review_required = true) OR "
            "status NOT IN ('completed', 'needs_attention')",
            name="ck_technical_extraction_page_review_state",
        ),
        CheckConstraint(
            "(ocr_status = 'ocr_not_required' "
            "AND ocr_block_count = 0 "
            "AND native_block_count > 0 "
            "AND minimum_ocr_confidence IS NULL) OR "
            "(ocr_status = 'ocr_completed' "
            "AND ocr_block_count > 0 "
            "AND minimum_ocr_confidence >= ocr_low_confidence_threshold) OR "
            "(ocr_status = 'low_confidence' "
            "AND ocr_block_count > 0 "
            "AND minimum_ocr_confidence < ocr_low_confidence_threshold "
            "AND human_review_required = true) OR "
            "(ocr_status = 'unreadable' "
            "AND ocr_block_count = 0 "
            "AND minimum_ocr_confidence IS NULL "
            "AND human_review_required = true) OR "
            "ocr_status IS NULL",
            name="ck_technical_extraction_page_ocr_state",
        ),
        UniqueConstraint(
            "run_id",
            "page_number",
            name="uq_technical_extraction_page_run_page",
        ),
        UniqueConstraint(
            "id",
            "run_id",
            "page_number",
            name="uq_technical_extraction_page_identity_binding",
        ),
        UniqueConstraint(
            "packet_artifact_id",
            name="uq_technical_extraction_page_packet_artifact",
        ),
        UniqueConstraint(
            "page_image_artifact_id",
            name="uq_technical_extraction_page_image_artifact",
        ),
        UniqueConstraint(
            "attempt_token",
            name="uq_technical_extraction_page_attempt_token",
        ),
        UniqueConstraint(
            "parser_invocation_id",
            name="uq_technical_extraction_page_parser_invocation",
        ),
        Index(
            "ix_technical_extraction_pages_run_page",
            "run_id",
            "page_number",
        ),
        Index(
            "ix_technical_extraction_pages_review_required",
            "human_review_required",
        ),
        Index(
            "ix_technical_extraction_pages_run_status_page",
            "run_id",
            "status",
            "page_number",
        ),
        Index(
            "uq_technical_extraction_pages_processing_run",
            "run_id",
            unique=True,
            sqlite_where=text("status = 'processing'"),
            postgresql_where=text("status = 'processing'"),
        ),
    )

    page_schema: Mapped[str] = mapped_column(
        String(100), default="technical-extraction-page-v1", nullable=False
    )
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    layout_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    layout_page_width_points: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    layout_page_height_points: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    evidence_schema: Mapped[str] = mapped_column(
        String(100), default="technical-page-evidence-v1", nullable=False
    )
    validator_policy: Mapped[str] = mapped_column(
        String(100), default="technical-page-evidence-validator-v1", nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True, nullable=False)
    attempt_token: Mapped[str | None] = mapped_column(String(36))
    attempt_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parser_invocation_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "technical_parser_invocation_receipts.invocation_id",
            name="fk_technical_extraction_page_parser_invocation",
            use_alter=True,
        )
    )
    outcome_code: Mapped[str | None] = mapped_column(String(100))
    outcome_retryable: Mapped[bool | None] = mapped_column(Boolean)
    last_outcome_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    packet_artifact_id: Mapped[str | None] = mapped_column(String(36))
    packet_artifact_kind: Mapped[str | None] = mapped_column(String(40))
    packet_size_bytes: Mapped[int | None] = mapped_column(Integer)
    page_image_artifact_id: Mapped[str | None] = mapped_column(String(36))
    page_image_artifact_kind: Mapped[str | None] = mapped_column(String(40))
    page_image_size_bytes: Mapped[int | None] = mapped_column(Integer)
    packet_sha256: Mapped[str | None] = mapped_column(String(64))
    page_image_sha256: Mapped[str | None] = mapped_column(String(64))
    binding_sha256: Mapped[str | None] = mapped_column(String(64))
    page_width_points: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    page_height_points: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    image_width_pixels: Mapped[int | None] = mapped_column(Integer)
    image_height_pixels: Mapped[int | None] = mapped_column(Integer)
    extraction_mode: Mapped[str | None] = mapped_column(String(30))
    native_block_count: Mapped[int | None] = mapped_column(Integer)
    ocr_block_count: Mapped[int | None] = mapped_column(Integer)
    minimum_ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    ocr_status: Mapped[str | None] = mapped_column(String(30))
    ocr_low_confidence_threshold: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    human_review_required: Mapped[bool | None] = mapped_column(Boolean)

    run: Mapped[TechnicalExtractionRun] = relationship(
        back_populates="pages",
        foreign_keys=[run_id],
        primaryjoin="TechnicalExtractionRun.id == TechnicalExtractionPage.run_id",
    )


class TechnicalVariant(RecordMixin, Base):
    __tablename__ = "technical_variants"

    variant_id: Mapped[str] = mapped_column(String(300), unique=True, index=True, nullable=False)
    system_id: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    technical_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    source_document_reference: Mapped[str | None] = mapped_column(String(300), index=True)
    source_page: Mapped[str | None] = mapped_column(String(100))
    source_table: Mapped[str | None] = mapped_column(String(300))
    source_figure: Mapped[str | None] = mapped_column(String(300))
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    product_family: Mapped[str | None] = mapped_column(String(300), index=True)
    service_type: Mapped[str | None] = mapped_column(String(300), index=True)
    service_material: Mapped[str | None] = mapped_column(String(300), index=True)
    minimum_service_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_service_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    permitted_service_quantity: Mapped[str | None] = mapped_column(String(100))
    insulation_type: Mapped[str | None] = mapped_column(Text)
    insulation_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    substrate_type: Mapped[str | None] = mapped_column(Text, index=True)
    minimum_substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    maximum_substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orientation: Mapped[str | None] = mapped_column(Text, index=True)
    installation_face: Mapped[str | None] = mapped_column(Text)
    opening_type: Mapped[str | None] = mapped_column(Text, index=True)
    opening_dimensions: Mapped[str | None] = mapped_column(Text)
    annular_gap_min_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    annular_gap_max_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    service_spacing_rules: Mapped[str | None] = mapped_column(Text)
    edge_distance_rules: Mapped[str | None] = mapped_column(Text)
    support_rules: Mapped[str | None] = mapped_column(Text)
    fixing_rules: Mapped[str | None] = mapped_column(Text)
    component_requirements: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON)
    labour_requirements: Mapped[list[str] | None] = mapped_column(JSON)
    hard_exclusions: Mapped[str | None] = mapped_column(Text)
    dependencies: Mapped[str | None] = mapped_column(Text)
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    confidence_cap: Mapped[Decimal | None] = mapped_column(Numeric(9, 3))
    search_eligibility: Mapped[str | None] = mapped_column(String(100), index=True)
    expert_review_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("technical_variants.id"))

    __table_args__ = (
        Index("ix_technical_search", "service_type", "service_material", "frl", "status"),
    )


class EstimatingRule(RecordMixin, Base):
    __tablename__ = "estimating_rules"
    __table_args__ = (UniqueConstraint("rule_code", "version", name="uq_rule_code_version"),)

    rule_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actions: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), default="warning", index=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    source_reference: Mapped[str | None] = mapped_column(Text)
    source_page: Mapped[str | None] = mapped_column(String(100))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    conflict_resolution: Mapped[str] = mapped_column(String(100), default="higher_priority_wins")
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    test_cases: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    author_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approver_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"), index=True)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("estimating_rules.id"))


class ChangeProposal(RecordMixin, Base):
    __tablename__ = "change_proposals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(100), index=True)
    proposal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    proposed_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="user", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    submitted_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    review_notes: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Customer(RecordMixin, Base):
    __tablename__ = "customers"

    name: Mapped[str] = mapped_column(String(300), index=True, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(300))
    tax_identifier: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    billing_address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )
    projects: Mapped[list[Project]] = relationship(back_populates="customer")


class Contact(RecordMixin, Base):
    __tablename__ = "contacts"

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[str | None] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Project(RecordMixin, Base):
    __tablename__ = "projects"

    customer_id: Mapped[str | None] = mapped_column(ForeignKey("customers.id"), index=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    site_address: Mapped[str | None] = mapped_column(Text)
    jurisdiction: Mapped[str] = mapped_column(String(200), default="NSW/ACT, Australia")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    notes: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship(back_populates="projects")
    estimates: Mapped[list[Estimate]] = relationship(back_populates="project")


class Estimate(RecordMixin, Base):
    __tablename__ = "estimates"
    __table_args__ = (
        UniqueConstraint("project_id", "revision", name="uq_project_estimate_revision"),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reference: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    currency: Mapped[str] = mapped_column(String(3), default="AUD")
    tax_name: Mapped[str] = mapped_column(String(30), default="GST")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0.10"))
    product_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    material_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    labour_markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    assumptions: Mapped[list[str] | None] = mapped_column(JSON)
    exclusions: Mapped[list[str] | None] = mapped_column(JSON)
    qualifications: Mapped[list[str] | None] = mapped_column(JSON)
    pricing_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    technical_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    rules_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    products_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    labour_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    markups_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    formula_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    brand_release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tax_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    snapshot_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

    project: Mapped[Project] = relationship(back_populates="estimates")
    openings: Mapped[list[Opening]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan", order_by="Opening.created_at"
    )
    lines: Mapped[list[EstimateLine]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan", order_by="EstimateLine.created_at"
    )


class Opening(RecordMixin, Base):
    __tablename__ = "openings"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    defect_id: Mapped[str | None] = mapped_column(String(100), index=True)
    canonical_defect_id: Mapped[str | None] = mapped_column(ForeignKey("defects.id"), index=True)
    opening_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    substrate_type: Mapped[str | None] = mapped_column(String(200), index=True)
    substrate_plane: Mapped[str | None] = mapped_column(String(50), index=True)
    substrate_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    orientation: Mapped[str | None] = mapped_column(String(100), index=True)
    opening_type: Mapped[str | None] = mapped_column(String(100))
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    frl: Mapped[str | None] = mapped_column(String(100), index=True)
    physical_model_status: Mapped[str] = mapped_column(String(30), default="draft")
    technical_status: Mapped[str] = mapped_column(String(50), default="not_assessed")
    selected_technical_variant_id: Mapped[str | None] = mapped_column(
        ForeignKey("technical_variants.id")
    )
    notes: Mapped[str | None] = mapped_column(Text)

    estimate: Mapped[Estimate] = relationship(back_populates="openings")
    services: Mapped[list[Service]] = relationship(
        back_populates="opening", cascade="all, delete-orphan", order_by="Service.created_at"
    )

    __table_args__ = (
        UniqueConstraint("estimate_id", "opening_code", name="uq_estimate_opening_code"),
    )


class Service(RecordMixin, Base):
    __tablename__ = "services"

    opening_id: Mapped[str] = mapped_column(ForeignKey("openings.id"), index=True, nullable=False)
    primary_opening_legacy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    service_code: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    service_type: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    material: Mapped[str | None] = mapped_column(String(200), index=True)
    nominal_size_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    outside_diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    width_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    height_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    insulation_type: Mapped[str | None] = mapped_column(String(200))
    insulation_thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("1"))
    centre_x_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    centre_y_mm: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    evidence_status: Mapped[str] = mapped_column(String(30), default="provisional")
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(9, 4))
    notes: Mapped[str | None] = mapped_column(Text)

    opening: Mapped[Opening] = relationship(back_populates="services")

    __table_args__ = (
        UniqueConstraint("opening_id", "service_code", name="uq_opening_service_code"),
    )


class EstimateLine(RecordMixin, Base):
    __tablename__ = "estimate_lines"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    service_id: Mapped[str | None] = mapped_column(ForeignKey("services.id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    component_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    component_reference: Mapped[str | None] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"))
    unit: Mapped[str] = mapped_column(String(50), default="each")
    base_unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    waste_factor: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"))
    markup_override: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    applied_markup: Mapped[Decimal] = mapped_column(Numeric(9, 6), default=Decimal("0"))
    markup_source: Mapped[str] = mapped_column(String(100), default="global_default")
    unit_sell: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    subtotal_ex_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_incl_tax: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    pricing_method: Mapped[str] = mapped_column(String(80), default="component_built")
    commercial_recovery_status: Mapped[str] = mapped_column(String(80), default="separately_priced")
    rate_source: Mapped[str | None] = mapped_column(String(300))
    formula_version: Mapped[str] = mapped_column(String(50), default="QF-CALC-1")
    status: Mapped[str] = mapped_column(String(30), default="draft")
    notes: Mapped[str | None] = mapped_column(Text)

    estimate: Mapped[Estimate] = relationship(back_populates="lines")

    __table_args__ = (
        UniqueConstraint("estimate_id", "line_number", name="uq_estimate_line_number"),
    )


class RuleEvaluation(RecordMixin, Base):
    __tablename__ = "rule_evaluations"

    estimate_id: Mapped[str] = mapped_column(ForeignKey("estimates.id"), index=True, nullable=False)
    opening_id: Mapped[str | None] = mapped_column(ForeignKey("openings.id"), index=True)
    rule_id: Mapped[str] = mapped_column(
        ForeignKey("estimating_rules.id"), index=True, nullable=False
    )
    result: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(30), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)


class Approval(RecordMixin, Base):
    __tablename__ = "approvals"

    entity_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    approval_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    requested_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    decided_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    snapshot_hash: Mapped[str | None] = mapped_column(String(64))


class BackgroundJob(RecordMixin, Base):
    __tablename__ = "background_jobs"

    job_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
