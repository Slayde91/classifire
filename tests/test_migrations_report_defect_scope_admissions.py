from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_report_scope_admission_migration_upgrades_existing_0012_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / 'report-scope-admissions.sqlite'
    database_url = f'sqlite:///{database_path.as_posix()}'
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, '0012_report_expected_label_manifests')
    _upgrade(database_url, environment, 'head')

    engine = create_engine(database_url)
    inspector = inspect(engine)
    columns = {
        column['name']: column for column in inspector.get_columns('report_defect_scopes')
    }
    assert columns['approved_expected_label_manifest_id']['nullable'] is True
    foreign_keys = inspector.get_foreign_keys('report_defect_scopes')
    assert any(
        foreign_key['constrained_columns'] == ['approved_expected_label_manifest_id']
        and foreign_key['referred_table'] == 'report_expected_label_manifests'
        for foreign_key in foreign_keys
    )
    assert any(
        index['name'] == 'ix_report_defect_scope_expected_label_manifest_id'
        for index in inspector.get_indexes('report_defect_scopes')
    )
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == (
            '0034_draft_project_packages'
        )
    engine.dispose()