from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from classifire import (
    models,  # noqa: F401
    physical_models,  # noqa: F401
)
from classifire.config import get_settings
from classifire.db import Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

if config.config_file_name is None:
    database_url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
else:
    database_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", database_url)
target_metadata = Base.metadata


def _set_sqlite_foreign_key_enforcement(connection: Connection, enabled: bool) -> None:
    connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")
    actual = bool(connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one())
    if actual != enabled:
        state = "enable" if enabled else "disable"
        raise RuntimeError(f"Unable to {state} SQLite foreign-key enforcement for migration")


def _verify_sqlite_foreign_keys(connection: Connection) -> None:
    """Fail closed if a SQLite batch migration left invalid references behind."""
    violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"SQLite foreign-key check failed after migration: {violations!r}")


if context.is_offline_mode():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        sqlite_foreign_keys = connection.dialect.name == "sqlite"
        if sqlite_foreign_keys:
            # SQLite batch mode recreates parent tables. Its foreign-key pragma
            # must be changed before Alembic starts the migration transaction.
            connection.commit()
            _set_sqlite_foreign_key_enforcement(connection, enabled=False)

        try:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()

            if sqlite_foreign_keys:
                connection.commit()
                _set_sqlite_foreign_key_enforcement(connection, enabled=True)
                _verify_sqlite_foreign_keys(connection)
        finally:
            if sqlite_foreign_keys:
                if connection.in_transaction():
                    connection.rollback()
                _set_sqlite_foreign_key_enforcement(connection, enabled=True)
