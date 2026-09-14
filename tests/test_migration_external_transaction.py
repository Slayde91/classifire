"""Caller-owned PostgreSQL migration transactions preserve commit/rollback control."""
from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from test_migrations_postgresql_history import migration_postgresql as _migration_postgresql

from classifire.migrations import SCRIPT_LOCATION

migration_postgresql = _migration_postgresql
BASELINE = "0047_draft_scope_docx_sources"
HEAD = "0049_draft_proposal_decisions"


def _config(connection: object) -> Config:
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    # The caller's already-open connection must be the only destination. This
    # dummy URL is deliberately unusable; a second connection is always a defect.
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://invalid.invalid/unused")
    config.attributes["connection"] = connection
    return config


def _deny_new_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args, **kwargs):
        pytest.fail(
            "Migration opened a separate connection instead of using the caller transaction"
        )

    monkeypatch.setattr(sqlalchemy, "engine_from_config", fail)


def test_external_transaction_commits_only_when_caller_commits(
    migration_postgresql, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine, _ = migration_postgresql
    _deny_new_engine(monkeypatch)
    with engine.connect() as connection:
        transaction = connection.begin()
        connection.exec_driver_sql("CREATE TABLE activation_probe (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO activation_probe VALUES (1)")
        command.upgrade(_config(connection), "head")
        assert connection.in_transaction()
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert "draft_workspace_proposal_decisions" in inspect(connection).get_table_names()
        # An independent reader cannot see the transaction's schema or rows yet.
        assert inspect(engine).get_table_names() == []
        transaction.commit()
        assert not connection.closed
    with engine.connect() as reader:
        assert reader.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        assert reader.scalar(text("SELECT id FROM activation_probe")) == 1


@pytest.mark.parametrize("failure_point", ["during_migration", "after_migrations"])
def test_conversion_stamp_and_upgrades_roll_back_together(
    migration_postgresql, monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    _, engine, _ = migration_postgresql
    _deny_new_engine(monkeypatch)
    with engine.begin() as connection:
        command.upgrade(_config(connection), BASELINE)
        connection.exec_driver_sql(
            "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)"
        )
        connection.exec_driver_sql("CREATE TABLE activation_probe (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO activation_probe VALUES (1)")
    before_tables = inspect(engine).get_table_names()
    before_columns = inspect(engine).get_columns("users")
    original_create_table = Operations.create_table

    def fail_during_migration(self, name, *args, **kwargs):
        if name == "draft_workspace_proposal_decisions":
            assert "draft_workspace_proposals" in inspect(self.get_bind()).get_table_names()
            raise RuntimeError("injected migration failure")
        return original_create_table(self, name, *args, **kwargs)

    if failure_point == "during_migration":
        monkeypatch.setattr(Operations, "create_table", fail_during_migration)
    with (
        pytest.raises(RuntimeError, match="injected migration failure"),
        engine.begin() as connection,
    ):
        connection.exec_driver_sql("ALTER TABLE users ADD COLUMN activation_probe INTEGER")
        connection.exec_driver_sql("INSERT INTO activation_probe VALUES (2)")
        config = _config(connection)
        command.stamp(config, BASELINE)
        command.upgrade(config, "head")
        assert connection.in_transaction()
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD
        raise RuntimeError("injected migration failure")
    with engine.connect() as connection:
        assert inspect(connection).get_table_names() == before_tables
        assert [str(c) for c in inspect(connection).get_columns("users")] == [
            str(c) for c in before_columns
        ]
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == BASELINE
        assert str(inspect(connection).get_columns("alembic_version")[0]["type"]) == "VARCHAR(32)"
        assert connection.scalars(text("SELECT id FROM activation_probe ORDER BY id")).all() == [1]


@pytest.mark.parametrize("state", ["inactive", "offline", "closed", "invalidated"])
def test_external_postgresql_connection_requires_online_active_transaction(
    migration_postgresql, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    _, engine, _ = migration_postgresql
    _deny_new_engine(monkeypatch)
    with engine.connect() as connection:
        if state in {"offline", "invalidated"}:
            connection.begin()
        if state == "closed":
            connection.close()
        if state == "invalidated":
            connection.invalidate()
        active_before = connection.in_transaction()
        closed_before = connection.closed
        with pytest.raises(RuntimeError, match="active PostgreSQL transaction"):
            command.upgrade(_config(connection), "head", sql=state == "offline")
        assert connection.in_transaction() == active_before
        assert connection.closed == closed_before
        if active_before:
            connection.rollback()
    assert inspect(engine).get_table_names() == []


@pytest.mark.parametrize("state", ["wrong_type", "sqlite"])
def test_external_connection_refuses_unsupported_modes_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, state: str
) -> None:
    _deny_new_engine(monkeypatch)
    engine = create_engine("sqlite:///" + str(tmp_path / "unchanged.sqlite"))
    with engine.connect() as connection:
        config = _config("not a connection" if state == "wrong_type" else connection)
        with pytest.raises(RuntimeError, match="migration connection|PostgreSQL transaction"):
            command.upgrade(config, "head")
    assert inspect(engine).get_table_names() == []
    engine.dispose()
