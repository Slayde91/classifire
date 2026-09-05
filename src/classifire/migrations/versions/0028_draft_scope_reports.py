"""Retain atomic Draft Scope PDF/XLSX report pairs and their frozen snapshot."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_draft_scope_reports"
down_revision = "0027_draft_scope_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_scope_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("pdf_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("pdf_sha256", sa.String(64), nullable=False),
        sa.Column("xlsx_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("xlsx_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_scope_report_revision",
        ),
        sa.CheckConstraint("scope_revision >= 1", name="ck_draft_scope_report_revision"),
        sa.CheckConstraint(
            "length(pdf_bytes) > 0 AND length(pdf_bytes) <= 8388608",
            name="ck_draft_scope_report_pdf_size",
        ),
        sa.CheckConstraint(
            "length(xlsx_bytes) > 0 AND length(xlsx_bytes) <= 8388608",
            name="ck_draft_scope_report_xlsx_size",
        ),
    )
    op.create_index(
        "ix_draft_scope_reports_draft_scope_id", "draft_scope_reports", ["draft_scope_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft Scope reports cannot be downgraded")
