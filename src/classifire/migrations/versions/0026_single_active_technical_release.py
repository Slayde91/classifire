"""Enforce one active technical library release."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0026_single_active_technical_release"
down_revision = "0025_signed_physical_model_lock_replacement_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_library_release_one_active_technical",
        "library_releases",
        ["library_type"],
        unique=True,
        sqlite_where=sa.text("status = 'active' AND library_type = 'technical'"),
        postgresql_where=sa.text("status = 'active' AND library_type = 'technical'"),
    )


def downgrade() -> None:
    raise RuntimeError(
        "Single-active technical-release enforcement cannot be downgraded"
    )
