from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote_plus

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from test_migrations_physical_foundation import _migration_environment, _upgrade
from typer.testing import CliRunner

from classifire.cli import _database_identity, _require_closed_sqlite_state
from classifire.cli import app as cli_app
from classifire.db import Base
from classifire.services.schema_bootstrap import SchemaBootstrapError


def _schema_snapshot(engine: Engine) -> tuple[tuple[object, ...], ...]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE sql IS NOT NULL ORDER BY type, name"
            )
        ).all()
    return tuple(tuple(row) for row in rows)


def _use_database(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    *,
    environment: str = "development",
    display_database_url: str = "sqlite:///doctor-test.sqlite",
) -> None:
    monkeypatch.setattr("classifire.cli.engine", engine)
    monkeypatch.setattr(
        "classifire.cli.get_settings",
        lambda: SimpleNamespace(
            env=environment,
            database_url=display_database_url,
            production_findings=lambda: (),
        ),
    )


def test_doctor_rejects_0009_without_mutating_the_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "doctor-0009.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0009_visual_validation_receipts")
    engine = create_engine(database_url)
    before = _schema_snapshot(engine)
    _use_database(monkeypatch, engine)

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "DATABASE_MIGRATION_REQUIRED" in result.output
    assert _schema_snapshot(engine) == before
    engine.dispose()


def test_doctor_rejects_stale_unversioned_schema_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
    before = _schema_snapshot(engine)
    _use_database(monkeypatch, engine)

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "UNVERSIONED_SCHEMA_NOT_CURRENT" in result.output
    assert _schema_snapshot(engine) == before
    engine.dispose()


def test_doctor_rejects_empty_local_database_without_creating_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    _use_database(monkeypatch, engine)

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "EMPTY_LOCAL_DATABASE" in result.output
    assert _schema_snapshot(engine) == ()
    engine.dispose()


def test_doctor_reports_current_governed_schema_ready_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "doctor-current.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "head")
    engine = create_engine(database_url)
    before = _schema_snapshot(engine)
    _use_database(monkeypatch, engine, environment="production")

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "GOVERNED_SCHEMA_CONFIRMED" in result.output
    assert "active_administrator_required" in result.output
    assert _schema_snapshot(engine) == before
    engine.dispose()


def test_doctor_reports_current_unversioned_local_schema_ready_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    before = _schema_snapshot(engine)
    _use_database(monkeypatch, engine, environment="test")

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "CURRENT_UNVERSIONED_SCHEMA_REUSED" in result.output
    assert _schema_snapshot(engine) == before
    engine.dispose()


def test_doctor_does_not_connect_the_application_engine_or_mutate_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "doctor-read-only.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    setup_engine = create_engine(database_url)
    with setup_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar_one() == "wal"
        connection.commit()
    Base.metadata.create_all(setup_engine)
    with setup_engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    setup_engine.dispose()
    before_bytes = database_path.read_bytes()
    assert before_bytes[18:20] == b"\x02\x02"
    before_modified = database_path.stat().st_mtime_ns
    sidecars = [
        Path(f"{database_path}-journal"),
        Path(f"{database_path}-shm"),
        Path(f"{database_path}-wal"),
    ]
    assert not any(path.exists() for path in sidecars)

    application_engine = create_engine(database_url)
    application_connections = 0

    @event.listens_for(application_engine, "connect")
    def application_wal_listener(
        dbapi_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        nonlocal application_connections
        application_connections += 1
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    real_sqlite_connect = sqlite3.connect
    diagnostic_connections: list[tuple[str, bool, bool]] = []

    def tracking_sqlite_connect(
        database: str,
        *,
        uri: bool = False,
        check_same_thread: bool = True,
    ) -> sqlite3.Connection:
        diagnostic_connections.append((database, uri, check_same_thread))
        return real_sqlite_connect(
            database,
            uri=uri,
            check_same_thread=check_same_thread,
        )

    monkeypatch.setattr("classifire.cli.sqlite3.connect", tracking_sqlite_connect)
    _use_database(monkeypatch, application_engine)

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "CURRENT_UNVERSIONED_SCHEMA_REUSED" in result.output
    assert application_connections == 0
    assert database_path.read_bytes() == before_bytes
    assert database_path.stat().st_mtime_ns == before_modified
    assert not any(path.exists() for path in sidecars)
    assert diagnostic_connections
    assert diagnostic_connections == [
        (
            f"{database_path.resolve().as_uri()}?mode=ro&immutable=1",
            True,
            False,
        )
    ] * len(diagnostic_connections)
    application_engine.dispose()
    assert database_path.read_bytes()[18:20] == b"\x02\x02"


@pytest.mark.parametrize(
    ("sidecar_suffix", "sidecar_bytes"),
    [
        ("-wal", b"retained-wal-evidence"),
        ("-shm", b""),
        ("-journal", b"retained-journal-evidence"),
    ],
)
def test_doctor_fails_closed_when_a_sqlite_sidecar_is_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sidecar_suffix: str,
    sidecar_bytes: bytes,
) -> None:
    database_path = tmp_path / "doctor-sidecar.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    setup_engine = create_engine(database_url)
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()
    sidecar_path = Path(f"{database_path}{sidecar_suffix}")
    sidecar_path.write_bytes(sidecar_bytes)
    before_database = database_path.read_bytes()
    before_database_modified = database_path.stat().st_mtime_ns
    before_sidecar = sidecar_path.read_bytes()
    before_sidecar_modified = sidecar_path.stat().st_mtime_ns

    application_engine = create_engine(database_url)
    application_connections = 0

    @event.listens_for(application_engine, "connect")
    def application_wal_listener(
        dbapi_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        nonlocal application_connections
        application_connections += 1
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    _use_database(monkeypatch, application_engine)

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "SQLITE_DIAGNOSTIC_SIDECAR_PRESENT" in result.output
    assert application_connections == 0
    assert database_path.read_bytes() == before_database
    assert database_path.stat().st_mtime_ns == before_database_modified
    assert sidecar_path.read_bytes() == before_sidecar
    assert sidecar_path.stat().st_mtime_ns == before_sidecar_modified
    for suffix in ("-journal", "-shm", "-wal"):
        if suffix != sidecar_suffix:
            assert not Path(f"{database_path}{suffix}").exists()
    application_engine.dispose()


def test_doctor_rejects_active_uncheckpointed_wal_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "doctor-active-wal.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    writer = sqlite3.connect(database_path)
    try:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone() == ("wal",)
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE retained (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO retained (value) VALUES ('committed-in-wal')")
        writer.commit()
        wal_path = Path(f"{database_path}-wal")
        shm_path = Path(f"{database_path}-shm")
        assert wal_path.stat().st_size > 0
        assert shm_path.stat().st_size > 0
        before = {
            path: (path.read_bytes(), path.stat().st_mtime_ns)
            for path in (database_path, wal_path, shm_path)
        }

        application_engine = create_engine(database_url)
        application_connections = 0
        diagnostic_connections = 0

        @event.listens_for(application_engine, "connect")
        def application_wal_listener(
            dbapi_connection: sqlite3.Connection,
            _connection_record: object,
        ) -> None:
            nonlocal application_connections
            application_connections += 1
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

        real_sqlite_connect = sqlite3.connect

        def tracking_sqlite_connect(
            database: str,
            *,
            uri: bool = False,
            check_same_thread: bool = True,
        ) -> sqlite3.Connection:
            nonlocal diagnostic_connections
            diagnostic_connections += 1
            return real_sqlite_connect(
                database,
                uri=uri,
                check_same_thread=check_same_thread,
            )

        monkeypatch.setattr("classifire.cli.sqlite3.connect", tracking_sqlite_connect)
        _use_database(monkeypatch, application_engine)

        result = CliRunner().invoke(cli_app, ["doctor"])

        assert result.exit_code == 1, result.output
        assert "SQLITE_DIAGNOSTIC_SIDECAR_PRESENT" in result.output
        assert application_connections == 0
        assert diagnostic_connections == 0
        for path, (contents, modified) in before.items():
            assert path.read_bytes() == contents
            assert path.stat().st_mtime_ns == modified
        application_engine.dispose()
    finally:
        writer.close()


def test_doctor_fails_closed_when_sidecar_inspection_is_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "doctor-sidecar-permission.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    setup_engine = create_engine(database_url)
    Base.metadata.create_all(setup_engine)
    setup_engine.dispose()
    before_database = database_path.read_bytes()
    before_modified = database_path.stat().st_mtime_ns

    application_engine = create_engine(database_url)
    application_connections = 0

    @event.listens_for(application_engine, "connect")
    def application_wal_listener(
        dbapi_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        nonlocal application_connections
        application_connections += 1
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    real_lstat = Path.lstat

    def guarded_lstat(path: Path) -> object:
        if str(path).endswith("-journal"):
            raise PermissionError("sidecar inspection denied")
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", guarded_lstat)
    _use_database(monkeypatch, application_engine)

    with pytest.raises(SchemaBootstrapError) as rejected:
        _require_closed_sqlite_state(database_path)
    assert rejected.value.code == "SQLITE_DIAGNOSTIC_SIDECAR_INSPECTION_FAILED"

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "sidecar inspection denied" not in result.output
    assert application_connections == 0
    assert database_path.read_bytes() == before_database
    assert database_path.stat().st_mtime_ns == before_modified
    application_engine.dispose()


def test_doctor_omits_mssql_odbc_connect_query_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    odbc_payload = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        "SERVER=tcp:secret-db.example.test,1433;"
        "UID=odbc-secret-user;PWD=odbc-secret-password;Encrypt=yes"
    )
    credential_url = f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_payload)}"
    assert _database_identity(credential_url) == "mssql+pyodbc database"
    _use_database(
        monkeypatch,
        engine,
        display_database_url=credential_url,
    )

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 0, result.output
    assert "CURRENT_UNVERSIONED_SCHEMA_REUSED" in result.output
    assert "mssql+pyodbc database" in result.output
    for secret in (
        "odbc_connect",
        "ODBC Driver",
        "secret-db.example.test",
        "odbc-secret-user",
        "odbc-secret-password",
    ):
        assert secret not in result.output
    engine.dispose()


def test_doctor_omits_userinfo_and_unknown_query_secret_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
    credential_url = (
        "postgresql://unknown-secret-user:unknown-secret-password@"
        "database.example.test/classifire?not_a_known_key=unknown-query-secret"
    )
    assert _database_identity(credential_url) == "postgresql database"
    _use_database(
        monkeypatch,
        engine,
        display_database_url=credential_url,
    )

    result = CliRunner().invoke(cli_app, ["doctor"])

    assert result.exit_code == 1, result.output
    assert "UNVERSIONED_SCHEMA_NOT_CURRENT" in result.output
    assert "postgresql database" in result.output
    for secret in (
        "unknown-secret-user",
        "unknown-secret-password",
        "not_a_known_key",
        "unknown-query-secret",
    ):
        assert secret not in result.output
    engine.dispose()
