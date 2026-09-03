"""Retain immutable proposal-only human review annotations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_proposal_review_annotations"
down_revision = "0020_proposal_review_family_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_review_annotations",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("annotation_id", sa.String(128), nullable=False),
        sa.Column("proposal_review_package_id", sa.String(36), nullable=False),
        sa.Column("proposal_review_package_redaction_id", sa.String(36)),
        sa.Column("package_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("reviewer_summary_sha256", sa.String(64), nullable=False),
        sa.Column("annotation_sha256", sa.String(64), nullable=False),
        sa.Column("scope_id", sa.String(36)),
        sa.Column("finding_state", sa.String(40), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=False),
        sa.Column("proposal_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reviewed_by_user_id", sa.String(36), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "finding_state IN ('confirmed', 'inferred', 'provisional', 'contradictory', "
            "'unknown', 'human_verification_required')",
            name="ck_proposal_review_annotation_finding_state",
        ),
        sa.CheckConstraint(
            "length(trim(reason_code)) > 0",
            name="ck_proposal_review_annotation_reason_code",
        ),
        sa.CheckConstraint(
            "proposal_only = true",
            name="ck_proposal_review_annotation_proposal_only",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_review_package_id"],
            ["proposal_review_packages.id"],
            name="fk_proposal_review_annotation_package",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposal_review_package_redaction_id"],
            ["proposal_review_package_redactions.id"],
            name="fk_proposal_review_annotation_redaction",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["reviewed_by_user_id"], ["users.id"]),
        sa.UniqueConstraint("annotation_id", name="uq_proposal_review_annotation_id"),
    )
    op.create_index(
        "ix_proposal_review_annotation_package_recorded",
        "proposal_review_annotations",
        ["proposal_review_package_id", "recorded_at"],
    )
    op.create_index(
        "ix_proposal_review_annotation_reviewer",
        "proposal_review_annotations",
        ["reviewed_by_user_id", "recorded_at"],
    )


def downgrade() -> None:
    raise RuntimeError("Proposal-review annotations cannot be downgraded")