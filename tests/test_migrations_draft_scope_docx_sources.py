from __future__ import annotations

from draft_migration_fixture import fixture, verify_current
from sqlalchemy import inspect
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_word_source_migration_preserves_history_and_refuses_downgrade(case, tmp_path):
    baseline = "0046_draft_pricing_quantity_bases"
    target = "0047_draft_scope_docx_sources"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert set(inspect(engine).get_table_names()) - before == {"draft_scope_docx_sources"}
    foreign_keys = inspect(engine).get_foreign_keys("draft_scope_docx_sources")
    assert any(
        key["constrained_columns"] == ["stored_file_id", "source_sha256", "source_size_bytes"]
        and key["referred_table"] == "stored_files"
        for key in foreign_keys
    )
    assert any(
        index["column_names"] == ["draft_scope_id"]
        for index in inspect(engine).get_indexes("draft_scope_docx_sources")
    )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft Scope DOCX sources cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
