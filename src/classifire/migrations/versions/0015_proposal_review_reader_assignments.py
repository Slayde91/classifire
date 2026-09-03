"""Add scoped human reader assignments for proposal-review packages."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_proposal_review_reader_assignments"
down_revision = "0014_proposal_review_package_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "proposal_review_reader_assignments",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("scope_kind", sa.String(20), nullable=False),
        sa.Column("project_id", sa.String(36)),
        sa.Column("proposal_review_package_id", sa.String(36)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("granted_by_user_id", sa.String(36), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_by_user_id", sa.String(36)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revocation_reason_code", sa.String(100)),
        sa.CheckConstraint(
            "(scope_kind = 'project' AND project_id IS NOT NULL AND proposal_review_"
            "package_id IS NULL) OR (scope_kind = 'package' AND project_id IS NULL "
            "AND proposal_review_package_id IS NOT NULL)",
            name="ck_proposal_review_reader_assignment_scope",
        ),
        sa.CheckConstraint(
            "(active = true AND revoked_by_user_id IS NULL AND revoked_at IS NULL "
            "AND revocation_reason_code IS NULL) OR (active = false AND revoked_by_user_id "
            "IS NOT NULL AND revoked_at IS NOT NULL AND revocation_reason_code IS NOT NULL)",
            name="ck_proposal_review_reader_assignment_lifecycle",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(
            ["proposal_review_package_id"],
            ["proposal_review_packages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["granted_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by_user_id"], ["users.id"]),
        sa.UniqueConstraint(
            "user_id",
            "scope_kind",
            "project_id",
            name="uq_proposal_review_reader_assignment_project",
        ),
        sa.UniqueConstraint(
            "user_id",
            "scope_kind",
            "proposal_review_package_id",
            name="uq_proposal_review_reader_assignment_package",
        ),
    )
    op.create_index(
        "ix_proposal_review_reader_assignment_active_user",
        "proposal_review_reader_assignments",
        ["active", "user_id"],
    )


def downgrade() -> None:
    raise RuntimeError("Proposal-review reader assignments cannot be downgraded")
