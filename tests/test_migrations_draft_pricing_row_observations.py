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


def test_row_observation_migration_preserves_state_and_enforces_one_profile_row(case, tmp_path):
    baseline = "0041_draft_pricing_profile_decisions"
    target = "0042_draft_pricing_row_observations"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    profiles = Table("draft_pricing_source_profiles", MetaData(), autoload_with=engine)
    sources = Table("draft_pricing_sources", MetaData(), autoload_with=engine)
    decisions = Table(
        "draft_pricing_source_profile_decisions", MetaData(), autoload_with=engine
    )
    with engine.begin() as connection:
        source = connection.execute(
            select(sources).where(sources.c.id == ids["draft_pricing_sources"])
        ).mappings().one()
        now = datetime.now(UTC)
        connection.execute(
            profiles.insert().values(
                id="profile-1",
                created_at=now,
                updated_at=now,
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
        connection.execute(
            decisions.insert().values(
                id="decision-1",
                created_at=now,
                updated_at=now,
                record_version=1,
                draft_scope_id=source["draft_scope_id"],
                source_id=source["id"],
                profile_id="profile-1",
                profile_revision=1,
                profile_sha256="a" * 64,
                decision="approve",
                reason="Synthetic approval",
                decision_json="{}",
                decision_sha256="b" * 64,
                reviewed_by_id=source["created_by_id"],
            )
        )
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, target, enforce_sqlite_foreign_keys=True)
    added = set(inspect(engine).get_table_names()) - before
    assert "draft_pricing_row_observations" in added
    observations = Table("draft_pricing_row_observations", MetaData(), autoload_with=engine)
    now = datetime.now(UTC)
    base = {
        "created_at": now,
        "updated_at": now,
        "record_version": 1,
        "draft_scope_id": source["draft_scope_id"],
        "source_id": source["id"],
        "profile_id": "profile-1",
        "profile_decision_id": "decision-1",
        "dataset_id": "dataset-migration",
        "dataset_version": 1,
        "source_sha256": source["source_sha256"],
        "document_sha256": "c" * 64,
        "profile_revision": 1,
        "profile_sha256": "a" * 64,
        "decision_sha256": "b" * 64,
        "sheet_index": 1,
        "row_number": 2,
        "row_sha256": "d" * 64,
        "item_kind": "service",
        "normalized_reference": "SYN-1",
        "evidence_state": "confirmed",
        "review_reason": "Synthetic exact-row observation",
        "observation_json": "{}",
        "observation_sha256": "e" * 64,
        "reviewed_by_id": source["created_by_id"],
    }
    with engine.begin() as connection:
        connection.execute(observations.insert().values(id="observation-1", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(observations.insert().values(id="observation-2", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            observations.insert().values(
                id="observation-3", **{**base, "row_number": 3, "item_kind": "system"}
            )
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing row observations cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
