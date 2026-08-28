from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from importlib import resources
from pathlib import Path

import pytest

from classifire.services.deployment_lineage import CLEAN_STACK_HEAD
from classifire.services.readiness import discover_repository_migration_heads

ROOT = Path(__file__).resolve().parents[1]


def test_packaged_migration_resource_has_single_policy_head() -> None:
    migration_root = resources.files("classifire.migrations")

    assert migration_root.joinpath("env.py").is_file()
    assert migration_root.joinpath("versions", f"{CLEAN_STACK_HEAD}.py").is_file()
    assert discover_repository_migration_heads() == (CLEAN_STACK_HEAD,)


def test_built_wheel_discovers_its_own_migration_graph(tmp_path: Path) -> None:
    pytest.importorskip(
        "setuptools.build_meta",
        reason="wheel smoke test requires the declared setuptools build backend",
    )
    wheel_directory = tmp_path / "wheel"
    installed_directory = tmp_path / "installed"
    source_directory = tmp_path / "source"
    wheel_directory.mkdir()
    installed_directory.mkdir()
    source_directory.mkdir()
    shutil.copytree(
        ROOT / "src",
        source_directory / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copy2(ROOT / "pyproject.toml", source_directory / "pyproject.toml")
    shutil.copy2(ROOT / "README.md", source_directory / "README.md")
    build = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
            str(source_directory),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert build.returncode == 0, build.stderr
    wheels = list(wheel_directory.glob("classifire-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        archive.extractall(installed_directory)
        names = set(archive.namelist())
    assert "classifire/migrations/env.py" in names
    assert f"classifire/migrations/versions/{CLEAN_STACK_HEAD}.py" in names

    environment = os.environ.copy()
    environment.update(
        {
            "CLASSIFIRE_DATABASE_URL": (
                f"sqlite:///{(tmp_path / 'installed-migration.sqlite').as_posix()}"
            ),
            "CLASSIFIRE_ENV": "test",
            "CLASSIFIRE_STORAGE_ROOT": str(tmp_path / "runtime-storage"),
            "PYTHONPATH": str(installed_directory),
            "PYTHONPYCACHEPREFIX": str(tmp_path / "pycache"),
        }
    )
    smoke = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-c",
            (
                "from classifire.cli import migrate_database; migrate_database(); "
                "from classifire.services.readiness import "
                "discover_repository_migration_heads; "
                "print('HEADS=' + ','.join(discover_repository_migration_heads()))"
            ),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert smoke.returncode == 0, smoke.stderr
    assert f"HEADS={CLEAN_STACK_HEAD}" in smoke.stdout
    with sqlite3.connect(tmp_path / "installed-migration.sqlite") as database:
        assert database.execute("SELECT version_num FROM alembic_version").fetchone() == (
            CLEAN_STACK_HEAD,
        )
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "technical_document_relationships" in tables
