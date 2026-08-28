from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal
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
    TechnicalExtractionPageClaim,
    TechnicalExtractionPageLayoutBinding,
    TechnicalExtractionRunClaim,
    TechnicalExtractionSourceSnapshot,
    TechnicalParserInvocationReservation,
    abort_technical_extraction_run,
    aggregate_technical_extraction_run,
    claim_next_technical_extraction_run,
    claim_technical_extraction_page,
    complete_technical_extraction_page,
    confirm_technical_extraction_source_snapshot,
    fail_technical_extraction_page,
    fail_technical_extraction_run,
    get_claimed_technical_extraction_source_snapshot,
    heartbeat_technical_extraction_page,
    heartbeat_technical_extraction_run,
    initialize_technical_extraction_pages,
    record_technical_parser_invocation_receipt,
    release_technical_extraction_run_for_retry,
    request_technical_extraction_run,
    reserve_technical_parser_invocation,
    verify_technical_extraction_manifest,
)
from classifire.services.technical_extraction_artifacts import (
    RetainedTechnicalPageArtifacts,
    cleanup_retained_technical_page_artifacts,
    retain_validated_technical_page_artifacts,
)
from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_SUCCESS,
    TechnicalParserExecutionReceipt,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
)
from classifire.services.technical_parser_protocol import (
    TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
)

SOURCE_SHA = "a" * 64
WORKER_SHA = "b" * 64
LAYOUT_SHA = "c" * 64
POLICY = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"schema":"technical-extraction-policy-v1"}'
RUNTIME_PROFILE_SHA = "d" * 64
RUNTIME_EXECUTABLE_SHA = "e" * 64
SECCOMP_PROFILE_SHA = "f" * 64
CONTROLLER_OWNER_ID = "11111111-1111-4111-8111-111111111111"
IMAGE_ID = f"sha256:{'1' * 64}"
CONTAINER_ID = "2" * 64
START = datetime(2026, 8, 28, 1, 0, tzinfo=UTC)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _seed(db: Session) -> tuple[User, StoredFile, TechnicalDocument]:
    actor = User(
        email="extraction-service@example.test",
        full_name="Extraction Service",
        password_hash="unused",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(actor)
    db.flush()
    source = StoredFile(
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
    db.add(source)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-EXTRACTION-SERVICE",
        stored_file_id=source.id,
        document_type="assessment",
        title="Extraction service source",
    )
    db.add(document)
    db.commit()
    return actor, source, document


def _request(
    db: Session,
    actor: User,
    document: TechnicalDocument,
) -> str:
    return request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    ).run_id


def _snapshot(
    db: Session,
    claim: TechnicalExtractionRunClaim,
) -> TechnicalExtractionSourceSnapshot:
    return get_claimed_technical_extraction_source_snapshot(db, claim=claim)


def _new_run_claim(db: Session) -> TechnicalExtractionRunClaim:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    return claim


def _layout(
    *,
    page_count: int = 2,
    sha256: str = LAYOUT_SHA,
    width_points: Decimal = Decimal("612"),
    height_points: Decimal = Decimal("792"),
) -> TechnicalExtractionLayoutBinding:
    return TechnicalExtractionLayoutBinding(
        schema="technical-parser-layout-v1",
        sha256=sha256,
        size_bytes=512,
        page_count=page_count,
        pages=tuple(
            TechnicalExtractionPageLayoutBinding(
                page_number=page_number,
                page_count=page_count,
                width_points=width_points,
                height_points=height_points,
            )
            for page_number in range(1, page_count + 1)
        ),
    )


def _layout_request(
    claim: TechnicalExtractionRunClaim,
    *,
    ocr_low_confidence_threshold: Decimal | None = None,
) -> bytes:
    return encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=(
            claim.ocr_low_confidence_threshold
            if ocr_low_confidence_threshold is None
            else ocr_low_confidence_threshold
        ),
    )


def _runtime_attestation(
    claim: TechnicalExtractionRunClaim,
    **overrides: object,
) -> TechnicalParserRuntimeAttestation:
    claims: dict[str, object] = {
        "controller_owner_id": CONTROLLER_OWNER_ID,
        "extraction_policy": claim.extraction_policy,
        "extraction_policy_sha256": claim.extraction_policy_sha256,
        "image_id": IMAGE_ID,
        "image_reference": (
            f"registry.example/classifire/parser@sha256:{claim.worker_image_digest}"
        ),
        "oci_profile_schema": "technical-parser-oci-profile-v1",
        "platform": "linux/amd64",
        "runtime_executable_sha256": RUNTIME_EXECUTABLE_SHA,
        "runtime_host": "unix:///run/user/1000/docker.sock",
        "runtime_profile_sha256": claim.runtime_profile_sha256,
        "seccomp_profile_sha256": SECCOMP_PROFILE_SHA,
        "transport_schema": "technical-parser-stdin-frame-v1",
        "worker_image_digest": claim.worker_image_digest,
    }
    claims.update(overrides)
    return create_technical_parser_runtime_attestation(
        engine="oci",
        claims=claims,
    )


def _not_started_receipt(
    reservation: TechnicalParserInvocationReservation,
    attestation: TechnicalParserRuntimeAttestation,
    *,
    completed_at: datetime = START + timedelta(milliseconds=2),
) -> TechnicalParserExecutionReceipt:
    return create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation=reservation.operation,
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code="PARSER_EXECUTION_UNAVAILABLE",
        container_id=None,
        started_at=None,
        completed_at=completed_at,
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )


def _successful_invocation(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    operation: Literal["layout", "page"],
    request: bytes,
    stdout_sha256: str,
    stdout_size_bytes: int,
    page_claim: TechnicalExtractionPageClaim | None = None,
) -> TechnicalParserInvocationReservation:
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        page_claim=page_claim,
        operation=operation,
        request=request,
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="succeeded",
        operation=operation,
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code=TECHNICAL_PARSER_EXECUTION_SUCCESS,
        container_id=CONTAINER_ID,
        started_at=START + timedelta(milliseconds=2),
        completed_at=START + timedelta(milliseconds=3),
        exit_code=0,
        stdout_sha256=stdout_sha256,
        stdout_size_bytes=stdout_size_bytes,
        cleanup_confirmed=True,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    return reservation


def _successful_layout_invocation(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    layout: TechnicalExtractionLayoutBinding,
) -> TechnicalParserInvocationReservation:
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    return _successful_invocation(
        db,
        claim=claim,
        operation="layout",
        request=request,
        stdout_sha256=layout.sha256,
        stdout_size_bytes=layout.size_bytes,
    )


def _page_request(claim: TechnicalExtractionPageClaim) -> bytes:
    return encode_technical_parser_request(
        technical_document_id=claim.run_claim.technical_document_id,
        source_sha256=claim.run_claim.source_sha256,
        source_size_bytes=claim.run_claim.source_size_bytes,
        page_number=claim.page_number,
        page_count=claim.page_count,
        page_width_points=claim.layout_page_width_points,
        page_height_points=claim.layout_page_height_points,
        layout_sha256=claim.layout_sha256,
        extraction_policy=claim.run_claim.extraction_policy,
        extraction_policy_sha256=claim.run_claim.extraction_policy_sha256,
        worker_image_digest=claim.run_claim.worker_image_digest,
        ocr_low_confidence_threshold=(claim.run_claim.ocr_low_confidence_threshold),
    )


def _failed_page_invocation(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
) -> TechnicalParserInvocationReservation:
    attestation = _runtime_attestation(claim.run_claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim.run_claim,
        page_claim=claim,
        operation="page",
        request=_page_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="failed",
        operation="page",
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code="PARSER_EXECUTION_FAILED",
        container_id=CONTAINER_ID,
        started_at=START + timedelta(milliseconds=2),
        completed_at=START + timedelta(milliseconds=3),
        exit_code=1,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    return reservation


def _claim_and_initialize(
    db: Session,
    *,
    page_count: int = 2,
) -> tuple[TechnicalExtractionRunClaim, tuple[str, ...]]:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    layout = _layout(page_count=page_count)
    invocation = _successful_layout_invocation(db, claim=claim, layout=layout)
    initialized = initialize_technical_extraction_pages(
        db,
        claim=invocation.run_claim,
        layout=layout,
        parser_invocation_id=invocation.invocation_id,
        now=START + timedelta(seconds=1),
    )
    return initialized.run_claim, initialized.page_ids


def _complete_page(
    db: Session,
    *,
    run_claim: TechnicalExtractionRunClaim,
    page_number: int,
    storage_root: Path,
    attention: bool = False,
) -> TechnicalExtractionRunClaim:
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=page_number,
        now=START + timedelta(seconds=page_number * 2),
    )
    retained = _retain_for_claim(
        storage_root,
        page_claim,
        attention=attention,
    )
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    completion = complete_technical_extraction_page(
        db,
        claim=page_claim,
        retained=retained,
        storage_root=storage_root,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=_snapshot(db, page_claim.run_claim),
        parser_invocation_id=invocation_id,
        parser_output=parser_output,
        now=START + timedelta(minutes=1, seconds=page_number),
    )
    return completion.run_claim


def _png() -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        checksum = zlib.crc32(kind + data) & 0xFFFFFFFF
        return len(data).to_bytes(4, "big") + kind + data + checksum.to_bytes(4, "big")

    header = struct.pack(">IIBBBBB", 8, 6, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"\x00"))
        + chunk(b"IEND", b"")
    )


def _retain_for_claim(
    storage_root: Path,
    claim,
    *,
    attention: bool = False,
) -> RetainedTechnicalPageArtifacts:  # type: ignore[no-untyped-def]
    image = _png()
    payload = {
        "schema": "technical-page-evidence-v1",
        "source": {
            "technical_document_id": claim.run_claim.technical_document_id,
            "sha256": claim.run_claim.source_sha256,
            "size_bytes": claim.run_claim.source_size_bytes,
        },
        "page": {
            "number": claim.page_number,
            "count": claim.page_count,
            "width_points": float(claim.layout_page_width_points),
            "height_points": float(claim.layout_page_height_points),
            "image": {
                "sha256": hashlib.sha256(image).hexdigest(),
                "size_bytes": len(image),
                "width_pixels": 8,
                "height_pixels": 6,
            },
        },
        "extraction": {
            "policy_version": claim.run_claim.extraction_policy,
            "policy_sha256": claim.run_claim.extraction_policy_sha256,
            "worker_image_digest": claim.run_claim.worker_image_digest,
            "ocr_low_confidence_threshold": 80,
            "native_text_blocks": [
                {
                    "bbox": {"x0": 10, "x1": 100, "y0": 20, "y1": 40},
                    "id": "native-1",
                    "order": 1,
                    "text": "Bound test evidence",
                }
            ],
            "ocr": {
                "status": "ocr_not_required",
                "engine": None,
                "engine_version": None,
                "language": None,
                "image_sha256": None,
                "blocks": [],
            },
            "human_review_required": attention,
            "warnings": ["HUMAN_REVIEW_REQUIRED"] if attention else [],
        },
    }
    raw = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return retain_validated_technical_page_artifacts(
        raw,
        page_image_bytes=image,
        storage_root=storage_root,
        run_id=claim.run_claim.run_id,
        expected_technical_document_id=claim.run_claim.technical_document_id,
        expected_source_sha256=claim.run_claim.source_sha256,
        expected_source_size_bytes=claim.run_claim.source_size_bytes,
        expected_page_number=claim.page_number,
        expected_page_count=claim.page_count,
        expected_page_width_points=claim.layout_page_width_points,
        expected_page_height_points=claim.layout_page_height_points,
        expected_page_image_sha256=hashlib.sha256(image).hexdigest(),
        expected_page_image_size_bytes=len(image),
        expected_page_image_width_pixels=8,
        expected_page_image_height_pixels=6,
        expected_extraction_policy=claim.run_claim.extraction_policy,
        expected_extraction_policy_bytes=POLICY_BYTES,
        expected_extraction_policy_sha256=claim.run_claim.extraction_policy_sha256,
        expected_worker_image_digest=claim.run_claim.worker_image_digest,
        expected_ocr_low_confidence_threshold=Decimal("80"),
    )


def _parser_page_frame(
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
) -> bytes:
    def json_number(value: Decimal) -> int | float:
        if value == value.to_integral_value():
            return int(value)
        return float(value)

    evidence_bytes = retained.packet.path.read_bytes()
    image_bytes = retained.page_image.path.read_bytes()
    header = json.dumps(
        {
            "evidence_sha256": hashlib.sha256(evidence_bytes).hexdigest(),
            "evidence_size_bytes": len(evidence_bytes),
            "image_height_pixels": retained.evidence.image.height_pixels,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "image_size_bytes": len(image_bytes),
            "image_width_pixels": retained.evidence.image.width_pixels,
            "page_count": claim.page_count,
            "page_height_points": json_number(claim.layout_page_height_points),
            "page_number": claim.page_number,
            "page_width_points": json_number(claim.layout_page_width_points),
            "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
            "status": "ok",
        },
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return len(header).to_bytes(4, "big") + header + evidence_bytes + image_bytes


def _successful_page_invocation(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
) -> tuple[TechnicalExtractionPageClaim, str, bytes]:
    parser_output = _parser_page_frame(claim, retained)
    reservation = _successful_invocation(
        db,
        claim=claim.run_claim,
        page_claim=claim,
        operation="page",
        request=_page_request(claim),
        stdout_sha256=hashlib.sha256(parser_output).hexdigest(),
        stdout_size_bytes=len(parser_output),
    )
    return (
        replace(claim, run_claim=reservation.run_claim),
        reservation.invocation_id,
        parser_output,
    )


def test_request_is_idempotent_and_never_creates_authority_records(
    db: Session,
) -> None:
    actor, _source, document = _seed(db)
    first = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    replay = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    assert replay.run_id == first.run_id
    assert replay.idempotent_replay is True
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionRun)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def test_runtime_profile_is_part_of_run_identity(db: Session) -> None:
    actor, _source, document = _seed(db)
    first = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    changed = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256="9" * 64,
    )
    replay = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256="9" * 64,
    )

    assert changed.run_id != first.run_id
    assert replay.run_id == changed.run_id
    assert replay.idempotent_replay is True
    assert set(db.scalars(select(TechnicalExtractionRun.runtime_profile_sha256))) == {
        RUNTIME_PROFILE_SHA,
        "9" * 64,
    }
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionRun)) == 2


@pytest.mark.parametrize("role", ("read_only", "estimator"))
def test_request_requires_technical_write_permission(
    db: Session,
    role: str,
) -> None:
    actor, _source, document = _seed(db)
    actor.role = role
    db.commit()
    with pytest.raises(TechnicalExtractionError) as forbidden:
        _request(db, actor, document)
    assert forbidden.value.code == "EXTRACTION_REQUEST_INVALID"
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionRun)) == 0


def test_administrator_can_request_extraction(db: Session) -> None:
    actor, _source, document = _seed(db)
    actor.role = "administrator"
    db.commit()
    assert _request(db, actor, document)


@pytest.mark.parametrize(
    ("persisted_role", "persisted_active"),
    (("read_only", True), ("technical_reviewer", False)),
)
def test_request_authorizes_persisted_user_not_forged_caller_fields(
    db: Session,
    persisted_role: str,
    persisted_active: bool,
) -> None:
    actor, _source, document = _seed(db)
    actor.role = persisted_role
    actor.is_active = persisted_active
    db.commit()
    actor_id = actor.id
    db.expunge(actor)
    forged = User(
        id=actor_id,
        email="forged-administrator@example.test",
        full_name="Forged Administrator",
        password_hash="unused",  # noqa: S106
        role="administrator",
        is_active=True,
    )

    with pytest.raises(TechnicalExtractionError) as forbidden:
        _request(db, forged, document)
    assert forbidden.value.code == "EXTRACTION_REQUEST_INVALID"
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionRun)) == 0


def test_ocr_threshold_is_validated_and_part_of_run_identity(db: Session) -> None:
    actor, _source, document = _seed(db)

    def request(threshold: object) -> str:
        return request_technical_extraction_run(
            db,
            actor=actor,
            technical_document_id=document.id,
            extraction_policy=POLICY,
            extraction_policy_bytes=POLICY_BYTES,
            ocr_low_confidence_threshold=threshold,
            worker_image_digest=WORKER_SHA,
            runtime_profile_sha256=RUNTIME_PROFILE_SHA,
        ).run_id

    first = request(Decimal("80"))
    second = request(Decimal("75"))
    assert first != second
    for invalid in (Decimal("-0.01"), Decimal("100.01"), Decimal("1.001"), 80.0):
        with pytest.raises(TechnicalExtractionError) as rejected:
            request(invalid)
        assert rejected.value.code == "EXTRACTION_POLICY_INVALID"
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionRun)) == 2


def test_run_claim_rejects_live_competitor_and_recovers_stale_lease(
    db: Session,
) -> None:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    first = claim_next_technical_extraction_run(db, now=START)
    assert first is not None
    assert first.ocr_low_confidence_threshold == Decimal("80")
    assert (
        claim_next_technical_extraction_run(
            db,
            now=START + timedelta(minutes=14),
        )
        is None
    )

    replacement = claim_next_technical_extraction_run(
        db,
        now=START + timedelta(minutes=16),
    )
    assert replacement is not None
    assert replacement.run_id == first.run_id
    assert replacement.attempt_token != first.attempt_token
    assert replacement.attempt_count == 2

    with pytest.raises(TechnicalExtractionError) as lost:
        heartbeat_technical_extraction_run(
            db,
            claim=first,
            now=START + timedelta(minutes=17),
        )
    assert lost.value.code == "EXTRACTION_RUN_CLAIM_LOST"

    release_technical_extraction_run_for_retry(
        db,
        claim=replacement,
        outcome_code="EXTRACTION_PARSER_TIMEOUT",
        now=START + timedelta(minutes=17),
    )
    persisted = db.get(TechnicalExtractionRun, replacement.run_id)
    assert persisted is not None
    assert persisted.status == "queued"
    assert persisted.outcome_code == "EXTRACTION_PARSER_TIMEOUT"
    assert persisted.outcome_retryable is True
    assert persisted.last_outcome_at is not None

    retried = claim_next_technical_extraction_run(
        db,
        now=START + timedelta(minutes=18),
    )
    assert retried is not None
    assert retried.attempt_count == 3
    persisted = db.get(TechnicalExtractionRun, replacement.run_id)
    assert persisted is not None
    assert persisted.status == "processing"
    assert persisted.outcome_code is None
    assert persisted.outcome_retryable is None


@pytest.mark.parametrize("resolution", ("fail", "retry"))
def test_run_level_resolution_rejects_initialized_pages_without_stranding_them(
    db: Session,
    resolution: str,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )

    with pytest.raises(TechnicalExtractionError) as rejected:
        if resolution == "fail":
            fail_technical_extraction_run(
                db,
                claim=page_claim.run_claim,
                outcome_code="EXTRACTION_PARSER_FAILED",
                now=START + timedelta(seconds=3),
            )
        else:
            release_technical_extraction_run_for_retry(
                db,
                claim=page_claim.run_claim,
                outcome_code="EXTRACTION_PARSER_TIMEOUT",
                now=START + timedelta(seconds=3),
            )

    assert rejected.value.code == "EXTRACTION_RUN_HAS_PAGES"
    assert not db.in_transaction()
    persisted_run = db.get(TechnicalExtractionRun, run_claim.run_id)
    persisted_pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_claim.run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert persisted_run is not None
    assert persisted_run.status == "processing"
    assert tuple(page.status for page in persisted_pages) == ("processing", "pending")
    assert persisted_pages[0].attempt_token == page_claim.attempt_token
    assert persisted_pages[1].attempt_token is None


def test_run_level_resolution_translates_page_guard_database_failure(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None

    def fail_scalar(*_args: object, **_kwargs: object) -> object:
        raise SQLAlchemyError("injected page-guard failure")

    monkeypatch.setattr(db, "scalar", fail_scalar)
    with pytest.raises(TechnicalExtractionError) as rejected:
        fail_technical_extraction_run(
            db,
            claim=claim,
            outcome_code="EXTRACTION_PARSER_FAILED",
            now=START + timedelta(seconds=1),
        )

    assert rejected.value.code == "EXTRACTION_RUN_PERSISTENCE_CONFLICT"
    assert rejected.value.fatal is True
    assert not db.in_transaction()


def test_source_snapshot_confirmation_fails_closed_after_quarantine(
    db: Session,
) -> None:
    actor, source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    assert snapshot.sha256 == SOURCE_SHA

    source.malware_scan_status = "quarantined"
    source.record_version += 1
    db.commit()
    with pytest.raises(TechnicalExtractionError) as changed:
        confirm_technical_extraction_source_snapshot(
            db,
            claim=claim,
            snapshot=snapshot,
        )
    assert changed.value.code == "EXTRACTION_SOURCE_BINDING_FAILED"


def test_page_completion_rechecks_source_snapshot_inside_attachment_transaction(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    snapshot = _snapshot(db, page_claim.run_claim)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    source = db.get(StoredFile, page_claim.run_claim.source_stored_file_id)
    assert source is not None
    source.malware_scan_status = "quarantined"
    source.record_version += 1
    db.commit()

    with pytest.raises(TechnicalExtractionError) as rejected:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=retained,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=snapshot,
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
        )
    assert rejected.value.code == "EXTRACTION_SOURCE_BINDING_FAILED"
    assert rejected.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_aggregate_rechecks_source_snapshot_before_terminalization(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    snapshot = _snapshot(db, run_claim)
    source = db.get(StoredFile, run_claim.source_stored_file_id)
    assert source is not None
    source.malware_scan_status = "quarantined"
    source.record_version += 1
    db.commit()

    with pytest.raises(TechnicalExtractionError) as rejected:
        aggregate_technical_extraction_run(
            db,
            claim=run_claim,
            source_snapshot=snapshot,
            artifact_storage_root=tmp_path,
            now=START + timedelta(seconds=3),
        )
    assert rejected.value.code == "EXTRACTION_SOURCE_BINDING_FAILED"
    assert not db.in_transaction()
    persisted = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert persisted is not None
    assert persisted.status == "processing"


def test_page_initialization_is_atomic_idempotent_and_count_bound(
    db: Session,
) -> None:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    layout = _layout(page_count=2)
    layout_invocation = _successful_layout_invocation(
        db,
        claim=claim,
        layout=layout,
    )
    initial = initialize_technical_extraction_pages(
        db,
        claim=layout_invocation.run_claim,
        layout=layout,
        parser_invocation_id=layout_invocation.invocation_id,
        now=START + timedelta(seconds=1),
    )
    replay = initialize_technical_extraction_pages(
        db,
        claim=initial.run_claim,
        layout=layout,
        parser_invocation_id=layout_invocation.invocation_id,
        now=START + timedelta(seconds=2),
    )
    assert replay.idempotent_replay is True
    assert replay.page_ids == initial.page_ids
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 2

    with pytest.raises(TechnicalExtractionError) as mismatch:
        initialize_technical_extraction_pages(
            db,
            claim=replay.run_claim,
            layout=_layout(page_count=3),
            parser_invocation_id=layout_invocation.invocation_id,
        )
    assert mismatch.value.code == "EXTRACTION_PAGE_COUNT_CONFLICT"
    conflicting_layout = _layout(page_count=2, sha256="d" * 64)
    with pytest.raises(TechnicalExtractionError) as layout_mismatch:
        initialize_technical_extraction_pages(
            db,
            claim=replay.run_claim,
            layout=conflicting_layout,
            parser_invocation_id=layout_invocation.invocation_id,
        )
    assert layout_mismatch.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"

    first_page = db.scalar(
        select(TechnicalExtractionPage).where(
            TechnicalExtractionPage.run_id == replay.run_claim.run_id,
            TechnicalExtractionPage.page_number == 1,
        )
    )
    assert first_page is not None
    assert first_page.layout_sha256 == LAYOUT_SHA
    assert first_page.layout_page_width_points == Decimal("612")


def test_page_initialization_rejects_invalid_layout_schema_digest_size_and_pages(
    db: Session,
) -> None:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    valid = _layout(page_count=1)
    invalid_layouts = (
        replace(valid, schema="technical-parser-layout-v2"),
        replace(valid, sha256="not-a-digest"),
        replace(valid, size_bytes=0),
        replace(
            valid,
            pages=(replace(valid.pages[0], page_number=2),),
        ),
        replace(
            valid,
            pages=(replace(valid.pages[0], width_points=Decimal("0")),),
        ),
    )
    for invalid in invalid_layouts:
        with pytest.raises(TechnicalExtractionError) as rejected:
            initialize_technical_extraction_pages(
                db,
                claim=claim,
                layout=invalid,
            )
        assert rejected.value.code == "EXTRACTION_LAYOUT_INVALID"
    run = db.get(TechnicalExtractionRun, claim.run_id)
    assert run is not None
    assert run.page_count is None
    assert run.layout_sha256 is None
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0


def test_layout_acceptance_requires_a_terminal_success_receipt(db: Session) -> None:
    actor, _source, document = _seed(db)
    _request(db, actor, document)
    claim = claim_next_technical_extraction_run(db, now=START)
    assert claim is not None
    layout = _layout(page_count=1)
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=encode_technical_parser_layout_request(
            technical_document_id=claim.technical_document_id,
            source_sha256=claim.source_sha256,
            source_size_bytes=claim.source_size_bytes,
            extraction_policy=claim.extraction_policy,
            extraction_policy_sha256=claim.extraction_policy_sha256,
            worker_image_digest=claim.worker_image_digest,
            ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
        ),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )

    with pytest.raises(TechnicalExtractionError) as missing:
        initialize_technical_extraction_pages(
            db,
            claim=reservation.run_claim,
            layout=layout,
            parser_invocation_id=reservation.invocation_id,
            now=START + timedelta(seconds=1),
        )
    assert missing.value.code == "EXTRACTION_INVOCATION_NOT_FOUND"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0


def test_runtime_attestation_cannot_change_after_layout_reservation(
    db: Session,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    mismatched = _runtime_attestation(
        page_claim.run_claim,
        image_id=f"sha256:{'9' * 64}",
    )

    with pytest.raises(TechnicalExtractionError) as rejected:
        reserve_technical_parser_invocation(
            db,
            claim=page_claim.run_claim,
            page_claim=page_claim,
            operation="page",
            request=_page_request(page_claim),
            runtime_attestation=mismatched,
            invocation_id=str(uuid4()),
            now=START + timedelta(seconds=3),
        )
    assert rejected.value.code == "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH"
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 1


def test_page_acceptance_rejects_a_failed_parser_receipt(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    retained = _retain_for_claim(tmp_path, page_claim)
    parser_output = _parser_page_frame(page_claim, retained)
    reservation = _failed_page_invocation(db, claim=page_claim)
    page_claim = replace(page_claim, run_claim=reservation.run_claim)

    with pytest.raises(TechnicalExtractionError) as failed:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=retained,
            storage_root=tmp_path,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=reservation.invocation_id,
            parser_output=parser_output,
            now=START + timedelta(seconds=3),
        )
    assert failed.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    page = db.get(TechnicalExtractionPage, page_claim.page_id)
    assert page is not None
    assert page.status == "processing"


def test_abort_initialized_run_cancels_unfinished_pages_without_source_eligibility(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=3)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    active_page = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=2,
        now=START + timedelta(seconds=2),
    )
    source = db.get(StoredFile, run_claim.source_stored_file_id)
    assert source is not None
    source.malware_scan_status = "quarantined"
    source.record_version += 1
    db.commit()

    result = abort_technical_extraction_run(
        db,
        claim=active_page.run_claim,
        outcome_code="PARSER_PROTOCOL_LAYOUT_INVALID",
        now=START + timedelta(seconds=3),
    )
    assert result.status == "failed"
    assert result.cancelled_page_count == 2
    assert result.preserved_page_count == 1

    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.outcome_code == "PARSER_PROTOCOL_LAYOUT_INVALID"
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_claim.run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert tuple(page.status for page in pages) == (
        "completed",
        "cancelled",
        "cancelled",
    )
    assert all(page.attempt_token is None for page in pages)
    assert all(page.outcome_code == "PAGE_EXTRACTION_CANCELLED" for page in pages[1:])
    assert (
        db.scalar(
            select(func.count())
            .select_from(TechnicalDerivedArtifact)
            .where(TechnicalDerivedArtifact.run_id == run_claim.run_id)
        )
        == 2
    )
    audit = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.entity_id == run_claim.run_id,
            AuditEvent.action == "abort_technical_extraction_run",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert audit is not None
    assert audit.new_value["cancelled_page_count"] == 2


def test_page_claim_retry_and_old_token_are_cas_protected(db: Session) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    with pytest.raises(TechnicalExtractionError) as live:
        claim_technical_extraction_page(
            db,
            run_claim=page_claim.run_claim,
            page_number=1,
            now=START + timedelta(minutes=10),
        )
    assert live.value.code == "EXTRACTION_PAGE_IN_PROGRESS"

    current_run = fail_technical_extraction_page(
        db,
        claim=page_claim,
        outcome_code="PAGE_PARSER_TIMEOUT",
        retryable=True,
        now=START + timedelta(minutes=11),
    )
    retry = claim_technical_extraction_page(
        db,
        run_claim=current_run,
        page_number=1,
        now=START + timedelta(minutes=12),
    )
    assert retry.attempt_count == 2
    assert retry.attempt_token != page_claim.attempt_token

    old_with_current_run = replace(
        page_claim,
        run_claim=retry.run_claim,
    )
    with pytest.raises(TechnicalExtractionError) as lost:
        heartbeat_technical_extraction_page(
            db,
            claim=old_with_current_run,
            now=START + timedelta(minutes=13),
        )
    assert lost.value.code == "EXTRACTION_PAGE_CLAIM_LOST"


def test_page_retry_appends_invocation_and_receipt_history(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    first = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    failed_reservation = _failed_page_invocation(db, claim=first)
    first = replace(first, run_claim=failed_reservation.run_claim)
    current_run = fail_technical_extraction_page(
        db,
        claim=first,
        outcome_code="PAGE_PARSER_TIMEOUT",
        retryable=True,
        now=START + timedelta(seconds=3),
    )
    retry = claim_technical_extraction_page(
        db,
        run_claim=current_run,
        page_number=1,
        now=START + timedelta(seconds=4),
    )
    retained = _retain_for_claim(tmp_path, retry)
    retry, successful_invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=retry,
        retained=retained,
    )
    completion = complete_technical_extraction_page(
        db,
        claim=retry,
        retained=retained,
        storage_root=tmp_path,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=_snapshot(db, retry.run_claim),
        parser_invocation_id=successful_invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=5),
    )

    page_invocations = tuple(
        db.scalars(
            select(TechnicalParserInvocation)
            .where(
                TechnicalParserInvocation.run_id == completion.run_claim.run_id,
                TechnicalParserInvocation.operation == "page",
            )
            .order_by(TechnicalParserInvocation.attempt_count)
        )
    )
    assert [invocation.id for invocation in page_invocations] == [
        failed_reservation.invocation_id,
        successful_invocation_id,
    ]
    assert [invocation.attempt_count for invocation in page_invocations] == [1, 2]
    assert [invocation.page_attempt_count for invocation in page_invocations] == [1, 2]
    assert page_invocations[0].attempt_token != page_invocations[1].attempt_token
    receipts = {
        receipt.invocation_id: receipt
        for receipt in db.scalars(
            select(TechnicalParserInvocationReceipt).where(
                TechnicalParserInvocationReceipt.run_id == completion.run_claim.run_id
            )
        )
    }
    assert receipts[failed_reservation.invocation_id].execution_state == "failed"
    assert receipts[successful_invocation_id].execution_state == "succeeded"
    assert len(receipts) == 3


def test_only_one_page_per_run_can_be_processing(db: Session) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    first = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    persisted = db.get(TechnicalExtractionPage, first.page_id)
    assert persisted is not None
    assert persisted.status == "processing"

    with pytest.raises(TechnicalExtractionError) as blocked:
        claim_technical_extraction_page(
            db,
            run_claim=first.run_claim,
            page_number=2,
            now=START + timedelta(seconds=3),
        )
    assert blocked.value.code == "EXTRACTION_PAGE_IN_PROGRESS"
    persisted = db.get(TechnicalExtractionPage, first.page_id)
    assert persisted is not None
    assert persisted.status == "processing"


def test_claim_audits_do_not_expose_live_lease_tokens(db: Session) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    audits = tuple(
        db.scalars(
            select(AuditEvent).where(
                AuditEvent.action.in_(
                    (
                        "claim_technical_extraction_run",
                        "claim_technical_extraction_page",
                    )
                )
            )
        )
    )
    assert len(audits) == 2
    payload = json.dumps([audit.new_value for audit in audits], sort_keys=True)
    assert "attempt_token" not in payload
    assert run_claim.attempt_token not in payload
    assert page_claim.attempt_token not in payload


def test_stale_page_claim_is_recovered_with_new_token(db: Session) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    first = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    refreshed_run = heartbeat_technical_extraction_run(
        db,
        claim=first.run_claim,
        now=START + timedelta(minutes=16),
    )
    recovered = claim_technical_extraction_page(
        db,
        run_claim=refreshed_run,
        page_number=1,
        now=START + timedelta(minutes=17),
        claim_ttl=timedelta(minutes=15),
    )
    assert recovered.attempt_token != first.attempt_token
    assert recovered.attempt_count == 2


def test_retryable_page_failure_prevents_aggregate_until_retried(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    current_run = fail_technical_extraction_page(
        db,
        claim=page_claim,
        outcome_code="PAGE_PARSER_TIMEOUT",
        retryable=True,
        now=START + timedelta(seconds=3),
    )
    with pytest.raises(TechnicalExtractionError) as pending:
        aggregate_technical_extraction_run(
            db,
            claim=current_run,
            source_snapshot=_snapshot(db, current_run),
            artifact_storage_root=tmp_path,
            now=START + timedelta(seconds=4),
        )
    assert pending.value.code == "EXTRACTION_AGGREGATION_NOT_READY"


def test_nonretryable_page_failure_aggregates_to_failed_run(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    current_run = fail_technical_extraction_page(
        db,
        claim=page_claim,
        outcome_code="PAGE_EVIDENCE_STRUCTURE_INVALID",
        retryable=False,
        now=START + timedelta(seconds=3),
    )
    result = aggregate_technical_extraction_run(
        db,
        claim=current_run,
        source_snapshot=_snapshot(db, current_run),
        artifact_storage_root=tmp_path,
        now=START + timedelta(seconds=4),
    )
    assert result.status == "failed"
    assert result.outcome_code == "EXTRACTION_PAGE_FAILED"
    assert result.manifest_sha256 is None
    run = db.get(TechnicalExtractionRun, current_run.run_id)
    assert run is not None
    assert run.outcome_retryable is False


def test_fatal_page_does_not_terminalize_run_while_sibling_is_pending(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    current_run = fail_technical_extraction_page(
        db,
        claim=page_claim,
        outcome_code="PAGE_EVIDENCE_STRUCTURE_INVALID",
        retryable=False,
        now=START + timedelta(seconds=3),
    )

    with pytest.raises(TechnicalExtractionError) as pending:
        aggregate_technical_extraction_run(
            db,
            claim=current_run,
            source_snapshot=_snapshot(db, current_run),
            artifact_storage_root=tmp_path,
            now=START + timedelta(seconds=4),
        )
    assert pending.value.code == "EXTRACTION_AGGREGATION_NOT_READY"
    persisted = db.get(TechnicalExtractionRun, current_run.run_id)
    assert persisted is not None
    assert persisted.status == "processing"
    assert persisted.manifest_sha256 is None


@pytest.mark.parametrize(
    ("attention", "expected_status"),
    ((False, "completed"), (True, "needs_attention")),
)
def test_validated_retained_artifacts_complete_page_atomically(
    db: Session,
    tmp_path: Path,
    attention: bool,
    expected_status: str,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(
        storage_root,
        page_claim,
        attention=attention,
    )
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    completion = complete_technical_extraction_page(
        db,
        claim=page_claim,
        retained=retained,
        storage_root=storage_root,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=_snapshot(db, page_claim.run_claim),
        parser_invocation_id=invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=3),
    )
    assert completion.status == expected_status
    assert completion.database_outcome == "committed"
    page = db.get(TechnicalExtractionPage, page_claim.page_id)
    assert page is not None
    assert page.status == expected_status
    assert page.binding_sha256 == retained.evidence.binding_sha256
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 2

    aggregate = aggregate_technical_extraction_run(
        db,
        claim=completion.run_claim,
        source_snapshot=_snapshot(db, completion.run_claim),
        artifact_storage_root=storage_root,
        now=START + timedelta(seconds=4),
    )
    assert aggregate.status == ("completed_with_attention" if attention else "completed")


@pytest.mark.parametrize("tamper", ("deleted", "corrupted"))
def test_aggregate_rechecks_exact_retained_artifact_bytes(
    db: Session,
    tmp_path: Path,
    tamper: str,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    completion = complete_technical_extraction_page(
        db,
        claim=page_claim,
        retained=retained,
        storage_root=storage_root,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=_snapshot(db, page_claim.run_claim),
        parser_invocation_id=invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=3),
    )
    packet_path = Path(retained.packet.storage_path)
    if tamper == "deleted":
        packet_path.unlink()
    else:
        packet_path.write_bytes(b"corrupted")

    with pytest.raises(TechnicalExtractionError) as rejected:
        aggregate_technical_extraction_run(
            db,
            claim=completion.run_claim,
            source_snapshot=_snapshot(db, completion.run_claim),
            artifact_storage_root=storage_root,
            now=START + timedelta(seconds=4),
        )

    assert rejected.value.code == "EXTRACTION_ARTIFACT_BINDING_MISMATCH"
    assert not db.in_transaction()
    persisted = db.get(TechnicalExtractionRun, completion.run_claim.run_id)
    assert persisted is not None
    assert persisted.status == "processing"
    assert persisted.manifest_sha256 is None


def test_forged_retained_binding_is_known_rollback_without_db_rows(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    forged = replace(
        retained,
        packet=replace(
            retained.packet,
            run_id="11111111-1111-4111-8111-111111111111",
        ),
    )
    with pytest.raises(TechnicalExtractionError) as rejected:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=forged,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
        )
    assert rejected.value.code == "EXTRACTION_ARTIFACT_BINDING_MISMATCH"
    assert rejected.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_self_consistent_receipt_with_forged_semantics_is_reparsed_and_rejected(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    forged = replace(
        retained,
        evidence=replace(
            retained.evidence,
            human_review_required=not retained.evidence.human_review_required,
        ),
    )

    with pytest.raises(TechnicalExtractionError) as rejected:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=forged,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
        )
    assert rejected.value.code == "EXTRACTION_ARTIFACT_BINDING_MISMATCH"
    assert rejected.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


@pytest.mark.parametrize("tamper", ("bytes", "path"))
def test_artifact_byte_or_path_verification_failure_is_known_rollback(
    db: Session,
    tmp_path: Path,
    tamper: str,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    supplied = retained
    if tamper == "bytes":
        retained.packet.path.write_bytes(b"changed")
    else:
        supplied = replace(
            retained,
            packet=replace(
                retained.packet,
                storage_path=str(storage_root / "wrong.json"),
            ),
        )
    with pytest.raises(TechnicalExtractionError) as rejected:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=supplied,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
        )
    assert rejected.value.code == "EXTRACTION_ARTIFACT_BINDING_MISMATCH"
    assert rejected.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_page_cas_loss_rolls_back_rows_and_allows_exact_compensation(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    page = db.get(TechnicalExtractionPage, page_claim.page_id)
    assert page is not None
    page.record_version += 1
    db.commit()

    with pytest.raises(TechnicalExtractionError) as lost:
        complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=retained,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
        )
    assert lost.value.code == "EXTRACTION_PAGE_CLAIM_LOST"
    assert lost.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    removed = cleanup_retained_technical_page_artifacts(
        retained,
        storage_root=storage_root,
        database_outcome=lost.value.database_outcome,
    )
    assert set(removed) == {
        retained.packet.artifact_id,
        retained.page_image.artifact_id,
    }
    assert not retained.packet.path.exists()
    assert not retained.page_image.path.exists()


def test_artifact_row_flush_failure_is_known_rollback(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    source_snapshot = _snapshot(db, page_claim.run_claim)
    original_flush = db.flush
    flush_calls = 0

    def fail_first_flush(objects: object | None = None) -> None:
        nonlocal flush_calls
        flush_calls += 1
        if flush_calls == 1:
            raise SQLAlchemyError("simulated flush")
        if objects is None:
            original_flush()
        else:
            original_flush(objects)  # type: ignore[arg-type]

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "flush", fail_first_flush)
        with pytest.raises(TechnicalExtractionError) as failed:
            complete_technical_extraction_page(
                db,
                claim=page_claim,
                retained=retained,
                storage_root=storage_root,
                extraction_policy_bytes=POLICY_BYTES,
                source_snapshot=source_snapshot,
                parser_invocation_id=invocation_id,
                parser_output=parser_output,
            )
    assert failed.value.code == "EXTRACTION_RUN_PERSISTENCE_CONFLICT"
    assert failed.value.database_outcome == "known_rollback"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_commit_acknowledgement_failure_retains_bytes_and_reports_unknown(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )

    with monkeypatch.context() as scoped:
        scoped.setattr(
            db,
            "commit",
            lambda: (_ for _ in ()).throw(SQLAlchemyError("unknown commit")),
        )
        with pytest.raises(TechnicalExtractionError) as unknown:
            complete_technical_extraction_page(
                db,
                claim=page_claim,
                retained=retained,
                storage_root=storage_root,
                extraction_policy_bytes=POLICY_BYTES,
                source_snapshot=_snapshot(db, page_claim.run_claim),
                parser_invocation_id=invocation_id,
                parser_output=parser_output,
            )
    assert unknown.value.code == "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN"
    assert unknown.value.database_outcome == "commit_outcome_unknown"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    removed = cleanup_retained_technical_page_artifacts(
        retained,
        storage_root=storage_root,
        database_outcome=unknown.value.database_outcome,
    )
    assert removed == ()
    assert retained.packet.path.exists()
    assert retained.page_image.path.exists()


def test_commit_then_acknowledgement_loss_replays_exact_committed_page(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    source_snapshot = _snapshot(db, page_claim.run_claim)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    original_commit = db.commit

    def commit_then_raise() -> None:
        original_commit()
        raise SQLAlchemyError("commit acknowledgement lost")

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "commit", commit_then_raise)
        with pytest.raises(TechnicalExtractionError) as unknown:
            complete_technical_extraction_page(
                db,
                claim=page_claim,
                retained=retained,
                storage_root=storage_root,
                extraction_policy_bytes=POLICY_BYTES,
                source_snapshot=source_snapshot,
                parser_invocation_id=invocation_id,
                parser_output=parser_output,
                now=START + timedelta(seconds=3),
            )
    assert unknown.value.code == "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN"
    assert unknown.value.database_outcome == "commit_outcome_unknown"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 2

    replay = complete_technical_extraction_page(
        db,
        claim=page_claim,
        retained=retained,
        storage_root=storage_root,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=source_snapshot,
        parser_invocation_id=invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=4),
    )
    assert replay.idempotent_replay is True
    assert replay.database_outcome == "committed"
    assert replay.run_claim.record_version == page_claim.run_claim.record_version + 1
    assert (
        cleanup_retained_technical_page_artifacts(
            retained,
            storage_root=storage_root,
            database_outcome=unknown.value.database_outcome,
        )
        == ()
    )
    assert retained.packet.path.exists()
    assert retained.page_image.path.exists()


def test_old_completion_replay_never_receives_a_later_page_run_claim(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    first_page = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    source_snapshot = _snapshot(db, first_page.run_claim)
    storage_root = tmp_path / "storage"
    storage_root.mkdir()
    retained = _retain_for_claim(storage_root, first_page)
    first_page, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=first_page,
        retained=retained,
    )
    first_completion = complete_technical_extraction_page(
        db,
        claim=first_page,
        retained=retained,
        storage_root=storage_root,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=source_snapshot,
        parser_invocation_id=invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=3),
    )
    claim_technical_extraction_page(
        db,
        run_claim=first_completion.run_claim,
        page_number=2,
        now=START + timedelta(seconds=4),
    )

    with pytest.raises(TechnicalExtractionError) as ambiguous:
        complete_technical_extraction_page(
            db,
            claim=first_page,
            retained=retained,
            storage_root=storage_root,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=source_snapshot,
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
            now=START + timedelta(seconds=5),
        )
    assert ambiguous.value.code == "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN"
    assert ambiguous.value.database_outcome == "commit_outcome_unknown"
    assert retained.packet.path.exists()
    assert retained.page_image.path.exists()


@pytest.mark.parametrize(
    ("attention_page", "expected_status", "expected_outcome"),
    (
        (None, "completed", "EXTRACTION_COMPLETE"),
        (
            2,
            "completed_with_attention",
            "EXTRACTION_COMPLETE_WITH_ATTENTION",
        ),
    ),
)
def test_terminal_pages_build_deterministic_verified_manifest_without_authority(
    db: Session,
    tmp_path: Path,
    attention_page: int | None,
    expected_status: str,
    expected_outcome: str,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    before = (
        db.scalar(select(func.count()).select_from(TechnicalVariant)),
        db.scalar(select(func.count()).select_from(Approval)),
        db.scalar(select(func.count()).select_from(LibraryRelease)),
    )
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
        attention=attention_page == 1,
    )
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=2,
        storage_root=tmp_path,
        attention=attention_page == 2,
    )
    result = aggregate_technical_extraction_run(
        db,
        claim=run_claim,
        source_snapshot=_snapshot(db, run_claim),
        artifact_storage_root=tmp_path,
        now=START + timedelta(minutes=2),
    )
    assert result.status == expected_status
    assert result.outcome_code == expected_outcome
    assert result.manifest_sha256 is not None

    first = verify_technical_extraction_manifest(
        db,
        run_id=run_claim.run_id,
        artifact_storage_root=tmp_path,
    )
    second = verify_technical_extraction_manifest(
        db,
        run_id=run_claim.run_id,
        artifact_storage_root=tmp_path,
    )
    assert first.sha256 == result.manifest_sha256
    assert first.canonical_json == second.canonical_json
    payload = first.as_dict()
    assert payload["schema"] == "technical-extraction-manifest-v2"
    assert payload["layout_schema"] == "technical-parser-layout-v1"
    assert payload["layout_sha256"] == LAYOUT_SHA
    assert payload["layout_size_bytes"] == 512
    assert payload["runtime_profile_sha256"] == RUNTIME_PROFILE_SHA
    assert payload["runtime_attestation_sha256"] == run_claim.runtime_attestation_sha256
    assert payload["layout_invocation_id"] == run_claim.layout_invocation_id
    runtime_attestation = payload["runtime_attestation"]
    assert isinstance(runtime_attestation, dict)
    claims = runtime_attestation["claims"]
    assert isinstance(claims, dict)
    assert set(claims) == {
        "controller_owner_id",
        "extraction_policy",
        "extraction_policy_sha256",
        "image_id",
        "image_reference",
        "oci_profile_schema",
        "platform",
        "runtime_executable_sha256",
        "runtime_host",
        "runtime_profile_sha256",
        "seccomp_profile_sha256",
        "transport_schema",
        "worker_image_digest",
    }
    assert [page["page_number"] for page in payload["pages"]] == [1, 2]  # type: ignore[index]
    assert all(page["layout_sha256"] == LAYOUT_SHA for page in payload["pages"])  # type: ignore[union-attr]
    assert all(
        page["layout_page_width_points"] == "612.0000"
        and page["layout_page_height_points"] == "792.0000"
        for page in payload["pages"]  # type: ignore[union-attr]
    )
    invocations = payload["invocations"]
    assert isinstance(invocations, list)
    assert len(invocations) == 3
    invocation_rows = {
        row.id: row
        for row in db.scalars(
            select(TechnicalParserInvocation).where(
                TechnicalParserInvocation.run_id == run_claim.run_id
            )
        )
    }
    receipt_rows = {
        row.invocation_id: row
        for row in db.scalars(
            select(TechnicalParserInvocationReceipt).where(
                TechnicalParserInvocationReceipt.run_id == run_claim.run_id
            )
        )
    }
    assert (
        {value["invocation_id"] for value in invocations}
        == set(invocation_rows)
        == set(receipt_rows)
    )
    assert {value["invocation_id"] for value in invocations if value["operation"] == "page"} == {
        page["parser_invocation_id"]
        for page in payload["pages"]  # type: ignore[union-attr]
    }
    for value in invocations:
        invocation_id = value["invocation_id"]
        receipt = receipt_rows[invocation_id]
        assert value["terminal_receipt"] == receipt.receipt_json
        assert value["terminal_receipt_sha256"] == receipt.receipt_sha256
        assert value["runtime_attestation_sha256"] == (run_claim.runtime_attestation_sha256)
        assert receipt.execution_state == "succeeded"
        assert receipt.cleanup_confirmed is True
    after = (
        db.scalar(select(func.count()).select_from(TechnicalVariant)),
        db.scalar(select(func.count()).select_from(Approval)),
        db.scalar(select(func.count()).select_from(LibraryRelease)),
    )
    assert after == before == (0, 0, 0)


def test_legacy_v1_manifest_remains_verifiable_without_parser_provenance(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    run = db.get(TechnicalExtractionRun, run_claim.run_id)
    assert run is not None
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage).where(
                TechnicalExtractionPage.run_id == run_claim.run_id
            )
        )
    )
    assert len(pages) == 1

    db.connection().exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    run.run_schema = "technical-extraction-run-v1"
    run.runtime_profile_sha256 = None
    run.runtime_attestation_sha256 = None
    run.layout_invocation_id = None
    for page in pages:
        page.page_schema = "technical-extraction-page-v1"
        page.parser_invocation_id = None
    db.flush()
    for receipt in db.scalars(
        select(TechnicalParserInvocationReceipt).where(
            TechnicalParserInvocationReceipt.run_id == run_claim.run_id
        )
    ):
        db.delete(receipt)
    db.flush()
    for invocation in db.scalars(
        select(TechnicalParserInvocation).where(
            TechnicalParserInvocation.run_id == run_claim.run_id
        )
    ):
        db.delete(invocation)
    db.flush()
    db.commit()

    legacy_claim = replace(
        run_claim,
        record_version=run.record_version,
        run_schema="technical-extraction-run-v1",
        runtime_profile_sha256=None,
        runtime_attestation_sha256=None,
        layout_invocation_id=None,
    )
    result = aggregate_technical_extraction_run(
        db,
        claim=legacy_claim,
        source_snapshot=_snapshot(db, legacy_claim),
        artifact_storage_root=tmp_path,
        now=START + timedelta(minutes=2),
    )
    manifest = verify_technical_extraction_manifest(
        db,
        run_id=legacy_claim.run_id,
        artifact_storage_root=tmp_path,
    )
    payload = manifest.as_dict()

    assert result.status == "completed"
    assert result.manifest_sha256 == manifest.sha256
    assert payload["schema"] == "technical-extraction-manifest-v1"
    assert "invocations" not in payload
    assert "layout_invocation_id" not in payload
    assert "runtime_attestation" not in payload
    assert "runtime_attestation_sha256" not in payload
    assert "runtime_profile_sha256" not in payload
    assert all(
        "parser_invocation_id" not in page
        for page in payload["pages"]  # type: ignore[union-attr]
    )


def test_manifest_verification_detects_artifact_path_tampering(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    aggregate_technical_extraction_run(
        db,
        claim=run_claim,
        source_snapshot=_snapshot(db, run_claim),
        artifact_storage_root=tmp_path,
        now=START + timedelta(minutes=2),
    )
    artifact = db.scalar(
        select(TechnicalDerivedArtifact).where(
            TechnicalDerivedArtifact.run_id == run_claim.run_id,
            TechnicalDerivedArtifact.artifact_kind == "page_evidence_json",
        )
    )
    assert artifact is not None
    artifact.storage_path = "derived/tampered/evidence.json"
    artifact.record_version += 1
    db.commit()

    with pytest.raises(TechnicalExtractionError) as tampered:
        verify_technical_extraction_manifest(
            db,
            run_id=run_claim.run_id,
            artifact_storage_root=tmp_path,
        )
    assert tampered.value.code == "EXTRACTION_ARTIFACT_BINDING_MISMATCH"


def test_manifest_reconstruction_rejects_unbound_extra_artifact(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    extra = TechnicalDerivedArtifact(
        run_id=run_claim.run_id,
        page_number=2,
        artifact_kind="page_image_png",
        media_type="image/png",
        sha256="9" * 64,
        size_bytes=50,
        storage_path="derived/extra.png",
    )
    db.add(extra)
    db.commit()

    with pytest.raises(TechnicalExtractionError) as unbound:
        aggregate_technical_extraction_run(
            db,
            claim=run_claim,
            source_snapshot=_snapshot(db, run_claim),
            artifact_storage_root=tmp_path,
            now=START + timedelta(minutes=2),
        )
    assert unbound.value.code == "EXTRACTION_RUN_PERSISTENCE_CONFLICT"
    assert not db.in_transaction()


def test_second_exact_unreceipted_invocation_reservation_is_pending(
    db: Session,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    request = _layout_request(claim)
    invocation_id = str(uuid4())
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=request,
        runtime_attestation=attestation,
        invocation_id=invocation_id,
        now=START + timedelta(milliseconds=1),
    )

    with pytest.raises(TechnicalExtractionError) as pending:
        reserve_technical_parser_invocation(
            db,
            claim=claim,
            operation="layout",
            request=request,
            runtime_attestation=attestation,
            invocation_id=invocation_id,
            now=START + timedelta(milliseconds=2),
        )

    assert reservation.idempotent_replay is False
    assert pending.value.code == "EXTRACTION_INVOCATION_PENDING"
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0


def test_second_exact_terminal_invocation_reservation_is_rejected(
    db: Session,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    request = _layout_request(claim)
    invocation_id = str(uuid4())
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=request,
        runtime_attestation=attestation,
        invocation_id=invocation_id,
        now=START + timedelta(milliseconds=1),
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=_not_started_receipt(reservation, attestation),
    )

    with pytest.raises(TechnicalExtractionError) as terminal:
        reserve_technical_parser_invocation(
            db,
            claim=claim,
            operation="layout",
            request=request,
            runtime_attestation=attestation,
            invocation_id=invocation_id,
            now=START + timedelta(milliseconds=3),
        )

    assert terminal.value.code == "EXTRACTION_INVOCATION_ALREADY_TERMINAL"
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 1


@pytest.mark.parametrize("terminal_receipt", (False, True))
def test_unsettled_layout_invocation_blocks_stale_run_claim(
    db: Session,
    terminal_receipt: bool,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(seconds=1),
    )
    if terminal_receipt:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=_not_started_receipt(reservation, attestation),
        )

    assert (
        claim_next_technical_extraction_run(
            db,
            now=START + timedelta(minutes=30),
        )
        is None
    )
    persisted = db.get(TechnicalExtractionRun, claim.run_id)
    assert persisted is not None
    assert persisted.attempt_token == reservation.run_claim.attempt_token
    assert persisted.attempt_count == reservation.run_claim.attempt_count


@pytest.mark.parametrize("terminal_receipt", (False, True))
def test_unsettled_page_invocation_blocks_stale_run_and_page_claims(
    db: Session,
    terminal_receipt: bool,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    attestation = _runtime_attestation(page_claim.run_claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=page_claim.run_claim,
        page_claim=page_claim,
        operation="page",
        request=_page_request(page_claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(seconds=3),
    )
    page_claim = replace(page_claim, run_claim=reservation.run_claim)
    if terminal_receipt:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=_not_started_receipt(reservation, attestation),
        )

    assert (
        claim_next_technical_extraction_run(
            db,
            now=START + timedelta(minutes=30),
        )
        is None
    )
    with pytest.raises(TechnicalExtractionError) as blocked:
        claim_technical_extraction_page(
            db,
            run_claim=page_claim.run_claim,
            page_number=1,
            now=START + timedelta(minutes=30),
        )
    assert blocked.value.code == "EXTRACTION_INVOCATION_PENDING"


@pytest.mark.parametrize("terminal_receipt", (False, True))
def test_settled_historical_layout_invocation_does_not_block_retry(
    db: Session,
    terminal_receipt: bool,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(seconds=1),
    )
    if terminal_receipt:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=_not_started_receipt(reservation, attestation),
        )
    release_technical_extraction_run_for_retry(
        db,
        claim=reservation.run_claim,
        outcome_code="EXTRACTION_PARSER_TIMEOUT",
        now=START + timedelta(seconds=2),
    )

    retry = claim_next_technical_extraction_run(
        db,
        now=START + timedelta(seconds=3),
    )
    assert retry is not None
    assert retry.run_id == claim.run_id
    assert retry.attempt_token != reservation.run_claim.attempt_token
    assert retry.attempt_count == reservation.run_claim.attempt_count + 1


@pytest.mark.parametrize("terminal_receipt", (False, True))
def test_settled_historical_page_invocation_does_not_block_page_retry(
    db: Session,
    terminal_receipt: bool,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    attestation = _runtime_attestation(page_claim.run_claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=page_claim.run_claim,
        page_claim=page_claim,
        operation="page",
        request=_page_request(page_claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(seconds=3),
    )
    page_claim = replace(page_claim, run_claim=reservation.run_claim)
    if terminal_receipt:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=_not_started_receipt(reservation, attestation),
        )
    refreshed_run = fail_technical_extraction_page(
        db,
        claim=page_claim,
        outcome_code="EXTRACTION_PARSER_TIMEOUT",
        retryable=True,
        now=START + timedelta(seconds=4),
    )

    retry = claim_technical_extraction_page(
        db,
        run_claim=refreshed_run,
        page_number=1,
        now=START + timedelta(seconds=5),
    )
    assert retry.attempt_token != page_claim.attempt_token
    assert retry.attempt_count == page_claim.attempt_count + 1


def test_not_started_receipt_with_null_start_time_exactly_replays(
    db: Session,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    receipt = _not_started_receipt(reservation, attestation)

    first = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    replay = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )

    persisted = db.get(TechnicalParserInvocationReceipt, reservation.invocation_id)
    assert persisted is not None
    assert persisted.started_at is None
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.receipt_sha256 == first.receipt_sha256


def test_not_started_receipt_accepts_and_replays_image_id_attestation_drift(
    db: Session,
) -> None:
    claim = _new_run_claim(db)
    reserved_attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=reserved_attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    observed_attestation = _runtime_attestation(
        reservation.run_claim,
        image_id=f"sha256:{'9' * 64}",
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation="layout",
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=reservation.runtime_attestation_sha256,
        attestation=observed_attestation,
        outcome_code="PARSER_EXECUTION_FAILED",
        container_id=None,
        started_at=None,
        completed_at=START + timedelta(milliseconds=2),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )

    first = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    replay = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )

    invocation = db.get(TechnicalParserInvocation, reservation.invocation_id)
    persisted = db.get(TechnicalParserInvocationReceipt, reservation.invocation_id)
    assert invocation is not None
    assert persisted is not None
    assert observed_attestation.sha256 != reserved_attestation.sha256
    assert reservation.runtime_attestation_sha256 == reserved_attestation.sha256
    assert invocation.runtime_attestation_sha256 == reserved_attestation.sha256
    assert persisted.runtime_attestation_sha256 == reserved_attestation.sha256
    assert (
        persisted.receipt_json["expected_attestation_sha256"]
        == reserved_attestation.sha256
    )
    assert (
        persisted.receipt_json["runtime_attestation_sha256"]
        == observed_attestation.sha256
    )
    assert persisted.receipt_json["runtime_attestation"] == observed_attestation.as_dict()
    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.receipt_sha256 == first.receipt_sha256


def test_not_started_receipt_rejects_runtime_host_attestation_drift(
    db: Session,
) -> None:
    claim = _new_run_claim(db)
    reserved_attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=reserved_attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    observed_attestation = _runtime_attestation(
        reservation.run_claim,
        runtime_host="unix:///run/user/1001/docker.sock",
    )
    receipt = create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation="layout",
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=reservation.runtime_attestation_sha256,
        attestation=observed_attestation,
        outcome_code="PARSER_EXECUTION_FAILED",
        container_id=None,
        started_at=None,
        completed_at=START + timedelta(milliseconds=2),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )

    with pytest.raises(TechnicalExtractionError) as rejected:
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=receipt,
        )

    invocation = db.get(TechnicalParserInvocation, reservation.invocation_id)
    assert invocation is not None
    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    assert invocation.runtime_attestation_sha256 == reserved_attestation.sha256
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0


def test_commit_then_raise_reservation_reconciles_once_then_blocks_second_caller(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    request = _layout_request(claim)
    invocation_id = str(uuid4())
    original_commit = db.commit

    def commit_then_raise() -> None:
        original_commit()
        raise SQLAlchemyError("reservation commit acknowledgement lost")

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "commit", commit_then_raise)
        reservation = reserve_technical_parser_invocation(
            db,
            claim=claim,
            operation="layout",
            request=request,
            runtime_attestation=attestation,
            invocation_id=invocation_id,
            now=START + timedelta(milliseconds=1),
        )

    assert reservation.idempotent_replay is True
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0
    with pytest.raises(TechnicalExtractionError) as pending:
        reserve_technical_parser_invocation(
            db,
            claim=claim,
            operation="layout",
            request=request,
            runtime_attestation=attestation,
            invocation_id=invocation_id,
            now=START + timedelta(milliseconds=2),
        )
    assert pending.value.code == "EXTRACTION_INVOCATION_PENDING"


def test_commit_then_raise_not_started_receipt_reconciles_exactly(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claim = _new_run_claim(db)
    attestation = _runtime_attestation(claim)
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=_layout_request(claim),
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=START + timedelta(milliseconds=1),
    )
    receipt = _not_started_receipt(reservation, attestation)
    original_commit = db.commit

    def commit_then_raise() -> None:
        original_commit()
        raise SQLAlchemyError("receipt commit acknowledgement lost")

    with monkeypatch.context() as scoped:
        scoped.setattr(db, "commit", commit_then_raise)
        binding = record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=receipt,
        )

    assert binding.idempotent_replay is True
    assert binding.execution_state == "not_started"
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 1
    replay = record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=receipt,
    )
    assert replay.idempotent_replay is True


@pytest.mark.parametrize("operation", ("layout", "page"))
def test_mismatched_canonical_request_creates_no_invocation(
    db: Session,
    operation: Literal["layout", "page"],
) -> None:
    if operation == "layout":
        claim = _new_run_claim(db)
        page_claim = None
        request = _layout_request(
            claim,
            ocr_low_confidence_threshold=Decimal("79"),
        )
    else:
        claim, _page_ids = _claim_and_initialize(db, page_count=1)
        page_claim = claim_technical_extraction_page(
            db,
            run_claim=claim,
            page_number=1,
            now=START + timedelta(seconds=2),
        )
        claim = page_claim.run_claim
        request = encode_technical_parser_request(
            technical_document_id=claim.technical_document_id,
            source_sha256=claim.source_sha256,
            source_size_bytes=claim.source_size_bytes,
            page_number=page_claim.page_number,
            page_count=page_claim.page_count,
            page_width_points=page_claim.layout_page_width_points,
            page_height_points=page_claim.layout_page_height_points,
            layout_sha256=page_claim.layout_sha256,
            extraction_policy=claim.extraction_policy,
            extraction_policy_sha256=claim.extraction_policy_sha256,
            worker_image_digest=claim.worker_image_digest,
            ocr_low_confidence_threshold=Decimal("79"),
        )
    invocation_count = db.scalar(select(func.count()).select_from(TechnicalParserInvocation))
    receipt_count = db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt))

    with pytest.raises(TechnicalExtractionError) as rejected:
        reserve_technical_parser_invocation(
            db,
            claim=claim,
            page_claim=page_claim,
            operation=operation,
            request=request,
            runtime_attestation=_runtime_attestation(claim),
            invocation_id=str(uuid4()),
            now=START + timedelta(seconds=3),
        )

    assert rejected.value.code == "EXTRACTION_REQUEST_INVALID"
    assert (
        db.scalar(select(func.count()).select_from(TechnicalParserInvocation))
        == invocation_count
    )
    assert (
        db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt))
        == receipt_count
    )


@pytest.mark.parametrize("boundary", ("acceptance", "manifest"))
def test_canonical_receipt_json_invocation_mismatch_is_rejected(
    db: Session,
    tmp_path: Path,
    boundary: Literal["acceptance", "manifest"],
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    page_claim = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    retained = _retain_for_claim(tmp_path, page_claim)
    page_claim, invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=page_claim,
        retained=retained,
    )
    if boundary == "manifest":
        completion = complete_technical_extraction_page(
            db,
            claim=page_claim,
            retained=retained,
            storage_root=tmp_path,
            extraction_policy_bytes=POLICY_BYTES,
            source_snapshot=_snapshot(db, page_claim.run_claim),
            parser_invocation_id=invocation_id,
            parser_output=parser_output,
            now=START + timedelta(seconds=3),
        )
        run_claim = completion.run_claim

    persisted = db.get(TechnicalParserInvocationReceipt, invocation_id)
    assert persisted is not None
    forged_payload = dict(persisted.receipt_json)
    forged_payload["invocation_id"] = str(uuid4())
    forged_bytes = json.dumps(
        forged_payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    persisted.receipt_json = forged_payload
    persisted.receipt_sha256 = hashlib.sha256(forged_bytes).hexdigest()
    db.commit()

    if boundary == "acceptance":
        with pytest.raises(TechnicalExtractionError) as rejected:
            complete_technical_extraction_page(
                db,
                claim=page_claim,
                retained=retained,
                storage_root=tmp_path,
                extraction_policy_bytes=POLICY_BYTES,
                source_snapshot=_snapshot(db, page_claim.run_claim),
                parser_invocation_id=invocation_id,
                parser_output=parser_output,
                now=START + timedelta(seconds=3),
            )
    else:
        with pytest.raises(TechnicalExtractionError) as rejected:
            aggregate_technical_extraction_run(
                db,
                claim=run_claim,
                source_snapshot=_snapshot(db, run_claim),
                artifact_storage_root=tmp_path,
                now=START + timedelta(minutes=2),
            )
    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"


def test_manifest_rejects_accepted_page_invocation_from_earlier_attempt(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=1)
    first = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=2),
    )
    invalid_output = b"invalid parser frame"
    earlier = _successful_invocation(
        db,
        claim=first.run_claim,
        page_claim=first,
        operation="page",
        request=_page_request(first),
        stdout_sha256=hashlib.sha256(invalid_output).hexdigest(),
        stdout_size_bytes=len(invalid_output),
    )
    first = replace(first, run_claim=earlier.run_claim)
    run_claim = fail_technical_extraction_page(
        db,
        claim=first,
        outcome_code="PAGE_PROTOCOL_INVALID",
        retryable=True,
        now=START + timedelta(seconds=3),
    )
    retry = claim_technical_extraction_page(
        db,
        run_claim=run_claim,
        page_number=1,
        now=START + timedelta(seconds=4),
    )
    retained = _retain_for_claim(tmp_path, retry)
    retry, accepted_invocation_id, parser_output = _successful_page_invocation(
        db,
        claim=retry,
        retained=retained,
    )
    completion = complete_technical_extraction_page(
        db,
        claim=retry,
        retained=retained,
        storage_root=tmp_path,
        extraction_policy_bytes=POLICY_BYTES,
        source_snapshot=_snapshot(db, retry.run_claim),
        parser_invocation_id=accepted_invocation_id,
        parser_output=parser_output,
        now=START + timedelta(seconds=5),
    )
    page = db.get(TechnicalExtractionPage, retry.page_id)
    assert page is not None
    assert page.attempt_count == 2
    page.parser_invocation_id = earlier.invocation_id
    page.record_version += 1
    db.commit()

    with pytest.raises(TechnicalExtractionError) as rejected:
        aggregate_technical_extraction_run(
            db,
            claim=completion.run_claim,
            source_snapshot=_snapshot(db, completion.run_claim),
            artifact_storage_root=tmp_path,
            now=START + timedelta(minutes=2),
        )
    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"


def test_mixed_run_attempt_history_aggregates_after_stale_reclaim(
    db: Session,
    tmp_path: Path,
) -> None:
    run_claim, _page_ids = _claim_and_initialize(db, page_count=2)
    run_claim = _complete_page(
        db,
        run_claim=run_claim,
        page_number=1,
        storage_root=tmp_path,
    )
    assert run_claim.attempt_count == 1
    reclaimed = claim_next_technical_extraction_run(
        db,
        now=START + timedelta(minutes=30),
    )
    assert reclaimed is not None
    assert reclaimed.run_id == run_claim.run_id
    assert reclaimed.attempt_count == 2
    reclaimed = _complete_page(
        db,
        run_claim=reclaimed,
        page_number=2,
        storage_root=tmp_path,
    )

    result = aggregate_technical_extraction_run(
        db,
        claim=reclaimed,
        source_snapshot=_snapshot(db, reclaimed),
        artifact_storage_root=tmp_path,
        now=START + timedelta(minutes=31),
    )
    manifest = verify_technical_extraction_manifest(
        db,
        run_id=reclaimed.run_id,
        artifact_storage_root=tmp_path,
    )
    run_attempt_counts = {
        invocation.run_attempt_count
        for invocation in db.scalars(
            select(TechnicalParserInvocation).where(
                TechnicalParserInvocation.run_id == reclaimed.run_id
            )
        )
    }

    assert result.status == "completed"
    assert result.manifest_sha256 == manifest.sha256
    assert manifest.schema == "technical-extraction-manifest-v2"
    assert run_attempt_counts == {1, 2}
