from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_expected_label_manifest_migration_upgrades_existing_0011_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "report-expected-label-manifests.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0011_report_evidence_locators")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "report_expected_label_manifests" in inspector.get_table_names()
    columns = {
        column["name"] for column in inspector.get_columns("report_expected_label_manifests")
    }
    assert {
        "project_evidence_id",
        "source_sha256",
        "estimate_id",
        "expected_report_defect_labels",
        "manifest_sha256",
        "approval_reference",
        "approved_by_user_id",
        "approved_at",
    }.issubset(columns)
    foreign_keys = inspector.get_foreign_keys("report_expected_label_manifests")
    assert any(
        foreign_key["constrained_columns"] == ["project_evidence_id", "source_sha256"]
        and foreign_key["referred_table"] == "project_evidence"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["estimate_id"]
        and foreign_key["referred_table"] == "estimates"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["approved_by_user_id"]
        and foreign_key["referred_table"] == "users"
        for foreign_key in foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0040_draft_pricing_source_profiles"
        )
    engine.dispose()
