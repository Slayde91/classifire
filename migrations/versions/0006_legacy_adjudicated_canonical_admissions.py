"""Historical marker for the superseded adjudicated-admission revision."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_adjudicated_canonical_admissions"
down_revision = "0005_agent_service_principals"
branch_labels = ("legacy_adjudicated_lineage",)
depends_on = None


def upgrade() -> None:
    """Register the marker after making its long revision ID PostgreSQL-safe."""

    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )


def downgrade() -> None:
    """Retain the wider revision column while Alembic records this long ID."""
