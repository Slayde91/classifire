"""Exercise real migration history in owned schemas on the opt-in PostgreSQL DB."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import (
    JSON,
    MetaData,
    Table,
    Text,
    bindparam,
    cast,
    create_engine,
    func,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema
from test_migrations_physical_foundation import (
    ROOT,
    _migration_environment,
    _run_migration,
    _upgrade,
)
from test_proposal_review_package_lifecycle import _package_and_bindings, _session
from test_shared_file_containment import _postgres_test_url

from classifire.db import Base
from classifire.models import DraftEstimate, DraftSystemMatch, User
from classifire.physical_models import PhysicalModelLock
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services.proposal_review_package import (
    create_proposal_review_package_redaction,
    grant_proposal_review_reader_assignment,
    register_proposal_review_package,
)

BASELINE = "0046_draft_pricing_quantity_bases"
HEAD = "0047_draft_scope_docx_sources"


@pytest.fixture
def migration_postgresql() -> Iterator[tuple[str, Engine, str]]:
    # Reuse the explicit loopback/database/opt-in guard, but never reset public
    # tables: each test owns one unpredictable schema and its own search_path.
    url = make_url(_postgres_test_url())
    schema = "classifire_migration_" + uuid4().hex
    owner = create_engine(url)
    with owner.begin() as connection:
        connection.execute(CreateSchema(schema))
    isolated_url = url.update_query_dict({"options": "-csearch_path=" + schema})
    engine = create_engine(isolated_url)
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
        yield url.render_as_string(hide_password=False), engine, schema
    finally:
        engine.dispose()
        with owner.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        owner.dispose()


def _environment(tmp_path: Path, url: str, schema: str) -> dict[str, str]:
    environment = _migration_environment(tmp_path, url)
    environment["PGOPTIONS"] = "-csearch_path=" + schema
    return environment


def _current(environment: dict[str, str]) -> None:
    result = subprocess.run(  # noqa: S603 - fixed local migration CLI, synthetic environment
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), "current"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _version(engine: Engine) -> tuple[str, str]:
    with engine.connect() as connection:
        return (
            connection.scalar(text("SELECT version_num FROM alembic_version")),
            str(inspect(connection).get_columns("alembic_version")[0]["type"]),
        )


def _review_history(engine: Engine) -> dict[str, list[dict]]:
    retained = {}
    with engine.connect() as connection:
        for name in (
            "proposal_review_packages",
            "proposal_review_package_redactions",
            "proposal_review_reader_assignments",
        ):
            table = Table(name, MetaData(), autoload_with=connection)
            retained[name] = [
                dict(row)
                for row in connection.execute(select(table).order_by(table.c.id)).mappings()
            ]
    return retained


def _copy_historical_rows(source: Engine, target: Engine) -> None:
    metadata = MetaData()
    metadata.reflect(target)
    with source.connect() as reader, target.begin() as writer:
        for table in metadata.sorted_tables:
            if table.name == "alembic_version":
                continue
            source_table = Table(table.name, MetaData(), autoload_with=source)
            json_values = {}
            for column in table.c:
                if isinstance(column.type, JSON):
                    # Read raw JSON text, retaining SQL NULL versus JSON null.
                    # PostgreSQL requires an explicit cast for these text binds.
                    source_table.c[column.name].type = Text()
                    json_values[column.name] = cast(
                        bindparam(column.name, type_=Text()), column.type
                    )
            records = reader.execute(
                select(*(source_table.c[column.name] for column in table.c))
            ).mappings()
            rows = [dict(row) for row in records]
            if rows:
                writer.execute(table.insert().values(**json_values), rows)


def _seed_review_history(engine: Engine) -> dict[str, list[dict]]:
    # Reuse native synthetic registration/permission/redaction fixtures, then
    # copy only columns actually present in the historical0019 schema.
    source = _session()
    try:
        package, administrator, reviewer, _ = _package_and_bindings(source)
        record, _ = register_proposal_review_package(
            source,
            package=package,
            actor=administrator,
            registered_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
        create_proposal_review_package_redaction(
            source,
            proposal_review_package_id=record.id,
            redacted_scope_ids=["SCOPE-001"],
            redaction_reason_code="PERSONAL_DATA",
            actor=administrator,
        )
        grant_proposal_review_reader_assignment(
            source,
            user_id=reviewer.id,
            proposal_review_package_id=record.id,
            reason_code="CONTROLLED_UAT",
            actor=administrator,
        )
        source.commit()
        _copy_historical_rows(source.get_bind(), engine)
    finally:
        source.close()
        source.get_bind().dispose()
    retained = _review_history(engine)
    assert all(len(rows) == 1 for rows in retained.values())
    return retained


def test_postgresql_migration_current_does_not_create_version_table(
    migration_postgresql, tmp_path: Path
) -> None:
    url, engine, schema = migration_postgresql
    assert inspect(engine).get_table_names() == []
    _current(_environment(tmp_path, url, schema))
    assert inspect(engine).get_table_names() == []


def test_postgresql_fresh_history_and_word_upgrade_preserve_scope_package(
    migration_postgresql, tmp_path: Path
) -> None:
    url, engine, schema = migration_postgresql
    environment = _environment(tmp_path, url, schema)
    _upgrade(url, environment, "0019_report_evidence_family_manifests")
    before_review = _seed_review_history(engine)
    incoming_tables = (
        "proposal_review_package_redactions",
        "proposal_review_reader_assignments",
    )
    incoming_keys = {table: inspect(engine).get_foreign_keys(table) for table in incoming_tables}
    _upgrade(url, environment, BASELINE)
    assert {
        table: inspect(engine).get_foreign_keys(table) for table in incoming_tables
    } == incoming_keys
    after_review = _review_history(engine)
    for table, rows in before_review.items():
        assert [
            {column: current[column] for column in original}
            for current, original in zip(after_review[table], rows, strict=True)
        ] == rows
    assert after_review["proposal_review_packages"][0]["package_kind"] == "single_report"
    assert _version(engine) == (BASELINE, "TEXT")
    admission_table = Base.metadata.tables["physical_model_lock_amendment_admissions"]
    admission_index = next(
        index
        for index in admission_table.indexes
        if list(index.columns.keys()) == ["amendment_admission_id"]
    )
    assert len(admission_index.name) > engine.dialect.max_identifier_length
    expected_name = engine.dialect.identifier_preparer.format_index(admission_index)
    assert any(
        index["name"] == expected_name and index["column_names"] == ["amendment_admission_id"]
        for index in inspect(engine).get_indexes(admission_table.name)
    )
    before_tables = set(inspect(engine).get_table_names())
    with Session(engine) as db:
        actor = User(
            email="migration-history@example.test",
            full_name="Synthetic migration history",
            password_hash="non-authenticating-test",  # noqa: S106 - synthetic fixture
            role="administrator",
            is_active=True,
        )
        db.add(actor)
        db.flush()
        draft = scopes.create_draft_project(
            db, actor, "SYNTHETIC-MIGRATION", "Retained Draft history"
        )
        scopes.save_revision(
            db,
            actor,
            draft.id,
            1,
            {"assumptions": ["Service material and quantity remain unknown"]},
        )
        selected = {"scope_revision": 2}
        preview = packages.preview(db, actor, draft.id, selected)
        package = packages.create_package(db, actor, draft.id, selected, 0, preview["preview_hash"])
        identities = actor.id, draft.id, package.id
        expected_scope = [scopes.revision_bytes(db, actor, draft.id, rev) for rev in (1, 2)]
        expected_zip = packages.package_bytes(db, actor, draft.id, package.id)
        db.commit()
    _upgrade(url, environment, "head")
    assert _version(engine) == (HEAD, "TEXT")
    assert set(inspect(engine).get_table_names()) - before_tables == {"draft_scope_docx_sources"}
    foreign_keys = inspect(engine).get_foreign_keys("draft_scope_docx_sources")
    assert any(
        key["constrained_columns"] == ["stored_file_id", "source_sha256", "source_size_bytes"]
        and key["referred_table"] == "stored_files"
        for key in foreign_keys
    )
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
        )
    refusal = _run_migration(url, environment, "downgrade", BASELINE, expect_success=False)
    assert refusal.returncode != 0
    assert "Retained Draft Scope DOCX sources cannot be downgraded" in refusal.stderr
    assert _version(engine) == (HEAD, "VARCHAR(32)")
    with Session(engine) as db:
        actor = db.get(User, identities[0])
        assert [scopes.revision_bytes(db, actor, identities[1], rev) for rev in (1, 2)] == (
            expected_scope
        )
        assert packages.package_bytes(db, actor, identities[1], identities[2]) == expected_zip
        for model in (DraftSystemMatch, DraftEstimate, PhysicalModelLock):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_postgresql_existing_short_version_column_expands_without_history_rewrite(
    migration_postgresql, tmp_path: Path
) -> None:
    url, engine, schema = migration_postgresql
    environment = _environment(tmp_path, url, schema)
    _upgrade(url, environment, "0001_baseline")
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(32)")
        )
        connection.execute(
            text(
                "INSERT INTO users (id, created_at, updated_at, record_version, email, "
                "full_name, password_hash, role, is_active) VALUES "
                "(:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :email, "
                "'Synthetic early history', 'non-authenticating-test', 'read_only', true)"
            ),
            {"id": "00000000-0000-0000-0000-000000000001", "email": "early@example.test"},
        )
        before_user = connection.execute(text("SELECT * FROM users")).mappings().one()
    _current(environment)
    assert _version(engine) == ("0001_baseline", "VARCHAR(32)")
    _upgrade(url, environment, "head")
    assert _version(engine) == (HEAD, "TEXT")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM users")).mappings().one() == before_user
