"""Retain explicit human-approved families of retained report evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_report_evidence_family_manifests"
down_revision = "0018_docx_report_evidence_locators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_evidence_family_manifests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("family_reference", sa.String(150), nullable=False),
        sa.Column("member_count", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("approval_reference", sa.String(500), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(family_reference)) > 0",
            name="ck_report_evidence_family_manifest_reference",
        ),
        sa.CheckConstraint(
            "length(trim(approval_reference)) > 0",
            name="ck_report_evidence_family_manifest_approval_reference",
        ),
        sa.CheckConstraint(
            "member_count >= 2",
            name="ck_report_evidence_family_manifest_member_count",
        ),
        sa.UniqueConstraint(
            "estimate_id",
            "manifest_sha256",
            "approval_reference",
            "approved_by_user_id",
            name="uq_report_evidence_family_manifest_approval",
        ),
    )
    op.create_index(
        "ix_report_evidence_family_manifest_estimate_id",
        "report_evidence_family_manifests",
        ["estimate_id"],
    )
    op.create_table(
        "report_evidence_family_members",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("report_evidence_family_manifest_id", sa.String(36), nullable=False),
        sa.Column("member_sequence", sa.Integer(), nullable=False),
        sa.Column("project_evidence_id", sa.String(36), nullable=False),
        sa.Column(
            "stored_file_id",
            sa.String(36),
            sa.ForeignKey("stored_files.id"),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "member_sequence > 0",
            name="ck_report_evidence_family_member_sequence",
        ),
        sa.ForeignKeyConstraint(
            ["report_evidence_family_manifest_id"],
            ["report_evidence_family_manifests.id"],
            name="fk_report_evidence_family_member_manifest",
        ),
        sa.ForeignKeyConstraint(
            ["project_evidence_id", "source_sha256"],
            ["project_evidence.id", "project_evidence.source_sha256"],
            name="fk_report_evidence_family_member_source",
        ),
        sa.UniqueConstraint(
            "report_evidence_family_manifest_id",
            "member_sequence",
            name="uq_report_evidence_family_member_sequence",
        ),
        sa.UniqueConstraint(
            "report_evidence_family_manifest_id",
            "project_evidence_id",
            name="uq_report_evidence_family_member_source",
        ),
    )
    op.create_index(
        "ix_report_evidence_family_member_project_evidence_id",
        "report_evidence_family_members",
        ["project_evidence_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Approved report evidence families cannot be downgraded")