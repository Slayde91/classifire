"""Default-off host coordination for isolated technical-document extraction.

The injected runner is an untrusted byte producer. This module supplies exact
source bytes and path-free requests, validates every returned byte, and may
attach only validator-approved Draft evidence. It grants no technical authority.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, Never, Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import (
    StoredFile,
    TechnicalExtractionPage,
    TechnicalExtractionRun,
    TechnicalParserInvocation,
    TechnicalParserInvocationReceipt,
)
from .storage import (
    StoredFileBindingError,
    VerifiedStoredFileStream,
    open_verified_stored_file,
)
from .technical_extraction import (
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
    count_unsettled_technical_parser_invocations,
    fail_technical_extraction_page,
    fail_technical_extraction_run,
    get_claimed_technical_extraction_source_snapshot,
    initialize_technical_extraction_pages,
    record_technical_parser_invocation_receipt,
    release_technical_extraction_run_for_retry,
    reserve_technical_parser_invocation,
)
from .technical_extraction_artifacts import (
    TechnicalExtractionArtifactError,
    cleanup_retained_technical_page_artifacts,
    retain_validated_technical_page_artifacts,
)
from .technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES,
    TechnicalPageEvidenceError,
)
from .technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
    TechnicalParserExecutionError,
    TechnicalParserExecutionReceipt,
    TechnicalParserExecutionSuccess,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
)
from .technical_parser_protocol import (
    TECHNICAL_PARSER_EVIDENCE_MAX_BYTES,
    TECHNICAL_PARSER_HEADER_MAX_BYTES,
    TECHNICAL_PARSER_PNG_MAX_BYTES,
    TechnicalParserDocumentLayout,
    TechnicalParserLayoutErrorResult,
    TechnicalParserPageErrorFrame,
    TechnicalParserPageSuccessFrame,
    TechnicalParserProtocolError,
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
    parse_technical_parser_layout_result,
    parse_technical_parser_page_frame,
)

_MAX_PAGE_RESULT_BYTES = (
    4
    + TECHNICAL_PARSER_HEADER_MAX_BYTES
    + TECHNICAL_PARSER_EVIDENCE_MAX_BYTES
    + TECHNICAL_PARSER_PNG_MAX_BYTES
)
_MAX_PAGE_ATTEMPTS_PER_EXECUTION = 3

_EXECUTION_FAILURE_POLICY: dict[str, tuple[str, bool]] = {
    "PARSER_EXECUTION_CONTAINMENT_LOST": (
        "EXTRACTION_PARSER_CONTAINMENT_LOST",
        False,
    ),
    "PARSER_EXECUTION_TIMEOUT": ("EXTRACTION_PARSER_TIMEOUT", True),
    "PARSER_EXECUTION_UNAVAILABLE": ("EXTRACTION_PARSER_UNAVAILABLE", True),
    "PARSER_EXECUTION_OUTPUT_OVERFLOW": ("EXTRACTION_PARSER_OUTPUT_INVALID", False),
    "PARSER_EXECUTION_FAILED": ("EXTRACTION_PARSER_FAILED", False),
    TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN: (
        "EXTRACTION_PARSER_EXECUTION_UNKNOWN",
        False,
    ),
    "PARSER_EXECUTION_SOURCE_INVALID": ("EXTRACTION_SOURCE_INVALID", False),
}
_REPORTED_FAILURE_POLICY: dict[str, tuple[str, bool]] = {
    "PARSER_LAYOUT_TIMEOUT": ("EXTRACTION_PARSER_TIMEOUT", True),
    "PARSER_PAGE_TIMEOUT": ("EXTRACTION_PARSER_TIMEOUT", True),
    "PARSER_TRANSIENT_FAILURE": ("EXTRACTION_PARSER_TRANSIENT_FAILURE", True),
    "PARSER_OCR_TEMPORARY_FAILURE": ("EXTRACTION_PARSER_TRANSIENT_FAILURE", True),
    "PARSER_SOURCE_ENCRYPTED": ("EXTRACTION_SOURCE_ENCRYPTED", False),
    "PARSER_SOURCE_INVALID": ("EXTRACTION_PARSER_SOURCE_INVALID", False),
    "PARSER_SOURCE_UNSUPPORTED": ("EXTRACTION_PARSER_SOURCE_UNSUPPORTED", False),
    "PARSER_PAGE_UNSUPPORTED": ("EXTRACTION_PARSER_PAGE_UNSUPPORTED", False),
    "PARSER_PAGE_FAILED": ("EXTRACTION_PARSER_PAGE_FAILED", False),
}
_SOURCE_FAILURE_CODES = frozenset(
    {
        "EXTRACTION_SOURCE_BINDING_FAILED",
        "EXTRACTION_SOURCE_NOT_ELIGIBLE",
        "EXTRACTION_SOURCE_NOT_FOUND",
        "EXTRACTION_SOURCE_TYPE_UNSUPPORTED",
    }
)


class TechnicalParserRunner(Protocol):
    """A runner that consumes one verified source descriptor per invocation."""

    @property
    def worker_image_digest(self) -> str: ...

    @property
    def runtime_profile_sha256(self) -> str: ...

    def probe(
        self,
        *,
        extraction_policy: str,
        extraction_policy_sha256: str,
    ) -> TechnicalParserRuntimeAttestation: ...

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
    ) -> TechnicalParserExecutionSuccess: ...

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
    ) -> TechnicalParserExecutionSuccess: ...


class TechnicalExtractionPolicyResolver(Protocol):
    def __call__(self, policy: str, policy_sha256: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class TechnicalExtractionExecutionResult:
    state: Literal[
        "disabled",
        "idle",
        "queued_for_retry",
        "completed",
        "completed_with_attention",
        "failed",
        "reconciliation_required",
        "commit_outcome_unknown",
    ]
    run_id: str | None = None
    outcome_code: str | None = None
    manifest_sha256: str | None = None


@dataclass(slots=True)
class _InvocationAdmission:
    reservation: TechnicalParserInvocationReservation | None = None
    finalized_receipt_sha256: str | None = None


def _fail(code: str) -> Never:
    raise TechnicalParserExecutionError(code)


def _policy_bytes(
    resolver: TechnicalExtractionPolicyResolver,
    claim: TechnicalExtractionRunClaim,
) -> bytes:
    try:
        raw = resolver(claim.extraction_policy, claim.extraction_policy_sha256)
    except TechnicalParserExecutionError:
        raise
    except Exception:
        _fail("PARSER_EXECUTION_UNAVAILABLE")
    if (
        not isinstance(raw, bytes)
        or not raw
        or len(raw) > TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES
        or hashlib.sha256(raw).hexdigest() != claim.extraction_policy_sha256
    ):
        _fail("PARSER_EXECUTION_FAILED")
    return raw


def _source_stream(
    snapshot: TechnicalExtractionSourceSnapshot,
    *,
    storage_root: Path,
) -> VerifiedStoredFileStream:
    # The immutable snapshot deliberately has the exact StoredFile read fields.
    # It is detached from SQLAlchemy so file I/O never holds a database transaction.
    return open_verified_stored_file(
        cast(StoredFile, snapshot),
        storage_root=storage_root,
        required_purpose="technical_evidence",
    )


def _invoke_runner(
    runner: TechnicalParserRunner,
    *,
    method: Literal["layout", "page"],
    request: bytes,
    snapshot: TechnicalExtractionSourceSnapshot,
    storage_root: Path,
    invocation_id: str,
    attestation: TechnicalParserRuntimeAttestation,
    prepare: Callable[[], None],
    authorize: Callable[[], None],
    finalize: Callable[[TechnicalParserExecutionReceipt], None],
) -> TechnicalParserExecutionSuccess:
    runner_called = False
    try:
        with _source_stream(snapshot, storage_root=storage_root) as verified:
            reader = verified.claim_binary_reader()
            with reader:
                runner_called = True
                if method == "layout":
                    result = runner.inspect_layout(
                        request,
                        source=reader,
                        invocation_id=invocation_id,
                        expected_attestation_sha256=attestation.sha256,
                        prepare=prepare,
                        authorize=authorize,
                        finalize=finalize,
                    )
                else:
                    result = runner.extract_page(
                        request,
                        source=reader,
                        invocation_id=invocation_id,
                        expected_attestation_sha256=attestation.sha256,
                        prepare=prepare,
                        authorize=authorize,
                        finalize=finalize,
                    )
    except TechnicalExtractionError:
        raise
    except TechnicalParserExecutionError:
        raise
    except TimeoutError:
        code = "PARSER_EXECUTION_TIMEOUT"
        if runner_called:
            _fail(code)
        raise TechnicalParserExecutionError(
            code,
            receipt=create_technical_parser_execution_receipt(
                execution_state="not_started",
                operation=method,
                invocation_id=invocation_id,
                expected_attestation_sha256=attestation.sha256,
                attestation=attestation,
                outcome_code=code,
                container_id=None,
                started_at=None,
                completed_at=datetime.now(UTC),
                exit_code=None,
                stdout_sha256=None,
                stdout_size_bytes=None,
                cleanup_confirmed=True,
            ),
        ) from None
    except StoredFileBindingError:
        code = "PARSER_EXECUTION_SOURCE_INVALID"
        raise TechnicalParserExecutionError(
            code,
            receipt=create_technical_parser_execution_receipt(
                execution_state="not_started",
                operation=method,
                invocation_id=invocation_id,
                expected_attestation_sha256=attestation.sha256,
                attestation=attestation,
                outcome_code=code,
                container_id=None,
                started_at=None,
                completed_at=datetime.now(UTC),
                exit_code=None,
                stdout_sha256=None,
                stdout_size_bytes=None,
                cleanup_confirmed=True,
            ),
        ) from None
    except OSError:
        code = "PARSER_EXECUTION_UNAVAILABLE"
        if runner_called:
            _fail(code)
        raise TechnicalParserExecutionError(
            code,
            receipt=create_technical_parser_execution_receipt(
                execution_state="not_started",
                operation=method,
                invocation_id=invocation_id,
                expected_attestation_sha256=attestation.sha256,
                attestation=attestation,
                outcome_code=code,
                container_id=None,
                started_at=None,
                completed_at=datetime.now(UTC),
                exit_code=None,
                stdout_sha256=None,
                stdout_size_bytes=None,
                cleanup_confirmed=True,
            ),
        ) from None
    except Exception:
        _fail("PARSER_EXECUTION_FAILED")
    if not isinstance(result, TechnicalParserExecutionSuccess):
        _fail("PARSER_EXECUTION_FAILED")
    return result


def _authorize_reserved_invocation(
    db: Session,
    *,
    reservation: TechnicalParserInvocationReservation,
) -> None:
    """Recheck the exact live reservation immediately before runtime creation."""

    invocation = db.get(
        TechnicalParserInvocation,
        reservation.invocation_id,
        populate_existing=True,
    )
    receipt = db.get(
        TechnicalParserInvocationReceipt,
        reservation.invocation_id,
        populate_existing=True,
    )
    run = db.get(
        TechnicalExtractionRun,
        reservation.run_claim.run_id,
        populate_existing=True,
    )
    page = (
        None
        if invocation is None or invocation.page_id is None
        else db.get(
            TechnicalExtractionPage,
            invocation.page_id,
            populate_existing=True,
        )
    )
    valid = (
        invocation is not None
        and receipt is None
        and run is not None
        and invocation.run_id == reservation.run_claim.run_id
        and invocation.operation == reservation.operation
        and invocation.page_number == reservation.page_number
        and invocation.request_sha256 == reservation.request_sha256
        and invocation.request_size_bytes == reservation.request_size_bytes
        and invocation.runtime_attestation_sha256
        == reservation.runtime_attestation_sha256
        and invocation.run_attempt_token == reservation.run_claim.attempt_token
        and invocation.run_attempt_count == reservation.run_claim.attempt_count
        and invocation.attempt_token == reservation.attempt_token
        and invocation.attempt_count == reservation.attempt_count
        and invocation.immutable is True
        and invocation.record_version == 1
        and run.status == "processing"
        and run.attempt_token == reservation.run_claim.attempt_token
        and run.attempt_count == reservation.run_claim.attempt_count
        and run.record_version == reservation.run_claim.record_version
        and run.runtime_attestation_sha256
        == reservation.runtime_attestation_sha256
        and (
            (
                reservation.operation == "layout"
                and reservation.page_number == 0
                and invocation.page_id is None
                and invocation.page_attempt_token is None
                and invocation.page_attempt_count is None
                and page is None
                and run.page_count is None
                and run.layout_invocation_id is None
            )
            or (
                reservation.operation == "page"
                and reservation.page_number > 0
                and invocation.page_id is not None
                and invocation.page_attempt_token == reservation.attempt_token
                and invocation.page_attempt_count == reservation.attempt_count
                and page is not None
                and page.run_id == reservation.run_claim.run_id
                and page.page_number == reservation.page_number
                and page.status == "processing"
                and page.attempt_token == reservation.attempt_token
                and page.attempt_count == reservation.attempt_count
                and page.parser_invocation_id is None
                and run.page_count is not None
            )
        )
    )
    if valid:
        valid = count_unsettled_technical_parser_invocations(db) == 1
    else:
        db.rollback()
    if not valid:
        raise TechnicalExtractionError("EXTRACTION_INVOCATION_RECEIPT_INVALID")


def _invoke_and_record(
    db: Session,
    *,
    runner: TechnicalParserRunner,
    method: Literal["layout", "page"],
    request: bytes,
    snapshot: TechnicalExtractionSourceSnapshot,
    storage_root: Path,
    claim: TechnicalExtractionRunClaim,
    page_claim: TechnicalExtractionPageClaim | None,
    invocation_id: str,
    admission: _InvocationAdmission,
    attestation: TechnicalParserRuntimeAttestation,
) -> bytes:
    """Reserve and persist one invocation entirely inside the runner fence."""

    if (
        not isinstance(request, bytes)
        or not request
        or not isinstance(invocation_id, str)
        or admission.reservation is not None
        or admission.finalized_receipt_sha256 is not None
        or claim.runtime_attestation_sha256 not in {None, attestation.sha256}
        or snapshot.technical_document_id
        != claim.technical_document_id
        or snapshot.source_stored_file_id
        != claim.source_stored_file_id
        or snapshot.sha256 != claim.source_sha256
        or snapshot.size_bytes != claim.source_size_bytes
        or not (
            (method == "layout" and page_claim is None)
            or (
                method == "page"
                and page_claim is not None
                and page_claim.run_claim == claim
            )
        )
    ):
        raise TechnicalExtractionError("EXTRACTION_INVOCATION_RECEIPT_INVALID")

    def prepare() -> None:
        if admission.reservation is not None:
            raise TechnicalExtractionError("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        if count_unsettled_technical_parser_invocations(db) != 0:
            raise TechnicalExtractionError("EXTRACTION_INVOCATION_PENDING")
        admission.reservation = reserve_technical_parser_invocation(
            db,
            claim=claim,
            page_claim=page_claim,
            operation=method,
            request=request,
            runtime_attestation=attestation,
            invocation_id=invocation_id,
        )

    def authorize() -> None:
        reservation = admission.reservation
        if reservation is None:
            raise TechnicalExtractionError("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        _authorize_reserved_invocation(db, reservation=reservation)

    def finalize(receipt: TechnicalParserExecutionReceipt) -> None:
        reservation = admission.reservation
        if (
            reservation is None
            or admission.finalized_receipt_sha256 is not None
        ):
            raise TechnicalExtractionError("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        record_technical_parser_invocation_receipt(
            db,
            reservation=reservation,
            receipt=receipt,
        )
        admission.finalized_receipt_sha256 = receipt.sha256

    try:
        success = _invoke_runner(
            runner,
            method=method,
            request=request,
            snapshot=snapshot,
            storage_root=storage_root,
            invocation_id=invocation_id,
            attestation=attestation,
            prepare=prepare,
            authorize=authorize,
            finalize=finalize,
        )
    except TechnicalParserExecutionError as error:
        if admission.reservation is None:
            raise
        if (
            error.receipt is None
            or admission.finalized_receipt_sha256 != error.receipt.sha256
        ):
            raise TechnicalExtractionError(
                "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
                database_outcome="commit_outcome_unknown",
            ) from error
        raise
    if (
        admission.reservation is None
        or admission.finalized_receipt_sha256 != success.receipt.sha256
    ):
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )
    return success.output


def _probe_runtime(
    runner: TechnicalParserRunner,
    claim: TechnicalExtractionRunClaim,
) -> TechnicalParserRuntimeAttestation:
    if (
        claim.run_schema != "technical-extraction-run-v2"
        or claim.runtime_profile_sha256 is None
    ):
        raise TechnicalExtractionError("EXTRACTION_RUNTIME_PROVENANCE_REQUIRED")
    try:
        runner_profile = getattr(runner, "runtime_profile_sha256", None)
        if runner_profile != claim.runtime_profile_sha256:
            raise TechnicalExtractionError("EXTRACTION_RUNTIME_ATTESTATION_MISMATCH")
        attestation = runner.probe(
            extraction_policy=claim.extraction_policy,
            extraction_policy_sha256=claim.extraction_policy_sha256,
        )
    except (TechnicalExtractionError, TechnicalParserExecutionError):
        raise
    except (AttributeError, TypeError, ValueError):
        _fail("PARSER_EXECUTION_FAILED")
    except OSError:
        _fail("PARSER_EXECUTION_UNAVAILABLE")
    except Exception:
        _fail("PARSER_EXECUTION_FAILED")
    if not isinstance(attestation, TechnicalParserRuntimeAttestation):
        _fail("PARSER_EXECUTION_FAILED")
    return attestation


def _reported_failure(error_code: str) -> tuple[str, bool]:
    return _REPORTED_FAILURE_POLICY.get(
        error_code,
        ("EXTRACTION_PARSER_OUTPUT_INVALID", False),
    )


def _execution_failure(error: TechnicalParserExecutionError) -> tuple[str, bool]:
    return _EXECUTION_FAILURE_POLICY[error.code]


def _resolve_before_layout(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    outcome_code: str,
    retryable: bool,
) -> TechnicalExtractionExecutionResult:
    try:
        if retryable:
            release_technical_extraction_run_for_retry(
                db,
                claim=claim,
                outcome_code=outcome_code,
            )
            state: Literal["queued_for_retry", "failed"] = "queued_for_retry"
        else:
            fail_technical_extraction_run(
                db,
                claim=claim,
                outcome_code=outcome_code,
            )
            state = "failed"
    except TechnicalExtractionError as error:
        if error.database_outcome == "commit_outcome_unknown":
            return TechnicalExtractionExecutionResult(
                state="commit_outcome_unknown",
                run_id=claim.run_id,
                outcome_code=error.code,
            )
        raise
    return TechnicalExtractionExecutionResult(
        state=state,
        run_id=claim.run_id,
        outcome_code=outcome_code,
    )


def _abort_initialized(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    outcome_code: str,
) -> TechnicalExtractionExecutionResult:
    try:
        abort_technical_extraction_run(
            db,
            claim=claim,
            outcome_code=outcome_code,
        )
    except TechnicalExtractionError as error:
        if error.database_outcome == "commit_outcome_unknown":
            return TechnicalExtractionExecutionResult(
                state="commit_outcome_unknown",
                run_id=claim.run_id,
                outcome_code=error.code,
            )
        raise
    return TechnicalExtractionExecutionResult(
        state="failed",
        run_id=claim.run_id,
        outcome_code=outcome_code,
    )


def _layout_binding(layout: TechnicalParserDocumentLayout) -> TechnicalExtractionLayoutBinding:
    return TechnicalExtractionLayoutBinding(
        schema=layout.schema,
        sha256=layout.layout_sha256,
        size_bytes=layout.layout_size_bytes,
        page_count=layout.page_count,
        pages=tuple(
            TechnicalExtractionPageLayoutBinding(
                page_number=page.number,
                page_count=page.count,
                width_points=page.width_points,
                height_points=page.height_points,
            )
            for page in layout.pages
        ),
    )


def _page_status(
    db: Session,
    *,
    run_id: str,
    page_number: int,
) -> tuple[str, bool | None]:
    row = db.execute(
        select(
            TechnicalExtractionPage.status,
            TechnicalExtractionPage.outcome_retryable,
        ).where(
            TechnicalExtractionPage.run_id == run_id,
            TechnicalExtractionPage.page_number == page_number,
        )
    ).one_or_none()
    db.rollback()
    if row is None:
        raise TechnicalExtractionError("EXTRACTION_PAGE_NOT_FOUND")
    return row[0], row[1]


def _artifact_id(run_id: str, page_number: int, artifact_kind: str) -> str:
    seed = f"technical-extraction-artifact-v1:{run_id}:{page_number}:{artifact_kind}"
    digest = hashlib.sha256(seed.encode("ascii")).digest()
    return str(UUID(bytes=digest[:16], version=4))


def _complete_retained_page(
    db: Session,
    *,
    claim,
    retained,
    storage_root: Path,
    policy_bytes: bytes,
    source_snapshot: TechnicalExtractionSourceSnapshot,
    parser_invocation_id: str,
    parser_output: bytes,
):
    try:
        return complete_technical_extraction_page(
            db,
            claim=claim,
            retained=retained,
            storage_root=storage_root,
            extraction_policy_bytes=policy_bytes,
            source_snapshot=source_snapshot,
            parser_invocation_id=parser_invocation_id,
            parser_output=parser_output,
        )
    except TechnicalExtractionError as first:
        if first.database_outcome != "commit_outcome_unknown":
            raise
        # Do not heartbeat, reclaim, regenerate output, or change IDs here.
        # Reconciliation must use the exact old claim and retained bindings.
        return complete_technical_extraction_page(
            db,
            claim=claim,
            retained=retained,
            storage_root=storage_root,
            extraction_policy_bytes=policy_bytes,
            source_snapshot=source_snapshot,
            parser_invocation_id=parser_invocation_id,
            parser_output=parser_output,
        )


def execute_next_technical_extraction(
    db: Session,
    *,
    settings: Settings,
    runner: TechnicalParserRunner,
    policy_resolver: TechnicalExtractionPolicyResolver,
    max_page_attempts: int = _MAX_PAGE_ATTEMPTS_PER_EXECUTION,
) -> TechnicalExtractionExecutionResult:
    """Process at most one queued/stale run through Draft manifest completion."""

    if not settings.technical_extraction_executor_runtime_allowed:
        return TechnicalExtractionExecutionResult(state="disabled")
    if (
        not isinstance(max_page_attempts, int)
        or isinstance(max_page_attempts, bool)
        or not 1 <= max_page_attempts <= _MAX_PAGE_ATTEMPTS_PER_EXECUTION
    ):
        _fail("PARSER_EXECUTION_FAILED")

    try:
        run_claim = claim_next_technical_extraction_run(db)
    except TechnicalExtractionError as error:
        if error.database_outcome == "commit_outcome_unknown":
            return TechnicalExtractionExecutionResult(
                state="commit_outcome_unknown",
                outcome_code=error.code,
            )
        raise
    if run_claim is None:
        return TechnicalExtractionExecutionResult(state="idle")

    initialized = run_claim.page_count is not None
    if not initialized and run_claim.attempt_count > max_page_attempts:
        return _resolve_before_layout(
            db,
            claim=run_claim,
            outcome_code="EXTRACTION_RUN_RETRY_EXHAUSTED",
            retryable=False,
        )
    try:
        runner_digest = getattr(runner, "worker_image_digest", None)
    except Exception:
        runner_digest = None
    if runner_digest != run_claim.worker_image_digest:
        if initialized:
            return _abort_initialized(
                db,
                claim=run_claim,
                outcome_code="EXTRACTION_WORKER_BINDING_FAILED",
            )
        return _resolve_before_layout(
            db,
            claim=run_claim,
            outcome_code="EXTRACTION_WORKER_BINDING_FAILED",
            retryable=False,
        )
    try:
        runner_profile = getattr(runner, "runtime_profile_sha256", None)
    except Exception:
        runner_profile = None
    if (
        run_claim.run_schema != "technical-extraction-run-v2"
        or run_claim.runtime_profile_sha256 is None
        or runner_profile != run_claim.runtime_profile_sha256
    ):
        outcome = (
            "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED"
            if run_claim.run_schema != "technical-extraction-run-v2"
            or run_claim.runtime_profile_sha256 is None
            else "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH"
        )
        if initialized:
            return _abort_initialized(db, claim=run_claim, outcome_code=outcome)
        return _resolve_before_layout(
            db,
            claim=run_claim,
            outcome_code=outcome,
            retryable=False,
        )

    try:
        policy_bytes = _policy_bytes(policy_resolver, run_claim)
    except TechnicalParserExecutionError as error:
        outcome_code, retryable = _execution_failure(error)
        if initialized:
            return _abort_initialized(
                db,
                claim=run_claim,
                outcome_code=outcome_code,
            )
        return _resolve_before_layout(
            db,
            claim=run_claim,
            outcome_code=outcome_code,
            retryable=retryable,
        )

    try:
        source_snapshot = get_claimed_technical_extraction_source_snapshot(
            db,
            claim=run_claim,
        )
    except TechnicalExtractionError:
        if initialized:
            return _abort_initialized(
                db,
                claim=run_claim,
                outcome_code="EXTRACTION_SOURCE_INVALID",
            )
        return _resolve_before_layout(
            db,
            claim=run_claim,
            outcome_code="EXTRACTION_SOURCE_INVALID",
            retryable=False,
        )

    if not initialized:
        layout_request = encode_technical_parser_layout_request(
            technical_document_id=run_claim.technical_document_id,
            source_sha256=run_claim.source_sha256,
            source_size_bytes=run_claim.source_size_bytes,
            extraction_policy=run_claim.extraction_policy,
            extraction_policy_sha256=run_claim.extraction_policy_sha256,
            worker_image_digest=run_claim.worker_image_digest,
            ocr_low_confidence_threshold=run_claim.ocr_low_confidence_threshold,
        )
        layout_invocation_id = str(uuid4())
        layout_admission = _InvocationAdmission()
        try:
            confirm_technical_extraction_source_snapshot(
                db,
                claim=run_claim,
                snapshot=source_snapshot,
            )
            attestation = _probe_runtime(runner, run_claim)
            raw_layout = _invoke_and_record(
                db,
                runner=runner,
                method="layout",
                request=layout_request,
                snapshot=source_snapshot,
                storage_root=settings.storage_root,
                claim=run_claim,
                page_claim=None,
                invocation_id=layout_invocation_id,
                admission=layout_admission,
                attestation=attestation,
            )
            reservation = layout_admission.reservation
            if reservation is None:  # pragma: no cover - callback contract invariant
                raise TechnicalExtractionError(
                    "EXTRACTION_INVOCATION_RECEIPT_INVALID"
                )
            run_claim = reservation.run_claim
            confirm_technical_extraction_source_snapshot(
                db,
                claim=run_claim,
                snapshot=source_snapshot,
            )
            layout_result = parse_technical_parser_layout_result(
                raw_layout,
                expected_technical_document_id=run_claim.technical_document_id,
                expected_source_sha256=run_claim.source_sha256,
                expected_source_size_bytes=run_claim.source_size_bytes,
                expected_extraction_policy=run_claim.extraction_policy,
                expected_extraction_policy_sha256=run_claim.extraction_policy_sha256,
                expected_worker_image_digest=run_claim.worker_image_digest,
            )
        except TechnicalParserExecutionError as error:
            if layout_admission.reservation is not None:
                run_claim = layout_admission.reservation.run_claim
            outcome_code, retryable = _execution_failure(error)
            if error.receipt is not None and error.receipt.cleanup_confirmed is not True:
                return TechnicalExtractionExecutionResult(
                    state="reconciliation_required",
                    run_id=run_claim.run_id,
                    outcome_code=outcome_code,
                )
            return _resolve_before_layout(
                db,
                claim=run_claim,
                outcome_code=outcome_code,
                retryable=(retryable and run_claim.attempt_count < max_page_attempts),
            )
        except TechnicalExtractionError as error:
            if layout_admission.reservation is not None:
                run_claim = layout_admission.reservation.run_claim
            if error.code == "EXTRACTION_INVOCATION_PENDING":
                return TechnicalExtractionExecutionResult(
                    state="reconciliation_required",
                    run_id=run_claim.run_id,
                    outcome_code=error.code,
                )
            if error.database_outcome == "commit_outcome_unknown":
                return TechnicalExtractionExecutionResult(
                    state="commit_outcome_unknown",
                    run_id=run_claim.run_id,
                    outcome_code=error.code,
                )
            return _resolve_before_layout(
                db,
                claim=run_claim,
                outcome_code=(
                    "EXTRACTION_SOURCE_INVALID"
                    if error.code in _SOURCE_FAILURE_CODES
                    else (
                        error.code
                        if error.code
                        in {
                            "EXTRACTION_RUNTIME_ATTESTATION_INVALID",
                            "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH",
                            "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED",
                        }
                        else "EXTRACTION_LAYOUT_PROTOCOL_INVALID"
                    )
                ),
                retryable=False,
            )
        except TechnicalParserProtocolError:
            return _resolve_before_layout(
                db,
                claim=run_claim,
                outcome_code="EXTRACTION_LAYOUT_PROTOCOL_INVALID",
                retryable=False,
            )
        if isinstance(layout_result, TechnicalParserLayoutErrorResult):
            outcome_code, retryable = _reported_failure(layout_result.error_code)
            return _resolve_before_layout(
                db,
                claim=run_claim,
                outcome_code=outcome_code,
                retryable=(retryable and run_claim.attempt_count < max_page_attempts),
            )
        try:
            initialized_pages = initialize_technical_extraction_pages(
                db,
                claim=run_claim,
                layout=_layout_binding(layout_result),
                parser_invocation_id=layout_invocation_id,
            )
        except TechnicalExtractionError as error:
            if error.database_outcome == "commit_outcome_unknown":
                return TechnicalExtractionExecutionResult(
                    state="commit_outcome_unknown",
                    run_id=run_claim.run_id,
                    outcome_code=error.code,
                )
            raise
        run_claim = initialized_pages.run_claim

    if run_claim.page_count is None:  # pragma: no cover - lifecycle invariant
        _fail("PARSER_EXECUTION_FAILED")
    for page_number in range(1, run_claim.page_count + 1):
        while True:
            status, outcome_retryable = _page_status(
                db,
                run_id=run_claim.run_id,
                page_number=page_number,
            )
            if status in {"completed", "needs_attention"}:
                break
            if status == "cancelled" or (status == "failed" and outcome_retryable is False):
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_PAGE_FAILED",
                )

            try:
                page_claim = claim_technical_extraction_page(
                    db,
                    run_claim=run_claim,
                    page_number=page_number,
                )
            except TechnicalExtractionError as error:
                if error.database_outcome == "commit_outcome_unknown":
                    return TechnicalExtractionExecutionResult(
                        state="commit_outcome_unknown",
                        run_id=run_claim.run_id,
                        outcome_code=error.code,
                    )
                raise
            run_claim = page_claim.run_claim
            if page_claim.attempt_count > max_page_attempts:
                try:
                    run_claim = fail_technical_extraction_page(
                        db,
                        claim=page_claim,
                        outcome_code="EXTRACTION_PAGE_RETRY_EXHAUSTED",
                        retryable=False,
                    )
                except TechnicalExtractionError as error:
                    if error.database_outcome == "commit_outcome_unknown":
                        return TechnicalExtractionExecutionResult(
                            state="commit_outcome_unknown",
                            run_id=run_claim.run_id,
                            outcome_code=error.code,
                        )
                    raise
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_PAGE_RETRY_EXHAUSTED",
                )
            page_request = encode_technical_parser_request(
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
            page_invocation_id = str(uuid4())
            page_admission = _InvocationAdmission()
            try:
                confirm_technical_extraction_source_snapshot(
                    db,
                    claim=run_claim,
                    snapshot=source_snapshot,
                )
                attestation = _probe_runtime(runner, run_claim)
                raw_frame = _invoke_and_record(
                    db,
                    runner=runner,
                    method="page",
                    request=page_request,
                    snapshot=source_snapshot,
                    storage_root=settings.storage_root,
                    claim=run_claim,
                    page_claim=page_claim,
                    invocation_id=page_invocation_id,
                    admission=page_admission,
                    attestation=attestation,
                )
                reservation = page_admission.reservation
                if reservation is None:  # pragma: no cover - callback contract invariant
                    raise TechnicalExtractionError(
                        "EXTRACTION_INVOCATION_RECEIPT_INVALID"
                    )
                run_claim = reservation.run_claim
                page_claim = replace(page_claim, run_claim=run_claim)
                confirm_technical_extraction_source_snapshot(
                    db,
                    claim=run_claim,
                    snapshot=source_snapshot,
                )
                if len(raw_frame) > _MAX_PAGE_RESULT_BYTES:
                    _fail("PARSER_EXECUTION_OUTPUT_OVERFLOW")
                frame = parse_technical_parser_page_frame(
                    raw_frame,
                    expected_page_number=page_claim.page_number,
                    expected_page_count=page_claim.page_count,
                    expected_page_width_points=page_claim.layout_page_width_points,
                    expected_page_height_points=page_claim.layout_page_height_points,
                )
            except TechnicalParserExecutionError as error:
                if page_admission.reservation is not None:
                    run_claim = page_admission.reservation.run_claim
                    page_claim = replace(page_claim, run_claim=run_claim)
                outcome_code, retryable = _execution_failure(error)
                if (
                    error.receipt is not None
                    and error.receipt.cleanup_confirmed is not True
                ):
                    return TechnicalExtractionExecutionResult(
                        state="reconciliation_required",
                        run_id=run_claim.run_id,
                        outcome_code=outcome_code,
                    )
                should_retry = retryable and page_claim.attempt_count < max_page_attempts
                try:
                    run_claim = fail_technical_extraction_page(
                        db,
                        claim=page_claim,
                        outcome_code=outcome_code,
                        retryable=should_retry,
                    )
                except TechnicalExtractionError as transition_error:
                    if transition_error.database_outcome == "commit_outcome_unknown":
                        return TechnicalExtractionExecutionResult(
                            state="commit_outcome_unknown",
                            run_id=run_claim.run_id,
                            outcome_code=transition_error.code,
                        )
                    raise
                if should_retry:
                    continue
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code=("EXTRACTION_PAGE_RETRY_EXHAUSTED" if retryable else outcome_code),
                )
            except TechnicalExtractionError as error:
                if page_admission.reservation is not None:
                    run_claim = page_admission.reservation.run_claim
                    page_claim = replace(page_claim, run_claim=run_claim)
                if error.code == "EXTRACTION_INVOCATION_PENDING":
                    return TechnicalExtractionExecutionResult(
                        state="reconciliation_required",
                        run_id=run_claim.run_id,
                        outcome_code=error.code,
                    )
                if error.database_outcome == "commit_outcome_unknown":
                    return TechnicalExtractionExecutionResult(
                        state="commit_outcome_unknown",
                        run_id=run_claim.run_id,
                        outcome_code=error.code,
                    )
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code=(
                        "EXTRACTION_SOURCE_INVALID"
                        if error.code in _SOURCE_FAILURE_CODES
                        else (
                            error.code
                            if error.code
                            in {
                                "EXTRACTION_RUNTIME_ATTESTATION_INVALID",
                                "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH",
                                "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED",
                            }
                            else "EXTRACTION_PAGE_PROTOCOL_INVALID"
                        )
                    ),
                )
            except TechnicalParserProtocolError:
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_PAGE_PROTOCOL_INVALID",
                )

            if isinstance(frame, TechnicalParserPageErrorFrame):
                outcome_code, retryable = _reported_failure(frame.error_code)
                should_retry = retryable and page_claim.attempt_count < max_page_attempts
                try:
                    run_claim = fail_technical_extraction_page(
                        db,
                        claim=page_claim,
                        outcome_code=outcome_code,
                        retryable=should_retry,
                    )
                except TechnicalExtractionError as transition_error:
                    if transition_error.database_outcome == "commit_outcome_unknown":
                        return TechnicalExtractionExecutionResult(
                            state="commit_outcome_unknown",
                            run_id=run_claim.run_id,
                            outcome_code=transition_error.code,
                        )
                    raise
                if should_retry:
                    continue
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code=("EXTRACTION_PAGE_RETRY_EXHAUSTED" if retryable else outcome_code),
                )
            if not isinstance(frame, TechnicalParserPageSuccessFrame):
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_PAGE_PROTOCOL_INVALID",
                )

            try:
                retained = retain_validated_technical_page_artifacts(
                    frame.evidence_bytes,
                    page_image_bytes=frame.image_bytes,
                    storage_root=settings.storage_root,
                    run_id=run_claim.run_id,
                    expected_technical_document_id=run_claim.technical_document_id,
                    expected_source_sha256=run_claim.source_sha256,
                    expected_source_size_bytes=run_claim.source_size_bytes,
                    expected_page_number=page_claim.page_number,
                    expected_page_count=page_claim.page_count,
                    expected_page_width_points=page_claim.layout_page_width_points,
                    expected_page_height_points=page_claim.layout_page_height_points,
                    expected_page_image_sha256=frame.image_sha256,
                    expected_page_image_size_bytes=frame.image_size_bytes,
                    expected_page_image_width_pixels=frame.image_width_pixels,
                    expected_page_image_height_pixels=frame.image_height_pixels,
                    expected_extraction_policy=run_claim.extraction_policy,
                    expected_extraction_policy_bytes=policy_bytes,
                    expected_extraction_policy_sha256=run_claim.extraction_policy_sha256,
                    expected_worker_image_digest=run_claim.worker_image_digest,
                    expected_ocr_low_confidence_threshold=(run_claim.ocr_low_confidence_threshold),
                    packet_artifact_id=_artifact_id(
                        run_claim.run_id,
                        page_claim.page_number,
                        "page_evidence_json",
                    ),
                    page_image_artifact_id=_artifact_id(
                        run_claim.run_id,
                        page_claim.page_number,
                        "page_image_png",
                    ),
                    allow_existing_artifact_replay=True,
                )
            except TechnicalExtractionArtifactError:
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_ARTIFACT_RETENTION_FAILED",
                )
            except TechnicalPageEvidenceError:
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code="EXTRACTION_PAGE_VALIDATION_FAILED",
                )

            try:
                completion = _complete_retained_page(
                    db,
                    claim=page_claim,
                    retained=retained,
                    storage_root=settings.storage_root,
                    policy_bytes=policy_bytes,
                    source_snapshot=source_snapshot,
                    parser_invocation_id=cast(str, page_invocation_id),
                    parser_output=raw_frame,
                )
            except TechnicalExtractionError as error:
                if error.database_outcome == "commit_outcome_unknown":
                    return TechnicalExtractionExecutionResult(
                        state="commit_outcome_unknown",
                        run_id=run_claim.run_id,
                        outcome_code=error.code,
                    )
                if error.database_outcome == "known_rollback":
                    try:
                        cleanup_retained_technical_page_artifacts(
                            retained,
                            storage_root=settings.storage_root,
                            database_outcome="known_rollback",
                        )
                    except TechnicalExtractionArtifactError:
                        return _abort_initialized(
                            db,
                            claim=run_claim,
                            outcome_code="EXTRACTION_ARTIFACT_CLEANUP_FAILED",
                        )
                return _abort_initialized(
                    db,
                    claim=run_claim,
                    outcome_code=error.code,
                )
            run_claim = completion.run_claim
            break

    try:
        aggregate = aggregate_technical_extraction_run(
            db,
            claim=run_claim,
            source_snapshot=source_snapshot,
            artifact_storage_root=settings.storage_root,
        )
    except TechnicalExtractionError as error:
        if error.database_outcome == "commit_outcome_unknown":
            return TechnicalExtractionExecutionResult(
                state="commit_outcome_unknown",
                run_id=run_claim.run_id,
                outcome_code=error.code,
            )
        return _abort_initialized(
            db,
            claim=run_claim,
            outcome_code=error.code,
        )
    return TechnicalExtractionExecutionResult(
        state=cast(
            Literal["completed", "completed_with_attention"],
            aggregate.status,
        ),
        run_id=aggregate.run_id,
        outcome_code=aggregate.outcome_code,
        manifest_sha256=aggregate.manifest_sha256,
    )


__all__ = [
    "TechnicalExtractionExecutionResult",
    "TechnicalExtractionPolicyResolver",
    "TechnicalParserExecutionError",
    "TechnicalParserRunner",
    "execute_next_technical_extraction",
]
