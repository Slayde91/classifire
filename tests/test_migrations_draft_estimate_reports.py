from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_estimates import add_payload
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade

from classifire.models import DraftEstimateReport, User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_estimate_reports import create_report, report_bytes
from classifire.services.draft_estimates import add_line, create_estimate, revision_bytes
from classifire.services.draft_scope import create_draft_project, save_revision


def test_forward_report_migration_preserves_estimate_and_requires_exact_revision(tmp_path):
    url = "sqlite:///" + (tmp_path / "report-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, url)
    _upgrade(url, environment, "0030_draft_estimates")
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="report-migration@example.test",
            full_name="Synthetic owner",
            password_hash="unused",  # noqa: S106 - isolated non-authenticating fixture
            role="administrator",
            is_active=True,
        )
        db.add(actor)
        db.commit()
        draft = create_draft_project(db, actor, "BEFORE-0031", "Retained estimate")
        save_revision(db, actor, draft.id, 1, sample_payload())
        estimate = create_estimate(db, actor, draft.id, 2)
        add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        old = revision_bytes(db, actor, draft.id, estimate.id)
        ids = (draft.id, estimate.id)
        db.commit()
    _upgrade(url, environment, "0031_draft_estimate_reports", enforce_sqlite_foreign_keys=True)
    inspector = inspect(engine)
    assert "draft_estimate_reports" in inspector.get_table_names()
    assert any(
        fk["constrained_columns"] == ["estimate_id", "estimate_revision"]
        for fk in inspector.get_foreign_keys("draft_estimate_reports")
    )
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert revision_bytes(db, actor, *ids) == old
        report = create_report(db, actor, *ids, 2)
        db.commit()
        assert report_bytes(db, actor, *ids, report.id, "pdf").startswith(b"%PDF-")
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version"))
            == "0031_draft_estimate_reports"
        )
        with pytest.raises(IntegrityError):
            db.execute(
                update(DraftEstimateReport)
                .where(DraftEstimateReport.id == report.id)
                .values(estimate_revision=999)
            )
            db.flush()
        db.rollback()
    refusal = _run_migration(
        url, environment, "downgrade", "0030_draft_estimates", expect_success=False
    )
    assert refusal.returncode != 0
    assert "Retained Draft Estimate reports cannot be downgraded" in refusal.stderr
    engine.dispose()
