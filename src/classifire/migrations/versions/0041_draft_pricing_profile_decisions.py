"""Retain immutable human decisions for exact Draft pricing profiles."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_draft_pricing_profile_decisions"
down_revision = "0040_draft_pricing_source_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pricing_source_profile_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("draft_pricing_sources.id"),
            nullable=False,
        ),
        sa.Column(
            "profile_id",
            sa.String(36),
            sa.ForeignKey("draft_pricing_source_profiles.id"),
            nullable=False,
        ),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decision_json", sa.Text(), nullable=False),
        sa.Column("decision_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("profile_id", name="uq_draft_pricing_profile_decision_profile"),
        sa.CheckConstraint(
            "profile_revision >= 1", name="ck_draft_pricing_profile_decision_revision"
        ),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject', 'request_revision')",
            name="ck_draft_pricing_profile_decision_value",
        ),
        sa.CheckConstraint(
            "length(reason) > 0 AND length(reason) <= 4000",
            name="ck_draft_pricing_profile_decision_reason",
        ),
        sa.CheckConstraint(
            "length(decision_json) > 0 AND length(decision_json) <= 16384",
            name="ck_draft_pricing_profile_decision_size",
        ),
    )
    for column in ("draft_scope_id", "source_id", "profile_id"):
        op.create_index(
            f"ix_draft_pricing_source_profile_decisions_{column}",
            "draft_pricing_source_profile_decisions",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing profile decisions cannot be downgraded")
