from __future__ import annotations

import hashlib
import json
import struct
import zlib
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Literal, Never

import pytest
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from classifire import physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import (
    Approval,
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
from classifire.services import technical_extraction_executor as executor_module
from classifire.services.technical_extraction import (
    TechnicalExtractionError,
    claim_next_technical_extraction_run,
    claim_technical_extraction_page,
    count_unsettled_technical_parser_invocations,
    fail_technical_extraction_page,
    get_claimed_technical_extraction_source_snapshot,
    initialize_technical_extraction_pages,
    record_technical_parser_invocation_receipt,
    request_technical_extraction_run,
    reserve_technical_parser_invocation,
    verify_technical_extraction_manifest,
)
from classifire.services.technical_extraction_executor import (
    TechnicalExtractionExecutionResult,
    TechnicalParserExecutionError,
    execute_next_technical_extraction,
)
from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionReceipt,
    TechnicalParserExecutionSuccess,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
)
from classifire.services.technical_parser_oci import (
    TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    TechnicalParserOciCleanupProof,
)
from classifire.services.technical_parser_protocol import (
    TECHNICAL_PARSER_LAYOUT_SCHEMA,
    TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
    TechnicalParserDocumentLayout,
    TechnicalParserLayoutRequest,
    TechnicalParserRequest,
    encode_technical_parser_layout_request,
    parse_technical_parser_layout_request,
    parse_technical_parser_layout_result,
    parse_technical_parser_request,
)
from classifire.services.technical_parser_reconciliation import (
    reconcile_technical_parser_worker_startup,
)

POLICY = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"schema":"technical-extraction-policy-v1"}'
POLICY_SHA = hashlib.sha256(POLICY_BYTES).hexdigest()
WORKER_SHA = "b" * 64
RUNTIME_PROFILE_SHA = "c" * 64
RUNTIME_EXECUTABLE_SHA = "d" * 64
SECCOMP_SHA = "e" * 64
IMAGE_ID = f"sha256:{'f' * 64}"
OCI_DAEMON_IDENTITY_SHA = "1" * 64
EXECUTION_FENCE_SHA = "2" * 64
CONTROLLER_OWNER_ID = "12345678-1234-4123-8123-123456789abc"


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


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


def _framed(header: dict[str, object], evidence: bytes = b"", image: bytes = b"") -> bytes:
    encoded = _canonical(header)
    return len(encoded).to_bytes(4, "big") + encoded + evidence + image


def _cleanup_proof(
    *,
    invocation_id: str,
    attestation: TechnicalParserRuntimeAttestation,
) -> TechnicalParserOciCleanupProof:
    completed_at = datetime.now(UTC)
    payload = {
        "cleanup_confirmed": True,
        "completed_at": completed_at.isoformat(timespec="microseconds").replace(
            "+00:00",
            "Z",
        ),
        "controller_owner_id": CONTROLLER_OWNER_ID,
        "execution_fence_sha256": EXECUTION_FENCE_SHA,
        "invocation_id": invocation_id,
        "observed_container_id": hashlib.sha256(
            invocation_id.encode("ascii")
        ).hexdigest(),
        "observed_container_state": "exited",
        "oci_daemon_identity_sha256": OCI_DAEMON_IDENTITY_SHA,
        "runtime_attestation_sha256": attestation.sha256,
        "runtime_profile_sha256": RUNTIME_PROFILE_SHA,
        "schema": TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    }
    canonical = _canonical(payload)
    return TechnicalParserOciCleanupProof(
        schema=TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
        invocation_id=invocation_id,
        runtime_attestation_sha256=attestation.sha256,
        controller_owner_id=CONTROLLER_OWNER_ID,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
        oci_daemon_identity_sha256=OCI_DAEMON_IDENTITY_SHA,
        execution_fence_sha256=EXECUTION_FENCE_SHA,
        observed_container_id=hashlib.sha256(
            invocation_id.encode("ascii")
        ).hexdigest(),
        observed_container_state="exited",
        cleanup_confirmed=True,
        completed_at=completed_at,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _evidence(request: TechnicalParserRequest, image: bytes) -> bytes:
    return _canonical(
        {
            "schema": "technical-page-evidence-v1",
            "source": {
                "technical_document_id": request.technical_document_id,
                "sha256": request.source_sha256,
                "size_bytes": request.source_size_bytes,
            },
            "page": {
                "number": request.page_number,
                "count": request.page_count,
                "width_points": _number(request.page_width_points),
                "height_points": _number(request.page_height_points),
                "image": {
                    "sha256": hashlib.sha256(image).hexdigest(),
                    "size_bytes": len(image),
                    "width_pixels": 8,
                    "height_pixels": 6,
                },
            },
            "extraction": {
                "policy_version": request.extraction_policy,
                "policy_sha256": request.extraction_policy_sha256,
                "worker_image_digest": request.worker_image_digest,
                "ocr_low_confidence_threshold": _number(request.ocr_low_confidence_threshold),
                "native_text_blocks": [
                    {
                        "bbox": {"x0": 10, "x1": 100, "y0": 20, "y1": 40},
                        "id": f"native-{request.page_number}",
                        "order": 1,
                        "text": f"Draft evidence page {request.page_number}",
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
                "human_review_required": False,
                "warnings": [],
            },
        }
    )


class FakeParserRunner:
    worker_image_digest = WORKER_SHA
    runtime_profile_sha256 = RUNTIME_PROFILE_SHA

    def __init__(
        self,
        source_bytes: bytes,
        *,
        page_behaviors: dict[int, list[str]] | None = None,
        layout_behavior: str = "success",
        page_callback: Callable[[TechnicalParserRequest], None] | None = None,
    ) -> None:
        self.source_bytes = source_bytes
        self.page_behaviors = {
            number: list(behaviors) for number, behaviors in (page_behaviors or {}).items()
        }
        self.layout_behavior = layout_behavior
        self.page_callback = page_callback
        self.layout_requests: list[TechnicalParserLayoutRequest] = []
        self.page_requests: list[TechnicalParserRequest] = []
        self.evidence_by_page: dict[int, bytes] = {}
        self.image_by_page: dict[int, bytes] = {}

    def probe(
        self,
        *,
        extraction_policy: str,
        extraction_policy_sha256: str,
    ):
        return create_technical_parser_runtime_attestation(
            engine="oci",
            schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
            claims={
                "controller_owner_id": CONTROLLER_OWNER_ID,
                "execution_fence_sha256": EXECUTION_FENCE_SHA,
                "extraction_policy": extraction_policy,
                "extraction_policy_sha256": extraction_policy_sha256,
                "image_id": IMAGE_ID,
                "image_reference": f"registry.example/classifire/parser@sha256:{WORKER_SHA}",
                "oci_profile_schema": "technical-parser-oci-profile-v1",
                "oci_daemon_identity_sha256": OCI_DAEMON_IDENTITY_SHA,
                "platform": "linux/amd64",
                "runtime_executable_sha256": RUNTIME_EXECUTABLE_SHA,
                "runtime_host": "unix:///run/user/1000/docker.sock",
                "runtime_profile_sha256": RUNTIME_PROFILE_SHA,
                "seccomp_profile_sha256": SECCOMP_SHA,
                "transport_schema": "technical-parser-stdin-frame-v1",
                "worker_image_digest": WORKER_SHA,
            },
        )

    def _success(
        self,
        *,
        operation: str,
        invocation_id: str,
        expected_attestation_sha256: str,
        output: bytes,
    ) -> TechnicalParserExecutionSuccess:
        attestation = self.probe(
            extraction_policy=POLICY,
            extraction_policy_sha256=POLICY_SHA,
        )
        now = datetime.now(UTC)
        return TechnicalParserExecutionSuccess(
            output=output,
            receipt=create_technical_parser_execution_receipt(
                execution_state="succeeded",
                operation=operation,
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                attestation=attestation,
                outcome_code="PARSER_EXECUTION_SUCCEEDED",
                container_id=hashlib.sha256(invocation_id.encode("ascii")).hexdigest(),
                started_at=now,
                completed_at=now,
                exit_code=0,
                stdout_sha256=hashlib.sha256(output).hexdigest(),
                stdout_size_bytes=len(output),
                cleanup_confirmed=True,
            ),
        )

    def _read_source(self, source: BinaryIO) -> None:
        assert source.read() == self.source_bytes

    def inspect_layout(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        if prepare is not None:
            prepare()
        if authorize is not None:
            authorize()
        self._read_source(source)
        parsed = parse_technical_parser_layout_request(request)
        self.layout_requests.append(parsed)
        if self.layout_behavior == "timeout":
            output = _canonical(
                {
                    "error_code": "PARSER_LAYOUT_TIMEOUT",
                    "retryable": False,
                    "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
                    "status": "error",
                }
            )
            success = self._success(
                operation="layout",
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                output=output,
            )
            if finalize is not None:
                finalize(success.receipt)
            return success
        output = _canonical(
            {
                "extraction_policy": parsed.extraction_policy,
                "extraction_policy_sha256": parsed.extraction_policy_sha256,
                "page_count": 2,
                "pages": [
                    {
                        "count": 2,
                        "height_points": 792,
                        "number": 1,
                        "width_points": 612,
                    },
                    {
                        "count": 2,
                        "height_points": 612,
                        "number": 2,
                        "width_points": 792,
                    },
                ],
                "schema": TECHNICAL_PARSER_LAYOUT_SCHEMA,
                "source_sha256": parsed.source_sha256,
                "source_size_bytes": parsed.source_size_bytes,
                "technical_document_id": parsed.technical_document_id,
                "worker_image_digest": parsed.worker_image_digest,
            }
        )
        success = self._success(
            operation="layout",
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            output=output,
        )
        if finalize is not None:
            finalize(success.receipt)
        return success

    def extract_page(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        if prepare is not None:
            prepare()
        if authorize is not None:
            authorize()
        self._read_source(source)
        parsed = parse_technical_parser_request(request)
        self.page_requests.append(parsed)
        if self.page_callback is not None:
            self.page_callback(parsed)
        behaviors = self.page_behaviors.setdefault(parsed.page_number, ["success"])
        behavior = behaviors.pop(0) if behaviors else "success"
        if behavior == "timeout":
            output = _framed(
                {
                    "error_code": "PARSER_PAGE_TIMEOUT",
                    "page_number": parsed.page_number,
                    "retryable": False,
                    "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
                    "status": "error",
                }
            )
            success = self._success(
                operation="page",
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                output=output,
            )
            if finalize is not None:
                finalize(success.receipt)
            return success

        image = _png()
        evidence = b"{}" if behavior == "malformed_evidence" else _evidence(parsed, image)
        width = (
            parsed.page_width_points + Decimal(1)
            if behavior == "forged_geometry"
            else parsed.page_width_points
        )
        header = {
            "evidence_sha256": hashlib.sha256(evidence).hexdigest(),
            "evidence_size_bytes": len(evidence),
            "image_height_pixels": 6,
            "image_sha256": hashlib.sha256(image).hexdigest(),
            "image_size_bytes": len(image),
            "image_width_pixels": 8,
            "page_count": parsed.page_count,
            "page_height_points": _number(parsed.page_height_points),
            "page_number": parsed.page_number,
            "page_width_points": _number(width),
            "schema": TECHNICAL_PARSER_PAGE_FRAME_SCHEMA,
            "status": "ok",
        }
        self.evidence_by_page[parsed.page_number] = evidence
        self.image_by_page[parsed.page_number] = image
        output = _framed(header, evidence, image)
        success = self._success(
            operation="page",
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            output=output,
        )
        if finalize is not None:
            finalize(success.receipt)
        return success


class ContainmentLostThenCleanupRunner(FakeParserRunner):
    def __init__(
        self,
        source_bytes: bytes,
        *,
        lose_on: Literal["layout", "page"],
    ) -> None:
        super().__init__(source_bytes)
        self.lose_on = lose_on
        self.cleanup_calls: list[tuple[str, str]] = []

    def _raise_containment_lost(
        self,
        *,
        operation: Literal["layout", "page"],
        invocation_id: str,
        expected_attestation_sha256: str,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None,
    ) -> Never:
        attestation = self.probe(
            extraction_policy=POLICY,
            extraction_policy_sha256=POLICY_SHA,
        )
        current = datetime.now(UTC)
        error = TechnicalParserExecutionError(
            "PARSER_EXECUTION_CONTAINMENT_LOST",
            receipt=create_technical_parser_execution_receipt(
                execution_state="containment_lost",
                operation=operation,
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                attestation=attestation,
                outcome_code="PARSER_EXECUTION_CONTAINMENT_LOST",
                container_id=hashlib.sha256(
                    invocation_id.encode("ascii")
                ).hexdigest(),
                started_at=current,
                completed_at=current,
                exit_code=None,
                stdout_sha256=None,
                stdout_size_bytes=None,
                cleanup_confirmed=False,
            ),
        )
        assert error.receipt is not None
        if finalize is not None:
            finalize(error.receipt)
        raise error

    def inspect_layout(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        if self.lose_on != "layout":
            return super().inspect_layout(
                request,
                source=source,
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                prepare=prepare,
                authorize=authorize,
                finalize=finalize,
            )
        if prepare is not None:
            prepare()
        if authorize is not None:
            authorize()
        self._read_source(source)
        self.layout_requests.append(parse_technical_parser_layout_request(request))
        self._raise_containment_lost(
            operation="layout",
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            finalize=finalize,
        )

    def extract_page(
        self,
        request: bytes,
        *,
        source: BinaryIO,
        invocation_id: str,
        expected_attestation_sha256: str,
        prepare: Callable[[], None] | None = None,
        authorize: Callable[[], None] | None = None,
        finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
    ) -> TechnicalParserExecutionSuccess:
        if self.lose_on != "page":
            return super().extract_page(
                request,
                source=source,
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
                prepare=prepare,
                authorize=authorize,
                finalize=finalize,
            )
        if prepare is not None:
            prepare()
        if authorize is not None:
            authorize()
        self._read_source(source)
        self.page_requests.append(parse_technical_parser_request(request))
        self._raise_containment_lost(
            operation="page",
            invocation_id=invocation_id,
            expected_attestation_sha256=expected_attestation_sha256,
            finalize=finalize,
        )

    def cleanup_orphan_invocation(
        self,
        *,
        invocation_id: str,
        operation: Literal["layout", "page"],
        persisted_runtime_attestation: TechnicalParserRuntimeAttestation,
        finalize: Callable[[TechnicalParserOciCleanupProof], None] | None = None,
    ) -> TechnicalParserOciCleanupProof:
        assert operation == self.lose_on
        proof = _cleanup_proof(
            invocation_id=invocation_id,
            attestation=persisted_runtime_attestation,
        )
        assert finalize is not None
        finalize(proof)
        self.cleanup_calls.append((invocation_id, operation))
        return proof


class ForbiddenRunner:
    @property
    def worker_image_digest(self) -> str:
        raise AssertionError("disabled executor inspected the runner")

    @property
    def runtime_profile_sha256(self) -> str:
        raise AssertionError("disabled executor inspected the runtime profile")

    def probe(self, **_kwargs):
        raise AssertionError("disabled executor probed the runner")

    def inspect_layout(self, request: bytes, *, source: BinaryIO, **_kwargs):
        raise AssertionError("disabled executor invoked layout")

    def extract_page(self, request: bytes, *, source: BinaryIO, **_kwargs):
        raise AssertionError("disabled executor invoked a page")


def _seed(
    db: Session,
    tmp_path: Path,
) -> tuple[str, str, bytes, Settings]:
    storage_root = (tmp_path / "storage").resolve()
    storage_root.mkdir()
    source_bytes = b"%PDF-1.7\nsynthetic executor source\n%%EOF\n"
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    source_path = storage_root / source_sha[:2] / source_sha[2:4] / f"{source_sha}.pdf"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(source_bytes)
    actor = User(
        email="executor@example.test",
        full_name="Extraction Executor",
        password_hash="unused",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(actor)
    db.flush()
    stored = StoredFile(
        original_filename="source.pdf",
        media_type="application/pdf",
        storage_path=str(source_path),
        sha256=source_sha,
        size_bytes=len(source_bytes),
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=actor.id,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id="TECH-EXECUTOR",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Executor source",
    )
    db.add(document)
    db.commit()
    requested = request_technical_extraction_run(
        db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal(80),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    settings = Settings(
        _env_file=None,
        env="test",
        storage_root=storage_root,
        technical_extraction_executor_enabled=True,
    )
    return requested.run_id, stored.id, source_bytes, settings


def _make_parser_invocation_stale(db: Session, invocation_id: str) -> None:
    stale_at = datetime.now(UTC) - timedelta(minutes=20)
    invocation = db.get(TechnicalParserInvocation, invocation_id)
    receipt = db.get(TechnicalParserInvocationReceipt, invocation_id)
    assert invocation is not None
    assert receipt is not None
    run = db.get(TechnicalExtractionRun, invocation.run_id)
    assert run is not None
    invocation.created_at = stale_at
    receipt.created_at = stale_at
    run.attempt_started_at = stale_at
    if invocation.page_id is not None:
        page = db.get(TechnicalExtractionPage, invocation.page_id)
        assert page is not None
        page.attempt_started_at = stale_at
    db.commit()


def _resolve_policy(policy: str, policy_sha256: str) -> bytes:
    assert policy == POLICY
    assert policy_sha256 == POLICY_SHA
    return POLICY_BYTES


def _assert_no_authority(db: Session) -> None:
    assert db.scalar(select(func.count()).select_from(TechnicalVariant)) == 0
    assert db.scalar(select(func.count()).select_from(Approval)) == 0
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def _execute(
    db: Session,
    *,
    settings: Settings,
    runner: FakeParserRunner,
    max_page_attempts: int = 3,
) -> TechnicalExtractionExecutionResult:
    return execute_next_technical_extraction(
        db,
        settings=settings,
        runner=runner,
        policy_resolver=_resolve_policy,
        max_page_attempts=max_page_attempts,
    )


def test_disabled_executor_claims_nothing_and_invokes_nothing(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    disabled = settings.model_copy(update={"technical_extraction_executor_enabled": False})

    def forbidden_resolver(_policy: str, _sha256: str) -> bytes:
        raise AssertionError("disabled executor resolved a policy")

    result = execute_next_technical_extraction(
        db,
        settings=disabled,
        runner=ForbiddenRunner(),
        policy_resolver=forbidden_resolver,
    )

    assert result == TechnicalExtractionExecutionResult(state="disabled")
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "queued"
    assert run.attempt_count == 0
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0
    _assert_no_authority(db)


@pytest.mark.parametrize(
    "mismatch",
    ("method", "request", "attestation", "source_snapshot"),
)
def test_invoke_and_record_rejects_pre_run_binding_mismatch_without_side_effects(
    db: Session,
    tmp_path: Path,
    mismatch: str,
) -> None:
    _run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    claim = claim_next_technical_extraction_run(db)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    method = "layout"
    invocation_request = request
    invocation_snapshot = snapshot
    invocation_attestation = attestation
    invocation_claim = claim
    if mismatch == "method":
        method = "page"
    elif mismatch == "request":
        invocation_request = b""
    elif mismatch == "attestation":
        invocation_claim = replace(
            claim,
            runtime_attestation_sha256=attestation.sha256,
        )
        payload = attestation.as_dict()
        claims = payload["claims"]
        assert isinstance(claims, dict)
        claims["image_id"] = f"sha256:{'9' * 64}"
        invocation_attestation = create_technical_parser_runtime_attestation(
            engine="oci",
            claims=claims,
            schema=attestation.schema,
        )
    else:
        invocation_snapshot = replace(snapshot, sha256="9" * 64)
    admission = executor_module._InvocationAdmission()

    with pytest.raises(TechnicalExtractionError) as rejected:
        executor_module._invoke_and_record(
            db,
            runner=runner,
            method=method,  # type: ignore[arg-type]
            request=invocation_request,
            snapshot=invocation_snapshot,
            storage_root=settings.storage_root,
            claim=invocation_claim,
            page_claim=None,
            invocation_id="12345678-1234-4123-8123-123456789abc",
            admission=admission,
            attestation=invocation_attestation,
        )

    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    assert admission.reservation is None
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0


@pytest.mark.parametrize(
    "durable_state",
    ("missing", "tampered", "terminal"),
)
def test_invoke_and_record_rechecks_durable_reservation_before_runner_side_effects(
    db: Session,
    tmp_path: Path,
    durable_state: str,
) -> None:
    _run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    claim = claim_next_technical_extraction_run(db)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    admission = executor_module._InvocationAdmission()

    class DurableReservationRaceRunner(FakeParserRunner):
        def inspect_layout(
            self,
            request: bytes,
            *,
            source: BinaryIO,
            invocation_id: str,
            expected_attestation_sha256: str,
            prepare: Callable[[], None] | None = None,
            authorize: Callable[[], None] | None = None,
            finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
        ) -> TechnicalParserExecutionSuccess:
            del request, source, expected_attestation_sha256, finalize
            assert prepare is not None
            assert authorize is not None
            prepare()
            reservation = admission.reservation
            assert reservation is not None
            if durable_state == "missing":
                invocation = db.get(TechnicalParserInvocation, invocation_id)
                assert invocation is not None
                db.delete(invocation)
                db.commit()
            elif durable_state == "tampered":
                db.execute(
                    update(TechnicalParserInvocation)
                    .where(TechnicalParserInvocation.id == invocation_id)
                    .values(request_sha256="0" * 64)
                )
                db.commit()
            else:
                now = datetime.now(UTC)
                receipt = create_technical_parser_execution_receipt(
                    execution_state="not_started",
                    operation="layout",
                    invocation_id=invocation_id,
                    expected_attestation_sha256=attestation.sha256,
                    attestation=attestation,
                    outcome_code="PARSER_EXECUTION_FAILED",
                    container_id=None,
                    started_at=None,
                    completed_at=now,
                    exit_code=None,
                    stdout_sha256=None,
                    stdout_size_bytes=None,
                    cleanup_confirmed=True,
                )
                record_technical_parser_invocation_receipt(
                    db,
                    reservation=reservation,
                    receipt=receipt,
                )
            authorize()
            raise AssertionError("invalid durable reservation reached parser work")

    runner = DurableReservationRaceRunner(source_bytes)

    with pytest.raises(TechnicalExtractionError) as rejected:
        executor_module._invoke_and_record(
            db,
            runner=runner,
            method="layout",
            request=request,
            snapshot=snapshot,
            storage_root=settings.storage_root,
            claim=claim,
            page_claim=None,
            invocation_id="12345678-1234-4123-8123-123456789abc",
            admission=admission,
            attestation=attestation,
        )

    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    expected_receipts = 1 if durable_state == "terminal" else 0
    assert (
        db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt))
        == expected_receipts
    )


def test_invoke_and_record_reauthorizes_after_runner_entry_before_side_effects(
    db: Session,
    tmp_path: Path,
) -> None:
    _run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    claim = claim_next_technical_extraction_run(db)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )

    class ReservationRaceRunner(FakeParserRunner):
        def inspect_layout(
            self,
            request: bytes,
            *,
            source: BinaryIO,
            invocation_id: str,
            expected_attestation_sha256: str,
            prepare: Callable[[], None] | None = None,
            authorize: Callable[[], None] | None = None,
            finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
        ) -> TechnicalParserExecutionSuccess:
            del request, source, expected_attestation_sha256, finalize
            assert prepare is not None
            assert authorize is not None
            prepare()
            db.execute(
                update(TechnicalParserInvocation)
                .where(TechnicalParserInvocation.id == invocation_id)
                .values(request_sha256="0" * 64)
            )
            db.commit()
            authorize()
            raise AssertionError("stale reservation reached parser work")

    runner = ReservationRaceRunner(source_bytes)
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    admission = executor_module._InvocationAdmission()

    with pytest.raises(TechnicalExtractionError) as rejected:
        executor_module._invoke_and_record(
            db,
            runner=runner,
            method="layout",
            request=request,
            snapshot=snapshot,
            storage_root=settings.storage_root,
            claim=claim,
            page_claim=None,
            invocation_id="22345678-1234-4123-8123-123456789abc",
            admission=admission,
            attestation=attestation,
        )

    assert rejected.value.code == "EXTRACTION_INVOCATION_RECEIPT_INVALID"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0


def test_prepare_rejects_another_unsettled_invocation_before_second_reservation(
    db: Session,
    tmp_path: Path,
) -> None:
    _run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    claim = claim_next_technical_extraction_run(db)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    existing = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=request,
        runtime_attestation=attestation,
        invocation_id="32345678-1234-4123-8123-123456789abc",
    )
    admission = executor_module._InvocationAdmission()

    with pytest.raises(TechnicalExtractionError) as rejected:
        executor_module._invoke_and_record(
            db,
            runner=runner,
            method="layout",
            request=request,
            snapshot=snapshot,
            storage_root=settings.storage_root,
            claim=existing.run_claim,
            page_claim=None,
            invocation_id="42345678-1234-4123-8123-123456789abc",
            admission=admission,
            attestation=attestation,
        )

    assert rejected.value.code == "EXTRACTION_INVOCATION_PENDING"
    assert admission.reservation is None
    assert count_unsettled_technical_parser_invocations(db) == 1
    assert tuple(db.scalars(select(TechnicalParserInvocation.id))) == (
        existing.invocation_id,
    )
    assert runner.layout_requests == []


def test_terminal_receipt_is_durable_before_runner_releases_execution_scope(
    db: Session,
    tmp_path: Path,
) -> None:
    _run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    claim = claim_next_technical_extraction_run(db)
    assert claim is not None
    snapshot = get_claimed_technical_extraction_source_snapshot(db, claim=claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    observed_receipts: list[str] = []

    class FinalizationScopeRunner(FakeParserRunner):
        def inspect_layout(
            self,
            request: bytes,
            *,
            source: BinaryIO,
            invocation_id: str,
            expected_attestation_sha256: str,
            prepare: Callable[[], None] | None = None,
            authorize: Callable[[], None] | None = None,
            finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
        ) -> TechnicalParserExecutionSuccess:
            assert prepare is not None
            assert authorize is not None
            assert finalize is not None
            prepare()
            authorize()
            success = super().inspect_layout(
                request,
                source=source,
                invocation_id=invocation_id,
                expected_attestation_sha256=expected_attestation_sha256,
            )
            finalize(success.receipt)
            persisted = db.get(TechnicalParserInvocationReceipt, invocation_id)
            assert persisted is not None
            observed_receipts.append(persisted.receipt_sha256)
            return success

    runner = FinalizationScopeRunner(source_bytes)
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    admission = executor_module._InvocationAdmission()

    output = executor_module._invoke_and_record(
        db,
        runner=runner,
        method="layout",
        request=request,
        snapshot=snapshot,
        storage_root=settings.storage_root,
        claim=claim,
        page_claim=None,
        invocation_id="52345678-1234-4123-8123-123456789abc",
        admission=admission,
        attestation=attestation,
    )

    assert output
    assert admission.reservation is not None
    assert observed_receipts == [admission.finalized_receipt_sha256]


def test_raising_worker_digest_property_fails_closed_before_runner_side_effects(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)

    class RaisingDigestRunner(FakeParserRunner):
        @property
        def worker_image_digest(self) -> str:
            raise RuntimeError("synthetic property failure")

    runner = RaisingDigestRunner(source_bytes)

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_WORKER_BINDING_FAILED"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocation)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalParserInvocationReceipt)) == 0
    _assert_no_authority(db)


def test_valid_runner_completes_exact_draft_manifest_without_authority(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "completed"
    assert result.run_id == run_id
    assert result.outcome_code == "EXTRACTION_COMPLETE"
    assert result.manifest_sha256 is not None
    assert len(runner.layout_requests) == 1
    assert [request.page_number for request in runner.page_requests] == [1, 2]
    assert all(request.layout_sha256 for request in runner.page_requests)
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert tuple(page.status for page in pages) == ("completed", "completed")
    assert all(page.page_width_points == page.layout_page_width_points for page in pages)
    assert all(page.page_height_points == page.layout_page_height_points for page in pages)
    artifacts = tuple(
        db.scalars(
            select(TechnicalDerivedArtifact)
            .where(TechnicalDerivedArtifact.run_id == run_id)
            .order_by(
                TechnicalDerivedArtifact.page_number,
                TechnicalDerivedArtifact.artifact_kind,
            )
        )
    )
    assert len(artifacts) == 4
    for artifact in artifacts:
        expected = (
            runner.evidence_by_page[artifact.page_number]
            if artifact.artifact_kind == "page_evidence_json"
            else runner.image_by_page[artifact.page_number]
        )
        assert Path(artifact.storage_path).read_bytes() == expected
    manifest = verify_technical_extraction_manifest(
        db,
        run_id=run_id,
        artifact_storage_root=settings.storage_root,
    )
    assert manifest.sha256 == result.manifest_sha256
    _assert_no_authority(db)


@pytest.mark.parametrize(
    ("behavior", "expected_code"),
    (
        ("forged_geometry", "EXTRACTION_PAGE_PROTOCOL_INVALID"),
        ("malformed_evidence", "EXTRACTION_PAGE_VALIDATION_FAILED"),
    ),
)
def test_untrusted_page_output_cannot_override_layout_or_reach_retention(
    db: Session,
    tmp_path: Path,
    behavior: str,
    expected_code: str,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes, page_behaviors={1: [behavior]})

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "failed"
    assert result.outcome_code == expected_code
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert tuple(page.status for page in pages) == ("cancelled", "cancelled")
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    _assert_no_authority(db)


def test_worker_retryable_flag_is_ignored_in_favour_of_host_policy(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(
        source_bytes,
        page_behaviors={1: ["timeout", "success"]},
    )

    result = _execute(
        db,
        settings=settings,
        runner=runner,
        max_page_attempts=2,
    )

    assert result.state == "completed"
    first_page = db.scalar(
        select(TechnicalExtractionPage).where(
            TechnicalExtractionPage.run_id == run_id,
            TechnicalExtractionPage.page_number == 1,
        )
    )
    assert first_page is not None
    assert first_page.attempt_count == 2
    assert [request.page_number for request in runner.page_requests] == [1, 1, 2]
    _assert_no_authority(db)


def test_layout_error_retryability_is_host_owned_and_requeues_before_pages(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes, layout_behavior="timeout")

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "queued_for_retry"
    assert result.outcome_code == "EXTRACTION_PARSER_TIMEOUT"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "queued"
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0
    _assert_no_authority(db)


def test_containment_loss_is_terminal_before_pages_or_authority(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, _source_bytes, settings = _seed(db, tmp_path)

    class ContainmentLostRunner(FakeParserRunner):
        def inspect_layout(
            self,
            request: bytes,
            *,
            source: BinaryIO,
            invocation_id: str,
            expected_attestation_sha256: str,
            prepare: Callable[[], None] | None = None,
            authorize: Callable[[], None] | None = None,
            finalize: Callable[[TechnicalParserExecutionReceipt], None] | None = None,
        ) -> TechnicalParserExecutionSuccess:
            if prepare is not None:
                prepare()
            if authorize is not None:
                authorize()
            self._read_source(source)
            attestation = self.probe(
                extraction_policy=POLICY,
                extraction_policy_sha256=POLICY_SHA,
            )
            now = datetime.now(UTC)
            error = TechnicalParserExecutionError(
                "PARSER_EXECUTION_CONTAINMENT_LOST",
                receipt=create_technical_parser_execution_receipt(
                    execution_state="containment_lost",
                    operation="layout",
                    invocation_id=invocation_id,
                    expected_attestation_sha256=expected_attestation_sha256,
                    attestation=attestation,
                    outcome_code="PARSER_EXECUTION_CONTAINMENT_LOST",
                    container_id="1" * 64,
                    started_at=now,
                    completed_at=now,
                    exit_code=None,
                    stdout_sha256=None,
                    stdout_size_bytes=None,
                    cleanup_confirmed=False,
                ),
            )
            assert error.receipt is not None
            if finalize is not None:
                finalize(error.receipt)
            raise error

        def extract_page(self, request: bytes, *, source: BinaryIO, **_kwargs):
            raise AssertionError("containment loss invoked a page")

    result = execute_next_technical_extraction(
        db,
        settings=settings,
        runner=ContainmentLostRunner(_source_bytes),
        policy_resolver=_resolve_policy,
    )

    assert result.state == "reconciliation_required"
    assert result.outcome_code == "EXTRACTION_PARSER_CONTAINMENT_LOST"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "processing"
    assert run.outcome_code is None
    assert count_unsettled_technical_parser_invocations(db) == 1
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    _assert_no_authority(db)


@pytest.mark.parametrize("operation", ("layout", "page"))
def test_containment_loss_is_cleaned_at_startup_without_parser_replay(
    db: Session,
    tmp_path: Path,
    operation: Literal["layout", "page"],
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    enabled = settings.model_copy(
        update={"technical_parser_orphan_reconciliation_enabled": True}
    )
    runner = ContainmentLostThenCleanupRunner(source_bytes, lose_on=operation)

    execution = execute_next_technical_extraction(
        db,
        settings=enabled,
        runner=runner,
        policy_resolver=_resolve_policy,
    )

    invocation = db.scalar(
        select(TechnicalParserInvocation).where(
            TechnicalParserInvocation.run_id == run_id,
            TechnicalParserInvocation.operation == operation,
        )
    )
    assert invocation is not None
    receipt = db.get(TechnicalParserInvocationReceipt, invocation.id)
    run = db.get(TechnicalExtractionRun, run_id)
    assert execution.state == "reconciliation_required"
    assert execution.outcome_code == "EXTRACTION_PARSER_CONTAINMENT_LOST"
    assert receipt is not None
    assert receipt.execution_state == "containment_lost"
    assert receipt.cleanup_confirmed is False
    assert run is not None
    assert run.status == "processing"
    assert count_unsettled_technical_parser_invocations(db) == 1
    parser_calls = (len(runner.layout_requests), len(runner.page_requests))
    receipt_count = db.scalar(
        select(func.count()).select_from(TechnicalParserInvocationReceipt)
    )
    _make_parser_invocation_stale(db, invocation.id)

    startup = reconcile_technical_parser_worker_startup(
        db,
        settings=enabled,
        runner=runner,
    )

    run = db.get(TechnicalExtractionRun, run_id)
    persisted = db.get(TechnicalParserInvocationReceipt, invocation.id)
    assert startup.state == "ready"
    assert startup.claimed_count == 1
    assert startup.reconciled_count == 1
    assert startup.remaining_count == 0
    assert runner.cleanup_calls == [(invocation.id, operation)]
    assert (len(runner.layout_requests), len(runner.page_requests)) == parser_calls
    assert db.scalar(
        select(func.count()).select_from(TechnicalParserInvocationReceipt)
    ) == receipt_count
    assert persisted is not None
    assert persisted.receipt_sha256 == receipt.receipt_sha256
    assert persisted.execution_state == "containment_lost"
    assert persisted.cleanup_confirmed is False
    assert run is not None
    assert run.status == "failed"
    assert run.outcome_code == "EXTRACTION_PARSER_CONTAINMENT_LOST"
    assert run.outcome_retryable is False
    assert count_unsettled_technical_parser_invocations(db) == 0
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    if operation == "layout":
        assert pages == ()
    else:
        assert tuple(page.status for page in pages) == ("failed", "cancelled")
        assert pages[0].outcome_code == "PAGE_PARSER_CONTAINMENT_LOST"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    _assert_no_authority(db)


def test_layout_retry_budget_uses_persisted_run_attempts_across_invocations(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes, layout_behavior="timeout")

    first = _execute(
        db,
        settings=settings,
        runner=runner,
        max_page_attempts=2,
    )
    second = _execute(
        db,
        settings=settings,
        runner=runner,
        max_page_attempts=2,
    )

    assert first.state == "queued_for_retry"
    assert second.state == "failed"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.attempt_count == 2
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0


def test_exhausted_persisted_layout_budget_blocks_runner_before_invocation(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    run.attempt_count = 2
    run.outcome_code = "EXTRACTION_PARSER_TIMEOUT"
    run.outcome_retryable = True
    run.last_outcome_at = datetime(2020, 1, 1, tzinfo=UTC)
    db.commit()
    runner = FakeParserRunner(source_bytes)

    result = _execute(
        db,
        settings=settings,
        runner=runner,
        max_page_attempts=2,
    )

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_RUN_RETRY_EXHAUSTED"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.attempt_count == 3
    assert run.status == "failed"


def test_exhausted_persisted_page_budget_blocks_runner_after_stale_reclaim(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    stale = datetime(2020, 1, 1, tzinfo=UTC)
    claim = claim_next_technical_extraction_run(db, now=stale)
    assert claim is not None
    runner = FakeParserRunner(source_bytes)
    layout_request = encode_technical_parser_layout_request(
        technical_document_id=claim.technical_document_id,
        source_sha256=claim.source_sha256,
        source_size_bytes=claim.source_size_bytes,
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
    )
    attestation = runner.probe(
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
    )
    reservation = reserve_technical_parser_invocation(
        db,
        claim=claim,
        operation="layout",
        request=layout_request,
        runtime_attestation=attestation,
        invocation_id="87654321-4321-4876-8876-cba987654321",
        now=stale + timedelta(milliseconds=250),
    )
    layout_execution = runner.inspect_layout(
        layout_request,
        source=BytesIO(source_bytes),
        invocation_id=reservation.invocation_id,
        expected_attestation_sha256=attestation.sha256,
    )
    record_technical_parser_invocation_receipt(
        db,
        reservation=reservation,
        receipt=layout_execution.receipt,
    )
    parsed_layout = parse_technical_parser_layout_result(
        layout_execution.output,
        expected_technical_document_id=claim.technical_document_id,
        expected_source_sha256=claim.source_sha256,
        expected_source_size_bytes=claim.source_size_bytes,
        expected_extraction_policy=claim.extraction_policy,
        expected_extraction_policy_sha256=claim.extraction_policy_sha256,
        expected_worker_image_digest=claim.worker_image_digest,
    )
    assert isinstance(parsed_layout, TechnicalParserDocumentLayout)
    initialized = initialize_technical_extraction_pages(
        db,
        claim=reservation.run_claim,
        layout=executor_module._layout_binding(parsed_layout),
        parser_invocation_id=reservation.invocation_id,
        now=stale + timedelta(seconds=1),
    )
    run_claim = initialized.run_claim
    for attempt in range(2):
        page_claim = claim_technical_extraction_page(
            db,
            run_claim=run_claim,
            page_number=1,
            now=stale + timedelta(seconds=2 + attempt * 2),
        )
        run_claim = fail_technical_extraction_page(
            db,
            claim=page_claim,
            outcome_code="EXTRACTION_PARSER_TIMEOUT",
            retryable=True,
            now=stale + timedelta(seconds=3 + attempt * 2),
        )
    runner.layout_requests.clear()
    result = _execute(
        db,
        settings=settings,
        runner=runner,
        max_page_attempts=2,
    )

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_PAGE_RETRY_EXHAUSTED"
    assert runner.layout_requests == []
    assert runner.page_requests == []
    page = db.scalar(
        select(TechnicalExtractionPage).where(
            TechnicalExtractionPage.run_id == run_id,
            TechnicalExtractionPage.page_number == 1,
        )
    )
    assert page is not None
    assert page.attempt_count == 3
    assert page.status == "failed"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"


def test_source_quarantine_during_page_aborts_initialized_run_without_artifacts(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, stored_id, source_bytes, settings = _seed(db, tmp_path)
    changed = False

    def quarantine(_request: TechnicalParserRequest) -> None:
        nonlocal changed
        if changed:
            return
        changed = True
        with Session(db.get_bind()) as other:
            stored = other.get(StoredFile, stored_id)
            assert stored is not None
            stored.malware_scan_status = "infected"
            other.commit()

    runner = FakeParserRunner(source_bytes, page_callback=quarantine)

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_SOURCE_INVALID"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert tuple(page.status for page in pages) == ("cancelled", "cancelled")
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0
    _assert_no_authority(db)


def test_source_quarantine_between_pages_blocks_the_next_parser_invocation(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    original_complete = executor_module.complete_technical_extraction_page
    quarantined = False

    def complete_then_quarantine(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal quarantined
        completed = original_complete(*args, **kwargs)
        claim = kwargs["claim"]
        if claim.page_number == 1 and not quarantined:
            quarantined = True
            with Session(db.get_bind()) as other:
                stored = other.get(StoredFile, stored_id)
                assert stored is not None
                stored.malware_scan_status = "infected"
                other.commit()
        return completed

    monkeypatch.setattr(
        executor_module,
        "complete_technical_extraction_page",
        complete_then_quarantine,
    )

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_SOURCE_INVALID"
    assert [request.page_number for request in runner.page_requests] == [1]
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    assert tuple(page.status for page in pages) == ("completed", "cancelled")
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 2
    _assert_no_authority(db)


def test_tampered_source_binding_is_terminal_not_requeued(
    db: Session,
    tmp_path: Path,
) -> None:
    run_id, stored_id, source_bytes, settings = _seed(db, tmp_path)
    stored = db.get(StoredFile, stored_id)
    assert stored is not None
    Path(stored.storage_path).write_bytes(source_bytes + b"tampered")
    runner = FakeParserRunner(source_bytes)

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "failed"
    assert result.outcome_code == "EXTRACTION_SOURCE_INVALID"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "failed"
    assert run.outcome_retryable is False
    assert runner.layout_requests == []
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 0


def test_commit_acknowledgement_loss_reconciles_without_rerunning_page(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    original_commit = db.commit
    inject_loss = False
    lost_once = False

    def commit_then_raise_once() -> None:
        nonlocal lost_once
        original_commit()
        if inject_loss and not lost_once:
            lost_once = True
            raise SQLAlchemyError("synthetic acknowledgement loss")

    def arm_loss(request: TechnicalParserRequest) -> None:
        nonlocal inject_loss
        if request.page_number == 1:
            inject_loss = True

    monkeypatch.setattr(db, "commit", commit_then_raise_once)
    runner = FakeParserRunner(source_bytes, page_callback=arm_loss)

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "completed"
    assert lost_once is True
    assert [request.page_number for request in runner.page_requests] == [1, 2]
    assert (
        db.scalar(
            select(func.count())
            .select_from(TechnicalDerivedArtifact)
            .where(TechnicalDerivedArtifact.run_id == run_id)
        )
        == 4
    )
    _assert_no_authority(db)


def test_layout_commit_ambiguity_stops_before_page_or_runner_replay(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    original_initialize = executor_module.initialize_technical_extraction_pages

    def initialize_then_lose_ack(*args, **kwargs):  # type: ignore[no-untyped-def]
        original_initialize(*args, **kwargs)
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )

    monkeypatch.setattr(
        executor_module,
        "initialize_technical_extraction_pages",
        initialize_then_lose_ack,
    )

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "commit_outcome_unknown"
    assert len(runner.layout_requests) == 1
    assert runner.page_requests == []
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "processing"
    assert run.page_count == 2
    assert db.scalar(select(func.count()).select_from(TechnicalExtractionPage)) == 2
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_page_claim_commit_ambiguity_stops_before_runner_or_abort(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    original_claim = executor_module.claim_technical_extraction_page

    def claim_then_lose_ack(*args, **kwargs):  # type: ignore[no-untyped-def]
        original_claim(*args, **kwargs)
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )

    def abort_must_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("page-claim ambiguity attempted an abort")

    monkeypatch.setattr(
        executor_module,
        "claim_technical_extraction_page",
        claim_then_lose_ack,
    )
    monkeypatch.setattr(
        executor_module,
        "abort_technical_extraction_run",
        abort_must_not_run,
    )

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "commit_outcome_unknown"
    assert len(runner.layout_requests) == 1
    assert runner.page_requests == []
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "processing"
    first_page = db.scalar(
        select(TechnicalExtractionPage).where(
            TechnicalExtractionPage.run_id == run_id,
            TechnicalExtractionPage.page_number == 1,
        )
    )
    assert first_page is not None
    assert first_page.status == "processing"
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_page_failure_commit_ambiguity_stops_before_retry_or_abort(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes, page_behaviors={1: ["timeout", "success"]})
    original_fail = executor_module.fail_technical_extraction_page

    def fail_then_lose_ack(*args, **kwargs):  # type: ignore[no-untyped-def]
        original_fail(*args, **kwargs)
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )

    def abort_must_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("page-failure ambiguity attempted an abort")

    monkeypatch.setattr(
        executor_module,
        "fail_technical_extraction_page",
        fail_then_lose_ack,
    )
    monkeypatch.setattr(
        executor_module,
        "abort_technical_extraction_run",
        abort_must_not_run,
    )

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "commit_outcome_unknown"
    assert [request.page_number for request in runner.page_requests] == [1]
    page = db.scalar(
        select(TechnicalExtractionPage).where(
            TechnicalExtractionPage.run_id == run_id,
            TechnicalExtractionPage.page_number == 1,
        )
    )
    assert page is not None
    assert page.status == "failed"
    assert page.outcome_retryable is True
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 0


def test_aggregate_commit_ambiguity_never_attempts_abort(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_id, _stored_id, source_bytes, settings = _seed(db, tmp_path)
    runner = FakeParserRunner(source_bytes)
    original_aggregate = executor_module.aggregate_technical_extraction_run

    def aggregate_then_lose_ack(*args, **kwargs):  # type: ignore[no-untyped-def]
        original_aggregate(*args, **kwargs)
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )

    def abort_must_not_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("aggregate ambiguity attempted an abort")

    monkeypatch.setattr(
        executor_module,
        "aggregate_technical_extraction_run",
        aggregate_then_lose_ack,
    )
    monkeypatch.setattr(
        executor_module,
        "abort_technical_extraction_run",
        abort_must_not_run,
    )

    result = _execute(db, settings=settings, runner=runner)

    assert result.state == "commit_outcome_unknown"
    run = db.get(TechnicalExtractionRun, run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.manifest_sha256 is not None
    assert db.scalar(select(func.count()).select_from(TechnicalDerivedArtifact)) == 4
