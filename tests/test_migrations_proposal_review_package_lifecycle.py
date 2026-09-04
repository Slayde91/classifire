from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_proposal_review_package_lifecycle_migration_upgrades_0013_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "proposal-review-package-lifecycle.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0013_report_defect_scope_admissions")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "proposal_review_packages",
        "proposal_review_package_redactions",
    }.issubset(inspector.get_table_names())
    columns = {
        column["name"] for column in inspector.get_columns("proposal_review_packages")
    }
    assert {
        "project_id",
        "estimate_id",
        "project_evidence_id",
        "report_sha256",
        "approved_expected_label_manifest_id",
        "approved_expected_label_manifest_sha256",
        "approval_reference",
        "package_manifest_sha256",
        "completion_receipt_sha256",
        "reviewer_summary_json",
        "safe_locator_json",
        "record_owner",
        "retention_until",
        "legal_hold_active",
    }.issubset(columns)
    package_foreign_keys = inspector.get_foreign_keys("proposal_review_packages")
    assert any(
        foreign_key["constrained_columns"] == ["project_evidence_id", "report_sha256"]
        and foreign_key["referred_table"] == "project_evidence"
        for foreign_key in package_foreign_keys
    )
    redaction_foreign_keys = inspector.get_foreign_keys("proposal_review_package_redactions")
    assert any(
        foreign_key["constrained_columns"] == ["proposal_review_package_id"]
        and foreign_key["referred_table"] == "proposal_review_packages"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in redaction_foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0024_signed_physical_model_lock_replacement_admissions"
        )