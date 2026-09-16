"""Retain Draft work assertions separately from inspection and release."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0050_draft_work_records"
down_revision = "0049_draft_proposal_decisions"
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
        "draft_work_records",
        *_record_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("latest_revision", sa.Integer(), nullable=False),
        sa.CheckConstraint("latest_revision >= 1", name="ck_work_record_revision"),
    )
    op.create_index(
        "ix_draft_work_records_draft_scope_id", "draft_work_records", ["draft_scope_id"]
    )
    op.create_table(
        "draft_work_record_revisions",
        *_record_columns(),
        sa.Column(
            "work_record_id", sa.String(36), sa.ForeignKey("draft_work_records.id"), nullable=False
        ),
        sa.Column(
            "scope_revision_id",
            sa.String(36),
            sa.ForeignKey("draft_scope_revisions.id"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("parent_hash", sa.String(64)),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("work_record_id", "revision", name="uq_work_record_revision"),
        sa.CheckConstraint("revision >= 1", name="ck_work_record_positive_revision"),
        sa.CheckConstraint("length(envelope_json) <= 262144", name="ck_work_record_size"),
    )
    op.create_index(
        "ix_draft_work_record_revisions_work_record_id",
        "draft_work_record_revisions",
        ["work_record_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Retained Draft work records cannot be downgraded")
