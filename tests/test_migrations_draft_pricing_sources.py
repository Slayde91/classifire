from __future__ import annotations

import pytest
from draft_migration_fixture import fixture, seed, verify_current
from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.exc import IntegrityError
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_historical_draft_pricing_sources_upgrade_preserves_bytes_and_constraints(case, tmp_path):
    baseline = "0032_draft_pdf_sources"
    target = "0033_draft_pricing_sources"
    url, environment, engine, source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    # The retained native data is present in the real historical schema before upgrade.
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert set(["draft_pricing_sources"]) <= set(inspect(engine).get_table_names()) - before
    seed(source, engine, tables=set(["draft_pricing_sources"]))
    table = Table("draft_pricing_sources", MetaData(), autoload_with=engine)
    for changes in [
        {"source_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"}
    ]:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(
                table.update().where(table.c.id == ids["draft_pricing_sources"]).values(**changes)
            )
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(table).where(table.c.id == ids["draft_pricing_sources"])
            ).first()
            is not None
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing XLSX sources cannot be downgraded" in refusal.stderr
    # Only current-head application code is used to read these historical records.
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    missing = (
        set(inspect(engine).get_table_names())
        - before
        - set(["draft_pricing_sources"])
        - {"alembic_version", "draft_package_imports", "draft_imported_report_sources"}
    )
    seed(source, engine, tables=missing)
    verify_current(engine, ids, expected)
    engine.dispose()
