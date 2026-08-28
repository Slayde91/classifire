from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoSuchModuleError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import Settings, get_settings


class Base(DeclarativeBase):
    pass


class DatabaseSetupError(RuntimeError):
    """A database setup refusal that exposes only a stable failure code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def create_database_engine(database_settings: Settings) -> Engine:
    """Build the configured engine without exposing driver or DSN error details."""

    engine_kwargs: dict[str, object] = {"pool_pre_ping": True, "future": True}
    if database_settings.database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    try:
        return create_engine(database_settings.database_url, **engine_kwargs)
    except (ImportError, NoSuchModuleError):
        raise DatabaseSetupError("DATABASE_DRIVER_UNAVAILABLE") from None
    except Exception:
        raise DatabaseSetupError("DATABASE_CONFIGURATION_INVALID") from None


settings = get_settings()
engine = create_database_engine(settings)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
