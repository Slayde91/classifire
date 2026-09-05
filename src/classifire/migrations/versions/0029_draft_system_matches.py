"""Persist independent, unapproved technical candidate review revisions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_draft_system_matches"
down_revision = "0028_draft_scope_reports"
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
        "draft_system_matches",
        *_common_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("scope_revision", sa.Integer(), nullable=False),
        sa.Column("scope_hash", sa.String(64), nullable=False),
        sa.Column(
            "release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=False
        ),
        sa.Column("release_hash", sa.String(64), nullable=False),
        sa.Column("latest_revision", sa.Integer(), nullable=False),
        sa.Column("latest_hash", sa.String(64)),
        sa.Column("basis_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(
            ["draft_scope_id", "scope_revision"],
            ["draft_scope_revisions.draft_scope_id", "draft_scope_revisions.revision"],
            name="fk_draft_system_match_scope_revision",
        ),
        sa.CheckConstraint("scope_revision >= 1", name="ck_draft_system_match_scope_revision"),
        sa.CheckConstraint("latest_revision >= 0", name="ck_draft_system_match_revision"),
    )
    op.create_index(
        "ix_draft_system_matches_draft_scope_id", "draft_system_matches", ["draft_scope_id"]
    )
    op.create_table(
        "draft_system_match_revisions",
        *_common_columns(),
        sa.Column(
            "match_id", sa.String(36), sa.ForeignKey("draft_system_matches.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("match_id", "revision", name="uq_draft_system_match_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_draft_system_match_saved_revision"),
    )
    op.create_index(
        "ix_draft_system_match_revisions_match_id", "draft_system_match_revisions", ["match_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft System Match reviews cannot be downgraded")
