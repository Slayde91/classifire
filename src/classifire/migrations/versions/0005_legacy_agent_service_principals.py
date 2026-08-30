"""Historical marker for the superseded agent-principal revision.

This revision is intentionally a no-op.  It lets Alembic recognise databases
that reached the former Phase 8 lineage, while fresh installations continue on
the reviewed clean-stack migrations.
"""

from __future__ import annotations

revision = "0005_agent_service_principals"
down_revision = "0004_agent_service_principals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Register the historical marker without recreating superseded schema."""


def downgrade() -> None:
    """The marker has no schema effect."""
