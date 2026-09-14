"""Explicit native proposal retention without Scope execution authority."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_draft_workspace_proposals"
down_revision = "0047_draft_scope_docx_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_workspace_proposals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("proposal_json", sa.Text(), nullable=False),
        sa.Column("proposal_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("base_revision >= 1", name="ck_workspace_proposal_revision"),
        sa.CheckConstraint("length(proposal_json) <= 1048576", name="ck_workspace_proposal_size"),
    )
    for column in ("draft_scope_id", "created_by_id"):
        op.create_index(
            "ix_draft_workspace_proposals_" + column, "draft_workspace_proposals", [column]
        )


def downgrade() -> None:
    raise RuntimeError("Retained native proposal history cannot be downgraded")
