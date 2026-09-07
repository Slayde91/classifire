from __future__ import annotations

from datetime import UTC, datetime

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import MetaData, Table, inspect
from sqlalchemy.exc import IntegrityError
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_scope import uid
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_roster_migration_preserves_state_and_enforces_revision(case, tmp_path):
    baseline = "0043_draft_pricing_system_mappings"
    target = "0044_draft_pricing_evaluation_rosters"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert set(inspect(engine).get_table_names()) - before == {
        "draft_pricing_evaluation_rosters"
    }
    table = Table("draft_pricing_evaluation_rosters", MetaData(), autoload_with=engine)
    now = datetime.now(UTC)
    base = {
        "created_at": now,
        "updated_at": now,
        "record_version": 1,
        "draft_scope_id": ids["draft"],
        "revision": 1,
        "manifest_id": "manifest-t13",
        "parent_manifest_sha256": None,
        "mapping_inventory_sha256": "a" * 64,
        "manifest_sha256": "b" * 64,
        "feature_cutoff_at": now,
        "roster_json": "{}",
        "roster_sha256": "c" * 64,
        "created_by_id": uid(100),
    }
    with engine.begin() as connection:
        connection.execute(table.insert().values(id="roster-one", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(table.insert().values(id="roster-duplicate", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            table.insert().values(
                id="roster-zero",
                **{**base, "revision": 0},
            )
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing evaluation rosters cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
