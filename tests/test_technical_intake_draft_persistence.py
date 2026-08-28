from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeDraft,
    User,
)
from classifire.services.deployment_lineage import CLEAN_STACK_HEAD

ROOT = Path(__file__).resolve().parents[1]
SOURCE_SIZE = 321


def _migration_environment(tmp_path: Path, database_url: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "CLASSIFIRE_DATABASE_URL": database_url,
            "CLASSIFIRE_STORAGE_ROOT": str(tmp_path / "storage"),
            "PYTHONPATH": str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", ""),
            "PYTHONPYCACHEPREFIX": str(tmp_path / "pycache"),
        }
    )
    return environment


def _run_migration(
    environment: dict[str, str],
    action: str,
    revision: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ROOT / "alembic.ini"),
            action,
            revision,
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _model_engine():  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    return engine


def _source(
    db: Session,
    suffix: str,
    *,
    source_sha256: str = "a" * 64,
    source_size_bytes: int = SOURCE_SIZE,
) -> tuple[User, StoredFile, TechnicalDocument]:
    owner = User(
        email=f"draft-owner-{suffix}@example.test",
        full_name=f"Draft Owner {suffix}",
        password_hash="not-used-in-persistence-test",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    stored = StoredFile(
        original_filename=f"assessment-{suffix}.pdf",
        media_type="application/pdf",
        storage_path=f"C:/governed/assessment-{suffix}.pdf",
        sha256=source_sha256,
        size_bytes=source_size_bytes,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=owner.id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=f"DOC-DRAFT-{suffix}",
        stored_file_id=stored.id,
        document_type="fire_assessment",
        title=f"Assessment {suffix}",
        status="draft",
        extraction_status="completed",
    )
    db.add(document)
    db.flush()
    return owner, stored, document


def _draft(
    owner: User,
    stored: StoredFile,
    document: TechnicalDocument,
) -> TechnicalIntakeDraft:
    return TechnicalIntakeDraft(
        technical_document_id=document.id,
        source_stored_file_id=stored.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
        owner_id=owner.id,
        payload_json={"fields": [], "template_schema": "technical-intake-template-v1"},
        payload_sha256="b" * 64,
    )


def _schema_signature(inspector, table_name: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "columns": frozenset(
            (column["name"], bool(column["nullable"]))
            for column in inspector.get_columns(table_name)
        ),
        "checks": frozenset(
            constraint["name"]
            for constraint in inspector.get_check_constraints(table_name)
        ),
        "foreign_keys": frozenset(
            (
                constraint["name"],
                tuple(constraint["constrained_columns"]),
                constraint["referred_table"],
                tuple(constraint["referred_columns"]),
            )
            for constraint in inspector.get_foreign_keys(table_name)
        ),
        "uniques": frozenset(
            (constraint["name"], tuple(constraint["column_names"]))
            for constraint in inspector.get_unique_constraints(table_name)
        ),
        "indexes": frozenset(
            (
                index["name"],
                tuple(index["column_names"]),
                bool(index["unique"]),
            )
            for index in inspector.get_indexes(table_name)
        ),
    }


def test_model_persists_only_exact_owner_bound_draft_payload() -> None:
    engine = _model_engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, stored, document = _source(db, "valid")
        draft = _draft(owner, stored, document)
        db.add(draft)
        db.commit()

        persisted = db.scalar(
            select(TechnicalIntakeDraft).where(TechnicalIntakeDraft.id == draft.id)
        )
        assert persisted is not None
        assert persisted.draft_schema == "technical-intake-draft-v1"
        assert persisted.status == "draft"
        assert persisted.record_version == 1
        assert persisted.technical_document_id == document.id
        assert persisted.source_stored_file_id == stored.id
        assert persisted.source_sha256 == stored.sha256
        assert persisted.source_size_bytes == stored.size_bytes
        assert persisted.owner_id == owner.id
        assert persisted.payload_json == {
            "fields": [],
            "template_schema": "technical-intake-template-v1",
        }


def test_model_declares_exact_constraints_bindings_and_indexes() -> None:
    table = TechnicalIntakeDraft.__table__
    assert set(table.c.keys()) == {
        "created_at",
        "draft_schema",
        "id",
        "owner_id",
        "payload_json",
        "payload_sha256",
        "record_version",
        "source_sha256",
        "source_size_bytes",
        "source_stored_file_id",
        "status",
        "technical_document_id",
        "updated_at",
    }
    assert {constraint.name for constraint in table.foreign_key_constraints} == {
        "fk_technical_intake_draft_document_source",
        "fk_technical_intake_draft_owner",
        "fk_technical_intake_draft_source_bytes",
    }
    assert {constraint.name for constraint in table.constraints} >= {
        "ck_technical_intake_draft_id",
        "ck_technical_intake_draft_payload_sha256",
        "ck_technical_intake_draft_record_version",
        "ck_technical_intake_draft_schema",
        "ck_technical_intake_draft_source_sha256",
        "ck_technical_intake_draft_source_size",
        "ck_technical_intake_draft_status",
        "uq_technical_intake_draft_owner_document_source",
    }
    assert {
        index.name: tuple(column.name for column in index.columns)
        for index in table.indexes
    } == {
        "ix_technical_intake_drafts_document": ("technical_document_id",),
        "ix_technical_intake_drafts_owner_status_updated": (
            "owner_id",
            "status",
            "updated_at",
        ),
    }
    assert table.c.payload_json.nullable is False
    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert "draft_schema = 'technical-intake-draft-v1'" in ddl
    assert "status = 'draft'" in ddl
    assert "source_size_bytes BETWEEN 1 AND 1073741824" in ddl
    assert "record_version >= 1" in ddl
    for sha256_column in ("source_sha256", "payload_sha256"):
        assert f"{sha256_column} = lower({sha256_column})" in ddl
        assert f"replace({sha256_column}, '0', '')" in ddl


@pytest.mark.parametrize(
    ("attribute", "invalid_value"),
    (
        ("id", "not-a-canonical-uuid4"),
        ("draft_schema", "technical-intake-draft-v2"),
        ("status", "approved"),
        ("payload_sha256", "A" * 64),
        ("payload_sha256", "g" * 64),
        ("source_size_bytes", 0),
        ("source_size_bytes", 1_073_741_825),
        ("record_version", 0),
    ),
)
def test_model_rejects_invalid_draft_constraints(
    attribute: str,
    invalid_value: object,
) -> None:
    engine = _model_engine()
    with Session(engine) as db:
        owner, stored, document = _source(db, attribute)
        draft = _draft(owner, stored, document)
        setattr(draft, attribute, invalid_value)
        db.add(draft)
        with pytest.raises(IntegrityError):
            db.commit()


def test_model_rejects_noncanonical_source_hash_even_when_stored_bytes_match() -> None:
    engine = _model_engine()
    with Session(engine) as db:
        owner, stored, document = _source(
            db,
            "uppercase-source",
            source_sha256="A" * 64,
        )
        db.add(_draft(owner, stored, document))
        with pytest.raises(IntegrityError):
            db.commit()


def test_model_rejects_wrong_document_file_and_exact_byte_bindings() -> None:
    engine = _model_engine()
    with Session(engine) as db:
        owner_a, stored_a, document_a = _source(db, "binding-a", source_sha256="a" * 64)
        _, stored_b, _ = _source(db, "binding-b", source_sha256="c" * 64)
        db.commit()

        wrong_document_file = _draft(owner_a, stored_b, document_a)
        db.add(wrong_document_file)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        wrong_bytes = _draft(owner_a, stored_a, document_a)
        wrong_bytes.source_sha256 = stored_b.sha256
        db.add(wrong_bytes)
        with pytest.raises(IntegrityError):
            db.commit()


def test_model_enforces_one_draft_per_owner_document_and_source() -> None:
    engine = _model_engine()
    with Session(engine, expire_on_commit=False) as db:
        owner, stored, document = _source(db, "unique")
        db.add(_draft(owner, stored, document))
        db.commit()

        db.add(_draft(owner, stored, document))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        second_owner = User(
            email="second-draft-owner@example.test",
            full_name="Second Draft Owner",
            password_hash="not-used-in-persistence-test",  # noqa: S106
            role="technical_reviewer",
            is_active=True,
        )
        db.add(second_owner)
        db.flush()
        db.add(_draft(second_owner, stored, document))
        db.commit()
        assert db.scalar(select(func.count()).select_from(TechnicalIntakeDraft)) == 2


def test_migration_0017_preserves_populated_0016_rows_and_matches_model(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-intake-drafts.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    initial = _run_migration(environment, "upgrade", "0016_parser_attestation_v2")
    assert initial.returncode == 0, initial.stderr

    engine = create_engine(database_url)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, created_at, updated_at, record_version, email, full_name, "
                "password_hash, role, is_active) VALUES "
                "('draft-migration-owner', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 7, "
                "'draft-migration@example.test', 'Draft Migration', 'unused', "
                "'technical_reviewer', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stored_files "
                "(id, created_at, updated_at, record_version, original_filename, "
                "media_type, storage_path, sha256, size_bytes, purpose, "
                "malware_scan_status, uploaded_by_id, immutable) VALUES "
                "('draft-migration-file', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 5, "
                "'source.pdf', 'application/pdf', 'technical/source.pdf', :sha, "
                ":size, 'technical_evidence', 'clean', 'draft-migration-owner', 1)"
            ),
            {"sha": "d" * 64, "size": SOURCE_SIZE},
        )
        connection.execute(
            text(
                "INSERT INTO technical_documents "
                "(id, created_at, updated_at, record_version, document_id, "
                "stored_file_id, document_type, title, status, extraction_status) "
                "VALUES ('draft-migration-document', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, 9, 'TECH-DRAFT-MIGRATION-001', "
                "'draft-migration-file', 'assessment', 'Migration source', "
                "'draft', 'not_started')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO library_releases "
                "(id, created_at, updated_at, record_version, library_type, "
                "version, status, active_publication_slot) VALUES "
                "('draft-migration-release', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "4, 'technical', 'legacy', 'active', 'technical')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO technical_variants "
                "(id, created_at, updated_at, record_version, variant_id, system_id, "
                "technical_document_id, search_eligibility, expert_review_required, "
                "status, source_json, release_id) VALUES "
                "('draft-migration-variant', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "6, 'LEGACY-VARIANT', 'LEGACY-SYSTEM', 'draft-migration-document', "
                "'eligible', 1, 'active', '{}', 'draft-migration-release')"
            )
        )
        legacy_document = connection.execute(
            text(
                "SELECT id, record_version, stored_file_id, status, extraction_status "
                "FROM technical_documents WHERE id='draft-migration-document'"
            )
        ).one()
        legacy_variant = connection.execute(
            text(
                "SELECT id, record_version, status, search_eligibility, release_id "
                "FROM technical_variants WHERE id='draft-migration-variant'"
            )
        ).one()

    upgraded = _run_migration(environment, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    inspector = inspect(engine)
    assert "technical_intake_drafts" in inspector.get_table_names()
    model_engine = _model_engine()
    assert _schema_signature(inspector, "technical_intake_drafts") == _schema_signature(
        inspect(model_engine),
        "technical_intake_drafts",
    )
    with engine.begin() as connection:
        assert connection.execute(
            text(
                "SELECT id, record_version, stored_file_id, status, extraction_status "
                "FROM technical_documents WHERE id='draft-migration-document'"
            )
        ).one() == legacy_document
        assert connection.execute(
            text(
                "SELECT id, record_version, status, search_eligibility, release_id "
                "FROM technical_variants WHERE id='draft-migration-variant'"
            )
        ).one() == legacy_variant
        connection.execute(
            text(
                "INSERT INTO technical_intake_drafts "
                "(id, created_at, updated_at, record_version, draft_schema, "
                "technical_document_id, source_stored_file_id, source_sha256, "
                "source_size_bytes, owner_id, status, payload_json, payload_sha256) "
                "VALUES ('11111111-1111-4111-8111-111111111111', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, 1, 'technical-intake-draft-v1', "
                "'draft-migration-document', 'draft-migration-file', :source_sha, "
                ":source_size, 'draft-migration-owner', 'draft', :payload, :payload_sha)"
            ),
            {
                "source_sha": "d" * 64,
                "source_size": SOURCE_SIZE,
                "payload": '{"fields":[]}',
                "payload_sha": "e" * 64,
            },
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            CLEAN_STACK_HEAD
        )

    rejected = _run_migration(
        environment,
        "downgrade",
        "0016_parser_attestation_v2",
    )
    assert rejected.returncode != 0
    assert "Technical intake Draft records are retained user data and cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            CLEAN_STACK_HEAD
        )
        assert connection.execute(
            text("SELECT COUNT(*) FROM technical_intake_drafts")
        ).scalar_one() == 1


def test_migration_0017_empty_downgrade_restores_exact_0016_schema(tmp_path: Path) -> None:
    database_path = tmp_path / "technical-intake-drafts-empty-downgrade.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    initial = _run_migration(environment, "upgrade", "0016_parser_attestation_v2")
    assert initial.returncode == 0, initial.stderr
    engine = create_engine(database_url)
    tables_before = frozenset(inspect(engine).get_table_names())

    upgraded = _run_migration(environment, "upgrade", "0017_technical_intake_drafts")
    assert upgraded.returncode == 0, upgraded.stderr
    assert "technical_intake_drafts" in inspect(engine).get_table_names()

    downgraded = _run_migration(
        environment,
        "downgrade",
        "0016_parser_attestation_v2",
    )
    assert downgraded.returncode == 0, downgraded.stderr
    assert frozenset(inspect(engine).get_table_names()) == tables_before
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0016_parser_attestation_v2"
        )


def test_migration_0018_adds_and_removes_containment_lookup_indexes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / 'shared-malware-containment-indexes.sqlite'
    database_url = f'sqlite:///{database_path.as_posix()}'
    environment = _migration_environment(tmp_path, database_url)
    initial = _run_migration(
        environment,
        'upgrade',
        '0017_technical_intake_drafts',
    )
    assert initial.returncode == 0, initial.stderr
    engine = create_engine(database_url)

    def index_columns(table_name: str) -> dict[str, tuple[str, ...]]:
        return {
            str(index['name']): tuple(index['column_names'])
            for index in inspect(engine).get_indexes(table_name)
        }

    assert 'ix_technical_documents_stored_file_id' not in index_columns(
        'technical_documents'
    )
    assert 'ix_intake_items_retained_sha_status_batch' not in index_columns(
        'technical_intake_batch_items'
    )

    upgraded = _run_migration(
        environment,
        'upgrade',
        '0018_shared_malware_containment',
    )
    assert upgraded.returncode == 0, upgraded.stderr
    assert index_columns('technical_documents')[
        'ix_technical_documents_stored_file_id'
    ] == ('stored_file_id',)
    assert index_columns('technical_intake_batch_items')[
        'ix_intake_items_retained_sha_status_batch'
    ] == ('retained_file_sha256', 'status', 'batch_id')

    downgraded = _run_migration(
        environment,
        'downgrade',
        '0017_technical_intake_drafts',
    )
    assert downgraded.returncode == 0, downgraded.stderr
    assert 'ix_technical_documents_stored_file_id' not in index_columns(
        'technical_documents'
    )
    assert 'ix_intake_items_retained_sha_status_batch' not in index_columns(
        'technical_intake_batch_items'
    )
    with engine.connect() as connection:
        assert connection.execute(
            text('SELECT version_num FROM alembic_version')
        ).scalar_one() == '0017_technical_intake_drafts'
