from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade


def _legacy_database(tmp_path: Path, *, retained_admission: bool) -> tuple[str, dict[str, str]]:
    database_path = tmp_path / "legacy-adjudicated-lineage.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0004_agent_service_principals")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE physical_model_admissions "
                "(id VARCHAR(36) PRIMARY KEY, artifact_manifest_sha256 VARCHAR(64) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE physical_model_initial_submissions "
                "(id VARCHAR(36) PRIMARY KEY, admission_record_id VARCHAR(36) NOT NULL)"
            )
        )
        if retained_admission:
            connection.execute(
                text(
                    "INSERT INTO physical_model_admissions (id, artifact_manifest_sha256) "
                    "VALUES ('legacy-admission', 'A')"
                )
            )
        connection.execute(
            text("UPDATE alembic_version SET version_num='0006_adjudicated_canonical_admissions'")
        )
    return database_url, environment


def test_empty_legacy_journal_reconciles_to_one_clean_head(tmp_path: Path) -> None:
    database_url, environment = _legacy_database(tmp_path, retained_admission=False)

    _upgrade(database_url, environment, "head", enforce_sqlite_foreign_keys=True)

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "physical_model_initial_submissions" not in inspector.get_table_names()
    admission_columns = {
        column["name"] for column in inspector.get_columns("physical_model_admissions")
    }
    assert {"artifact_digests", "policy_versions", "normalised_submission_payload_json"}.issubset(
        admission_columns
    )
    assert "artifact_manifest_sha256" not in admission_columns
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0045_draft_pricing_recipe_links"
        )
        assert (
            connection.execute(text("SELECT COUNT(*) FROM physical_model_admissions")).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM physical_model_submission_receipts")
            ).scalar_one()
            == 0
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_legacy_reconciliation_rejects_retained_admission_records(tmp_path: Path) -> None:
    database_url, environment = _legacy_database(tmp_path, retained_admission=True)

    result = _run_migration(
        database_url,
        environment,
        "upgrade",
        "head",
        expect_success=False,
    )

    assert result.returncode != 0
    assert "Refusing legacy adjudication-lineage reconciliation" in result.stdout + result.stderr
    engine = create_engine(database_url)
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT COUNT(*) FROM physical_model_admissions")).scalar_one()
            == 1
        )
