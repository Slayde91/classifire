from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    Approval,
    AuditEvent,
    LibraryRelease,
    StoredFile,
    TechnicalDerivedArtifact,
    TechnicalDocument,
    TechnicalExtractionPage,
    TechnicalExtractionRun,
    TechnicalParserInvocation,
    TechnicalParserInvocationReceipt,
    TechnicalVariant,
    User,
)
from classifire.services.technical_extraction import (
    TechnicalExtractionError,
    TechnicalExtractionLayoutBinding,
    TechnicalExtractionPageLayoutBinding,
    TechnicalExtractionRunClaim,
    claim_next_stale_technical_parser_invocation,
    claim_next_technical_extraction_run,
    claim_technical_extraction_page,
    count_unsettled_technical_parser_invocations,
    finalize_technical_parser_invocation_reconciliation,
    initialize_technical_extraction_pages,
    record_technical_parser_invocation_receipt,
    request_technical_extraction_run,
    reserve_technical_parser_invocation,
)
from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_SUCCESS,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionReceipt,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
)
from classifire.services.technical_parser_oci import (
    TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    TechnicalParserOciCleanupProof,
)
from classifire.services.technical_parser_protocol import (
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
)

SOURCE_SHA = "a" * 64
WORKER_SHA = "b" * 64
LAYOUT_SHA = "c" * 64
RUNTIME_PROFILE_SHA = "d" * 64
RUNTIME_EXECUTABLE_SHA = "e" * 64
SECCOMP_SHA = "f" * 64
DAEMON_SHA = "1" * 64
FENCE_SHA = "2" * 64
IMAGE_ID = f"sha256:{'3' * 64}"
CONTAINER_ID = "4" * 64
OWNER_ID = "11111111-1111-4111-8111-111111111111"
POLICY = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"schema":"technical-extraction-policy-v1"}'
START = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)
STALE = START + timedelta(minutes=16)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _seed_run(db: Session) -> TechnicalExtractionRunClaim:
    actor = User(
        email="reconciliation@example.test",
        full_name="Reconciliation Worker",
        password_hash="unused",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(actor)
    db.flush()
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path="retained/source.pdf",
        sha256=SOURCE_SHA,
        size_bytes=4096,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=actor.id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-RECONCILIATION",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Reconciliation source",
    )
    db.add(document)
    db.commit()
    request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    return claim


def _attestation(claim: TechnicalExtractionRunClaim) -> TechnicalParserRuntimeAttestation:
    return create_technical_parser_runtime_attestation(
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        engine="oci",
        claims={
            "controller_owner_id": OWNER_ID,
            "execution_fence_sha256": FENCE_SHA,
            "extraction_policy": claim.extraction_policy,
            "extraction_policy_sha256": claim.extraction_policy_sha256,
            "image_id": IMAGE_ID,
            "image_reference": (
                f"registry.example/classifire/parser@sha256:{claim.worker_image_digest}"
            ),
            "oci_daemon_identity_sha256": DAEMON_SHA,
            "oci_profile_schema": "technical-parser-oci-profile-v1",
            "platform": "linux/amd64",
            "runtime_executable_sha256": RUNTIME_EXECUTABLE_SHA,
            "runtime_host": "unix:///run/user/1000/docker.sock",
            "runtime_profile_sha256": claim.runtime_profile_sha256,
            "seccomp_profile_sha256": SECCOMP_SHA,
            "transport_schema": "technical-parser-stdin-frame-v1",
            "worker_image_digest": claim.worker_image_digest,
        },
    )


def _v1_attestation(
    claim: TechnicalExtractionRunClaim,
) -> TechnicalParserRuntimeAttestation:
    payload = _attestation(claim).as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    legacy_claims = dict(claims)
    legacy_claims.pop("execution_fence_sha256")
    legacy_claims.pop("oci_daemon_identity_sha256")
    return create_technical_parser_runtime_attestation(
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1,
        engine="oci",
        claims=legacy_claims,
    )


def _layout() -> TechnicalExtractionLayoutBinding:
    return TechnicalExtractionLayoutBinding(
        schema="technical-parser-layout-v1",
        sha256=LAYOUT_SHA,
        size_bytes=512,
        page_count=2,
        pages=tuple(
            TechnicalExtractionPageLayoutBinding(
                page_number=number,
                page_count=2,
                width_points=Decimal("612"),
                height_points=Decimal("792"),
            )
            for number in (1, 2)
        ),
    )


def _layout_request(claim: TechnicalExtractionRunClaim) -> bytes:
    return bytes(
        encode_technical_parser_layout_request(
            technical_document_id=claim.technical_document_id,
            source_sha256=claim.source_sha256,
            source_size_bytes=claim.source_size_bytes,
            extraction_policy=claim.extraction_policy,
            extraction_policy_sha256=claim.extraction_policy_sha256,
            worker_image_digest=claim.worker_image_digest,
            ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
        )
    )


def _success_receipt(
    reservation_id: str,
    *,
    operation: str,
    attestation: TechnicalParserRuntimeAttestation,
    stdout_sha256: str,
    stdout_size_bytes: int,
) -> TechnicalParserExecutionReceipt:
    return create_technical_parser_execution_receipt(
        execution_state="succeeded",
        operation=operation,  # type: ignore[arg-type]
        invocation_id=reservation_id,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code=TECHNICAL_PARSER_EXECUTION_SUCCESS,
        container_id=CONTAINER_ID,
        started_at=START + timedelta(seconds=1),
        completed_at=START + timedelta(seconds=2),
        exit_code=0,
        stdout_sha256=stdout_sha256,
        stdout_size_bytes=stdout_size_bytes,
        cleanup_confirmed=True,
    )


def _containment_lost_receipt(
    reservation_id: str,
    *,
    operation: str,
    attestation: TechnicalParserRuntimeAttestation,
) -> TechnicalParserExecutionReceipt:
    return create_technical_parser_execution_receipt(
        execution_state="containment_lost",
        operation=operation,  # type: ignore[arg-type]
        invocation_id=reservation_id,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code="PARSER_EXECUTION_CONTAINMENT_LOST",
        container_id=CONTAINER_ID,
        started_at=START + timedelta(seconds=1),
        completed_at=START + timedelta(seconds=2),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=False,
    )


def _make_stale(db: Session, invocation_id: str, *, receipt: bool = False) -> None:
    invocation = db.get(TechnicalParserInvocation, invocation_id)
    assert invocation is not None
    invocation.created_at = START
    run = db.get(TechnicalExtractionRun, invocation.run_id)
    assert run is not None
    run.attempt_started_at = START
    if invocation.page_id is not None:
        page = db.get(TechnicalExtractionPage, invocation.page_id)
        assert page is not None
        page.attempt_started_at = START
    if receipt:
        persisted = db.get(TechnicalParserInvocationReceipt, invocation_id)
        assert persisted is not None
        persisted.created_at = START
    db.commit()


def _cleanup_proof(
    *,
    invocation_id: str,
    attestation: TechnicalParserRuntimeAttestation,
    completed_at: datetime,
    observed_container_id: str | None = None,
    observed_container_state: str | None = None,
) -> TechnicalParserOciCleanupProof:
    payload = {
        "cleanup_confirmed": True,
        "completed_at": completed_at.isoformat(timespec="microseconds").replace(
            "+00:00",
            "Z",
        ),
        "controller_owner_id": OWNER_ID,
        "execution_fence_sha256": FENCE_SHA,
        "invocation_id": invocation_id,
        "observed_container_id": observed_container_id,
        "observed_container_state": observed_container_state,
        "oci_daemon_identity_sha256": DAEMON_SHA,
        "runtime_attestation_sha256": attestation.sha256,
        "runtime_profile_sha256": RUNTIME_PROFILE_SHA,
        "schema": TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    }
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return TechnicalParserOciCleanupProof(
        schema=TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
        invocation_id=invocation_id,
        runtime_attestation_sha256=attestation.sha256,
        controller_owner_id=OWNER_ID,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
        oci_daemon_identity_sha256=DAEMON_SHA,
        execution_fence_sha256=FENCE_SHA,
        observed_container_id=observed_container_id,
        observed_container_state=observed_container_state,
        cleanup_confirmed=True,
        completed_at=completed_at,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _reserve_layout(
    db: Session,
    claim: TechnicalExtractionRunClaim,
) -> tuple[str, TechnicalParserRuntimeAttestation]:
    attestation = _attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    return reservation.invocation_id, attestation


def _initialized_run(
    db: Session,
) -> tuple[TechnicalExtractionRunClaim, TechnicalParserRuntimeAttestation]:
    claim = _seed_run(db)
    attestation = _attestation(claim)
    layout = _layout()
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    receipt = _success_receipt(
        reservation.invocation_id,
        operation="layout",
        attestation=attestation,
        stdout_sha256=layout.sha256,
        stdout_size_bytes=layout.size_bytes,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    initialized = initialize_technical_extraction_pages(
        db,
        claim=reservation.run_claim,
        layout=layout,
        parser_invocation_id=reservation.invocation_id,
        now=START + timedelta(seconds=3),
    )
    return initialized.run_claim, attestation


def test_claim_requires_staleness_and_renews_the_exact_lease(db: Session) -> None:
    run_claim = _seed_run(db)
    invocation_id, _attestation_value = _reserve_layout(db, run_claim)
    _make_stale(db, invocation_id)

    assert count_unsettled_technical_parser_invocations(db) == 1
    assert (
        claim_next_stale_technical_parser_invocation(
            db,
            now=START + timedelta(minutes=14),
        )
        is None
    )

    claimed = claim_next_stale_technical_parser_invocation(db, now=STALE)

    assert claimed is not None
    assert claimed.invocation_id == invocation_id
    assert claimed.operation == "layout"
    assert claimed.page_claim is None
    assert claimed.run_claim.record_version == run_claim.record_version + 2
    assert claimed.run_claim.attempt_started_at == STALE
    assert count_unsettled_technical_parser_invocations(db) == 1
    assert claim_next_stale_technical_parser_invocation(db, now=STALE) is None


def test_receiptless_layout_becomes_execution_unknown_atomically(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_claim = _seed_run(db)
    invocation_id, attestation = _reserve_layout(db, run_claim)
    _make_stale(db, invocation_id)
    claim = claim_next_stale_technical_parser_invocation(db, now=STALE)
    assert claim is not None
    proof = _cleanup_proof(
        invocation_id=invocation_id,
        attestation=attestation,
        completed_at=STALE + timedelta(seconds=1),
    )

    original_commit = db.commit
    commit_count = 0

    def counted_commit() -> None:
        nonlocal commit_count
        commit_count += 1
        original_commit()

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "commit", counted_commit)
        result = finalize_technical_parser_invocation_reconciliation(
            db,
            claim=claim,
            cleanup_proof=proof,
            now=STALE + timedelta(seconds=2),
        )

    assert commit_count == 1
    receipt = db.get(TechnicalParserInvocationReceipt, invocation_id)
    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert receipt is not None
    assert receipt.execution_state == "execution_unknown"
    assert receipt.outcome_code == "PARSER_EXECUTION_OUTCOME_UNKNOWN"
    assert receipt.cleanup_confirmed is True
    assert result.execution_state == "execution_unknown"
    assert result.run_outcome_code == "EXTRACTION_PARSER_EXECUTION_UNKNOWN"
    assert run is not None
    assert run.status == "failed"
    assert run.outcome_retryable is False
    assert count_unsettled_technical_parser_invocations(db) == 0
    assert db.scalar(select(func.count(TechnicalDerivedArtifact.id))) == 0
    assert db.scalar(select(func.count(TechnicalVariant.id))) == 0
    assert db.scalar(select(func.count(Approval.id))) == 0
    assert db.scalar(select(func.count(LibraryRelease.id))) == 0


def test_existing_success_receipt_is_failed_as_lost_output(db: Session) -> None:
    claim = _seed_run(db)
    attestation = _attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    receipt = _success_receipt(
        reservation.invocation_id,
        operation="layout",
        attestation=attestation,
        stdout_sha256=LAYOUT_SHA,
        stdout_size_bytes=512,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    _make_stale(db, reservation.invocation_id, receipt=True)
    reconciliation_claim = claim_next_stale_technical_parser_invocation(
        db,
        now=STALE,
    )
    assert reconciliation_claim is not None

    result = finalize_technical_parser_invocation_reconciliation(
        db,
        claim=reconciliation_claim,
        now=STALE + timedelta(seconds=1),
    )

    assert result.execution_state == "succeeded"
    assert result.run_outcome_code == "EXTRACTION_PARSER_OUTPUT_LOST_AFTER_SUCCESS"
    assert result.receipt_sha256 == receipt.sha256
    assert db.scalar(select(func.count(TechnicalParserInvocationReceipt.invocation_id))) == 1


def test_containment_lost_receipt_requires_cleanup_proof_before_terminalization(
    db: Session,
) -> None:
    run_claim = _seed_run(db)
    attestation = _attestation(run_claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=run_claim,
        operation="layout",
        request=_layout_request(run_claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    receipt = _containment_lost_receipt(
        reservation.invocation_id,
        operation="layout",
        attestation=attestation,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    _make_stale(db, reservation.invocation_id, receipt=True)
    reconciliation_claim = claim_next_stale_technical_parser_invocation(
        db,
        now=STALE,
    )
    assert reconciliation_claim is not None

    with pytest.raises(TechnicalExtractionError) as rejected:
        finalize_technical_parser_invocation_reconciliation(
            db,
            claim=reconciliation_claim,
            now=STALE + timedelta(seconds=1),
        )

    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    persisted = db.get(
        TechnicalParserInvocationReceipt,
        reservation.invocation_id,
    )
    assert rejected.value.code == "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED"
    assert run is not None
    assert run.status == "processing"
    assert run.attempt_token == reconciliation_claim.run_claim.attempt_token
    assert persisted is not None
    assert persisted.execution_state == "containment_lost"
    assert persisted.cleanup_confirmed is False
    assert count_unsettled_technical_parser_invocations(db) == 1


def test_page_reconciliation_fails_active_page_and_cancels_unfinished_pages(
    db: Session,
) -> None:
    run_claim, attestation = _initialized_run(db)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=4),
    )
    request = encode_technical_parser_request(
        technical_document_id=run_claim.technical_document_id,
        source_sha256=run_claim.source_sha256,
        source_size_bytes=run_claim.source_size_bytes,
        page_number=page_claim.page_number,
        page_count=page_claim.page_count,
        page_width_points=page_claim.layout_page_width_points,
        page_height_points=page_claim.layout_page_height_points,
        layout_sha256=page_claim.layout_sha256,
        extraction_policy=run_claim.extraction_policy,
        extraction_policy_sha256=run_claim.extraction_policy_sha256,
        worker_image_digest=run_claim.worker_image_digest,
        ocr_low_confidence_threshold=run_claim.ocr_low_confidence_threshold,
    )
    reservation = reserve_technical_parser_invocation(
        db,
        claim=page_claim.run_claim,
        page_claim=page_claim,
        operation="page",
        request=request,
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(seconds=5),
    )
    receipt = _success_receipt(
        reservation.invocation_id,
        operation="page",
        attestation=attestation,
        stdout_sha256="5" * 64,
        stdout_size_bytes=128,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    _make_stale(db, reservation.invocation_id, receipt=True)
    reconciliation_claim = claim_next_stale_technical_parser_invocation(
        db,
        now=STALE,
    )
    assert reconciliation_claim is not None
    assert reconciliation_claim.page_claim is not None

    result = finalize_technical_parser_invocation_reconciliation(
        db,
        claim=reconciliation_claim,
        now=STALE + timedelta(seconds=1),
    )

    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_claim.run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert run is not None
    assert run.status == "failed"
    assert pages[0].status == "failed"
    assert pages[0].outcome_code == "PAGE_PARSER_OUTPUT_LOST_AFTER_SUCCESS"
    assert pages[0].parser_invocation_id is None
    assert pages[1].status == "cancelled"
    assert result.cancelled_page_count == 1
    assert result.preserved_page_count == 0


def test_cleanup_proof_mismatch_leaves_no_synthetic_receipt(db: Session) -> None:
    run_claim = _seed_run(db)
    invocation_id, attestation = _reserve_layout(db, run_claim)
    _make_stale(db, invocation_id)
    claim = claim_next_stale_technical_parser_invocation(db, now=STALE)
    assert claim is not None
    proof = _cleanup_proof(
        invocation_id=invocation_id,
        attestation=attestation,
        completed_at=STALE + timedelta(seconds=1),
    )
    object.__setattr__(proof, "execution_fence_sha256", "9" * 64)

    with pytest.raises(TechnicalExtractionError) as error:
        finalize_technical_parser_invocation_reconciliation(
            db,
            claim=claim,
            cleanup_proof=proof,
            now=STALE + timedelta(seconds=2),
        )

    assert error.value.code == "EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID"
    assert db.get(TechnicalParserInvocationReceipt, invocation_id) is None
    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert run is not None
    assert run.status == "processing"
    assert db.scalar(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.action
            == "finalize_technical_parser_invocation_reconciliation"
        )
    ) == 0


def test_v1_receiptless_invocation_cannot_synthesize_unknown_receipt(
    db: Session,
) -> None:
    run_claim = _seed_run(db)
    attestation = _v1_attestation(run_claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=run_claim,
        operation="layout",
        request=_layout_request(run_claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    _make_stale(db, reservation.invocation_id)
    claim = claim_next_stale_technical_parser_invocation(db, now=STALE)
    assert claim is not None
    proof = _cleanup_proof(
        invocation_id=reservation.invocation_id,
        attestation=attestation,
        completed_at=STALE + timedelta(seconds=1),
    )

    with pytest.raises(TechnicalExtractionError) as error:
        finalize_technical_parser_invocation_reconciliation(
            db,
            claim=claim,
            cleanup_proof=proof,
            now=STALE + timedelta(seconds=2),
        )

    assert error.value.code == "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED"
    assert (
        db.get(
            TechnicalParserInvocationReceipt,
            reservation.invocation_id,
        )
        is None
    )


def test_v2_reservation_rejects_an_incomplete_claim_set(db: Session) -> None:
    claim = _seed_run(db)
    payload = _attestation(claim).as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    incomplete_claims = dict(claims)
    incomplete_claims.pop("execution_fence_sha256")
    incomplete = create_technical_parser_runtime_attestation(
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        engine="oci",
        claims=incomplete_claims,
    )

    with pytest.raises(TechnicalExtractionError) as error:
        reserve_technical_parser_invocation(
            db,
            claim=claim,
            operation="layout",
            request=_layout_request(claim),
            runtime_attestation=incomplete,
            invocation_id=str(uuid4()),
            now=START,
        )

    assert error.value.code == "EXTRACTION_RUNTIME_ATTESTATION_INVALID"
    assert db.scalar(select(func.count(TechnicalParserInvocation.id))) == 0


def test_finalizer_reconciles_commit_acknowledgement_loss(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_claim = _seed_run(db)
    invocation_id, attestation = _reserve_layout(db, run_claim)
    _make_stale(db, invocation_id)
    claim = claim_next_stale_technical_parser_invocation(db, now=STALE)
    assert claim is not None
    proof = _cleanup_proof(
        invocation_id=invocation_id,
        attestation=attestation,
        completed_at=STALE + timedelta(seconds=1),
    )
    original_commit = db.commit

    def commit_then_raise() -> None:
        original_commit()
        raise SQLAlchemyError("database acknowledgement lost after commit")

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "commit", commit_then_raise)
        result = finalize_technical_parser_invocation_reconciliation(
            db,
            claim=claim,
            cleanup_proof=proof,
            now=STALE + timedelta(seconds=2),
        )

    assert result.idempotent_replay is True
    assert result.execution_state == "execution_unknown"
    assert (
        db.scalar(
            select(func.count(TechnicalParserInvocationReceipt.invocation_id))
        )
        == 1
    )


def test_v2_not_started_receipt_allows_only_daemon_and_image_drift(
    db: Session,
) -> None:
    claim = _seed_run(db)
    reserved_attestation = _attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=reserved_attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    payload = reserved_attestation.as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    observed_claims = dict(claims)
    observed_claims["image_id"] = f"sha256:{'6' * 64}"
    observed_claims["oci_daemon_identity_sha256"] = "7" * 64
    observed_attestation = create_technical_parser_runtime_attestation(
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        engine="oci",
        claims=observed_claims,
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation="layout",
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=reserved_attestation.sha256,
        attestation=observed_attestation,
        outcome_code="PARSER_EXECUTION_FAILED",
        container_id=None,
        started_at=None,
        completed_at=START + timedelta(seconds=1),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )

    binding = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )

    assert binding.execution_state == "not_started"


def test_v2_not_started_receipt_rejects_fence_drift(db: Session) -> None:
    claim = _seed_run(db)
    reserved_attestation = _attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=reserved_attestation,
        invocation_id=str(uuid4()),
        now=START,
    )
    payload = reserved_attestation.as_dict()
    claims = payload["claims"]
    assert isinstance(claims, dict)
    observed_claims = dict(claims)
    observed_claims["execution_fence_sha256"] = "8" * 64
    observed_attestation = create_technical_parser_runtime_attestation(
        schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        engine="oci",
        claims=observed_claims,
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation="layout",
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=reserved_attestation.sha256,
        attestation=observed_attestation,
        outcome_code="PARSER_EXECUTION_FAILED",
        container_id=None,
        started_at=None,
        completed_at=START + timedelta(seconds=1),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )

    with pytest.raises(TechnicalExtractionError) as error:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=receipt,
        )

    assert error.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    assert (
        db.get(
            TechnicalParserInvocationReceipt,
            reservation.invocation_id,
        )
        is None
    )
