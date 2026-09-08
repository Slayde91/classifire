from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_report_locator_migration_upgrades_existing_0010_database(tmp_path: Path) -> None:
    database_path = tmp_path / 'report-evidence-locators.sqlite'
    database_url = f'sqlite:///{database_path.as_posix()}'
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, '0010_project_evidence_ownership')
    _upgrade(database_url, environment, 'head')

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {'report_evidence_locators', 'report_defect_scopes'}.issubset(
        inspector.get_table_names()
    )
    assert {
        'project_evidence_id',
        'source_sha256',
        'sequence',
        'locator_key',
        'item_kind',
        'page_number',
        'content_sha256',
        'locator_json',
    }.issubset({column['name'] for column in inspector.get_columns('report_evidence_locators')})
    assert {
        'project_evidence_id',
        'source_sha256',
        'defect_id',
        'report_defect_label',
        'start_locator_id',
        'end_locator_id',
    }.issubset({column['name'] for column in inspector.get_columns('report_defect_scopes')})
    locator_foreign_keys = inspector.get_foreign_keys('report_evidence_locators')
    assert any(
        foreign_key['constrained_columns'] == ['project_evidence_id', 'source_sha256']
        and foreign_key['referred_table'] == 'project_evidence'
        for foreign_key in locator_foreign_keys
    )
    scope_foreign_keys = inspector.get_foreign_keys('report_defect_scopes')
    assert any(
        foreign_key['constrained_columns'] == ['start_locator_id', 'project_evidence_id']
        and foreign_key['referred_table'] == 'report_evidence_locators'
        for foreign_key in scope_foreign_keys
    )
    assert any(
        foreign_key['constrained_columns'] == ['end_locator_id', 'project_evidence_id']
        and foreign_key['referred_table'] == 'report_evidence_locators'
        for foreign_key in scope_foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == (
            '0046_draft_pricing_quantity_bases'
        )
    engine.dispose()


def test_docx_locator_migration_admits_safe_document_paragraph_and_table_kinds(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / 'xlsx-report-evidence-locators.sqlite'
    database_url = f'sqlite:///{database_path.as_posix()}'
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, '0017_xlsx_report_evidence_locators')
    _upgrade(database_url, environment, 'head')

    engine = create_engine(database_url)
    inspector = inspect(engine)
    constraints = {
        constraint['name']: constraint['sqltext']
        for constraint in inspector.get_check_constraints('report_evidence_locators')
    }
    item_kind_constraint = constraints['ck_report_evidence_locator_item_kind']
    assert "'worksheet'" in item_kind_constraint
    assert "'cell'" in item_kind_constraint
    assert "'document'" in item_kind_constraint
    assert "'paragraph'" in item_kind_constraint
    assert "'document_table'" in item_kind_constraint
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == (
            '0046_draft_pricing_quantity_bases'
        )
    engine.dispose()
