"""Link explicit native proposal decisions to saved Scope revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_draft_proposal_decisions"
down_revision = "0048_draft_workspace_proposals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_workspace_proposal_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("draft_workspace_proposals.id"),
            nullable=False,
        ),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("scope_revision_id", sa.String(36), sa.ForeignKey("draft_scope_revisions.id")),
        sa.Column("decision_json", sa.Text(), nullable=False),
        sa.Column("decision_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint("proposal_id", name="uq_workspace_proposal_decision"),
        sa.CheckConstraint(
            "(outcome = 'confirmed' AND scope_revision_id IS NOT NULL) OR "
            "(outcome = 'rejected' AND scope_revision_id IS NULL)",
            name="ck_workspace_decision_outcome",
        ),
        sa.CheckConstraint("length(decision_json) <= 16384", name="ck_workspace_decision_size"),
    )
    op.create_index(
        "ix_draft_workspace_proposal_decisions_created_by_id",
        "draft_workspace_proposal_decisions",
        ["created_by_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Retained native proposal decisions cannot be downgraded")
