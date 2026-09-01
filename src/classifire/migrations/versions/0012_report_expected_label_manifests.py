"""Retain human-approved expected Defect-label manifests for project reports."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_report_expected_label_manifests"
down_revision = "0011_report_evidence_locators"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_expected_label_manifests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("project_evidence_id", sa.String(36), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("expected_report_defect_labels", sa.JSON(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("approval_reference", sa.String(500), nullable=False),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "length(trim(approval_reference)) > 0",
            name="ck_report_expected_label_manifest_approval_reference",
        ),
        sa.ForeignKeyConstraint(
            ["project_evidence_id", "source_sha256"],
            ["project_evidence.id", "project_evidence.source_sha256"],
            name="fk_report_expected_label_manifest_source",
        ),
        sa.UniqueConstraint(
            "project_evidence_id",
            "manifest_sha256",
            "approval_reference",
            "approved_by_user_id",
            name="uq_report_expected_label_manifest_approval",
        ),
    )
    op.create_index(
        "ix_report_expected_label_manifest_estimate_id",
        "report_expected_label_manifests",
        ["estimate_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Approved report label manifests cannot be downgraded")
