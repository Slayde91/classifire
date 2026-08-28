from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, inspect, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeBatch,
    TechnicalIntakeBatchItem,
    User,
)

ROOT = Path(__file__).resolve().parents[1]
NIL_UUID = "00000000-0000-0000-0000-000000000000"
V1_UUID = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
NON_HEX_UUID = "zzzzzzzz-zzzz-4zzz-8zzz-zzzzzzzzzzzz"
UPPERCASE_UUID = "ABCDEFAB-CDEF-4ABC-8ABC-ABCDEFABCDEF"
INVALID_UUID4_VALUES = (NIL_UUID, V1_UUID, NON_HEX_UUID, UPPERCASE_UUID)
V4_ATTEMPT_UUID = "33333333-3333-4333-a333-333333333333"
INVALID_SHA256_VALUES = ("A" * 64, "g" * 64, ("a" * 63) + "-")


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


def _user() -> User:
    return User(
        email="batch-owner@example.test",
        full_name="Batch Owner",
        password_hash="not-used-in-persistence-test",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )


def _batch(owner: User) -> TechnicalIntakeBatch:
    return TechnicalIntakeBatch(
        client_request_id="11111111-1111-4111-8111-111111111111",
        created_by_id=owner.id,
        expected_item_count=1,
        manifest_sha256="a" * 64,
    )


def _item(batch: TechnicalIntakeBatch) -> TechnicalIntakeBatchItem:
    return TechnicalIntakeBatchItem(
        batch_id=batch.id,
        client_item_id="22222222-2222-4222-8222-222222222222",
        ordinal=1,
        original_filename="assessment.pdf",
        declared_size_bytes=123,
        expected_sha256="b" * 64,
        declared_document_id="DOC-BATCH-001",
        registration_snapshot={"document_id": "DOC-BATCH-001"},
        registration_sha256="c" * 64,
    )


def _set_terminal_outcome(
    item: TechnicalIntakeBatchItem,
    *,
    status: str,
    outcome_code: str,
    retryable: bool,
) -> None:
    item.status = status
    item.attempt_count = 1
    item.outcome_code = outcome_code
    item.outcome_retryable = retryable
    item.last_outcome_at = datetime.now(UTC)
    item.receipt_schema = "technical-intake-item-receipt-v1"
    item.receipt_json = {"code": outcome_code}
    item.receipt_sha256 = "d" * 64


def _retained_evidence(
    db: Session,
    owner: User,
) -> tuple[StoredFile, TechnicalDocument]:
    stored = StoredFile(
        original_filename="assessment.pdf",
        media_type="application/pdf",
        storage_path="C:/governed/assessment.pdf",
        sha256="e" * 64,
        size_bytes=123,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=owner.id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="DOC-BATCH-001",
        stored_file_id=stored.id,
        document_type="fire_assessment",
        title="Assessment",
        status="draft",
        extraction_status="awaiting_safe_extraction",
    )
    db.add(document)
    db.flush()
    return stored, document


def test_model_schema_supports_one_concurrency_safe_claim() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        db.add(item)
        db.commit()

        claim_token = str(uuid4())
        claim_time = datetime.now(UTC)
        claimed = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "pending",
                TechnicalIntakeBatchItem.record_version == 1,
            )
            .values(
                status="processing",
                attempt_token=claim_token,
                attempt_started_at=claim_time,
                attempt_count=TechnicalIntakeBatchItem.attempt_count + 1,
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
        )
        db.commit()
        assert claimed.rowcount == 1

        stale_claim = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "pending",
                TechnicalIntakeBatchItem.record_version == 1,
            )
            .values(status="processing")
        )
        db.commit()
        assert stale_claim.rowcount == 0

        with pytest.raises(IntegrityError):
            db.execute(
                update(TechnicalIntakeBatchItem)
                .where(TechnicalIntakeBatchItem.id == item.id)
                .values(
                    status="rejected",
                    outcome_code="MALWARE_SCANNER_UNAVAILABLE",
                    outcome_retryable=True,
                    last_outcome_at=claim_time,
                    receipt_schema="technical-intake-item-receipt-v1",
                    receipt_json={"code": "MALWARE_SCANNER_UNAVAILABLE"},
                    receipt_sha256="d" * 64,
                )
            )
            db.commit()
        db.rollback()

        resolved = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "processing",
                TechnicalIntakeBatchItem.attempt_token == claim_token,
            )
            .values(
                status="rejected",
                attempt_token=None,
                attempt_started_at=None,
                outcome_code="MALWARE_SCANNER_UNAVAILABLE",
                outcome_retryable=True,
                last_outcome_at=claim_time,
                receipt_schema="technical-intake-item-receipt-v1",
                receipt_json={"code": "MALWARE_SCANNER_UNAVAILABLE"},
                receipt_sha256="d" * 64,
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
        )
        db.commit()
        assert resolved.rowcount == 1
        persisted = db.scalar(
            select(TechnicalIntakeBatchItem).where(TechnicalIntakeBatchItem.id == item.id)
        )
        assert persisted is not None
        assert persisted.status == "rejected"
        assert persisted.attempt_token is None
        assert persisted.attempt_count == 1

        retry_token = str(uuid4())
        retry_claim = db.execute(
            update(TechnicalIntakeBatchItem)
            .where(
                TechnicalIntakeBatchItem.id == item.id,
                TechnicalIntakeBatchItem.status == "rejected",
                TechnicalIntakeBatchItem.outcome_retryable.is_(True),
            )
            .values(
                status="processing",
                attempt_token=retry_token,
                attempt_started_at=datetime.now(UTC),
                attempt_count=TechnicalIntakeBatchItem.attempt_count + 1,
                record_version=TechnicalIntakeBatchItem.record_version + 1,
            )
        )
        db.commit()
        assert retry_claim.rowcount == 1
        retried = db.get(TechnicalIntakeBatchItem, item.id)
        assert retried is not None
        assert retried.status == "processing"
        assert retried.attempt_token == retry_token
        assert retried.attempt_count == 2
        assert retried.outcome_code == "MALWARE_SCANNER_UNAVAILABLE"
        assert retried.receipt_sha256 == "d" * 64


def test_model_constraints_reject_unbound_or_ambiguous_manifest_rows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.commit()
        invalid = _item(batch)
        invalid.expected_sha256 = "B" * 64
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        empty = _item(batch)
        empty.declared_size_bytes = 0
        db.add(empty)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        duplicate_request = _batch(owner)
        db.add(duplicate_request)
        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    "field_name",
    ["batch_id", "client_request_id", "item_id", "client_item_id", "attempt_token"],
)
@pytest.mark.parametrize("invalid_uuid", INVALID_UUID4_VALUES)
def test_uuid_v4_constraints_reject_noncanonical_identifiers(
    field_name: str,
    invalid_uuid: str,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        if field_name == "batch_id":
            batch.id = invalid_uuid
        elif field_name == "client_request_id":
            batch.client_request_id = invalid_uuid
        db.add(batch)

        if field_name not in {"batch_id", "client_request_id"}:
            db.flush()
            item = _item(batch)
            if field_name == "item_id":
                item.id = invalid_uuid
            elif field_name == "client_item_id":
                item.client_item_id = invalid_uuid
            else:
                item.status = "processing"
                item.attempt_count = 1
                item.attempt_token = invalid_uuid
                item.attempt_started_at = datetime.now(UTC)
            db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()


def test_uuid_v4_constraints_accept_request_item_and_attempt_identifiers() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        item.status = "processing"
        item.attempt_count = 1
        item.attempt_token = V4_ATTEMPT_UUID
        item.attempt_started_at = datetime.now(UTC)
        db.add(item)
        db.commit()

        assert batch.client_request_id == "11111111-1111-4111-8111-111111111111"
        assert UUID(batch.id).version == 4
        assert item.client_item_id == "22222222-2222-4222-8222-222222222222"
        assert UUID(item.id).version == 4
        assert item.attempt_token == V4_ATTEMPT_UUID


@pytest.mark.parametrize(
    "field_name",
    ["manifest_sha256", "registration_sha256", "expected_sha256", "receipt_sha256"],
)
@pytest.mark.parametrize("invalid_sha256", INVALID_SHA256_VALUES)
def test_sha256_constraints_reject_noncanonical_or_nonhex_digests(
    field_name: str,
    invalid_sha256: str,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        if field_name == "manifest_sha256":
            batch.manifest_sha256 = invalid_sha256
        db.add(batch)
        if field_name != "manifest_sha256":
            db.flush()
            item = _item(batch)
            if field_name == "receipt_sha256":
                _set_terminal_outcome(
                    item,
                    status="rejected",
                    outcome_code="MALWARE_DETECTED",
                    retryable=False,
                )
                item.receipt_sha256 = invalid_sha256
            else:
                setattr(item, field_name, invalid_sha256)
            db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    "filename",
    ["nested/report.pdf", "C:report.pdf", "report?.pdf", "report.exe"],
)
def test_filename_constraint_rejects_noncanonical_values(filename: str) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        item.original_filename = filename
        db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    ("status", "outcome_retryable", "receipt_schema"),
    [
        ("rejected", True, None),
        ("processing", None, "technical-intake-item-receipt-v1"),
        ("processing", True, None),
    ],
)
def test_outcome_constraint_rejects_incomplete_terminal_or_retry_receipts(
    status: str,
    outcome_retryable: bool | None,
    receipt_schema: str | None,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        item.status = status
        item.attempt_count = 1
        if status == "processing":
            item.attempt_token = str(uuid4())
            item.attempt_started_at = datetime.now(UTC)
        item.outcome_code = "MALWARE_SCANNER_UNAVAILABLE"
        item.outcome_retryable = outcome_retryable
        item.last_outcome_at = datetime.now(UTC)
        item.receipt_schema = receipt_schema
        item.receipt_json = {"code": "MALWARE_SCANNER_UNAVAILABLE"}
        item.receipt_sha256 = "d" * 64
        db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    (
        "status",
        "invalid_code",
        "invalid_retryable",
        "valid_code",
        "valid_retryable",
    ),
    [
        (
            "rejected",
            "ACCEPTED",
            True,
            "MALWARE_SCANNER_UNAVAILABLE",
            True,
        ),
        (
            "needs_attention",
            "OPERATOR_REVIEW_REQUIRED",
            True,
            "OPERATOR_REVIEW_REQUIRED",
            False,
        ),
    ],
)
def test_terminal_semantics_reject_invalid_and_accept_valid_rows(
    status: str,
    invalid_code: str,
    invalid_retryable: bool,
    valid_code: str,
    valid_retryable: bool,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.commit()

        invalid = _item(batch)
        _set_terminal_outcome(
            invalid,
            status=status,
            outcome_code=invalid_code,
            retryable=invalid_retryable,
        )
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        valid = _item(batch)
        _set_terminal_outcome(
            valid,
            status=status,
            outcome_code=valid_code,
            retryable=valid_retryable,
        )
        db.add(valid)
        db.commit()
        assert valid.status == status
        assert valid.outcome_code == valid_code
        assert valid.outcome_retryable is valid_retryable


def test_accepted_item_must_bind_the_manifest_expected_hash() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        stored = StoredFile(
            original_filename="assessment.pdf",
            media_type="application/pdf",
            storage_path="C:/governed/assessment.pdf",
            sha256="e" * 64,
            size_bytes=123,
            purpose="technical_evidence",
            malware_scan_status="clean",
            uploaded_by_id=owner.id,
            immutable=True,
        )
        db.add(stored)
        db.flush()
        document = TechnicalDocument(
            document_id="DOC-BATCH-001",
            stored_file_id=stored.id,
            document_type="fire_assessment",
            title="Assessment",
            status="draft",
            extraction_status="awaiting_safe_extraction",
        )
        db.add(document)
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        db.commit()

        item = _item(batch)
        item.status = "accepted"
        item.attempt_count = 1
        item.technical_document_id = document.id
        item.retained_file_sha256 = stored.sha256
        item.outcome_code = "ACCEPTED"
        item.outcome_retryable = False
        item.last_outcome_at = datetime.now(UTC)
        item.receipt_schema = "technical-intake-item-receipt-v1"
        item.receipt_json = {"code": "ACCEPTED", "file_sha256": stored.sha256}
        item.receipt_sha256 = "f" * 64
        db.add(item)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        item = _item(batch)
        item.expected_sha256 = stored.sha256
        item.status = "accepted"
        item.attempt_count = 1
        item.technical_document_id = document.id
        item.retained_file_sha256 = stored.sha256
        item.outcome_code = "UPLOAD_ACCEPTED"
        item.outcome_retryable = False
        item.last_outcome_at = datetime.now(UTC)
        item.receipt_schema = "technical-intake-item-receipt-v1"
        item.receipt_json = {"code": "UPLOAD_ACCEPTED", "file_sha256": stored.sha256}
        item.receipt_sha256 = "f" * 64
        db.add(item)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        item = _item(batch)
        item.expected_sha256 = stored.sha256
        item.status = "accepted"
        item.attempt_count = 1
        item.technical_document_id = document.id
        item.retained_file_sha256 = stored.sha256
        item.outcome_code = "ACCEPTED"
        item.outcome_retryable = False
        item.last_outcome_at = datetime.now(UTC)
        item.receipt_schema = "technical-intake-item-receipt-v1"
        item.receipt_json = {"code": "ACCEPTED", "file_sha256": stored.sha256}
        item.receipt_sha256 = "f" * 64
        db.add(item)
        db.commit()
        assert item.technical_document_id == document.id


@pytest.mark.parametrize(
    "outcome_code",
    [
        "MALWARE_DETECTED",
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "UPLOAD_CONTENT_SIGNATURE_INVALID",
        "UPLOAD_STAGED_BYTES_CHANGED",
    ],
)
def test_integrity_attention_item_can_retain_accepted_evidence_linkage(
    outcome_code: str,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        stored, document = _retained_evidence(db, owner)
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        item.expected_sha256 = stored.sha256
        _set_terminal_outcome(
            item,
            status="needs_attention",
            outcome_code=outcome_code,
            retryable=False,
        )
        item.technical_document_id = document.id
        item.retained_file_sha256 = stored.sha256
        db.add(item)

        db.commit()

        assert item.status == "needs_attention"
        assert item.technical_document_id == document.id
        assert item.retained_file_sha256 == item.expected_sha256


@pytest.mark.parametrize(
    ("outcome_code", "document_linked", "retained_sha256"),
    [
        ("OPERATOR_REVIEW_REQUIRED", True, "expected"),
        ("STORED_FILE_CONTENT_COLLISION", False, "expected"),
        ("UPLOAD_STAGED_BYTES_CHANGED", True, "wrong"),
    ],
)
def test_attention_item_rejects_unauthorised_or_partial_evidence_linkage(
    outcome_code: str,
    document_linked: bool,
    retained_sha256: str,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        stored, document = _retained_evidence(db, owner)
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        item.expected_sha256 = stored.sha256
        _set_terminal_outcome(
            item,
            status="needs_attention",
            outcome_code=outcome_code,
            retryable=False,
        )
        item.technical_document_id = document.id if document_linked else None
        item.retained_file_sha256 = (
            stored.sha256 if retained_sha256 == "expected" else "f" * 64
        )
        db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()


@pytest.mark.parametrize(
    "outcome_code",
    ["STORED_FILE_CONTENT_COLLISION", "UPLOAD_STAGED_BYTES_CHANGED"],
)
def test_preaccept_integrity_attention_keeps_evidence_links_null(
    outcome_code: str,
) -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        owner = _user()
        db.add(owner)
        db.flush()
        batch = _batch(owner)
        db.add(batch)
        db.flush()
        item = _item(batch)
        _set_terminal_outcome(
            item,
            status="needs_attention",
            outcome_code=outcome_code,
            retryable=False,
        )
        db.add(item)

        db.commit()

        assert item.technical_document_id is None
        assert item.retained_file_sha256 is None


def test_model_tables_compile_for_postgresql() -> None:
    dialect = postgresql.dialect()
    batch_ddl = str(CreateTable(TechnicalIntakeBatch.__table__).compile(dialect=dialect))
    item_ddl = str(CreateTable(TechnicalIntakeBatchItem.__table__).compile(dialect=dialect))

    assert "technical_intake_batches" in batch_ddl
    assert "technical_intake_batch_items" in item_ddl
    assert "substr(id, 15, 1) = '4'" in batch_ddl
    assert "substr(id, 15, 1) = '4'" in item_ddl
    assert "substr(client_request_id, 15, 1) = '4'" in batch_ddl
    assert "substr(client_request_id, 20, 1) IN ('8', '9', 'a', 'b')" in batch_ddl
    assert "client_request_id = lower(client_request_id)" in batch_ddl
    assert "length(replace(client_request_id, '-', '')) = 32" in batch_ddl
    assert "attempt_token" in item_ddl
    assert "substr(client_item_id, 15, 1) = '4'" in item_ddl
    assert "client_item_id = lower(client_item_id)" in item_ddl
    assert "length(replace(client_item_id, '-', '')) = 32" in item_ddl
    assert "substr(attempt_token, 15, 1) = '4'" in item_ddl
    assert "attempt_token = lower(attempt_token)" in item_ddl
    assert "length(replace(attempt_token, '-', '')) = 32" in item_ddl
    assert "replace(original_filename, '?', '') = original_filename" in item_ddl
    assert "lower(original_filename) LIKE '_%%.pdf'" in item_ddl
    assert "expected_sha256" in item_ddl
    for sha256_column in (
        "manifest_sha256",
        "registration_sha256",
        "expected_sha256",
        "retained_file_sha256",
        "receipt_sha256",
    ):
        ddl = batch_ddl if sha256_column == "manifest_sha256" else item_ddl
        assert f"{sha256_column} = lower({sha256_column})" in ddl
        assert f"replace({sha256_column}, '0', '')" in ddl
    assert "outcome_retryable = false" in item_ddl
    assert "outcome_code = 'ACCEPTED'" in item_ddl
    assert "STORED_FILE_CONTENT_COLLISION" in item_ddl
    assert "STORED_FILE_CONTEXT_CONFLICT" in item_ddl
    assert "MALWARE_DETECTED" in item_ddl
    assert "UPLOAD_CONTENT_SIGNATURE_INVALID" in item_ddl
    assert "UPLOAD_STAGED_BYTES_CHANGED" in item_ddl
    assert "outcome_code <> 'ACCEPTED'" in item_ddl
    assert "status <> 'needs_attention'" in item_ddl
    assert item_ddl.count("outcome_retryable IS NOT NULL") >= 2
    assert item_ddl.count("receipt_schema IS NOT NULL") >= 2


def test_migration_0013_preserves_0012_rows_and_adds_constrained_ledger(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-intake-batches.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    initial = _run_migration(environment, "upgrade", "0012_technical_source_registration")
    assert initial.returncode == 0, initial.stderr

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, created_at, updated_at, record_version, email, full_name, "
                "password_hash, role, is_active) VALUES "
                "('batch-migration-user', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 3, "
                "'batch-migration@example.test', 'Batch Migration', 'not-used', "
                "'technical_reviewer', 1)"
            )
        )

    upgraded = _run_migration(
        environment,
        "upgrade",
        "0013_technical_intake_batches",
    )
    assert upgraded.returncode == 0, upgraded.stderr
    inspector = inspect(engine)
    assert {
        "technical_intake_batches",
        "technical_intake_batch_items",
    }.issubset(inspector.get_table_names())
    assert {
        "attempt_count",
        "attempt_started_at",
        "attempt_token",
        "expected_sha256",
        "registration_snapshot",
        "receipt_json",
    }.issubset(
        {column["name"] for column in inspector.get_columns("technical_intake_batch_items")}
    )
    assert {
        "ix_technical_intake_batch_items_batch_status_ordinal",
        "ix_technical_intake_batch_items_status",
    }.issubset(
        {index["name"] for index in inspector.get_indexes("technical_intake_batch_items")}
    )
    assert {
        "ck_technical_intake_batch_item_acceptance",
        "ck_technical_intake_batch_item_id",
        "ck_technical_intake_batch_item_attempt_token",
        "ck_technical_intake_batch_item_claim",
        "ck_technical_intake_batch_item_client_id",
        "ck_technical_intake_batch_item_expected_sha256",
        "ck_technical_intake_batch_item_outcome",
        "ck_technical_intake_batch_item_terminal_semantics",
    }.issubset(
        {
            constraint["name"]
            for constraint in inspector.get_check_constraints(
                "technical_intake_batch_items"
            )
        }
    )
    outcome_constraint = next(
        constraint
        for constraint in inspector.get_check_constraints(
            "technical_intake_batch_items"
        )
        if constraint["name"] == "ck_technical_intake_batch_item_outcome"
    )
    outcome_sql = " ".join(str(outcome_constraint["sqltext"]).lower().split())
    assert outcome_sql.count("outcome_retryable is not null") >= 2
    assert outcome_sql.count("receipt_schema is not null") >= 2
    acceptance_constraint = next(
        constraint
        for constraint in inspector.get_check_constraints(
            "technical_intake_batch_items"
        )
        if constraint["name"] == "ck_technical_intake_batch_item_acceptance"
    )
    acceptance_sql = " ".join(
        str(acceptance_constraint["sqltext"]).lower().split()
    )
    for integrity_code in (
        "malware_detected",
        "stored_file_content_collision",
        "stored_file_context_conflict",
        "upload_content_signature_invalid",
        "upload_staged_bytes_changed",
    ):
        assert integrity_code in acceptance_sql
    terminal_constraint = next(
        constraint
        for constraint in inspector.get_check_constraints(
            "technical_intake_batch_items"
        )
        if constraint["name"]
        == "ck_technical_intake_batch_item_terminal_semantics"
    )
    terminal_sql = " ".join(str(terminal_constraint["sqltext"]).lower().split())
    assert "outcome_code = 'accepted'" in terminal_sql
    assert "outcome_code <> 'accepted'" in terminal_sql
    assert "status <> 'needs_attention' or outcome_retryable = false" in terminal_sql
    request_id_constraint = next(
        constraint
        for constraint in inspector.get_check_constraints("technical_intake_batches")
        if constraint["name"] == "ck_technical_intake_batch_client_request_id"
    )
    request_id_sql = " ".join(
        str(request_id_constraint["sqltext"]).lower().split()
    )
    assert "substr(client_request_id, 15, 1) = '4'" in request_id_sql
    assert (
        "substr(client_request_id, 20, 1) in ('8', '9', 'a', 'b')"
        in request_id_sql
    )
    assert "client_request_id = lower(client_request_id)" in request_id_sql
    assert "length(replace(client_request_id, '-', '')) = 32" in request_id_sql
    batch_id_constraint = next(
        constraint
        for constraint in inspector.get_check_constraints("technical_intake_batches")
        if constraint["name"] == "ck_technical_intake_batch_id"
    )
    batch_id_sql = " ".join(str(batch_id_constraint["sqltext"]).lower().split())
    assert "substr(id, 15, 1) = '4'" in batch_id_sql
    assert "substr(id, 20, 1) in ('8', '9', 'a', 'b')" in batch_id_sql
    assert "id = lower(id)" in batch_id_sql
    for constraint_name, column_name in (
        ("ck_technical_intake_batch_item_id", "id"),
        ("ck_technical_intake_batch_item_client_id", "client_item_id"),
        ("ck_technical_intake_batch_item_attempt_token", "attempt_token"),
    ):
        uuid_constraint = next(
            constraint
            for constraint in inspector.get_check_constraints(
                "technical_intake_batch_items"
            )
            if constraint["name"] == constraint_name
        )
        uuid_sql = " ".join(str(uuid_constraint["sqltext"]).lower().split())
        assert f"substr({column_name}, 15, 1) = '4'" in uuid_sql
        assert (
            f"substr({column_name}, 20, 1) in ('8', '9', 'a', 'b')"
            in uuid_sql
        )
        assert f"{column_name} = lower({column_name})" in uuid_sql
        assert f"length(replace({column_name}, '-', '')) = 32" in uuid_sql
    with Session(engine, expire_on_commit=False) as db:
        owner = db.get(User, "batch-migration-user")
        assert owner is not None
        for invalid_uuid in INVALID_UUID4_VALUES:
            invalid_batch = _batch(owner)
            invalid_batch.client_request_id = invalid_uuid
            db.add(invalid_batch)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        for invalid_uuid in INVALID_UUID4_VALUES:
            invalid_batch = _batch(owner)
            invalid_batch.id = invalid_uuid
            db.add(invalid_batch)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        batch = _batch(owner)
        db.add(batch)
        db.commit()

        for invalid_uuid in INVALID_UUID4_VALUES:
            invalid_item = _item(batch)
            invalid_item.client_item_id = invalid_uuid
            db.add(invalid_item)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        for invalid_uuid in INVALID_UUID4_VALUES:
            invalid_item = _item(batch)
            invalid_item.id = invalid_uuid
            db.add(invalid_item)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        for invalid_sha256 in INVALID_SHA256_VALUES:
            invalid_batch = _batch(owner)
            invalid_batch.manifest_sha256 = invalid_sha256
            db.add(invalid_batch)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        for invalid_uuid in INVALID_UUID4_VALUES:
            invalid_claim = _item(batch)
            invalid_claim.status = "processing"
            invalid_claim.attempt_count = 1
            invalid_claim.attempt_token = invalid_uuid
            invalid_claim.attempt_started_at = datetime.now(UTC)
            db.add(invalid_claim)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        invalid = _item(batch)
        _set_terminal_outcome(
            invalid,
            status="needs_attention",
            outcome_code="OPERATOR_REVIEW_REQUIRED",
            retryable=True,
        )
        db.add(invalid)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

        valid = _item(batch)
        _set_terminal_outcome(
            valid,
            status="needs_attention",
            outcome_code="OPERATOR_REVIEW_REQUIRED",
            retryable=False,
        )
        db.add(valid)
        db.commit()
        assert valid.outcome_retryable is False

        claim_batch = _batch(owner)
        claim_batch.client_request_id = "44444444-4444-4444-8444-444444444444"
        db.add(claim_batch)
        db.flush()
        valid_claim = _item(claim_batch)
        valid_claim.status = "processing"
        valid_claim.attempt_count = 1
        valid_claim.attempt_token = V4_ATTEMPT_UUID
        valid_claim.attempt_started_at = datetime.now(UTC)
        db.add(valid_claim)
        db.commit()
        assert valid_claim.attempt_token == V4_ATTEMPT_UUID
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0013_technical_intake_batches"
        )
        assert connection.execute(
            text("SELECT record_version FROM users WHERE id='batch-migration-user'")
        ).scalar_one() == 3
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []


def test_migration_0013_cannot_discard_batch_receipt_storage(tmp_path: Path) -> None:
    database_path = tmp_path / "technical-intake-batches-no-downgrade.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    upgraded = _run_migration(
        environment,
        "upgrade",
        "0013_technical_intake_batches",
    )
    assert upgraded.returncode == 0, upgraded.stderr

    rejected = _run_migration(
        environment,
        "downgrade",
        "0012_technical_source_registration",
    )
    assert rejected.returncode != 0
    assert "Technical intake batch ledger cannot be downgraded" in (
        rejected.stdout + rejected.stderr
    )
    with create_engine(database_url).connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0013_technical_intake_batches"
        )
