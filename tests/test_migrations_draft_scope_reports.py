from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_scope import uid
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade

from classifire import physical_models  # noqa: F401
from classifire.models import DraftScopeReport, User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_scope import create_draft_project, save_revision
from classifire.services.draft_scope_reports import create_report, read_report


def test_report_migration_preserves_scope_and_retains_pair_with_foreign_key_binding(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "reports-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0027_draft_scope_revisions")
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="migration@example.test",
            full_name="Retained owner",
            password_hash="unused",  # noqa: S106 - isolated non-authenticating fixture
            role="estimator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.commit()
        scope = create_draft_project(db, actor, "BEFORE-0028", "Retained source")
        save_revision(db, actor, scope.id, 1, {"assumptions": ["Predates report migration"]})
        draft_id = scope.id
        db.commit()
    _upgrade(
        database_url, environment, "0028_draft_scope_reports", enforce_sqlite_foreign_keys=True
    )
    inspector = inspect(engine)
    assert "draft_scope_reports" in inspector.get_table_names()
    assert any(
        fk["constrained_columns"] == ["draft_scope_id", "scope_revision"]
        and fk["referred_table"] == "draft_scope_revisions"
        for fk in inspector.get_foreign_keys("draft_scope_reports")
    )
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        report = create_report(db, actor, draft_id, 2)
        db.commit()
        assert read_report(db, actor, draft_id, report.id)["scope"]["content"]["assumptions"] == [
            "Predates report migration"
        ]
        assert assess_deployment_lineage(db).code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "0028_draft_scope_reports"
        )
        assert db.scalar(select(User.full_name).where(User.id == uid(100))) == "Retained owner"
        with pytest.raises(IntegrityError):
            db.execute(
                update(DraftScopeReport)
                .where(DraftScopeReport.id == report.id)
                .values(scope_revision=999)
            )
            db.flush()
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(
                update(DraftScopeReport)
                .where(DraftScopeReport.id == report.id)
                .values(pdf_bytes=b"")
            )
            db.flush()
        db.rollback()
    refusal = _run_migration(
        database_url, environment, "downgrade", "0027_draft_scope_revisions", expect_success=False
    )
    assert refusal.returncode != 0
    assert "Retained Draft Scope reports cannot be downgraded" in refusal.stderr
    engine.dispose()
