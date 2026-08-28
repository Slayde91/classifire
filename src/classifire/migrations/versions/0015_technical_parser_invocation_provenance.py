"""Bind technical extraction output to exact isolated-parser invocations."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_technical_parser_invocation_provenance"
down_revision = "0014_technical_extraction_foundation"
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
    return f"length({column}) = 64 AND {column} = lower({column}) AND length({unsupported}) = 0"


def _extend_extraction_runs() -> None:
    with op.batch_alter_table("technical_extraction_runs") as batch:
        batch.add_column(sa.Column("runtime_profile_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("runtime_attestation_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("layout_invocation_id", sa.String(36), nullable=True))
        batch.drop_constraint("ck_technical_extraction_run_schema", type_="check")
        batch.create_check_constraint(
            "ck_technical_extraction_run_schema",
            "run_schema IN ('technical-extraction-run-v1', 'technical-extraction-run-v2')",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_run_runtime_profile_sha256",
            "runtime_profile_sha256 IS NULL OR ("
            + _canonical_sha256_check("runtime_profile_sha256")
            + ")",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_run_runtime_attestation_sha256",
            "runtime_attestation_sha256 IS NULL OR ("
            + _canonical_sha256_check("runtime_attestation_sha256")
            + ")",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_run_layout_invocation_id",
            "layout_invocation_id IS NULL OR ("
            + _canonical_uuid4_check("layout_invocation_id")
            + ")",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_run_runtime_provenance",
            "(run_schema = 'technical-extraction-run-v1' "
            "AND runtime_profile_sha256 IS NULL "
            "AND runtime_attestation_sha256 IS NULL "
            "AND layout_invocation_id IS NULL) OR "
            "(run_schema = 'technical-extraction-run-v2' "
            "AND runtime_profile_sha256 IS NOT NULL "
            "AND ((page_count IS NULL AND layout_invocation_id IS NULL) OR "
            "(page_count IS NOT NULL "
            "AND runtime_attestation_sha256 IS NOT NULL "
            "AND layout_invocation_id IS NOT NULL)))",
        )
        batch.drop_constraint("uq_technical_extraction_run_identity", type_="unique")
        batch.create_unique_constraint(
            "uq_technical_extraction_run_runtime_binding",
            [
                "id",
                "runtime_profile_sha256",
                "worker_image_digest",
                "runtime_attestation_sha256",
            ],
        )

    op.create_index(
        "uq_technical_extraction_run_identity_v1",
        "technical_extraction_runs",
        [
            "technical_document_id",
            "source_stored_file_id",
            "source_sha256",
            "source_size_bytes",
            "extraction_policy_sha256",
            "ocr_low_confidence_threshold",
            "worker_image_digest",
        ],
        unique=True,
        sqlite_where=sa.text("run_schema = 'technical-extraction-run-v1'"),
        postgresql_where=sa.text("run_schema = 'technical-extraction-run-v1'"),
    )
    op.create_index(
        "uq_technical_extraction_run_identity_v2",
        "technical_extraction_runs",
        [
            "technical_document_id",
            "source_stored_file_id",
            "source_sha256",
            "source_size_bytes",
            "extraction_policy_sha256",
            "ocr_low_confidence_threshold",
            "worker_image_digest",
            "runtime_profile_sha256",
        ],
        unique=True,
        sqlite_where=sa.text("run_schema = 'technical-extraction-run-v2'"),
        postgresql_where=sa.text("run_schema = 'technical-extraction-run-v2'"),
    )


def _extend_extraction_pages() -> None:
    with op.batch_alter_table("technical_extraction_pages") as batch:
        batch.add_column(sa.Column("parser_invocation_id", sa.String(36), nullable=True))
        batch.drop_constraint("ck_technical_extraction_page_schema", type_="check")
        batch.create_check_constraint(
            "ck_technical_extraction_page_schema",
            "page_schema IN ('technical-extraction-page-v1', 'technical-extraction-page-v2')",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_page_parser_invocation_id",
            "parser_invocation_id IS NULL OR ("
            + _canonical_uuid4_check("parser_invocation_id")
            + ")",
        )
        batch.create_check_constraint(
            "ck_technical_extraction_page_parser_provenance",
            "(page_schema = 'technical-extraction-page-v1' "
            "AND parser_invocation_id IS NULL) OR "
            "(page_schema = 'technical-extraction-page-v2' "
            "AND ((status IN ('completed', 'needs_attention') "
            "AND parser_invocation_id IS NOT NULL) OR "
            "(status NOT IN ('completed', 'needs_attention') "
            "AND parser_invocation_id IS NULL)))",
        )
        batch.create_unique_constraint(
            "uq_technical_extraction_page_identity_binding",
            ["id", "run_id", "page_number"],
        )
        batch.create_unique_constraint(
            "uq_technical_extraction_page_parser_invocation",
            ["parser_invocation_id"],
        )


def _create_invocation_reservations() -> None:
    op.create_table(
        "technical_parser_invocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("invocation_schema", sa.String(100), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("run_attempt_token", sa.String(36), nullable=False),
        sa.Column("run_attempt_count", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_attempt_token", sa.String(36), nullable=True),
        sa.Column("page_attempt_count", sa.Integer(), nullable=True),
        sa.Column("attempt_token", sa.String(36), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("request_size_bytes", sa.Integer(), nullable=False),
        sa.Column("extraction_policy", sa.String(100), nullable=False),
        sa.Column("extraction_policy_sha256", sa.String(64), nullable=False),
        sa.Column("worker_image_digest", sa.String(64), nullable=False),
        sa.Column("oci_profile_schema", sa.String(100), nullable=False),
        sa.Column("transport_schema", sa.String(100), nullable=False),
        sa.Column("image_reference", sa.String(500), nullable=False),
        sa.Column("image_id", sa.String(71), nullable=False),
        sa.Column("platform", sa.String(32), nullable=False),
        sa.Column("runtime_host", sa.String(500), nullable=False),
        sa.Column("runtime_executable_sha256", sa.String(64), nullable=False),
        sa.Column("seccomp_profile_sha256", sa.String(64), nullable=False),
        sa.Column("runtime_profile_sha256", sa.String(64), nullable=False),
        sa.Column("runtime_attestation_schema", sa.String(100), nullable=False),
        sa.Column("runtime_attestation_json", sa.JSON(), nullable=False),
        sa.Column("runtime_attestation_sha256", sa.String(64), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "run_id",
                "runtime_profile_sha256",
                "worker_image_digest",
                "runtime_attestation_sha256",
            ],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.runtime_profile_sha256",
                "technical_extraction_runs.worker_image_digest",
                "technical_extraction_runs.runtime_attestation_sha256",
            ],
            name="fk_technical_parser_invocation_run_runtime",
        ),
        sa.ForeignKeyConstraint(
            ["page_id", "run_id", "page_number"],
            [
                "technical_extraction_pages.id",
                "technical_extraction_pages.run_id",
                "technical_extraction_pages.page_number",
            ],
            name="fk_technical_parser_invocation_page",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_parser_invocation_id",
        ),
        sa.CheckConstraint(
            "invocation_schema = 'technical-parser-invocation-v1'",
            name="ck_technical_parser_invocation_schema",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("run_attempt_token"),
            name="ck_technical_parser_invocation_run_attempt_token",
        ),
        sa.CheckConstraint(
            "run_attempt_count > 0",
            name="ck_technical_parser_invocation_run_attempt_count",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("attempt_token"),
            name="ck_technical_parser_invocation_attempt_token",
        ),
        sa.CheckConstraint(
            "attempt_count > 0",
            name="ck_technical_parser_invocation_attempt_count",
        ),
        sa.CheckConstraint(
            "page_id IS NULL OR (" + _canonical_uuid4_check("page_id") + ")",
            name="ck_technical_parser_invocation_page_id",
        ),
        sa.CheckConstraint(
            "page_attempt_token IS NULL OR (" + _canonical_uuid4_check("page_attempt_token") + ")",
            name="ck_technical_parser_invocation_page_attempt_token",
        ),
        sa.CheckConstraint(
            "(operation = 'layout' "
            "AND page_number = 0 "
            "AND page_id IS NULL "
            "AND page_attempt_token IS NULL "
            "AND page_attempt_count IS NULL "
            "AND attempt_token = run_attempt_token "
            "AND attempt_count = run_attempt_count) OR "
            "(operation = 'page' "
            "AND page_number BETWEEN 1 AND 500 "
            "AND page_id IS NOT NULL "
            "AND page_attempt_token IS NOT NULL "
            "AND page_attempt_count > 0 "
            "AND attempt_token = page_attempt_token "
            "AND attempt_count = page_attempt_count)",
            name="ck_technical_parser_invocation_operation",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("request_sha256"),
            name="ck_technical_parser_invocation_request_sha256",
        ),
        sa.CheckConstraint(
            "request_size_bytes BETWEEN 1 AND 4096",
            name="ck_technical_parser_invocation_request_size",
        ),
        sa.CheckConstraint(
            "length(extraction_policy) BETWEEN 1 AND 100 "
            "AND extraction_policy = trim(extraction_policy)",
            name="ck_technical_parser_invocation_policy",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("extraction_policy_sha256"),
            name="ck_technical_parser_invocation_policy_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("worker_image_digest"),
            name="ck_technical_parser_invocation_worker_digest",
        ),
        sa.CheckConstraint(
            "oci_profile_schema = 'technical-parser-oci-profile-v1'",
            name="ck_technical_parser_invocation_oci_profile_schema",
        ),
        sa.CheckConstraint(
            "transport_schema = 'technical-parser-stdin-frame-v1'",
            name="ck_technical_parser_invocation_transport_schema",
        ),
        sa.CheckConstraint(
            "length(image_reference) BETWEEN 73 AND 500 "
            "AND image_reference = trim(image_reference) "
            "AND substr(image_reference, length(image_reference) - 71, 72) = "
            "('@sha256:' || worker_image_digest)",
            name="ck_technical_parser_invocation_image_reference",
        ),
        sa.CheckConstraint(
            "length(image_id) = 71 "
            "AND substr(image_id, 1, 7) = 'sha256:' "
            "AND " + _canonical_sha256_check("substr(image_id, 8, 64)"),
            name="ck_technical_parser_invocation_image_id",
        ),
        sa.CheckConstraint(
            "platform IN ('linux/amd64', 'linux/arm64')",
            name="ck_technical_parser_invocation_platform",
        ),
        sa.CheckConstraint(
            "length(runtime_host) BETWEEN 30 AND 500 "
            "AND runtime_host = trim(runtime_host) "
            "AND runtime_host LIKE 'unix:///run/user/%/docker.sock'",
            name="ck_technical_parser_invocation_runtime_host",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("runtime_executable_sha256"),
            name="ck_technical_parser_invocation_runtime_executable_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("seccomp_profile_sha256"),
            name="ck_technical_parser_invocation_seccomp_profile_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("runtime_profile_sha256"),
            name="ck_technical_parser_invocation_runtime_profile_sha256",
        ),
        sa.CheckConstraint(
            "runtime_attestation_schema = 'technical-parser-runtime-attestation-v1'",
            name="ck_technical_parser_invocation_runtime_attestation_schema",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("runtime_attestation_sha256"),
            name="ck_technical_parser_invocation_runtime_attestation_sha256",
        ),
        sa.CheckConstraint(
            "immutable = true",
            name="ck_technical_parser_invocation_immutable",
        ),
        sa.UniqueConstraint(
            "attempt_token",
            name="uq_technical_parser_invocation_attempt_token",
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            "operation",
            "page_number",
            "request_sha256",
            "runtime_attestation_sha256",
            name="uq_technical_parser_invocation_receipt_binding",
        ),
    )
    op.create_index(
        "ix_technical_parser_invocations_run_created",
        "technical_parser_invocations",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_technical_parser_invocations_run_operation_page",
        "technical_parser_invocations",
        ["run_id", "operation", "page_number"],
    )


def _create_invocation_receipts() -> None:
    op.create_table(
        "technical_parser_invocation_receipts",
        sa.Column("invocation_id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("receipt_schema", sa.String(100), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("runtime_attestation_sha256", sa.String(64), nullable=False),
        sa.Column("execution_state", sa.String(30), nullable=False),
        sa.Column("outcome_code", sa.String(100), nullable=False),
        sa.Column("container_id", sa.String(64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("stdout_sha256", sa.String(64), nullable=True),
        sa.Column("stdout_size_bytes", sa.Integer(), nullable=True),
        sa.Column("cleanup_confirmed", sa.Boolean(), nullable=False),
        sa.Column("receipt_json", sa.JSON(), nullable=False),
        sa.Column("receipt_sha256", sa.String(64), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            [
                "invocation_id",
                "run_id",
                "operation",
                "page_number",
                "request_sha256",
                "runtime_attestation_sha256",
            ],
            [
                "technical_parser_invocations.id",
                "technical_parser_invocations.run_id",
                "technical_parser_invocations.operation",
                "technical_parser_invocations.page_number",
                "technical_parser_invocations.request_sha256",
                "technical_parser_invocations.runtime_attestation_sha256",
            ],
            name="fk_technical_parser_invocation_receipt_reservation",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("invocation_id"),
            name="ck_technical_parser_invocation_receipt_invocation_id",
        ),
        sa.CheckConstraint(
            "receipt_schema = 'technical-parser-invocation-receipt-v1'",
            name="ck_technical_parser_invocation_receipt_schema",
        ),
        sa.CheckConstraint(
            "operation IN ('layout', 'page') "
            "AND ((operation = 'layout' AND page_number = 0) OR "
            "(operation = 'page' AND page_number BETWEEN 1 AND 500))",
            name="ck_technical_parser_invocation_receipt_operation",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("request_sha256"),
            name="ck_technical_parser_invocation_receipt_request_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("runtime_attestation_sha256"),
            name="ck_technical_parser_receipt_runtime_attestation_sha256",
        ),
        sa.CheckConstraint(
            "execution_state IN ("
            "'not_started', 'succeeded', 'failed', "
            "'execution_unknown', 'containment_lost')",
            name="ck_technical_parser_invocation_receipt_state",
        ),
        sa.CheckConstraint(
            "length(outcome_code) BETWEEN 1 AND 100 AND outcome_code = trim(outcome_code)",
            name="ck_technical_parser_invocation_receipt_outcome",
        ),
        sa.CheckConstraint(
            "container_id IS NULL OR (" + _canonical_sha256_check("container_id") + ")",
            name="ck_technical_parser_invocation_receipt_container_id",
        ),
        sa.CheckConstraint(
            "exit_code IS NULL OR exit_code BETWEEN 0 AND 255",
            name="ck_technical_parser_invocation_receipt_exit_code",
        ),
        sa.CheckConstraint(
            "(stdout_sha256 IS NULL AND stdout_size_bytes IS NULL) OR "
            "(stdout_sha256 IS NOT NULL "
            "AND stdout_size_bytes BETWEEN 0 AND 30412804)",
            name="ck_technical_parser_invocation_receipt_stdout_binding",
        ),
        sa.CheckConstraint(
            "stdout_sha256 IS NULL OR (" + _canonical_sha256_check("stdout_sha256") + ")",
            name="ck_technical_parser_invocation_receipt_stdout_sha256",
        ),
        sa.CheckConstraint(
            "started_at IS NULL OR completed_at >= started_at",
            name="ck_technical_parser_invocation_receipt_timing",
        ),
        sa.CheckConstraint(
            "(execution_state = 'not_started' "
            "AND container_id IS NULL "
            "AND started_at IS NULL "
            "AND exit_code IS NULL "
            "AND stdout_sha256 IS NULL "
            "AND stdout_size_bytes IS NULL "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'succeeded' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND exit_code = 0 "
            "AND stdout_sha256 IS NOT NULL "
            "AND stdout_size_bytes BETWEEN 1 AND 30412804 "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'failed' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'execution_unknown' "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'containment_lost' "
            "AND cleanup_confirmed = false)",
            name="ck_technical_parser_invocation_receipt_lifecycle",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("receipt_sha256"),
            name="ck_technical_parser_invocation_receipt_sha256",
        ),
        sa.CheckConstraint(
            "immutable = true",
            name="ck_technical_parser_invocation_receipt_immutable",
        ),
    )
    op.create_index(
        "ix_technical_parser_invocation_receipts_run_created",
        "technical_parser_invocation_receipts",
        ["run_id", "created_at"],
    )
    op.create_index(
        "ix_technical_parser_invocation_receipts_state",
        "technical_parser_invocation_receipts",
        ["execution_state"],
    )


def _bind_accepted_invocations() -> None:
    with op.batch_alter_table("technical_extraction_runs") as batch:
        batch.create_foreign_key(
            "fk_technical_extraction_run_layout_invocation",
            "technical_parser_invocation_receipts",
            ["layout_invocation_id"],
            ["invocation_id"],
        )
    with op.batch_alter_table("technical_extraction_pages") as batch:
        batch.create_foreign_key(
            "fk_technical_extraction_page_parser_invocation",
            "technical_parser_invocation_receipts",
            ["parser_invocation_id"],
            ["invocation_id"],
        )


def upgrade() -> None:
    _extend_extraction_runs()
    _extend_extraction_pages()
    _create_invocation_reservations()
    _create_invocation_receipts()
    _bind_accepted_invocations()


def downgrade() -> None:
    raise RuntimeError("Technical parser invocation provenance cannot be downgraded")
