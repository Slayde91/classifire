from __future__ import annotations

import warnings
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError, SAWarning
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.schema import CreateTable
from test_migrations_physical_foundation import (
    _migration_environment,
    _run_migration,
    _upgrade,
)

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    StoredFile,
    TechnicalDerivedArtifact,
    TechnicalDocument,
    TechnicalExtractionPage,
    TechnicalExtractionRun,
    TechnicalParserInvocation,
    TechnicalParserInvocationReceipt,
    User,
)
from classifire.services.deployment_lineage import CLEAN_STACK_HEAD

SOURCE_SHA256 = "a" * 64
POLICY_SHA256 = "b" * 64
WORKER_DIGEST = "c" * 64
RUNTIME_PROFILE_SHA256 = "1" * 64
RUNTIME_ATTESTATION_SHA256 = "2" * 64
RUNTIME_EXECUTABLE_SHA256 = "3" * 64
SECCOMP_PROFILE_SHA256 = "4" * 64
REQUEST_SHA256 = "5" * 64
LAYOUT_SHA256 = "6" * 64
PACKET_SHA256 = "d" * 64
IMAGE_SHA256 = "e" * 64
BINDING_SHA256 = "f" * 64
SOURCE_SIZE = 12_345
PACKET_SIZE = 2_048
IMAGE_SIZE = 4_096
PAGE_COUNT = 2


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _seed_sources(
    db: Session,
) -> tuple[User, StoredFile, TechnicalDocument, TechnicalDocument]:
    owner = User(
        email="extraction-owner@example.test",
        full_name="Extraction Owner",
        password_hash="not-used-in-persistence-test",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(owner)
    db.flush()
    source = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path="technical/source.pdf",
        sha256=SOURCE_SHA256,
        size_bytes=SOURCE_SIZE,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=owner.id,
        immutable=True,
    )
    db.add(source)
    db.flush()
    first_document = TechnicalDocument(
        document_id="TECH-EXTRACT-001",
        stored_file_id=source.id,
        document_type="assessment",
        title="First registration",
    )
    second_document = TechnicalDocument(
        document_id="TECH-EXTRACT-002",
        stored_file_id=source.id,
        document_type="assessment",
        title="Second registration of the same retained bytes",
    )
    db.add_all([first_document, second_document])
    db.commit()
    return owner, source, first_document, second_document


def _run(
    document: TechnicalDocument,
    source: StoredFile,
    *,
    page_count: int | None = PAGE_COUNT,
) -> TechnicalExtractionRun:
    return TechnicalExtractionRun(
        source_stored_file_id=source.id,
        technical_document_id=document.id,
        source_sha256=source.sha256,
        source_size_bytes=source.size_bytes,
        extraction_policy="technical-extraction-policy-v1",
        extraction_policy_sha256=POLICY_SHA256,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_DIGEST,
        page_count=page_count,
        layout_schema="technical-parser-layout-v1" if page_count is not None else None,
        layout_sha256=LAYOUT_SHA256 if page_count is not None else None,
        layout_size_bytes=512 if page_count is not None else None,
    )


def _v2_run(
    document: TechnicalDocument,
    source: StoredFile,
    *,
    runtime_profile_sha256: str = RUNTIME_PROFILE_SHA256,
) -> TechnicalExtractionRun:
    return TechnicalExtractionRun(
        run_schema="technical-extraction-run-v2",
        source_stored_file_id=source.id,
        technical_document_id=document.id,
        source_sha256=source.sha256,
        source_size_bytes=source.size_bytes,
        extraction_policy="technical-extraction-policy-v1",
        extraction_policy_sha256=POLICY_SHA256,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_DIGEST,
        runtime_profile_sha256=runtime_profile_sha256,
    )


def _layout_invocation(
    run: TechnicalExtractionRun,
    *,
    runtime_attestation_schema: str = "technical-parser-runtime-attestation-v1",
) -> TechnicalParserInvocation:
    assert run.attempt_token is not None
    assert run.runtime_profile_sha256 is not None
    assert run.runtime_attestation_sha256 is not None
    return TechnicalParserInvocation(
        run_id=run.id,
        run_attempt_token=run.attempt_token,
        run_attempt_count=run.attempt_count,
        operation="layout",
        page_number=0,
        attempt_token=run.attempt_token,
        attempt_count=run.attempt_count,
        request_sha256=REQUEST_SHA256,
        request_size_bytes=512,
        extraction_policy=run.extraction_policy,
        extraction_policy_sha256=run.extraction_policy_sha256,
        worker_image_digest=run.worker_image_digest,
        image_reference=("registry.example/classifire/parser@sha256:" + run.worker_image_digest),
        image_id="sha256:" + ("8" * 64),
        platform="linux/amd64",
        runtime_host="unix:///run/user/1000/docker.sock",
        runtime_executable_sha256=RUNTIME_EXECUTABLE_SHA256,
        seccomp_profile_sha256=SECCOMP_PROFILE_SHA256,
        runtime_profile_sha256=run.runtime_profile_sha256,
        runtime_attestation_schema=runtime_attestation_schema,
        runtime_attestation_json={
            "schema": runtime_attestation_schema,
            "runtime_profile_sha256": run.runtime_profile_sha256,
        },
        runtime_attestation_sha256=run.runtime_attestation_sha256,
    )


def _successful_receipt(
    invocation: TechnicalParserInvocation,
    *,
    stdout_sha256: str = LAYOUT_SHA256,
    stdout_size_bytes: int = 512,
) -> TechnicalParserInvocationReceipt:
    started = datetime.now(UTC)
    return TechnicalParserInvocationReceipt(
        invocation_id=invocation.id,
        run_id=invocation.run_id,
        operation=invocation.operation,
        page_number=invocation.page_number,
        request_sha256=invocation.request_sha256,
        runtime_attestation_sha256=invocation.runtime_attestation_sha256,
        execution_state="succeeded",
        outcome_code="PARSER_INVOCATION_SUCCEEDED",
        container_id="9" * 64,
        started_at=started,
        completed_at=started,
        exit_code=0,
        stdout_sha256=stdout_sha256,
        stdout_size_bytes=stdout_size_bytes,
        cleanup_confirmed=True,
        receipt_json={
            "invocation_id": invocation.id,
            "schema": "technical-parser-invocation-receipt-v1",
        },
        receipt_sha256="7" * 64,
    )


def _legacy_execution_unknown_receipt(
    invocation: TechnicalParserInvocation,
) -> TechnicalParserInvocationReceipt:
    receipt = _successful_receipt(invocation)
    receipt.execution_state = "execution_unknown"
    receipt.outcome_code = "PARSER_EXECUTION_OUTCOME_UNKNOWN"
    return receipt


def _page_layout_values(
    *,
    page_number: int,
) -> dict[str, object]:
    return {
        "layout_sha256": LAYOUT_SHA256,
        "layout_page_width_points": Decimal(611 + page_number),
        "layout_page_height_points": Decimal("792"),
    }


def _artifacts(
    db: Session,
    run: TechnicalExtractionRun,
    *,
    page_number: int = 1,
) -> tuple[TechnicalDerivedArtifact, TechnicalDerivedArtifact]:
    packet = TechnicalDerivedArtifact(
        run_id=run.id,
        page_number=page_number,
        artifact_kind="page_evidence_json",
        media_type="application/json",
        sha256=PACKET_SHA256,
        size_bytes=PACKET_SIZE,
        storage_path=f"derived/{run.id}/{page_number}/evidence.json",
    )
    image = TechnicalDerivedArtifact(
        run_id=run.id,
        page_number=page_number,
        artifact_kind="page_image_png",
        media_type="image/png",
        sha256=IMAGE_SHA256,
        size_bytes=IMAGE_SIZE,
        storage_path=f"derived/{run.id}/{page_number}/page.png",
    )
    db.add_all([packet, image])
    db.flush()
    return packet, image


def _accepted_page(
    run: TechnicalExtractionRun,
    packet: TechnicalDerivedArtifact,
    image: TechnicalDerivedArtifact,
    *,
    page_number: int = 1,
    status: str = "completed",
) -> TechnicalExtractionPage:
    now = datetime.now(UTC)
    needs_attention = status == "needs_attention"
    return TechnicalExtractionPage(
        run_id=run.id,
        page_number=page_number,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=page_number),
        status=status,
        attempt_count=1,
        outcome_code=(
            "PAGE_EXTRACTION_NEEDS_ATTENTION" if needs_attention else "PAGE_EXTRACTION_COMPLETE"
        ),
        outcome_retryable=False,
        last_outcome_at=now,
        completed_at=now,
        packet_artifact_id=packet.id,
        packet_artifact_kind="page_evidence_json",
        packet_size_bytes=packet.size_bytes,
        page_image_artifact_id=image.id,
        page_image_artifact_kind="page_image_png",
        page_image_size_bytes=image.size_bytes,
        packet_sha256=packet.sha256,
        page_image_sha256=image.sha256,
        binding_sha256=BINDING_SHA256,
        page_width_points=Decimal("612"),
        page_height_points=Decimal("792"),
        image_width_pixels=8,
        image_height_pixels=6,
        extraction_mode="native_text",
        native_block_count=1,
        ocr_block_count=0,
        minimum_ocr_confidence=None,
        ocr_status="ocr_not_required",
        ocr_low_confidence_threshold=Decimal("80"),
        human_review_required=needs_attention,
    )


def _assert_integrity_error(db: Session, instance: object, match: str | None = None) -> None:
    db.add(instance)
    with pytest.raises(IntegrityError, match=match):
        db.commit()
    db.rollback()


def _schema_signature(inspector, table_name: str) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        "columns": tuple(
            sorted(
                (
                    column["name"],
                    bool(column["nullable"]),
                    str(column["type"]),
                )
                for column in inspector.get_columns(table_name)
            )
        ),
        "checks": tuple(
            sorted(constraint["name"] for constraint in inspector.get_check_constraints(table_name))
        ),
        "foreign_keys": tuple(
            sorted(
                (
                    foreign_key["name"] or "",
                    tuple(foreign_key["constrained_columns"]),
                    foreign_key["referred_table"],
                    tuple(foreign_key["referred_columns"]),
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            )
        ),
        "indexes": tuple(
            sorted(
                (
                    index["name"],
                    tuple(index["column_names"]),
                    bool(index["unique"]),
                )
                for index in inspector.get_indexes(table_name)
            )
        ),
        "unique_constraints": tuple(
            sorted(
                (
                    constraint["name"] or "",
                    tuple(constraint["column_names"]),
                )
                for constraint in inspector.get_unique_constraints(table_name)
            )
        ),
    }


def test_extraction_mappers_have_read_only_unambiguous_provenance_links() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", SAWarning)
        configure_mappers()
    assert not [warning for warning in caught if issubclass(warning.category, SAWarning)]
    assert TechnicalExtractionRun.source_stored_file.property.viewonly
    assert TechnicalExtractionRun.technical_document.property.viewonly


def test_run_identity_is_idempotent_per_document_not_per_file(db: Session) -> None:
    _, source, first_document, second_document = _seed_sources(db)
    first_run = _run(first_document, source)
    db.add(first_run)
    db.commit()

    _assert_integrity_error(db, _run(first_document, source))

    second_run = _run(second_document, source)
    db.add(second_run)
    db.commit()

    other_threshold = _run(first_document, source)
    other_threshold.ocr_low_confidence_threshold = Decimal("75")
    db.add(other_threshold)
    db.commit()

    assert first_run.id != second_run.id
    assert first_run.id != other_threshold.id
    assert first_run.source_sha256 == second_run.source_sha256
    assert first_run.technical_document_id != second_run.technical_document_id


def test_v2_run_identity_includes_runtime_profile_and_preserves_v1(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    legacy = _run(document, source, page_count=None)
    db.add(legacy)
    db.commit()

    first = _v2_run(document, source)
    db.add(first)
    db.commit()

    _assert_integrity_error(db, _v2_run(document, source))

    other_profile = _v2_run(
        document,
        source,
        runtime_profile_sha256="a" * 64,
    )
    db.add(other_profile)
    db.commit()

    missing_profile = _v2_run(document, source)
    missing_profile.runtime_profile_sha256 = None
    _assert_integrity_error(db, missing_profile)

    forged_legacy = _run(document, source, page_count=None)
    forged_legacy.runtime_profile_sha256 = RUNTIME_PROFILE_SHA256
    _assert_integrity_error(db, forged_legacy)

    assert legacy.runtime_profile_sha256 is None
    assert first.id != other_profile.id


def test_v2_layout_requires_bound_runtime_and_successful_receipt_reference(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _v2_run(document, source)
    run.status = "processing"
    run.attempt_token = "10000000-0000-4000-8000-000000000001"  # noqa: S105
    run.attempt_started_at = datetime.now(UTC)
    run.attempt_count = 1
    run.runtime_attestation_sha256 = RUNTIME_ATTESTATION_SHA256
    db.add(run)
    db.commit()

    invocation = _layout_invocation(run)
    db.add(invocation)
    db.commit()

    run.page_count = 1
    run.layout_schema = "technical-parser-layout-v1"
    run.layout_sha256 = LAYOUT_SHA256
    run.layout_size_bytes = 512
    run.layout_invocation_id = "20000000-0000-4000-8000-000000000002"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    receipt = _successful_receipt(invocation)
    db.add(receipt)
    db.commit()
    run.page_count = 1
    run.layout_schema = "technical-parser-layout-v1"
    run.layout_sha256 = LAYOUT_SHA256
    run.layout_size_bytes = 512
    run.layout_invocation_id = invocation.id
    db.commit()

    assert run.layout_invocation_id == receipt.invocation_id
    assert run.runtime_attestation_sha256 == invocation.runtime_attestation_sha256

    run.runtime_attestation_sha256 = "a" * 64
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_invocation_reservation_and_receipt_constraints_fail_closed(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _v2_run(document, source)
    run.status = "processing"
    run.attempt_token = "30000000-0000-4000-8000-000000000003"  # noqa: S105
    run.attempt_started_at = datetime.now(UTC)
    run.attempt_count = 1
    run.runtime_attestation_sha256 = RUNTIME_ATTESTATION_SHA256
    db.add(run)
    db.commit()

    invocation = _layout_invocation(run)
    db.add(invocation)
    db.commit()

    duplicate_attempt = _layout_invocation(run)
    _assert_integrity_error(db, duplicate_attempt)

    invalid_receipt = _successful_receipt(invocation)
    invalid_receipt.cleanup_confirmed = False
    _assert_integrity_error(db, invalid_receipt)

    invalid_not_started = _successful_receipt(invocation)
    invalid_not_started.execution_state = "not_started"
    invalid_not_started.outcome_code = "PARSER_EXECUTION_SUCCEEDED"
    invalid_not_started.container_id = None
    invalid_not_started.started_at = None
    invalid_not_started.exit_code = None
    invalid_not_started.stdout_sha256 = None
    invalid_not_started.stdout_size_bytes = None
    _assert_integrity_error(db, invalid_not_started)

    receipt = _successful_receipt(invocation)
    db.add(receipt)
    db.commit()

    db.expunge(receipt)
    duplicate_receipt = _successful_receipt(invocation)
    _assert_integrity_error(db, duplicate_receipt)

    assert receipt.invocation_id == invocation.id
    assert receipt.execution_state == "succeeded"
    assert receipt.cleanup_confirmed is True


def test_invocation_reservation_accepts_v2_runtime_attestation_and_rejects_unknown_schema(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _v2_run(document, source)
    run.status = "processing"
    run.attempt_token = "31000000-0000-4000-8000-000000000003"  # noqa: S105
    run.attempt_started_at = datetime.now(UTC)
    run.attempt_count = 1
    run.runtime_attestation_sha256 = RUNTIME_ATTESTATION_SHA256
    db.add(run)
    db.commit()

    invocation = _layout_invocation(
        run,
        runtime_attestation_schema="technical-parser-runtime-attestation-v2",
    )
    db.add(invocation)
    db.commit()

    assert invocation.runtime_attestation_schema == (
        "technical-parser-runtime-attestation-v2"
    )
    invocation.runtime_attestation_schema = "technical-parser-runtime-attestation-v3"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_v2_page_acceptance_requires_an_invocation_only_at_terminal_success(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _v2_run(document, source)
    run.status = "processing"
    run.attempt_token = "40000000-0000-4000-8000-000000000004"  # noqa: S105
    run.attempt_started_at = datetime.now(UTC)
    run.attempt_count = 1
    run.runtime_attestation_sha256 = RUNTIME_ATTESTATION_SHA256
    db.add(run)
    db.commit()
    invocation = _layout_invocation(run)
    db.add(invocation)
    db.commit()
    receipt = _successful_receipt(invocation)
    db.add(receipt)
    db.commit()
    run.page_count = 1
    run.layout_schema = "technical-parser-layout-v1"
    run.layout_sha256 = LAYOUT_SHA256
    run.layout_size_bytes = 512
    run.layout_invocation_id = invocation.id
    db.commit()

    pending = TechnicalExtractionPage(
        page_schema="technical-extraction-page-v2",
        run_id=run.id,
        page_number=1,
        page_count=1,
        layout_sha256=LAYOUT_SHA256,
        layout_page_width_points=Decimal("612"),
        layout_page_height_points=Decimal("792"),
        parser_invocation_id=invocation.id,
    )
    _assert_integrity_error(db, pending)

    compatible_pending = TechnicalExtractionPage(
        page_schema="technical-extraction-page-v2",
        run_id=run.id,
        page_number=1,
        page_count=1,
        layout_sha256=LAYOUT_SHA256,
        layout_page_width_points=Decimal("612"),
        layout_page_height_points=Decimal("792"),
    )
    db.add(compatible_pending)
    db.commit()
    assert compatible_pending.parser_invocation_id is None


def test_run_rejects_document_file_hash_and_size_substitution(db: Session) -> None:
    owner, source, first_document, _ = _seed_sources(db)
    other_source = StoredFile(
        original_filename="other.pdf",
        media_type="application/pdf",
        storage_path="technical/other.pdf",
        sha256="9" * 64,
        size_bytes=999,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=owner.id,
        immutable=True,
    )
    db.add(other_source)
    db.commit()

    wrong_file = _run(first_document, other_source)
    _assert_integrity_error(db, wrong_file, "FOREIGN KEY constraint failed")

    wrong_hash = _run(first_document, source)
    wrong_hash.source_sha256 = "8" * 64
    _assert_integrity_error(db, wrong_hash, "FOREIGN KEY constraint failed")

    wrong_size = _run(first_document, source)
    wrong_size.source_size_bytes += 1
    _assert_integrity_error(db, wrong_size, "FOREIGN KEY constraint failed")


def test_failed_run_cannot_claim_a_success_outcome(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    failed = _run(document, source)
    failed.status = "failed"
    failed.attempt_count = 1
    failed.outcome_code = "EXTRACTION_COMPLETE"
    failed.outcome_retryable = False
    failed.last_outcome_at = datetime.now(UTC)
    failed.completed_at = failed.last_outcome_at

    _assert_integrity_error(db, failed)


@pytest.mark.parametrize("threshold", (None, Decimal("-0.01"), Decimal("100.01")))
def test_run_ocr_threshold_is_required_and_range_bound(
    db: Session,
    threshold: Decimal | None,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    run.ocr_low_confidence_threshold = threshold  # type: ignore[assignment]
    _assert_integrity_error(db, run)


def test_layout_binding_is_required_with_page_count_and_page_fk_bound(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    missing_layout = _run(document, source)
    missing_layout.layout_sha256 = None
    _assert_integrity_error(db, missing_layout)

    run = _run(document, source)
    db.add(run)
    db.commit()
    wrong_layout = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=PAGE_COUNT,
        layout_sha256="7" * 64,
        layout_page_width_points=Decimal("612"),
        layout_page_height_points=Decimal("792"),
    )
    _assert_integrity_error(db, wrong_layout, "FOREIGN KEY constraint failed")


def test_cancelled_page_is_terminal_without_outputs(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()
    now = datetime.now(UTC)
    cancelled = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=1),
        status="cancelled",
        outcome_code="PAGE_EXTRACTION_CANCELLED",
        outcome_retryable=False,
        last_outcome_at=now,
        completed_at=now,
    )
    db.add(cancelled)
    db.commit()
    assert cancelled.attempt_count == 0
    assert cancelled.packet_artifact_id is None


def test_run_retry_and_terminal_outcomes_are_schema_bound(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    now = datetime.now(UTC)
    retry = _run(document, source)
    retry.status = "queued"
    retry.attempt_count = 1
    retry.outcome_code = "EXTRACTION_PARSER_TIMEOUT"
    retry.outcome_retryable = True
    retry.last_outcome_at = now
    db.add(retry)
    db.commit()

    retry.outcome_retryable = False
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    other_policy_run = _run(document, source)
    other_policy_run.extraction_policy_sha256 = "7" * 64
    other_policy_run.status = "failed"
    other_policy_run.attempt_count = 1
    other_policy_run.outcome_code = "EXTRACTION_SOURCE_BINDING_FAILED"
    other_policy_run.outcome_retryable = False
    other_policy_run.last_outcome_at = now
    other_policy_run.completed_at = now
    db.add(other_policy_run)
    db.commit()
    assert other_policy_run.status == "failed"
    assert other_policy_run.outcome_retryable is False


def test_page_lifecycle_retains_pending_processing_and_retryable_failure(
    db: Session,
) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()

    pending = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=1),
    )
    db.add(pending)
    db.commit()
    assert pending.status == "pending"
    assert pending.attempt_count == 0
    assert pending.packet_artifact_id is None

    invalid_processing = TechnicalExtractionPage(
        run_id=run.id,
        page_number=2,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=2),
        status="processing",
        attempt_count=1,
    )
    _assert_integrity_error(db, invalid_processing)

    now = datetime.now(UTC)
    retryable_failure = TechnicalExtractionPage(
        run_id=run.id,
        page_number=2,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=2),
        status="failed",
        attempt_count=1,
        outcome_code="PAGE_PARSER_TIMEOUT",
        outcome_retryable=True,
        last_outcome_at=now,
        completed_at=now,
    )
    db.add(retryable_failure)
    db.commit()
    assert retryable_failure.status == "failed"
    assert retryable_failure.outcome_retryable is True
    assert retryable_failure.packet_artifact_id is None


def test_database_allows_only_one_processing_page_per_run(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source, page_count=2)
    db.add(run)
    db.commit()
    first = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=2,
        **_page_layout_values(page_number=1),
        status="processing",
        attempt_token="11111111-1111-4111-8111-111111111111",  # noqa: S106
        attempt_started_at=datetime.now(UTC),
        attempt_count=1,
    )
    db.add(first)
    db.commit()
    second = TechnicalExtractionPage(
        run_id=run.id,
        page_number=2,
        page_count=2,
        **_page_layout_values(page_number=2),
        status="processing",
        attempt_token="22222222-2222-4222-8222-222222222222",  # noqa: S106
        attempt_started_at=datetime.now(UTC),
        attempt_count=1,
    )
    _assert_integrity_error(db, second)


def test_page_count_and_accepted_output_lifecycle_are_schema_bound(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()

    mismatched_count = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=1,
        **_page_layout_values(page_number=1),
    )
    _assert_integrity_error(db, mismatched_count, "FOREIGN KEY constraint failed")

    completed_without_artifacts = TechnicalExtractionPage(
        run_id=run.id,
        page_number=1,
        page_count=PAGE_COUNT,
        **_page_layout_values(page_number=1),
        status="completed",
        attempt_count=1,
        outcome_code="PAGE_EXTRACTION_COMPLETE",
        outcome_retryable=False,
        last_outcome_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
    )
    _assert_integrity_error(db, completed_without_artifacts)

    packet, image = _artifacts(db, run)
    completed = _accepted_page(run, packet, image)
    db.add(completed)
    db.commit()
    assert completed.ocr_status == "ocr_not_required"
    assert completed.human_review_required is False


def test_page_ocr_threshold_must_match_its_run(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()
    packet, image = _artifacts(db, run)
    mismatched = _accepted_page(run, packet, image)
    mismatched.ocr_low_confidence_threshold = Decimal("75")

    _assert_integrity_error(db, mismatched, "FOREIGN KEY constraint failed")


@pytest.mark.parametrize(
    "tamper",
    ("cross_run", "wrong_page", "wrong_kind", "wrong_sha", "wrong_size"),
)
def test_page_artifact_composite_binding_rejects_tampering(
    db: Session,
    tamper: str,
) -> None:
    _, source, first_document, second_document = _seed_sources(db)
    first_run = _run(first_document, source)
    second_run = _run(second_document, source)
    db.add_all([first_run, second_run])
    db.commit()
    first_packet, first_image = _artifacts(db, first_run)

    if tamper == "cross_run":
        packet, image = _artifacts(db, second_run)
        page = _accepted_page(first_run, packet, image)
    elif tamper == "wrong_page":
        packet, image = _artifacts(db, first_run, page_number=2)
        page = _accepted_page(first_run, packet, image, page_number=1)
    elif tamper == "wrong_kind":
        page = _accepted_page(first_run, first_image, first_packet)
    else:
        page = _accepted_page(first_run, first_packet, first_image)
        if tamper == "wrong_sha":
            page.packet_sha256 = "0" * 64
        else:
            page.packet_size_bytes = PACKET_SIZE + 1

    _assert_integrity_error(db, page, "FOREIGN KEY constraint failed")


def test_artifact_kind_media_and_page_ocr_state_fail_closed(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()

    wrong_media = TechnicalDerivedArtifact(
        run_id=run.id,
        page_number=1,
        artifact_kind="page_evidence_json",
        media_type="image/png",
        sha256=PACKET_SHA256,
        size_bytes=PACKET_SIZE,
        storage_path="derived/wrong-media.json",
    )
    _assert_integrity_error(db, wrong_media)

    packet, image = _artifacts(db, run)
    low_confidence = _accepted_page(
        run,
        packet,
        image,
        status="needs_attention",
    )
    low_confidence.extraction_mode = "ocr"
    low_confidence.native_block_count = 0
    low_confidence.ocr_block_count = 1
    low_confidence.minimum_ocr_confidence = Decimal("79.99")
    low_confidence.ocr_status = "low_confidence"
    db.add(low_confidence)
    db.commit()
    assert low_confidence.human_review_required is True


def test_unreadable_page_cannot_claim_ocr_was_not_required(db: Session) -> None:
    _, source, document, _ = _seed_sources(db)
    run = _run(document, source)
    db.add(run)
    db.commit()
    packet, image = _artifacts(db, run)
    unreadable = _accepted_page(
        run,
        packet,
        image,
        status="needs_attention",
    )
    unreadable.extraction_mode = "unreadable"
    unreadable.native_block_count = 0
    unreadable.ocr_block_count = 0
    unreadable.ocr_status = "ocr_not_required"

    _assert_integrity_error(db, unreadable)


def test_postgresql_ddl_contains_exact_composite_guards() -> None:
    run_ddl = str(
        CreateTable(TechnicalExtractionRun.__table__).compile(dialect=postgresql.dialect())
    )
    page_ddl = str(
        CreateTable(TechnicalExtractionPage.__table__).compile(dialect=postgresql.dialect())
    )
    invocation_ddl = str(
        CreateTable(TechnicalParserInvocation.__table__).compile(dialect=postgresql.dialect())
    )
    receipt_ddl = str(
        CreateTable(TechnicalParserInvocationReceipt.__table__).compile(
            dialect=postgresql.dialect()
        )
    )

    assert "fk_technical_extraction_run_document_source" in run_ddl
    assert "fk_technical_extraction_run_source_bytes" in run_ddl
    assert "uq_technical_extraction_run_page_count_binding" in run_ddl
    assert "uq_technical_extraction_run_layout_binding" in run_ddl
    assert "uq_technical_extraction_run_ocr_threshold_binding" in run_ddl
    assert "outcome_retryable" in run_ddl
    assert "last_outcome_at" in run_ddl
    assert "ocr_low_confidence_threshold" in run_ddl
    assert "layout_sha256" in run_ddl
    assert "runtime_profile_sha256" in run_ddl
    assert "runtime_attestation_sha256" in run_ddl
    assert "layout_invocation_id" in run_ddl
    assert "ck_technical_extraction_run_runtime_provenance" in run_ddl
    assert "uq_technical_extraction_run_runtime_binding" in run_ddl
    assert "fk_technical_extraction_page_run_page_count" in page_ddl
    assert "fk_technical_extraction_page_run_layout" in page_ddl
    assert "fk_technical_extraction_page_run_ocr_threshold" in page_ddl
    assert "fk_technical_extraction_page_packet_binding" in page_ddl
    assert "fk_technical_extraction_page_image_binding" in page_ddl
    assert "packet_size_bytes" in page_ddl
    assert "ocr_status" in page_ddl
    assert "layout_page_width_points" in page_ddl
    assert "PAGE_EXTRACTION_CANCELLED" in page_ddl
    assert "parser_invocation_id" in page_ddl
    assert "ck_technical_extraction_page_parser_provenance" in page_ddl
    assert "uq_technical_extraction_page_identity_binding" in page_ddl
    assert "uq_technical_extraction_page_parser_invocation" in page_ddl
    assert "uq_technical_extraction_pages_processing_run" in {
        index.name for index in TechnicalExtractionPage.__table__.indexes
    }
    assert "fk_technical_parser_invocation_run_runtime" in invocation_ddl
    assert "ck_technical_parser_invocation_operation" in invocation_ddl
    assert "technical-parser-runtime-attestation-v1" in invocation_ddl
    assert "technical-parser-runtime-attestation-v2" in invocation_ddl
    assert "uq_technical_parser_invocation_attempt_token" in invocation_ddl
    assert "uq_technical_parser_invocation_receipt_binding" in invocation_ddl
    assert "fk_technical_parser_invocation_receipt_reservation" in receipt_ddl
    assert "ck_technical_parser_invocation_receipt_lifecycle" in receipt_ddl
    assert "execution_unknown" in receipt_ddl
    assert "containment_lost" in receipt_ddl
    assert {
        foreign_key.name for foreign_key in TechnicalExtractionRun.__table__.foreign_key_constraints
    } >= {"fk_technical_extraction_run_layout_invocation"}
    assert {
        foreign_key.name
        for foreign_key in TechnicalExtractionPage.__table__.foreign_key_constraints
    } >= {"fk_technical_extraction_page_parser_invocation"}
    assert {
        foreign_key.name
        for foreign_key in TechnicalParserInvocation.__table__.foreign_key_constraints
    } >= {"fk_technical_parser_invocation_page"}


def test_parser_provenance_migrations_preserve_v1_and_legacy_unknown_rows(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "technical-extraction-foundation.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)
    _upgrade(database_url, environment, "0013_technical_intake_batches")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users "
                "(id, created_at, updated_at, record_version, email, full_name, "
                "password_hash, role, is_active) VALUES "
                "('migration-owner', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 7, "
                "'migration-owner@example.test', 'Migration Owner', 'unused', "
                "'technical_reviewer', 1)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO stored_files "
                "(id, created_at, updated_at, record_version, original_filename, "
                "media_type, storage_path, sha256, size_bytes, purpose, "
                "malware_scan_status, uploaded_by_id, immutable) VALUES "
                "('migration-file', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 5, "
                "'source.pdf', 'application/pdf', 'technical/source.pdf', :sha, "
                ":size, 'technical_evidence', 'clean', 'migration-owner', 1)"
            ),
            {"sha": SOURCE_SHA256, "size": SOURCE_SIZE},
        )
        connection.execute(
            text(
                "INSERT INTO technical_documents "
                "(id, created_at, updated_at, record_version, document_id, "
                "stored_file_id, document_type, title, status, extraction_status) "
                "VALUES ('migration-document', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "9, 'TECH-MIGRATION-001', 'migration-file', 'assessment', "
                "'Migration source', 'draft', 'not_started')"
            )
        )

    _upgrade(
        database_url,
        environment,
        "0014_technical_extraction_foundation",
        enforce_sqlite_foreign_keys=True,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO technical_extraction_runs "
                "(id, created_at, updated_at, record_version, run_schema, "
                "source_stored_file_id, technical_document_id, source_sha256, "
                "source_size_bytes, extraction_policy, extraction_policy_sha256, "
                "ocr_low_confidence_threshold, worker_image_digest, "
                "page_evidence_schema, status, attempt_count, requested_by_id) "
                "VALUES ('10000000-0000-4000-8000-000000000001', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 3, "
                "'technical-extraction-run-v1', 'migration-file', "
                "'migration-document', :source_sha256, :source_size, "
                "'technical-extraction-policy-v1', :policy_sha256, 80, "
                ":worker_digest, 'technical-page-evidence-v1', 'queued', 0, "
                "'migration-owner')"
            ),
            {
                "source_sha256": SOURCE_SHA256,
                "source_size": SOURCE_SIZE,
                "policy_sha256": POLICY_SHA256,
                "worker_digest": WORKER_DIGEST,
            },
        )

    _upgrade(
        database_url,
        environment,
        "0015_technical_parser_invocation_provenance",
        enforce_sqlite_foreign_keys=True,
    )
    with Session(engine, expire_on_commit=False) as migration_db:
        source = migration_db.get(StoredFile, "migration-file")
        document = migration_db.get(TechnicalDocument, "migration-document")
        assert source is not None
        assert document is not None
        provenance_run = _v2_run(document, source)
        provenance_run.id = "20000000-0000-4000-8000-000000000002"
        provenance_run.status = "processing"
        provenance_run.attempt_token = "30000000-0000-4000-8000-000000000003"  # noqa: S105
        provenance_run.attempt_started_at = datetime.now(UTC)
        provenance_run.attempt_count = 1
        provenance_run.runtime_attestation_sha256 = RUNTIME_ATTESTATION_SHA256
        migration_db.add(provenance_run)
        migration_db.commit()

        provenance_invocation = _layout_invocation(provenance_run)
        provenance_invocation.id = "40000000-0000-4000-8000-000000000004"
        migration_db.add(provenance_invocation)
        migration_db.commit()
        migration_db.add(_legacy_execution_unknown_receipt(provenance_invocation))
        migration_db.commit()

    with engine.connect() as connection:
        invocation_before_v2_migration = connection.execute(
            text(
                "SELECT id, run_id, operation, page_number, request_sha256, "
                "runtime_attestation_schema, runtime_attestation_json, "
                "runtime_attestation_sha256, immutable, record_version "
                "FROM technical_parser_invocations "
                "WHERE id='40000000-0000-4000-8000-000000000004'"
            )
        ).one()
        receipt_before_v2_migration = connection.execute(
            text(
                "SELECT invocation_id, run_id, execution_state, outcome_code, "
                "container_id, started_at, completed_at, exit_code, "
                "stdout_sha256, stdout_size_bytes, receipt_json, receipt_sha256, "
                "cleanup_confirmed, immutable "
                "FROM technical_parser_invocation_receipts "
                "WHERE invocation_id='40000000-0000-4000-8000-000000000004'"
            )
        ).one()

    _upgrade(
        database_url,
        environment,
        "head",
        enforce_sqlite_foreign_keys=True,
    )
    inspector = inspect(engine)
    model_engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(model_engine)
    model_inspector = inspect(model_engine)
    for table_name in (
        "stored_files",
        "technical_documents",
        "technical_extraction_runs",
        "technical_derived_artifacts",
        "technical_extraction_pages",
        "technical_parser_invocations",
        "technical_parser_invocation_receipts",
    ):
        assert _schema_signature(inspector, table_name) == _schema_signature(
            model_inspector,
            table_name,
        )
    for model in (
        TechnicalExtractionRun,
        TechnicalDerivedArtifact,
        TechnicalExtractionPage,
        TechnicalParserInvocation,
        TechnicalParserInvocationReceipt,
    ):
        assert {column.name for column in model.__table__.columns} == {
            column["name"] for column in inspector.get_columns(model.__tablename__)
        }
    assert {
        "technical_extraction_runs",
        "technical_derived_artifacts",
        "technical_extraction_pages",
        "technical_parser_invocations",
        "technical_parser_invocation_receipts",
    }.issubset(inspector.get_table_names())
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            CLEAN_STACK_HEAD
        )
        assert (
            connection.execute(
                text("SELECT record_version FROM technical_documents WHERE id='migration-document'")
            ).scalar_one()
            == 9
        )
        legacy = connection.execute(
            text(
                "SELECT run_schema, runtime_profile_sha256, "
                "runtime_attestation_sha256, layout_invocation_id, record_version "
                "FROM technical_extraction_runs "
                "WHERE id='10000000-0000-4000-8000-000000000001'"
            )
        ).one()
        assert legacy == ("technical-extraction-run-v1", None, None, None, 3)
        assert (
            connection.execute(
                text(
                    "SELECT id, run_id, operation, page_number, request_sha256, "
                    "runtime_attestation_schema, runtime_attestation_json, "
                    "runtime_attestation_sha256, immutable, record_version "
                    "FROM technical_parser_invocations "
                    "WHERE id='40000000-0000-4000-8000-000000000004'"
                )
            ).one()
            == invocation_before_v2_migration
        )
        assert (
            connection.execute(
                text(
                    "SELECT invocation_id, run_id, execution_state, outcome_code, "
                    "container_id, started_at, completed_at, exit_code, "
                    "stdout_sha256, stdout_size_bytes, receipt_json, receipt_sha256, "
                    "cleanup_confirmed, immutable "
                    "FROM technical_parser_invocation_receipts "
                    "WHERE invocation_id='40000000-0000-4000-8000-000000000004'"
                )
            ).one()
            == receipt_before_v2_migration
        )
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []

    rejected = _run_migration(
        database_url,
        environment,
        "downgrade",
        "0014_technical_extraction_foundation",
        expect_success=False,
    )
    assert rejected.returncode != 0
    assert "Technical parser runtime attestation v2 may already be retained" in (
        rejected.stdout + rejected.stderr
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            CLEAN_STACK_HEAD
        )
