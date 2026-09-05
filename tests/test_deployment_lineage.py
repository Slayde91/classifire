from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from classifire.services.deployment_lineage import assess_deployment_lineage


def _assessment(  # type: ignore[no-untyped-def]
    revision: str,
    *,
    required_tables: bool,
    legacy_submission_table: bool = False,
    draft_tables: bool = True,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
        connection.execute(text("CREATE TABLE physical_model_admissions (id VARCHAR(36))"))
        if required_tables:
            connection.execute(
                text("CREATE TABLE physical_model_submission_receipts (id VARCHAR(36))")
            )
            connection.execute(
                text("CREATE TABLE physical_model_lock_amendment_admissions (id VARCHAR(36))")
            )
            connection.execute(
                text("CREATE TABLE physical_model_lock_amendment_outcomes (id VARCHAR(36))")
            )
            connection.execute(
                text("CREATE TABLE physical_model_lock_replacement_admissions (id VARCHAR(36))")
            )
            connection.execute(
                text("CREATE TABLE physical_model_lock_replacement_outcomes (id VARCHAR(36))")
            )
            connection.execute(text("CREATE TABLE visual_validation_receipts (id VARCHAR(36))"))
            connection.execute(text("CREATE TABLE project_evidence (id VARCHAR(36))"))
            connection.execute(text("CREATE TABLE report_evidence_locators (id VARCHAR(36))"))
            connection.execute(
                text("CREATE TABLE report_evidence_family_manifests (id VARCHAR(36))")
            )
            connection.execute(text("CREATE TABLE report_evidence_family_members (id VARCHAR(36))"))
            connection.execute(text("CREATE TABLE report_defect_scopes (id VARCHAR(36))"))
            connection.execute(
                text("CREATE TABLE report_expected_label_manifests (id VARCHAR(36))")
            )
            connection.execute(text("CREATE TABLE proposal_review_packages (id VARCHAR(36))"))
            connection.execute(text("CREATE TABLE proposal_review_annotations (id VARCHAR(36))"))
            connection.execute(
                text("CREATE TABLE proposal_review_package_redactions (id VARCHAR(36))")
            )
        if required_tables and draft_tables:
            connection.execute(text("CREATE TABLE draft_scopes (id VARCHAR(36))"))
            connection.execute(text("CREATE TABLE draft_scope_revisions (id VARCHAR(36))"))
        if legacy_submission_table:
            connection.execute(
                text("CREATE TABLE physical_model_initial_submissions (id VARCHAR(36))")
            )
    with Session(engine) as db:
        return assess_deployment_lineage(db)


def test_clean_stack_head_is_ready_only_with_all_required_journal_tables() -> None:
    result = _assessment(
        "0027_draft_scope_revisions",
        required_tables=True,
    )
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"
    assert result.database_write_performed is False


def test_immediately_previous_head_requires_the_draft_scope_migration() -> None:
    result = _assessment("0026_single_active_technical_release", required_tables=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_previous_head_with_stray_legacy_table_requires_retirement() -> None:
    result = _assessment(
        "0007_reconcile_adjudicated_admission_lineages",
        required_tables=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED"
    assert result.unexpected_tables == ("physical_model_initial_submissions",)


def test_current_head_with_stray_legacy_table_fails_as_schema_drift() -> None:
    result = _assessment(
        "0027_draft_scope_revisions",
        required_tables=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"


def test_legacy_adjudicated_head_fails_closed_for_rehearsal() -> None:
    result = _assessment("0006_adjudicated_canonical_admissions", required_tables=False)
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_LINEAGE_REHEARSAL_REQUIRED"
    assert result.missing_tables == (
        "draft_scope_revisions",
        "draft_scopes",
        "physical_model_lock_amendment_admissions",
        "physical_model_lock_amendment_outcomes",
        "physical_model_lock_replacement_admissions",
        "physical_model_lock_replacement_outcomes",
        "physical_model_submission_receipts",
        "project_evidence",
        "proposal_review_annotations",
        "proposal_review_package_redactions",
        "proposal_review_packages",
        "report_defect_scopes",
        "report_evidence_family_manifests",
        "report_evidence_family_members",
        "report_evidence_locators",
        "report_expected_label_manifests",
        "visual_validation_receipts",
    )


def test_unknown_revision_fails_closed() -> None:
    result = _assessment("unexpected_revision", required_tables=True)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"


def test_current_head_without_draft_tables_fails_as_schema_drift() -> None:
    result = _assessment("0027_draft_scope_revisions", required_tables=True, draft_tables=False)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_tables == ("draft_scope_revisions", "draft_scopes")
    assert result.database_write_performed is False
