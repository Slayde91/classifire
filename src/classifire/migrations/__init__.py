"""The versioned CLASSIFIRE database upgrade history and runtime entry point."""

from __future__ import annotations

import sys

from alembic import command
from alembic.config import Config

from classifire.config import (
    ProductionConfigurationError,
    Settings,
    get_settings,
    require_production_configuration,
)

SCRIPT_LOCATION = "classifire:migrations"


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


def main() -> None:
    """Run the explicit installed-package migration command."""

    try:
        upgrade_to_head(get_settings())
    except ProductionConfigurationError as exc:
        print(f"CLASSIFIRE migration refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print("Database migrated to the packaged head.")
