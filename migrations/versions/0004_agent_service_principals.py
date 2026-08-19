from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_agent_service_principals"
down_revision = "0003_physical_model_foundation"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "agent_service_principals" in _table_names():
        return
    op.create_table(
        "agent_service_principals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_hint", sa.String(16), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("agent_id", name="uq_agent_service_principal_agent_id"),
        sa.UniqueConstraint("token_hash", name="uq_agent_service_principal_token_hash"),
    )
    op.create_index(
        "ix_agent_service_principals_agent_id", "agent_service_principals", ["agent_id"]
    )
    op.create_index(
        "ix_agent_service_principals_is_active", "agent_service_principals", ["is_active"]
    )


def downgrade() -> None:
    if "agent_service_principals" in _table_names():
        count = (
            op.get_bind().execute(sa.text("SELECT COUNT(*) FROM agent_service_principals")).scalar()
        )
        if count:
            raise RuntimeError("Refusing to downgrade retained agent service-principal records")
        op.drop_table("agent_service_principals")
