from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade
from test_technical_release_publication import _bound_variant

from classifire import physical_models  # noqa: F401
from classifire.models import DraftSystemMatch, User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_scope import create_draft_project, save_revision
from classifire.services.draft_scope_reports import create_report, report_bytes
from classifire.services.draft_system_matches import create_match, read_match_revision
from classifire.services.technical_release_publication import publish_governed_technical_release


def test_match_migration_preserves_scope_reports_and_retains_bound_candidate_review(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "matches-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0028_draft_scope_reports")
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    storage_root = (tmp_path / "storage").resolve()
    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="migration-match@example.test",
            full_name="Retained owner",
            password_hash="unused",  # noqa: S106 - isolated migration fixture
            role="administrator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.commit()
        draft = create_draft_project(db, actor, "BEFORE-0029", "Retained source")
        content = sample_payload()
        content["services"][0]["service_type"] = "pipe"
        save_revision(db, actor, draft.id, 1, content)
        report = create_report(db, actor, draft.id, 2)
        old_pdf = report_bytes(db, actor, draft.id, report.id, "pdf")
        _bound_variant(db, storage_root)
        release = publish_governed_technical_release(
            db,
            version="BEFORE-0029",
            notes="Synthetic migration fixture",
            actor=actor,
            storage_root=storage_root,
        )
        draft_id, release_id, report_id = draft.id, release.id, report.id
        db.commit()
    _upgrade(
        database_url, environment, "0029_draft_system_matches", enforce_sqlite_foreign_keys=True
    )
    inspector = inspect(engine)
    assert {"draft_system_matches", "draft_system_match_revisions"} <= set(
        inspector.get_table_names()
    )
    assert any(
        fk["constrained_columns"] == ["draft_scope_id", "scope_revision"]
        and fk["referred_table"] == "draft_scope_revisions"
        for fk in inspector.get_foreign_keys("draft_system_matches")
    )
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        match = create_match(
            db, actor, draft_id, 2, release_id, uid(2), uid(5), storage_root=storage_root
        )
        db.commit()
        assert read_match_revision(db, actor, draft_id, match.id)["candidates"]
        assert report_bytes(db, actor, draft_id, report_id, "pdf") == old_pdf
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version"))
            == "0029_draft_system_matches"
        )
        with pytest.raises(IntegrityError):
            db.execute(
                update(DraftSystemMatch)
                .where(DraftSystemMatch.id == match.id)
                .values(scope_revision=999)
            )
            db.flush()
        db.rollback()
    refusal = _run_migration(
        database_url, environment, "downgrade", "0028_draft_scope_reports", expect_success=False
    )
    assert refusal.returncode != 0
    assert "Retained Draft System Match reviews cannot be downgraded" in refusal.stderr
    engine.dispose()
