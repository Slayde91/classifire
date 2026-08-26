from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade

from classifire.db import Base
from classifire.services.deployment_lineage import CLEAN_STACK_HEAD
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


@pytest.mark.parametrize(
    "starting_revision",
    (
        "0008_retire_legacy_initial_submissions",
        "0009_visual_validation_receipts",
        "0010_human_sessions",
    ),
    ids=("retired-legacy-table", "visual-validation-receipts", "human-sessions"),
)
def test_known_stale_startup_rejection_is_read_only_and_can_still_upgrade(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    starting_revision: str,
) -> None:
    database_path = tmp_path / f"startup-{starting_revision}.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, starting_revision)
    engine = create_engine(database_url)
    before = _schema_snapshot(engine)
    _forbid_create_all(monkeypatch)

    with pytest.raises(SchemaBootstrapError) as rejected:
        prepare_application_schema(engine, "development")

    assert rejected.value.code == "DATABASE_MIGRATION_REQUIRED"
    assert CLEAN_STACK_HEAD in str(rejected.value)
    assert _schema_snapshot(engine) == before

    engine.dispose()
    _upgrade(database_url, environment, "head")
    upgraded_engine = create_engine(database_url)
    result = prepare_application_schema(upgraded_engine, "production")
    assert result.code == "GOVERNED_SCHEMA_CONFIRMED"
    assert result.schema_created is False
    assert result.governed_lineage is True


@pytest.mark.parametrize(
    ("corruption_sql", "expected_detail"),
    [
        ("DROP TABLE customers", "missing tables ('customers',)"),
        (
            "DROP TABLE malware_scan_attestations",
            "missing tables ('malware_scan_attestations',)",
        ),
        (
            "ALTER TABLE customers DROP COLUMN legal_name",
            "missing columns ('customers.legal_name',)",
        ),
        (
            "ALTER TABLE alembic_version RENAME COLUMN version_num TO wrong_name",
            "schema violations ('alembic_version:column_contract_required',)",
        ),
    ],
    ids=(
        "missing-table",
        "missing-malware-attestation-table",
        "missing-column",
        "malformed-alembic-version",
    ),
)
def test_current_head_rejects_incomplete_mapped_schema_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption_sql: str,
    expected_detail: str,
) -> None:
    database_path = tmp_path / "incomplete-current-head.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "head")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text(corruption_sql))
    before = _schema_snapshot(engine)
    _forbid_create_all(monkeypatch)

    with pytest.raises(SchemaBootstrapError) as rejected:
        prepare_application_schema(engine, "production")

    expected_code = (
        "DEPLOYMENT_LINEAGE_UNRECOGNISED"
        if "alembic_version" in corruption_sql
        else "DEPLOYMENT_SCHEMA_DRIFT"
    )
    assert rejected.value.code == expected_code
    assert expected_detail in str(rejected.value)
    assert _schema_snapshot(engine) == before
