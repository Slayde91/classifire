from __future__ import annotations

from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

from classifire.config import Settings, get_settings
from classifire.migrations import (
    SCRIPT_LOCATION,
    MigrationReadinessError,
    require_current_migration_head,
    upgrade_to_head,
)
from classifire.migrations import main as migration_main

ROOT = Path(__file__).resolve().parents[1]


def test_source_alembic_configuration_uses_packaged_history() -> None:
    config = Config(str(ROOT / "alembic.ini"))

    assert config.get_main_option("script_location") == SCRIPT_LOCATION
    assert (
        ScriptDirectory.from_config(config).get_current_head()
        == "0018_docx_report_evidence_locators"
    )


def test_migration_command_upgrades_disposable_database_to_packaged_head(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "classifire.sqlite"
    monkeypatch.setenv("CLASSIFIRE_ENV", "test")
    monkeypatch.setenv("CLASSIFIRE_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    try:
        migration_main()
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0018_docx_report_evidence_locators"
        )


def test_migration_command_refuses_unsafe_production_before_creating_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "must-not-exist.sqlite"
    monkeypatch.setenv("CLASSIFIRE_ENV", "production")
    monkeypatch.setenv("CLASSIFIRE_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()

    try:
        with pytest.raises(SystemExit) as raised:
            migration_main()
    finally:
        get_settings.cache_clear()

    assert raised.value.code == 2
    assert "PostgreSQL is required for multi-user production deployment" in capsys.readouterr().err
    assert not database_path.exists()


def test_migration_readiness_requires_exact_packaged_head(tmp_path: Path) -> None:
    database_path = tmp_path / "readiness.sqlite"
    settings = Settings(
        env="test",
        database_url=f"sqlite:///{database_path.as_posix()}",
    )

    with pytest.raises(MigrationReadinessError, match="DATABASE_MIGRATION_REQUIRED"):
        require_current_migration_head(settings)

    upgrade_to_head(settings)

    require_current_migration_head(settings)
