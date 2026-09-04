from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade


def _drifted_database(tmp_path: Path, *, retained_record: bool) -> tuple[str, dict[str, str]]:
    database_path = tmp_path / "legacy-initial-submission-drift.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0007_reconcile_adjudicated_admission_lineages")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE physical_model_initial_submissions "
                "(id VARCHAR(36) PRIMARY KEY, admission_record_id VARCHAR(36) NOT NULL)"
            )
        )
        if retained_record:
            connection.execute(
                text(
                    "INSERT INTO physical_model_initial_submissions "
                    "(id, admission_record_id) VALUES ('legacy-submission', 'legacy-admission')"
                )
            )
    return database_url, environment


def test_empty_stray_legacy_table_is_retired(tmp_path: Path) -> None:
    database_url, environment = _drifted_database(tmp_path, retained_record=False)

    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    assert "physical_model_initial_submissions" not in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0024_signed_physical_model_lock_replacement_admissions"
        )


def test_stray_legacy_table_with_records_fails_closed(tmp_path: Path) -> None:
    database_url, environment = _drifted_database(tmp_path, retained_record=True)

    result = _run_migration(
        database_url,
        environment,
        "upgrade",
        "head",
        expect_success=False,
    )

    assert result.returncode != 0
    assert "Refusing to retire physical_model_initial_submissions" in (
        result.stdout + result.stderr
    )
    engine = create_engine(database_url)
    assert "physical_model_initial_submissions" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT COUNT(*) FROM physical_model_initial_submissions")
            ).scalar_one()
            == 1
        )
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0007_reconcile_adjudicated_admission_lineages"
        )