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
    LargeBinary,
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
        UniqueConstraint(
            "library_type", "version", name="uq_library_release_type_version"
        ),
        Index(
            "uq_library_release_one_active_technical",
            "library_type",
            unique=True,
            sqlite_where=text("status = 'active' AND library_type = 'technical'"),
            postgresql_where=text("status = 'active' AND library_type = 'technical'"),
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
    __table_args__ = (
        UniqueConstraint(
            'id',
            'sha256',
            'size_bytes',
            name='uq_stored_file_id_sha256_size',
        ),
    )

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


class ProjectEvidence(RecordMixin, Base):
    '''One immutable report or package binding to exactly one project context.'''

    __tablename__ = 'project_evidence'
    __table_args__ = (
        CheckConstraint(
            '(project_id IS NOT NULL AND estimate_id IS NULL) '
            'OR (project_id IS NULL AND estimate_id IS NOT NULL)',
            name='ck_project_evidence_single_owner',
        ),
        CheckConstraint(
            'source_size_bytes > 0',
            name='ck_project_evidence_source_size',
        ),
        ForeignKeyConstraint(
            ['stored_file_id', 'source_sha256', 'source_size_bytes'],
            ['stored_files.id', 'stored_files.sha256', 'stored_files.size_bytes'],
            name='fk_project_evidence_source_bytes',
        ),
        UniqueConstraint('id', 'source_sha256', name='uq_project_evidence_id_source_sha256'),
        UniqueConstraint('stored_file_id', name='uq_project_evidence_stored_file'),
        Index('ix_project_evidence_project_id', 'project_id'),
        Index('ix_project_evidence_estimate_id', 'estimate_id'),
    )

    project_id: Mapped[str | None] = mapped_column(ForeignKey('projects.id'))
    estimate_id: Mapped[str | None] = mapped_column(ForeignKey('estimates.id'))
    stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class ReportEvidenceLocator(RecordMixin, Base):
    '''A hash-bound, content-safe position inside one retained project report.'''

    __tablename__ = 'report_evidence_locators'
    __table_args__ = (
        CheckConstraint('sequence > 0', name='ck_report_evidence_locator_sequence'),
        CheckConstraint(
            'page_number IS NULL OR page_number > 0',
            name='ck_report_evidence_locator_page_number',
        ),
        CheckConstraint(
            'item_kind IN (\'metadata\', \'page\', \'text\', \'table\', \'caption\', '
            '\'drawing\', \'annotation\', \'image\', \'document\', \'worksheet\', \'cell\', '
            '\'paragraph\', \'document_table\')',
            name='ck_report_evidence_locator_item_kind',
        ),
        ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_evidence_locator_source',
        ),
        UniqueConstraint(
            'id',
            'project_evidence_id',
            name='uq_report_evidence_locator_id_project_evidence',
        ),
        UniqueConstraint(
            'project_evidence_id',
            'sequence',
            name='uq_report_evidence_locator_sequence',
        ),
        UniqueConstraint(
            'project_evidence_id',
            'locator_key',
            name='uq_report_evidence_locator_key',
        ),
        Index('ix_report_evidence_locator_project_page', 'project_evidence_id', 'page_number'),
    )

    project_evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    locator_key: Mapped[str] = mapped_column(String(300), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    locator_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ReportDefectScope(RecordMixin, Base):
    '''One selected range from a hash-bound report for an existing Defect.'''

    __tablename__ = 'report_defect_scopes'
    __table_args__ = (
        CheckConstraint(
            'length(trim(report_defect_label)) > 0',
            name='ck_report_defect_scope_label',
        ),
        ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_defect_scope_source',
        ),
        ForeignKeyConstraint(
            ['start_locator_id', 'project_evidence_id'],
            ['report_evidence_locators.id', 'report_evidence_locators.project_evidence_id'],
            name='fk_report_defect_scope_start_locator',
        ),
        ForeignKeyConstraint(
            ['end_locator_id', 'project_evidence_id'],
            ['report_evidence_locators.id', 'report_evidence_locators.project_evidence_id'],
            name='fk_report_defect_scope_end_locator',
        ),
        UniqueConstraint(
            'project_evidence_id',
            'defect_id',
            name='uq_report_defect_scope_report_defect',
        ),
        Index('ix_report_defect_scope_defect_id', 'defect_id'),
        Index(
            'ix_report_defect_scope_expected_label_manifest_id',
            'approved_expected_label_manifest_id',
        ),
    )

    project_evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    defect_id: Mapped[str] = mapped_column(ForeignKey('defects.id'), nullable=False)
    report_defect_label: Mapped[str] = mapped_column(String(150), nullable=False)
    approved_expected_label_manifest_id: Mapped[str | None] = mapped_column(
        ForeignKey('report_expected_label_manifests.id')
    )
    start_locator_id: Mapped[str] = mapped_column(String(36), nullable=False)
    end_locator_id: Mapped[str] = mapped_column(String(36), nullable=False)


class ReportExpectedLabelManifest(RecordMixin, Base):
    '''One immutable, human-approved expected Defect-label set for a retained report.'''

    __tablename__ = 'report_expected_label_manifests'
    __table_args__ = (
        CheckConstraint(
            'length(trim(approval_reference)) > 0',
            name='ck_report_expected_label_manifest_approval_reference',
        ),
        ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_expected_label_manifest_source',
        ),
        UniqueConstraint(
            'project_evidence_id',
            'manifest_sha256',
            'approval_reference',
            'approved_by_user_id',
            name='uq_report_expected_label_manifest_approval',
        ),
        Index('ix_report_expected_label_manifest_estimate_id', 'estimate_id'),
    )

    project_evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey('estimates.id'), nullable=False)
    expected_report_defect_labels: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    approved_by_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportEvidenceFamilyManifest(RecordMixin, Base):
    '''An immutable, human-approved exact set of retained reports for one estimate.'''

    __tablename__ = 'report_evidence_family_manifests'
    __table_args__ = (
        CheckConstraint(
            'length(trim(family_reference)) > 0',
            name='ck_report_evidence_family_manifest_reference',
        ),
        CheckConstraint(
            'length(trim(approval_reference)) > 0',
            name='ck_report_evidence_family_manifest_approval_reference',
        ),
        CheckConstraint(
            'member_count >= 2',
            name='ck_report_evidence_family_manifest_member_count',
        ),
        UniqueConstraint(
            'estimate_id',
            'manifest_sha256',
            'approval_reference',
            'approved_by_user_id',
            name='uq_report_evidence_family_manifest_approval',
        ),
        Index('ix_report_evidence_family_manifest_estimate_id', 'estimate_id'),
    )

    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey('estimates.id'), nullable=False)
    family_reference: Mapped[str] = mapped_column(String(150), nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    approved_by_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportEvidenceFamilyMember(RecordMixin, Base):
    '''One ordered, hash-bound retained report in an approved evidence family.'''

    __tablename__ = 'report_evidence_family_members'
    __table_args__ = (
        CheckConstraint(
            'member_sequence > 0',
            name='ck_report_evidence_family_member_sequence',
        ),
        ForeignKeyConstraint(
            ['report_evidence_family_manifest_id'],
            ['report_evidence_family_manifests.id'],
            name='fk_report_evidence_family_member_manifest',
        ),
        ForeignKeyConstraint(
            ['project_evidence_id', 'source_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_report_evidence_family_member_source',
        ),
        UniqueConstraint(
            'report_evidence_family_manifest_id',
            'member_sequence',
            name='uq_report_evidence_family_member_sequence',
        ),
        UniqueConstraint(
            'report_evidence_family_manifest_id',
            'project_evidence_id',
            name='uq_report_evidence_family_member_source',
        ),
        Index('ix_report_evidence_family_member_project_evidence_id', 'project_evidence_id'),
    )

    report_evidence_family_manifest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    member_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    project_evidence_id: Mapped[str] = mapped_column(String(36), nullable=False)
    stored_file_id: Mapped[str] = mapped_column(ForeignKey('stored_files.id'), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

class ProposalReviewPackage(RecordMixin, Base):
    '''Immutable proposal-only metadata for one report or approved report family.'''

    __tablename__ = 'proposal_review_packages'
    __table_args__ = (
        CheckConstraint(
            "record_owner = 'CLASSIFIRE'",
            name='ck_proposal_review_package_record_owner',
        ),
        CheckConstraint(
            'selected_defect_count > 0',
            name='ck_proposal_review_package_selected_defect_count',
        ),
        CheckConstraint(
            "(package_kind = 'single_report' "
            "AND project_evidence_id IS NOT NULL "
            "AND report_sha256 IS NOT NULL "
            "AND approved_expected_label_manifest_id IS NOT NULL "
            "AND approved_expected_label_manifest_sha256 IS NOT NULL "
            "AND report_evidence_family_manifest_id IS NULL "
            "AND report_evidence_family_manifest_sha256 IS NULL "
            "AND report_evidence_family_manifest_approval_reference IS NULL) "
            "OR (package_kind = 'report_evidence_family' "
            "AND project_evidence_id IS NULL "
            "AND report_sha256 IS NULL "
            "AND approved_expected_label_manifest_id IS NULL "
            "AND approved_expected_label_manifest_sha256 IS NULL "
            "AND report_evidence_family_manifest_id IS NOT NULL "
            "AND report_evidence_family_manifest_sha256 IS NOT NULL "
            "AND report_evidence_family_manifest_approval_reference IS NOT NULL)",
            name='ck_proposal_review_package_kind_binding',
        ),
        ForeignKeyConstraint(
            ['project_evidence_id', 'report_sha256'],
            ['project_evidence.id', 'project_evidence.source_sha256'],
            name='fk_proposal_review_package_report_source',
        ),
        UniqueConstraint('package_id', name='uq_proposal_review_package_package_id'),
        UniqueConstraint(
            'package_manifest_sha256',
            name='uq_proposal_review_package_manifest_sha256',
        ),
        Index('ix_proposal_review_package_project_estimate', 'project_id', 'estimate_id'),
        Index('ix_proposal_review_package_retention', 'retention_until'),
        Index(
            'ix_proposal_review_package_family_manifest_id',
            'report_evidence_family_manifest_id',
        ),
    )

    package_id: Mapped[str] = mapped_column(String(128), nullable=False)
    package_kind: Mapped[str] = mapped_column(String(30), default='single_report', nullable=False)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'), nullable=False)
    estimate_id: Mapped[str] = mapped_column(ForeignKey('estimates.id'), nullable=False)
    project_evidence_id: Mapped[str | None] = mapped_column(String(36))
    report_sha256: Mapped[str | None] = mapped_column(String(64))
    approved_expected_label_manifest_id: Mapped[str | None] = mapped_column(
        ForeignKey('report_expected_label_manifests.id')
    )
    approved_expected_label_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    report_evidence_family_manifest_id: Mapped[str | None] = mapped_column(
        ForeignKey('report_evidence_family_manifests.id')
    )
    report_evidence_family_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    report_evidence_family_manifest_approval_reference: Mapped[str | None] = mapped_column(
        String(500)
    )
    approval_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    package_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    completion_receipt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    selected_defect_count: Mapped[int] = mapped_column(Integer, nullable=False)
    reviewer_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    reviewer_summary_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_locator_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    safe_locator_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_owner: Mapped[str] = mapped_column(String(30), default='CLASSIFIRE', nullable=False)
    retention_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    legal_hold_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    legal_hold_reason_code: Mapped[str | None] = mapped_column(String(100))

class ProposalReviewPackageRedaction(RecordMixin, Base):
    '''A separate, immutable redacted reviewer view; it never changes the package.'''

    __tablename__ = 'proposal_review_package_redactions'
    __table_args__ = (
        ForeignKeyConstraint(
            ['proposal_review_package_id'],
            ['proposal_review_packages.id'],
            name='fk_proposal_review_package_redaction_package',
            ondelete='CASCADE',
        ),
        UniqueConstraint(
            'proposal_review_package_id',
            'redacted_summary_sha256',
            name='uq_proposal_review_package_redaction_summary',
        ),
        Index(
            'ix_proposal_review_package_redaction_package_created',
            'proposal_review_package_id',
            'created_at',
        ),
    )

    proposal_review_package_id: Mapped[str] = mapped_column(String(36), nullable=False)
    redaction_reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    redacted_scope_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    redacted_summary_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    redacted_summary_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)


class ProposalReviewAnnotation(RecordMixin, Base):
    """An immutable human review annotation with no downstream authority."""

    __tablename__ = "proposal_review_annotations"
    __table_args__ = (
        CheckConstraint(
            "finding_state IN ('confirmed', 'inferred', 'provisional', 'contradictory', "
            "'unknown', 'human_verification_required')",
            name="ck_proposal_review_annotation_finding_state",
        ),
        CheckConstraint(
            "length(trim(reason_code)) > 0",
            name="ck_proposal_review_annotation_reason_code",
        ),
        CheckConstraint(
            "proposal_only = true",
            name="ck_proposal_review_annotation_proposal_only",
        ),
        ForeignKeyConstraint(
            ["proposal_review_package_id"],
            ["proposal_review_packages.id"],
            name="fk_proposal_review_annotation_package",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["proposal_review_package_redaction_id"],
            ["proposal_review_package_redactions.id"],
            name="fk_proposal_review_annotation_redaction",
            ondelete="CASCADE",
        ),
        Index(
            "ix_proposal_review_annotation_package_recorded",
            "proposal_review_package_id",
            "recorded_at",
        ),
        Index(
            "ix_proposal_review_annotation_reviewer",
            "reviewed_by_user_id",
            "recorded_at",
        ),
    )

    annotation_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    proposal_review_package_id: Mapped[str] = mapped_column(String(36), nullable=False)
    proposal_review_package_redaction_id: Mapped[str | None] = mapped_column(String(36))
    package_manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_summary_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    annotation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(36))
    finding_state: Mapped[str] = mapped_column(String(40), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    proposal_only: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    reviewed_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

class ProposalReviewReaderAssignment(RecordMixin, Base):
    """An auditable active/revoked human-reader grant for one Project or package."""

    __tablename__ = "proposal_review_reader_assignments"
    __table_args__ = (
        CheckConstraint(
            "(scope_kind = 'project' AND project_id IS NOT NULL AND proposal_review_"
            "package_id IS NULL) OR (scope_kind = 'package' AND project_id IS NULL "
            "AND proposal_review_package_id IS NOT NULL)",
            name="ck_proposal_review_reader_assignment_scope",
        ),
        CheckConstraint(
            "(active = true AND revoked_by_user_id IS NULL AND revoked_at IS NULL "
            "AND revocation_reason_code IS NULL) OR "
            "(active = false AND revoked_by_user_id IS NOT NULL AND revoked_at IS NOT NULL "
            "AND revocation_reason_code IS NOT NULL)",
            name="ck_proposal_review_reader_assignment_lifecycle",
        ),
        UniqueConstraint(
            "user_id",
            "scope_kind",
            "project_id",
            name="uq_proposal_review_reader_assignment_project",
        ),
        UniqueConstraint(
            "user_id",
            "scope_kind",
            "proposal_review_package_id",
            name="uq_proposal_review_reader_assignment_package",
        ),
        Index("ix_proposal_review_reader_assignment_active_user", "active", "user_id"),
    )

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("projects.id"))
    proposal_review_package_id: Mapped[str | None] = mapped_column(
        ForeignKey("proposal_review_packages.id", ondelete="CASCADE")
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    granted_by_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_by_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocation_reason_code: Mapped[str | None] = mapped_column(String(100))

class TechnicalDocument(RecordMixin, Base):
    __tablename__ = "technical_documents"

    document_id: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    stored_file_id: Mapped[str] = mapped_column(ForeignKey("stored_files.id"), nullable=False)
    document_type: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(200), index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(300), index=True)
    revision: Mapped[str | None] = mapped_column(String(100))
    issuing_organisation: Mapped[str | None] = mapped_column(String(300))
    publication_date: Mapped[date | None] = mapped_column(Date)
    review_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    jurisdiction: Mapped[str | None] = mapped_column(String(200), index=True)
    standards: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    extraction_status: Mapped[str] = mapped_column(String(50), default="not_started")
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    supersedes_document_id: Mapped[str | None] = mapped_column(ForeignKey("technical_documents.id"))
    source_lineage_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    source_lineage_sha256: Mapped[str | None] = mapped_column(String(64))
    reviewed_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class DraftScope(RecordMixin, Base):
    """Owner-scoped Draft artifact; never a canonical physical-model write."""

    __tablename__ = "draft_scopes"
    __table_args__ = (CheckConstraint("latest_revision >= 0", name="ck_draft_scope_revision"),)

    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    latest_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    project: Mapped[Project] = relationship()


class DraftScopeRevision(RecordMixin, Base):
    """Append-only through the Draft Scope service, with verified serialized bytes."""

    __tablename__ = "draft_scope_revisions"
    __table_args__ = (
        UniqueConstraint("draft_scope_id", "revision", name="uq_draft_scope_revision"),
        CheckConstraint("revision >= 1", name="ck_draft_scope_positive_revision"),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftPdfSource(RecordMixin, Base):
    """Draft-owned retained PDF and scanner/normalization metadata, never approval."""

    __tablename__ = "draft_pdf_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_draft_pdf_source_bytes",
        ),
        UniqueConstraint("stored_file_id", name="uq_draft_pdf_source_file"),
        CheckConstraint("source_size_bytes > 0 AND source_size_bytes <= 10485760",
                        name="ck_draft_pdf_source_size"),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    scan_json: Mapped[str | None] = mapped_column(Text)
    processing_error: Mapped[str | None] = mapped_column(String(80))
    document_json: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))


class DraftPdfSuggestion(RecordMixin, Base):
    """Retained optional inference proposal; never a canonical model or approval."""

    __tablename__ = "draft_pdf_suggestions"
    __table_args__ = (
        CheckConstraint("base_revision >= 1", name="ck_draft_pdf_suggestion_revision"),
        CheckConstraint(
            "status IN ('pending', 'applied', 'rejected')",
            name="ck_draft_pdf_suggestion_status",
        ),
        CheckConstraint(
            "(status = 'applied' AND applied_revision IS NOT NULL "
            "AND applied_revision = base_revision + 1) OR "
            "(status != 'applied' AND applied_revision IS NULL)",
            name="ck_draft_pdf_suggestion_applied",
        ),
        CheckConstraint("length(proposal_json) <= 131072", name="ck_draft_pdf_suggestion_size"),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("draft_pdf_sources.id"), index=True)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    proposal_json: Mapped[str] = mapped_column(Text, nullable=False)
    proposal_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    applied_revision: Mapped[int | None] = mapped_column(Integer)


class DraftScopeXlsxSource(RecordMixin, Base):
    """Draft-owned defect XLSX and scan metadata, separate from pricing authority."""

    __tablename__ = "draft_scope_xlsx_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_draft_scope_xlsx_source_bytes",
        ),
        UniqueConstraint("stored_file_id", name="uq_draft_scope_xlsx_source_file"),
        CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="ck_draft_scope_xlsx_source_size",
        ),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    scan_json: Mapped[str | None] = mapped_column(Text)
    processing_error: Mapped[str | None] = mapped_column(String(80))
    document_json: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))


class DraftPricingSource(RecordMixin, Base):
    """Draft-owned retained pricing XLSX and scanner/normalization metadata, never approval."""

    __tablename__ = "draft_pricing_sources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_draft_pricing_source_bytes",
        ),
        UniqueConstraint("stored_file_id", name="uq_draft_pricing_source_file"),
        CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="ck_draft_pricing_source_size",
        ),
        CheckConstraint(
            "(dataset_id IS NULL AND dataset_kind IS NULL AND dataset_version IS NULL) OR "
            "(dataset_id IS NOT NULL AND dataset_kind IN "
            "('general_pricelist', 'firefly_system_prices') AND dataset_version >= 1)",
            name="ck_draft_pricing_source_dataset_identity",
        ),
        UniqueConstraint(
            "draft_scope_id",
            "dataset_kind",
            "dataset_version",
            name="uq_draft_pricing_source_dataset_version",
        ),
        UniqueConstraint(
            "dataset_id", "dataset_version", name="uq_draft_pricing_source_stable_version"
        ),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    scan_json: Mapped[str | None] = mapped_column(Text)
    processing_error: Mapped[str | None] = mapped_column(String(80))
    document_json: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    dataset_id: Mapped[str | None] = mapped_column(String(36), index=True)
    dataset_kind: Mapped[str | None] = mapped_column(String(32), index=True)
    dataset_version: Mapped[int | None] = mapped_column(Integer)


class DraftPricingSourceProfile(RecordMixin, Base):
    """Append-only unapproved interpretation of one exact Draft pricing source version."""

    __tablename__ = "draft_pricing_source_profiles"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "revision", name="uq_draft_pricing_source_profile_revision"
        ),
        CheckConstraint("revision >= 1", name="ck_draft_pricing_source_profile_revision"),
        CheckConstraint(
            "length(profile_json) > 0 AND length(profile_json) <= 131072",
            name="ck_draft_pricing_source_profile_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_sources.id"), index=True, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_profile_sha256: Mapped[str | None] = mapped_column(String(64))
    profile_json: Mapped[str] = mapped_column(Text, nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftPricingSourceProfileDecision(RecordMixin, Base):
    """Append-only human decision bound to one exact pricing source profile."""

    __tablename__ = "draft_pricing_source_profile_decisions"
    __table_args__ = (
        UniqueConstraint("profile_id", name="uq_draft_pricing_profile_decision_profile"),
        CheckConstraint(
            "profile_revision >= 1", name="ck_draft_pricing_profile_decision_revision"
        ),
        CheckConstraint(
            "decision IN ('approve', 'reject', 'request_revision')",
            name="ck_draft_pricing_profile_decision_value",
        ),
        CheckConstraint(
            "length(reason) > 0 AND length(reason) <= 4000",
            name="ck_draft_pricing_profile_decision_reason",
        ),
        CheckConstraint(
            "length(decision_json) > 0 AND length(decision_json) <= 16384",
            name="ck_draft_pricing_profile_decision_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_sources.id"), index=True, nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_source_profiles.id"), index=True, nullable=False
    )
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decision_json: Mapped[str] = mapped_column(Text, nullable=False)
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftPricingRowObservation(RecordMixin, Base):
    """Append-only human interpretation of one exact approved Dataset A row."""

    __tablename__ = "draft_pricing_row_observations"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "sheet_index",
            "row_number",
            name="uq_draft_pricing_row_observation_profile_row",
        ),
        CheckConstraint("profile_revision >= 1", name="ck_draft_pricing_row_observation_revision"),
        CheckConstraint(
            "sheet_index >= 1 AND sheet_index <= 10",
            name="ck_draft_pricing_row_observation_sheet",
        ),
        CheckConstraint(
            "row_number >= 2 AND row_number <= 1000",
            name="ck_draft_pricing_row_observation_row",
        ),
        CheckConstraint(
            "item_kind IN ('product', 'material', 'labour', 'service')",
            name="ck_draft_pricing_row_observation_kind",
        ),
        CheckConstraint(
            "evidence_state IN ('confirmed', 'provisional')",
            name="ck_draft_pricing_row_observation_evidence_state",
        ),
        CheckConstraint(
            "length(normalized_reference) > 0 AND length(normalized_reference) <= 300",
            name="ck_draft_pricing_row_observation_reference",
        ),
        CheckConstraint(
            "length(review_reason) > 0 AND length(review_reason) <= 4000",
            name="ck_draft_pricing_row_observation_reason",
        ),
        CheckConstraint(
            "length(observation_json) > 0 AND length(observation_json) <= 131072",
            name="ck_draft_pricing_row_observation_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_sources.id"), index=True, nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_source_profiles.id"), index=True, nullable=False
    )
    profile_decision_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_source_profile_decisions.id"), index=True, nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    item_kind: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    normalized_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    evidence_state: Mapped[str] = mapped_column(String(20), nullable=False)
    review_reason: Mapped[str] = mapped_column(Text, nullable=False)
    observation_json: Mapped[str] = mapped_column(Text, nullable=False)
    observation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftPricingSystemMapping(RecordMixin, Base):
    """Append-only human mapping of one exact Dataset B row to technical identity."""

    __tablename__ = "draft_pricing_system_mappings"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "sheet_index",
            "row_number",
            name="uq_draft_pricing_system_mapping_profile_row",
        ),
        CheckConstraint("profile_revision >= 1", name="ck_draft_pricing_system_mapping_revision"),
        CheckConstraint(
            "sheet_index >= 1 AND sheet_index <= 10",
            name="ck_draft_pricing_system_mapping_sheet",
        ),
        CheckConstraint(
            "row_number >= 2 AND row_number <= 1000",
            name="ck_draft_pricing_system_mapping_row",
        ),
        CheckConstraint(
            "mapping_status IN ('mapped', 'unmatched', 'ambiguous')",
            name="ck_draft_pricing_system_mapping_status",
        ),
        CheckConstraint(
            "(mapping_status = 'mapped' AND technical_variant_id IS NOT NULL "
            "AND technical_variant_snapshot_sha256 IS NOT NULL) OR "
            "(mapping_status IN ('unmatched', 'ambiguous') AND technical_variant_id IS NULL "
            "AND technical_variant_snapshot_sha256 IS NULL)",
            name="ck_draft_pricing_system_mapping_variant",
        ),
        CheckConstraint(
            "length(normalized_reference) > 0 AND length(normalized_reference) <= 300",
            name="ck_draft_pricing_system_mapping_reference",
        ),
        CheckConstraint(
            "length(review_reason) > 0 AND length(review_reason) <= 4000",
            name="ck_draft_pricing_system_mapping_reason",
        ),
        CheckConstraint(
            "length(mapping_json) > 0 AND length(mapping_json) <= 524288",
            name="ck_draft_pricing_system_mapping_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_sources.id"), index=True, nullable=False
    )
    profile_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_source_profiles.id"), index=True, nullable=False
    )
    profile_decision_id: Mapped[str] = mapped_column(
        ForeignKey("draft_pricing_source_profile_decisions.id"), index=True, nullable=False
    )
    dataset_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    dataset_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_status: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    normalized_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    review_reason: Mapped[str] = mapped_column(Text, nullable=False)
    technical_release_id: Mapped[str] = mapped_column(
        ForeignKey("library_releases.id"), index=True, nullable=False
    )
    technical_release_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    technical_variant_id: Mapped[str | None] = mapped_column(
        ForeignKey("technical_variants.id"), index=True
    )
    technical_variant_snapshot_sha256: Mapped[str | None] = mapped_column(String(64))
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewed_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftPricingEvaluationRoster(RecordMixin, Base):
    """Append-only target-blind pricing evaluation split roster."""

    __tablename__ = "draft_pricing_evaluation_rosters"
    __table_args__ = (
        UniqueConstraint(
            "draft_scope_id",
            "revision",
            name="uq_draft_pricing_evaluation_roster_revision",
        ),
        CheckConstraint(
            "revision >= 1", name="ck_draft_pricing_evaluation_roster_revision"
        ),
        CheckConstraint(
            "length(roster_json) > 0 AND length(roster_json) <= 1048576",
            name="ck_draft_pricing_evaluation_roster_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_id: Mapped[str] = mapped_column(String(36), nullable=False)
    parent_manifest_sha256: Mapped[str | None] = mapped_column(String(64))
    mapping_inventory_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    roster_json: Mapped[str] = mapped_column(Text, nullable=False)
    roster_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftScopeReport(RecordMixin, Base):
    """Retained scope-only Draft snapshot and its two exact rendered outputs."""

    __tablename__ = "draft_scope_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_scope_report_revision",
        ),
        CheckConstraint("scope_revision >= 1", name="ck_draft_scope_report_revision"),
        CheckConstraint(
            "length(pdf_bytes) > 0 AND length(pdf_bytes) <= 8388608",
            name="ck_draft_scope_report_pdf_size",
        ),
        CheckConstraint(
            "length(xlsx_bytes) > 0 AND length(xlsx_bytes) <= 8388608",
            name="ck_draft_scope_report_xlsx_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(
        ForeignKey("draft_scopes.id"), index=True, nullable=False
    )
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    xlsx_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    xlsx_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class DraftSystemMatch(RecordMixin, Base):
    """One selected Draft Scope target and release, with immutable review revisions."""

    __tablename__ = "draft_system_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_system_match_scope_revision",
        ),
        CheckConstraint(
            "(release_id IS NOT NULL AND import_id IS NULL) OR "
            "(release_id IS NULL AND import_id IS NOT NULL)",
            name="ck_draft_match_origin",
        ),
        CheckConstraint("scope_revision >= 1", name="ck_draft_system_match_scope_revision"),
        CheckConstraint("latest_revision >= 0", name="ck_draft_system_match_revision"),
    )

    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    release_id: Mapped[str | None] = mapped_column(ForeignKey("library_releases.id"))
    import_id: Mapped[str | None] = mapped_column(ForeignKey("draft_package_imports.id"))
    release_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    latest_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latest_hash: Mapped[str | None] = mapped_column(String(64))
    basis_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftSystemMatchRevision(RecordMixin, Base):
    __tablename__ = "draft_system_match_revisions"
    __table_args__ = (
        UniqueConstraint("match_id", "revision", name="uq_draft_system_match_revision"),
        CheckConstraint("revision >= 1", name="ck_draft_system_match_saved_revision"),
    )

    match_id: Mapped[str] = mapped_column(ForeignKey("draft_system_matches.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftEstimate(RecordMixin, Base):
    """Independent manual estimate bound to saved Draft inputs, never a canonical Estimate."""

    __tablename__ = "draft_estimates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_estimate_scope_revision",
        ),
        ForeignKeyConstraint(
            ["match_id", "match_revision"],
            ["draft_system_match_revisions.match_id", "draft_system_match_revisions.revision"],
            name="fk_draft_estimate_match_revision",
        ),
        CheckConstraint("scope_revision >= 1", name="ck_draft_estimate_scope_revision"),
        CheckConstraint("latest_revision >= 0", name="ck_draft_estimate_revision"),
        CheckConstraint(
            "(match_id IS NULL AND match_revision IS NULL AND match_hash IS NULL) OR "
            "(match_id IS NOT NULL AND match_revision IS NOT NULL "
            "AND match_revision >= 1 AND match_hash IS NOT NULL)",
            name="ck_draft_estimate_match_binding",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    import_id: Mapped[str | None] = mapped_column(ForeignKey("draft_package_imports.id"))
    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    match_id: Mapped[str | None] = mapped_column(ForeignKey("draft_system_matches.id"))
    match_revision: Mapped[int | None] = mapped_column(Integer)
    match_hash: Mapped[str | None] = mapped_column(String(64))
    latest_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latest_hash: Mapped[str | None] = mapped_column(String(64))
    basis_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftEstimateRevision(RecordMixin, Base):
    __tablename__ = "draft_estimate_revisions"
    __table_args__ = (
        UniqueConstraint("estimate_id", "revision", name="uq_draft_estimate_revision"),
        CheckConstraint("revision >= 1", name="ck_draft_estimate_saved_revision"),
    )

    estimate_id: Mapped[str] = mapped_column(ForeignKey("draft_estimates.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_hash: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftEstimateReport(RecordMixin, Base):
    """Retained estimate-only Draft snapshot and exact PDF/XLSX pair."""

    __tablename__ = "draft_estimate_reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["estimate_id", "estimate_revision"],
            ["draft_estimate_revisions.estimate_id", "draft_estimate_revisions.revision"],
            name="fk_draft_estimate_report_revision",
        ),
        CheckConstraint("estimate_revision >= 1", name="ck_draft_estimate_report_revision"),
        CheckConstraint(
            "length(pdf_bytes) > 0 AND length(pdf_bytes) <= 8388608",
            name="ck_draft_estimate_report_pdf_size",
        ),
        CheckConstraint(
            "length(xlsx_bytes) > 0 AND length(xlsx_bytes) <= 8388608",
            name="ck_draft_estimate_report_xlsx_size",
        ),
    )

    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    estimate_id: Mapped[str] = mapped_column(ForeignKey("draft_estimates.id"), index=True)
    estimate_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    estimate_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    pdf_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pdf_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    xlsx_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    xlsx_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class DraftPackageImport(RecordMixin, Base):
    """Immutable foreign archive and local identity map; never source/library authority."""
    __tablename__ = "draft_package_imports"
    __table_args__ = (
        UniqueConstraint("draft_scope_id", name="uq_draft_import_scope"),
        CheckConstraint("length(archive_bytes) > 0 AND length(archive_bytes) <= 134217728",
                        name="ck_draft_import_size"),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    archive_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    archive_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_json: Mapped[str] = mapped_column(Text, nullable=False)
    mapping_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)


class DraftImportedReportSource(RecordMixin, Base):
    """Draft-owned original report bytes using the shared scan/quarantine lifecycle."""
    __tablename__ = "draft_imported_report_sources"
    __table_args__ = (
        UniqueConstraint("draft_scope_id", "stored_file_id", name="uq_import_report_file"),
        ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_imported_report_source_bytes",
        ),
        CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="ck_imported_report_source_size",
        ),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    stored_file_id: Mapped[str] = mapped_column(String(36), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    scan_json: Mapped[str | None] = mapped_column(Text)
    document_json: Mapped[str | None] = mapped_column(Text)
    document_sha256: Mapped[str | None] = mapped_column(String(64))
    processing_error: Mapped[str | None] = mapped_column(String(80))


class DraftProjectPackage(RecordMixin, Base):
    """Immutable selected Draft artifacts; never canonical or imported authority."""

    __tablename__ = "draft_project_packages"
    __table_args__ = (
        UniqueConstraint("draft_scope_id", "revision", name="uq_draft_package_revision"),
        CheckConstraint("revision >= 1", name="ck_draft_package_revision"),
        CheckConstraint("length(archive_bytes) > 0 AND length(archive_bytes) <= 134217728",
                        name="ck_draft_package_size"),
    )
    draft_scope_id: Mapped[str] = mapped_column(ForeignKey("draft_scopes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_hash: Mapped[str | None] = mapped_column(String(64))
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    manifest_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    archive_bytes: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    archive_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class DraftClientRequest(RecordMixin, Base):
    """A client's proposal; only a separate human session can execute it."""

    __tablename__ = "draft_client_requests"
    owner_user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    command: Mapped[str] = mapped_column(String(30), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    identity_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        CheckConstraint(
            "command IN ('create', 'edit', 'package', 'capability')", name="ck_client_command"
        ),
        CheckConstraint("status IN ('pending', 'confirmed', 'rejected')", name="ck_client_status"),
        CheckConstraint("length(payload_json) <= 1048576", name="ck_client_payload_size"),
    )


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
