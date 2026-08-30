"""Add immutable, hash-bound visual-validation receipt evidence."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009_visual_validation_receipts"
down_revision = "0008_retire_legacy_initial_submissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_validation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("source_run_id", sa.String(160), nullable=False),
        sa.Column("candidate_submission_payload_sha256", sa.String(64), nullable=False),
        sa.Column("controller_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_manifest_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_family_inventory_sha256", sa.String(64), nullable=False),
        sa.Column("evidence_family_review_sha256", sa.String(64), nullable=False),
        sa.Column("human_review_request_sha256", sa.String(64), nullable=False),
        sa.Column("human_review_response_sha256", sa.String(64), nullable=False),
        sa.Column("approval_reference", sa.String(200), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("unresolved_items", sa.JSON(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("implementation_revision", sa.String(40), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "status IN ('SEMANTICALLY_APPROVED', 'WITHHELD')",
            name="ck_visual_validation_receipt_status",
        ),
        sa.UniqueConstraint("receipt_id", name="uq_visual_validation_receipt_id"),
        sa.UniqueConstraint("receipt_sha256", name="uq_visual_validation_receipt_sha256"),
    )
    for name, columns in (
        ("ix_visual_validation_receipts_receipt_id", ["receipt_id"]),
        ("ix_visual_validation_receipts_project_id", ["project_id"]),
        ("ix_visual_validation_receipts_estimate_id", ["estimate_id"]),
        ("ix_visual_validation_receipts_status", ["status"]),
        ("ix_visual_validation_receipts_receipt_sha256", ["receipt_sha256"]),
        ("ix_visual_validation_receipt_estimate_status", ["estimate_id", "status"]),
    ):
        op.create_index(name, "visual_validation_receipts", columns)


def downgrade() -> None:
    raise RuntimeError("Visual-validation receipt evidence cannot be downgraded")
