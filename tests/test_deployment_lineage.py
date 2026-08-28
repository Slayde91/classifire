from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.services.deployment_lineage import (
    CLEAN_STACK_HEAD,
    assess_deployment_lineage,
)


def _assessment(  # type: ignore[no-untyped-def]
    revision: str,
    *,
    receipt_table: bool,
    legacy_submission_table: bool = False,
    publication_guard: bool | None = None,
    relationship_table: bool | None = None,
    missing_core_table: bool = False,
    missing_core_column: bool = False,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
        if publication_guard is None:
            publication_guard = revision in {
                "0010_release_publication_slot",
                "0011_technical_document_relationships",
                "0012_technical_source_registration",
                "0013_technical_intake_batches",
                "0014_technical_extraction_foundation",
                "0015_technical_parser_invocation_provenance",
                "0016_parser_attestation_v2",
                "0017_technical_intake_drafts",
                "0018_shared_malware_containment",
            }
        if not publication_guard:
            connection.execute(
                text("DROP INDEX IF EXISTS uq_library_release_active_publication_slot")
            )
        if not receipt_table:
            connection.execute(text("DROP TABLE physical_model_submission_receipts"))
            connection.execute(text("DROP TABLE visual_validation_receipts"))
        if relationship_table is None:
            relationship_table = revision in {
                "0011_technical_document_relationships",
                "0012_technical_source_registration",
                "0013_technical_intake_batches",
                "0014_technical_extraction_foundation",
                "0015_technical_parser_invocation_provenance",
                "0016_parser_attestation_v2",
                "0017_technical_intake_drafts",
                "0018_shared_malware_containment",
            }
        if not relationship_table:
            connection.execute(text("DROP TABLE technical_document_relationships"))
        if legacy_submission_table:
            connection.execute(
                text("CREATE TABLE physical_model_initial_submissions (id VARCHAR(36))")
            )
        if missing_core_table:
            connection.execute(text("DROP TABLE users"))
        if missing_core_column:
            connection.execute(text("DROP TABLE users"))
            connection.execute(text("CREATE TABLE users (id VARCHAR(36))"))
    with Session(engine) as db:
        return assess_deployment_lineage(db)


def test_clean_stack_head_is_ready_only_with_both_journal_tables() -> None:
    result = _assessment(CLEAN_STACK_HEAD, receipt_table=True)
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"
    assert result.database_write_performed is False


def test_previous_head_with_stray_legacy_table_requires_retirement() -> None:
    result = _assessment(
        "0007_reconcile_adjudicated_admission_lineages",
        receipt_table=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED"
    assert result.unexpected_tables == ("physical_model_initial_submissions",)


def test_current_head_with_stray_legacy_table_fails_as_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"


def test_pre_publication_head_requires_publication_slot_migration() -> None:
    result = _assessment("0009_visual_validation_receipts", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_current_head_without_publication_slot_guard_is_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        publication_guard=False,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"


def test_previous_clean_head_requires_relationship_migration() -> None:
    result = _assessment("0010_release_publication_slot", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_relationship_head_requires_source_registration_migration() -> None:
    result = _assessment("0011_technical_document_relationships", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_source_registration_head_requires_batch_ledger_migration() -> None:
    result = _assessment("0012_technical_source_registration", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_batch_ledger_head_requires_extraction_foundation_migration() -> None:
    result = _assessment("0013_technical_intake_batches", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_extraction_foundation_head_requires_invocation_provenance_migration() -> None:
    result = _assessment("0014_technical_extraction_foundation", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_invocation_provenance_head_requires_attestation_v2_migration() -> None:
    result = _assessment(
        "0015_technical_parser_invocation_provenance",
        receipt_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_attestation_v2_head_requires_intake_draft_migration() -> None:
    result = _assessment(
        "0016_parser_attestation_v2",
        receipt_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_intake_draft_head_requires_shared_malware_containment_migration() -> None:
    result = _assessment(
        "0017_technical_intake_drafts",
        receipt_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_current_head_without_relationship_table_is_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        relationship_table=False,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"


def test_current_head_without_core_model_table_is_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        missing_core_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_tables == ("users",)


def test_current_head_without_core_model_columns_is_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        missing_core_column=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert "users.email" in result.missing_columns


def test_legacy_adjudicated_head_fails_closed_for_rehearsal() -> None:
    result = _assessment("0006_adjudicated_canonical_admissions", receipt_table=False)
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_LINEAGE_REHEARSAL_REQUIRED"
    assert result.missing_tables == (
        "physical_model_submission_receipts",
        "technical_document_relationships",
        "visual_validation_receipts",
    )


def test_unknown_revision_fails_closed() -> None:
    result = _assessment("unexpected_revision", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
