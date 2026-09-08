from __future__ import annotations

from draft_migration_fixture import fixture, verify_current
from sqlalchemy import inspect
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_quantity_basis_migration_preserves_state_and_refuses_downgrade(case, tmp_path):
    baseline = "0045_draft_pricing_recipe_links"
    target = "0046_draft_pricing_quantity_bases"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert set(inspect(engine).get_table_names()) - before == {"draft_pricing_quantity_bases"}
    columns = {
        column["name"] for column in inspect(engine).get_columns("draft_pricing_quantity_bases")
    }
    assert {
        "draft_scope_id",
        "scope_revision",
        "scope_sha256",
        "scope_service_id",
        "technical_release_id",
        "recipe_link_id",
        "requirement_id",
        "quantity",
        "unit",
        "definition_sha256",
        "basis_json",
        "basis_sha256",
    } <= columns
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing quantity bases cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
