from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_physical_submission_receipts"
down_revision = "0005_adjudicated_admission_journal"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if "physical_model_submission_receipts" in _table_names():
        return
    op.create_table(
        "physical_model_submission_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "admission_record_id",
            sa.String(36),
            sa.ForeignKey("physical_model_admissions.id"),
            nullable=False,
        ),
        sa.Column("admission_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("normalised_submission_payload_sha256", sa.String(64), nullable=False),
        sa.Column("protected_state_fingerprint_before", sa.String(64), nullable=False),
        sa.Column("opening_count", sa.Integer(), nullable=False),
        sa.Column("service_count", sa.Integer(), nullable=False),
        sa.Column("service_opening_link_count", sa.Integer(), nullable=False),
        sa.Column("canonical_write_performed", sa.Boolean(), nullable=False),
        sa.Column("physical_model_lock_created", sa.Boolean(), nullable=False),
        sa.Column("receipt_json", sa.Text(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.UniqueConstraint(
            "admission_record_id", name="uq_physical_submission_receipt_admission_record"
        ),
        sa.UniqueConstraint("admission_id", name="uq_physical_submission_receipt_admission_id"),
        sa.UniqueConstraint("receipt_sha256", name="uq_physical_submission_receipt_sha256"),
    )
    op.create_index(
        "ix_physical_model_submission_receipts_admission_record_id",
        "physical_model_submission_receipts",
        ["admission_record_id"],
    )
    op.create_index(
        "ix_physical_model_submission_receipts_admission_id",
        "physical_model_submission_receipts",
        ["admission_id"],
    )
    op.create_index(
        "ix_physical_model_submission_receipts_project_id",
        "physical_model_submission_receipts",
        ["project_id"],
    )
    op.create_index(
        "ix_physical_model_submission_receipts_estimate_id",
        "physical_model_submission_receipts",
        ["estimate_id"],
    )
    op.create_index(
        "ix_physical_model_submission_receipts_receipt_sha256",
        "physical_model_submission_receipts",
        ["receipt_sha256"],
    )


def downgrade() -> None:
    if "physical_model_submission_receipts" in _table_names():
        count = (
            op.get_bind()
            .execute(sa.text("SELECT COUNT(*) FROM physical_model_submission_receipts"))
            .scalar()
        )
        if count:
            raise RuntimeError("Refusing to downgrade retained physical-model submission receipts")
        op.drop_table("physical_model_submission_receipts")
