"""Retain immutable reviewed Dataset B price-to-system mappings."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_draft_pricing_system_mappings"
down_revision = "0042_draft_pricing_row_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_pricing_system_mappings",
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
        sa.Column(
            "profile_decision_id",
            sa.String(36),
            sa.ForeignKey("draft_pricing_source_profile_decisions.id"),
            nullable=False,
        ),
        sa.Column("dataset_id", sa.String(36), nullable=False),
        sa.Column("dataset_version", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("profile_revision", sa.Integer(), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("decision_sha256", sa.String(64), nullable=False),
        sa.Column("sheet_index", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("row_sha256", sa.String(64), nullable=False),
        sa.Column("mapping_status", sa.String(20), nullable=False),
        sa.Column("normalized_reference", sa.String(300), nullable=False),
        sa.Column("review_reason", sa.Text(), nullable=False),
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
            nullable=True,
        ),
        sa.Column("technical_variant_snapshot_sha256", sa.String(64), nullable=True),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("mapping_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint(
            "profile_id",
            "sheet_index",
            "row_number",
            name="uq_draft_pricing_system_mapping_profile_row",
        ),
        sa.CheckConstraint(
            "profile_revision >= 1", name="ck_draft_pricing_system_mapping_revision"
        ),
        sa.CheckConstraint(
            "sheet_index >= 1 AND sheet_index <= 10",
            name="ck_draft_pricing_system_mapping_sheet",
        ),
        sa.CheckConstraint(
            "row_number >= 2 AND row_number <= 1000",
            name="ck_draft_pricing_system_mapping_row",
        ),
        sa.CheckConstraint(
            "mapping_status IN ('mapped', 'unmatched', 'ambiguous')",
            name="ck_draft_pricing_system_mapping_status",
        ),
        sa.CheckConstraint(
            "(mapping_status = 'mapped' AND technical_variant_id IS NOT NULL "
            "AND technical_variant_snapshot_sha256 IS NOT NULL) OR "
            "(mapping_status IN ('unmatched', 'ambiguous') AND technical_variant_id IS NULL "
            "AND technical_variant_snapshot_sha256 IS NULL)",
            name="ck_draft_pricing_system_mapping_variant",
        ),
        sa.CheckConstraint(
            "length(normalized_reference) > 0 AND length(normalized_reference) <= 300",
            name="ck_draft_pricing_system_mapping_reference",
        ),
        sa.CheckConstraint(
            "length(review_reason) > 0 AND length(review_reason) <= 4000",
            name="ck_draft_pricing_system_mapping_reason",
        ),
        sa.CheckConstraint(
            "length(mapping_json) > 0 AND length(mapping_json) <= 524288",
            name="ck_draft_pricing_system_mapping_size",
        ),
    )
    for column in (
        "draft_scope_id",
        "source_id",
        "profile_id",
        "profile_decision_id",
        "dataset_id",
        "mapping_status",
        "technical_release_id",
        "technical_variant_id",
    ):
        op.create_index(
            f"ix_draft_pricing_system_mappings_{column}",
            "draft_pricing_system_mappings",
            [column],
        )


def downgrade() -> None:
    raise RuntimeError("Retained Draft pricing system mappings cannot be downgraded")
