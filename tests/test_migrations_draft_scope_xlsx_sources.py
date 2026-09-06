from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import JSON, MetaData, Table, Text, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_scope import uid
from test_migrations_physical_foundation import _run_migration, _upgrade

from classifire.models import (
    DraftPdfSource,
    DraftPricingSource,
    DraftScopeXlsxSource,
    StoredFile,
    User,
    new_id,
)
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as scope_reports
from classifire.services.deployment_lineage import assess_deployment_lineage

base_case = _base_case
case = _case

BASELINE = "0037_draft_client_capabilities"
TARGET = "0038_draft_scope_xlsx_sources"
SOURCE_TABLE = "draft_scope_xlsx_sources"
HISTORICAL_TABLES = (
    "stored_files",
    "draft_pdf_sources",
    "draft_pricing_sources",
    "draft_scopes",
    "draft_scope_revisions",
    "draft_scope_reports",
    "draft_system_matches",
    "draft_system_match_revisions",
    "draft_estimates",
    "draft_estimate_revisions",
    "draft_estimate_reports",
    "draft_project_packages",
    "draft_package_imports",
    "draft_imported_report_sources",
    "draft_client_requests",
    "audit_events",
)


def _snapshot(engine):
    # Preserve exact JSON text and binary columns rather than reserializing them.
    metadata = MetaData()
    metadata.reflect(engine, only=HISTORICAL_TABLES)
    for table in metadata.tables.values():
        for column in table.c:
            if isinstance(column.type, JSON):
                column.type = Text()
    with engine.connect() as connection:
        return {
            name: connection.execute(
                select(metadata.tables[name]).order_by(metadata.tables[name].c.id)
            ).fetchall()
            for name in HISTORICAL_TABLES
        }


def _pending_source(db, model, draft_id, actor_id, path, content, purpose):
    # Pending source bytes are retained evidence only; no parser or clean verdict is fabricated.
    path.write_bytes(content)
    stored = StoredFile(
        original_filename=path.name,
        storage_path=str(path),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        purpose=purpose,
        malware_scan_status="pending",
        uploaded_by_id=actor_id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    # This helper intentionally writes a historical schema. A current ORM instance
    # would include columns introduced by later migrations even when their values are null.
    row_id = new_id()
    db.execute(
        model.__table__.insert().values(
            id=row_id,
            draft_scope_id=draft_id,
            stored_file_id=stored.id,
            source_sha256=stored.sha256,
            source_size_bytes=stored.size_bytes,
            created_by_id=actor_id,
            original_filename=path.name,
        )
    )
    db.flush()
    return SimpleNamespace(id=row_id, scan_json=None, document_json=None)


def test_scope_xlsx_upgrade_preserves_native_history_and_enforces_source_bindings(case, tmp_path):
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, BASELINE)
    retained_files = {
        tmp_path / "retained-pending.pdf": b"Synthetic pending PDF source before migration",
        tmp_path / "retained-pending.xlsx": b"Synthetic pending pricing source before migration",
    }
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        for model, path, purpose in (
            (DraftPdfSource, tmp_path / "retained-pending.pdf", "draft_scope_pdf"),
            (DraftPricingSource, tmp_path / "retained-pending.xlsx", "draft_pricing_xlsx"),
        ):
            _pending_source(db, model, ids["draft"], actor.id, path, retained_files[path], purpose)
        scope_report = scope_reports.create_report(db, actor, ids["draft"], 2)
        scope_report_id = scope_report.id
        scope_history = {
            revision: scopes.revision_bytes(db, actor, ids["draft"], revision)
            for revision in (1, 2)
        }
        scope_outputs = {
            fmt: scope_reports.report_bytes(db, actor, ids["draft"], scope_report_id, fmt)
            for fmt in ("pdf", "xlsx")
        }
        db.commit()
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    before_tables = set(inspect(engine).get_table_names())
    before = _snapshot(engine)
    assert SOURCE_TABLE not in before_tables

    _upgrade(url, environment, TARGET, enforce_sqlite_foreign_keys=True)

    assert set(inspect(engine).get_table_names()) - before_tables == {SOURCE_TABLE}
    assert before_tables <= set(inspect(engine).get_table_names())
    assert _snapshot(engine) == before
    assert any(
        index["column_names"] == ["draft_scope_id"]
        for index in inspect(engine).get_indexes(SOURCE_TABLE)
    )
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
        for revision, content in scope_history.items():
            assert scopes.revision_bytes(db, actor, ids["draft"], revision) == content
        for fmt, content in scope_outputs.items():
            assert (
                scope_reports.report_bytes(db, actor, ids["draft"], scope_report_id, fmt) == content
            )
        assert (
            packages.package_bytes(db, actor, ids["draft"], ids["draft_project_packages"])
            == expected["package"]
        )
        source = _pending_source(
            db,
            DraftScopeXlsxSource,
            ids["draft"],
            actor.id,
            tmp_path / "new-pending-defects.xlsx",
            b"Synthetic pending defect workbook after migration",
            "draft_scope_xlsx",
        )
        source_id = source.id
        db.commit()
        assert source.scan_json is None and source.document_json is None
        assert db.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    table = Table(SOURCE_TABLE, MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        retained = dict(
            connection.execute(select(table).where(table.c.id == source_id)).mappings().one()
        )
    for changes in (
        {"source_sha256": "c" * 64},
        {"source_size_bytes": retained["source_size_bytes"] + 1},
        {"stored_file_id": uid(901)},
        {"draft_scope_id": uid(902)},
        {"created_by_id": uid(903)},
    ):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(table.update().where(table.c.id == source_id).values(**changes))
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(table.insert().values(**(retained | {"id": uid(904)})))
    for size in (0, 10485761):
        with Session(engine) as db:
            stored = StoredFile(
                original_filename="invalid-size.xlsx",
                storage_path="not-read-invalid-size.xlsx",
                sha256="d" * 64,
                size_bytes=size,
                purpose="draft_scope_xlsx",
                malware_scan_status="pending",
                uploaded_by_id=uid(100),
                immutable=True,
            )
            db.add(stored)
            db.flush()
            with pytest.raises(IntegrityError, match="ck_draft_scope_xlsx_source_size"):
                db.execute(
                    table.insert().values(
                        **(
                            retained
                            | {
                                "id": uid(905),
                                "stored_file_id": stored.id,
                                "source_sha256": stored.sha256,
                                "source_size_bytes": size,
                            }
                        )
                    )
                )
            db.rollback()

    refusal = _run_migration(url, environment, "downgrade", BASELINE, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft Scope XLSX sources cannot be downgraded" in refusal.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == TARGET
        )
        assert (
            dict(connection.execute(select(table).where(table.c.id == source_id)).mappings().one())
            == retained
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert assess_deployment_lineage(db).code == "CLEAN_STACK_HEAD_CONFIRMED"
        assert (
            packages.package_bytes(db, actor, ids["draft"], ids["draft_project_packages"])
            == expected["package"]
        )
        for revision, content in scope_history.items():
            assert scopes.revision_bytes(db, actor, ids["draft"], revision) == content
        for fmt, content in scope_outputs.items():
            assert (
                scope_reports.report_bytes(db, actor, ids["draft"], scope_report_id, fmt) == content
            )
    for path, content in retained_files.items():
        assert path.read_bytes() == content
    engine.dispose()
