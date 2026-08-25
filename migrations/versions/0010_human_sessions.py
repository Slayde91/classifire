"""Add opaque human sessions and per-user authentication generations."""

from __future__ import annotations

import secrets

import sqlalchemy as sa
from alembic import op

revision = "0010_human_sessions"
down_revision = "0009_visual_validation_receipts"
branch_labels = None
depends_on = None


def _distinct_auth_generation(existing: set[str]) -> str:
    while True:
        generation = secrets.token_hex(32)
        if generation not in existing:
            existing.add(generation)
            return generation


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("auth_generation", sa.String(64), nullable=True))

    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String(36)),
        sa.column("auth_generation", sa.String(64)),
    )
    generations: set[str] = set()
    user_ids = bind.execute(sa.select(users.c.id).order_by(users.c.id)).scalars().all()
    for user_id in user_ids:
        bind.execute(
            sa.update(users)
            .where(users.c.id == user_id)
            .values(auth_generation=_distinct_auth_generation(generations))
        )

    with op.batch_alter_table("users") as batch:
        batch.alter_column(
            "auth_generation",
            existing_type=sa.String(64),
            nullable=False,
        )

    op.create_table(
        "human_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("token_hint", sa.String(12), nullable=False),
        sa.Column("auth_generation", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_human_sessions_user_id", "human_sessions", ["user_id"])
    op.create_index(
        "ix_human_sessions_token_hash",
        "human_sessions",
        ["token_hash"],
        unique=True,
    )


def downgrade() -> None:
    raise RuntimeError("Human-session revocation state cannot be downgraded")
