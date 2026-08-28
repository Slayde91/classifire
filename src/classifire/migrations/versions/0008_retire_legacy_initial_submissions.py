"""Retire a stray empty legacy initial-submission journal table."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_retire_legacy_initial_submissions"
down_revision = "0007_reconcile_adjudicated_admission_lineages"
branch_labels = None
depends_on = None

_LEGACY_TABLE = "physical_model_initial_submissions"


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if _LEGACY_TABLE not in tables:
        return
    count = int(
        op.get_bind()
        .execute(sa.text("SELECT COUNT(*) FROM physical_model_initial_submissions"))
        .scalar_one()
    )
    if count:
        raise RuntimeError(
            "Refusing to retire physical_model_initial_submissions with retained records"
        )
    op.drop_table(_LEGACY_TABLE)


def downgrade() -> None:
    raise RuntimeError("Legacy initial-submission table retirement cannot be downgraded")
