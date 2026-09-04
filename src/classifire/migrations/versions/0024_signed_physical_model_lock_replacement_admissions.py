"""Add immutable admissions for signed replacement Physical Model Locks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0024_signed_physical_model_lock_replacement_admissions"
down_revision = "0023_signed_physical_model_lock_amendment_outcomes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "physical_model_lock_replacement_admissions",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("replacement_lock_admission_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column(
            "amendment_outcome_id",
            sa.String(36),
            sa.ForeignKey("physical_model_lock_amendment_outcomes.id"),
            nullable=False,
        ),
        sa.Column("amendment_admission_id", sa.String(36), nullable=False),
        sa.Column("amendment_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("amendment_execution_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("visual_validation_receipt_sha256", sa.String(64), nullable=False),
        sa.Column(
            "superseded_lock_id",
            sa.String(36),
            sa.ForeignKey("physical_model_locks.id"),
            nullable=False,
        ),
        sa.Column("superseded_lock_content_hash", sa.String(64), nullable=False),
        sa.Column("replacement_lock_content_hash", sa.String(64), nullable=False),
        sa.Column("replacement_lock_reason", sa.Text(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("replacement_lock_envelope_json", sa.Text(), nullable=False),
        sa.Column("replacement_lock_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("issuer_id", sa.String(200), nullable=False),
        sa.Column("signing_key_id", sa.String(200), nullable=False),
        sa.Column("signature_algorithm", sa.String(80), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preflight_receipt_json", sa.Text(), nullable=False),
        sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "length(trim(replacement_lock_reason)) > 0",
            name="ck_pm_lock_replacement_admission_reason",
        ),
        sa.UniqueConstraint(
            "replacement_lock_admission_id",
            name="uq_pm_lock_replacement_admission_id",
        ),
        sa.UniqueConstraint(
            "replacement_lock_envelope_sha256",
            name="uq_pm_lock_replacement_admission_envelope",
        ),
        sa.UniqueConstraint(
            "preflight_receipt_sha256",
            name="uq_pm_lock_replacement_admission_preflight",
        ),
    )
    for name, columns in (
        ("ix_pm_lock_replacement_admissions_id", ["replacement_lock_admission_id"]),
        ("ix_pm_lock_replacement_admissions_project", ["project_id"]),
        ("ix_pm_lock_replacement_admissions_estimate", ["estimate_id"]),
        ("ix_pm_lock_replacement_admissions_outcome", ["amendment_outcome_id"]),
        ("ix_pm_lock_replacement_admissions_superseded_lock", ["superseded_lock_id"]),
        (
            "ix_physical_model_lock_replacement_admission_estimate_created",
            ["estimate_id", "created_at"],
        ),
    ):
        op.create_index(name, "physical_model_lock_replacement_admissions", columns)


def downgrade() -> None:
    raise RuntimeError("Signed replacement-lock admission records cannot be downgraded")
