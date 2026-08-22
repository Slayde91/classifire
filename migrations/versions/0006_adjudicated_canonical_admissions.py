from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_adjudicated_canonical_admissions"
down_revision = "0005_agent_service_principals"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    tables = _table_names()
    if "physical_model_admissions" not in tables:
        op.create_table(
            "physical_model_admissions",
            *_record_columns(),
            sa.Column("admission_id", sa.String(100), nullable=False),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("purpose", sa.String(80), nullable=False),
            sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
            sa.Column("normalised_submission_payload_sha256", sa.String(64), nullable=False),
            sa.Column("protected_state_fingerprint", sa.String(64), nullable=False),
            sa.Column("protected_state_fingerprint_version", sa.String(100), nullable=False),
            sa.Column("source_run_id", sa.String(160), nullable=False),
            sa.Column("adjudicated_run_id", sa.String(160), nullable=False),
            sa.Column("artifact_manifest_sha256", sa.String(64), nullable=False),
            sa.Column("implementation_manifest_sha256", sa.String(64), nullable=False),
            sa.Column("admission_envelope_json", sa.Text(), nullable=False),
            sa.Column("admission_envelope_sha256", sa.String(64), nullable=False),
            sa.Column("preflight_receipt_json", sa.Text(), nullable=False),
            sa.Column("normalised_submission_payload_json", sa.Text(), nullable=False),
            sa.Column("issuer_id", sa.String(200), nullable=False),
            sa.Column("signing_key_id", sa.String(200), nullable=False),
            sa.Column("signature_algorithm", sa.String(80), nullable=False),
            sa.Column("signature", sa.Text(), nullable=False),
            sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("state", sa.String(20), nullable=False, server_default="issued"),
            sa.Column("claim_idempotency_key_hash", sa.String(64), nullable=True),
            sa.Column(
                "claimed_by_agent_principal_id",
                sa.String(36),
                sa.ForeignKey("agent_service_principals.id"),
                nullable=True,
            ),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("resolution_code", sa.String(100), nullable=True),
            sa.Column("resolution_receipt_sha256", sa.String(64), nullable=True),
            sa.CheckConstraint(
                "purpose = 'initial_adjudicated_canonicalisation'",
                name="ck_physical_model_admission_purpose",
            ),
            sa.CheckConstraint(
                "state IN "
                "('issued', 'claimed', 'consumed', 'rejected', 'revoked', 'expired', 'stale')",
                name="ck_physical_model_admission_state",
            ),
            sa.UniqueConstraint("admission_id", name="uq_physical_model_admission_admission_id"),
            sa.UniqueConstraint(
                "admission_envelope_sha256", name="uq_physical_model_admission_envelope_sha256"
            ),
        )
        op.create_index(
            "ix_physical_model_admissions_admission_id",
            "physical_model_admissions",
            ["admission_id"],
        )
        op.create_index(
            "ix_physical_model_admissions_project_id",
            "physical_model_admissions",
            ["project_id"],
        )
        op.create_index(
            "ix_physical_model_admissions_estimate_id",
            "physical_model_admissions",
            ["estimate_id"],
        )
        op.create_index(
            "ix_physical_model_admissions_state", "physical_model_admissions", ["state"]
        )
        op.create_index(
            "ix_physical_model_admissions_admission_envelope_sha256",
            "physical_model_admissions",
            ["admission_envelope_sha256"],
        )
        op.create_index(
            "ix_physical_model_admissions_claimed_by_agent_principal_id",
            "physical_model_admissions",
            ["claimed_by_agent_principal_id"],
        )
        op.create_index(
            "ix_physical_model_admission_estimate_state",
            "physical_model_admissions",
            ["estimate_id", "state"],
        )

    if "physical_model_initial_submissions" not in tables:
        op.create_table(
            "physical_model_initial_submissions",
            *_record_columns(),
            sa.Column(
                "admission_record_id",
                sa.String(36),
                sa.ForeignKey("physical_model_admissions.id"),
                nullable=False,
            ),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
            sa.Column("preflight_receipt_sha256", sa.String(64), nullable=False),
            sa.Column("normalised_submission_payload_sha256", sa.String(64), nullable=False),
            sa.Column("protected_state_fingerprint_before", sa.String(64), nullable=False),
            sa.Column("protected_state_fingerprint_after", sa.String(64), nullable=False),
            sa.Column("protected_state_fingerprint_version", sa.String(100), nullable=False),
            sa.Column("opening_count", sa.Integer(), nullable=False),
            sa.Column("service_count", sa.Integer(), nullable=False),
            sa.Column("service_opening_link_count", sa.Integer(), nullable=False),
            sa.Column("submission_receipt_sha256", sa.String(64), nullable=False),
            sa.Column("submission_receipt_json", sa.Text(), nullable=False),
            sa.Column("committed_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "admission_record_id", name="uq_physical_model_initial_submission_admission"
            ),
            sa.UniqueConstraint(
                "estimate_id", name="uq_physical_model_initial_submission_estimate"
            ),
            sa.UniqueConstraint(
                "submission_receipt_sha256",
                name="uq_physical_model_initial_submission_receipt_sha256",
            ),
        )
        op.create_index(
            "ix_physical_model_initial_submissions_project_id",
            "physical_model_initial_submissions",
            ["project_id"],
        )
        op.create_index(
            "ix_physical_model_initial_submissions_estimate_id",
            "physical_model_initial_submissions",
            ["estimate_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _table_names()
    for table in ("physical_model_initial_submissions", "physical_model_admissions"):
        if table in tables:
            count = int(bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one())
            if count:
                raise RuntimeError(
                    f"Refusing to downgrade non-empty immutable controlled-write journal: {table}"
                )
    if "physical_model_initial_submissions" in tables:
        op.drop_table("physical_model_initial_submissions")
    if "physical_model_admissions" in tables:
        op.drop_table("physical_model_admissions")
