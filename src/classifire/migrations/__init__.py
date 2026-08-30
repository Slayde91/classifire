"""The versioned CLASSIFIRE database upgrade history and runtime entry point."""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from classifire.config import (
    ProductionConfigurationError,
    Settings,
    get_settings,
    require_production_configuration,
)

SCRIPT_LOCATION = "classifire:migrations"


class MigrationReadinessError(RuntimeError):
    """The configured database cannot prove it is at the packaged migration head."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def migration_config(settings: Settings) -> Config:
    """Build an Alembic configuration for the supplied, validated settings."""

    require_production_configuration(settings)
    config = Config()
    config.set_main_option("script_location", SCRIPT_LOCATION)
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def upgrade_to_head(settings: Settings) -> None:
    """Explicitly apply the packaged migration history through its current head."""

    command.upgrade(migration_config(settings), "head")


def require_current_migration_head(settings: Settings) -> None:
    """Fail closed unless the configured database is exactly at every packaged head."""

    config = migration_config(settings)
    expected_heads = frozenset(ScriptDirectory.from_config(config).get_heads())
    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as connection:
            actual_heads = frozenset(MigrationContext.configure(connection).get_current_heads())
    except SQLAlchemyError as exc:
        raise MigrationReadinessError("DATABASE_MIGRATION_UNAVAILABLE") from exc
    finally:
        engine.dispose()

    if actual_heads != expected_heads:
        raise MigrationReadinessError("DATABASE_MIGRATION_REQUIRED")


def main() -> None:
    """Run the explicit installed-package migration command."""

    try:
        upgrade_to_head(get_settings())
    except ProductionConfigurationError as exc:
        print(f"CLASSIFIRE migration refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print("Database migrated to the packaged head.")
