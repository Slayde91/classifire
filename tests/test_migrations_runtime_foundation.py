from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def test_fresh_database_upgrades_through_runtime_foundation(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh-runtime-foundation.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = os.environ.copy()
    environment.update(
        {
            "CLASSIFIRE_DATABASE_URL": database_url,
            "CLASSIFIRE_STORAGE_ROOT": str(tmp_path / "storage"),
            "PYTHONPATH": str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", ""),
        }
    )

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "upgrade", "head"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    engine = create_engine(database_url)
    assert {"alembic_version", "estimates", "openings", "services"}.issubset(
        inspect(engine).get_table_names()
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0002_estimate_release_pins"
        )
