from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.ddl.postgresql import PostgresqlImpl
from sqlalchemy import Index, String, Table, Text, engine_from_config, inspect, pool
from sqlalchemy.engine import Connection
from sqlalchemy.schema import conv

from classifire import (
    models,  # noqa: F401
    physical_models,  # noqa: F401
)
from classifire.config import get_settings
from classifire.db import Base


class ClassifirePostgresqlImpl(PostgresqlImpl):
    """Use Alembic's dialect hook without renaming historical revision IDs."""

    __dialect__ = "postgresql"

    def version_table_impl(self, **kw: Any) -> Table:
        table = super().version_table_impl(**kw)
        table.c.version_num.type = Text()
        return table

    def create_index(self, index: Index, **kw: Any) -> None:
        # Historical explicit names must match the deterministic truncation
        # SQLAlchemy already uses for the same indexes in ORM-created schemas.
        if index.name is not None and len(index.name) > self.dialect.max_identifier_length:
            index.name = conv(index.name)
        super().create_index(index, **kw)

    def drop_index(self, index: Index, **kw: Any) -> None:
        if index.name is not None and len(index.name) > self.dialect.max_identifier_length:
            index.name = conv(index.name)
        super().drop_index(index, **kw)


def _has_migration_destination() -> bool:
    """Inspection commands such as ``current`` must never prepare schema."""
    try:
        context.get_revision_argument()
    except KeyError:
        return False
    return True


def _prepare_postgresql_version_table(connection: Connection) -> None:
    """Widen an existing bounded version field inside the migration transaction."""
    inspector = inspect(connection)
    if not inspector.has_table("alembic_version"):
        return
    column = next(
        column
        for column in inspector.get_columns("alembic_version")
        if column["name"] == "version_num"
    )
    if isinstance(column["type"], String) and column["type"].length is not None:
        connection.exec_driver_sql("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE TEXT")


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
                if connection.dialect.name == "postgresql" and _has_migration_destination():
                    _prepare_postgresql_version_table(connection)
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
