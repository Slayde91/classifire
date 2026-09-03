"""Add hash-bound Draft technical document supersession lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_technical_document_supersession_lineage"
down_revision = "0015_proposal_review_reader_assignments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("technical_documents") as batch_op:
        batch_op.add_column(sa.Column("source_lineage_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("source_lineage_sha256", sa.String(length=64), nullable=True))
        batch_op.create_check_constraint(
            "ck_technical_document_source_lineage",
            "(source_lineage_json IS NULL AND source_lineage_sha256 IS NULL) OR "
            "(supersedes_document_id IS NOT NULL AND source_lineage_json IS NOT NULL "
            "AND source_lineage_sha256 IS NOT NULL)",
        )


def downgrade() -> None:
    raise RuntimeError("Technical document source-lineage history cannot be downgraded")