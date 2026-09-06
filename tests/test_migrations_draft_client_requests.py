from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_scope import uid
from test_migrations_physical_foundation import _run_migration, _upgrade

from classifire.models import DraftClientRequest

base_case = _base_case
case = _case


def test_client_request_migration_preserves_native_packages_and_review_history(case, tmp_path):
    url, environment, engine, source, ids, expected = fixture(
        case, tmp_path, "0035_draft_package_imports"
    )
    assert "draft_client_requests" not in inspect(engine).get_table_names()
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        db.add(
            DraftClientRequest(
                owner_user_id=uid(100),
                command="create",
                payload_json="{}",
                payload_hash="0" * 64,
                identity_json=json.dumps({"source": "synthetic-migration"}),
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                status="pending",
            )
        )
        db.commit()
        assert db.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE draft_client_requests SET status='released'"))
            db.flush()
        db.rollback()
    refusal = _run_migration(
        url, environment, "downgrade", "0035_draft_package_imports", expect_success=False
    )
    assert (
        refusal.returncode != 0
        and "Retained client review history prevents downgrade" in refusal.stderr
    )
    verify_current(engine, ids, expected)
    engine.dispose()


def test_capability_migration_retains_existing_requests_and_refuses_history_loss(case, tmp_path):
    url, environment, engine, source, ids, expected = fixture(
        case, tmp_path, "0036_draft_client_requests"
    )
    with Session(engine) as db:
        row = DraftClientRequest(
            owner_user_id=uid(100),
            command="create",
            payload_json='{"name":"retained"}',
            payload_hash="1" * 64,
            identity_json='{"source":"synthetic"}',
            expires_at=datetime.now(UTC) + timedelta(minutes=5),
            status="pending",
        )
        db.add(row)
        db.commit()
        request_id = row.id
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        retained = db.get(DraftClientRequest, request_id)
        assert retained.payload_json == '{"name":"retained"}' and retained.status == "pending"
        db.add(
            DraftClientRequest(
                owner_user_id=uid(100),
                command="capability",
                payload_json="{}",
                payload_hash="2" * 64,
                identity_json="{}",
                expires_at=datetime.now(UTC) + timedelta(minutes=5),
                status="rejected",
            )
        )
        db.commit()
        assert db.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        with pytest.raises(IntegrityError):
            db.execute(text("UPDATE draft_client_requests SET command='release'"))
        db.rollback()
    refusal = _run_migration(
        url, environment, "downgrade", "0036_draft_client_requests", expect_success=False
    )
    assert (
        refusal.returncode != 0
        and "Retained capability requests prevent downgrade" in refusal.stderr
    )
    verify_current(engine, ids, expected)
    engine.dispose()
