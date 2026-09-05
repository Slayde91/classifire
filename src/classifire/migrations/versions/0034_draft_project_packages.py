"""Retain selected Draft project packages and exact archive revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_draft_project_packages"
down_revision = "0033_draft_pricing_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_project_packages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_hash", sa.String(64)),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("archive_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("archive_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("draft_scope_id", "revision", name="uq_draft_package_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_draft_package_revision"),
        sa.CheckConstraint(
            "length(archive_bytes) > 0 AND length(archive_bytes) <= 67108864",
            name="ck_draft_package_size",
        ),
    )
    op.create_index(
        "ix_draft_project_packages_draft_scope_id", "draft_project_packages", ["draft_scope_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft project packages cannot be downgraded")
