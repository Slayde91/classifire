"""Add immutable journal records for signed lock-amendment admissions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_signed_physical_model_lock_amendment_admissions"
down_revision = "0021_proposal_review_annotations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "physical_model_lock_amendment_admissions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amendment_admission_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column(
            "target_lock_id",
            sa.String(36),
            sa.ForeignKey("physical_model_locks.id"),
            nullable=False,
        ),
        sa.Column("target_lock_content_hash", sa.String(64), nullable=False),
        sa.Column("target_lock_signature_sha256", sa.String(64), nullable=False),
        sa.Column("current_physical_model_content_hash", sa.String(64), nullable=False),
        sa.Column("amendment_submission_payload_sha256", sa.String(64), nullable=False),
        sa.Column("amendment_submission_payload_json", sa.Text(), nullable=False),
        sa.Column("visual_validation_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("amendment_reason", sa.Text(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("amendment_envelope_json", sa.Text(), nullable=False),
        sa.Column("amendment_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("issuer_id", sa.String(200), nullable=False),
        sa.Column("signing_key_id", sa.String(200), nullable=False),
        sa.Column("signature_algorithm", sa.String(80), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preflight_receipt_json", sa.Text(), nullable=False),
        sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "length(trim(amendment_reason)) > 0",
            name="ck_physical_model_lock_amendment_admission_reason",
        ),
        sa.UniqueConstraint(
            "amendment_admission_id",
            name="uq_physical_model_lock_amendment_admission_id",
        ),
        sa.UniqueConstraint(
            "amendment_envelope_sha256",
            name="uq_physical_model_lock_amendment_admission_envelope_sha256",
        ),
        sa.UniqueConstraint(
            "preflight_receipt_sha256",
            name="uq_physical_model_lock_amendment_admission_preflight_sha256",
        ),
    )
    for name, columns in (
        (
            "ix_physical_model_lock_amendment_admissions_amendment_admission_id",
            ["amendment_admission_id"],
        ),
        ("ix_physical_model_lock_amendment_admissions_project_id", ["project_id"]),
        ("ix_physical_model_lock_amendment_admissions_estimate_id", ["estimate_id"]),
        ("ix_physical_model_lock_amendment_admissions_target_lock_id", ["target_lock_id"]),
        (
            "ix_physical_model_lock_amendment_admission_estimate_created",
            ["estimate_id", "created_at"],
        ),
    ):
        op.create_index(name, "physical_model_lock_amendment_admissions", columns)


def downgrade() -> None:
    raise RuntimeError("Signed lock-amendment admission records cannot be downgraded")
