# ruff: noqa: S106
from __future__ import annotations

import copy
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine, event, func, select, text, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.sql.dml import Update

from classifire import models, physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeBatch,
    TechnicalIntakeBatchItem,
    User,
)
from classifire.services.technical_intake import (
    TechnicalIntakeError as TechnicalUploadError,
)
from classifire.services.technical_intake_batch import (
    TECHNICAL_INTAKE_BATCH_SCHEMA,
    TECHNICAL_INTAKE_CLAIM_TTL,
    TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA,
    TechnicalIntakeBatchError,
    canonical_json_sha256,
    claim_technical_intake_batch_item,
    create_technical_intake_batch,
    get_owned_technical_intake_batch,
    normalize_technical_intake_registration,
    refresh_technical_intake_batch_status,
    serialize_technical_intake_batch,
)

_REQUEST_A = "11111111-1111-4111-8111-111111111111"
_REQUEST_B = "11111111-1111-4111-8111-111111111112"
_ITEM_A = "22222222-2222-4222-8222-222222222221"
_ITEM_B = "22222222-2222-4222-8222-222222222222"
_ITEM_C = "22222222-2222-4222-8222-222222222223"


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        max_upload_mb=2,
    )


def _user(db: Session, email: str) -> User:
    actor = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="not-used-in-batch-service-tests",
        role="technical_reviewer",
        is_active=True,
    )
    db.add(actor)
    db.flush()
    return actor


def _registration(document_id: str, **overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "artifact_provenance_note": None,
        "artifact_provenance_status": "unknown",
        "declared_source_role": "primary_test",
        "document_id": document_id,
        "document_type": "fire_test_report",
        "evidence_limitations": None,
        "evidence_scope": "full_source",
        "expiry_date": None,
        "issuing_organisation": "Example Test Laboratory",
        "jurisdiction": "Australia",
        "manufacturer": "Example Manufacturer",
        "publication_date": "2026-08-01",
        "reference": document_id,
        "related_document_id": None,
        "relationship_effective_date": None,
        "relationship_reason": None,
        "relationship_scope": None,
        "relationship_type": None,
        "review_date": None,
        "revision": "R1",
        "sponsor_organisation": "Example Sponsor",
        "standards": ["AS 1530.4:2014", "AS 4072.1:2005"],
        "title": f"Report {document_id}",
    }
    value.update(overrides)
    return value


def _item(
    ordinal: int,
    *,
    client_item_id: str,
    document_id: str,
    digest_character: str,
    filename: str | None = None,
    registration: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "client_item_id": client_item_id,
        "expected_sha256": digest_character * 64,
        "filename": filename or f"{document_id}.pdf",
        "ordinal": ordinal,
        "registration": registration or _registration(document_id),
        "size_bytes": 1_024 + ordinal,
    }


def _create_batch(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    request_id: str = _REQUEST_A,
    items: list[dict[str, object]] | None = None,
):
    return create_technical_intake_batch(
        db,
        settings,
        actor=actor,
        client_request_id=request_id,
        items=items
        or [
            _item(
                1,
                client_item_id=_ITEM_A,
                document_id="DOC-BATCH-A",
                digest_character="a",
            )
        ],
        source_ip="127.0.0.1",
    )


def _source_document(
    db: Session,
    *,
    document_id: str,
    digest: str | None = None,
    size_bytes: int = 1_024,
) -> TechnicalDocument:
    file_digest = digest or hashlib.sha256(document_id.encode("utf-8")).hexdigest()
    stored = StoredFile(
        original_filename=f"{document_id}.pdf",
        media_type="application/pdf",
        storage_path=f"C:/governed-test-storage/{file_digest}.pdf",
        sha256=file_digest,
        size_bytes=size_bytes,
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="fire_test_report",
        declared_source_role="primary_test",
        artifact_provenance_status="unknown",
        evidence_scope="full_source",
        title=f"Source {document_id}",
        status="draft",
        extraction_status="awaiting_safe_extraction",
    )
    db.add(document)
    db.flush()
    return document


def _error_receipt(
    item: TechnicalIntakeBatchItem,
    code: str,
    *,
    retryable: bool,
    operator_attention: bool,
) -> dict[str, object]:
    error = TechnicalUploadError(code)
    return {
        "batch_id": item.batch_id,
        "code": code,
        "expected_sha256": item.expected_sha256,
        "expected_size_bytes": item.declared_size_bytes,
        "http_status": error.status_code,
        "item_id": item.id,
        "ok": False,
        "operator_attention": operator_attention,
        "retryable": retryable,
        "schema": TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _set_processing(
    item: TechnicalIntakeBatchItem,
    *,
    started_at: datetime | None = None,
) -> None:
    attempt_count = max(item.attempt_count, 1)
    item.status = "processing"
    item.attempt_token = "33333333-3333-4333-8333-333333333333"  # noqa: S105
    item.attempt_started_at = started_at or datetime.now(UTC)
    item.attempt_count = attempt_count


def _set_rejected(
    item: TechnicalIntakeBatchItem,
    *,
    retryable: bool,
    code: str = "MALWARE_SCANNER_UNAVAILABLE",
) -> None:
    receipt = _error_receipt(
        item,
        code,
        retryable=retryable,
        operator_attention=False,
    )
    item.status = "rejected"
    item.attempt_token = None
    item.attempt_started_at = None
    item.attempt_count = max(item.attempt_count, 1)
    item.outcome_code = code
    item.outcome_retryable = retryable
    item.last_outcome_at = datetime.now(UTC)
    item.receipt_schema = TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
    item.receipt_json = receipt
    item.receipt_sha256 = canonical_json_sha256(receipt)


def _set_needs_attention(item: TechnicalIntakeBatchItem) -> None:
    receipt = _error_receipt(
        item,
        "TECHNICAL_INTAKE_AUDIT_FAILURE",
        retryable=False,
        operator_attention=True,
    )
    item.status = "needs_attention"
    item.attempt_token = None
    item.attempt_started_at = None
    item.attempt_count = max(item.attempt_count, 1)
    item.outcome_code = "TECHNICAL_INTAKE_AUDIT_FAILURE"
    item.outcome_retryable = False
    item.last_outcome_at = datetime.now(UTC)
    item.receipt_schema = TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
    item.receipt_json = receipt
    item.receipt_sha256 = canonical_json_sha256(receipt)


def _set_accepted(db: Session, item: TechnicalIntakeBatchItem) -> None:
    document = _source_document(
        db,
        document_id=item.declared_document_id,
        digest=item.expected_sha256,
        size_bytes=item.declared_size_bytes,
    )
    registration = item.registration_snapshot
    receipt = {
        "artifact_provenance_status": registration["artifact_provenance_status"],
        "batch_id": item.batch_id,
        "declared_source_role": registration["declared_source_role"],
        "document_id": item.declared_document_id,
        "document_type": registration["document_type"],
        "evidence_scope": registration["evidence_scope"],
        "exact_content_duplicate_document_ids": [],
        "extraction_status": "awaiting_safe_extraction",
        "file_sha256": item.expected_sha256,
        "http_status": 201,
        "id": document.id,
        "item_id": item.id,
        "malware_scan_status": "clean",
        "ok": True,
        "relationship": (
            {
                "relationship_type": registration["relationship_type"],
                "related_document_id": registration["related_document_id"],
            }
            if registration["relationship_type"] is not None
            and registration["related_document_id"] is not None
            else None
        ),
        "schema": TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA,
        "status": "draft",
        "status_url": f"/api/v1/technical/upload-batches/{item.batch_id}",
    }
    item.status = "accepted"
    item.attempt_token = None
    item.attempt_started_at = None
    item.attempt_count = max(item.attempt_count, 1)
    item.technical_document_id = document.id
    item.retained_file_sha256 = item.expected_sha256
    item.outcome_code = "ACCEPTED"
    item.outcome_retryable = False
    item.last_outcome_at = datetime.now(UTC)
    item.receipt_schema = TECHNICAL_INTAKE_ITEM_RECEIPT_SCHEMA
    item.receipt_json = receipt
    item.receipt_sha256 = canonical_json_sha256(receipt)


def _assert_error(code: str, operation: Any) -> None:
    with pytest.raises(TechnicalIntakeBatchError) as caught:
        operation()
    assert caught.value.code == code


def test_create_persists_exact_normalized_manifest_and_order(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "manifest.owner@example.test")
    raw_a = _registration(
        "DOC-MANIFEST-A",
        title="  Manifest report A  ",
        standards="AS 1530.4:2014\nAS 4072.1:2005",
    )
    raw_b = _registration("DOC-MANIFEST-B")
    supplied = [
        _item(
            2,
            client_item_id=_ITEM_B,
            document_id="DOC-MANIFEST-B",
            digest_character="b",
            registration=raw_b,
        ),
        _item(
            1,
            client_item_id=_ITEM_A,
            document_id="DOC-MANIFEST-A",
            digest_character="a",
            filename="report-a.pdf",
            registration=raw_a,
        ),
    ]

    result = _create_batch(db, settings, actor, items=supplied)

    normalized_a = {
        **raw_a,
        "title": "Manifest report A",
        "standards": ["AS 1530.4:2014", "AS 4072.1:2005"],
    }
    normalized_b = copy.deepcopy(raw_b)
    expected_manifest = {
        "batch_schema": TECHNICAL_INTAKE_BATCH_SCHEMA,
        "client_request_id": _REQUEST_A,
        "items": [
            {
                "client_item_id": _ITEM_A,
                "expected_sha256": "a" * 64,
                "filename": "report-a.pdf",
                "ordinal": 1,
                "registration": normalized_a,
                "registration_sha256": canonical_json_sha256(normalized_a),
                "size_bytes": 1_025,
            },
            {
                "client_item_id": _ITEM_B,
                "expected_sha256": "b" * 64,
                "filename": "DOC-MANIFEST-B.pdf",
                "ordinal": 2,
                "registration": normalized_b,
                "registration_sha256": canonical_json_sha256(normalized_b),
                "size_bytes": 1_026,
            },
        ],
    }
    assert result.idempotent_replay is False
    assert result.batch.batch_schema == TECHNICAL_INTAKE_BATCH_SCHEMA
    assert result.batch.manifest_sha256 == canonical_json_sha256(expected_manifest)
    assert [item.ordinal for item in result.items] == [1, 2]
    assert result.items[0].registration_snapshot == normalized_a
    assert result.items[0].registration_sha256 == canonical_json_sha256(normalized_a)
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "technical_intake_batch",
            AuditEvent.entity_id == result.batch.id,
        )
    )
    assert event is not None
    assert event.correlation_id == result.batch.id
    assert event.new_value["manifest_sha256"] == result.batch.manifest_sha256


@pytest.mark.parametrize(
    "filename",
    [
        "nested/report.pdf",
        "nested\\report.pdf",
        " report.pdf",
        "report.pdf ",
        "C:report.pdf",
        "report?.pdf",
        "report\u0085.pdf",
        "report\u00a0.pdf",
        "report\u200e.pdf",
    ],
)
def test_create_rejects_noncanonical_filenames(
    db: Session,
    settings: Settings,
    filename: str,
) -> None:
    actor = _user(db, f"filename-{hashlib.sha256(filename.encode()).hexdigest()}@example.test")

    _assert_error(
        "INTAKE_BATCH_MANIFEST_INVALID",
        lambda: _create_batch(
            db,
            settings,
            actor,
            items=[
                _item(
                    1,
                    client_item_id=_ITEM_A,
                    document_id="DOC-CANONICAL-FILENAME",
                    digest_character="a",
                    filename=filename,
                )
            ],
        ),
    )


@pytest.mark.parametrize("filename", ["report.csv", "report.xlsm"])
def test_create_rejects_storage_only_extensions_before_database_flush(
    db: Session,
    settings: Settings,
    filename: str,
) -> None:
    actor = _user(db, f"extension-{filename}@example.test")

    _assert_error(
        "INTAKE_BATCH_MANIFEST_INVALID",
        lambda: _create_batch(
            db,
            settings,
            actor,
            items=[
                _item(
                    1,
                    client_item_id=_ITEM_A,
                    document_id="DOC-BATCH-EXTENSION",
                    digest_character="a",
                    filename=filename,
                )
            ],
        ),
    )
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 0


@pytest.mark.parametrize(
    "identifier",
    [
        "00000000-0000-0000-0000-000000000000",
        "11111111-1111-1111-8111-111111111111",
        "ABCDEFAB-CDEF-4ABC-8ABC-ABCDEFABCDEF",
        f" {_REQUEST_A}",
    ],
)
def test_create_rejects_non_v4_request_and_item_identifiers(
    db: Session,
    settings: Settings,
    identifier: str,
) -> None:
    identifier_digest = hashlib.sha256(identifier.encode()).hexdigest()[:12]
    actor = _user(db, f"uuid-{identifier_digest}@example.test")
    _assert_error(
        "INTAKE_BATCH_ID_INVALID",
        lambda: _create_batch(
            db,
            settings,
            actor,
            request_id=identifier,
        ),
    )
    _assert_error(
        "INTAKE_BATCH_ITEM_ID_INVALID",
        lambda: _create_batch(
            db,
            settings,
            actor,
            items=[
                _item(
                    1,
                    client_item_id=identifier,
                    document_id="DOC-UUID-CONTRACT",
                    digest_character="a",
                )
            ],
        ),
    )


def test_create_requires_explicit_jurisdiction_in_manifest(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "jurisdiction-default@example.test")
    registration = _registration("DOC-JURISDICTION", jurisdiction=None)

    _assert_error(
        "INTAKE_FIELD_INVALID",
        lambda: _create_batch(
            db,
            settings,
            actor,
            items=[
                _item(
                    1,
                    client_item_id=_ITEM_A,
                    document_id="DOC-JURISDICTION",
                    digest_character="a",
                    registration=registration,
                )
            ],
        ),
    )


def test_exact_create_replay_is_idempotent_and_changed_intent_fails_closed(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "replay.owner@example.test")
    original_items = [
        _item(
            1,
            client_item_id=_ITEM_A,
            document_id="DOC-REPLAY-A",
            digest_character="a",
        )
    ]
    first = _create_batch(db, settings, actor, items=original_items)

    replay = _create_batch(
        db,
        settings,
        actor,
        items=copy.deepcopy(original_items),
    )

    assert replay.idempotent_replay is True
    assert replay.batch.id == first.batch.id
    assert [item.id for item in replay.items] == [item.id for item in first.items]
    changed_settings = Settings(
        _env_file=None,
        env="test",
        storage_root=settings.storage_root,
        max_upload_mb=2,
        jurisdiction="A different configured jurisdiction",
    )
    config_changed_replay = _create_batch(
        db,
        changed_settings,
        actor,
        items=copy.deepcopy(original_items),
    )
    assert config_changed_replay.idempotent_replay is True
    assert config_changed_replay.batch.id == first.batch.id
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.entity_type == "technical_intake_batch")
        )
        == 1
    )

    changed_metadata = copy.deepcopy(original_items)
    changed_metadata[0]["registration"]["title"] = "Different report title"  # type: ignore[index]
    _assert_error(
        "INTAKE_BATCH_MANIFEST_MISMATCH",
        lambda: _create_batch(db, settings, actor, items=changed_metadata),
    )
    changed_bytes = copy.deepcopy(original_items)
    changed_bytes[0]["expected_sha256"] = "f" * 64
    _assert_error(
        "INTAKE_BATCH_MANIFEST_MISMATCH",
        lambda: _create_batch(db, settings, actor, items=changed_bytes),
    )
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 1


def test_exact_create_replay_uses_the_admitted_size_policy(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "size-policy-replay@example.test")
    larger_manifest = [
        _item(
            1,
            client_item_id=_ITEM_B,
            document_id="DOC-REPLAY-SIZE-POLICY",
            digest_character="b",
        )
    ]
    larger_manifest[0]["size_bytes"] = 1_500_000
    first = _create_batch(
        db,
        settings,
        actor,
        request_id=_REQUEST_B,
        items=larger_manifest,
    )
    reduced_limit_settings = Settings(
        _env_file=None,
        env="test",
        storage_root=settings.storage_root,
        max_upload_mb=1,
    )

    replay = _create_batch(
        db,
        reduced_limit_settings,
        actor,
        request_id=_REQUEST_B,
        items=copy.deepcopy(larger_manifest),
    )

    assert replay.idempotent_replay is True
    assert replay.batch.id == first.batch.id
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatchItem)) == 1


def test_create_integrity_error_without_competing_request_is_persistence_conflict(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _user(db, "integrity-classification@example.test")
    db.commit()
    real_flush = db.flush
    injected = False

    def fail_once(*args: object, **kwargs: object) -> None:
        nonlocal injected
        if not injected and any(
            isinstance(value, TechnicalIntakeBatch) for value in db.new
        ):
            injected = True
            raise IntegrityError("forced batch insert", {}, RuntimeError("forced"))
        real_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", fail_once)

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: _create_batch(db, settings, actor),
    )
    assert injected is True
    assert db.scalar(select(func.count()).select_from(TechnicalIntakeBatch)) == 0


def test_idempotent_create_replay_projects_changed_item_state_in_one_snapshot(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "replay-snapshot@example.test")
    items = [
        _item(
            1,
            client_item_id=_ITEM_A,
            document_id="DOC-REPLAY-SNAPSHOT",
            digest_character="a",
        )
    ]
    created = _create_batch(db, settings, actor, items=items)
    claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=created.items[0].id,
        filename=created.items[0].original_filename,
        registration_snapshot=created.items[0].registration_snapshot,
    )
    _ = actor.id
    observed_statements: list[object] = []

    def capture_statement(execute_state: object) -> None:
        statement = getattr(execute_state, "statement", None)
        if statement is not None:
            observed_statements.append(statement)

    event.listen(db, "do_orm_execute", capture_statement)
    try:
        replay = _create_batch(
            db,
            settings,
            actor,
            items=copy.deepcopy(items),
        )
    finally:
        event.remove(db, "do_orm_execute", capture_statement)

    assert replay.idempotent_replay is True
    assert replay.batch.status == "in_progress"
    assert replay.items[0].status == "processing"
    assert len(observed_statements) == 1
    sql = str(observed_statements[0].compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN technical_intake_batch_items" in sql


def test_batch_ownership_hides_status_and_claims_from_other_users(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "first.owner@example.test")
    other = _user(db, "second.owner@example.test")
    created = _create_batch(db, settings, owner)
    item = created.items[0]

    _assert_error(
        "INTAKE_BATCH_NOT_FOUND",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=other,
            batch_id=created.batch.id,
        ),
    )
    _assert_error(
        "INTAKE_BATCH_NOT_FOUND",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=other,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=item.original_filename,
            registration_snapshot=item.registration_snapshot,
        ),
    )

    separate = _create_batch(db, settings, other)
    assert separate.batch.id != created.batch.id
    assert separate.batch.client_request_id == created.batch.client_request_id


def test_registration_normalization_is_exact_and_rejects_invalid_shapes() -> None:
    raw = _registration(
        "DOC-NORMALIZED",
        title="  A normalized title  ",
        manufacturer="  A manufacturer  ",
        standards="AS 1530.4:2014, AS 4072.1:2005",
        relationship_type="assessment_of",
        related_document_id="DOC-NORMALIZED-TARGET",
        relationship_reason="Assessment relationship",
        relationship_scope="  Line one\r\nLine two\tservice group  ",
    )

    normalized = normalize_technical_intake_registration(raw)

    assert normalized["title"] == "A normalized title"
    assert normalized["manufacturer"] == "A manufacturer"
    assert normalized["standards"] == ["AS 1530.4:2014", "AS 4072.1:2005"]
    assert normalized["relationship_scope"] == (
        "Line one\nLine two\tservice group"
    )
    assert set(normalized) == set(raw)

    missing = copy.deepcopy(raw)
    missing.pop("reference")
    _assert_error(
        "INTAKE_BATCH_MANIFEST_INVALID",
        lambda: normalize_technical_intake_registration(missing),
    )
    extra = {**raw, "unexpected": "not allowed"}
    _assert_error(
        "INTAKE_BATCH_MANIFEST_INVALID",
        lambda: normalize_technical_intake_registration(extra),
    )
    invalid_rir = _registration(
        "DOC-RIR-INVALID",
        document_type="regulatory_information_report",
        declared_source_role="assessment",
        evidence_scope="full_source",
    )
    _assert_error(
        "SOURCE_CLASSIFICATION_INVALID",
        lambda: normalize_technical_intake_registration(invalid_rir),
    )


@pytest.mark.parametrize(
    ("document_type", "declared_source_role", "evidence_scope"),
    [
        ("fire_test_report", "primary_test", "full_source"),
        ("regulatory_information_report", "regulatory_summary", "summary_only"),
        ("fire_assessment", "assessment", "full_source"),
        ("extended_application_report", "assessment", "full_source"),
        ("field_of_application_report", "assessment", "full_source"),
        (
            "fire_engineering_report_performance_solution",
            "assessment",
            "full_source",
        ),
        ("certificate_summary_of_assessment", "assessment", "full_source"),
        ("test_certificate", "primary_test", "full_source"),
    ],
)
def test_batch_registration_accepts_each_new_report_family(
    document_type: str,
    declared_source_role: str,
    evidence_scope: str,
) -> None:
    registration = _registration(
        f"DOC-BATCH-FAMILY-{document_type.upper()}",
        document_type=document_type,
        declared_source_role=declared_source_role,
        evidence_scope=evidence_scope,
    )

    normalized = normalize_technical_intake_registration(registration)

    assert normalized["document_type"] == document_type
    assert normalized["declared_source_role"] == declared_source_role
    assert normalized["evidence_scope"] == evidence_scope


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        (
            {"relationship_type": "revision_of"},
            "RELATIONSHIP_FIELDS_INCOMPLETE",
        ),
        (
            {
                "relationship_type": "not-a-relationship",
                "related_document_id": "DOC-TARGET",
                "relationship_reason": "Invalid relationship type",
            },
            "RELATIONSHIP_TYPE_INVALID",
        ),
        (
            {
                "relationship_type": "revision_of",
                "related_document_id": "DOC-RELATIONSHIP",
                "relationship_reason": "Self reference",
            },
            "RELATIONSHIP_SELF_REFERENCE",
        ),
    ],
)
def test_relationship_registration_rejects_incomplete_invalid_and_self_edges(
    overrides: dict[str, object],
    expected: str,
) -> None:
    registration = _registration("DOC-RELATIONSHIP", **overrides)
    _assert_error(
        expected,
        lambda: normalize_technical_intake_registration(registration),
    )


def test_batch_requires_existing_relationship_target(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "relationship.owner@example.test")
    registration = _registration(
        "DOC-RELATIONSHIP-CHILD",
        relationship_type="assessment_of",
        related_document_id="DOC-RELATIONSHIP-TARGET",
        relationship_reason="This assessment explicitly evaluates the retained source.",
        relationship_scope="Whole report",
        relationship_effective_date="2026-08-27",
    )
    items = [
        _item(
            1,
            client_item_id=_ITEM_A,
            document_id="DOC-RELATIONSHIP-CHILD",
            digest_character="a",
            registration=registration,
        )
    ]

    _assert_error(
        "RELATED_DOCUMENT_NOT_FOUND",
        lambda: _create_batch(db, settings, actor, items=items),
    )

    _source_document(db, document_id="DOC-RELATIONSHIP-TARGET")
    db.commit()
    created = _create_batch(db, settings, actor, items=items)
    assert created.items[0].registration_snapshot["relationship_type"] == "assessment_of"
    assert (
        created.items[0].registration_snapshot["related_document_id"]
        == "DOC-RELATIONSHIP-TARGET"
    )


def test_claim_is_exact_and_serializes_active_attempts(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "claim.owner@example.test")
    created = _create_batch(db, settings, actor)
    item = created.items[0]

    _assert_error(
        "INTAKE_BATCH_ITEM_REPLAY_MISMATCH",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename="different.pdf",
            registration_snapshot=item.registration_snapshot,
        ),
    )
    _assert_error(
        "INTAKE_BATCH_ITEM_REPLAY_MISMATCH",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=f"nested/{item.original_filename}",
            registration_snapshot=item.registration_snapshot,
        ),
    )
    changed_registration = copy.deepcopy(item.registration_snapshot)
    changed_registration["title"] = "Changed title"
    _assert_error(
        "INTAKE_BATCH_ITEM_REPLAY_MISMATCH",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=item.original_filename,
            registration_snapshot=changed_registration,
        ),
    )

    claim = claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )

    assert claim.accepted_replay is False
    assert claim.prior_status == "pending"
    assert claim.attempt_token is not None
    persisted = db.get(TechnicalIntakeBatchItem, item.id)
    assert persisted is not None
    assert persisted.status == "processing"
    assert persisted.attempt_count == 1
    assert persisted.attempt_token == claim.attempt_token
    assert db.get(TechnicalIntakeBatch, created.batch.id).status == "in_progress"

    _assert_error(
        "INTAKE_BATCH_ITEM_IN_PROGRESS",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=item.original_filename,
            registration_snapshot=item.registration_snapshot,
        ),
    )


def test_claim_uses_record_version_compare_and_swap(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _user(db, "cas.owner@example.test")
    created = _create_batch(db, settings, actor)
    item = created.items[0]
    real_execute = db.execute
    injected = False

    def execute_with_stale_version(statement, *args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal injected
        if (
            not injected
            and isinstance(statement, Update)
            and statement.table.name == TechnicalIntakeBatchItem.__tablename__
        ):
            injected = True
            real_execute(
                update(TechnicalIntakeBatchItem)
                .where(TechnicalIntakeBatchItem.id == item.id)
                .values(
                    record_version=TechnicalIntakeBatchItem.record_version + 1
                )
                .execution_options(synchronize_session=False)
            )
        return real_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db, "execute", execute_with_stale_version)

    _assert_error(
        "INTAKE_BATCH_ITEM_IN_PROGRESS",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=item.original_filename,
            registration_snapshot=item.registration_snapshot,
        ),
    )

    assert injected is True
    persisted = db.get(TechnicalIntakeBatchItem, item.id)
    assert persisted is not None
    assert persisted.status == "pending"
    assert persisted.record_version == 1


def test_retryable_rejection_and_expired_claim_can_be_reclaimed(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "retry.owner@example.test")
    created = _create_batch(db, settings, actor)
    item = created.items[0]
    first = claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )
    persisted = db.get(TechnicalIntakeBatchItem, item.id)
    assert persisted is not None
    _set_rejected(persisted, retryable=True)
    refresh_technical_intake_batch_status(db, batch_id=created.batch.id)
    db.commit()

    retry = claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )

    assert retry.prior_status == "rejected"
    assert retry.attempt_token not in {None, first.attempt_token}
    retried = db.get(TechnicalIntakeBatchItem, item.id)
    assert retried is not None
    assert retried.status == "processing"
    assert retried.attempt_count == 2
    assert retried.outcome_code == "MALWARE_SCANNER_UNAVAILABLE"
    assert retried.outcome_retryable is True
    active_payload = serialize_technical_intake_batch(
        created.batch,
        (retried,),
    )["items"][0]
    assert active_payload["retryable"] is False
    assert isinstance(active_payload["claim_expires_at"], str)
    assert datetime.fromisoformat(active_payload["claim_expires_at"]).tzinfo is not None

    retried.attempt_started_at = (
        datetime.now(UTC) - TECHNICAL_INTAKE_CLAIM_TTL - timedelta(seconds=1)
    )
    expired_payload = serialize_technical_intake_batch(
        created.batch,
        (retried,),
    )["items"][0]
    assert expired_payload["retryable"] is True
    assert isinstance(expired_payload["claim_expires_at"], str)
    old_token = retried.attempt_token
    db.commit()
    reclaimed = claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )
    assert reclaimed.prior_status == "rejected"
    assert reclaimed.attempt_token not in {None, old_token}
    assert db.get(TechnicalIntakeBatchItem, item.id).attempt_count == 3


def test_nonretryable_rejection_cannot_be_claimed_again(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "terminal.owner@example.test")
    created = _create_batch(db, settings, actor)
    item = created.items[0]
    _set_rejected(item, retryable=False, code="MALWARE_DETECTED")
    refresh_technical_intake_batch_status(db, batch_id=created.batch.id)
    db.commit()

    _assert_error(
        "INTAKE_BATCH_ITEM_NOT_RETRYABLE",
        lambda: claim_technical_intake_batch_item(
            db,
            actor=actor,
            batch_id=created.batch.id,
            item_id=item.id,
            filename=item.original_filename,
            registration_snapshot=item.registration_snapshot,
        ),
    )


def test_accepted_claim_replays_without_mutating_attempt_state(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "accepted.owner@example.test")
    created = _create_batch(db, settings, actor)
    item = created.items[0]
    _set_accepted(db, item)
    refresh_technical_intake_batch_status(db, batch_id=created.batch.id)
    db.commit()
    version = item.record_version

    replay = claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )

    assert replay.accepted_replay is True
    assert replay.attempt_token is None
    assert replay.prior_status == "accepted"
    persisted = db.get(TechnicalIntakeBatchItem, item.id)
    assert persisted is not None
    assert persisted.status == "accepted"
    assert persisted.attempt_count == 1
    assert persisted.record_version == version


def test_serialization_is_stable_ordered_and_owner_safe(
    db: Session,
    settings: Settings,
) -> None:
    actor = _user(db, "serialize.owner@example.test")
    created = _create_batch(
        db,
        settings,
        actor,
        items=[
            _item(
                2,
                client_item_id=_ITEM_B,
                document_id="DOC-SERIALIZE-B",
                digest_character="b",
            ),
            _item(
                1,
                client_item_id=_ITEM_A,
                document_id="DOC-SERIALIZE-A",
                digest_character="a",
            ),
        ],
    )

    payload = serialize_technical_intake_batch(
        created.batch,
        created.items,
        idempotent_replay=True,
    )

    assert payload["ok"] is True
    assert payload["batch_schema"] == TECHNICAL_INTAKE_BATCH_SCHEMA
    assert payload["idempotent_replay"] is True
    assert payload["status_url"] == (
        f"/api/v1/technical/upload-batches/{created.batch.id}"
    )
    assert payload["counts"] == {
        "pending": 2,
        "processing": 0,
        "accepted": 0,
        "rejected": 0,
        "needs_attention": 0,
    }
    assert [item["ordinal"] for item in payload["items"]] == [1, 2]
    assert payload["created_at"].endswith("+00:00")
    assert payload["updated_at"].endswith("+00:00")
    assert all(item["retryable"] is True for item in payload["items"])
    assert all(item["claim_expires_at"] is None for item in payload["items"])
    assert payload["items"][0]["registration"] == created.items[0].registration_snapshot
    assert "created_by_id" not in payload
    assert all("attempt_token" not in item for item in payload["items"])


def test_status_refresh_locks_batch_before_folding_item_states(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "status-lock@example.test")
    created = _create_batch(db, settings, owner)
    batch_id = created.batch.id
    observed_statements: list[object] = []

    def capture_statement(execute_state: object) -> None:
        statement = getattr(execute_state, "statement", None)
        if statement is not None:
            observed_statements.append(statement)

    event.listen(db, "do_orm_execute", capture_statement)
    try:
        refresh_technical_intake_batch_status(
            db,
            batch_id=batch_id,
        )
    finally:
        event.remove(db, "do_orm_execute", capture_statement)

    assert observed_statements
    first_sql = str(
        observed_statements[0].compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" in first_sql


def test_owned_batch_projection_uses_one_joined_database_snapshot(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "consistent-read@example.test")
    created = _create_batch(db, settings, owner)
    batch_id = created.batch.id
    _ = owner.id
    observed_statements: list[object] = []

    def capture_statement(execute_state: object) -> None:
        statement = getattr(execute_state, "statement", None)
        if statement is not None:
            observed_statements.append(statement)

    event.listen(db, "do_orm_execute", capture_statement)
    try:
        batch, items = get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=batch_id,
        )
    finally:
        event.remove(db, "do_orm_execute", capture_statement)

    assert batch.id == batch_id
    assert len(items) == 1
    assert len(observed_statements) == 1
    sql = str(observed_statements[0].compile(dialect=postgresql.dialect()))
    assert "LEFT OUTER JOIN technical_intake_batch_items" in sql


def test_owned_batch_rejects_tampered_parent_manifest_hash(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "manifest-integrity@example.test")
    created = _create_batch(db, settings, owner)
    batch_id = created.batch.id
    created.batch.manifest_sha256 = "f" * 64
    db.commit()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=batch_id,
        ),
    )


def test_owned_batch_rejects_self_consistent_noncanonical_persisted_filename(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "persisted-filename-integrity@example.test")
    created = _create_batch(db, settings, owner)
    batch = created.batch
    item = created.items[0]
    batch_id = batch.id
    item.original_filename = "report\u200e.pdf"
    batch.manifest_sha256 = canonical_json_sha256(
        {
            "batch_schema": batch.batch_schema,
            "client_request_id": batch.client_request_id,
            "items": [
                {
                    "client_item_id": item.client_item_id,
                    "expected_sha256": item.expected_sha256,
                    "filename": item.original_filename,
                    "ordinal": item.ordinal,
                    "registration": item.registration_snapshot,
                    "registration_sha256": item.registration_sha256,
                    "size_bytes": item.declared_size_bytes,
                }
            ],
        }
    )
    db.commit()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=batch_id,
        ),
    )


@pytest.mark.parametrize("tamper", ["receipt_digest", "receipt_outcome_binding"])
def test_owned_batch_rejects_corrupt_terminal_receipt(
    db: Session,
    settings: Settings,
    tamper: str,
) -> None:
    owner = _user(db, f"receipt-integrity-{tamper}@example.test")
    created = _create_batch(db, settings, owner)
    item = created.items[0]
    _set_rejected(item, retryable=False, code="MALWARE_DETECTED")
    refresh_technical_intake_batch_status(db, batch_id=created.batch.id)
    db.commit()
    get_owned_technical_intake_batch(
        db,
        actor=owner,
        batch_id=created.batch.id,
    )

    if tamper == "receipt_digest":
        item.receipt_sha256 = "f" * 64
    else:
        receipt = dict(item.receipt_json)
        receipt["code"] = "UPLOAD_CONTENT_SIGNATURE_INVALID"
        item.receipt_json = receipt
        item.receipt_sha256 = canonical_json_sha256(receipt)
    db.commit()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=created.batch.id,
        ),
    )


def test_owned_batch_rejects_status_not_derived_from_item_states(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "batch-status-integrity@example.test")
    created = _create_batch(db, settings, owner)
    created.batch.status = "in_progress"
    db.commit()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=created.batch.id,
        ),
    )


def test_owned_batch_rejects_noncanonical_persisted_item_id(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "item-id-integrity@example.test")
    created = _create_batch(db, settings, owner)
    item_id = created.items[0].id
    db.commit()
    db.execute(text("PRAGMA ignore_check_constraints = ON"))
    db.execute(
        update(TechnicalIntakeBatchItem)
        .where(TechnicalIntakeBatchItem.id == item_id)
        .values(id="not-a-canonical-uuid")
        .execution_options(synchronize_session=False)
    )
    db.commit()
    db.execute(text("PRAGMA ignore_check_constraints = OFF"))
    db.expire_all()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=created.batch.id,
        ),
    )


@pytest.mark.parametrize("tamper", ["document_link", "quarantined_file"])
def test_owned_batch_rejects_unsafe_accepted_evidence_binding(
    db: Session,
    settings: Settings,
    tamper: str,
) -> None:
    owner = _user(db, f"accepted-binding-{tamper}@example.test")
    created = _create_batch(db, settings, owner)
    item = created.items[0]
    _set_accepted(db, item)
    refresh_technical_intake_batch_status(db, batch_id=created.batch.id)
    db.commit()
    get_owned_technical_intake_batch(
        db,
        actor=owner,
        batch_id=created.batch.id,
    )
    document = db.get(TechnicalDocument, item.technical_document_id)
    assert document is not None
    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None

    if tamper == "document_link":
        other = StoredFile(
            original_filename="other.pdf",
            media_type="application/pdf",
            storage_path="C:/governed-test-storage/other.pdf",
            sha256="f" * 64,
            size_bytes=item.declared_size_bytes,
            purpose="technical_evidence",
            malware_scan_status="clean",
            immutable=True,
        )
        db.add(other)
        db.flush()
        document.stored_file_id = other.id
    else:
        stored.malware_scan_status = "quarantined"
    db.commit()

    _assert_error(
        "INTAKE_BATCH_PERSISTENCE_CONFLICT",
        lambda: get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=created.batch.id,
        ),
    )


def test_claim_preserves_existing_operator_attention_precedence(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "claim-attention@example.test")
    created = _create_batch(
        db,
        settings,
        owner,
        items=[
            _item(
                1,
                client_item_id=_ITEM_A,
                document_id="DOC-CLAIM-ATTENTION-A",
                digest_character="a",
            ),
            _item(
                2,
                client_item_id=_ITEM_B,
                document_id="DOC-CLAIM-ATTENTION-B",
                digest_character="b",
            ),
        ],
    )
    _set_needs_attention(created.items[0])
    db.flush()
    refresh_technical_intake_batch_status(
        db,
        batch_id=created.batch.id,
    )
    db.commit()
    claim_technical_intake_batch_item(
        db,
        actor=owner,
        batch_id=created.batch.id,
        item_id=created.items[1].id,
        filename=created.items[1].original_filename,
        registration_snapshot=created.items[1].registration_snapshot,
    )

    persisted = db.get(TechnicalIntakeBatch, created.batch.id)
    assert persisted is not None
    assert persisted.status == "needs_attention"


@pytest.mark.parametrize(
    ("states", "expected_status", "terminal"),
    [
        (("pending", "pending"), "open", False),
        (("processing", "pending"), "in_progress", False),
        (("accepted", "pending"), "in_progress", False),
        (("needs_attention", "pending"), "needs_attention", False),
        (("accepted", "accepted"), "completed", True),
        (("accepted", "rejected"), "completed_with_rejections", True),
        (("rejected", "rejected"), "completed_with_rejections", True),
    ],
)
def test_batch_status_is_derived_from_all_item_states(
    db: Session,
    settings: Settings,
    states: tuple[str, str],
    expected_status: str,
    terminal: bool,
) -> None:
    owner = _user(db, f"status-{expected_status}-{states[0]}@example.test")
    request_id = {
        ("pending", "pending"): "44444444-4444-4444-8444-444444444441",
        ("processing", "pending"): "44444444-4444-4444-8444-444444444442",
        ("accepted", "pending"): "44444444-4444-4444-8444-444444444443",
        ("needs_attention", "pending"): "44444444-4444-4444-8444-444444444444",
        ("accepted", "accepted"): "44444444-4444-4444-8444-444444444445",
        ("accepted", "rejected"): "44444444-4444-4444-8444-444444444446",
        ("rejected", "rejected"): "44444444-4444-4444-8444-444444444447",
    }[states]
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=request_id,
        items=[
            _item(
                1,
                client_item_id=_ITEM_A,
                document_id=f"DOC-STATUS-{request_id[-1]}-A",
                digest_character="a",
            ),
            _item(
                2,
                client_item_id=_ITEM_B,
                document_id=f"DOC-STATUS-{request_id[-1]}-B",
                digest_character="b",
            ),
        ],
    )
    for item, state in zip(created.items, states, strict=True):
        if state == "processing":
            _set_processing(item)
        elif state == "accepted":
            _set_accepted(db, item)
        elif state == "rejected":
            _set_rejected(item, retryable=False, code="MALWARE_DETECTED")
        elif state == "needs_attention":
            _set_needs_attention(item)
    db.flush()
    completed_at = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)

    refresh_technical_intake_batch_status(
        db,
        batch_id=created.batch.id,
        now=completed_at,
    )
    db.commit()

    persisted = db.get(TechnicalIntakeBatch, created.batch.id)
    assert persisted is not None
    assert persisted.status == expected_status
    assert (persisted.completed_at is not None) is terminal
    if terminal:
        assert persisted.completed_at is not None
        assert _as_utc(persisted.completed_at) == completed_at


def test_completed_batch_refresh_preserves_first_completion_timestamp(
    db: Session,
    settings: Settings,
) -> None:
    owner = _user(db, "completion.timestamp@example.test")
    created = _create_batch(db, settings, owner)
    _set_accepted(db, created.items[0])
    first_completion = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    refresh_technical_intake_batch_status(
        db,
        batch_id=created.batch.id,
        now=first_completion,
    )
    db.commit()
    version = created.batch.record_version

    refresh_technical_intake_batch_status(
        db,
        batch_id=created.batch.id,
        now=first_completion + timedelta(hours=1),
    )
    db.commit()

    persisted = db.get(TechnicalIntakeBatch, created.batch.id)
    assert persisted is not None
    assert persisted.completed_at is not None
    assert _as_utc(persisted.completed_at) == first_completion
    assert persisted.record_version == version
