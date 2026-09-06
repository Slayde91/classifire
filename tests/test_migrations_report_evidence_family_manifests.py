from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_report_evidence_family_manifest_migration_upgrades_existing_0018_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "report-evidence-family-manifests.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0018_docx_report_evidence_locators")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "report_evidence_family_manifests",
        "report_evidence_family_members",
    }.issubset(inspector.get_table_names())
    manifest_columns = {
        column["name"] for column in inspector.get_columns("report_evidence_family_manifests")
    }
    assert {
        "project_id",
        "estimate_id",
        "family_reference",
        "member_count",
        "manifest_sha256",
        "approval_reference",
        "approved_by_user_id",
        "approved_at",
    }.issubset(manifest_columns)
    member_columns = {
        column["name"] for column in inspector.get_columns("report_evidence_family_members")
    }
    assert {
        "report_evidence_family_manifest_id",
        "member_sequence",
        "project_evidence_id",
        "stored_file_id",
        "source_sha256",
    }.issubset(member_columns)
    foreign_keys = inspector.get_foreign_keys("report_evidence_family_members")
    assert any(
        foreign_key["constrained_columns"] == ["project_evidence_id", "source_sha256"]
        and foreign_key["referred_table"] == "project_evidence"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["stored_file_id"]
        and foreign_key["referred_table"] == "stored_files"
        for foreign_key in foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0040_draft_pricing_source_profiles"
        )
    engine.dispose()
