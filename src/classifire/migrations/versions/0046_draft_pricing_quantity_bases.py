"""Retain immutable Scope-bound quantities for frozen pricing requirements."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0046_draft_pricing_quantity_bases"
down_revision = "0045_draft_pricing_recipe_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pricing_quantity_bases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("scope_sha256", sa.String(64), nullable=False),
        sa.Column("scope_service_id", sa.String(64), nullable=False),
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
        sa.Column(
            "recipe_link_id",
            sa.String(36),
            sa.ForeignKey("draft_pricing_recipe_links.id"),
            nullable=False,
        ),
        sa.Column("recipe_link_sha256", sa.String(64), nullable=False),
        sa.Column("requirement_id", sa.String(64), nullable=False),
        sa.Column("requirement_kind", sa.String(20), nullable=False),
        sa.Column("requirement_path", sa.String(500), nullable=False),
        sa.Column("quantity", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.Column("basis_json", sa.Text(), nullable=False),
        sa.Column("basis_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_pricing_quantity_basis_scope_revision",
        ),
        sa.UniqueConstraint("definition_sha256", name="uq_draft_pricing_quantity_basis_definition"),
        sa.CheckConstraint("scope_revision >= 1", name="ck_draft_pricing_quantity_basis_revision"),
        sa.CheckConstraint(
            "unit IN ('each', 'm', 'mm')", name="ck_draft_pricing_quantity_basis_unit"
        ),
        sa.CheckConstraint(
            "length(quantity) > 0 AND length(quantity) <= 32",
            name="ck_draft_pricing_quantity_basis_quantity",
        ),
        sa.CheckConstraint(
            "length(basis_json) > 0 AND length(basis_json) <= 1048576",
            name="ck_draft_pricing_quantity_basis_size",
        ),
    )
    for column in (
        "draft_scope_id",
        "scope_service_id",
        "technical_release_id",
        "technical_variant_id",
        "recipe_link_id",
        "requirement_id",
    ):
        op.create_index(
            f"ix_draft_pricing_quantity_bases_{column}",
            "draft_pricing_quantity_bases",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing quantity bases cannot be downgraded")
