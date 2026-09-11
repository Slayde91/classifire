"""Retain Draft-owned defect DOCX sources separately from pricing sources."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_draft_scope_docx_sources"
down_revision = "0046_draft_pricing_quantity_bases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_scope_docx_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("stored_file_id", sa.String(36), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_filename", sa.String(200), nullable=False),
        sa.Column("scan_json", sa.Text()),
        sa.Column("processing_error", sa.String(80)),
        sa.Column("document_json", sa.Text()),
        sa.Column("document_sha256", sa.String(64)),
        sa.ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_draft_scope_docx_source_bytes",
        ),
        sa.UniqueConstraint("stored_file_id", name="uq_draft_scope_docx_source_file"),
        sa.CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="ck_draft_scope_docx_source_size",
        ),
    )
    op.create_index(
        "ix_draft_scope_docx_sources_draft_scope_id", "draft_scope_docx_sources", ["draft_scope_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft Scope DOCX sources cannot be downgraded")
