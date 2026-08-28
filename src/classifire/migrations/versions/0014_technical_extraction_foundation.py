"""Add Draft-only technical extraction run and page evidence lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_technical_extraction_foundation"
down_revision = "0013_technical_intake_batches"
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


def upgrade() -> None:
    op.create_index(
        "uq_stored_file_extraction_source_identity",
        "stored_files",
        ["id", "sha256", "size_bytes"],
        unique=True,
    )
    op.create_index(
        "uq_technical_document_stored_file_binding",
        "technical_documents",
        ["id", "stored_file_id"],
        unique=True,
    )
    op.create_table(
        "technical_extraction_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("run_schema", sa.String(100), nullable=False),
        sa.Column(
            "source_stored_file_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column(
            "technical_document_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("extraction_policy", sa.String(100), nullable=False),
        sa.Column("extraction_policy_sha256", sa.String(64), nullable=False),
        sa.Column(
            "ocr_low_confidence_threshold",
            sa.Numeric(5, 2),
            nullable=False,
        ),
        sa.Column("worker_image_digest", sa.String(64), nullable=False),
        sa.Column("page_evidence_schema", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("attempt_token", sa.String(36), nullable=True),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("layout_schema", sa.String(100), nullable=True),
        sa.Column("layout_sha256", sa.String(64), nullable=True),
        sa.Column("layout_size_bytes", sa.Integer(), nullable=True),
        sa.Column("manifest_sha256", sa.String(64), nullable=True),
        sa.Column("outcome_code", sa.String(100), nullable=True),
        sa.Column("outcome_retryable", sa.Boolean(), nullable=True),
        sa.Column("last_outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "requested_by_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["technical_document_id", "source_stored_file_id"],
            ["technical_documents.id", "technical_documents.stored_file_id"],
            name="fk_technical_extraction_run_document_source",
        ),
        sa.ForeignKeyConstraint(
            ["source_stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_technical_extraction_run_source_bytes",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_extraction_run_id",
        ),
        sa.CheckConstraint(
            "run_schema = 'technical-extraction-run-v1'",
            name="ck_technical_extraction_run_schema",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("source_sha256"),
            name="ck_technical_extraction_run_source_sha256",
        ),
        sa.CheckConstraint(
            "source_size_bytes BETWEEN 1 AND 1073741824",
            name="ck_technical_extraction_run_source_size",
        ),
        sa.CheckConstraint(
            "length(extraction_policy) BETWEEN 1 AND 100 "
            "AND extraction_policy = trim(extraction_policy)",
            name="ck_technical_extraction_run_policy",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("extraction_policy_sha256"),
            name="ck_technical_extraction_run_policy_sha256",
        ),
        sa.CheckConstraint(
            "ocr_low_confidence_threshold BETWEEN 0 AND 100",
            name="ck_technical_extraction_run_ocr_threshold",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("worker_image_digest"),
            name="ck_technical_extraction_run_worker_digest",
        ),
        sa.CheckConstraint(
            "page_evidence_schema = 'technical-page-evidence-v1'",
            name="ck_technical_extraction_run_evidence_schema",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'completed', 'completed_with_attention', 'failed')",
            name="ck_technical_extraction_run_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_extraction_run_attempt_count",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count BETWEEN 1 AND 500",
            name="ck_technical_extraction_run_page_count",
        ),
        sa.CheckConstraint(
            "(page_count IS NULL "
            "AND layout_schema IS NULL "
            "AND layout_sha256 IS NULL "
            "AND layout_size_bytes IS NULL) OR "
            "(page_count BETWEEN 1 AND 500 "
            "AND layout_schema = 'technical-parser-layout-v1' "
            "AND layout_sha256 IS NOT NULL "
            "AND layout_size_bytes BETWEEN 1 AND 131072)",
            name="ck_technical_extraction_run_layout_binding",
        ),
        sa.CheckConstraint(
            "layout_sha256 IS NULL OR (" + _canonical_sha256_check("layout_sha256") + ")",
            name="ck_technical_extraction_run_layout_sha256",
        ),
        sa.CheckConstraint(
            "attempt_token IS NULL OR (" + _canonical_uuid4_check("attempt_token") + ")",
            name="ck_technical_extraction_run_attempt_token",
        ),
        sa.CheckConstraint(
            "manifest_sha256 IS NULL OR (" + _canonical_sha256_check("manifest_sha256") + ")",
            name="ck_technical_extraction_run_manifest_sha256",
        ),
        sa.CheckConstraint(
            "outcome_code IS NULL OR ("
            "length(outcome_code) BETWEEN 1 AND 100 "
            "AND outcome_code = trim(outcome_code))",
            name="ck_technical_extraction_run_outcome_code",
        ),
        sa.CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_extraction_run_claim",
        ),
        sa.CheckConstraint(
            "(status = 'queued' "
            "AND completed_at IS NULL "
            "AND manifest_sha256 IS NULL "
            "AND ((attempt_count = 0 "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL) OR "
            "(attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'EXTRACTION_COMPLETE', 'EXTRACTION_COMPLETE_WITH_ATTENTION'"
            ") "
            "AND outcome_retryable = true "
            "AND last_outcome_at IS NOT NULL))) OR "
            "(status = 'processing' "
            "AND completed_at IS NULL "
            "AND manifest_sha256 IS NULL "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL) OR "
            "(status = 'completed' "
            "AND completed_at IS NOT NULL "
            "AND page_count IS NOT NULL "
            "AND manifest_sha256 IS NOT NULL "
            "AND outcome_code = 'EXTRACTION_COMPLETE' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status = 'completed_with_attention' "
            "AND completed_at IS NOT NULL "
            "AND page_count IS NOT NULL "
            "AND manifest_sha256 IS NOT NULL "
            "AND outcome_code = 'EXTRACTION_COMPLETE_WITH_ATTENTION' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status = 'failed' "
            "AND completed_at IS NOT NULL "
            "AND manifest_sha256 IS NULL "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'EXTRACTION_COMPLETE', 'EXTRACTION_COMPLETE_WITH_ATTENTION'"
            ") "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND attempt_count > 0)",
            name="ck_technical_extraction_run_terminal_state",
        ),
        sa.UniqueConstraint(
            "technical_document_id",
            "source_stored_file_id",
            "source_sha256",
            "source_size_bytes",
            "extraction_policy_sha256",
            "ocr_low_confidence_threshold",
            "worker_image_digest",
            name="uq_technical_extraction_run_identity",
        ),
        sa.UniqueConstraint(
            "attempt_token",
            name="uq_technical_extraction_run_attempt_token",
        ),
        sa.UniqueConstraint(
            "id",
            "page_count",
            name="uq_technical_extraction_run_page_count_binding",
        ),
        sa.UniqueConstraint(
            "id",
            "layout_sha256",
            name="uq_technical_extraction_run_layout_binding",
        ),
        sa.UniqueConstraint(
            "id",
            "ocr_low_confidence_threshold",
            name="uq_technical_extraction_run_ocr_threshold_binding",
        ),
    )
    op.create_index(
        "ix_technical_extraction_runs_status",
        "technical_extraction_runs",
        ["status"],
    )
    op.create_index(
        "ix_technical_extraction_runs_status_created",
        "technical_extraction_runs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_technical_extraction_runs_source_sha256",
        "technical_extraction_runs",
        ["source_sha256"],
    )

    op.create_table(
        "technical_derived_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("artifact_schema", sa.String(100), nullable=False),
        sa.Column(
            "run_id",
            sa.String(36),
            sa.ForeignKey("technical_extraction_runs.id"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("artifact_kind", sa.String(40), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("validation_policy", sa.String(100), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_derived_artifact_id",
        ),
        sa.CheckConstraint(
            "artifact_schema = 'technical-derived-artifact-v1'",
            name="ck_technical_derived_artifact_schema",
        ),
        sa.CheckConstraint(
            "page_number BETWEEN 1 AND 500",
            name="ck_technical_derived_artifact_page",
        ),
        sa.CheckConstraint(
            "artifact_kind IN ('page_evidence_json', 'page_image_png')",
            name="ck_technical_derived_artifact_kind",
        ),
        sa.CheckConstraint(
            "(artifact_kind = 'page_evidence_json' "
            "AND media_type = 'application/json') OR "
            "(artifact_kind = 'page_image_png' "
            "AND media_type = 'image/png')",
            name="ck_technical_derived_artifact_media_type",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("sha256"),
            name="ck_technical_derived_artifact_sha256",
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 26214400",
            name="ck_technical_derived_artifact_size",
        ),
        sa.CheckConstraint(
            "length(storage_path) BETWEEN 1 AND 1000 AND storage_path = trim(storage_path)",
            name="ck_technical_derived_artifact_storage_path",
        ),
        sa.CheckConstraint(
            "validation_policy = 'technical-page-evidence-validator-v1'",
            name="ck_technical_derived_artifact_validation_policy",
        ),
        sa.CheckConstraint(
            "immutable = true",
            name="ck_technical_derived_artifact_immutable",
        ),
        sa.UniqueConstraint(
            "run_id",
            "page_number",
            "artifact_kind",
            name="uq_technical_derived_artifact_run_page_kind",
        ),
        sa.UniqueConstraint(
            "id",
            "run_id",
            "page_number",
            "artifact_kind",
            "sha256",
            "size_bytes",
            name="uq_technical_derived_artifact_page_binding",
        ),
    )
    op.create_index(
        "ix_technical_derived_artifacts_run_page",
        "technical_derived_artifacts",
        ["run_id", "page_number"],
    )
    op.create_index(
        "ix_technical_derived_artifacts_sha256",
        "technical_derived_artifacts",
        ["sha256"],
    )

    op.create_table(
        "technical_extraction_pages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("page_schema", sa.String(100), nullable=False),
        sa.Column(
            "run_id",
            sa.String(36),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("layout_sha256", sa.String(64), nullable=False),
        sa.Column("layout_page_width_points", sa.Numeric(12, 4), nullable=False),
        sa.Column("layout_page_height_points", sa.Numeric(12, 4), nullable=False),
        sa.Column("evidence_schema", sa.String(100), nullable=False),
        sa.Column("validator_policy", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempt_token", sa.String(36), nullable=True),
        sa.Column("attempt_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("outcome_code", sa.String(100), nullable=True),
        sa.Column("outcome_retryable", sa.Boolean(), nullable=True),
        sa.Column("last_outcome_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("packet_artifact_id", sa.String(36), nullable=True),
        sa.Column("packet_artifact_kind", sa.String(40), nullable=True),
        sa.Column("packet_size_bytes", sa.Integer(), nullable=True),
        sa.Column("page_image_artifact_id", sa.String(36), nullable=True),
        sa.Column("page_image_artifact_kind", sa.String(40), nullable=True),
        sa.Column("page_image_size_bytes", sa.Integer(), nullable=True),
        sa.Column("packet_sha256", sa.String(64), nullable=True),
        sa.Column("page_image_sha256", sa.String(64), nullable=True),
        sa.Column("binding_sha256", sa.String(64), nullable=True),
        sa.Column("page_width_points", sa.Numeric(12, 4), nullable=True),
        sa.Column("page_height_points", sa.Numeric(12, 4), nullable=True),
        sa.Column("image_width_pixels", sa.Integer(), nullable=True),
        sa.Column("image_height_pixels", sa.Integer(), nullable=True),
        sa.Column("extraction_mode", sa.String(30), nullable=True),
        sa.Column("native_block_count", sa.Integer(), nullable=True),
        sa.Column("ocr_block_count", sa.Integer(), nullable=True),
        sa.Column("minimum_ocr_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("ocr_status", sa.String(30), nullable=True),
        sa.Column("ocr_low_confidence_threshold", sa.Numeric(5, 2), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id", "page_count"],
            ["technical_extraction_runs.id", "technical_extraction_runs.page_count"],
            name="fk_technical_extraction_page_run_page_count",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "ocr_low_confidence_threshold"],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.ocr_low_confidence_threshold",
            ],
            name="fk_technical_extraction_page_run_ocr_threshold",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "layout_sha256"],
            [
                "technical_extraction_runs.id",
                "technical_extraction_runs.layout_sha256",
            ],
            name="fk_technical_extraction_page_run_layout",
        ),
        sa.ForeignKeyConstraint(
            [
                "packet_artifact_id",
                "run_id",
                "page_number",
                "packet_artifact_kind",
                "packet_sha256",
                "packet_size_bytes",
            ],
            [
                "technical_derived_artifacts.id",
                "technical_derived_artifacts.run_id",
                "technical_derived_artifacts.page_number",
                "technical_derived_artifacts.artifact_kind",
                "technical_derived_artifacts.sha256",
                "technical_derived_artifacts.size_bytes",
            ],
            name="fk_technical_extraction_page_packet_binding",
        ),
        sa.ForeignKeyConstraint(
            [
                "page_image_artifact_id",
                "run_id",
                "page_number",
                "page_image_artifact_kind",
                "page_image_sha256",
                "page_image_size_bytes",
            ],
            [
                "technical_derived_artifacts.id",
                "technical_derived_artifacts.run_id",
                "technical_derived_artifacts.page_number",
                "technical_derived_artifacts.artifact_kind",
                "technical_derived_artifacts.sha256",
                "technical_derived_artifacts.size_bytes",
            ],
            name="fk_technical_extraction_page_image_binding",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_extraction_page_id",
        ),
        sa.CheckConstraint(
            "page_schema = 'technical-extraction-page-v1'",
            name="ck_technical_extraction_page_schema",
        ),
        sa.CheckConstraint(
            "evidence_schema = 'technical-page-evidence-v1'",
            name="ck_technical_extraction_page_evidence_schema",
        ),
        sa.CheckConstraint(
            "validator_policy = 'technical-page-evidence-validator-v1'",
            name="ck_technical_extraction_page_validator_policy",
        ),
        sa.CheckConstraint(
            "status IN ("
            "'pending', 'processing', 'completed', 'needs_attention', 'failed', 'cancelled'"
            ")",
            name="ck_technical_extraction_page_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_technical_extraction_page_attempt_count",
        ),
        sa.CheckConstraint(
            "attempt_token IS NULL OR (" + _canonical_uuid4_check("attempt_token") + ")",
            name="ck_technical_extraction_page_attempt_token",
        ),
        sa.CheckConstraint(
            "outcome_code IS NULL OR ("
            "length(outcome_code) BETWEEN 1 AND 100 "
            "AND outcome_code = trim(outcome_code))",
            name="ck_technical_extraction_page_outcome_code",
        ),
        sa.CheckConstraint(
            "(status = 'processing' "
            "AND attempt_token IS NOT NULL "
            "AND attempt_started_at IS NOT NULL "
            "AND attempt_count > 0) OR "
            "(status <> 'processing' "
            "AND attempt_token IS NULL "
            "AND attempt_started_at IS NULL)",
            name="ck_technical_extraction_page_claim",
        ),
        sa.CheckConstraint(
            "(status = 'pending' "
            "AND attempt_count = 0 "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'processing' "
            "AND outcome_code IS NULL "
            "AND outcome_retryable IS NULL "
            "AND last_outcome_at IS NULL "
            "AND completed_at IS NULL) OR "
            "(status = 'completed' "
            "AND attempt_count > 0 "
            "AND outcome_code = 'PAGE_EXTRACTION_COMPLETE' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'needs_attention' "
            "AND attempt_count > 0 "
            "AND outcome_code = 'PAGE_EXTRACTION_NEEDS_ATTENTION' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'failed' "
            "AND attempt_count > 0 "
            "AND outcome_code IS NOT NULL "
            "AND outcome_code NOT IN ("
            "'PAGE_EXTRACTION_COMPLETE', 'PAGE_EXTRACTION_NEEDS_ATTENTION'"
            ") "
            "AND outcome_retryable IS NOT NULL "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL) OR "
            "(status = 'cancelled' "
            "AND outcome_code = 'PAGE_EXTRACTION_CANCELLED' "
            "AND outcome_retryable = false "
            "AND last_outcome_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_technical_extraction_page_lifecycle",
        ),
        sa.CheckConstraint(
            "page_number BETWEEN 1 AND 500 "
            "AND page_count BETWEEN 1 AND 500 "
            "AND page_number <= page_count",
            name="ck_technical_extraction_page_number",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("layout_sha256"),
            name="ck_technical_extraction_page_layout_sha256",
        ),
        sa.CheckConstraint(
            "layout_page_width_points > 0 "
            "AND layout_page_width_points <= 20000 "
            "AND layout_page_height_points > 0 "
            "AND layout_page_height_points <= 20000",
            name="ck_technical_extraction_page_layout_dimensions",
        ),
        sa.CheckConstraint(
            "packet_artifact_kind IS NULL OR packet_artifact_kind = 'page_evidence_json'",
            name="ck_technical_extraction_page_packet_kind",
        ),
        sa.CheckConstraint(
            "page_image_artifact_kind IS NULL OR page_image_artifact_kind = 'page_image_png'",
            name="ck_technical_extraction_page_image_kind",
        ),
        sa.CheckConstraint(
            "packet_size_bytes IS NULL OR packet_size_bytes BETWEEN 1 AND 4194304",
            name="ck_technical_extraction_page_packet_size",
        ),
        sa.CheckConstraint(
            "page_image_size_bytes IS NULL OR page_image_size_bytes BETWEEN 1 AND 26214400",
            name="ck_technical_extraction_page_image_size",
        ),
        sa.CheckConstraint(
            "ocr_status IS NULL OR ocr_status IN ("
            "'ocr_not_required', 'ocr_completed', 'low_confidence', 'unreadable'"
            ")",
            name="ck_technical_extraction_page_ocr_status",
        ),
        sa.CheckConstraint(
            "ocr_low_confidence_threshold IS NULL OR "
            "ocr_low_confidence_threshold BETWEEN 0 AND 100",
            name="ck_technical_extraction_page_ocr_threshold",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("packet_sha256"),
            name="ck_technical_extraction_page_packet_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("page_image_sha256"),
            name="ck_technical_extraction_page_image_sha256",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("binding_sha256"),
            name="ck_technical_extraction_page_binding_sha256",
        ),
        sa.CheckConstraint(
            "page_width_points > 0 AND page_width_points <= 20000 "
            "AND page_height_points > 0 AND page_height_points <= 20000",
            name="ck_technical_extraction_page_dimensions",
        ),
        sa.CheckConstraint(
            "page_width_points IS NULL OR ("
            "page_width_points = layout_page_width_points "
            "AND page_height_points = layout_page_height_points)",
            name="ck_technical_extraction_page_output_layout_dimensions",
        ),
        sa.CheckConstraint(
            "image_width_pixels BETWEEN 1 AND 4096 "
            "AND image_height_pixels BETWEEN 1 AND 4096 "
            "AND image_width_pixels * image_height_pixels <= 8000000",
            name="ck_technical_extraction_page_image_dimensions",
        ),
        sa.CheckConstraint(
            "extraction_mode IN ('native_text', 'ocr', 'hybrid', 'unreadable')",
            name="ck_technical_extraction_page_mode",
        ),
        sa.CheckConstraint(
            "native_block_count BETWEEN 0 AND 10000 "
            "AND ocr_block_count BETWEEN 0 AND 10000 "
            "AND native_block_count + ocr_block_count <= 10000",
            name="ck_technical_extraction_page_block_counts",
        ),
        sa.CheckConstraint(
            "(extraction_mode = 'native_text' "
            "AND native_block_count > 0 AND ocr_block_count = 0) OR "
            "(extraction_mode = 'ocr' "
            "AND native_block_count = 0 AND ocr_block_count > 0) OR "
            "(extraction_mode = 'hybrid' "
            "AND native_block_count > 0 AND ocr_block_count > 0) OR "
            "(extraction_mode = 'unreadable' "
            "AND native_block_count = 0 AND ocr_block_count = 0 "
            "AND human_review_required = true)",
            name="ck_technical_extraction_page_mode_counts",
        ),
        sa.CheckConstraint(
            "(ocr_block_count = 0 AND minimum_ocr_confidence IS NULL) OR "
            "(ocr_block_count > 0 "
            "AND minimum_ocr_confidence BETWEEN 0 AND 100)",
            name="ck_technical_extraction_page_ocr_confidence",
        ),
        sa.CheckConstraint(
            "packet_artifact_id <> page_image_artifact_id",
            name="ck_technical_extraction_page_distinct_artifacts",
        ),
        sa.CheckConstraint(
            "(status IN ('completed', 'needs_attention') "
            "AND packet_artifact_id IS NOT NULL "
            "AND packet_artifact_kind = 'page_evidence_json' "
            "AND packet_size_bytes IS NOT NULL "
            "AND page_image_artifact_id IS NOT NULL "
            "AND page_image_artifact_kind = 'page_image_png' "
            "AND page_image_size_bytes IS NOT NULL "
            "AND packet_sha256 IS NOT NULL "
            "AND page_image_sha256 IS NOT NULL "
            "AND binding_sha256 IS NOT NULL "
            "AND page_width_points IS NOT NULL "
            "AND page_height_points IS NOT NULL "
            "AND image_width_pixels IS NOT NULL "
            "AND image_height_pixels IS NOT NULL "
            "AND extraction_mode IS NOT NULL "
            "AND native_block_count IS NOT NULL "
            "AND ocr_block_count IS NOT NULL "
            "AND ocr_status IS NOT NULL "
            "AND ocr_low_confidence_threshold IS NOT NULL "
            "AND human_review_required IS NOT NULL) OR "
            "(status NOT IN ('completed', 'needs_attention') "
            "AND packet_artifact_id IS NULL "
            "AND packet_artifact_kind IS NULL "
            "AND packet_size_bytes IS NULL "
            "AND page_image_artifact_id IS NULL "
            "AND page_image_artifact_kind IS NULL "
            "AND page_image_size_bytes IS NULL "
            "AND packet_sha256 IS NULL "
            "AND page_image_sha256 IS NULL "
            "AND binding_sha256 IS NULL "
            "AND page_width_points IS NULL "
            "AND page_height_points IS NULL "
            "AND image_width_pixels IS NULL "
            "AND image_height_pixels IS NULL "
            "AND extraction_mode IS NULL "
            "AND native_block_count IS NULL "
            "AND ocr_block_count IS NULL "
            "AND minimum_ocr_confidence IS NULL "
            "AND ocr_status IS NULL "
            "AND ocr_low_confidence_threshold IS NULL "
            "AND human_review_required IS NULL)",
            name="ck_technical_extraction_page_output_presence",
        ),
        sa.CheckConstraint(
            "(status = 'completed' AND human_review_required = false) OR "
            "(status = 'needs_attention' AND human_review_required = true) OR "
            "status NOT IN ('completed', 'needs_attention')",
            name="ck_technical_extraction_page_review_state",
        ),
        sa.CheckConstraint(
            "(ocr_status = 'ocr_not_required' "
            "AND ocr_block_count = 0 "
            "AND native_block_count > 0 "
            "AND minimum_ocr_confidence IS NULL) OR "
            "(ocr_status = 'ocr_completed' "
            "AND ocr_block_count > 0 "
            "AND minimum_ocr_confidence >= ocr_low_confidence_threshold) OR "
            "(ocr_status = 'low_confidence' "
            "AND ocr_block_count > 0 "
            "AND minimum_ocr_confidence < ocr_low_confidence_threshold "
            "AND human_review_required = true) OR "
            "(ocr_status = 'unreadable' "
            "AND ocr_block_count = 0 "
            "AND minimum_ocr_confidence IS NULL "
            "AND human_review_required = true) OR "
            "ocr_status IS NULL",
            name="ck_technical_extraction_page_ocr_state",
        ),
        sa.UniqueConstraint(
            "run_id",
            "page_number",
            name="uq_technical_extraction_page_run_page",
        ),
        sa.UniqueConstraint(
            "packet_artifact_id",
            name="uq_technical_extraction_page_packet_artifact",
        ),
        sa.UniqueConstraint(
            "page_image_artifact_id",
            name="uq_technical_extraction_page_image_artifact",
        ),
        sa.UniqueConstraint(
            "attempt_token",
            name="uq_technical_extraction_page_attempt_token",
        ),
    )
    op.create_index(
        "ix_technical_extraction_pages_status",
        "technical_extraction_pages",
        ["status"],
    )
    op.create_index(
        "ix_technical_extraction_pages_run_page",
        "technical_extraction_pages",
        ["run_id", "page_number"],
    )
    op.create_index(
        "ix_technical_extraction_pages_review_required",
        "technical_extraction_pages",
        ["human_review_required"],
    )
    op.create_index(
        "ix_technical_extraction_pages_run_status_page",
        "technical_extraction_pages",
        ["run_id", "status", "page_number"],
    )
    op.create_index(
        "uq_technical_extraction_pages_processing_run",
        "technical_extraction_pages",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("status = 'processing'"),
        postgresql_where=sa.text("status = 'processing'"),
    )


def downgrade() -> None:
    raise RuntimeError("Technical extraction evidence lineage cannot be downgraded")
