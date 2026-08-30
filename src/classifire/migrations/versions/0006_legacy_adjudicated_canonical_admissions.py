"""Historical marker for the superseded adjudicated-admission revision."""

from __future__ import annotations

revision = "0006_adjudicated_canonical_admissions"
down_revision = "0005_agent_service_principals"
branch_labels = ("legacy_adjudicated_lineage",)
depends_on = None


def upgrade() -> None:
    """Register the historical marker without recreating superseded schema."""


def downgrade() -> None:
    """The marker has no schema effect."""
