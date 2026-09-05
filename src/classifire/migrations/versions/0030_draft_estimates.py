"""Persist independent manual Draft Estimate revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_draft_estimates"
down_revision = "0029_draft_system_matches"
branch_labels = None
depends_on = None


def _common_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "draft_estimates",
        *_common_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column("match_id", sa.String(36), sa.ForeignKey("draft_system_matches.id")),
        sa.Column("match_revision", sa.Integer()),
        sa.Column("match_hash", sa.String(64)),
        sa.Column("latest_revision", sa.Integer(), nullable=False),
        sa.Column("latest_hash", sa.String(64)),
        sa.Column("basis_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_estimate_scope_revision",
        ),
        sa.ForeignKeyConstraint(
            ["match_id", "match_revision"],
            ["draft_system_match_revisions.match_id", "draft_system_match_revisions.revision"],
            name="fk_draft_estimate_match_revision",
        ),
        sa.CheckConstraint(
            "(match_id IS NULL AND match_revision IS NULL AND match_hash IS NULL) OR "
            "(match_id IS NOT NULL AND match_revision IS NOT NULL "
            "AND match_revision >= 1 AND match_hash IS NOT NULL)",
            name="ck_draft_estimate_match_binding",
        ),
        sa.CheckConstraint("scope_revision >= 1", name="ck_draft_estimate_scope_revision"),
        sa.CheckConstraint("latest_revision >= 0", name="ck_draft_estimate_revision"),
    )
    op.create_index("ix_draft_estimates_draft_scope_id", "draft_estimates", ["draft_scope_id"])
    op.create_table(
        "draft_estimate_revisions",
        *_common_columns(),
        sa.Column(
            "estimate_id", sa.String(36), sa.ForeignKey("draft_estimates.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("estimate_id", "revision", name="uq_draft_estimate_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_draft_estimate_saved_revision"),
    )
    op.create_index(
        "ix_draft_estimate_revisions_estimate_id", "draft_estimate_revisions", ["estimate_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft Estimates cannot be downgraded")
