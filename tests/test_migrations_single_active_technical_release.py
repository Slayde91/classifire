from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade


def test_single_active_release_migration_upgrades_existing_0025_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "single-active-library-release.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(
        database_url,
        environment,
        "0025_signed_physical_model_lock_replacement_outcomes",
    )
    _upgrade(database_url, environment, "0026_single_active_technical_release")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    index = next(
        item
        for item in inspector.get_indexes("library_releases")
        if item["name"] == "uq_library_release_one_active_technical"
    )
    assert index["unique"] == 1
    assert index["column_names"] == ["library_type"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO library_releases "
                "(id, created_at, updated_at, record_version, library_type, version, status) "
                "VALUES ('one', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                "'technical', 'v1', 'active')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO library_releases "
                "(id, created_at, updated_at, record_version, library_type, version, status) "
                "VALUES ('old', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                "'technical', 'v0', 'superseded')"
            )
        )
        for release_id, version in (("pricing-one", "p1"), ("pricing-two", "p2")):
            connection.execute(
                text(
                    "INSERT INTO library_releases "
                    "(id, created_at, updated_at, record_version, library_type, version, status) "
                    "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                    "'pricing', :version, 'active')"
                ),
                {"id": release_id, "version": version},
            )
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM library_releases "
                "WHERE library_type = 'pricing' AND status = 'active'"
            )
        ).scalar_one() == 2
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO library_releases "
                    "(id, created_at, updated_at, record_version, library_type, version, status) "
                    "VALUES ('two', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                    "'technical', 'v2', 'active')"
                )
            )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0026_single_active_technical_release"
        )
    engine.dispose()


def test_single_active_release_migration_refuses_ambiguous_existing_state(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ambiguous-active-library-releases.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(
        database_url,
        environment,
        "0025_signed_physical_model_lock_replacement_outcomes",
    )
    engine = create_engine(database_url)
    with engine.begin() as connection:
        for release_id, version in (("one", "v1"), ("two", "v2")):
            connection.execute(
                text(
                    "INSERT INTO library_releases "
                    "(id, created_at, updated_at, record_version, library_type, version, status) "
                    "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                    "'technical', :version, 'active')"
                ),
                {"id": release_id, "version": version},
            )

    result = _run_migration(
        database_url,
        environment,
        "upgrade",
        "head",
        expect_success=False,
    )

    assert result.returncode != 0
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0025_signed_physical_model_lock_replacement_outcomes"
        )
        assert connection.execute(
            text(
                "SELECT COUNT(*) FROM library_releases "
                "WHERE library_type = 'technical' AND status = 'active'"
            )
        ).scalar_one() == 2
    engine.dispose()
