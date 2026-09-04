"""Add immutable outcomes for executed signed replacement locks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_signed_physical_model_lock_replacement_outcomes"
down_revision = "0024_signed_physical_model_lock_replacement_admissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "physical_model_lock_replacement_outcomes",
        sa.Column("id", sa.String(36), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "admission_record_id",
            sa.String(36),
            sa.ForeignKey("physical_model_lock_replacement_admissions.id"),
            nullable=False,
        ),
        sa.Column("replacement_lock_admission_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column(
            "amendment_outcome_id",
            sa.String(36),
            sa.ForeignKey("physical_model_lock_amendment_outcomes.id"),
            nullable=False,
        ),
        sa.Column(
            "superseded_lock_id",
            sa.String(36),
            sa.ForeignKey("physical_model_locks.id"),
            nullable=False,
        ),
        sa.Column(
            "replacement_lock_id",
            sa.String(36),
            sa.ForeignKey("physical_model_locks.id"),
            nullable=False,
        ),
        sa.Column("replacement_lock_content_hash", sa.String(64), nullable=False),
        sa.Column("replacement_lock_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physical_model_lock_created", sa.Boolean(), nullable=False),
        sa.Column("downstream_authority_granted", sa.Boolean(), nullable=False),
        sa.Column("execution_receipt_json", sa.Text(), nullable=False),
        sa.Column("execution_receipt_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "admission_record_id", name="uq_pm_lock_replacement_outcome_admission_record"
        ),
        sa.UniqueConstraint(
            "replacement_lock_admission_id",
            name="uq_pm_lock_replacement_outcome_admission_id",
        ),
        sa.UniqueConstraint(
            "amendment_outcome_id", name="uq_pm_lock_replacement_outcome_amendment"
        ),
        sa.UniqueConstraint("superseded_lock_id", name="uq_pm_lock_replacement_outcome_superseded"),
        sa.UniqueConstraint("replacement_lock_id", name="uq_pm_lock_replacement_outcome_lock"),
        sa.UniqueConstraint(
            "replacement_lock_content_hash", name="uq_pm_lock_replacement_outcome_content"
        ),
        sa.UniqueConstraint(
            "replacement_lock_envelope_sha256", name="uq_pm_lock_replacement_outcome_envelope"
        ),
        sa.UniqueConstraint(
            "execution_receipt_sha256", name="uq_pm_lock_replacement_outcome_receipt"
        ),
        sa.CheckConstraint(
            "physical_model_lock_created = true",
            name="ck_pm_lock_replacement_outcome_created",
        ),
        sa.CheckConstraint(
            "downstream_authority_granted = false",
            name="ck_pm_lock_replacement_outcome_no_authority",
        ),
    )
    for name, columns in (
        ("ix_pm_lock_replacement_outcomes_admission_record", ["admission_record_id"]),
        ("ix_pm_lock_replacement_outcomes_admission_id", ["replacement_lock_admission_id"]),
        ("ix_pm_lock_replacement_outcomes_project", ["project_id"]),
        ("ix_pm_lock_replacement_outcomes_estimate", ["estimate_id"]),
        ("ix_pm_lock_replacement_outcomes_amendment", ["amendment_outcome_id"]),
        ("ix_pm_lock_replacement_outcomes_superseded", ["superseded_lock_id"]),
        ("ix_pm_lock_replacement_outcomes_lock", ["replacement_lock_id"]),
        ("ix_pm_lock_replacement_outcomes_actor", ["created_by_user_id"]),
        ("ix_pm_lock_replacement_outcomes_receipt", ["execution_receipt_sha256"]),
    ):
        op.create_index(name, "physical_model_lock_replacement_outcomes", columns)


def downgrade() -> None:
    raise RuntimeError("Signed replacement-lock execution outcomes cannot be downgraded")
