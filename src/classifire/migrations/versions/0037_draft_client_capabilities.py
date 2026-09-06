"""Extend retained client commands without rewriting earlier request history."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_draft_client_capabilities"
down_revision = "0036_draft_client_requests"
branch_labels = None
depends_on = None


def _constraint(commands: str) -> None:
    with op.batch_alter_table("draft_client_requests") as batch:
        batch.drop_constraint("ck_client_command", type_="check")
        batch.create_check_constraint("ck_client_command", f"command IN ({commands})")


def upgrade() -> None:
    _constraint("'create', 'edit', 'package', 'capability'")


def downgrade() -> None:
    if (
        op.get_bind()
        .execute(sa.text("SELECT 1 FROM draft_client_requests WHERE command='capability' LIMIT 1"))
        .first()
    ):
        raise RuntimeError("Retained capability requests prevent downgrade")
    _constraint("'create', 'edit', 'package'")
