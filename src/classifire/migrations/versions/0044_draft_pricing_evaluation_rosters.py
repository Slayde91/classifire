"""Retain immutable target-blind pricing evaluation rosters."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_draft_pricing_evaluation_rosters"
down_revision = "0043_draft_pricing_system_mappings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pricing_evaluation_rosters",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id",
            sa.String(36),
            sa.ForeignKey("draft_scopes.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("manifest_id", sa.String(36), nullable=False),
        sa.Column("parent_manifest_sha256", sa.String(64), nullable=True),
        sa.Column("mapping_inventory_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("feature_cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("roster_json", sa.Text(), nullable=False),
        sa.Column("roster_sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "draft_scope_id",
            "revision",
            name="uq_draft_pricing_evaluation_roster_revision",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_draft_pricing_evaluation_roster_revision",
        ),
        sa.CheckConstraint(
            "length(roster_json) > 0 AND length(roster_json) <= 1048576",
            name="ck_draft_pricing_evaluation_roster_size",
        ),
    )
    op.create_index(
        "ix_draft_pricing_evaluation_rosters_draft_scope_id",
        "draft_pricing_evaluation_rosters",
        ["draft_scope_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing evaluation rosters cannot be downgraded")
