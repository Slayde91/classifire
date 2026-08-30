from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

ROOT = Path(__file__).resolve().parents[1]


def _upgrade(database_url: str, environment: dict[str, str], revision: str) -> None:
    result = subprocess.run(  # noqa: S603
        [
            sys.executable,
            '-m',
            'alembic',
            '-c',
            str(ROOT / 'alembic.ini'),
            'upgrade',
            revision,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_project_evidence_migration_upgrades_existing_0009_database(tmp_path: Path) -> None:
    database_path = tmp_path / 'project-evidence-ownership.sqlite'
    database_url = f'sqlite:///{database_path.as_posix()}'
    environment = os.environ.copy()
    environment.update(
        {
            'CLASSIFIRE_DATABASE_URL': database_url,
            'CLASSIFIRE_STORAGE_ROOT': str(tmp_path / 'storage'),
            'PYTHONPATH': str(ROOT / 'src') + os.pathsep + environment.get('PYTHONPATH', ''),
        }
    )

    _upgrade(database_url, environment, '0009_visual_validation_receipts')
    _upgrade(database_url, environment, '0010_project_evidence_ownership')

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert 'project_evidence' in inspector.get_table_names()
    assert {
        'id',
        'project_id',
        'estimate_id',
        'stored_file_id',
        'source_sha256',
        'source_size_bytes',
    }.issubset({column['name'] for column in inspector.get_columns('project_evidence')})
    assert {
        'ix_project_evidence_project_id',
        'ix_project_evidence_estimate_id',
    }.issubset({index['name'] for index in inspector.get_indexes('project_evidence')})
    assert any(
        foreign_key['constrained_columns']
        == ['stored_file_id', 'source_sha256', 'source_size_bytes']
        and foreign_key['referred_table'] == 'stored_files'
        for foreign_key in inspector.get_foreign_keys('project_evidence')
    )
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == (
            '0010_project_evidence_ownership'
        )
    engine.dispose()
