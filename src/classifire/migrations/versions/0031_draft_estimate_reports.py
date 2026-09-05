"""Retain independent Draft Estimate report snapshots and exact outputs."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_draft_estimate_reports"
down_revision = "0030_draft_estimates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_estimate_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column(
            "estimate_id", sa.String(36), sa.ForeignKey("draft_estimates.id"), nullable=False
        ),
        sa.Column("estimate_revision", sa.Integer(), nullable=False),
        sa.Column("estimate_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("xlsx_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("xlsx_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["estimate_id", "estimate_revision"],
            ["draft_estimate_revisions.estimate_id", "draft_estimate_revisions.revision"],
            name="fk_draft_estimate_report_revision",
        ),
        sa.CheckConstraint("estimate_revision >= 1", name="ck_draft_estimate_report_revision"),
        sa.CheckConstraint(
            "length(pdf_bytes) > 0 AND length(pdf_bytes) <= 8388608",
            name="ck_draft_estimate_report_pdf_size",
        ),
        sa.CheckConstraint(
            "length(xlsx_bytes) > 0 AND length(xlsx_bytes) <= 8388608",
            name="ck_draft_estimate_report_xlsx_size",
        ),
    )
    for column in ("draft_scope_id", "estimate_id"):
        op.create_index("ix_draft_estimate_reports_" + column, "draft_estimate_reports", [column])


def downgrade() -> None:
    raise RuntimeError("Retained Draft Estimate reports cannot be downgraded")
