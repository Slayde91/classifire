"""Durable human-reviewed Draft client requests; no canonical authority."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_draft_client_requests"
down_revision = "0035_draft_package_imports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "draft_client_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("command", sa.String(30), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("identity_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result_json", sa.Text()),
        sa.CheckConstraint("command IN ('create', 'edit', 'package')", name="ck_client_command"),
        sa.CheckConstraint(
            "status IN ('pending', 'confirmed', 'rejected')", name="ck_client_status"
        ),
        sa.CheckConstraint("length(payload_json) <= 1048576", name="ck_client_payload_size"),
    )
    op.create_index(
        "ix_draft_client_requests_owner_user_id", "draft_client_requests", ["owner_user_id"]
    )


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT 1 FROM draft_client_requests LIMIT 1")).first():
        raise RuntimeError("Retained client review history prevents downgrade")
    op.drop_table("draft_client_requests")
