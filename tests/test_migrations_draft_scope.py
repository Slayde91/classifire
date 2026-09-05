from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade

from classifire import physical_models  # noqa: F401
from classifire.models import User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_scope import create_draft_project, read_revision, save_revision


def test_draft_scope_migration_preserves_existing_data_and_supports_revisions(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "migration.sqlite").as_posix()
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0026_single_active_technical_release")
    engine = create_engine(database_url)
    with Session(engine) as db:
        actor = User(
            email="migration@example.test",
            full_name="Retained user",
            password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
            role="estimator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.commit()
        actor_id = actor.id
    _upgrade(database_url, environment, "head", enforce_sqlite_foreign_keys=True)
    inspector = inspect(engine)
    assert {"draft_scopes", "draft_scope_revisions"} <= set(inspector.get_table_names())
    assert {
        tuple(row["column_names"])
        for row in inspector.get_unique_constraints("draft_scope_revisions")
    } == {("draft_scope_id", "revision")}
    with Session(engine) as db:
        actor = db.get(User, actor_id)
        assert actor.full_name == "Retained user"
        draft = create_draft_project(db, actor, "MIGRATED", "Migrated draft")
        save_revision(db, actor, draft.id, 1, {"assumptions": ["Synthetic migration test"]})
        db.commit()
        assert read_revision(db, actor, draft.id)["revision"] == 2
        assert assess_deployment_lineage(db).status == "READY"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version"))
            == "0027_draft_scope_revisions"
        )
    with engine.begin() as connection:
        with pytest.raises(IntegrityError, match="UNIQUE constraint failed"):
            connection.execute(
                text(
                    "INSERT INTO draft_scope_revisions SELECT 'different-id', created_at, "
                    "updated_at, record_version, draft_scope_id, revision, parent_hash, "
                    "content_hash, envelope_json, created_by_id "
                    "FROM draft_scope_revisions LIMIT 1"
                )
            )
    refusal = _run_migration(
        database_url,
        environment,
        "downgrade",
        "0026_single_active_technical_release",
        expect_success=False,
    )
    assert refusal.returncode != 0
    assert "Retained Draft Scope revision history cannot be downgraded" in refusal.stderr
    engine.dispose()
