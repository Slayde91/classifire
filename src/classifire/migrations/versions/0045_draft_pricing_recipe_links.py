"""Retain immutable reviewed Dataset A links to frozen technical recipes."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_draft_pricing_recipe_links"
down_revision = "0044_draft_pricing_evaluation_rosters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pricing_recipe_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column(
            "technical_release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=False,
        ),
        sa.Column("technical_release_sha256", sa.String(64), nullable=False),
        sa.Column(
            "technical_variant_id",
            sa.String(36),
            sa.ForeignKey("technical_variants.id"),
            nullable=False,
        ),
        sa.Column("technical_variant_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("recipe_snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("requirement_id", sa.String(64), nullable=False),
        sa.Column("requirement_kind", sa.String(20), nullable=False),
        sa.Column("requirement_path", sa.String(500), nullable=False),
        sa.Column("mapping_status", sa.String(20), nullable=False),
        sa.Column("evidence_state", sa.String(20), nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.Column("link_json", sa.Text(), nullable=False),
        sa.Column("link_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("definition_sha256", name="uq_draft_pricing_recipe_link_definition"),
        sa.CheckConstraint(
            "mapping_status IN ('linked', 'unresolved')", name="ck_draft_pricing_recipe_link_status"
        ),
        sa.CheckConstraint(
            "evidence_state IN ('confirmed', 'provisional', 'unresolved')",
            name="ck_draft_pricing_recipe_link_evidence",
        ),
        sa.CheckConstraint(
            "length(link_json) > 0 AND length(link_json) <= 1048576",
            name="ck_draft_pricing_recipe_link_size",
        ),
    )
    for column in (
        "draft_scope_id",
        "technical_release_id",
        "technical_variant_id",
        "requirement_id",
        "mapping_status",
    ):
        op.create_index(
            f"ix_draft_pricing_recipe_links_{column}", "draft_pricing_recipe_links", [column]
        )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing recipe links cannot be downgraded")
