"""Add the durable, claim-safe technical intake batch ledger."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_technical_intake_batches"
down_revision = "0012_technical_source_registration"
branch_labels = None
depends_on = None


def _canonical_uuid4_check(column: str) -> str:
    without_hyphens = f"replace({column}, '-', '')"
    unsupported = without_hyphens
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return (
        f"length({column}) = 36 "
        f"AND substr({column}, 9, 1) = '-' "
        f"AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' "
        f"AND substr({column}, 24, 1) = '-' "
        f"AND substr({column}, 15, 1) = '4' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b') "
        f"AND {column} = lower({column}) "
        f"AND length({without_hyphens}) = 32 "
        f"AND length({unsupported}) = 0"
    )


def _canonical_sha256_check(column: str) -> str:
    unsupported = column
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return (
        f"length({column}) = 64 "
        f"AND {column} = lower({column}) "
        f"AND length({unsupported}) = 0"
    )


def _technical_intake_filename_check(column: str) -> str:
    safe_characters = " AND ".join(
        f"replace({column}, '{character}', '') = {column}"
        for character in '<>:"/\\|?*'
    )
    return (
        f"length({column}) BETWEEN 1 AND 500 "
        f"AND {column} = trim({column}) "
        f"AND {safe_characters} "
        f"AND (lower({column}) LIKE '_%.pdf' "
        f"OR lower({column}) LIKE '_%.docx' "
        f"OR lower({column}) LIKE '_%.xlsx' "
        f"OR lower({column}) LIKE '_%.xlsb')"
    )


def upgrade() -> None:
    op.create_table(
        "technical_intake_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("batch_schema", sa.String(100), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("expected_item_count", sa.Integer(), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_batch_id",
        ),
        sa.CheckConstraint(
            "batch_schema = 'technical-intake-batch-v1'",
            name="ck_technical_intake_batch_schema",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'open', 'in_progress', 'completed', "
            "'completed_with_rejections', 'needs_attention'"
            ")",
            name="ck_technical_intake_batch_status",
        ),
        sa.CheckConstraint(
            "expected_item_count BETWEEN 1 AND 20",
            name="ck_technical_intake_batch_item_count",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("client_request_id"),
            name="ck_technical_intake_batch_client_request_id",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("manifest_sha256"),
            name="ck_technical_intake_batch_manifest_sha256",
        ),
        sa.CheckConstraint(
            "(status IN ('completed', 'completed_with_rejections') "
            "AND completed_at IS NOT NULL) OR "
            "(status NOT IN ('completed', 'completed_with_rejections') "
            "AND completed_at IS NULL)",
            name="ck_technical_intake_batch_completion",
        ),
        sa.UniqueConstraint(
            "created_by_id",
            "client_request_id",
            name="uq_technical_intake_batch_creator_request",
        ),
    )
    op.create_index(
        "ix_technical_intake_batches_status",
        "technical_intake_batches",
        ["status"],
    )
    op.create_index(
        "ix_technical_intake_batches_creator_status_created",
        "technical_intake_batches",
        ["created_by_id", "status", "created_at"],
    )

    op.create_table(
        "technical_intake_batch_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("technical_intake_batches.id"),
            nullable=False,
        ),
        sa.Column("client_item_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("declared_size_bytes", sa.Integer(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("declared_document_id", sa.String(200), nullable=False),
        sa.Column("registration_schema", sa.String(100), nullable=False),
        sa.Column("registration_snapshot", sa.JSON(), nullable=False),
        sa.Column("registration_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt_token", sa.String(36), nullable=True),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column(
            "technical_document_id",
            sa.String(36),
            sa.ForeignKey("technical_documents.id"),
            nullable=True,
        ),
        sa.Column("retained_file_sha256", sa.String(64), nullable=True),
        sa.Column("outcome_code", sa.String(100), nullable=True),
        sa.Column("outcome_retryable", sa.Boolean(), nullable=True),
        sa.Column("last_outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipt_schema", sa.String(100), nullable=True),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("receipt_sha256", sa.String(64), nullable=True),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_batch_item_id",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'pending', 'processing', 'accepted', 'rejected', 'needs_attention'"
            ")",
            name="ck_technical_intake_batch_item_status",
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 20",
            name="ck_technical_intake_batch_item_ordinal",
        ),
        sa.CheckConstraint(
            "declared_size_bytes > 0",
            name="ck_technical_intake_batch_item_size",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_intake_batch_item_attempt_count",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("client_item_id"),
            name="ck_technical_intake_batch_item_client_id",
        ),
        sa.CheckConstraint(
            _technical_intake_filename_check("original_filename"),
            name="ck_technical_intake_batch_item_filename",
        ),
        sa.CheckConstraint(
            "length(trim(declared_document_id)) BETWEEN 1 AND 200",
            name="ck_technical_intake_batch_item_document_id",
        ),
        sa.CheckConstraint(
            "registration_schema = 'technical-source-registration-v1'",
            name="ck_technical_intake_batch_item_registration_schema",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("registration_sha256"),
            name="ck_technical_intake_batch_item_registration_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("expected_sha256"),
            name="ck_technical_intake_batch_item_expected_sha256",
        ),
        sa.CheckConstraint(
            "retained_file_sha256 IS NULL OR ("
            + _canonical_sha256_check("retained_file_sha256")
            + ")",
            name="ck_technical_intake_batch_item_file_sha256",
        ),
        sa.CheckConstraint(
            "receipt_sha256 IS NULL OR ("
            + _canonical_sha256_check("receipt_sha256")
            + ")",
            name="ck_technical_intake_batch_item_receipt_sha256",
        ),
        sa.CheckConstraint(
            "attempt_token IS NULL OR ("
            + _canonical_uuid4_check("attempt_token")
            + ")",
            name="ck_technical_intake_batch_item_attempt_token",
        ),
        sa.CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_intake_batch_item_claim",
        ),
        sa.CheckConstraint(
            "(status = 'pending' "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND receipt_schema IS NULL "
            "AND receipt_json IS NULL "
            "AND receipt_sha256 IS NULL) OR "
            "(status = 'processing' AND (("
            "outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND receipt_schema IS NULL "
            "AND receipt_json IS NULL "
            "AND receipt_sha256 IS NULL) OR ("
            "outcome_code IS NOT NULL "
            "AND outcome_retryable IS NOT NULL "
            "AND outcome_retryable = true "
            "AND last_outcome_at IS NOT NULL "
            "AND receipt_schema IS NOT NULL "
            "AND receipt_schema = 'technical-intake-item-receipt-v1' "
            "AND receipt_json IS NOT NULL "
            "AND receipt_sha256 IS NOT NULL))) OR "
            "(status IN ('accepted', 'rejected', 'needs_attention') "
            "AND attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_retryable IS NOT NULL "
            "AND last_outcome_at IS NOT NULL "
            "AND receipt_schema IS NOT NULL "
            "AND receipt_schema = 'technical-intake-item-receipt-v1' "
            "AND receipt_json IS NOT NULL "
            "AND receipt_sha256 IS NOT NULL)",
            name="ck_technical_intake_batch_item_outcome",
        ),
        sa.CheckConstraint(
            "(status = 'accepted' "
            "AND technical_document_id IS NOT NULL "
            "AND retained_file_sha256 IS NOT NULL "
            "AND retained_file_sha256 = expected_sha256 "
            "AND outcome_retryable = false) OR "
            "(status = 'needs_attention' "
            "AND outcome_code IN ("
            "'MALWARE_DETECTED', 'STORED_FILE_CONTENT_COLLISION', "
            "'STORED_FILE_CONTEXT_CONFLICT', "
            "'UPLOAD_CONTENT_SIGNATURE_INVALID', 'UPLOAD_STAGED_BYTES_CHANGED'"
            ") "
            "AND technical_document_id IS NOT NULL "
            "AND retained_file_sha256 IS NOT NULL "
            "AND retained_file_sha256 = expected_sha256 "
            "AND outcome_retryable = false) OR "
            "(status <> 'accepted' "
            "AND technical_document_id IS NULL "
            "AND retained_file_sha256 IS NULL)",
            name="ck_technical_intake_batch_item_acceptance",
        ),
        sa.CheckConstraint(
            "(status <> 'accepted' OR ("
            "outcome_code = 'ACCEPTED' "
            "AND outcome_retryable = false)) "
            "AND (status <> 'rejected' OR outcome_code <> 'ACCEPTED') "
            "AND (status <> 'needs_attention' OR outcome_retryable = false)",
            name="ck_technical_intake_batch_item_terminal_semantics",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "client_item_id",
            name="uq_technical_intake_batch_item_client_id",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "ordinal",
            name="uq_technical_intake_batch_item_ordinal",
        ),
        sa.UniqueConstraint(
            "batch_id",
            "declared_document_id",
            name="uq_technical_intake_batch_item_document_id",
        ),
        sa.UniqueConstraint(
            "technical_document_id",
            name="uq_technical_intake_batch_item_technical_document",
        ),
        sa.UniqueConstraint(
            "attempt_token",
            name="uq_technical_intake_batch_item_attempt_token",
        ),
    )
    op.create_index(
        "ix_technical_intake_batch_items_batch_status_ordinal",
        "technical_intake_batch_items",
        ["batch_id", "status", "ordinal"],
    )
    op.create_index(
        "ix_technical_intake_batch_items_status",
        "technical_intake_batch_items",
        ["status"],
    )


def downgrade() -> None:
    raise RuntimeError("Technical intake batch ledger cannot be downgraded")
