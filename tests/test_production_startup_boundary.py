from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from classifire import main
from classifire.config import (
    ProductionConfigurationError,
    Settings,
    require_production_configuration,
)
from classifire.migrations import MigrationReadinessError


def _safe_production_settings(tmp_path: Path) -> Settings:
    values: dict[str, object] = {
        "env": "production",
        "database_url": "postgresql+psycopg://classifire@127.0.0.1:5432/classifire",
        "secret_key": "production-session-" + "secret-0123456789",
        "admin_" + "password": "approved-administrator-" + "password",
        "session_https_only": True,
        "storage_root": tmp_path / "storage",
    }
    return Settings(**values)


def test_production_configuration_refuses_defaults_before_startup(tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    settings = Settings(env="production", storage_root=storage_root)

    assert not storage_root.exists()

    with pytest.raises(ProductionConfigurationError) as raised:
        require_production_configuration(settings)

    assert any("SECRET_KEY" in finding for finding in raised.value.findings)
    assert any("administrator password" in finding for finding in raised.value.findings)
    assert any("HTTPS" in finding for finding in raised.value.findings)
    assert any("PostgreSQL is required" in finding for finding in raised.value.findings)
    assert not storage_root.exists()


def test_production_configuration_refuses_any_non_postgresql_database(
    tmp_path: Path,
) -> None:
    settings = _safe_production_settings(tmp_path).model_copy(
        update={"database_url": "mysql+pymysql://classifire@127.0.0.1/classifire"}
    )

    with pytest.raises(ProductionConfigurationError) as raised:
        require_production_configuration(settings)

    assert raised.value.findings == (
        "PostgreSQL is required for multi-user production deployment",
    )


def test_production_lifespan_never_creates_schema_or_seeds_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _safe_production_settings(tmp_path)
    assert not settings.storage_root.exists()
    monkeypatch.setattr(main, "settings", settings)

    def unexpected_write(*_args: object, **_kwargs: object) -> None:
        pytest.fail("production startup must not create schema or seed data")

    monkeypatch.setattr(main.Base.metadata, "create_all", unexpected_write)
    monkeypatch.setattr(main, "SessionLocal", unexpected_write)
    monkeypatch.setattr(main, "require_current_migration_head", lambda _settings: None)

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            pass

    asyncio.run(run_lifespan())
    assert settings.storage_root.is_dir()


def test_production_lifespan_refuses_unmigrated_database_before_storage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = _safe_production_settings(tmp_path)
    monkeypatch.setattr(main, "settings", settings)

    def missing_head(_settings: Settings) -> None:
        raise MigrationReadinessError("DATABASE_MIGRATION_REQUIRED")

    monkeypatch.setattr(main, "require_current_migration_head", missing_head)

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            pass

    with pytest.raises(MigrationReadinessError, match="DATABASE_MIGRATION_REQUIRED"):
        asyncio.run(run_lifespan())

    assert not settings.storage_root.exists()


def test_unsafe_production_lifespan_does_not_create_storage_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "storage"
    settings = Settings(env="production", storage_root=storage_root)
    monkeypatch.setattr(main, "settings", settings)

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            pass

    with pytest.raises(ProductionConfigurationError):
        asyncio.run(run_lifespan())

    assert not storage_root.exists()
