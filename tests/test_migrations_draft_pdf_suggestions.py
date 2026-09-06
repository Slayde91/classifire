from __future__ import annotations

import hashlib

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import JSON, MetaData, Table, Text, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_project_packages import save
from test_draft_scope import uid
from test_draft_workbook_evidence_outputs import workbook_scope
from test_migrations_draft_scope_xlsx_sources import HISTORICAL_TABLES, _pending_source
from test_migrations_physical_foundation import _run_migration, _upgrade

from classifire.models import (
    DraftPdfSource,
    DraftPdfSuggestion,
    DraftPricingSource,
    DraftScopeXlsxSource,
    User,
)
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services import draft_scope_reports as reports
from classifire.services.deployment_lineage import assess_deployment_lineage

base_case = _base_case
case = _case
BASELINE = "0038_draft_scope_xlsx_sources"
TARGET = "0039_draft_pdf_suggestions"
NEW_TABLE = "draft_pdf_suggestions"


def snapshot(engine):
    names = (*HISTORICAL_TABLES, "draft_scope_xlsx_sources")
    metadata = MetaData()
    metadata.reflect(engine, only=names)
    for table in metadata.tables.values():
        for column in table.c:
            if isinstance(column.type, JSON):
                column.type = Text()
    with engine.connect() as connection:
        return {
            name: connection.execute(
                select(metadata.tables[name]).order_by(metadata.tables[name].c.id)
            ).fetchall()
            for name in names
        }


def test_suggestion_migration_retains_pdf_xlsx_v5_history_and_enforces_status(case, tmp_path):
    url, environment, engine, _source, ids, expected = fixture(case, tmp_path, BASELINE)
    retained_files = {}
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        for model, filename, purpose in (
            (DraftPdfSource, "pending-report.pdf", "draft_scope_pdf"),
            (DraftPricingSource, "pending-pricing.xlsx", "draft_pricing_xlsx"),
            (DraftScopeXlsxSource, "pending-defects.xlsx", "draft_scope_xlsx"),
        ):
            path = tmp_path / filename
            retained_files[path] = ("Synthetic retained pending bytes: " + filename).encode()
            _pending_source(db, model, ids["draft"], actor.id, path, retained_files[path], purpose)
        # A real portable import retains foreign PDF/cell/image claims without inventing
        # a clean scan or local evidence authority in the historical database.
        raw = scopes._json(workbook_scope())
        imported = scopes.apply_import(
            db, actor, ids["draft"], 2, raw, hashlib.sha256(raw).hexdigest()
        )
        assert imported["schema_version"] == "CLASSIFIRE-DRAFT-SCOPE-v5"
        assert all(ref["origin"] == "imported_unverified" for ref in imported["evidence_refs"])
        report = reports.create_report(db, actor, ids["draft"], 3)
        report_id = report.id
        outputs = {
            fmt: reports.report_bytes(db, actor, ids["draft"], report_id, fmt)
            for fmt in ("pdf", "xlsx")
        }
        package = save(
            db, actor, ids["draft"], {"scope_revision": 3, "scope_reports": [report_id]}, revision=1
        )
        package_id, package_bytes = package.id, package.archive_bytes
        history = {rev: scopes.revision_bytes(db, actor, ids["draft"], rev) for rev in (1, 2, 3)}
        db.commit()
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    before_tables = set(inspect(engine).get_table_names())
    before = snapshot(engine)
    assert NEW_TABLE not in before_tables

    _upgrade(url, environment, TARGET, enforce_sqlite_foreign_keys=True)

    assert set(inspect(engine).get_table_names()) == before_tables | {NEW_TABLE}
    assert snapshot(engine) == before
    indexes = {tuple(index["column_names"]) for index in inspect(engine).get_indexes(NEW_TABLE)}
    assert {("draft_scope_id",), ("source_id",)} <= indexes
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        # This test intentionally stops at historical revision 0039. Once a later
        # migration exists, the current deployment guard must continue to fail closed.
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
        row = DraftPdfSuggestion(
            draft_scope_id=ids["draft"],
            source_id=ids["draft_pdf_sources"],
            created_by_id=actor.id,
            base_revision=3,
            proposal_json='{"synthetic":"retained-pending-proposal"}',
            proposal_sha256="a" * 64,
            status="pending",
        )
        db.add(row)
        db.flush()
        row_id = row.id
        db.commit()
    table = Table(NEW_TABLE, MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        retained = dict(
            connection.execute(select(table).where(table.c.id == row_id)).mappings().one()
        )
    for changes in (
        {"status": "approved"},
        {"base_revision": 0},
        {"status": "applied", "applied_revision": None},
        {"status": "applied", "applied_revision": 3},
        {"status": "pending", "applied_revision": 4},
        {"status": "rejected", "applied_revision": 4},
        {"proposal_json": "x" * 131073},
        {"source_id": uid(980)},
        {"draft_scope_id": uid(981)},
        {"created_by_id": uid(982)},
    ):
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(table.update().where(table.c.id == row_id).values(**changes))
    assert snapshot(engine) == before
    refusal = _run_migration(url, environment, "downgrade", BASELINE, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft PDF suggestions cannot be downgraded" in refusal.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            == TARGET
        )
        assert (
            dict(connection.execute(select(table).where(table.c.id == row_id)).mappings().one())
            == retained
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    assert snapshot(engine) == before
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        for rev, content in history.items():
            assert scopes.revision_bytes(db, actor, ids["draft"], rev) == content
        for fmt, content in outputs.items():
            assert reports.report_bytes(db, actor, ids["draft"], report_id, fmt) == content
        assert packages.package_bytes(db, actor, ids["draft"], package_id) == package_bytes
        assert (
            packages.package_bytes(db, actor, ids["draft"], ids["draft_project_packages"])
            == expected["package"]
        )
    for path, content in retained_files.items():
        assert path.read_bytes() == content
    engine.dispose()
