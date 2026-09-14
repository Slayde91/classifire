from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

import classifire.migrations as migrations
from classifire.config import Settings
from classifire.migrations import (
    MigrationReadinessError,
    require_current_migration_head,
    upgrade_to_head,
)


@pytest.fixture
def migrated_database(tmp_path: Path) -> Settings:
    database_url = f"sqlite:///{(tmp_path / 'lineage.sqlite').as_posix()}"
    settings = Settings(env="test", database_url=database_url)
    upgrade_to_head(settings)
    return settings


def _assert_read_only_check(settings: Settings, *, expected_error: str | None) -> None:
    database_path = Path(settings.database_url.removeprefix("sqlite:///"))
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    statements: list[str] = []

    def observe(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)
        prefix = statement.strip().upper()
        assert prefix.startswith("SELECT") or (
            prefix.startswith(("PRAGMA MAIN.TABLE_INFO", "PRAGMA TEMP.TABLE_INFO"))
            and "=" not in prefix
        ), f"Startup readiness attempted a non-read statement: {statement}"

    event.listen(Engine, "before_cursor_execute", observe)
    try:
        if expected_error is None:
            require_current_migration_head(settings)
        else:
            with pytest.raises(MigrationReadinessError) as raised:
                require_current_migration_head(settings)
            assert raised.value.code == expected_error
            assert str(raised.value) == expected_error
    finally:
        event.remove(Engine, "before_cursor_execute", observe)
    assert statements
    assert hashlib.sha256(database_path.read_bytes()).hexdigest() == before


def test_startup_accepts_migrated_schema_without_writes(migrated_database: Settings) -> None:
    _assert_read_only_check(migrated_database, expected_error=None)


@pytest.mark.parametrize(
    "table_name",
    [
        "draft_workspace_proposal_decisions",
        "draft_scope_docx_sources",
        "draft_project_packages",
        "physical_model_submission_receipts",
    ],
)
def test_startup_rejects_missing_required_table_at_current_head(
    migrated_database: Settings, table_name: str
) -> None:
    engine = create_engine(migrated_database.database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE "{table_name}"'))
    finally:
        engine.dispose()
    _assert_read_only_check(migrated_database, expected_error="DEPLOYMENT_SCHEMA_DRIFT")


def test_startup_rejects_retired_table_at_current_head(migrated_database: Settings) -> None:
    engine = create_engine(migrated_database.database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE physical_model_initial_submissions (id TEXT)"))
    finally:
        engine.dispose()
    _assert_read_only_check(migrated_database, expected_error="DEPLOYMENT_SCHEMA_DRIFT")


def test_startup_schema_inspection_failure_is_redacted(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(_db: object) -> None:
        raise OperationalError("synthetic query", {}, RuntimeError("synthetic-private-detail"))

    monkeypatch.setattr(migrations, "assess_deployment_lineage", unavailable)
    _assert_read_only_check(migrated_database, expected_error="DATABASE_MIGRATION_UNAVAILABLE")
