from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade

from classifire.db import Base
from classifire.services.schema_bootstrap import (
    SchemaBootstrapError,
    prepare_application_schema,
)


def _schema_snapshot(engine) -> tuple[tuple[object, ...], ...]:  # type: ignore[no-untyped-def]
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE sql IS NOT NULL ORDER BY type, name"
            )
        ).all()
    return tuple(tuple(row) for row in rows)


def _forbid_create_all(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_create_all(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("create_all must not be called for a non-empty database")

    monkeypatch.setattr(Base.metadata, "create_all", fail_create_all)


def test_development_creates_only_an_entirely_empty_database() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    result = prepare_application_schema(engine, "development")

    assert result.code == "EMPTY_LOCAL_SCHEMA_CREATED"
    assert result.schema_created is True
    tables = set(inspect(engine).get_table_names())
    assert "users" in tables
    assert "human_sessions" in tables
    assert "alembic_version" not in tables


def test_read_only_check_rejects_an_empty_local_database_without_ddl() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    with pytest.raises(SchemaBootstrapError) as rejected:
        prepare_application_schema(engine, "development", create_empty=False)

    assert rejected.value.code == "EMPTY_LOCAL_DATABASE"
    assert inspect(engine).get_table_names() == []


def test_current_unversioned_local_schema_is_reused_without_create_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    before = _schema_snapshot(engine)
    _forbid_create_all(monkeypatch)

    result = prepare_application_schema(engine, "test")

    assert result.code == "CURRENT_UNVERSIONED_SCHEMA_REUSED"
    assert result.schema_created is False
    assert _schema_snapshot(engine) == before


def test_stale_unversioned_local_schema_fails_without_create_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
    before = _schema_snapshot(engine)
    _forbid_create_all(monkeypatch)

    with pytest.raises(SchemaBootstrapError) as rejected:
        prepare_application_schema(engine, "development")

    assert rejected.value.code == "UNVERSIONED_SCHEMA_NOT_CURRENT"
    assert _schema_snapshot(engine) == before


def test_production_rejects_empty_and_unversioned_databases() -> None:
    empty_engine = create_engine("sqlite+pysqlite:///:memory:")
    with pytest.raises(SchemaBootstrapError) as empty_rejected:
        prepare_application_schema(empty_engine, "production")
    assert empty_rejected.value.code == "EMPTY_PRODUCTION_DATABASE"
    assert inspect(empty_engine).get_table_names() == []

    unversioned_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(unversioned_engine)
    before = _schema_snapshot(unversioned_engine)
    with pytest.raises(SchemaBootstrapError) as unversioned_rejected:
        prepare_application_schema(unversioned_engine, "production")
    assert unversioned_rejected.value.code == "ALEMBIC_VERSION_TABLE_MISSING"
    assert _schema_snapshot(unversioned_engine) == before


def test_0009_startup_rejection_is_read_only_and_0010_can_still_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database_path = tmp_path / "startup-0009.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0009_visual_validation_receipts")
    engine = create_engine(database_url)
    before = _schema_snapshot(engine)
    _forbid_create_all(monkeypatch)

    with pytest.raises(SchemaBootstrapError) as rejected:
        prepare_application_schema(engine, "development")

    assert rejected.value.code == "DATABASE_MIGRATION_REQUIRED"
    assert "0010_human_sessions" in str(rejected.value)
    assert _schema_snapshot(engine) == before

    engine.dispose()
    _upgrade(database_url, environment, "head")
    upgraded_engine = create_engine(database_url)
    result = prepare_application_schema(upgraded_engine, "production")
    assert result.code == "GOVERNED_SCHEMA_CONFIRMED"
    assert result.schema_created is False
    assert result.governed_lineage is True
