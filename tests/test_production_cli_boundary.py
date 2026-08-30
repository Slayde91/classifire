from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from classifire import cli
from classifire.config import Settings
from classifire.migrations import MigrationReadinessError


def _safe_production_settings(tmp_path: Path) -> Settings:
    return Settings(
        env="production",
        database_url="postgresql+psycopg://classifire@127.0.0.1:5432/classifire",
        secret_key="production-session-" + "secret-0123456789",
        admin_password="approved-administrator-" + "password",
        session_https_only=True,
        trusted_hosts=["app.example.test"],
        allowed_origins=["https://app.example.test"],
        storage_root=tmp_path / "storage",
    )


@pytest.mark.parametrize(
    "action",
    [
        lambda: cli.init_database(),
        lambda: cli.create_admin("admin@example.test", "Administrator", "safe-password"),
        lambda: cli.import_pricing(Path("not-read.csv")),
        lambda: cli.import_technical(Path("not-read.jsonl")),
        lambda: cli.import_supplied_v213(),
        lambda: cli.register_adjudicated_admission(
            Path("not-read-manifest.json"),
            Path("not-read-preflight.json"),
            "operator-reference",
        ),
    ],
)
def test_unsafe_production_cli_writes_fail_before_schema_or_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: Callable[[], None],
) -> None:
    settings = Settings(env="production", storage_root=tmp_path / "storage")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def unexpected_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unsafe production CLI command must not create schema or seed data")

    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected_write)
    monkeypatch.setattr(cli, "seed_database", unexpected_write)

    with pytest.raises(typer.BadParameter, match="Unsafe production configuration"):
        action()

    assert not settings.storage_root.exists()


@pytest.mark.parametrize(
    "action",
    [
        lambda: cli.init_database(),
        lambda: cli.import_pricing(Path("not-read.csv")),
        lambda: cli.import_technical(Path("not-read.jsonl")),
        lambda: cli.import_supplied_v213(),
    ],
)
def test_safe_production_seed_commands_are_forbidden_before_schema_or_seed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: Callable[[], None],
) -> None:
    settings = _safe_production_settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def unexpected_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("production seed command must not create schema or seed data")

    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected_write)
    monkeypatch.setattr(cli, "seed_database", unexpected_write)

    with pytest.raises(typer.BadParameter, match="PRODUCTION_SEEDING_FORBIDDEN"):
        action()


def test_safe_production_create_admin_never_creates_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "get_settings", lambda: _safe_production_settings(tmp_path))

    def unexpected_schema_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("production create-admin must not create schema")

    def unavailable_session() -> None:
        raise RuntimeError("schema must be migrated before administrator creation")

    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected_schema_write)
    monkeypatch.setattr(cli, "SessionLocal", unavailable_session)
    monkeypatch.setattr(cli, "require_current_migration_head", lambda _settings: None)

    with pytest.raises(RuntimeError, match="schema must be migrated"):
        cli.create_admin("admin@example.test", "Administrator", "safe-password")


@pytest.mark.parametrize(
    "action",
    [
        lambda: cli.create_admin("admin@example.test", "Administrator", "safe-password"),
        lambda: cli.worker(),
        lambda: cli.register_adjudicated_admission(
            Path("not-read-manifest.json"),
            Path("not-read-preflight.json"),
            "operator-reference",
        ),
    ],
)
def test_safe_production_database_commands_refuse_unmigrated_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    action: Callable[[], None],
) -> None:
    settings = _safe_production_settings(tmp_path)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def missing_head(_settings: Settings) -> None:
        raise MigrationReadinessError("DATABASE_MIGRATION_REQUIRED")

    def unexpected_schema_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("production create-admin must not create schema")

    monkeypatch.setattr(cli, "require_current_migration_head", missing_head)
    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected_schema_write)

    with pytest.raises(typer.BadParameter, match="DATABASE_MIGRATION_REQUIRED"):
        action()


def test_unsafe_production_init_command_reports_refusal_before_schema_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = Settings(env="production", storage_root=tmp_path / "storage")
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def unexpected_schema_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("unsafe production init must not create schema")

    monkeypatch.setattr(cli.Base.metadata, "create_all", unexpected_schema_write)

    result = CliRunner().invoke(cli.app, ["init"])

    assert result.exit_code != 0
    assert "Unsafe production configuration" in result.output
    assert not settings.storage_root.exists()
