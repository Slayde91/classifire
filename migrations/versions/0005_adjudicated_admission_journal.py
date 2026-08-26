from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_adjudicated_admission_journal"
down_revision = "0004_agent_service_principals"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.alter_column(
            "alembic_version",
            "version_num",
            existing_type=sa.String(32),
            type_=sa.String(64),
            existing_nullable=False,
        )
    if "physical_model_admissions" in _table_names():
        return
    op.create_table(
        "physical_model_admissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("admission_id", sa.String(100), nullable=False),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
        sa.Column("normalised_submission_payload_sha256", sa.String(64), nullable=False),
        sa.Column("normalised_submission_payload_json", sa.Text(), nullable=False),
        sa.Column("protected_state_fingerprint", sa.String(64), nullable=False),
        sa.Column("protected_state_fingerprint_version", sa.String(100), nullable=False),
        sa.Column("source_run_id", sa.String(160), nullable=False),
        sa.Column("adjudicated_run_id", sa.String(160), nullable=False),
        sa.Column("artifact_digests", sa.JSON(), nullable=False),
        sa.Column("policy_versions", sa.JSON(), nullable=False),
        sa.Column("admission_envelope_json", sa.Text(), nullable=False),
        sa.Column("admission_envelope_sha256", sa.String(64), nullable=False),
        sa.Column("issuer_id", sa.String(200), nullable=False),
        sa.Column("signing_key_id", sa.String(200), nullable=False),
        sa.Column("signature_algorithm", sa.String(80), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default=sa.text("'issued'")),
        sa.CheckConstraint(
            "purpose = 'initial_adjudicated_canonicalisation'",
            name="ck_physical_model_admission_purpose",
        ),
        sa.CheckConstraint(
            "state IN ('issued', 'claimed', 'consumed', 'rejected', 'revoked', 'expired')",
            name="ck_physical_model_admission_state",
        ),
        sa.UniqueConstraint("admission_id", name="uq_physical_model_admission_admission_id"),
        sa.UniqueConstraint(
            "admission_envelope_sha256", name="uq_physical_model_admission_envelope_sha256"
        ),
    )
    op.create_index(
        "ix_physical_model_admissions_admission_id", "physical_model_admissions", ["admission_id"]
    )
    op.create_index(
        "ix_physical_model_admissions_project_id", "physical_model_admissions", ["project_id"]
    )
    op.create_index(
        "ix_physical_model_admissions_estimate_id", "physical_model_admissions", ["estimate_id"]
    )
    op.create_index("ix_physical_model_admissions_state", "physical_model_admissions", ["state"])
    op.create_index(
        "ix_physical_model_admission_estimate_state",
        "physical_model_admissions",
        ["estimate_id", "state"],
    )


def downgrade() -> None:
    if "physical_model_admissions" in _table_names():
        count = (
            op.get_bind()
            .execute(sa.text("SELECT COUNT(*) FROM physical_model_admissions"))
            .scalar()
        )
        if count:
            raise RuntimeError("Refusing to downgrade retained physical-model admission records")
        op.drop_table("physical_model_admissions")
