"""Serialize governed release publication through a database-owned slot."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_release_publication_slot"
down_revision = "0009_visual_validation_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "library_releases",
        sa.Column("active_publication_slot", sa.String(50), nullable=True),
    )
    op.create_index(
        "uq_library_release_active_publication_slot",
        "library_releases",
        ["active_publication_slot"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError("Governed release publication serialization cannot be downgraded")
