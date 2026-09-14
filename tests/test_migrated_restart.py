from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import typer
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from classifire import cli, main
from classifire.config import Settings
from classifire.migrations import (
    MigrationReadinessError,
    require_current_migration_head,
    upgrade_to_head,
)
from classifire.models import User

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_draft_scope_demo.py"
WRAPPER = """
import runpy,sys
import uvicorn
from sqlalchemy import MetaData,event
from sqlalchemy.engine import Engine
from fastapi.testclient import TestClient

def forbidden(*args,**kwargs):
    raise AssertionError('Restart attempted metadata creation')
MetaData.create_all=forbidden

def observe(conn,cursor,statement,parameters,context,executemany):
    sql=statement.strip().upper()
    assert sql.startswith('SELECT') or (sql.startswith('PRAGMA') and '=' not in sql), sql
event.listen(Engine,'before_cursor_execute',observe)

def serve(app,**kwargs):
    with TestClient(app,base_url='http://127.0.0.1:8820') as client:
        assert client.get('/login').status_code==200
    print('MIGRATED_RESTART_READ_ONLY')
uvicorn.run=serve
sys.argv=sys.argv[1:]
runpy.run_path(sys.argv[0],run_name='__main__')
"""


def snapshot(directory):
    return {
        str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in directory.rglob("*")
        if p.is_file()
    }


@pytest.fixture
def migrated_demo(tmp_path):
    directory = tmp_path / "migrated demo"
    directory.mkdir()
    (directory / "classifire-draft-scope-demo.json").write_text(
        json.dumps(
            {
                "kind": "synthetic-scope-demo-v1",
                "session_key": "synthetic-session-" + "x" * 32,
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        _env_file=None,
        env="test",
        require_migrated_database=True,
        database_url="sqlite:///" + (directory / "demo.sqlite3").as_posix(),
        storage_root=directory / "storage",
    )
    upgrade_to_head(settings)
    engine = create_engine(settings.database_url)
    with Session(engine) as db:
        db.add(
            User(
                email="scope-demo@example.test",
                full_name="Synthetic restart fixture",
                password_hash="synthetic-unusable-hash",  # noqa: S106 - deliberately unusable fixture hash
                role="administrator",
                is_active=True,
            )
        )
        db.commit()
    engine.dispose()
    return directory, settings


def run_demo(directory, *arguments):
    env = {
        k: v for k, v in os.environ.items() if not k.upper().startswith(("CLASSIFIRE_", "OPENAI_"))
    }
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(  # noqa: S603 - fixed synthetic local launcher test
        [
            sys.executable,
            "-c",
            WRAPPER,
            str(SCRIPT),
            "--data-dir",
            str(directory),
            "--require-current-migrations",
            *arguments,
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_migrated_demo_restarts_twice_without_bootstrap_or_data_writes(migrated_demo):
    directory, _ = migrated_demo
    before = snapshot(directory)
    for _ in range(2):
        result = run_demo(directory)
        assert result.returncode == 0, result.stderr
        assert "MIGRATED_RESTART_READ_ONLY" in result.stdout
        assert snapshot(directory) == before


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("head", "DATABASE_MIGRATION_REQUIRED"),
        ("table", "DEPLOYMENT_SCHEMA_DRIFT"),
        ("user", "requires an existing demo user"),
        ("database", "requires an existing database"),
    ],
)
def test_migrated_demo_refuses_before_writes(migrated_demo, change, error):
    directory, settings = migrated_demo
    if change == "database":
        (directory / "demo.sqlite3").unlink()
    else:
        engine = create_engine(settings.database_url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    {
                        "head": "DELETE FROM alembic_version",
                        "table": "DROP TABLE draft_workspace_proposal_decisions",
                        "user": "DELETE FROM users",
                    }[change]
                )
            )
        engine.dispose()
    before = snapshot(directory)
    result = run_demo(directory)
    assert result.returncode != 0
    assert error in result.stderr
    assert "MIGRATED_RESTART_READ_ONLY" not in result.stdout
    assert snapshot(directory) == before
    assert not settings.storage_root.exists()


@pytest.mark.parametrize(
    "argument",
    [
        "--prepare-external-client",
        "--client-demo",
        "--seed-technical-library",
        "--seed-constraint-library",
        "--seed-service-size-library",
        "--scripted-pdf-suggestions",
    ],
)
def test_migrated_restart_refuses_creation_modes(tmp_path, argument):
    directory = tmp_path / "marked"
    directory.mkdir()
    (directory / "classifire-draft-scope-demo.json").write_text("{}", encoding="utf-8")
    before = snapshot(directory)
    result = run_demo(directory, argument)
    assert result.returncode != 0
    assert "cannot create identities, policies or fixtures" in result.stderr
    assert snapshot(directory) == before


def test_migrated_restart_never_creates_unmarked_directory(tmp_path):
    directory = tmp_path / "absent"
    result = run_demo(directory)
    assert result.returncode != 0
    assert "existing marked demo directory" in result.stderr
    assert not directory.exists()


@pytest.mark.parametrize("env", ["test", "development"])
def test_migrated_web_startup_skips_bootstrap(migrated_demo, monkeypatch, env):
    directory, settings = migrated_demo
    monkeypatch.setattr(main, "settings", settings.model_copy(update={"env": env}))

    def forbidden(*args, **kwargs):
        pytest.fail("Migrated startup must not bootstrap")

    monkeypatch.setattr(main.Base.metadata, "create_all", forbidden)
    monkeypatch.setattr(main, "SessionLocal", forbidden)
    before = snapshot(directory)

    async def start():
        async with main.lifespan(main.app):
            pass

    asyncio.run(start())
    assert snapshot(directory) == before


def test_migrated_web_refuses_missing_sqlite_without_creating_file(tmp_path, monkeypatch):
    path = tmp_path / "absent.sqlite"
    settings = Settings(
        _env_file=None,
        env="test",
        require_migrated_database=True,
        database_url="sqlite:///" + path.as_posix(),
        storage_root=tmp_path / "storage",
    )
    monkeypatch.setattr(main, "settings", settings)

    async def start():
        async with main.lifespan(main.app):
            pass

    with pytest.raises(MigrationReadinessError, match="DATABASE_MIGRATION_REQUIRED"):
        asyncio.run(start())
    assert not path.exists()
    assert not settings.storage_root.exists()


def test_migrated_cli_refuses_seed_and_uses_real_readiness(migrated_demo, monkeypatch):
    directory, settings = migrated_demo
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    def forbidden(*args, **kwargs):
        pytest.fail("Migrated CLI must not bootstrap")

    monkeypatch.setattr(cli.Base.metadata, "create_all", forbidden)
    before = snapshot(directory)
    with pytest.raises(typer.BadParameter, match="MIGRATED_DATABASE_SEEDING_FORBIDDEN"):
        cli._prepare_cli_write(seeds_controlled_defaults=True)
    cli._ensure_cli_schema(settings)
    assert snapshot(directory) == before
    engine = create_engine(settings.database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE draft_workspace_proposal_decisions"))
    engine.dispose()
    before = snapshot(directory)
    with pytest.raises(typer.BadParameter, match="DEPLOYMENT_SCHEMA_DRIFT"):
        cli._ensure_cli_schema(settings)
    assert snapshot(directory) == before


def test_migration_inspection_refuses_memory_database_without_bootstrap():
    with pytest.raises(MigrationReadinessError, match="DATABASE_MIGRATION_REQUIRED"):
        require_current_migration_head(Settings(_env_file=None, database_url="sqlite:///:memory:"))
