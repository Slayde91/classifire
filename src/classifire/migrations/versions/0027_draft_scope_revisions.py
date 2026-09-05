"""Owner-scoped manual Draft Scope artifacts and append-only revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0027_draft_scope_revisions"
down_revision = "0026_single_active_technical_release"
branch_labels = None
depends_on = None


def _record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "draft_scopes",
        *_record_columns(),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("latest_revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("latest_revision >= 0", name="ck_draft_scope_revision"),
    )
    op.create_index("ix_draft_scopes_project_id", "draft_scopes", ["project_id"])
    op.create_index("ix_draft_scopes_owner_user_id", "draft_scopes", ["owner_user_id"])
    op.create_table(
        "draft_scope_revisions",
        *_record_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("draft_scope_id", "revision", name="uq_draft_scope_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_draft_scope_positive_revision"),
    )
    op.create_index(
        "ix_draft_scope_revisions_draft_scope_id", "draft_scope_revisions", ["draft_scope_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft Scope revision history cannot be downgraded")
