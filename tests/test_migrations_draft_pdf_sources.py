from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, inspect, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_estimates import add_payload
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _migration_environment, _run_migration, _upgrade

from classifire.models import DraftPdfSource, StoredFile, User
from classifire.services.deployment_lineage import assess_deployment_lineage
from classifire.services.draft_estimate_reports import create_report, report_bytes
from classifire.services.draft_estimates import add_line, create_estimate, revision_bytes
from classifire.services.draft_scope import create_draft_project, save_revision


def test_pdf_migration_preserves_saved_work_and_binds_exact_source_bytes(tmp_path):
    url = "sqlite:///" + (tmp_path / "pdf-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, url)
    _upgrade(url, environment, "0031_draft_estimate_reports")
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="pdf-migration@example.test",
            full_name="Synthetic owner",
            password_hash="unused",  # noqa: S106 - synthetic fixture
            role="administrator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.commit()
        draft = create_draft_project(db, actor, "BEFORE-0032", "Retained estimate and report")
        save_revision(db, actor, draft.id, 1, sample_payload())
        estimate = create_estimate(db, actor, draft.id, 2)
        add_line(db, actor, draft.id, estimate.id, 1, add_payload())
        old = revision_bytes(db, actor, draft.id, estimate.id)
        report = create_report(db, actor, draft.id, estimate.id, 2)
        report_id = report.id
        outputs = {
            kind: report_bytes(db, actor, draft.id, estimate.id, report.id, kind)
            for kind in ("pdf", "xlsx")
        }
        ids = (draft.id, estimate.id)
        db.commit()
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    assert "draft_pdf_sources" in inspect(engine).get_table_names()
    assert any(
        fk["constrained_columns"] == ["stored_file_id", "source_sha256", "source_size_bytes"]
        for fk in inspect(engine).get_foreign_keys("draft_pdf_sources")
    )
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert revision_bytes(db, actor, *ids) == old
        for kind, content in outputs.items():
            assert report_bytes(db, actor, *ids, report_id, kind) == content
        assert assess_deployment_lineage(db).code == "CLEAN_STACK_HEAD_CONFIRMED"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "0032_draft_pdf_sources"
        )
        stored = StoredFile(
            original_filename="synthetic.pdf",
            storage_path="not-read.pdf",
            sha256="a" * 64,
            size_bytes=100,
            purpose="draft_scope_pdf",
            malware_scan_status="pending",
            uploaded_by_id=actor.id,
            immutable=True,
        )
        db.add(stored)
        db.flush()
        source = DraftPdfSource(
            draft_scope_id=ids[0],
            stored_file_id=stored.id,
            source_sha256=stored.sha256,
            source_size_bytes=100,
            original_filename="synthetic.pdf",
            created_by_id=actor.id,
        )
        db.add(source)
        db.commit()
        with pytest.raises(IntegrityError):
            db.execute(
                update(DraftPdfSource)
                .where(DraftPdfSource.id == source.id)
                .values(source_sha256="b" * 64)
            )
            db.flush()
        db.rollback()
    refusal = _run_migration(
        url, environment, "downgrade", "0031_draft_estimate_reports", expect_success=False
    )
    assert refusal.returncode != 0
    assert "Retained Draft PDF sources cannot be downgraded" in refusal.stderr
    engine.dispose()
