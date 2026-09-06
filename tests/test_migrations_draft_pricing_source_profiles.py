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


def test_profile_migration_preserves_historical_sources_and_enforces_history(case, tmp_path):
    baseline = "0039_draft_pdf_suggestions"
    target = "0040_draft_pricing_source_profiles"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    assert "draft_pricing_source_profiles" in set(inspect(engine).get_table_names()) - before
    sources = Table("draft_pricing_sources", MetaData(), autoload_with=engine)
    profiles = Table("draft_pricing_source_profiles", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        historical = connection.execute(
            select(sources).where(sources.c.id == ids["draft_pricing_sources"])
        ).mappings().one()
    assert historical["dataset_id"] is None
    assert historical["dataset_kind"] is None
    assert historical["dataset_version"] is None
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sources.update()
            .where(sources.c.id == ids["draft_pricing_sources"])
            .values(dataset_kind="general_pricelist")
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sources.update()
            .where(sources.c.id == ids["draft_pricing_sources"])
            .values(dataset_id="dataset", dataset_kind="other", dataset_version=1)
        )
    with engine.begin() as connection:
        connection.execute(
            sources.update()
            .where(sources.c.id == ids["draft_pricing_sources"])
            .values(
                dataset_id="dataset-a",
                dataset_kind="general_pricelist",
                dataset_version=1,
            )
        )
        now = datetime.now(UTC)
        base = {
            "created_at": now,
            "updated_at": now,
            "record_version": 1,
            "draft_scope_id": historical["draft_scope_id"],
            "source_id": historical["id"],
            "revision": 1,
            "parent_profile_sha256": None,
            "profile_json": "{}",
            "profile_sha256": "a" * 64,
            "created_by_id": historical["created_by_id"],
        }
        connection.execute(profiles.insert().values(id="profile-1", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(profiles.insert().values(id="profile-2", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            profiles.insert().values(id="profile-3", **{**base, "revision": 0})
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing source profiles cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
