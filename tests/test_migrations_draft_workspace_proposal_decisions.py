"""Actual historical migration preserves bytes and enforces decision constraints."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_migrations_physical_foundation import _run_migration, _upgrade

from classifire.services.deployment_lineage import assess_deployment_lineage

base_case = _base_case
case = _case


def test_decision_migration_preserves_saved_history_and_enforces_one_decision(case, tmp_path):
    url, environment, engine, _source, ids, expected = fixture(
        case, tmp_path, "0048_draft_workspace_proposals"
    )
    now = datetime.now(UTC)
    proposals = Table("draft_workspace_proposals", MetaData(), autoload_with=engine)
    with engine.begin() as c:
        actor = c.scalar(
            text("SELECT owner_user_id FROM draft_scopes WHERE id=:id"), {"id": ids["draft"]}
        )
        # Structural historical fixture; never presented as an application-validated proposal.
        raw = '{"fixture":"synthetic retained migration history"}'
        c.execute(
            proposals.insert(),
            {
                "id": "00000000-0000-4000-8000-000000000049",
                "created_at": now,
                "updated_at": now,
                "record_version": 1,
                "draft_scope_id": ids["draft"],
                "created_by_id": actor,
                "base_revision": 1,
                "proposal_json": raw,
                "proposal_sha256": hashlib.sha256(raw.encode()).hexdigest(),
            },
        )
    with Session(engine) as db:
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    before = set(inspect(engine).get_table_names())
    _upgrade(url, environment, "0049_draft_proposal_decisions", enforce_sqlite_foreign_keys=True)
    assert set(inspect(engine).get_table_names()) - before == {"draft_workspace_proposal_decisions"}
    keys = inspect(engine).get_foreign_keys("draft_workspace_proposal_decisions")
    assert {k["referred_table"] for k in keys} == {
        "draft_workspace_proposals",
        "users",
        "draft_scope_revisions",
    }
    with Session(engine) as db:
        assessment = assess_deployment_lineage(db)
        assert assessment.status == "READY" and not assessment.database_write_performed
    with engine.connect() as c:
        assert c.scalar(select(proposals.c.proposal_json)) == raw
    decisions = Table("draft_workspace_proposal_decisions", MetaData(), autoload_with=engine)
    row = {
        "id": "00000000-0000-4000-8000-000000000050",
        "created_at": now,
        "updated_at": now,
        "record_version": 1,
        "proposal_id": "00000000-0000-4000-8000-000000000049",
        "created_by_id": actor,
        "outcome": "rejected",
        "scope_revision_id": None,
        "decision_json": "{}",
        "decision_sha256": hashlib.sha256(b"{}").hexdigest(),
    }
    for changed in (
        {"proposal_id": "missing"},
        {"outcome": "confirmed"},
        {"outcome": "automatically_approved"},
        {"decision_json": "x" * 16385},
    ):
        with pytest.raises(IntegrityError), engine.begin() as c:
            c.execute(decisions.insert(), row | changed)
    with engine.begin() as c:
        c.execute(decisions.insert(), row)
    with pytest.raises(IntegrityError), engine.begin() as c:
        c.execute(decisions.insert(), row | {"id": "00000000-0000-4000-8000-000000000051"})
    refusal = _run_migration(
        url, environment, "downgrade", "0048_draft_workspace_proposals", expect_success=False
    )
    assert (
        refusal.returncode != 0
        and "Retained native proposal decisions cannot be downgraded" in refusal.stderr
    )
    with engine.connect() as c:
        assert len(c.execute(select(decisions)).all()) == 1
        assert c.scalar(select(proposals.c.proposal_json)) == raw
    verify_current(engine, ids, expected)
    engine.dispose()
