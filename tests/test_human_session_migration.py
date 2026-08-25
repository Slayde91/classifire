from __future__ import annotations

import re
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from test_migrations_physical_foundation import _downgrade, _migration_environment, _upgrade

from classifire.models import User

_AUTH_GENERATION = re.compile(r"^[0-9a-f]{64}$")


def _insert_legacy_user(connection, *, user_id: str, email: str) -> None:  # type: ignore[no-untyped-def]
    connection.execute(
        text(
            "INSERT INTO users "
            "(id, created_at, updated_at, record_version, email, full_name, "
            "password_hash, role, is_active) "
            "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :email, "
            "'Migration user', 'not-a-real-password-hash', 'estimator', 1)"
        ),
        {"id": user_id, "email": email},
    )


def test_human_session_migration_backfills_distinct_generations_and_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "human-sessions.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0009_visual_validation_receipts")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        _insert_legacy_user(
            connection,
            user_id="10000000-0000-0000-0000-000000000001",
            email="first@example.test",
        )
        _insert_legacy_user(
            connection,
            user_id="10000000-0000-0000-0000-000000000002",
            email="second@example.test",
        )

    _upgrade(database_url, environment, "head")

    inspector = inspect(engine)
    assert "human_sessions" in inspector.get_table_names()
    user_columns = {column["name"]: column for column in inspector.get_columns("users")}
    assert not user_columns["auth_generation"]["nullable"]
    assert getattr(user_columns["auth_generation"]["type"], "length", None) == 64

    session_columns = {
        column["name"]: column for column in inspector.get_columns("human_sessions")
    }
    assert set(session_columns) == {
        "auth_generation",
        "created_at",
        "expires_at",
        "id",
        "record_version",
        "revoked_at",
        "revoked_reason",
        "token_hash",
        "token_hint",
        "updated_at",
        "user_id",
    }
    for column_name in (
        "auth_generation",
        "created_at",
        "expires_at",
        "id",
        "record_version",
        "token_hash",
        "token_hint",
        "updated_at",
        "user_id",
    ):
        assert not session_columns[column_name]["nullable"]
    assert session_columns["revoked_at"]["nullable"]
    assert session_columns["revoked_reason"]["nullable"]
    assert getattr(session_columns["token_hash"]["type"], "length", None) == 64
    assert getattr(session_columns["token_hint"]["type"], "length", None) == 12
    assert getattr(session_columns["auth_generation"]["type"], "length", None) == 64

    indexes = {index["name"]: index for index in inspector.get_indexes("human_sessions")}
    assert not indexes["ix_human_sessions_user_id"]["unique"]
    assert indexes["ix_human_sessions_token_hash"]["unique"]
    foreign_key = next(
        foreign_key
        for foreign_key in inspector.get_foreign_keys("human_sessions")
        if foreign_key["constrained_columns"] == ["user_id"]
    )
    assert foreign_key["referred_table"] == "users"
    assert foreign_key["referred_columns"] == ["id"]
    assert foreign_key["options"].get("ondelete") == "CASCADE"

    with engine.connect() as connection:
        generations = connection.execute(
            text("SELECT auth_generation FROM users ORDER BY id")
        ).scalars().all()
        assert len(generations) == 2
        assert len(set(generations)) == 2
        assert all(_AUTH_GENERATION.fullmatch(generation) for generation in generations)
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0010_human_sessions"
        )

    with Session(engine) as db:
        users = [
            User(
                email="third@example.test",
                full_name="Third user",
                password_hash="x" * 64,
                role="estimator",
            ),
            User(
                email="fourth@example.test",
                full_name="Fourth user",
                password_hash="x" * 64,
                role="estimator",
            ),
        ]
        db.add_all(users)
        db.flush()
        assert all(_AUTH_GENERATION.fullmatch(user.auth_generation) for user in users)
        assert users[0].auth_generation != users[1].auth_generation


def test_human_session_migration_downgrade_fails_closed(tmp_path: Path) -> None:
    database_path = tmp_path / "human-sessions-downgrade.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "head")

    rejected = _downgrade(
        database_url,
        environment,
        "0009_visual_validation_receipts",
        expect_success=False,
    )

    assert rejected.returncode != 0
    assert "Human-session revocation state cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "human_sessions" in inspector.get_table_names()
    assert "auth_generation" in {
        column["name"] for column in inspector.get_columns("users")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0010_human_sessions"
        )
