"""Retain optional Draft PDF suggestions separately from reviewed Scope revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_draft_pdf_suggestions"
down_revision = "0038_draft_scope_xlsx_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pdf_suggestions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column(
            "source_id", sa.String(36), sa.ForeignKey("draft_pdf_sources.id"), nullable=False
        ),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("proposal_json", sa.Text(), nullable=False),
        sa.Column("proposal_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("applied_revision", sa.Integer()),
        sa.CheckConstraint("base_revision >= 1", name="ck_draft_pdf_suggestion_revision"),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'rejected')", name="ck_draft_pdf_suggestion_status"
        ),
        sa.CheckConstraint(
            "(status = 'applied' AND applied_revision IS NOT NULL "
            "AND applied_revision = base_revision + 1) OR "
            "(status != 'applied' AND applied_revision IS NULL)",
            name="ck_draft_pdf_suggestion_applied",
        ),
        sa.CheckConstraint("length(proposal_json) <= 131072", name="ck_draft_pdf_suggestion_size"),
    )
    for column in ("draft_scope_id", "source_id"):
        op.create_index(f"ix_draft_pdf_suggestions_{column}", "draft_pdf_suggestions", [column])


def downgrade() -> None:
    raise RuntimeError("Retained Draft PDF suggestions cannot be downgraded")
