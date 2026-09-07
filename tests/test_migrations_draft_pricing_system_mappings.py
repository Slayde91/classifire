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


def test_system_mapping_migration_preserves_state_and_enforces_status_binding(case, tmp_path):
    baseline = "0042_draft_pricing_row_observations"
    target = "0043_draft_pricing_system_mappings"
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, baseline)
    metadata = MetaData()
    profiles = Table("draft_pricing_source_profiles", metadata, autoload_with=engine)
    sources = Table("draft_pricing_sources", metadata, autoload_with=engine)
    decisions = Table(
        "draft_pricing_source_profile_decisions", metadata, autoload_with=engine
    )
    releases = Table("library_releases", metadata, autoload_with=engine)
    variants = Table("technical_variants", metadata, autoload_with=engine)
    now = datetime.now(UTC)
    with engine.begin() as connection:
        source = connection.execute(
            select(sources).where(sources.c.id == ids["draft_pricing_sources"])
        ).mappings().one()
        release = connection.execute(
            select(releases).where(
                releases.c.library_type == "technical",
                releases.c.status == "active",
            )
        ).mappings().one()
        variant = connection.execute(select(variants).limit(1)).mappings().one()
        common = {
            "created_at": now,
            "updated_at": now,
            "record_version": 1,
        }
        connection.execute(
            profiles.insert().values(
                id="profile-b",
                **common,
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
                id="decision-b",
                **common,
                draft_scope_id=source["draft_scope_id"],
                source_id=source["id"],
                profile_id="profile-b",
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
    assert added == {"draft_pricing_system_mappings"}
    mappings = Table("draft_pricing_system_mappings", MetaData(), autoload_with=engine)
    base = {
        "created_at": now,
        "updated_at": now,
        "record_version": 1,
        "draft_scope_id": source["draft_scope_id"],
        "source_id": source["id"],
        "profile_id": "profile-b",
        "profile_decision_id": "decision-b",
        "dataset_id": "dataset-b",
        "dataset_version": 1,
        "source_sha256": source["source_sha256"],
        "document_sha256": "d" * 64,
        "profile_revision": 1,
        "profile_sha256": "a" * 64,
        "decision_sha256": "b" * 64,
        "sheet_index": 1,
        "row_number": 2,
        "row_sha256": "e" * 64,
        "mapping_status": "mapped",
        "normalized_reference": "SYN-B",
        "review_reason": "Synthetic exact-row mapping",
        "technical_release_id": release["id"],
        "technical_release_sha256": "c" * 64,
        "technical_variant_id": variant["id"],
        "technical_variant_snapshot_sha256": "f" * 64,
        "mapping_json": "{}",
        "mapping_sha256": "1" * 64,
        "reviewed_by_id": source["created_by_id"],
    }
    with engine.begin() as connection:
        connection.execute(mappings.insert().values(id="mapping-b", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(mappings.insert().values(id="mapping-b-replay", **base))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            mappings.insert().values(
                id="mapping-b-invalid",
                **{
                    **base,
                    "row_number": 3,
                    "mapping_status": "unmatched",
                },
            )
        )
    refusal = _run_migration(url, environment, "downgrade", baseline, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft pricing system mappings cannot be downgraded" in refusal.stderr
    verify_current(engine, ids, expected)
    engine.dispose()
