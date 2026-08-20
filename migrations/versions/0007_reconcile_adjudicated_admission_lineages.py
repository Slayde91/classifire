"""Merge the empty legacy adjudication journal into the reviewed clean lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_reconcile_adjudicated_admission_lineages"
down_revision = (
    "0006_physical_submission_receipts",
    "0006_adjudicated_canonical_admissions",
)
branch_labels = None
depends_on = None

_LEGACY_TABLES = (
    "physical_model_initial_submissions",
    "physical_model_admissions",
    "physical_model_submission_receipts",
)
_EMPTY_JOURNAL_COUNT_QUERIES = {
    "physical_model_initial_submissions": sa.text(
        "SELECT COUNT(*) FROM physical_model_initial_submissions"
    ),
    "physical_model_admissions": sa.text("SELECT COUNT(*) FROM physical_model_admissions"),
    "physical_model_submission_receipts": sa.text(
        "SELECT COUNT(*) FROM physical_model_submission_receipts"
    ),
}


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _is_legacy_admission_table(tables: set[str]) -> bool:
    if "physical_model_initial_submissions" in tables:
        return True
    if "physical_model_admissions" not in tables:
        return False
    return bool(
        {
            "artifact_manifest_sha256",
            "implementation_manifest_sha256",
            "preflight_receipt_json",
            "signature",
            "claim_idempotency_key_hash",
        }
        & _column_names("physical_model_admissions")
    )


def _require_empty(table: str) -> None:
    count = int(op.get_bind().execute(_EMPTY_JOURNAL_COUNT_QUERIES[table]).scalar_one())
    if count:
        raise RuntimeError(
            "Refusing legacy adjudication-lineage reconciliation with retained "
            f"journal records in {table}"
        )


def _create_clean_admissions() -> None:
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
    for name, columns in (
        ("ix_physical_model_admissions_admission_id", ["admission_id"]),
        ("ix_physical_model_admissions_project_id", ["project_id"]),
        ("ix_physical_model_admissions_estimate_id", ["estimate_id"]),
        ("ix_physical_model_admissions_state", ["state"]),
        ("ix_physical_model_admission_estimate_state", ["estimate_id", "state"]),
    ):
        op.create_index(name, "physical_model_admissions", columns)


def _create_clean_receipts() -> None:
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
    for name, columns in (
        ("ix_physical_model_submission_receipts_admission_record_id", ["admission_record_id"]),
        ("ix_physical_model_submission_receipts_admission_id", ["admission_id"]),
        ("ix_physical_model_submission_receipts_project_id", ["project_id"]),
        ("ix_physical_model_submission_receipts_estimate_id", ["estimate_id"]),
        ("ix_physical_model_submission_receipts_receipt_sha256", ["receipt_sha256"]),
    ):
        op.create_index(name, "physical_model_submission_receipts", columns)


def upgrade() -> None:
    tables = _table_names()
    if not _is_legacy_admission_table(tables):
        return
    for table in _LEGACY_TABLES:
        if table in tables:
            _require_empty(table)
    if "physical_model_submission_receipts" in tables:
        op.drop_table("physical_model_submission_receipts")
    if "physical_model_initial_submissions" in tables:
        op.drop_table("physical_model_initial_submissions")
    op.drop_table("physical_model_admissions")
    _create_clean_admissions()
    _create_clean_receipts()


def downgrade() -> None:
    raise RuntimeError("Legacy adjudication-lineage reconciliation cannot be downgraded")
