"""Classify Draft pricing datasets and retain append-only source profile revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_draft_pricing_source_profiles"
down_revision = "0039_draft_pdf_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("draft_pricing_sources") as batch:
        batch.add_column(sa.Column("dataset_id", sa.String(36)))
        batch.add_column(sa.Column("dataset_kind", sa.String(32)))
        batch.add_column(sa.Column("dataset_version", sa.Integer()))
        batch.create_check_constraint(
            "ck_draft_pricing_source_dataset_identity",
            "(dataset_id IS NULL AND dataset_kind IS NULL AND dataset_version IS NULL) OR "
            "(dataset_id IS NOT NULL AND dataset_kind IN "
            "('general_pricelist', 'firefly_system_prices') AND dataset_version >= 1)",
        )
        batch.create_unique_constraint(
            "uq_draft_pricing_source_dataset_version",
            ["draft_scope_id", "dataset_kind", "dataset_version"],
        )
        batch.create_unique_constraint(
            "uq_draft_pricing_source_stable_version", ["dataset_id", "dataset_version"]
        )
    op.create_index(
        "ix_draft_pricing_sources_dataset_id", "draft_pricing_sources", ["dataset_id"]
    )
    op.create_index(
        "ix_draft_pricing_sources_dataset_kind", "draft_pricing_sources", ["dataset_kind"]
    )
    op.create_table(
        "draft_pricing_source_profiles",
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
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_profile_sha256", sa.String(64)),
        sa.Column("profile_json", sa.Text(), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint(
            "source_id", "revision", name="uq_draft_pricing_source_profile_revision"
        ),
        sa.CheckConstraint("revision >= 1", name="ck_draft_pricing_source_profile_revision"),
        sa.CheckConstraint(
            "length(profile_json) > 0 AND length(profile_json) <= 131072",
            name="ck_draft_pricing_source_profile_size",
        ),
    )
    for column in ("draft_scope_id", "source_id"):
        op.create_index(
            f"ix_draft_pricing_source_profiles_{column}",
            "draft_pricing_source_profiles",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing source profiles cannot be downgraded")
