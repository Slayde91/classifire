from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy import table as sa_table
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[1]

_FK_ENFORCED_ALEMBIC_RUNNER = """
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.engine import Engine


@event.listens_for(Engine, 'connect')
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute('PRAGMA foreign_keys=ON')
    finally:
        cursor.close()


config = Config(os.environ['CLASSIFIRE_TEST_ALEMBIC_CONFIG'])
revision = os.environ['CLASSIFIRE_TEST_ALEMBIC_REVISION']
action = os.environ['CLASSIFIRE_TEST_ALEMBIC_ACTION']
if action == 'upgrade':
    command.upgrade(config, revision)
elif action == 'downgrade':
    command.downgrade(config, revision)
else:
    raise RuntimeError(f'Unsupported Alembic test action: {action}')
"""


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
    database_url: str,
    environment: dict[str, str],
    action: str,
    revision: str,
    *,
    enforce_sqlite_foreign_keys: bool = False,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        "-m",
        "alembic",
        "-c",
        str(ROOT / "alembic.ini"),
        action,
        revision,
    ]
    if enforce_sqlite_foreign_keys:
        environment = environment.copy()
        environment.update(
            {
                "CLASSIFIRE_TEST_ALEMBIC_ACTION": action,
                "CLASSIFIRE_TEST_ALEMBIC_CONFIG": str(ROOT / "alembic.ini"),
                "CLASSIFIRE_TEST_ALEMBIC_REVISION": revision,
            }
        )
        command = [sys.executable, "-c", _FK_ENFORCED_ALEMBIC_RUNNER]

    result = subprocess.run(  # noqa: S603
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if expect_success:
        assert result.returncode == 0, f"{database_url}: {result.stderr}"
    return result


def _upgrade(
    database_url: str,
    environment: dict[str, str],
    revision: str,
    *,
    enforce_sqlite_foreign_keys: bool = False,
) -> None:
    _run_migration(
        database_url,
        environment,
        "upgrade",
        revision,
        enforce_sqlite_foreign_keys=enforce_sqlite_foreign_keys,
    )


def _downgrade(
    database_url: str,
    environment: dict[str, str],
    revision: str,
    *,
    enforce_sqlite_foreign_keys: bool = False,
    expect_success: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run_migration(
        database_url,
        environment,
        "downgrade",
        revision,
        enforce_sqlite_foreign_keys=enforce_sqlite_foreign_keys,
        expect_success=expect_success,
    )


def test_fresh_database_upgrades_through_physical_foundation(tmp_path: Path) -> None:
    database_path = tmp_path / "fresh-physical-foundation.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "head")
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert {
        "alembic_version",
        "defects",
        "evidence_sources",
        "service_opening_links",
        "physical_model_locks",
        "agent_service_principals",
        "physical_model_admissions",
        "physical_model_submission_receipts",
        "technical_document_relationships",
        "visual_validation_receipts",
    }.issubset(inspector.get_table_names())
    assert "canonical_defect_id" in {column["name"] for column in inspector.get_columns("openings")}
    assert "primary_opening_legacy" in {
        column["name"] for column in inspector.get_columns("services")
    }
    visual_validation_columns = {
        column["name"]: column for column in inspector.get_columns("visual_validation_receipts")
    }
    assert not visual_validation_columns["receipt_id"]["nullable"]
    assert not visual_validation_columns["receipt_sha256"]["nullable"]
    assert not visual_validation_columns["evidence_family_review_sha256"]["nullable"]
    physical_lock_columns = {
        column["name"]: column for column in inspector.get_columns("physical_model_locks")
    }
    assert not physical_lock_columns["estimate_id"]["nullable"]
    active_lock_index = next(
        index
        for index in inspector.get_indexes("physical_model_locks")
        if index["name"] == "uq_physical_model_locks_active_estimate"
    )
    assert active_lock_index["unique"]
    release_columns = {
        column["name"]: column for column in inspector.get_columns("library_releases")
    }
    assert release_columns["active_publication_slot"]["nullable"]
    publication_slot_index = next(
        index
        for index in inspector.get_indexes("library_releases")
        if index["name"] == "uq_library_release_active_publication_slot"
    )
    assert publication_slot_index["unique"]
    relationship_columns = {
        column["name"]: column
        for column in inspector.get_columns("technical_document_relationships")
    }
    assert not relationship_columns["document_id"]["nullable"]
    assert not relationship_columns["related_document_id"]["nullable"]
    assert not relationship_columns["relationship_type"]["nullable"]
    assert not relationship_columns["reason"]["nullable"]
    assert relationship_columns["scope"]["nullable"]
    assert relationship_columns["effective_date"]["nullable"]
    assert not relationship_columns["created_by_id"]["nullable"]
    assert {
        "ix_technical_document_relationship_document_id",
        "ix_technical_document_relationship_related_id",
        "ix_technical_document_relationship_type",
        "ix_technical_document_relationship_created_by_id",
    }.issubset(
        {
            index["name"]
            for index in inspector.get_indexes("technical_document_relationships")
        }
    )
    assert {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(
            "technical_document_relationships"
        )
    } == {("document_id", "related_document_id", "relationship_type")}
    assert {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "technical_document_relationships"
        )
    } == {
        "ck_technical_document_relationship_not_self",
        "ck_technical_document_relationship_type",
    }
    relationship_foreign_keys = {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(
            "technical_document_relationships"
        )
    }
    assert {
        (("document_id",), "technical_documents", ("id",)),
        (("related_document_id",), "technical_documents", ("id",)),
        (("created_by_id",), "users", ("id",)),
    }.issubset(relationship_foreign_keys)
    technical_document_columns = {
        column["name"]: column for column in inspector.get_columns("technical_documents")
    }
    for column_name in (
        "declared_source_role",
        "sponsor_organisation",
        "artifact_provenance_status",
        "artifact_provenance_note",
        "evidence_scope",
        "evidence_limitations",
    ):
        assert technical_document_columns[column_name]["nullable"]
    assert {
        "ix_technical_documents_declared_source_role",
        "ix_technical_documents_artifact_provenance_status",
        "ix_technical_documents_evidence_scope",
    }.issubset(
        {
            index["name"]
            for index in inspector.get_indexes("technical_documents")
        }
    )
    assert {
        "ck_technical_document_declared_source_role",
        "ck_technical_document_artifact_provenance_status",
        "ck_technical_document_evidence_scope",
    }.issubset(
        {
            constraint["name"]
            for constraint in inspector.get_check_constraints("technical_documents")
        }
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0018_shared_malware_containment"
        )
        active_lock_index_sql = connection.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE type='index' AND name='uq_physical_model_locks_active_estimate'"
            )
        ).scalar_one()
        assert "WHERE invalidated_at IS NULL" in active_lock_index_sql


def test_fk_enforced_physical_migration_backfills_and_downgrades_safely(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "legacy-physical-foundation.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0002_estimate_release_pins")

    project_id = "10000000-0000-0000-0000-000000000001"
    estimate_id = "20000000-0000-0000-0000-000000000001"
    opening_id = "30000000-0000-0000-0000-000000000001"
    service_id = "40000000-0000-0000-0000-000000000001"
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, created_at, updated_at, record_version, "
                "reference, name, jurisdiction, status) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, 'PHYS-MIGRATION', "
                "'Physical migration', 'AU', 'active')"
            ),
            {"id": project_id},
        )
        connection.execute(
            text(
                "INSERT INTO estimates "
                "(id, created_at, updated_at, record_version, project_id, revision, "
                "reference, title, status, currency, tax_name, tax_rate, "
                "subtotal_ex_tax, tax_total, total_incl_tax) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :project_id, 1, "
                "'PHYS-MIGRATION-R1', 'Physical migration', 'draft', 'AUD', 'GST', 0.1, 0, 0, 0)"
            ),
            {"id": estimate_id, "project_id": project_id},
        )
        connection.execute(
            text(
                "INSERT INTO openings "
                "(id, created_at, updated_at, record_version, estimate_id, defect_id, "
                "opening_code, physical_model_status, technical_status) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :estimate_id, 'D-LEGACY', "
                "'O-001', 'draft', 'not_assessed')"
            ),
            {"id": opening_id, "estimate_id": estimate_id},
        )
        connection.execute(
            text(
                "INSERT INTO services "
                "(id, created_at, updated_at, record_version, opening_id, service_code, "
                "service_type, quantity, evidence_status) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :opening_id, "
                "'S-001', 'pipe', 1, 'provisional')"
            ),
            {"id": service_id, "opening_id": opening_id},
        )

    _upgrade(
        database_url,
        environment,
        "0006_physical_submission_receipts",
        enforce_sqlite_foreign_keys=True,
    )
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        canonical_defect_id = connection.execute(
            text("SELECT canonical_defect_id FROM openings WHERE id=:id"), {"id": opening_id}
        ).scalar_one()
        assert canonical_defect_id
        assert (
            connection.execute(
                text(
                    "SELECT external_defect_id FROM defects WHERE id=:id "
                    "AND estimate_id=:estimate_id"
                ),
                {"id": canonical_defect_id, "estimate_id": estimate_id},
            ).scalar_one()
            == "D-LEGACY"
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM service_opening_links "
                    "WHERE service_id=:service_id AND opening_id=:opening_id"
                ),
                {"service_id": service_id, "opening_id": opening_id},
            ).scalar_one()
            == 1
        )

    evidence_id = "50000000-0000-0000-0000-000000000001"
    lock_id = "60000000-0000-0000-0000-000000000001"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO evidence_sources "
                "(id, created_at, updated_at, record_version, estimate_id, evidence_type, "
                "evidence_class, status) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :estimate_id, "
                "'inspection_photo', 'observed', 'active')"
            ),
            {"id": evidence_id, "estimate_id": estimate_id},
        )
        connection.execute(
            text(
                "INSERT INTO physical_model_locks "
                "(id, created_at, updated_at, record_version, project_id, estimate_id, "
                "service_ids, opening_ids, validator_result, content_hash) "
                "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :project_id, "
                ":estimate_id, '[]', '[]', 'PASS', :content_hash)"
            ),
            {
                "id": lock_id,
                "project_id": project_id,
                "estimate_id": estimate_id,
                "content_hash": "b" * 64,
            },
        )

    rejected = _downgrade(
        database_url,
        environment,
        "0002_estimate_release_pins",
        enforce_sqlite_foreign_keys=True,
        expect_success=False,
    )
    assert rejected.returncode != 0
    rejection_text = rejected.stdout + rejected.stderr
    assert "Refusing to downgrade the physical-model foundation" in rejection_text
    for table in (
        "defects",
        "evidence_sources",
        "service_opening_links",
        "physical_model_locks",
    ):
        assert table in rejection_text

    inspector = inspect(engine)
    assert {
        "defects",
        "evidence_sources",
        "service_opening_links",
        "physical_model_locks",
    }.issubset(inspector.get_table_names())
    assert "canonical_defect_id" in {column["name"] for column in inspector.get_columns("openings")}
    assert "primary_opening_legacy" in {
        column["name"] for column in inspector.get_columns("services")
    }
    with engine.connect() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
        assert (
            connection.execute(
                text("SELECT defect_id FROM openings WHERE id=:id"), {"id": opening_id}
            ).scalar_one()
            == "D-LEGACY"
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM services WHERE id=:id"), {"id": service_id}
            ).scalar_one()
            == 1
        )
        for table in (
            "defects",
            "evidence_sources",
            "service_opening_links",
            "physical_model_locks",
        ):
            assert (
                connection.execute(select(func.count()).select_from(sa_table(table))).scalar_one()
                == 1
            )
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0006_physical_submission_receipts"
        )


def test_visual_validation_receipt_migration_refuses_evidence_loss(tmp_path: Path) -> None:
    database_path = tmp_path / "visual-validation-receipt.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0009_visual_validation_receipts")

    rejected = _downgrade(
        database_url,
        environment,
        "0008_retire_legacy_initial_submissions",
        expect_success=False,
    )

    assert rejected.returncode != 0
    assert "Visual-validation receipt evidence cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "visual_validation_receipts" in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0009_visual_validation_receipts"
        )


def test_governed_publication_slot_migration_cannot_be_downgraded(tmp_path: Path) -> None:
    database_path = tmp_path / "governed-publication-slot.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0010_release_publication_slot")

    rejected = _downgrade(
        database_url,
        environment,
        "0009_visual_validation_receipts",
        expect_success=False,
    )

    assert rejected.returncode != 0
    assert "Governed release publication serialization cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "active_publication_slot" in {
        column["name"] for column in inspector.get_columns("library_releases")
    }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0010_release_publication_slot"
        )


def test_technical_document_relationship_migration_cannot_be_downgraded(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-document-relationships.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0011_technical_document_relationships")

    rejected = _downgrade(
        database_url,
        environment,
        "0010_release_publication_slot",
        expect_success=False,
    )

    assert rejected.returncode != 0
    assert "Technical document provenance relationships cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    engine = create_engine(database_url)
    assert "technical_document_relationships" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0011_technical_document_relationships"
        )


def test_technical_source_registration_migration_preserves_populated_lineage(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-source-registration.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(
        database_url,
        environment,
        "0011_technical_document_relationships",
        enforce_sqlite_foreign_keys=True,
    )
    engine = create_engine(database_url)
    timestamp = "2026-08-27 10:11:12"
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, created_at, updated_at, record_version, email, full_name, "
                "password_hash, role, is_active) VALUES "
                "(:id, :created_at, :updated_at, 7, :email, :full_name, "
                ":password_hash, :role, 1)"
            ),
            {
                "id": "source-registration-user",
                "created_at": timestamp,
                "updated_at": timestamp,
                "email": "source-registration@example.test",
                "full_name": "Source Registration",
                "password_hash": "not-used",
                "role": "technical_reviewer",
            },
        )
        for suffix, digest in (("root", "a" * 64), ("related", "b" * 64)):
            connection.execute(
                text(
                    "INSERT INTO stored_files "
                    "(id, created_at, updated_at, record_version, original_filename, "
                    "storage_path, sha256, size_bytes, purpose, malware_scan_status, "
                    "immutable) VALUES "
                    "(:id, :created_at, :updated_at, 3, :filename, :storage_path, "
                    ":sha256, 123, 'technical_evidence', 'clean', 1)"
                ),
                {
                    "id": f"stored-{suffix}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "filename": f"{suffix}.pdf",
                    "storage_path": f"C:/governed/{suffix}.pdf",
                    "sha256": digest,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO technical_documents "
                    "(id, created_at, updated_at, record_version, document_id, "
                    "stored_file_id, document_type, title, status, extraction_status) "
                    "VALUES (:id, :created_at, :updated_at, 5, :document_id, "
                    ":stored_file_id, 'fire_assessment', :title, 'draft', 'not_started')"
                ),
                {
                    "id": f"document-{suffix}",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "document_id": f"DOCUMENT-{suffix.upper()}",
                    "stored_file_id": f"stored-{suffix}",
                    "title": f"Document {suffix}",
                },
            )
        connection.execute(
            text(
                "INSERT INTO technical_document_relationships "
                "(id, created_at, updated_at, record_version, document_id, "
                "related_document_id, relationship_type, reason, scope, "
                "effective_date, created_by_id) VALUES "
                "('relationship-existing', :created_at, :updated_at, 9, "
                "'document-root', 'document-related', 'assessment_of', "
                "'Existing governed relationship', 'Whole source', "
                "'2026-08-27', 'source-registration-user')"
            ),
            {"created_at": timestamp, "updated_at": timestamp},
        )

    before = inspect(engine)
    before_document_indexes = {
        index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
        for index in before.get_indexes("technical_documents")
    }
    before_relationship_indexes = {
        index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
        for index in before.get_indexes("technical_document_relationships")
    }
    with engine.connect() as connection:
        document_before = connection.execute(
            text(
                "SELECT id, created_at, updated_at, record_version, document_id, "
                "stored_file_id, title FROM technical_documents "
                "WHERE id='document-root'"
            )
        ).mappings().one()
        relationship_before = connection.execute(
            text(
                "SELECT id, created_at, updated_at, record_version, document_id, "
                "related_document_id, relationship_type, reason, scope, "
                "effective_date, created_by_id "
                "FROM technical_document_relationships "
                "WHERE id='relationship-existing'"
            )
        ).mappings().one()

    _upgrade(
        database_url,
        environment,
        "head",
        enforce_sqlite_foreign_keys=True,
    )

    after = inspect(engine)
    after_document_indexes = {
        index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
        for index in after.get_indexes("technical_documents")
    }
    after_relationship_indexes = {
        index["name"]: (tuple(index["column_names"]), bool(index["unique"]))
        for index in after.get_indexes("technical_document_relationships")
    }
    assert before_document_indexes.items() <= after_document_indexes.items()
    assert before_relationship_indexes == after_relationship_indexes
    assert {
        "ix_technical_documents_declared_source_role",
        "ix_technical_documents_artifact_provenance_status",
        "ix_technical_documents_evidence_scope",
    }.issubset(after_document_indexes)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT id, created_at, updated_at, record_version, document_id, "
                "stored_file_id, title FROM technical_documents "
                "WHERE id='document-root'"
            )
        ).mappings().one() == document_before
        assert connection.execute(
            text(
                "SELECT id, created_at, updated_at, record_version, document_id, "
                "related_document_id, relationship_type, reason, scope, "
                "effective_date, created_by_id "
                "FROM technical_document_relationships "
                "WHERE id='relationship-existing'"
            )
        ).mappings().one() == relationship_before
        registration = connection.execute(
            text(
                "SELECT declared_source_role, sponsor_organisation, "
                "artifact_provenance_status, artifact_provenance_note, "
                "evidence_scope, evidence_limitations "
                "FROM technical_documents WHERE id='document-root'"
            )
        ).one()
        assert registration == (None, None, None, None, None, None)
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE technical_documents SET "
                "declared_source_role='regulatory_summary', "
                "sponsor_organisation='Example sponsor', "
                "artifact_provenance_status='issuer_copy', "
                "artifact_provenance_note='Supplied issuer copy', "
                "evidence_scope='summary_only', "
                "evidence_limitations='Main assessment remains separately governed' "
                "WHERE id='document-root'"
            )
        )
        connection.execute(
            text(
                "INSERT INTO technical_document_relationships "
                "(id, created_at, updated_at, record_version, document_id, "
                "related_document_id, relationship_type, reason, created_by_id) "
                "VALUES ('relationship-summary', :created_at, :updated_at, 1, "
                "'document-root', 'document-related', 'summary_of', "
                "'The retained source declares this summary relationship', "
                "'source-registration-user')"
            ),
            {"created_at": timestamp, "updated_at": timestamp},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE technical_documents "
                    "SET declared_source_role='unsupported_role' "
                    "WHERE id='document-root'"
                )
            )
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE technical_document_relationships "
                    "SET relationship_type='unsupported_relationship' "
                    "WHERE id='relationship-existing'"
                )
            )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0018_shared_malware_containment"
        )
        assert connection.execute(
            text(
                "SELECT relationship_type FROM technical_document_relationships "
                "WHERE id='relationship-summary'"
            )
        ).scalar_one() == "summary_of"


def test_technical_source_registration_migration_cannot_be_downgraded(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-source-registration-no-downgrade.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0012_technical_source_registration")

    rejected = _downgrade(
        database_url,
        environment,
        "0011_technical_document_relationships",
        expect_success=False,
    )

    assert rejected.returncode != 0
    assert "Technical source registration cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    with create_engine(database_url).connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0012_technical_source_registration"
        )
