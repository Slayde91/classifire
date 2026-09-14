from __future__ import annotations

from draft_migration_fixture import fixture, verify_current
from sqlalchemy import inspect
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_proposal_history_migration_preserves_history_and_refuses_downgrade(case, tmp_path):
    baseline = "0047_draft_scope_docx_sources"
    target = "0048_draft_workspace_proposals"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert set(inspect(engine).get_table_names()) - before == {"draft_workspace_proposals"}
    keys = inspect(engine).get_foreign_keys("draft_workspace_proposals")
    assert {k["referred_table"] for k in keys} == {"draft_scopes", "users"}
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained native proposal history cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
