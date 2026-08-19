from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_fresh_sqlite_database_migrates_to_head(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "fresh-classifire.db"
    env = os.environ.copy()
    env["CLASSIFIRE_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert revision == ("0006_adjudicated_canonical_admissions",)
    assert {
        "users",
        "projects",
        "estimates",
        "openings",
        "services",
        "agent_service_principals",
        "physical_model_admissions",
        "physical_model_initial_submissions",
        "physical_model_locks",
        "repair_strategy_locks",
        "pricing_components",
        "gate_evidence",
        "audit_trails",
    } <= tables
