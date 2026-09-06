from __future__ import annotations

from datetime import UTC, datetime

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.exc import IntegrityError
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

base_case = _base_case
case = _case


def test_profile_decision_migration_preserves_profiles_and_enforces_one_decision(case, tmp_path):
    baseline = "0040_draft_pricing_source_profiles"
    target = "0041_draft_pricing_profile_decisions"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    profiles = Table("draft_pricing_source_profiles", MetaData(), autoload_with=engine)
    sources = Table("draft_pricing_sources", MetaData(), autoload_with=engine)
    with engine.begin() as connection:
        source = connection.execute(
            select(sources).where(sources.c.id == ids["draft_pricing_sources"])
        ).mappings().one()
        connection.execute(
            profiles.insert().values(
                id="profile-1",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                record_version=1,
                draft_scope_id=source["draft_scope_id"],
                source_id=source["id"],
                revision=1,
                parent_profile_sha256=None,
                profile_json="{}",
                profile_sha256="a" * 64,
                created_by_id=source["created_by_id"],
            )
        )
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    added = set(inspect(engine).get_table_names()) - before
    assert "draft_pricing_source_profile_decisions" in added
    decisions = Table(
        "draft_pricing_source_profile_decisions", MetaData(), autoload_with=engine
    )
    now = datetime.now(UTC)
    base = {
        "created_at": now,
        "updated_at": now,
        "record_version": 1,
        "draft_scope_id": source["draft_scope_id"],
        "source_id": source["id"],
        "profile_id": "profile-1",
        "profile_revision": 1,
        "profile_sha256": "a" * 64,
        "decision": "approve",
        "reason": "Synthetic migration decision",
        "decision_json": "{}",
        "decision_sha256": "b" * 64,
        "reviewed_by_id": source["created_by_id"],
    }
    with engine.begin() as connection:
        connection.execute(decisions.insert().values(id="decision-1", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(decisions.insert().values(id="decision-2", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            decisions.insert().values(id="decision-3", **{**base, "profile_revision": 0})
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing profile decisions cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
