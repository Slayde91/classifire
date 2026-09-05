from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_estimates import add_payload
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade
from test_technical_release_publication import _bound_variant

from classifire import physical_models  # noqa: F401
from classifire.models import DraftEstimate, User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_estimates import add_line, create_estimate, read_estimate_revision
from classifire.services.draft_scope import create_draft_project, save_revision
from classifire.services.draft_scope_reports import create_report, report_bytes
from classifire.services.draft_system_matches import create_match
from classifire.services.draft_system_matches import revision_bytes as match_bytes
from classifire.services.technical_release_publication import publish_governed_technical_release


def test_forward_estimate_migration_preserves_saved_inputs_and_reports(tmp_path):
    database_url = "sqlite:///" + (tmp_path / "estimates-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0029_draft_system_matches")
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    storage_root = (tmp_path / "storage").resolve()
    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="migration-estimate@example.test",
            full_name="Retained owner",
            password_hash="unused",  # noqa: S106 - isolated migration fixture
            role="administrator",
            is_active=True,
        )  # noqa: S106 - isolated migration fixture
        db.add(actor)
        db.commit()
        draft = create_draft_project(db, actor, "BEFORE-0030", "Retained source")
        content = sample_payload()
        content["services"][0]["service_type"] = "pipe"
        save_revision(db, actor, draft.id, 1, content)
        report = create_report(db, actor, draft.id, 2)
        old_pdf = report_bytes(db, actor, draft.id, report.id, "pdf")
        _bound_variant(db, storage_root)
        release = publish_governed_technical_release(
            db,
            version="BEFORE-0030",
            notes="Synthetic migration fixture",
            actor=actor,
            storage_root=storage_root,
        )
        match = create_match(
            db, actor, draft.id, 2, release.id, uid(2), uid(5), storage_root=storage_root
        )
        old_match = match_bytes(db, actor, draft.id, match.id)
        draft_id, match_id, report_id = draft.id, match.id, report.id
        db.commit()
    _upgrade(database_url, environment, "head", enforce_sqlite_foreign_keys=True)
    inspector = inspect(engine)
    assert {"draft_estimates", "draft_estimate_revisions"} <= set(inspector.get_table_names())
    constraints = inspector.get_foreign_keys("draft_estimates")
    assert any(
        fk["constrained_columns"] == ["draft_scope_id", "scope_revision"]
        and fk["referred_table"] == "draft_scope_revisions"
        for fk in constraints
    )
    assert any(
        fk["constrained_columns"] == ["match_id", "match_revision"]
        and fk["referred_table"] == "draft_system_match_revisions"
        for fk in constraints
    )
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        estimate = create_estimate(db, actor, draft_id, 2, match_id=match_id, match_revision=1)
        add_line(db, actor, draft_id, estimate.id, 1, add_payload())
        db.commit()
        assert (
            read_estimate_revision(db, actor, draft_id, estimate.id)["summary"][
                "priced_subtotal_ex_tax"
            ]
            == "2.01"
        )
        assert match_bytes(db, actor, draft_id, match_id) == old_match
        assert report_bytes(db, actor, draft_id, report_id, "pdf") == old_pdf
        assert assess_deployment_lineage(db).status == "READY"
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0030_draft_estimates"
        for changes in (
            {"scope_revision": 999},
            {"match_revision": 999},
            {"match_hash": None},
            {"match_revision": None},
        ):
            with pytest.raises(IntegrityError):
                db.execute(
                    update(DraftEstimate).where(DraftEstimate.id == estimate.id).values(**changes)
                )
                db.flush()
            db.rollback()
    refusal = _run_migration(
        database_url, environment, "downgrade", "0029_draft_system_matches", expect_success=False
    )
    assert refusal.returncode != 0
    assert "Retained Draft Estimates cannot be downgraded" in refusal.stderr
    engine.dispose()
