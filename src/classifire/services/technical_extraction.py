"""Durable, authority-neutral orchestration for technical-source extraction.

This module owns only database lifecycle and integrity. It never invokes a
parser, retains derived bytes, or creates technical variants or approvals.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Literal, Never
from uuid import UUID, uuid4

from sqlalchemy import and_, case, func, or_, select, true, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import (
    StoredFile,
    TechnicalDerivedArtifact,
    TechnicalDocument,
    TechnicalExtractionPage,
    TechnicalExtractionRun,
    TechnicalParserInvocation,
    TechnicalParserInvocationReceipt,
    User,
)
from ..security import has_permission
from .technical_extraction_artifacts import (
    RetainedTechnicalPageArtifacts,
    TechnicalDerivedArtifactBinding,
    TechnicalExtractionArtifactError,
    build_unflushed_technical_derived_artifact_rows,
    open_verified_technical_derived_artifact,
)
from .technical_page_evidence import (
    TECHNICAL_PAGE_EVIDENCE_MAX_PAGES,
    TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES,
    TECHNICAL_PAGE_EVIDENCE_SCHEMA,
    TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY,
    TechnicalPageEvidence,
    TechnicalPageEvidenceError,
    parse_technical_page_evidence,
)
from .technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
    TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionReceipt,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_execution_receipt,
    parse_technical_parser_execution_receipt,
    parse_technical_parser_runtime_attestation,
)
from .technical_parser_protocol import (
    TechnicalParserPageSuccessFrame,
    TechnicalParserProtocolError,
    encode_technical_parser_layout_request,
    encode_technical_parser_request,
    parse_technical_parser_page_frame,
)

TECHNICAL_EXTRACTION_RUN_SCHEMA_V1 = "technical-extraction-run-v1"
TECHNICAL_EXTRACTION_RUN_SCHEMA = "technical-extraction-run-v2"
TECHNICAL_EXTRACTION_PAGE_SCHEMA_V1 = "technical-extraction-page-v1"
TECHNICAL_EXTRACTION_PAGE_SCHEMA = "technical-extraction-page-v2"
TECHNICAL_EXTRACTION_MANIFEST_SCHEMA_V1 = "technical-extraction-manifest-v1"
TECHNICAL_EXTRACTION_MANIFEST_SCHEMA = "technical-extraction-manifest-v2"
TECHNICAL_EXTRACTION_LAYOUT_SCHEMA = "technical-parser-layout-v1"
TECHNICAL_EXTRACTION_LAYOUT_MAX_BYTES = 128 * 1024
TECHNICAL_EXTRACTION_RUN_CLAIM_TTL = timedelta(minutes=15)
TECHNICAL_EXTRACTION_PAGE_CLAIM_TTL = timedelta(minutes=15)
TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL = timedelta(minutes=15)

_TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA = (
    "technical-parser-oci-cleanup-proof-v1"
)
_OCI_CONTAINER_STATES = frozenset(
    {"created", "dead", "exited", "paused", "removing", "restarting", "running"}
)

_HEX = frozenset("0123456789abcdef")
_SAFE_POLICY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:+/-]{0,99}$")
_SAFE_OUTCOME = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")
_RUN_SUCCESS_CODES = frozenset({"EXTRACTION_COMPLETE", "EXTRACTION_COMPLETE_WITH_ATTENTION"})
_PAGE_SUCCESS_CODES = frozenset({"PAGE_EXTRACTION_COMPLETE", "PAGE_EXTRACTION_NEEDS_ATTENTION"})
_ERROR_CODES = frozenset(
    {
        "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
        "EXTRACTION_AGGREGATION_NOT_READY",
        "EXTRACTION_ARTIFACT_BINDING_MISMATCH",
        "EXTRACTION_LAYOUT_CONFLICT",
        "EXTRACTION_LAYOUT_INVALID",
        "EXTRACTION_MANIFEST_MISMATCH",
        "EXTRACTION_PAGE_CLAIM_LOST",
        "EXTRACTION_PAGE_COUNT_CONFLICT",
        "EXTRACTION_PAGE_IN_PROGRESS",
        "EXTRACTION_PAGE_NOT_FOUND",
        "EXTRACTION_PAGE_NOT_RETRYABLE",
        "EXTRACTION_POLICY_INVALID",
        "EXTRACTION_REQUEST_INVALID",
        "EXTRACTION_RUNTIME_ATTESTATION_INVALID",
        "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH",
        "EXTRACTION_RUNTIME_PROFILE_INVALID",
        "EXTRACTION_RUNTIME_PROVENANCE_REQUIRED",
        "EXTRACTION_INVOCATION_ALREADY_TERMINAL",
        "EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
        "EXTRACTION_INVOCATION_NOT_FOUND",
        "EXTRACTION_INVOCATION_PENDING",
        "EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST",
        "EXTRACTION_INVOCATION_RECEIPT_INVALID",
        "EXTRACTION_RUN_CLAIM_LOST",
        "EXTRACTION_RUN_HAS_PAGES",
        "EXTRACTION_RUN_NOT_FOUND",
        "EXTRACTION_RUN_NOT_INITIALIZED",
        "EXTRACTION_RUN_NOT_RETRYABLE",
        "EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        "EXTRACTION_SOURCE_BINDING_FAILED",
        "EXTRACTION_SOURCE_NOT_ELIGIBLE",
        "EXTRACTION_SOURCE_NOT_FOUND",
        "EXTRACTION_SOURCE_TYPE_UNSUPPORTED",
        "EXTRACTION_WORKER_DIGEST_INVALID",
    }
)


class TechnicalExtractionError(RuntimeError):
    """A stable, path-free extraction lifecycle failure."""

    def __init__(
        self,
        code: str,
        *,
        database_outcome: Literal["known_rollback", "commit_outcome_unknown"] | None = None,
    ) -> None:
        if code not in _ERROR_CODES:
            raise ValueError("Unknown technical extraction error code")
        self.code = code
        self.database_outcome = database_outcome
        self.retryable = code in {
            "EXTRACTION_AGGREGATION_NOT_READY",
            "EXTRACTION_INVOCATION_PENDING",
            "EXTRACTION_PAGE_CLAIM_LOST",
            "EXTRACTION_PAGE_IN_PROGRESS",
            "EXTRACTION_RUN_CLAIM_LOST",
        }
        self.fatal = code in {
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            "EXTRACTION_LAYOUT_CONFLICT",
            "EXTRACTION_MANIFEST_MISMATCH",
            "EXTRACTION_RUNTIME_ATTESTATION_MISMATCH",
            "EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            "EXTRACTION_SOURCE_BINDING_FAILED",
        }
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class TechnicalExtractionRequestResult:
    run_id: str
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class TechnicalExtractionRunClaim:
    run_id: str
    record_version: int
    attempt_token: str
    attempt_started_at: datetime
    attempt_count: int
    technical_document_id: str
    source_stored_file_id: str
    source_sha256: str
    source_size_bytes: int
    extraction_policy: str
    extraction_policy_sha256: str
    ocr_low_confidence_threshold: Decimal
    worker_image_digest: str
    run_schema: str
    runtime_profile_sha256: str | None
    runtime_attestation_sha256: str | None
    page_count: int | None
    layout_schema: str | None
    layout_sha256: str | None
    layout_size_bytes: int | None
    layout_invocation_id: str | None


@dataclass(frozen=True, slots=True)
class TechnicalExtractionPageLayoutBinding:
    page_number: int
    page_count: int
    width_points: Decimal
    height_points: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalExtractionLayoutBinding:
    schema: str
    sha256: str
    size_bytes: int
    page_count: int
    pages: tuple[TechnicalExtractionPageLayoutBinding, ...]


@dataclass(frozen=True, slots=True)
class TechnicalExtractionSourceSnapshot:
    technical_document_id: str
    source_stored_file_id: str
    source_record_version: int
    original_filename: str
    media_type: str | None
    storage_path: str
    sha256: str
    size_bytes: int
    purpose: str
    malware_scan_status: str
    immutable: bool


@dataclass(frozen=True, slots=True)
class TechnicalExtractionPageClaim:
    run_claim: TechnicalExtractionRunClaim
    page_id: str
    record_version: int
    page_number: int
    page_count: int
    layout_sha256: str
    layout_page_width_points: Decimal
    layout_page_height_points: Decimal
    attempt_token: str
    attempt_started_at: datetime
    attempt_count: int


@dataclass(frozen=True, slots=True)
class TechnicalParserInvocationReservation:
    invocation_id: str
    run_claim: TechnicalExtractionRunClaim
    operation: Literal["layout", "page"]
    page_number: int
    attempt_token: str
    attempt_count: int
    request_sha256: str
    request_size_bytes: int
    runtime_attestation_sha256: str
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class TechnicalParserInvocationReceiptBinding:
    invocation_id: str
    receipt_sha256: str
    execution_state: str
    stdout_sha256: str | None
    stdout_size_bytes: int | None
    cleanup_confirmed: bool
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class TechnicalParserInvocationReconciliationClaim:
    """One stale, exact invocation attempt leased for cleanup-only resolution."""

    invocation_id: str
    operation: Literal["layout", "page"]
    page_number: int
    invocation_created_at: datetime
    run_claim: TechnicalExtractionRunClaim
    page_claim: TechnicalExtractionPageClaim | None
    request_sha256: str
    request_size_bytes: int
    runtime_attestation: TechnicalParserRuntimeAttestation
    terminal_receipt: TechnicalParserExecutionReceipt | None
    lease_started_at: datetime


@dataclass(frozen=True, slots=True)
class TechnicalParserInvocationReconciliationResult:
    """Terminal database disposition for one orphaned parser invocation."""

    invocation_id: str
    run_id: str
    operation: Literal["layout", "page"]
    execution_state: str
    receipt_sha256: str
    run_outcome_code: str
    page_outcome_code: str | None
    cancelled_page_count: int
    preserved_page_count: int
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class TechnicalExtractionPageInitialization:
    run_claim: TechnicalExtractionRunClaim
    page_ids: tuple[str, ...]
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class TechnicalExtractionManifest:
    schema: str
    canonical_json: bytes
    sha256: str

    def as_dict(self) -> dict[str, object]:
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover - constructor invariant
            raise RuntimeError("Technical extraction manifest root is invalid")
        return value


@dataclass(frozen=True, slots=True)
class TechnicalExtractionAggregateResult:
    run_id: str
    status: str
    outcome_code: str
    manifest_sha256: str | None


@dataclass(frozen=True, slots=True)
class TechnicalExtractionPageCompletion:
    run_claim: TechnicalExtractionRunClaim
    page_id: str
    status: str
    outcome_code: str
    database_outcome: Literal["committed"] = "committed"
    idempotent_replay: bool = False


@dataclass(frozen=True, slots=True)
class TechnicalExtractionAbortResult:
    run_id: str
    status: Literal["failed"]
    outcome_code: str
    cancelled_page_count: int
    preserved_page_count: int


def _fail(
    code: str,
    *,
    database_outcome: Literal["known_rollback", "commit_outcome_unknown"] | None = None,
) -> Never:
    raise TechnicalExtractionError(code, database_outcome=database_outcome)


def _canonical_uuid4(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        _fail(code)
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail(code)
    if parsed.version != 4 or str(parsed) != value:
        _fail(code)
    return value


def _canonical_sha256(value: object, *, code: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in _HEX for character in value)
    ):
        _fail(code)
    return value


def _ocr_threshold(value: object, *, code: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, Decimal)):
        _fail(code)
    try:
        parsed = Decimal(value)
        exponent = parsed.as_tuple().exponent
        valid_places = isinstance(exponent, int) and exponent >= -2
    except DecimalException:
        _fail(code)
    if not parsed.is_finite() or not Decimal(0) <= parsed <= Decimal(100):
        _fail(code)
    if not valid_places:
        _fail(code)
    return parsed


def _layout_dimension(value: object, *, code: str) -> Decimal:
    if not isinstance(value, Decimal):
        _fail(code)
    try:
        exponent = value.as_tuple().exponent
        valid_places = isinstance(exponent, int) and exponent >= -4
    except DecimalException:
        _fail(code)
    if not value.is_finite() or not Decimal(0) < value <= Decimal(20000) or not valid_places:
        _fail(code)
    return value


def _page_schema_for_run(run_schema: str) -> str:
    if run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA_V1:
        return TECHNICAL_EXTRACTION_PAGE_SCHEMA_V1
    if run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA:
        return TECHNICAL_EXTRACTION_PAGE_SCHEMA
    _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def _validated_layout(
    value: object,
    *,
    code: str,
) -> TechnicalExtractionLayoutBinding:
    if not isinstance(value, TechnicalExtractionLayoutBinding):
        _fail(code)
    if value.schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA:
        _fail(code)
    sha256 = _canonical_sha256(value.sha256, code=code)
    if (
        not isinstance(value.size_bytes, int)
        or isinstance(value.size_bytes, bool)
        or not 1 <= value.size_bytes <= TECHNICAL_EXTRACTION_LAYOUT_MAX_BYTES
        or not isinstance(value.page_count, int)
        or isinstance(value.page_count, bool)
        or not 1 <= value.page_count <= TECHNICAL_PAGE_EVIDENCE_MAX_PAGES
        or not isinstance(value.pages, tuple)
        or len(value.pages) != value.page_count
    ):
        _fail(code)
    pages: list[TechnicalExtractionPageLayoutBinding] = []
    for expected_number, raw_page in enumerate(value.pages, start=1):
        if (
            not isinstance(raw_page, TechnicalExtractionPageLayoutBinding)
            or not isinstance(raw_page.page_number, int)
            or isinstance(raw_page.page_number, bool)
            or raw_page.page_number != expected_number
            or not isinstance(raw_page.page_count, int)
            or isinstance(raw_page.page_count, bool)
            or raw_page.page_count != value.page_count
        ):
            _fail(code)
        pages.append(
            TechnicalExtractionPageLayoutBinding(
                page_number=expected_number,
                page_count=value.page_count,
                width_points=_layout_dimension(raw_page.width_points, code=code),
                height_points=_layout_dimension(raw_page.height_points, code=code),
            )
        )
    return TechnicalExtractionLayoutBinding(
        schema=TECHNICAL_EXTRACTION_LAYOUT_SCHEMA,
        sha256=sha256,
        size_bytes=value.size_bytes,
        page_count=value.page_count,
        pages=tuple(pages),
    )


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(UTC)
    if not isinstance(current, datetime):
        _fail("EXTRACTION_REQUEST_INVALID")
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    return current.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _outcome(value: object, *, success_codes: frozenset[str]) -> str:
    if not isinstance(value, str) or not _SAFE_OUTCOME.fullmatch(value) or value in success_codes:
        _fail("EXTRACTION_REQUEST_INVALID")
    return value


def _rollback(db: Session) -> None:
    try:
        db.rollback()
    except SQLAlchemyError:
        pass


def _commit(db: Session) -> None:
    try:
        db.commit()
        db.expire_all()
    except SQLAlchemyError:
        _rollback(db)
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )
    except (AttributeError, TypeError, ValueError):
        _rollback(db)
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )


def _flush(db: Session) -> None:
    try:
        db.flush()
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def _system_audit(
    db: Session,
    *,
    action: str,
    run_id: str,
    previous_value: dict[str, object] | None,
    new_value: dict[str, object] | None,
    reason: str,
) -> None:
    record_audit(
        db,
        actor=None,
        actor_type="service",
        actor_name="CLASSIFIRE technical extraction worker",
        action=action,
        entity_type="technical_extraction_run",
        entity_id=run_id,
        previous_value=previous_value,
        new_value=new_value,
        reason=reason,
        correlation_id=run_id,
    )


def _canonical_payload_bytes(value: object, *, code: str) -> bytes:
    if not isinstance(value, dict):
        _fail(code)
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeEncodeError, RecursionError):
        _fail(code)


def _require_successful_invocation_receipt(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    invocation_id: str,
    operation: Literal["layout", "page"],
    page_number: int,
    expected_stdout_sha256: str,
    expected_stdout_size_bytes: int,
    page_claim: TechnicalExtractionPageClaim | None = None,
) -> tuple[TechnicalParserInvocation, TechnicalParserInvocationReceipt]:
    invocation = db.get(TechnicalParserInvocation, invocation_id)
    receipt = db.get(TechnicalParserInvocationReceipt, invocation_id)
    if invocation is None or receipt is None:
        _fail("EXTRACTION_INVOCATION_NOT_FOUND")
    _validated_persisted_execution_receipt(invocation, receipt)
    expected_attempt_token = (
        claim.attempt_token if page_claim is None else page_claim.attempt_token
    )
    expected_attempt_count = (
        claim.attempt_count if page_claim is None else page_claim.attempt_count
    )
    if (
        claim.run_schema != TECHNICAL_EXTRACTION_RUN_SCHEMA
        or claim.runtime_profile_sha256 is None
        or claim.runtime_attestation_sha256 is None
        or invocation.run_id != claim.run_id
        or invocation.run_attempt_token != claim.attempt_token
        or invocation.run_attempt_count != claim.attempt_count
        or invocation.operation != operation
        or invocation.page_number != page_number
        or invocation.attempt_token != expected_attempt_token
        or invocation.attempt_count != expected_attempt_count
        or invocation.worker_image_digest != claim.worker_image_digest
        or invocation.runtime_profile_sha256 != claim.runtime_profile_sha256
        or invocation.runtime_attestation_sha256 != claim.runtime_attestation_sha256
        or receipt.run_id != claim.run_id
        or receipt.operation != operation
        or receipt.page_number != page_number
        or receipt.request_sha256 != invocation.request_sha256
        or receipt.runtime_attestation_sha256 != invocation.runtime_attestation_sha256
        or receipt.execution_state != "succeeded"
        or receipt.cleanup_confirmed is not True
        or receipt.exit_code != 0
        or receipt.stdout_sha256 != expected_stdout_sha256
        or receipt.stdout_size_bytes != expected_stdout_size_bytes
        or (
            page_claim is None
            and (
                invocation.page_id is not None
                or invocation.page_attempt_token is not None
                or invocation.page_attempt_count is not None
            )
        )
        or (
            page_claim is not None
            and (
                invocation.page_id != page_claim.page_id
                or invocation.page_attempt_token != page_claim.attempt_token
                or invocation.page_attempt_count != page_claim.attempt_count
            )
        )
    ):
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    return invocation, receipt


def _source_is_eligible(stored: StoredFile) -> None:
    if (
        stored.purpose != "technical_evidence"
        or stored.malware_scan_status != "clean"
        or stored.immutable is not True
    ):
        _fail("EXTRACTION_SOURCE_NOT_ELIGIBLE")
    if Path(stored.original_filename).suffix.lower() != ".pdf":
        _fail("EXTRACTION_SOURCE_TYPE_UNSUPPORTED")
    _canonical_sha256(
        stored.sha256,
        code="EXTRACTION_SOURCE_BINDING_FAILED",
    )
    if (
        not isinstance(stored.size_bytes, int)
        or isinstance(stored.size_bytes, bool)
        or not 1 <= stored.size_bytes <= 1024 * 1024 * 1024
    ):
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")


def _claim_from_run(
    run: TechnicalExtractionRun,
    *,
    token: str | None = None,
    started_at: datetime | None = None,
    record_version: int | None = None,
    attempt_count: int | None = None,
    layout: TechnicalExtractionLayoutBinding | None = None,
    runtime_attestation_sha256: str | None = None,
    layout_invocation_id: str | None = None,
) -> TechnicalExtractionRunClaim:
    safe_token = token if token is not None else run.attempt_token
    safe_started = started_at if started_at is not None else run.attempt_started_at
    if (token is None and run.status != "processing") or safe_token is None or safe_started is None:
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    effective_page_count = run.page_count if layout is None else layout.page_count
    effective_layout_schema = run.layout_schema if layout is None else layout.schema
    effective_layout_sha256 = run.layout_sha256 if layout is None else layout.sha256
    effective_layout_size = run.layout_size_bytes if layout is None else layout.size_bytes
    if effective_page_count is None:
        if any(
            value is not None
            for value in (
                effective_layout_schema,
                effective_layout_sha256,
                effective_layout_size,
            )
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    elif (
        not isinstance(effective_page_count, int)
        or isinstance(effective_page_count, bool)
        or not 1 <= effective_page_count <= TECHNICAL_PAGE_EVIDENCE_MAX_PAGES
        or effective_layout_schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA
        or not isinstance(effective_layout_size, int)
        or isinstance(effective_layout_size, bool)
        or not 1 <= effective_layout_size <= TECHNICAL_EXTRACTION_LAYOUT_MAX_BYTES
    ):
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if effective_layout_sha256 is not None:
        effective_layout_sha256 = _canonical_sha256(
            effective_layout_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        )
    runtime_profile_sha256 = run.runtime_profile_sha256
    effective_runtime_attestation_sha256 = (
        run.runtime_attestation_sha256
        if runtime_attestation_sha256 is None
        else runtime_attestation_sha256
    )
    effective_layout_invocation_id = (
        run.layout_invocation_id if layout_invocation_id is None else layout_invocation_id
    )
    if run.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA_V1:
        if any(
            value is not None
            for value in (
                runtime_profile_sha256,
                effective_runtime_attestation_sha256,
                effective_layout_invocation_id,
            )
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    elif run.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA:
        runtime_profile_sha256 = _canonical_sha256(
            runtime_profile_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        )
        if effective_runtime_attestation_sha256 is not None:
            effective_runtime_attestation_sha256 = _canonical_sha256(
                effective_runtime_attestation_sha256,
                code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            )
        if effective_page_count is None:
            if effective_layout_invocation_id is not None:
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        else:
            effective_layout_invocation_id = _canonical_uuid4(
                effective_layout_invocation_id,
                code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            )
            if effective_runtime_attestation_sha256 is None:
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    else:
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    return TechnicalExtractionRunClaim(
        run_id=_canonical_uuid4(run.id, code="EXTRACTION_RUN_PERSISTENCE_CONFLICT"),
        record_version=record_version or run.record_version,
        attempt_token=_canonical_uuid4(
            safe_token,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        attempt_started_at=_as_utc(safe_started),
        attempt_count=attempt_count or run.attempt_count,
        technical_document_id=_canonical_uuid4(
            run.technical_document_id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        source_stored_file_id=_canonical_uuid4(
            run.source_stored_file_id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        source_sha256=_canonical_sha256(
            run.source_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        source_size_bytes=run.source_size_bytes,
        extraction_policy=run.extraction_policy,
        extraction_policy_sha256=_canonical_sha256(
            run.extraction_policy_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        ocr_low_confidence_threshold=_ocr_threshold(
            run.ocr_low_confidence_threshold,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        worker_image_digest=_canonical_sha256(
            run.worker_image_digest,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        run_schema=run.run_schema,
        runtime_profile_sha256=runtime_profile_sha256,
        runtime_attestation_sha256=effective_runtime_attestation_sha256,
        page_count=effective_page_count,
        layout_schema=effective_layout_schema,
        layout_sha256=effective_layout_sha256,
        layout_size_bytes=effective_layout_size,
        layout_invocation_id=effective_layout_invocation_id,
    )


def _refreshed_run_claim(
    claim: TechnicalExtractionRunClaim,
    *,
    now: datetime,
    layout: TechnicalExtractionLayoutBinding | None = None,
    runtime_attestation_sha256: str | None = None,
    layout_invocation_id: str | None = None,
) -> TechnicalExtractionRunClaim:
    return replace(
        claim,
        record_version=claim.record_version + 1,
        attempt_started_at=now,
        page_count=claim.page_count if layout is None else layout.page_count,
        layout_schema=claim.layout_schema if layout is None else layout.schema,
        layout_sha256=claim.layout_sha256 if layout is None else layout.sha256,
        layout_size_bytes=claim.layout_size_bytes if layout is None else layout.size_bytes,
        runtime_attestation_sha256=(
            claim.runtime_attestation_sha256
            if runtime_attestation_sha256 is None
            else runtime_attestation_sha256
        ),
        layout_invocation_id=(
            claim.layout_invocation_id
            if layout_invocation_id is None
            else layout_invocation_id
        ),
    )


def _request_technical_extraction_run(
    db: Session,
    *,
    actor: User,
    technical_document_id: object,
    extraction_policy: object,
    extraction_policy_bytes: object,
    ocr_low_confidence_threshold: object,
    worker_image_digest: object,
    runtime_profile_sha256: object,
    source_ip: str | None = None,
) -> TechnicalExtractionRequestResult:
    """Create or replay one exact Draft extraction identity."""

    if not isinstance(actor, User) or not actor.id:
        _fail("EXTRACTION_REQUEST_INVALID")
    with db.no_autoflush:
        persisted_actor = db.get(User, actor.id, populate_existing=True)
    if (
        persisted_actor is None
        or not persisted_actor.is_active
        or not has_permission(persisted_actor, "technical:write")
    ):
        _fail("EXTRACTION_REQUEST_INVALID")
    document_id = _canonical_uuid4(
        technical_document_id,
        code="EXTRACTION_REQUEST_INVALID",
    )
    if (
        not isinstance(extraction_policy, str)
        or not _SAFE_POLICY.fullmatch(extraction_policy)
        or not isinstance(extraction_policy_bytes, bytes)
        or not extraction_policy_bytes
        or len(extraction_policy_bytes) > TECHNICAL_PAGE_EVIDENCE_MAX_POLICY_BYTES
    ):
        _fail("EXTRACTION_POLICY_INVALID")
    policy_sha256 = hashlib.sha256(extraction_policy_bytes).hexdigest()
    ocr_threshold = _ocr_threshold(
        ocr_low_confidence_threshold,
        code="EXTRACTION_POLICY_INVALID",
    )
    worker_digest = _canonical_sha256(
        worker_image_digest,
        code="EXTRACTION_WORKER_DIGEST_INVALID",
    )
    runtime_profile_digest = _canonical_sha256(
        runtime_profile_sha256,
        code="EXTRACTION_RUNTIME_PROFILE_INVALID",
    )
    document = db.get(TechnicalDocument, document_id)
    if document is None:
        _fail("EXTRACTION_SOURCE_NOT_FOUND")
    stored = db.get(StoredFile, document.stored_file_id)
    if stored is None:
        _fail("EXTRACTION_SOURCE_NOT_FOUND")
    _source_is_eligible(stored)

    identity = (
        TechnicalExtractionRun.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA,
        TechnicalExtractionRun.technical_document_id == document.id,
        TechnicalExtractionRun.source_stored_file_id == stored.id,
        TechnicalExtractionRun.source_sha256 == stored.sha256,
        TechnicalExtractionRun.source_size_bytes == stored.size_bytes,
        TechnicalExtractionRun.extraction_policy_sha256 == policy_sha256,
        TechnicalExtractionRun.ocr_low_confidence_threshold == ocr_threshold,
        TechnicalExtractionRun.worker_image_digest == worker_digest,
        TechnicalExtractionRun.runtime_profile_sha256 == runtime_profile_digest,
    )

    def existing_result() -> TechnicalExtractionRequestResult | None:
        existing = db.scalar(select(TechnicalExtractionRun).where(*identity))
        if existing is None:
            return None
        if (
            existing.run_schema != TECHNICAL_EXTRACTION_RUN_SCHEMA
            or existing.extraction_policy != extraction_policy
            or existing.page_evidence_schema != TECHNICAL_PAGE_EVIDENCE_SCHEMA
            or existing.runtime_attestation_sha256 is not None
            and existing.status == "queued"
            and existing.attempt_count == 0
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        return TechnicalExtractionRequestResult(existing.id, True)

    replay = existing_result()
    if replay is not None:
        db.rollback()
        return replay

    run = TechnicalExtractionRun(
        run_schema=TECHNICAL_EXTRACTION_RUN_SCHEMA,
        source_stored_file_id=stored.id,
        technical_document_id=document.id,
        source_sha256=stored.sha256,
        source_size_bytes=stored.size_bytes,
        extraction_policy=extraction_policy,
        extraction_policy_sha256=policy_sha256,
        ocr_low_confidence_threshold=ocr_threshold,
        worker_image_digest=worker_digest,
        runtime_profile_sha256=runtime_profile_digest,
        requested_by_id=persisted_actor.id,
    )
    db.add(run)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replay = existing_result()
        if replay is None:
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        db.rollback()
        return replay
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    record_audit(
        db,
        actor=persisted_actor,
        action="request_technical_extraction",
        entity_type="technical_extraction_run",
        entity_id=run.id,
        new_value={
            "run_schema": run.run_schema,
            "technical_document_id": document.id,
            "source_stored_file_id": stored.id,
            "source_sha256": stored.sha256,
            "source_size_bytes": stored.size_bytes,
            "extraction_policy": extraction_policy,
            "extraction_policy_sha256": policy_sha256,
            "ocr_low_confidence_threshold": format(ocr_threshold, "f"),
            "worker_image_digest": worker_digest,
            "runtime_profile_sha256": runtime_profile_digest,
            "status": "queued",
        },
        reason="Requested an authority-neutral Draft extraction",
        source_ip=source_ip,
        correlation_id=run.id,
    )
    _flush(db)
    _commit(db)
    return TechnicalExtractionRequestResult(run.id, False)


def request_technical_extraction_run(
    db: Session,
    *,
    actor: User,
    technical_document_id: object,
    extraction_policy: object,
    extraction_policy_bytes: object,
    ocr_low_confidence_threshold: object,
    worker_image_digest: object,
    runtime_profile_sha256: object,
    source_ip: str | None = None,
) -> TechnicalExtractionRequestResult:
    """Own and close the transaction for an idempotent extraction request."""

    try:
        return _request_technical_extraction_run(
            db,
            actor=actor,
            technical_document_id=technical_document_id,
            extraction_policy=extraction_policy,
            extraction_policy_bytes=extraction_policy_bytes,
            ocr_low_confidence_threshold=ocr_low_confidence_threshold,
            worker_image_digest=worker_image_digest,
            runtime_profile_sha256=runtime_profile_sha256,
            source_ip=source_ip,
        )
    except TechnicalExtractionError:
        _rollback(db)
        raise
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


_RUNTIME_ATTESTATION_CLAIMS_V1 = frozenset(
    {
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
)
_RUNTIME_ATTESTATION_CLAIMS_V2 = _RUNTIME_ATTESTATION_CLAIMS_V1 | {
    "execution_fence_sha256",
    "oci_daemon_identity_sha256",
}


def _runtime_attestation_claims(
    attestation: object,
    *,
    claim: TechnicalExtractionRunClaim,
) -> tuple[TechnicalParserRuntimeAttestation, dict[str, object], dict[str, object]]:
    if not isinstance(attestation, TechnicalParserRuntimeAttestation):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    payload = attestation.as_dict()
    claims = payload.get("claims")
    if (
        attestation.schema
        not in {
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA,
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        }
        or attestation.engine != "oci"
        or set(payload) != {"claims", "engine", "schema"}
        or not isinstance(claims, dict)
        or set(claims)
        != (
            _RUNTIME_ATTESTATION_CLAIMS_V2
            if attestation.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2
            else _RUNTIME_ATTESTATION_CLAIMS_V1
        )
        or claim.run_schema != TECHNICAL_EXTRACTION_RUN_SCHEMA
        or claim.runtime_profile_sha256 is None
        or claims.get("extraction_policy") != claim.extraction_policy
        or claims.get("extraction_policy_sha256") != claim.extraction_policy_sha256
        or claims.get("worker_image_digest") != claim.worker_image_digest
        or claims.get("runtime_profile_sha256") != claim.runtime_profile_sha256
        or claims.get("oci_profile_schema") != "technical-parser-oci-profile-v1"
        or claims.get("transport_schema") != "technical-parser-stdin-frame-v1"
        or claims.get("platform") not in {"linux/amd64", "linux/arm64"}
    ):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    for key in (
        "extraction_policy_sha256",
        "worker_image_digest",
        "runtime_executable_sha256",
        "runtime_profile_sha256",
        "seccomp_profile_sha256",
    ):
        _canonical_sha256(
            claims.get(key),
            code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
        )
    if attestation.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2:
        for key in ("execution_fence_sha256", "oci_daemon_identity_sha256"):
            _canonical_sha256(
                claims.get(key),
                code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
            )
    _canonical_uuid4(
        claims.get("controller_owner_id"),
        code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
    )
    image_id = claims.get("image_id")
    image_reference = claims.get("image_reference")
    runtime_host = claims.get("runtime_host")
    if (
        not isinstance(image_id, str)
        or not image_id.startswith("sha256:")
        or len(image_id) != 71
        or _canonical_sha256(
            image_id.removeprefix("sha256:"),
            code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
        )
        != image_id.removeprefix("sha256:")
        or not isinstance(image_reference, str)
        or not image_reference.endswith(f"@sha256:{claim.worker_image_digest}")
        or not 73 <= len(image_reference) <= 500
        or not isinstance(runtime_host, str)
        or re.fullmatch(r"unix:///run/user/[1-9][0-9]{0,9}/docker\.sock", runtime_host)
        is None
        or hashlib.sha256(attestation.canonical_json).hexdigest() != attestation.sha256
    ):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    return attestation, payload, claims


def _reservation_matches(
    invocation: TechnicalParserInvocation,
    *,
    claim: TechnicalExtractionRunClaim,
    page_claim: TechnicalExtractionPageClaim | None,
    operation: Literal["layout", "page"],
    page_number: int,
    request_sha256: str,
    request_size_bytes: int,
    attestation: TechnicalParserRuntimeAttestation,
    payload: dict[str, object],
    claims: dict[str, object],
) -> bool:
    attempt_token = claim.attempt_token if page_claim is None else page_claim.attempt_token
    attempt_count = claim.attempt_count if page_claim is None else page_claim.attempt_count
    return (
        invocation.invocation_schema == "technical-parser-invocation-v1"
        and invocation.run_id == claim.run_id
        and invocation.run_attempt_token == claim.attempt_token
        and invocation.run_attempt_count == claim.attempt_count
        and invocation.operation == operation
        and invocation.page_id == (None if page_claim is None else page_claim.page_id)
        and invocation.page_number == page_number
        and invocation.page_attempt_token
        == (None if page_claim is None else page_claim.attempt_token)
        and invocation.page_attempt_count
        == (None if page_claim is None else page_claim.attempt_count)
        and invocation.attempt_token == attempt_token
        and invocation.attempt_count == attempt_count
        and invocation.request_sha256 == request_sha256
        and invocation.request_size_bytes == request_size_bytes
        and invocation.extraction_policy == claim.extraction_policy
        and invocation.extraction_policy_sha256 == claim.extraction_policy_sha256
        and invocation.worker_image_digest == claim.worker_image_digest
        and invocation.oci_profile_schema == claims["oci_profile_schema"]
        and invocation.transport_schema == claims["transport_schema"]
        and invocation.image_reference == claims["image_reference"]
        and invocation.image_id == claims["image_id"]
        and invocation.platform == claims["platform"]
        and invocation.runtime_host == claims["runtime_host"]
        and invocation.runtime_executable_sha256
        == claims["runtime_executable_sha256"]
        and invocation.seccomp_profile_sha256 == claims["seccomp_profile_sha256"]
        and invocation.runtime_profile_sha256 == claim.runtime_profile_sha256
        and invocation.runtime_attestation_schema == attestation.schema
        and invocation.runtime_attestation_json == payload
        and invocation.runtime_attestation_sha256 == attestation.sha256
        and invocation.immutable is True
        and invocation.record_version == 1
    )


def _reconcile_parser_invocation_reservation(
    db: Session,
    *,
    invocation_id: str,
    claim: TechnicalExtractionRunClaim,
    page_claim: TechnicalExtractionPageClaim | None,
    operation: Literal["layout", "page"],
    page_number: int,
    request_sha256: str,
    request_size_bytes: int,
    attestation: TechnicalParserRuntimeAttestation,
    payload: dict[str, object],
    claims: dict[str, object],
) -> TechnicalParserInvocationReservation | None:
    _rollback(db)
    invocation = db.get(
        TechnicalParserInvocation,
        invocation_id,
        populate_existing=True,
    )
    run = db.get(TechnicalExtractionRun, claim.run_id, populate_existing=True)
    if invocation is None:
        db.rollback()
        return None
    if db.get(TechnicalParserInvocationReceipt, invocation_id) is not None:
        db.rollback()
        _fail("EXTRACTION_INVOCATION_ALREADY_TERMINAL")
    if (
        run is None
        or run.status != "processing"
        or run.attempt_token != claim.attempt_token
        or run.record_version != claim.record_version + 1
        or run.runtime_attestation_sha256 != attestation.sha256
        or not _reservation_matches(
            invocation,
            claim=claim,
            page_claim=page_claim,
            operation=operation,
            page_number=page_number,
            request_sha256=request_sha256,
            request_size_bytes=request_size_bytes,
            attestation=attestation,
            payload=payload,
            claims=claims,
        )
    ):
        db.rollback()
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )
    refreshed = _claim_from_run(run)
    db.rollback()
    return TechnicalParserInvocationReservation(
        invocation_id=invocation_id,
        run_claim=refreshed,
        operation=operation,
        page_number=page_number,
        attempt_token=(
            claim.attempt_token if page_claim is None else page_claim.attempt_token
        ),
        attempt_count=(
            claim.attempt_count if page_claim is None else page_claim.attempt_count
        ),
        request_sha256=request_sha256,
        request_size_bytes=request_size_bytes,
        runtime_attestation_sha256=attestation.sha256,
        idempotent_replay=True,
    )


def reserve_technical_parser_invocation(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    operation: Literal["layout", "page"],
    request: object,
    runtime_attestation: object,
    invocation_id: object,
    page_claim: TechnicalExtractionPageClaim | None = None,
    now: datetime | None = None,
) -> TechnicalParserInvocationReservation:
    """Commit one immutable invocation identity before external parser work."""

    safe_invocation_id = _canonical_uuid4(
        invocation_id,
        code="EXTRACTION_REQUEST_INVALID",
    )
    if (
        not isinstance(request, bytes)
        or not 1 <= len(request) <= 4096
        or operation not in {"layout", "page"}
        or (operation == "layout" and page_claim is not None)
        or (operation == "page" and page_claim is None)
    ):
        _fail("EXTRACTION_REQUEST_INVALID")
    if page_claim is not None and page_claim.run_claim != claim:
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    page_number = 0 if page_claim is None else page_claim.page_number
    expected_request = (
        encode_technical_parser_layout_request(
            technical_document_id=claim.technical_document_id,
            source_sha256=claim.source_sha256,
            source_size_bytes=claim.source_size_bytes,
            extraction_policy=claim.extraction_policy,
            extraction_policy_sha256=claim.extraction_policy_sha256,
            worker_image_digest=claim.worker_image_digest,
            ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
        )
        if page_claim is None
        else encode_technical_parser_request(
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
            ocr_low_confidence_threshold=claim.ocr_low_confidence_threshold,
        )
    )
    if request != expected_request:
        _fail("EXTRACTION_REQUEST_INVALID")
    request_sha256 = hashlib.sha256(request).hexdigest()
    attestation, payload, claims = _runtime_attestation_claims(
        runtime_attestation,
        claim=claim,
    )
    if (
        claim.runtime_attestation_sha256 is not None
        and claim.runtime_attestation_sha256 != attestation.sha256
    ):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_MISMATCH")

    existing = db.get(TechnicalParserInvocation, safe_invocation_id)
    if existing is not None:
        if not _reservation_matches(
            existing,
            claim=claim,
            page_claim=page_claim,
            operation=operation,
            page_number=page_number,
            request_sha256=request_sha256,
            request_size_bytes=len(request),
            attestation=attestation,
            payload=payload,
            claims=claims,
        ):
            db.rollback()
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        run = db.get(TechnicalExtractionRun, claim.run_id, populate_existing=True)
        if (
            run is None
            or run.status != "processing"
            or run.attempt_token != claim.attempt_token
            or run.runtime_attestation_sha256 != attestation.sha256
        ):
            db.rollback()
            _fail("EXTRACTION_RUN_CLAIM_LOST")
        if db.get(TechnicalParserInvocationReceipt, safe_invocation_id) is not None:
            db.rollback()
            _fail("EXTRACTION_INVOCATION_ALREADY_TERMINAL")
        db.rollback()
        _fail("EXTRACTION_INVOCATION_PENDING")

    run = db.scalar(
        select(TechnicalExtractionRun).where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
        )
    )
    if run is None:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    if (
        run.run_schema != TECHNICAL_EXTRACTION_RUN_SCHEMA
        or run.runtime_profile_sha256 != claim.runtime_profile_sha256
        or run.worker_image_digest != claim.worker_image_digest
        or run.runtime_attestation_sha256 not in {None, attestation.sha256}
    ):
        db.rollback()
        _fail("EXTRACTION_RUNTIME_ATTESTATION_MISMATCH")
    current = _utc(now)
    refreshed = _cas_run_heartbeat(
        db,
        claim=claim,
        now=current,
        runtime_attestation_sha256=attestation.sha256,
    )
    attempt_token = claim.attempt_token if page_claim is None else page_claim.attempt_token
    attempt_count = claim.attempt_count if page_claim is None else page_claim.attempt_count
    invocation = TechnicalParserInvocation(
        id=safe_invocation_id,
        run_id=claim.run_id,
        run_attempt_token=claim.attempt_token,
        run_attempt_count=claim.attempt_count,
        operation=operation,
        page_id=None if page_claim is None else page_claim.page_id,
        page_number=page_number,
        page_attempt_token=None if page_claim is None else page_claim.attempt_token,
        page_attempt_count=None if page_claim is None else page_claim.attempt_count,
        attempt_token=attempt_token,
        attempt_count=attempt_count,
        request_sha256=request_sha256,
        request_size_bytes=len(request),
        extraction_policy=claim.extraction_policy,
        extraction_policy_sha256=claim.extraction_policy_sha256,
        worker_image_digest=claim.worker_image_digest,
        oci_profile_schema=claims["oci_profile_schema"],
        transport_schema=claims["transport_schema"],
        image_reference=claims["image_reference"],
        image_id=claims["image_id"],
        platform=claims["platform"],
        runtime_host=claims["runtime_host"],
        runtime_executable_sha256=claims["runtime_executable_sha256"],
        seccomp_profile_sha256=claims["seccomp_profile_sha256"],
        runtime_profile_sha256=claim.runtime_profile_sha256,
        runtime_attestation_schema=attestation.schema,
        runtime_attestation_json=payload,
        runtime_attestation_sha256=attestation.sha256,
        immutable=True,
    )
    db.add(invocation)
    try:
        db.flush()
        _system_audit(
            db,
            action="reserve_technical_parser_invocation",
            run_id=claim.run_id,
            previous_value={"record_version": claim.record_version},
            new_value={
                "record_version": refreshed.record_version,
                "invocation_id": safe_invocation_id,
                "operation": operation,
                "page_number": page_number,
                "request_sha256": request_sha256,
                "runtime_attestation_sha256": attestation.sha256,
            },
            reason="Reserved an exact authority-neutral parser invocation",
        )
        db.flush()
        _commit(db)
    except TechnicalExtractionError as error:
        replay = _reconcile_parser_invocation_reservation(
            db,
            invocation_id=safe_invocation_id,
            claim=claim,
            page_claim=page_claim,
            operation=operation,
            page_number=page_number,
            request_sha256=request_sha256,
            request_size_bytes=len(request),
            attestation=attestation,
            payload=payload,
            claims=claims,
        )
        if replay is not None:
            return replay
        if error.database_outcome == "commit_outcome_unknown":
            raise
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    except SQLAlchemyError:
        replay = _reconcile_parser_invocation_reservation(
            db,
            invocation_id=safe_invocation_id,
            claim=claim,
            page_claim=page_claim,
            operation=operation,
            page_number=page_number,
            request_sha256=request_sha256,
            request_size_bytes=len(request),
            attestation=attestation,
            payload=payload,
            claims=claims,
        )
        if replay is not None:
            return replay
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    return TechnicalParserInvocationReservation(
        invocation_id=safe_invocation_id,
        run_claim=refreshed,
        operation=operation,
        page_number=page_number,
        attempt_token=attempt_token,
        attempt_count=attempt_count,
        request_sha256=request_sha256,
        request_size_bytes=len(request),
        runtime_attestation_sha256=attestation.sha256,
    )


def _receipt_matches(
    persisted: TechnicalParserInvocationReceipt,
    *,
    invocation: TechnicalParserInvocation,
    receipt: TechnicalParserExecutionReceipt,
    payload: dict[str, object],
) -> bool:
    return (
        persisted.invocation_id == invocation.id
        and persisted.receipt_schema == TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA
        and persisted.run_id == invocation.run_id
        and persisted.operation == invocation.operation
        and persisted.page_number == invocation.page_number
        and persisted.request_sha256 == invocation.request_sha256
        and persisted.runtime_attestation_sha256
        == invocation.runtime_attestation_sha256
        and persisted.execution_state == receipt.execution_state
        and persisted.outcome_code == receipt.outcome_code
        and persisted.container_id == receipt.container_id
        and (
            (persisted.started_at is None and receipt.started_at is None)
            or (
                persisted.started_at is not None
                and receipt.started_at is not None
                and _as_utc(persisted.started_at) == _as_utc(receipt.started_at)
            )
        )
        and _as_utc(persisted.completed_at) == _as_utc(receipt.completed_at)
        and persisted.exit_code == receipt.exit_code
        and persisted.stdout_sha256 == receipt.stdout_sha256
        and persisted.stdout_size_bytes == receipt.stdout_size_bytes
        and persisted.cleanup_confirmed is receipt.cleanup_confirmed
        and persisted.receipt_json == payload
        and persisted.receipt_sha256 == receipt.sha256
        and persisted.immutable is True
    )


def _validated_invocation_runtime_attestation(
    invocation: TechnicalParserInvocation,
) -> tuple[TechnicalParserRuntimeAttestation, dict[str, object]]:
    attestation_bytes = _canonical_payload_bytes(
        invocation.runtime_attestation_json,
        code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
    )
    try:
        attestation = parse_technical_parser_runtime_attestation(
            attestation_bytes,
            expected_sha256=invocation.runtime_attestation_sha256,
        )
    except ValueError:
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    attestation_payload = attestation.as_dict()
    claims = attestation_payload.get("claims")
    if not isinstance(claims, dict):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    controller_owner_id = _canonical_uuid4(
        claims.get("controller_owner_id"),
        code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
    )
    expected_claims: dict[str, object] = {
        "controller_owner_id": controller_owner_id,
        "extraction_policy": invocation.extraction_policy,
        "extraction_policy_sha256": invocation.extraction_policy_sha256,
        "image_id": invocation.image_id,
        "image_reference": invocation.image_reference,
        "oci_profile_schema": invocation.oci_profile_schema,
        "platform": invocation.platform,
        "runtime_executable_sha256": invocation.runtime_executable_sha256,
        "runtime_host": invocation.runtime_host,
        "runtime_profile_sha256": invocation.runtime_profile_sha256,
        "seccomp_profile_sha256": invocation.seccomp_profile_sha256,
        "transport_schema": invocation.transport_schema,
        "worker_image_digest": invocation.worker_image_digest,
    }
    if attestation.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2:
        expected_claims.update(
            execution_fence_sha256=_canonical_sha256(
                claims.get("execution_fence_sha256"),
                code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
            ),
            oci_daemon_identity_sha256=_canonical_sha256(
                claims.get("oci_daemon_identity_sha256"),
                code="EXTRACTION_RUNTIME_ATTESTATION_INVALID",
            ),
        )
    if (
        attestation.schema != invocation.runtime_attestation_schema
        or attestation.schema
        not in {
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA,
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        }
        or attestation.engine != "oci"
        or claims != expected_claims
        or invocation.invocation_schema != "technical-parser-invocation-v1"
        or invocation.immutable is not True
        or invocation.record_version != 1
    ):
        _fail("EXTRACTION_RUNTIME_ATTESTATION_INVALID")
    return attestation, expected_claims


def _receipt_attestation_matches_invocation(
    *,
    reserved: TechnicalParserRuntimeAttestation,
    expected_claims: dict[str, object],
    receipt: TechnicalParserExecutionReceipt,
) -> bool:
    if receipt.attestation == reserved:
        return True
    observed_payload = receipt.attestation.as_dict()
    observed_claims = observed_payload.get("claims")
    if not isinstance(observed_claims, dict):
        return False
    observed_image_id = observed_claims.get("image_id")
    expected_drift_claims = dict(expected_claims)
    expected_drift_claims["image_id"] = observed_image_id
    if reserved.schema == TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2:
        observed_daemon_sha256 = observed_claims.get(
            "oci_daemon_identity_sha256"
        )
        if (
            not isinstance(observed_daemon_sha256, str)
            or len(observed_daemon_sha256) != 64
            or any(
                character not in _HEX
                for character in observed_daemon_sha256
            )
        ):
            return False
        expected_drift_claims["oci_daemon_identity_sha256"] = (
            observed_daemon_sha256
        )
    return (
        receipt.execution_state == "not_started"
        and receipt.outcome_code == "PARSER_EXECUTION_FAILED"
        and receipt.container_id is None
        and receipt.started_at is None
        and receipt.exit_code is None
        and receipt.stdout_sha256 is None
        and receipt.stdout_size_bytes is None
        and receipt.cleanup_confirmed is True
        and receipt.attestation.schema == reserved.schema
        and receipt.attestation.engine == reserved.engine == "oci"
        and receipt.attestation.sha256 != reserved.sha256
        and isinstance(observed_image_id, str)
        and observed_image_id.startswith("sha256:")
        and len(observed_image_id) == 71
        and set(observed_image_id.removeprefix("sha256:")) <= _HEX
        and observed_claims == expected_drift_claims
    )


def _validated_persisted_execution_receipt(
    invocation: TechnicalParserInvocation,
    persisted: TechnicalParserInvocationReceipt,
) -> TechnicalParserExecutionReceipt:
    """Reparse canonical evidence and bind every narrative field to its columns."""

    reserved_attestation, expected_claims = (
        _validated_invocation_runtime_attestation(invocation)
    )
    receipt_bytes = _canonical_payload_bytes(
        persisted.receipt_json,
        code="EXTRACTION_INVOCATION_RECEIPT_INVALID",
    )
    try:
        receipt = parse_technical_parser_execution_receipt(
            receipt_bytes,
            expected_sha256=persisted.receipt_sha256,
        )
    except ValueError:
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    if (
        receipt.invocation_id != invocation.id
        or receipt.operation != invocation.operation
        or receipt.expected_attestation_sha256
        != invocation.runtime_attestation_sha256
        or not _receipt_attestation_matches_invocation(
            reserved=reserved_attestation,
            expected_claims=expected_claims,
            receipt=receipt,
        )
        or not _receipt_matches(
            persisted,
            invocation=invocation,
            receipt=receipt,
            payload=receipt.as_dict(),
        )
    ):
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    return receipt


def _receipt_binding(
    receipt: TechnicalParserExecutionReceipt,
    *,
    idempotent_replay: bool,
) -> TechnicalParserInvocationReceiptBinding:
    return TechnicalParserInvocationReceiptBinding(
        invocation_id=receipt.invocation_id,
        receipt_sha256=receipt.sha256,
        execution_state=receipt.execution_state,
        stdout_sha256=receipt.stdout_sha256,
        stdout_size_bytes=receipt.stdout_size_bytes,
        cleanup_confirmed=receipt.cleanup_confirmed,
        idempotent_replay=idempotent_replay,
    )


def _stage_technical_parser_invocation_receipt(
    db: Session,
    *,
    invocation: TechnicalParserInvocation,
    receipt: TechnicalParserExecutionReceipt,
    receipt_payload: dict[str, object],
    reconciliation: bool = False,
) -> TechnicalParserInvocationReceiptBinding:
    """Stage an append-only receipt and its audit without committing."""

    existing = db.get(
        TechnicalParserInvocationReceipt,
        invocation.id,
        populate_existing=True,
    )
    if existing is not None:
        if not _receipt_matches(
            existing,
            invocation=invocation,
            receipt=receipt,
            payload=receipt_payload,
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        return _receipt_binding(receipt, idempotent_replay=True)

    db.add(
        TechnicalParserInvocationReceipt(
            invocation_id=invocation.id,
            receipt_schema=receipt.receipt_schema,
            run_id=invocation.run_id,
            operation=invocation.operation,
            page_number=invocation.page_number,
            request_sha256=invocation.request_sha256,
            runtime_attestation_sha256=invocation.runtime_attestation_sha256,
            execution_state=receipt.execution_state,
            outcome_code=receipt.outcome_code,
            container_id=receipt.container_id,
            started_at=receipt.started_at,
            completed_at=receipt.completed_at,
            exit_code=receipt.exit_code,
            stdout_sha256=receipt.stdout_sha256,
            stdout_size_bytes=receipt.stdout_size_bytes,
            cleanup_confirmed=receipt.cleanup_confirmed,
            receipt_json=receipt_payload,
            receipt_sha256=receipt.sha256,
            immutable=True,
        )
    )
    _flush(db)
    _system_audit(
        db,
        action="record_technical_parser_invocation_receipt",
        run_id=invocation.run_id,
        previous_value=None,
        new_value={
            "invocation_id": invocation.id,
            "execution_state": receipt.execution_state,
            "outcome_code": receipt.outcome_code,
            "receipt_sha256": receipt.sha256,
            "cleanup_confirmed": receipt.cleanup_confirmed,
            "reconciliation": reconciliation,
        },
        reason=(
            "Recorded a cleanup-proven orphan parser receipt during reconciliation"
            if reconciliation
            else "Recorded an append-only isolated-parser invocation receipt"
        ),
    )
    _flush(db)
    return _receipt_binding(receipt, idempotent_replay=False)


def record_technical_parser_invocation_receipt(
    db: Session,
    *,
    reservation: TechnicalParserInvocationReservation,
    receipt: object,
) -> TechnicalParserInvocationReceiptBinding:
    """Append or exactly replay one terminal receipt before output parsing."""

    if (
        not isinstance(reservation, TechnicalParserInvocationReservation)
        or not isinstance(receipt, TechnicalParserExecutionReceipt)
        or receipt.invocation_id != reservation.invocation_id
        or receipt.operation != reservation.operation
        or receipt.expected_attestation_sha256
        != reservation.runtime_attestation_sha256
        or hashlib.sha256(receipt.canonical_json).hexdigest() != receipt.sha256
    ):
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    invocation = db.get(
        TechnicalParserInvocation,
        reservation.invocation_id,
        populate_existing=True,
    )
    if invocation is None:
        db.rollback()
        _fail("EXTRACTION_INVOCATION_NOT_FOUND")
    reserved_attestation, expected_claims = (
        _validated_invocation_runtime_attestation(invocation)
    )
    receipt_payload = receipt.as_dict()
    if (
        invocation.run_id != reservation.run_claim.run_id
        or invocation.operation != reservation.operation
        or invocation.page_number != reservation.page_number
        or invocation.attempt_token != reservation.attempt_token
        or invocation.attempt_count != reservation.attempt_count
        or invocation.request_sha256 != reservation.request_sha256
        or invocation.request_size_bytes != reservation.request_size_bytes
        or invocation.runtime_attestation_sha256
        != reservation.runtime_attestation_sha256
        or not _receipt_attestation_matches_invocation(
            reserved=reserved_attestation,
            expected_claims=expected_claims,
            receipt=receipt,
        )
    ):
        db.rollback()
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    try:
        binding = _stage_technical_parser_invocation_receipt(
            db,
            invocation=invocation,
            receipt=receipt,
            receipt_payload=receipt_payload,
        )
        if binding.idempotent_replay:
            db.rollback()
            return binding
        _commit(db)
    except (TechnicalExtractionError, SQLAlchemyError) as error:
        _rollback(db)
        existing = db.get(
            TechnicalParserInvocationReceipt,
            reservation.invocation_id,
            populate_existing=True,
        )
        if existing is not None and _receipt_matches(
            existing,
            invocation=invocation,
            receipt=receipt,
            payload=receipt_payload,
        ):
            db.rollback()
            return _receipt_binding(receipt, idempotent_replay=True)
        db.rollback()
        if (
            isinstance(error, TechnicalExtractionError)
            and error.database_outcome == "commit_outcome_unknown"
        ):
            raise
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )
    return binding


def _unsettled_current_attempt_invocation():  # type: ignore[no-untyped-def]
    """Return a run-correlated guard for parser work awaiting resolution.

    A receipt does not settle an invocation by itself: the coordinator may die
    after recording it but before accepting its output or resolving its
    failure. Only the exact live run/page attempt with no accepted invocation
    binding is fenced. Earlier attempts therefore remain provenance without
    preventing an explicitly resolved retry.
    """

    return (
        select(TechnicalParserInvocation.id)
        .outerjoin(
            TechnicalExtractionPage,
            and_(
                TechnicalParserInvocation.operation == "page",
                TechnicalExtractionPage.id == TechnicalParserInvocation.page_id,
                TechnicalExtractionPage.run_id == TechnicalParserInvocation.run_id,
                TechnicalExtractionPage.page_number
                == TechnicalParserInvocation.page_number,
            ),
        )
        .where(
            TechnicalParserInvocation.run_id == TechnicalExtractionRun.id,
            TechnicalParserInvocation.run_attempt_token
            == TechnicalExtractionRun.attempt_token,
            TechnicalParserInvocation.run_attempt_count
            == TechnicalExtractionRun.attempt_count,
            or_(
                and_(
                    TechnicalParserInvocation.operation == "layout",
                    TechnicalExtractionRun.layout_invocation_id.is_(None),
                ),
                and_(
                    TechnicalParserInvocation.operation == "page",
                    TechnicalExtractionPage.status == "processing",
                    TechnicalExtractionPage.attempt_token
                    == TechnicalParserInvocation.page_attempt_token,
                    TechnicalExtractionPage.attempt_count
                    == TechnicalParserInvocation.page_attempt_count,
                    TechnicalExtractionPage.parser_invocation_id.is_(None),
                ),
            ),
        )
        .exists()
    )


def _reconciliation_invocation_conditions():  # type: ignore[no-untyped-def]
    return (
        TechnicalExtractionRun.status == "processing",
        TechnicalExtractionRun.attempt_token
        == TechnicalParserInvocation.run_attempt_token,
        TechnicalExtractionRun.attempt_count
        == TechnicalParserInvocation.run_attempt_count,
        or_(
            and_(
                TechnicalParserInvocation.operation == "layout",
                TechnicalParserInvocation.page_id.is_(None),
                TechnicalParserInvocation.page_number == 0,
                TechnicalExtractionRun.layout_invocation_id.is_(None),
            ),
            and_(
                TechnicalParserInvocation.operation == "page",
                TechnicalExtractionPage.id == TechnicalParserInvocation.page_id,
                TechnicalExtractionPage.run_id == TechnicalParserInvocation.run_id,
                TechnicalExtractionPage.page_number
                == TechnicalParserInvocation.page_number,
                TechnicalExtractionPage.status == "processing",
                TechnicalExtractionPage.attempt_token
                == TechnicalParserInvocation.page_attempt_token,
                TechnicalExtractionPage.attempt_count
                == TechnicalParserInvocation.page_attempt_count,
                TechnicalExtractionPage.parser_invocation_id.is_(None),
            ),
        ),
    )


def count_unsettled_technical_parser_invocations(db: Session) -> int:
    """Count exact current-attempt invocations whose output is not accepted."""

    value = db.scalar(
        select(func.count(TechnicalParserInvocation.id))
        .select_from(TechnicalParserInvocation)
        .join(
            TechnicalExtractionRun,
            TechnicalExtractionRun.id == TechnicalParserInvocation.run_id,
        )
        .outerjoin(
            TechnicalExtractionPage,
            and_(
                TechnicalParserInvocation.operation == "page",
                TechnicalExtractionPage.id == TechnicalParserInvocation.page_id,
            ),
        )
        .where(*_reconciliation_invocation_conditions())
    )
    db.rollback()
    return 0 if value is None else int(value)


def claim_next_stale_technical_parser_invocation(
    db: Session,
    *,
    now: datetime | None = None,
    claim_ttl: timedelta = TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL,
) -> TechnicalParserInvocationReconciliationClaim | None:
    """Lease the oldest stale unsettled invocation without replaying it."""

    current = _utc(now)
    if not isinstance(claim_ttl, timedelta) or claim_ttl <= timedelta(0):
        _fail("EXTRACTION_REQUEST_INVALID")
    cutoff = current - claim_ttl
    for _attempt in range(8):
        row = db.execute(
            select(
                TechnicalParserInvocation,
                TechnicalExtractionRun,
                TechnicalExtractionPage,
                TechnicalParserInvocationReceipt,
            )
            .join(
                TechnicalExtractionRun,
                TechnicalExtractionRun.id == TechnicalParserInvocation.run_id,
            )
            .outerjoin(
                TechnicalExtractionPage,
                and_(
                    TechnicalParserInvocation.operation == "page",
                    TechnicalExtractionPage.id == TechnicalParserInvocation.page_id,
                ),
            )
            .outerjoin(
                TechnicalParserInvocationReceipt,
                TechnicalParserInvocationReceipt.invocation_id
                == TechnicalParserInvocation.id,
            )
            .where(
                *_reconciliation_invocation_conditions(),
                TechnicalParserInvocation.created_at <= cutoff,
                or_(
                    TechnicalParserInvocationReceipt.invocation_id.is_(None),
                    TechnicalParserInvocationReceipt.created_at <= cutoff,
                ),
                TechnicalExtractionRun.attempt_started_at <= cutoff,
                or_(
                    TechnicalParserInvocation.operation == "layout",
                    TechnicalExtractionPage.attempt_started_at <= cutoff,
                ),
            )
            .order_by(
                TechnicalParserInvocation.created_at,
                TechnicalParserInvocation.id,
            )
            .limit(1)
            .execution_options(populate_existing=True)
        ).one_or_none()
        if row is None:
            db.rollback()
            return None
        invocation, run, page, persisted_receipt = row
        attestation, _expected_claims = _validated_invocation_runtime_attestation(
            invocation
        )
        terminal_receipt = (
            None
            if persisted_receipt is None
            else _validated_persisted_execution_receipt(
                invocation,
                persisted_receipt,
            )
        )
        prior_run_version = run.record_version
        prior_run_started_at = run.attempt_started_at
        if prior_run_started_at is None:
            db.rollback()
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        try:
            leased_run = db.execute(
                update(TechnicalExtractionRun)
                .where(
                    TechnicalExtractionRun.id == run.id,
                    TechnicalExtractionRun.status == "processing",
                    TechnicalExtractionRun.attempt_token == run.attempt_token,
                    TechnicalExtractionRun.attempt_count == run.attempt_count,
                    TechnicalExtractionRun.record_version == prior_run_version,
                    TechnicalExtractionRun.attempt_started_at == prior_run_started_at,
                    TechnicalExtractionRun.attempt_started_at <= cutoff,
                    (
                        TechnicalExtractionRun.layout_invocation_id.is_(None)
                        if invocation.operation == "layout"
                        else true()
                    ),
                )
                .values(
                    attempt_started_at=current,
                    record_version=TechnicalExtractionRun.record_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        except SQLAlchemyError:
            _rollback(db)
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        if getattr(leased_run, "rowcount", 0) != 1:
            db.rollback()
            continue

        refreshed_run = _claim_from_run(
            run,
            started_at=current,
            record_version=prior_run_version + 1,
        )
        refreshed_page: TechnicalExtractionPageClaim | None = None
        if invocation.operation == "page":
            if (
                page is None
                or page.attempt_started_at is None
                or page.attempt_token is None
                or page.page_schema != _page_schema_for_run(run.run_schema)
            ):
                db.rollback()
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
            prior_page_version = page.record_version
            prior_page_started_at = page.attempt_started_at
            try:
                leased_page = db.execute(
                    update(TechnicalExtractionPage)
                    .where(
                        TechnicalExtractionPage.id == page.id,
                        TechnicalExtractionPage.run_id == run.id,
                        TechnicalExtractionPage.status == "processing",
                        TechnicalExtractionPage.attempt_token == page.attempt_token,
                        TechnicalExtractionPage.attempt_count == page.attempt_count,
                        TechnicalExtractionPage.record_version == prior_page_version,
                        TechnicalExtractionPage.attempt_started_at
                        == prior_page_started_at,
                        TechnicalExtractionPage.attempt_started_at <= cutoff,
                        TechnicalExtractionPage.parser_invocation_id.is_(None),
                    )
                    .values(
                        attempt_started_at=current,
                        record_version=TechnicalExtractionPage.record_version + 1,
                    )
                    .execution_options(synchronize_session=False)
                )
            except SQLAlchemyError:
                _rollback(db)
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
            if getattr(leased_page, "rowcount", 0) != 1:
                db.rollback()
                continue
            refreshed_page = TechnicalExtractionPageClaim(
                run_claim=refreshed_run,
                page_id=page.id,
                record_version=prior_page_version + 1,
                page_number=page.page_number,
                page_count=page.page_count,
                layout_sha256=page.layout_sha256,
                layout_page_width_points=_layout_dimension(
                    page.layout_page_width_points,
                    code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
                ),
                layout_page_height_points=_layout_dimension(
                    page.layout_page_height_points,
                    code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
                ),
                attempt_token=page.attempt_token,
                attempt_started_at=current,
                attempt_count=page.attempt_count,
            )
        elif page is not None:
            db.rollback()
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

        claimed_result = TechnicalParserInvocationReconciliationClaim(
            invocation_id=invocation.id,
            operation=invocation.operation,
            page_number=invocation.page_number,
            invocation_created_at=_as_utc(invocation.created_at),
            run_claim=refreshed_run,
            page_claim=refreshed_page,
            request_sha256=invocation.request_sha256,
            request_size_bytes=invocation.request_size_bytes,
            runtime_attestation=attestation,
            terminal_receipt=terminal_receipt,
            lease_started_at=current,
        )
        _system_audit(
            db,
            action="claim_stale_technical_parser_invocation",
            run_id=run.id,
            previous_value={
                "invocation_id": invocation.id,
                "run_record_version": prior_run_version,
                "page_record_version": (
                    None if page is None else page.record_version
                ),
            },
            new_value={
                "invocation_id": invocation.id,
                "run_record_version": refreshed_run.record_version,
                "page_record_version": (
                    None
                    if refreshed_page is None
                    else refreshed_page.record_version
                ),
                "lease_started_at": current.isoformat(),
            },
            reason="Leased one stale parser invocation for cleanup-only reconciliation",
        )
        _flush(db)
        _commit(db)
        return claimed_result
    _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def _cleanup_proof_datetime_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _validated_reconciliation_cleanup_proof(
    claim: TechnicalParserInvocationReconciliationClaim,
    proof: object,
) -> tuple[dict[str, object], datetime, str | None, str]:
    """Validate a structural OCI cleanup proof without importing the runtime."""

    canonical_json = getattr(proof, "canonical_json", None)
    completed_at = getattr(proof, "completed_at", None)
    sha256 = getattr(proof, "sha256", None)
    if (
        not isinstance(canonical_json, bytes)
        or not canonical_json
        or len(canonical_json) > 64 * 1024
        or not isinstance(completed_at, datetime)
        or completed_at.tzinfo is None
        or not isinstance(sha256, str)
    ):
        _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")
    safe_completed_at = completed_at.astimezone(UTC)
    try:
        payload = json.loads(canonical_json.decode("ascii"))
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
        RecursionError,
    ):
        _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")
    if not isinstance(payload, dict):
        _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")

    attestation = claim.runtime_attestation
    attestation_payload = attestation.as_dict()
    attestation_claims = attestation_payload.get("claims")
    if (
        attestation.schema != TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2
        or not isinstance(attestation_claims, dict)
    ):
        _fail("EXTRACTION_RUNTIME_PROVENANCE_REQUIRED")
    owner_id = _canonical_uuid4(
        attestation_claims.get("controller_owner_id"),
        code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
    )
    daemon_sha256 = _canonical_sha256(
        attestation_claims.get("oci_daemon_identity_sha256"),
        code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
    )
    fence_sha256 = _canonical_sha256(
        attestation_claims.get("execution_fence_sha256"),
        code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
    )
    runtime_profile_sha256 = _canonical_sha256(
        claim.run_claim.runtime_profile_sha256,
        code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
    )
    observed_container_id = getattr(proof, "observed_container_id", None)
    observed_container_state = getattr(proof, "observed_container_state", None)
    if (
        (observed_container_id is None) != (observed_container_state is None)
        or observed_container_id is not None
        and (
            not isinstance(observed_container_id, str)
            or len(observed_container_id) != 64
            or any(character not in _HEX for character in observed_container_id)
        )
        or observed_container_state is not None
        and observed_container_state not in _OCI_CONTAINER_STATES
    ):
        _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")

    expected_payload: dict[str, object] = {
        "cleanup_confirmed": True,
        "completed_at": _cleanup_proof_datetime_text(safe_completed_at),
        "controller_owner_id": owner_id,
        "execution_fence_sha256": fence_sha256,
        "invocation_id": claim.invocation_id,
        "observed_container_id": observed_container_id,
        "observed_container_state": observed_container_state,
        "oci_daemon_identity_sha256": daemon_sha256,
        "runtime_attestation_sha256": attestation.sha256,
        "runtime_profile_sha256": runtime_profile_sha256,
        "schema": _TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    }
    if (
        payload != expected_payload
        or _canonical_payload_bytes(
            payload,
            code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
        )
        != canonical_json
        or hashlib.sha256(canonical_json).hexdigest()
        != _canonical_sha256(
            sha256,
            code="EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID",
        )
        or getattr(proof, "schema", None)
        != _TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA
        or getattr(proof, "invocation_id", None) != claim.invocation_id
        or getattr(proof, "runtime_attestation_sha256", None)
        != attestation.sha256
        or getattr(proof, "controller_owner_id", None) != owner_id
        or getattr(proof, "runtime_profile_sha256", None)
        != runtime_profile_sha256
        or getattr(proof, "oci_daemon_identity_sha256", None) != daemon_sha256
        or getattr(proof, "execution_fence_sha256", None) != fence_sha256
        or getattr(proof, "cleanup_confirmed", None) is not True
    ):
        _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")
    return (
        expected_payload,
        safe_completed_at,
        observed_container_id,
        sha256,
    )


def _reconciliation_outcomes(
    receipt: TechnicalParserExecutionReceipt,
) -> tuple[str, str]:
    if receipt.execution_state == "succeeded":
        suffix = "PARSER_OUTPUT_LOST_AFTER_SUCCESS"
    elif receipt.execution_state == "execution_unknown":
        suffix = "PARSER_EXECUTION_UNKNOWN"
    elif receipt.execution_state == "containment_lost":
        suffix = "PARSER_CONTAINMENT_LOST"
    elif receipt.execution_state == "not_started":
        suffix = "PARSER_NOT_STARTED"
    else:
        suffix = "PARSER_EXECUTION_FAILED"
    return f"EXTRACTION_{suffix}", f"PAGE_{suffix}"


def _reconciliation_page_claim_from_row(
    page: TechnicalExtractionPage,
    *,
    run_claim: TechnicalExtractionRunClaim,
) -> TechnicalExtractionPageClaim:
    if page.attempt_token is None or page.attempt_started_at is None:
        _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")
    return TechnicalExtractionPageClaim(
        run_claim=run_claim,
        page_id=page.id,
        record_version=page.record_version,
        page_number=page.page_number,
        page_count=page.page_count,
        layout_sha256=page.layout_sha256,
        layout_page_width_points=_layout_dimension(
            page.layout_page_width_points,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        layout_page_height_points=_layout_dimension(
            page.layout_page_height_points,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        attempt_token=page.attempt_token,
        attempt_started_at=_as_utc(page.attempt_started_at),
        attempt_count=page.attempt_count,
    )


def _reconciliation_result_if_committed(
    db: Session,
    *,
    claim: TechnicalParserInvocationReconciliationClaim,
    expected_receipt: TechnicalParserExecutionReceipt,
    run_outcome_code: str,
    page_outcome_code: str,
) -> TechnicalParserInvocationReconciliationResult | None:
    invocation = db.get(
        TechnicalParserInvocation,
        claim.invocation_id,
        populate_existing=True,
    )
    persisted_receipt = db.get(
        TechnicalParserInvocationReceipt,
        claim.invocation_id,
        populate_existing=True,
    )
    run = db.get(
        TechnicalExtractionRun,
        claim.run_claim.run_id,
        populate_existing=True,
    )
    if invocation is None or persisted_receipt is None or run is None:
        db.rollback()
        return None
    try:
        receipt = _validated_persisted_execution_receipt(
            invocation,
            persisted_receipt,
        )
    except TechnicalExtractionError:
        db.rollback()
        return None
    if (
        receipt != expected_receipt
        or run.status != "failed"
        or run.attempt_token is not None
        or run.attempt_started_at is not None
        or run.outcome_code != run_outcome_code
        or run.outcome_retryable is not False
        or run.record_version != claim.run_claim.record_version + 1
    ):
        db.rollback()
        return None
    cancelled_count = 0
    preserved_count = 0
    if claim.operation == "layout":
        if (
            claim.page_claim is not None
            or run.page_count is not None
            or db.scalar(
                select(TechnicalExtractionPage.id)
                .where(TechnicalExtractionPage.run_id == run.id)
                .limit(1)
            )
            is not None
        ):
            db.rollback()
            return None
        page_outcome: str | None = None
    else:
        page_claim = claim.page_claim
        page = (
            None
            if page_claim is None
            else db.get(
                TechnicalExtractionPage,
                page_claim.page_id,
                populate_existing=True,
            )
        )
        pages = tuple(
            db.scalars(
                select(TechnicalExtractionPage)
                .where(TechnicalExtractionPage.run_id == run.id)
                .order_by(TechnicalExtractionPage.page_number)
            )
        )
        if (
            page_claim is None
            or page is None
            or page.status != "failed"
            or page.outcome_code != page_outcome_code
            or page.outcome_retryable is not False
            or page.record_version != page_claim.record_version + 1
            or run.page_count is None
            or len(pages) != run.page_count
            or any(
                item.id != page.id
                and (
                    item.status in {"pending", "processing"}
                    or item.status == "failed"
                    and item.outcome_retryable is True
                )
                for item in pages
            )
        ):
            db.rollback()
            return None
        cancelled_count = sum(item.status == "cancelled" for item in pages)
        preserved_count = len(pages) - cancelled_count - 1
        page_outcome = page_outcome_code
    result = TechnicalParserInvocationReconciliationResult(
        invocation_id=claim.invocation_id,
        run_id=claim.run_claim.run_id,
        operation=claim.operation,
        execution_state=receipt.execution_state,
        receipt_sha256=receipt.sha256,
        run_outcome_code=run_outcome_code,
        page_outcome_code=page_outcome,
        cancelled_page_count=cancelled_count,
        preserved_page_count=preserved_count,
        idempotent_replay=True,
    )
    db.rollback()
    return result


def finalize_technical_parser_invocation_reconciliation(
    db: Session,
    *,
    claim: TechnicalParserInvocationReconciliationClaim,
    cleanup_proof: object | None = None,
    now: datetime | None = None,
) -> TechnicalParserInvocationReconciliationResult:
    """Atomically receipt and terminalize one cleanup-proven orphan attempt.

    Receiptless calls must run synchronously from the OCI cleanup callback
    while its cross-process execution fence remains held.
    """

    if (
        not isinstance(claim, TechnicalParserInvocationReconciliationClaim)
        or claim.lease_started_at != claim.run_claim.attempt_started_at
        or (claim.operation == "layout") != (claim.page_claim is None)
        or claim.page_claim is not None
        and (
            claim.page_claim.run_claim != claim.run_claim
            or claim.page_claim.attempt_started_at != claim.lease_started_at
        )
    ):
        _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")
    current = _utc(now)
    expected_receipt: TechnicalParserExecutionReceipt | None = None
    run_outcome_code: str | None = None
    page_outcome_code: str | None = None
    proof_payload: dict[str, object] | None = None
    proof_sha256: str | None = None
    try:
        invocation = db.scalar(
            select(TechnicalParserInvocation)
            .where(TechnicalParserInvocation.id == claim.invocation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if invocation is None:
            _fail("EXTRACTION_INVOCATION_NOT_FOUND")
        attestation, _expected_claims = _validated_invocation_runtime_attestation(
            invocation
        )
        if (
            attestation != claim.runtime_attestation
            or invocation.run_id != claim.run_claim.run_id
            or invocation.operation != claim.operation
            or invocation.page_number != claim.page_number
            or _as_utc(invocation.created_at) != claim.invocation_created_at
            or invocation.request_sha256 != claim.request_sha256
            or invocation.request_size_bytes != claim.request_size_bytes
            or invocation.run_attempt_token != claim.run_claim.attempt_token
            or invocation.run_attempt_count != claim.run_claim.attempt_count
            or invocation.attempt_token
            != (
                claim.run_claim.attempt_token
                if claim.page_claim is None
                else claim.page_claim.attempt_token
            )
            or invocation.attempt_count
            != (
                claim.run_claim.attempt_count
                if claim.page_claim is None
                else claim.page_claim.attempt_count
            )
            or invocation.runtime_attestation_sha256
            != claim.runtime_attestation.sha256
        ):
            _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")

        if cleanup_proof is not None:
            (
                proof_payload,
                cleanup_completed_at,
                observed_container_id,
                proof_sha256,
            ) = _validated_reconciliation_cleanup_proof(claim, cleanup_proof)
            if (
                cleanup_completed_at < claim.lease_started_at
                or cleanup_completed_at > current
            ):
                _fail("EXTRACTION_INVOCATION_CLEANUP_PROOF_INVALID")
        else:
            cleanup_completed_at = None
            observed_container_id = None

        persisted_receipt = db.get(
            TechnicalParserInvocationReceipt,
            claim.invocation_id,
            populate_existing=True,
        )
        if persisted_receipt is not None:
            expected_receipt = _validated_persisted_execution_receipt(
                invocation,
                persisted_receipt,
            )
            if (
                claim.terminal_receipt is not None
                and expected_receipt != claim.terminal_receipt
            ):
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        else:
            if claim.terminal_receipt is not None:
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
            if cleanup_completed_at is None:
                _fail("EXTRACTION_RUNTIME_PROVENANCE_REQUIRED")
            expected_receipt = create_technical_parser_execution_receipt(
                execution_state="execution_unknown",
                operation=claim.operation,
                invocation_id=claim.invocation_id,
                expected_attestation_sha256=claim.runtime_attestation.sha256,
                attestation=claim.runtime_attestation,
                outcome_code=TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
                container_id=observed_container_id,
                started_at=None,
                completed_at=cleanup_completed_at,
                exit_code=None,
                stdout_sha256=None,
                stdout_size_bytes=None,
                cleanup_confirmed=True,
            )
            _stage_technical_parser_invocation_receipt(
                db,
                invocation=invocation,
                receipt=expected_receipt,
                receipt_payload=expected_receipt.as_dict(),
                reconciliation=True,
            )
        if (
            expected_receipt.cleanup_confirmed is not True
            and cleanup_completed_at is None
        ):
            _fail("EXTRACTION_RUNTIME_PROVENANCE_REQUIRED")

        run_outcome_code, page_outcome_code = _reconciliation_outcomes(
            expected_receipt
        )
        run = db.scalar(
            select(TechnicalExtractionRun)
            .where(TechnicalExtractionRun.id == claim.run_claim.run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            run is None
            or _claim_from_run(run) != claim.run_claim
            or run.layout_invocation_id is not None
            and claim.operation == "layout"
        ):
            _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")

        cancelled_count = 0
        preserved_count = 0
        page_outcome: str | None = None
        if claim.operation == "layout":
            if (
                claim.page_claim is not None
                or invocation.page_id is not None
                or run.page_count is not None
                or db.scalar(
                    select(TechnicalExtractionPage.id)
                    .where(TechnicalExtractionPage.run_id == run.id)
                    .limit(1)
                )
                is not None
            ):
                _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")
        else:
            page_claim = claim.page_claim
            if (
                page_claim is None
                or invocation.page_id != page_claim.page_id
                or invocation.page_attempt_token != page_claim.attempt_token
                or invocation.page_attempt_count != page_claim.attempt_count
            ):
                _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")
            pages = tuple(
                db.scalars(
                    select(TechnicalExtractionPage)
                    .where(TechnicalExtractionPage.run_id == run.id)
                    .order_by(TechnicalExtractionPage.page_number)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
            )
            if (
                run.page_count is None
                or len(pages) != run.page_count
                or tuple(page.page_number for page in pages)
                != tuple(range(1, run.page_count + 1))
            ):
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
            active_page = next(
                (page for page in pages if page.id == page_claim.page_id),
                None,
            )
            if (
                active_page is None
                or _reconciliation_page_claim_from_row(
                    active_page,
                    run_claim=claim.run_claim,
                )
                != page_claim
                or active_page.parser_invocation_id is not None
            ):
                _fail("EXTRACTION_INVOCATION_RECONCILIATION_CLAIM_LOST")
            active_page.status = "failed"
            active_page.attempt_token = None
            active_page.attempt_started_at = None
            active_page.outcome_code = page_outcome_code
            active_page.outcome_retryable = False
            active_page.last_outcome_at = current
            active_page.completed_at = current
            active_page.record_version += 1
            page_outcome = page_outcome_code
            for page in pages:
                if page.id == active_page.id:
                    continue
                if page.status == "pending" or (
                    page.status == "failed" and page.outcome_retryable is True
                ):
                    page.status = "cancelled"
                    page.attempt_token = None
                    page.attempt_started_at = None
                    page.outcome_code = "PAGE_EXTRACTION_CANCELLED"
                    page.outcome_retryable = False
                    page.last_outcome_at = current
                    page.completed_at = current
                    page.record_version += 1
                    cancelled_count += 1
                elif page.status in {"completed", "needs_attention"} or (
                    page.status == "failed" and page.outcome_retryable is False
                ):
                    preserved_count += 1
                else:
                    _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

        run.status = "failed"
        run.attempt_token = None
        run.attempt_started_at = None
        run.manifest_sha256 = None
        run.outcome_code = run_outcome_code
        run.outcome_retryable = False
        run.last_outcome_at = current
        run.completed_at = current
        run.record_version += 1
        _system_audit(
            db,
            action="finalize_technical_parser_invocation_reconciliation",
            run_id=run.id,
            previous_value={
                "invocation_id": invocation.id,
                "operation": claim.operation,
                "run_status": "processing",
                "run_record_version": claim.run_claim.record_version,
            },
            new_value={
                "invocation_id": invocation.id,
                "operation": claim.operation,
                "execution_state": expected_receipt.execution_state,
                "receipt_sha256": expected_receipt.sha256,
                "run_status": "failed",
                "run_outcome_code": run_outcome_code,
                "page_outcome_code": page_outcome,
                "cancelled_page_count": cancelled_count,
                "preserved_page_count": preserved_count,
                "cleanup_proof": proof_payload,
                "cleanup_proof_sha256": proof_sha256,
            },
            reason=(
                "Terminalized an orphan parser attempt without replay or output acceptance"
            ),
        )
        _flush(db)
        result = TechnicalParserInvocationReconciliationResult(
            invocation_id=claim.invocation_id,
            run_id=claim.run_claim.run_id,
            operation=claim.operation,
            execution_state=expected_receipt.execution_state,
            receipt_sha256=expected_receipt.sha256,
            run_outcome_code=run_outcome_code,
            page_outcome_code=page_outcome,
            cancelled_page_count=cancelled_count,
            preserved_page_count=preserved_count,
        )
        _commit(db)
        return result
    except TechnicalExtractionError:
        _rollback(db)
        if (
            expected_receipt is not None
            and run_outcome_code is not None
            and page_outcome_code is not None
        ):
            replay = _reconciliation_result_if_committed(
                db,
                claim=claim,
                expected_receipt=expected_receipt,
                run_outcome_code=run_outcome_code,
                page_outcome_code=page_outcome_code,
            )
            if replay is not None:
                return replay
        raise
    except SQLAlchemyError:
        _rollback(db)
        if (
            expected_receipt is not None
            and run_outcome_code is not None
            and page_outcome_code is not None
        ):
            replay = _reconciliation_result_if_committed(
                db,
                claim=claim,
                expected_receipt=expected_receipt,
                run_outcome_code=run_outcome_code,
                page_outcome_code=page_outcome_code,
            )
            if replay is not None:
                return replay
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def claim_next_technical_extraction_run(
    db: Session,
    *,
    now: datetime | None = None,
    claim_ttl: timedelta = TECHNICAL_EXTRACTION_RUN_CLAIM_TTL,
) -> TechnicalExtractionRunClaim | None:
    """CAS-claim the oldest queued or stale run and commit before external work."""

    current = _utc(now)
    if not isinstance(claim_ttl, timedelta) or claim_ttl <= timedelta(0):
        _fail("EXTRACTION_REQUEST_INVALID")
    cutoff = current - claim_ttl
    unsettled_invocation = _unsettled_current_attempt_invocation()
    eligibility = and_(
        or_(
            TechnicalExtractionRun.status == "queued",
            and_(
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_started_at <= cutoff,
            ),
        ),
        ~unsettled_invocation,
    )
    for _attempt in range(8):
        run = db.scalar(
            select(TechnicalExtractionRun)
            .where(eligibility)
            .order_by(
                case((TechnicalExtractionRun.status == "queued", 0), else_=1),
                TechnicalExtractionRun.created_at,
                TechnicalExtractionRun.id,
            )
            .execution_options(populate_existing=True)
        )
        if run is None:
            db.rollback()
            return None
        token = str(uuid4())
        prior_status = run.status
        prior_token = run.attempt_token
        prior_started_at = run.attempt_started_at
        exact_eligibility = (
            and_(
                TechnicalExtractionRun.status == "queued",
                TechnicalExtractionRun.attempt_token.is_(None),
                TechnicalExtractionRun.attempt_started_at.is_(None),
            )
            if prior_status == "queued"
            else and_(
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == prior_token,
                TechnicalExtractionRun.attempt_started_at == prior_started_at,
                TechnicalExtractionRun.attempt_started_at <= cutoff,
            )
        )
        try:
            claimed = db.execute(
                update(TechnicalExtractionRun)
                .where(
                    TechnicalExtractionRun.id == run.id,
                    TechnicalExtractionRun.record_version == run.record_version,
                    exact_eligibility,
                )
                .values(
                    status="processing",
                    attempt_token=token,
                    attempt_started_at=current,
                    attempt_count=TechnicalExtractionRun.attempt_count + 1,
                    outcome_code=None,
                    outcome_retryable=None,
                    last_outcome_at=None,
                    completed_at=None,
                    manifest_sha256=None,
                    record_version=TechnicalExtractionRun.record_version + 1,
                )
                .execution_options(synchronize_session=False)
            )
        except SQLAlchemyError:
            _rollback(db)
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        if getattr(claimed, "rowcount", 0) != 1:
            db.rollback()
            continue
        next_count = run.attempt_count + 1
        next_version = run.record_version + 1
        _system_audit(
            db,
            action="claim_technical_extraction_run",
            run_id=run.id,
            previous_value={
                "status": prior_status,
                "record_version": run.record_version,
                "attempt_count": run.attempt_count,
            },
            new_value={
                "status": "processing",
                "record_version": next_version,
                "attempt_count": next_count,
            },
            reason="Claimed a queued or expired Draft extraction lease",
        )
        _flush(db)
        _commit(db)
        return _claim_from_run(
            run,
            token=token,
            started_at=current,
            record_version=next_version,
            attempt_count=next_count,
        )
    _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def _cas_run_heartbeat(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    now: datetime,
    layout: TechnicalExtractionLayoutBinding | None = None,
    runtime_attestation_sha256: str | None = None,
    layout_invocation_id: str | None = None,
) -> TechnicalExtractionRunClaim:
    values: dict[str, object] = {
        "attempt_started_at": now,
        "record_version": TechnicalExtractionRun.record_version + 1,
    }
    if layout is not None:
        values.update(
            page_count=layout.page_count,
            layout_schema=layout.schema,
            layout_sha256=layout.sha256,
            layout_size_bytes=layout.size_bytes,
            layout_invocation_id=layout_invocation_id,
        )
    if runtime_attestation_sha256 is not None:
        values["runtime_attestation_sha256"] = runtime_attestation_sha256
    try:
        heartbeat = db.execute(
            update(TechnicalExtractionRun)
            .where(
                TechnicalExtractionRun.id == claim.run_id,
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == claim.attempt_token,
                TechnicalExtractionRun.record_version == claim.record_version,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(heartbeat, "rowcount", 0) != 1:
        _rollback(db)
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    return _refreshed_run_claim(
        claim,
        now=now,
        layout=layout,
        runtime_attestation_sha256=runtime_attestation_sha256,
        layout_invocation_id=layout_invocation_id,
    )


def heartbeat_technical_extraction_run(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    now: datetime | None = None,
) -> TechnicalExtractionRunClaim:
    current = _utc(now)
    refreshed = _cas_run_heartbeat(db, claim=claim, now=current)
    _system_audit(
        db,
        action="heartbeat_technical_extraction_run",
        run_id=claim.run_id,
        previous_value={"record_version": claim.record_version},
        new_value={"record_version": refreshed.record_version},
        reason="Renewed the active Draft extraction lease",
    )
    _flush(db)
    _commit(db)
    return refreshed


def _resolve_run_claim(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    status: str,
    outcome_code: str,
    retryable: bool,
    now: datetime,
) -> None:
    try:
        existing_page_id = db.scalar(
            select(TechnicalExtractionPage.id)
            .join(
                TechnicalExtractionRun,
                TechnicalExtractionRun.id == TechnicalExtractionPage.run_id,
            )
            .where(
                TechnicalExtractionPage.run_id == claim.run_id,
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == claim.attempt_token,
                TechnicalExtractionRun.record_version == claim.record_version,
            )
            .limit(1)
        )
        if existing_page_id is not None:
            db.rollback()
            _fail("EXTRACTION_RUN_HAS_PAGES")
        resolved = db.execute(
            update(TechnicalExtractionRun)
            .where(
                TechnicalExtractionRun.id == claim.run_id,
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == claim.attempt_token,
                TechnicalExtractionRun.record_version == claim.record_version,
            )
            .values(
                status=status,
                attempt_token=None,
                attempt_started_at=None,
                outcome_code=outcome_code,
                outcome_retryable=retryable,
                last_outcome_at=now,
                completed_at=now if status == "failed" else None,
                manifest_sha256=None,
                record_version=TechnicalExtractionRun.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(resolved, "rowcount", 0) != 1:
        _rollback(db)
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    _system_audit(
        db,
        action=("retry_technical_extraction_run" if retryable else "fail_technical_extraction_run"),
        run_id=claim.run_id,
        previous_value={
            "status": "processing",
            "record_version": claim.record_version,
            "attempt_count": claim.attempt_count,
        },
        new_value={
            "status": status,
            "record_version": claim.record_version + 1,
            "attempt_count": claim.attempt_count,
            "outcome_code": outcome_code,
            "outcome_retryable": retryable,
        },
        reason=(
            "Released a transient Draft extraction failure for retry"
            if retryable
            else "Recorded a terminal Draft extraction failure"
        ),
    )
    _flush(db)
    _commit(db)


def release_technical_extraction_run_for_retry(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    outcome_code: object,
    now: datetime | None = None,
) -> None:
    code = _outcome(outcome_code, success_codes=_RUN_SUCCESS_CODES)
    _resolve_run_claim(
        db,
        claim=claim,
        status="queued",
        outcome_code=code,
        retryable=True,
        now=_utc(now),
    )


def fail_technical_extraction_run(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    outcome_code: object,
    now: datetime | None = None,
) -> None:
    code = _outcome(outcome_code, success_codes=_RUN_SUCCESS_CODES)
    _resolve_run_claim(
        db,
        claim=claim,
        status="failed",
        outcome_code=code,
        retryable=False,
        now=_utc(now),
    )


def get_claimed_technical_extraction_source_snapshot(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
) -> TechnicalExtractionSourceSnapshot:
    """Read an exact source snapshot, ending the DB transaction before I/O."""

    row = db.execute(
        select(TechnicalExtractionRun, TechnicalDocument, StoredFile)
        .join(
            TechnicalDocument,
            TechnicalDocument.id == TechnicalExtractionRun.technical_document_id,
        )
        .join(StoredFile, StoredFile.id == TechnicalExtractionRun.source_stored_file_id)
        .where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
            TechnicalDocument.id == claim.technical_document_id,
            TechnicalDocument.stored_file_id == claim.source_stored_file_id,
        )
        .execution_options(populate_existing=True)
    ).one_or_none()
    if row is None:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    run, _document, stored = row
    if (
        run.source_sha256 != claim.source_sha256
        or run.source_size_bytes != claim.source_size_bytes
        or stored.sha256 != claim.source_sha256
        or stored.size_bytes != claim.source_size_bytes
    ):
        db.rollback()
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")
    try:
        _source_is_eligible(stored)
    except TechnicalExtractionError:
        db.rollback()
        raise
    snapshot = TechnicalExtractionSourceSnapshot(
        technical_document_id=claim.technical_document_id,
        source_stored_file_id=stored.id,
        source_record_version=stored.record_version,
        original_filename=stored.original_filename,
        media_type=stored.media_type,
        storage_path=stored.storage_path,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        purpose=stored.purpose,
        malware_scan_status=stored.malware_scan_status,
        immutable=stored.immutable,
    )
    db.rollback()
    return snapshot


def confirm_technical_extraction_source_snapshot(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    snapshot: TechnicalExtractionSourceSnapshot,
) -> None:
    """Confirm source state again after hashing/parser work and before attachment."""

    run = db.scalar(
        select(TechnicalExtractionRun).where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
        )
    )
    if run is None:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    document = db.get(TechnicalDocument, claim.technical_document_id)
    stored = db.get(StoredFile, claim.source_stored_file_id)
    if document is None or stored is None:
        db.rollback()
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")
    current = (
        document.id,
        document.stored_file_id,
        stored.id,
        stored.record_version,
        stored.original_filename,
        stored.media_type,
        stored.storage_path,
        stored.sha256,
        stored.size_bytes,
        stored.purpose,
        stored.malware_scan_status,
        stored.immutable,
    )
    expected = (
        snapshot.technical_document_id,
        snapshot.source_stored_file_id,
        snapshot.source_stored_file_id,
        snapshot.source_record_version,
        snapshot.original_filename,
        snapshot.media_type,
        snapshot.storage_path,
        snapshot.sha256,
        snapshot.size_bytes,
        snapshot.purpose,
        snapshot.malware_scan_status,
        snapshot.immutable,
    )
    if (
        current != expected
        or run.technical_document_id != snapshot.technical_document_id
        or run.source_stored_file_id != snapshot.source_stored_file_id
        or run.source_sha256 != snapshot.sha256
        or run.source_size_bytes != snapshot.size_bytes
    ):
        db.rollback()
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")
    try:
        _source_is_eligible(stored)
    except TechnicalExtractionError:
        db.rollback()
        raise
    db.rollback()


def _lock_and_confirm_source_snapshot(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    snapshot: TechnicalExtractionSourceSnapshot,
) -> None:
    if not isinstance(snapshot, TechnicalExtractionSourceSnapshot):
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")
    row = db.execute(
        select(TechnicalExtractionRun, TechnicalDocument, StoredFile)
        .join(
            TechnicalDocument,
            TechnicalDocument.id == TechnicalExtractionRun.technical_document_id,
        )
        .join(StoredFile, StoredFile.id == TechnicalExtractionRun.source_stored_file_id)
        .where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
            TechnicalDocument.id == claim.technical_document_id,
            TechnicalDocument.stored_file_id == claim.source_stored_file_id,
            StoredFile.id == claim.source_stored_file_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if row is None:
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    run, document, stored = row
    current = (
        document.id,
        document.stored_file_id,
        stored.id,
        stored.record_version,
        stored.original_filename,
        stored.media_type,
        stored.storage_path,
        stored.sha256,
        stored.size_bytes,
        stored.purpose,
        stored.malware_scan_status,
        stored.immutable,
    )
    expected = (
        snapshot.technical_document_id,
        snapshot.source_stored_file_id,
        snapshot.source_stored_file_id,
        snapshot.source_record_version,
        snapshot.original_filename,
        snapshot.media_type,
        snapshot.storage_path,
        snapshot.sha256,
        snapshot.size_bytes,
        snapshot.purpose,
        snapshot.malware_scan_status,
        snapshot.immutable,
    )
    if (
        current != expected
        or run.source_sha256 != claim.source_sha256
        or run.source_size_bytes != claim.source_size_bytes
        or snapshot.sha256 != claim.source_sha256
        or snapshot.size_bytes != claim.source_size_bytes
    ):
        _fail("EXTRACTION_SOURCE_BINDING_FAILED")
    _source_is_eligible(stored)


def initialize_technical_extraction_pages(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    layout: object,
    parser_invocation_id: object | None = None,
    now: datetime | None = None,
) -> TechnicalExtractionPageInitialization:
    """Atomically bind one exact validated layout and its contiguous page set."""

    safe_layout = _validated_layout(layout, code="EXTRACTION_LAYOUT_INVALID")
    expected_page_schema = _page_schema_for_run(claim.run_schema)
    safe_invocation_id: str | None = None
    if claim.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA:
        safe_invocation_id = _canonical_uuid4(
            parser_invocation_id,
            code="EXTRACTION_INVOCATION_RECEIPT_INVALID",
        )
        _require_successful_invocation_receipt(
            db,
            claim=claim,
            invocation_id=safe_invocation_id,
            operation="layout",
            page_number=0,
            expected_stdout_sha256=safe_layout.sha256,
            expected_stdout_size_bytes=safe_layout.size_bytes,
        )
    elif parser_invocation_id is not None:
        _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
    page_count = safe_layout.page_count
    current = _utc(now)
    run = db.scalar(
        select(TechnicalExtractionRun)
        .where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
        )
        .execution_options(populate_existing=True)
    )
    if run is None:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == claim.run_id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    if run.page_count is not None and run.page_count != safe_layout.page_count:
        db.rollback()
        _fail("EXTRACTION_PAGE_COUNT_CONFLICT")
    replay = run.page_count is not None
    if replay:
        if (
            run.layout_schema != safe_layout.schema
            or run.layout_sha256 != safe_layout.sha256
            or run.layout_size_bytes != safe_layout.size_bytes
            or run.layout_invocation_id != safe_invocation_id
        ):
            db.rollback()
            _fail("EXTRACTION_LAYOUT_CONFLICT")
        if (
            len(pages) != page_count
            or tuple(page.page_number for page in pages) != tuple(range(1, page_count + 1))
            or any(
                page.page_count != page_count
                or page.layout_sha256 != safe_layout.sha256
                or page.layout_page_width_points != layout_page.width_points
                or page.layout_page_height_points != layout_page.height_points
                or page.page_schema != expected_page_schema
                or page.evidence_schema != TECHNICAL_PAGE_EVIDENCE_SCHEMA
                or page.validator_policy != TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
                for page, layout_page in zip(pages, safe_layout.pages, strict=True)
            )
        ):
            db.rollback()
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    elif pages:
        db.rollback()
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

    refreshed = _cas_run_heartbeat(
        db,
        claim=claim,
        now=current,
        layout=safe_layout,
        layout_invocation_id=safe_invocation_id,
    )
    if not replay:
        pages = tuple(
            TechnicalExtractionPage(
                page_schema=expected_page_schema,
                run_id=claim.run_id,
                page_number=layout_page.page_number,
                page_count=page_count,
                layout_sha256=safe_layout.sha256,
                layout_page_width_points=layout_page.width_points,
                layout_page_height_points=layout_page.height_points,
            )
            for layout_page in safe_layout.pages
        )
        db.add_all(pages)
    _system_audit(
        db,
        action="initialize_technical_extraction_pages",
        run_id=claim.run_id,
        previous_value={
            "page_count": run.page_count,
            "layout_schema": run.layout_schema,
            "layout_sha256": run.layout_sha256,
            "layout_size_bytes": run.layout_size_bytes,
            "record_version": claim.record_version,
        },
        new_value={
            "page_count": page_count,
            "layout_schema": safe_layout.schema,
            "layout_sha256": safe_layout.sha256,
            "layout_size_bytes": safe_layout.size_bytes,
            "layout_invocation_id": safe_invocation_id,
            "record_version": refreshed.record_version,
            "idempotent_replay": replay,
        },
        reason="Bound a contiguous isolated-extraction page set",
    )
    _flush(db)
    _commit(db)
    return TechnicalExtractionPageInitialization(
        run_claim=refreshed,
        page_ids=tuple(page.id for page in pages),
        idempotent_replay=replay,
    )


def claim_technical_extraction_page(
    db: Session,
    *,
    run_claim: TechnicalExtractionRunClaim,
    page_number: object,
    now: datetime | None = None,
    claim_ttl: timedelta = TECHNICAL_EXTRACTION_PAGE_CLAIM_TTL,
) -> TechnicalExtractionPageClaim:
    if (
        not isinstance(page_number, int)
        or isinstance(page_number, bool)
        or run_claim.page_count is None
        or run_claim.layout_schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA
        or run_claim.layout_sha256 is None
        or run_claim.layout_size_bytes is None
        or not 1 <= page_number <= run_claim.page_count
        or not isinstance(claim_ttl, timedelta)
        or claim_ttl <= timedelta(0)
    ):
        _fail("EXTRACTION_PAGE_NOT_FOUND")
    current = _utc(now)
    cutoff = current - claim_ttl
    page = db.scalar(
        select(TechnicalExtractionPage)
        .where(
            TechnicalExtractionPage.run_id == run_claim.run_id,
            TechnicalExtractionPage.page_number == page_number,
            TechnicalExtractionPage.page_count == run_claim.page_count,
        )
        .execution_options(populate_existing=True)
    )
    if page is None:
        db.rollback()
        _fail("EXTRACTION_PAGE_NOT_FOUND")
    unsettled_invocation_id = db.scalar(
        select(TechnicalExtractionRun.id)
        .where(
            TechnicalExtractionRun.id == run_claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == run_claim.attempt_token,
            TechnicalExtractionRun.attempt_count == run_claim.attempt_count,
            _unsettled_current_attempt_invocation(),
        )
        .limit(1)
    )
    if unsettled_invocation_id is not None:
        db.rollback()
        _fail("EXTRACTION_INVOCATION_PENDING")
    if (
        page.layout_sha256 != run_claim.layout_sha256
        or page.page_schema != _page_schema_for_run(run_claim.run_schema)
        or page.parser_invocation_id is not None
        or page.layout_page_width_points is None
        or page.layout_page_height_points is None
    ):
        db.rollback()
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    layout_width = _layout_dimension(
        page.layout_page_width_points,
        code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
    )
    layout_height = _layout_dimension(
        page.layout_page_height_points,
        code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
    )
    other_processing_page_id = db.scalar(
        select(TechnicalExtractionPage.id)
        .where(
            TechnicalExtractionPage.run_id == run_claim.run_id,
            TechnicalExtractionPage.status == "processing",
            TechnicalExtractionPage.id != page.id,
        )
        .order_by(TechnicalExtractionPage.page_number)
    )
    if other_processing_page_id is not None:
        db.rollback()
        _fail("EXTRACTION_PAGE_IN_PROGRESS")

    if page.status == "pending":
        exact_eligibility = and_(
            TechnicalExtractionPage.status == "pending",
            TechnicalExtractionPage.attempt_token.is_(None),
            TechnicalExtractionPage.attempt_started_at.is_(None),
            TechnicalExtractionPage.attempt_count == 0,
        )
    elif page.status == "failed" and page.outcome_retryable is True:
        exact_eligibility = and_(
            TechnicalExtractionPage.status == "failed",
            TechnicalExtractionPage.outcome_retryable.is_(True),
            TechnicalExtractionPage.attempt_token.is_(None),
        )
    elif (
        page.status == "processing"
        and page.attempt_started_at is not None
        and _as_utc(page.attempt_started_at) <= cutoff
    ):
        exact_eligibility = and_(
            TechnicalExtractionPage.status == "processing",
            TechnicalExtractionPage.attempt_token == page.attempt_token,
            TechnicalExtractionPage.attempt_started_at == page.attempt_started_at,
            TechnicalExtractionPage.attempt_started_at <= cutoff,
        )
    elif page.status == "processing":
        db.rollback()
        _fail("EXTRACTION_PAGE_IN_PROGRESS")
    else:
        db.rollback()
        _fail("EXTRACTION_PAGE_NOT_RETRYABLE")

    refreshed_run = _cas_run_heartbeat(db, claim=run_claim, now=current)
    token = str(uuid4())
    try:
        claimed = db.execute(
            update(TechnicalExtractionPage)
            .where(
                TechnicalExtractionPage.id == page.id,
                TechnicalExtractionPage.run_id == run_claim.run_id,
                TechnicalExtractionPage.record_version == page.record_version,
                exact_eligibility,
            )
            .values(
                status="processing",
                attempt_token=token,
                attempt_started_at=current,
                attempt_count=TechnicalExtractionPage.attempt_count + 1,
                outcome_code=None,
                outcome_retryable=None,
                last_outcome_at=None,
                completed_at=None,
                record_version=TechnicalExtractionPage.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except IntegrityError:
        _rollback(db)
        competing_page_id = db.scalar(
            select(TechnicalExtractionPage.id).where(
                TechnicalExtractionPage.run_id == run_claim.run_id,
                TechnicalExtractionPage.status == "processing",
            )
        )
        db.rollback()
        if competing_page_id is not None:
            _fail("EXTRACTION_PAGE_IN_PROGRESS")
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(claimed, "rowcount", 0) != 1:
        db.rollback()
        _fail("EXTRACTION_PAGE_CLAIM_LOST")
    next_count = page.attempt_count + 1
    next_version = page.record_version + 1
    _system_audit(
        db,
        action="claim_technical_extraction_page",
        run_id=run_claim.run_id,
        previous_value={
            "page_id": page.id,
            "page_number": page.page_number,
            "status": page.status,
            "record_version": page.record_version,
            "attempt_count": page.attempt_count,
        },
        new_value={
            "page_id": page.id,
            "page_number": page.page_number,
            "status": "processing",
            "record_version": next_version,
            "attempt_count": next_count,
        },
        reason="Claimed a pending, retryable, or expired extraction page",
    )
    _flush(db)
    _commit(db)
    return TechnicalExtractionPageClaim(
        run_claim=refreshed_run,
        page_id=page.id,
        record_version=next_version,
        page_number=page.page_number,
        page_count=page.page_count,
        layout_sha256=run_claim.layout_sha256,
        layout_page_width_points=layout_width,
        layout_page_height_points=layout_height,
        attempt_token=token,
        attempt_started_at=current,
        attempt_count=next_count,
    )


def heartbeat_technical_extraction_page(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
    now: datetime | None = None,
) -> TechnicalExtractionPageClaim:
    current = _utc(now)
    refreshed_run = _cas_run_heartbeat(
        db,
        claim=claim.run_claim,
        now=current,
    )
    try:
        heartbeat = db.execute(
            update(TechnicalExtractionPage)
            .where(
                TechnicalExtractionPage.id == claim.page_id,
                TechnicalExtractionPage.run_id == claim.run_claim.run_id,
                TechnicalExtractionPage.status == "processing",
                TechnicalExtractionPage.attempt_token == claim.attempt_token,
                TechnicalExtractionPage.record_version == claim.record_version,
            )
            .values(
                attempt_started_at=current,
                record_version=TechnicalExtractionPage.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(heartbeat, "rowcount", 0) != 1:
        db.rollback()
        _fail("EXTRACTION_PAGE_CLAIM_LOST")
    refreshed = replace(
        claim,
        run_claim=refreshed_run,
        record_version=claim.record_version + 1,
        attempt_started_at=current,
    )
    _system_audit(
        db,
        action="heartbeat_technical_extraction_page",
        run_id=claim.run_claim.run_id,
        previous_value={
            "page_id": claim.page_id,
            "record_version": claim.record_version,
        },
        new_value={
            "page_id": claim.page_id,
            "record_version": refreshed.record_version,
        },
        reason="Renewed the active extraction page lease",
    )
    _flush(db)
    _commit(db)
    return refreshed


def fail_technical_extraction_page(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
    outcome_code: object,
    retryable: object,
    now: datetime | None = None,
) -> TechnicalExtractionRunClaim:
    code = _outcome(outcome_code, success_codes=_PAGE_SUCCESS_CODES)
    if not isinstance(retryable, bool):
        _fail("EXTRACTION_REQUEST_INVALID")
    current = _utc(now)
    refreshed_run = _cas_run_heartbeat(
        db,
        claim=claim.run_claim,
        now=current,
    )
    try:
        failed = db.execute(
            update(TechnicalExtractionPage)
            .where(
                TechnicalExtractionPage.id == claim.page_id,
                TechnicalExtractionPage.run_id == claim.run_claim.run_id,
                TechnicalExtractionPage.status == "processing",
                TechnicalExtractionPage.attempt_token == claim.attempt_token,
                TechnicalExtractionPage.record_version == claim.record_version,
            )
            .values(
                status="failed",
                attempt_token=None,
                attempt_started_at=None,
                outcome_code=code,
                outcome_retryable=retryable,
                last_outcome_at=current,
                completed_at=current,
                record_version=TechnicalExtractionPage.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(failed, "rowcount", 0) != 1:
        db.rollback()
        _fail("EXTRACTION_PAGE_CLAIM_LOST")
    _system_audit(
        db,
        action="fail_technical_extraction_page",
        run_id=claim.run_claim.run_id,
        previous_value={
            "page_id": claim.page_id,
            "page_number": claim.page_number,
            "status": "processing",
            "record_version": claim.record_version,
        },
        new_value={
            "page_id": claim.page_id,
            "page_number": claim.page_number,
            "status": "failed",
            "record_version": claim.record_version + 1,
            "outcome_code": code,
            "outcome_retryable": retryable,
        },
        reason="Recorded a stable extraction page failure",
    )
    _flush(db)
    _commit(db)
    return refreshed_run


def abort_technical_extraction_run(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    outcome_code: object,
    now: datetime | None = None,
) -> TechnicalExtractionAbortResult:
    """Fail an initialized run and cancel only its unfinished page work."""

    try:
        code = _outcome(outcome_code, success_codes=_RUN_SUCCESS_CODES)
        current = _utc(now)
        run = db.scalar(
            select(TechnicalExtractionRun)
            .where(
                TechnicalExtractionRun.id == claim.run_id,
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == claim.attempt_token,
                TechnicalExtractionRun.record_version == claim.record_version,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if run is None:
            _fail("EXTRACTION_RUN_CLAIM_LOST")
        if (
            run.page_count is None
            or run.layout_schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA
            or run.layout_sha256 is None
            or run.layout_size_bytes is None
            or claim.page_count != run.page_count
            or claim.layout_schema != run.layout_schema
            or claim.layout_sha256 != run.layout_sha256
            or claim.layout_size_bytes != run.layout_size_bytes
        ):
            _fail("EXTRACTION_RUN_NOT_INITIALIZED")
        pages = tuple(
            db.scalars(
                select(TechnicalExtractionPage)
                .where(TechnicalExtractionPage.run_id == run.id)
                .order_by(TechnicalExtractionPage.page_number)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
        if (
            len(pages) != run.page_count
            or tuple(page.page_number for page in pages) != tuple(range(1, run.page_count + 1))
            or any(
                page.page_count != run.page_count or page.layout_sha256 != run.layout_sha256
                for page in pages
            )
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

        previous_counts: dict[str, int] = {}
        cancelled_count = 0
        preserved_count = 0
        for page in pages:
            previous_counts[page.status] = previous_counts.get(page.status, 0) + 1
            cancellable = page.status in {"pending", "processing"} or (
                page.status == "failed" and page.outcome_retryable is True
            )
            if cancellable:
                page.status = "cancelled"
                page.attempt_token = None
                page.attempt_started_at = None
                page.outcome_code = "PAGE_EXTRACTION_CANCELLED"
                page.outcome_retryable = False
                page.last_outcome_at = current
                page.completed_at = current
                page.record_version += 1
                cancelled_count += 1
            elif page.status in {"completed", "needs_attention"} or (
                page.status == "failed" and page.outcome_retryable is False
            ):
                preserved_count += 1
            else:
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

        run.status = "failed"
        run.attempt_token = None
        run.attempt_started_at = None
        run.manifest_sha256 = None
        run.outcome_code = code
        run.outcome_retryable = False
        run.last_outcome_at = current
        run.completed_at = current
        run.record_version += 1
        _system_audit(
            db,
            action="abort_technical_extraction_run",
            run_id=claim.run_id,
            previous_value={
                "status": "processing",
                "record_version": claim.record_version,
                "page_status_counts": previous_counts,
            },
            new_value={
                "status": "failed",
                "record_version": claim.record_version + 1,
                "outcome_code": code,
                "cancelled_page_count": cancelled_count,
                "preserved_page_count": preserved_count,
            },
            reason="Aborted initialized Draft extraction and cancelled unfinished pages",
        )
        _flush(db)
        _commit(db)
        return TechnicalExtractionAbortResult(
            run_id=claim.run_id,
            status="failed",
            outcome_code=code,
            cancelled_page_count=cancelled_count,
            preserved_page_count=preserved_count,
        )
    except TechnicalExtractionError:
        _rollback(db)
        raise
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


def _known_rollback(code: str) -> Never:
    _fail(code, database_outcome="known_rollback")


def _require_retained_page_binding(
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
) -> None:
    if not isinstance(retained, RetainedTechnicalPageArtifacts):
        _fail("EXTRACTION_ARTIFACT_BINDING_MISMATCH")
    evidence = retained.evidence
    if (
        claim.run_claim.layout_schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA
        or claim.run_claim.layout_sha256 is None
        or claim.layout_sha256 != claim.run_claim.layout_sha256
        or evidence.schema != TECHNICAL_PAGE_EVIDENCE_SCHEMA
        or evidence.validator_policy != TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
        or evidence.technical_document_id != claim.run_claim.technical_document_id
        or evidence.source_sha256 != claim.run_claim.source_sha256
        or evidence.source_size_bytes != claim.run_claim.source_size_bytes
        or evidence.page_number != claim.page_number
        or evidence.page_count != claim.page_count
        or evidence.page_width_points != claim.layout_page_width_points
        or evidence.page_height_points != claim.layout_page_height_points
        or evidence.extraction_policy != claim.run_claim.extraction_policy
        or evidence.extraction_policy_sha256 != claim.run_claim.extraction_policy_sha256
        or evidence.ocr_low_confidence_threshold != claim.run_claim.ocr_low_confidence_threshold
        or evidence.worker_image_digest != claim.run_claim.worker_image_digest
        or retained.packet.run_id != claim.run_claim.run_id
        or retained.page_image.run_id != claim.run_claim.run_id
        or retained.packet.page_number != claim.page_number
        or retained.page_image.page_number != claim.page_number
        or retained.packet.artifact_kind != "page_evidence_json"
        or retained.page_image.artifact_kind != "page_image_png"
        or retained.packet.sha256 != evidence.packet_sha256
        or retained.packet.size_bytes != evidence.packet_size_bytes
        or retained.page_image.sha256 != evidence.image.sha256
        or retained.page_image.size_bytes != evidence.image.size_bytes
        or retained.packet.artifact_id == retained.page_image.artifact_id
    ):
        _fail("EXTRACTION_ARTIFACT_BINDING_MISMATCH")


def _artifact_matches_retained_binding(
    artifact: TechnicalDerivedArtifact,
    binding: TechnicalDerivedArtifactBinding,
) -> bool:
    return (
        artifact.id == binding.artifact_id
        and artifact.artifact_schema == "technical-derived-artifact-v1"
        and artifact.run_id == binding.run_id
        and artifact.page_number == binding.page_number
        and artifact.artifact_kind == binding.artifact_kind
        and artifact.media_type == binding.media_type
        and artifact.sha256 == binding.sha256
        and artifact.size_bytes == binding.size_bytes
        and artifact.storage_path == binding.storage_path
        and artifact.validation_policy == binding.validation_policy
        and artifact.immutable is True
    )


def _page_matches_completed_evidence(
    page: TechnicalExtractionPage,
    *,
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
    evidence: TechnicalPageEvidence,
    parser_invocation_id: str | None,
) -> bool:
    needs_attention = evidence.human_review_required
    expected_status = "needs_attention" if needs_attention else "completed"
    expected_outcome = (
        "PAGE_EXTRACTION_NEEDS_ATTENTION" if needs_attention else "PAGE_EXTRACTION_COMPLETE"
    )
    return (
        page.id == claim.page_id
        and page.run_id == claim.run_claim.run_id
        and page.page_number == claim.page_number
        and page.page_count == claim.page_count
        and page.layout_sha256 == claim.layout_sha256
        and page.layout_page_width_points == claim.layout_page_width_points
        and page.layout_page_height_points == claim.layout_page_height_points
        and page.page_schema == _page_schema_for_run(claim.run_claim.run_schema)
        and page.parser_invocation_id == parser_invocation_id
        and page.evidence_schema == TECHNICAL_PAGE_EVIDENCE_SCHEMA
        and page.validator_policy == TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
        and page.status == expected_status
        and page.attempt_token is None
        and page.attempt_started_at is None
        and page.attempt_count == claim.attempt_count
        and page.outcome_code == expected_outcome
        and page.outcome_retryable is False
        and page.last_outcome_at is not None
        and page.completed_at is not None
        and page.packet_artifact_id == retained.packet.artifact_id
        and page.packet_artifact_kind == retained.packet.artifact_kind
        and page.packet_size_bytes == retained.packet.size_bytes
        and page.page_image_artifact_id == retained.page_image.artifact_id
        and page.page_image_artifact_kind == retained.page_image.artifact_kind
        and page.page_image_size_bytes == retained.page_image.size_bytes
        and page.packet_sha256 == retained.packet.sha256
        and page.page_image_sha256 == retained.page_image.sha256
        and page.binding_sha256 == evidence.binding_sha256
        and page.page_width_points == evidence.page_width_points
        and page.page_height_points == evidence.page_height_points
        and page.image_width_pixels == evidence.image.width_pixels
        and page.image_height_pixels == evidence.image.height_pixels
        and page.extraction_mode == evidence.extraction_mode
        and page.native_block_count == len(evidence.native_text_blocks)
        and page.ocr_block_count == len(evidence.ocr.blocks)
        and page.minimum_ocr_confidence == evidence.ocr.minimum_confidence
        and page.ocr_status == evidence.ocr.status
        and page.ocr_low_confidence_threshold == evidence.ocr_low_confidence_threshold
        and page.human_review_required is needs_attention
    )


def _reconcile_completed_page(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
    evidence: TechnicalPageEvidence | None,
    parser_invocation_id: str | None,
) -> TechnicalExtractionPageCompletion | None:
    """Return an exact committed replay, or prove retained paths unreferenced."""

    _rollback(db)
    try:
        if not isinstance(retained, RetainedTechnicalPageArtifacts):
            _fail(
                "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
                database_outcome="commit_outcome_unknown",
            )
        bindings = retained.bindings
        if len(bindings) != 2 or any(
            not isinstance(binding.artifact_id, str)
            or not isinstance(binding.storage_path, str)
            or not binding.artifact_id
            or not binding.storage_path
            for binding in bindings
        ):
            _fail(
                "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
                database_outcome="commit_outcome_unknown",
            )
        artifact_ids = tuple(binding.artifact_id for binding in bindings)
        storage_paths = tuple(binding.storage_path for binding in bindings)
        artifacts = tuple(
            db.scalars(
                select(TechnicalDerivedArtifact)
                .where(
                    or_(
                        TechnicalDerivedArtifact.id.in_(artifact_ids),
                        TechnicalDerivedArtifact.storage_path.in_(storage_paths),
                    )
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
        )
        page_references = tuple(
            db.scalars(
                select(TechnicalExtractionPage)
                .where(
                    or_(
                        TechnicalExtractionPage.packet_artifact_id.in_(artifact_ids),
                        TechnicalExtractionPage.page_image_artifact_id.in_(artifact_ids),
                    )
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
        )
        if not artifacts and not page_references:
            db.rollback()
            return None
        if evidence is None or len(artifacts) != 2 or len(page_references) != 1:
            db.rollback()
            _fail(
                "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
                database_outcome="commit_outcome_unknown",
            )
        artifacts_by_id = {artifact.id: artifact for artifact in artifacts}
        exact_artifacts = len(artifacts_by_id) == 2 and all(
            binding.artifact_id in artifacts_by_id
            and _artifact_matches_retained_binding(
                artifacts_by_id[binding.artifact_id],
                binding,
            )
            for binding in bindings
        )
        page = page_references[0]
        with db.no_autoflush:
            run = db.get(
                TechnicalExtractionRun,
                claim.run_claim.run_id,
                populate_existing=True,
            )
        processing_page_id = db.scalar(
            select(TechnicalExtractionPage.id)
            .where(
                TechnicalExtractionPage.run_id == claim.run_claim.run_id,
                TechnicalExtractionPage.status == "processing",
            )
            .execution_options(autoflush=False)
        )
        if (
            not exact_artifacts
            or not _page_matches_completed_evidence(
                page,
                claim=claim,
                retained=retained,
                evidence=evidence,
                parser_invocation_id=parser_invocation_id,
            )
            or run is None
            or run.technical_document_id != claim.run_claim.technical_document_id
            or run.source_stored_file_id != claim.run_claim.source_stored_file_id
            or run.source_sha256 != claim.run_claim.source_sha256
            or run.source_size_bytes != claim.run_claim.source_size_bytes
            or run.extraction_policy != claim.run_claim.extraction_policy
            or run.extraction_policy_sha256 != claim.run_claim.extraction_policy_sha256
            or run.ocr_low_confidence_threshold != claim.run_claim.ocr_low_confidence_threshold
            or run.worker_image_digest != claim.run_claim.worker_image_digest
            or run.page_count != claim.page_count
            or run.layout_schema != claim.run_claim.layout_schema
            or run.layout_sha256 != claim.layout_sha256
            or run.layout_size_bytes != claim.run_claim.layout_size_bytes
            or run.status != "processing"
            or run.attempt_token != claim.run_claim.attempt_token
            or run.record_version != claim.run_claim.record_version + 1
            or processing_page_id is not None
        ):
            db.rollback()
            _fail(
                "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
                database_outcome="commit_outcome_unknown",
            )
        refreshed_run = _claim_from_run(run)
        status = "needs_attention" if evidence.human_review_required else "completed"
        outcome_code = (
            "PAGE_EXTRACTION_NEEDS_ATTENTION"
            if evidence.human_review_required
            else "PAGE_EXTRACTION_COMPLETE"
        )
        db.rollback()
        return TechnicalExtractionPageCompletion(
            run_claim=refreshed_run,
            page_id=claim.page_id,
            status=status,
            outcome_code=outcome_code,
            idempotent_replay=True,
        )
    except TechnicalExtractionError:
        _rollback(db)
        raise
    except SQLAlchemyError:
        _rollback(db)
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )
    except (AttributeError, TypeError, ValueError):
        _rollback(db)
        _fail(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )


def _known_rollback_or_reconcile(
    db: Session,
    *,
    code: str,
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
    evidence: TechnicalPageEvidence | None,
    parser_invocation_id: str | None,
) -> TechnicalExtractionPageCompletion:
    replay = _reconcile_completed_page(
        db,
        claim=claim,
        retained=retained,
        evidence=evidence,
        parser_invocation_id=parser_invocation_id,
    )
    if replay is not None:
        return replay
    _known_rollback(code)


def complete_technical_extraction_page(
    db: Session,
    *,
    claim: TechnicalExtractionPageClaim,
    retained: RetainedTechnicalPageArtifacts,
    storage_root: Path,
    extraction_policy_bytes: bytes,
    source_snapshot: TechnicalExtractionSourceSnapshot,
    parser_invocation_id: object | None = None,
    parser_output: object | None = None,
    now: datetime | None = None,
) -> TechnicalExtractionPageCompletion:
    """Atomically attach exact validated retained bytes to a live page claim.

    Byte verification happens before the transaction. On failure, the error's
    database_outcome says whether retained-byte compensation is safe.
    """

    evidence: TechnicalPageEvidence | None = None
    safe_parser_invocation_id: str | None = None
    parser_frame: TechnicalParserPageSuccessFrame | None = None
    try:
        _require_retained_page_binding(claim, retained)
        if claim.run_claim.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA:
            safe_parser_invocation_id = _canonical_uuid4(
                parser_invocation_id,
                code="EXTRACTION_INVOCATION_RECEIPT_INVALID",
            )
            if not isinstance(parser_output, bytes):
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
            parsed_frame = parse_technical_parser_page_frame(
                parser_output,
                expected_page_number=claim.page_number,
                expected_page_count=claim.page_count,
                expected_page_width_points=claim.layout_page_width_points,
                expected_page_height_points=claim.layout_page_height_points,
            )
            if not isinstance(parsed_frame, TechnicalParserPageSuccessFrame):
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
            parser_frame = parsed_frame
        elif parser_invocation_id is not None or parser_output is not None:
            _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        current = _utc(now)
        with open_verified_technical_derived_artifact(
            retained.packet,
            storage_root=storage_root,
        ) as packet_stream:
            packet_bytes = b"".join(packet_stream)
        with open_verified_technical_derived_artifact(
            retained.page_image,
            storage_root=storage_root,
        ) as image_stream:
            image_bytes = b"".join(image_stream)
        if parser_frame is not None and (
            parser_frame.evidence_bytes != packet_bytes
            or parser_frame.image_bytes != image_bytes
        ):
            _fail("EXTRACTION_ARTIFACT_BINDING_MISMATCH")
        evidence = parse_technical_page_evidence(
            packet_bytes,
            page_image_bytes=image_bytes,
            expected_technical_document_id=claim.run_claim.technical_document_id,
            expected_source_sha256=claim.run_claim.source_sha256,
            expected_source_size_bytes=claim.run_claim.source_size_bytes,
            expected_page_number=claim.page_number,
            expected_page_count=claim.page_count,
            expected_page_width_points=claim.layout_page_width_points,
            expected_page_height_points=claim.layout_page_height_points,
            expected_page_image_sha256=retained.page_image.sha256,
            expected_page_image_size_bytes=retained.page_image.size_bytes,
            expected_page_image_width_pixels=retained.evidence.image.width_pixels,
            expected_page_image_height_pixels=retained.evidence.image.height_pixels,
            expected_extraction_policy=claim.run_claim.extraction_policy,
            expected_extraction_policy_bytes=extraction_policy_bytes,
            expected_extraction_policy_sha256=(claim.run_claim.extraction_policy_sha256),
            expected_worker_image_digest=claim.run_claim.worker_image_digest,
            expected_ocr_low_confidence_threshold=(claim.run_claim.ocr_low_confidence_threshold),
        )
        if evidence != retained.evidence:
            _fail("EXTRACTION_ARTIFACT_BINDING_MISMATCH")
        packet_row, image_row = build_unflushed_technical_derived_artifact_rows(retained)
    except TechnicalExtractionError as exc:
        return _known_rollback_or_reconcile(
            db,
            code=exc.code,
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    except SQLAlchemyError:
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    except (
        TechnicalExtractionArtifactError,
        TechnicalPageEvidenceError,
        TechnicalParserProtocolError,
    ):
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_ARTIFACT_BINDING_MISMATCH",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    except (AttributeError, TypeError, ValueError):
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_ARTIFACT_BINDING_MISMATCH",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )

    try:
        _lock_and_confirm_source_snapshot(
            db,
            claim=claim.run_claim,
            snapshot=source_snapshot,
        )
        if safe_parser_invocation_id is not None:
            if not isinstance(parser_output, bytes):
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
            _require_successful_invocation_receipt(
                db,
                claim=claim.run_claim,
                page_claim=claim,
                invocation_id=safe_parser_invocation_id,
                operation="page",
                page_number=claim.page_number,
                expected_stdout_sha256=hashlib.sha256(parser_output).hexdigest(),
                expected_stdout_size_bytes=len(parser_output),
            )
        refreshed_run = _cas_run_heartbeat(
            db,
            claim=claim.run_claim,
            now=current,
        )
    except TechnicalExtractionError as exc:
        return _known_rollback_or_reconcile(
            db,
            code=exc.code,
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    except SQLAlchemyError:
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    try:
        db.add_all([packet_row, image_row])
        db.flush()
    except SQLAlchemyError:
        _rollback(db)
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )

    needs_attention = evidence.human_review_required
    status = "needs_attention" if needs_attention else "completed"
    outcome_code = (
        "PAGE_EXTRACTION_NEEDS_ATTENTION" if needs_attention else "PAGE_EXTRACTION_COMPLETE"
    )
    try:
        completed = db.execute(
            update(TechnicalExtractionPage)
            .where(
                TechnicalExtractionPage.id == claim.page_id,
                TechnicalExtractionPage.run_id == claim.run_claim.run_id,
                TechnicalExtractionPage.page_number == claim.page_number,
                TechnicalExtractionPage.page_count == claim.page_count,
                TechnicalExtractionPage.layout_sha256 == claim.layout_sha256,
                TechnicalExtractionPage.layout_page_width_points == claim.layout_page_width_points,
                TechnicalExtractionPage.layout_page_height_points
                == claim.layout_page_height_points,
                TechnicalExtractionPage.status == "processing",
                TechnicalExtractionPage.attempt_token == claim.attempt_token,
                TechnicalExtractionPage.record_version == claim.record_version,
            )
            .values(
                status=status,
                parser_invocation_id=safe_parser_invocation_id,
                attempt_token=None,
                attempt_started_at=None,
                outcome_code=outcome_code,
                outcome_retryable=False,
                last_outcome_at=current,
                completed_at=current,
                packet_artifact_id=packet_row.id,
                packet_artifact_kind=packet_row.artifact_kind,
                packet_size_bytes=packet_row.size_bytes,
                page_image_artifact_id=image_row.id,
                page_image_artifact_kind=image_row.artifact_kind,
                page_image_size_bytes=image_row.size_bytes,
                packet_sha256=packet_row.sha256,
                page_image_sha256=image_row.sha256,
                binding_sha256=evidence.binding_sha256,
                page_width_points=evidence.page_width_points,
                page_height_points=evidence.page_height_points,
                image_width_pixels=evidence.image.width_pixels,
                image_height_pixels=evidence.image.height_pixels,
                extraction_mode=evidence.extraction_mode,
                native_block_count=len(evidence.native_text_blocks),
                ocr_block_count=len(evidence.ocr.blocks),
                minimum_ocr_confidence=evidence.ocr.minimum_confidence,
                ocr_status=evidence.ocr.status,
                ocr_low_confidence_threshold=evidence.ocr_low_confidence_threshold,
                human_review_required=needs_attention,
                record_version=TechnicalExtractionPage.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    if getattr(completed, "rowcount", 0) != 1:
        db.rollback()
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_PAGE_CLAIM_LOST",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    try:
        _system_audit(
            db,
            action="complete_technical_extraction_page",
            run_id=claim.run_claim.run_id,
            previous_value={
                "page_id": claim.page_id,
                "page_number": claim.page_number,
                "status": "processing",
                "record_version": claim.record_version,
            },
            new_value={
                "page_id": claim.page_id,
                "page_number": claim.page_number,
                "status": status,
                "record_version": claim.record_version + 1,
                "outcome_code": outcome_code,
                "packet_artifact_id": packet_row.id,
                "page_image_artifact_id": image_row.id,
                "binding_sha256": evidence.binding_sha256,
                "parser_invocation_id": safe_parser_invocation_id,
            },
            reason="Attached exact validator-approved retained page evidence",
        )
        db.flush()
    except SQLAlchemyError:
        _rollback(db)
        return _known_rollback_or_reconcile(
            db,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            claim=claim,
            retained=retained,
            evidence=evidence,
            parser_invocation_id=safe_parser_invocation_id,
        )
    _commit(db)
    return TechnicalExtractionPageCompletion(
        run_claim=refreshed_run,
        page_id=claim.page_id,
        status=status,
        outcome_code=outcome_code,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return format(value, "f") if isinstance(value, Decimal) else None


def _artifact_manifest_value(
    artifact: TechnicalDerivedArtifact,
    *,
    artifact_storage_root: Path | None,
    run_id: str,
    page_number: int,
    kind: str,
    sha256: str,
    size_bytes: int,
) -> dict[str, object]:
    if (
        artifact.run_id != run_id
        or artifact.page_number != page_number
        or artifact.artifact_kind != kind
        or artifact.sha256 != sha256
        or artifact.size_bytes != size_bytes
        or artifact.validation_policy != TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
        or artifact.immutable is not True
        or (kind == "page_evidence_json" and artifact.media_type != "application/json")
        or (kind == "page_image_png" and artifact.media_type != "image/png")
    ):
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if artifact_storage_root is not None:
        try:
            with open_verified_technical_derived_artifact(
                artifact,
                storage_root=artifact_storage_root,
            ):
                pass
        except TechnicalExtractionArtifactError:
            _fail("EXTRACTION_ARTIFACT_BINDING_MISMATCH")
    return {
        "artifact_id": _canonical_uuid4(
            artifact.id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "artifact_kind": kind,
        "immutable": True,
        "media_type": artifact.media_type,
        "sha256": _canonical_sha256(
            artifact.sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "size_bytes": artifact.size_bytes,
        "storage_path_sha256": hashlib.sha256(artifact.storage_path.encode("utf-8")).hexdigest(),
        "validation_policy": artifact.validation_policy,
    }


def _manifest_for_run(
    db: Session,
    run: TechnicalExtractionRun,
    *,
    artifact_storage_root: Path | None = None,
) -> TechnicalExtractionManifest:
    legacy = run.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA_V1
    current = run.run_schema == TECHNICAL_EXTRACTION_RUN_SCHEMA
    if (
        run.page_count is None
        or not 1 <= run.page_count <= TECHNICAL_PAGE_EVIDENCE_MAX_PAGES
        or not (legacy or current)
        or run.page_evidence_schema != TECHNICAL_PAGE_EVIDENCE_SCHEMA
        or run.layout_schema != TECHNICAL_EXTRACTION_LAYOUT_SCHEMA
        or run.layout_sha256 is None
        or run.layout_size_bytes is None
        or not 1 <= run.layout_size_bytes <= TECHNICAL_EXTRACTION_LAYOUT_MAX_BYTES
    ):
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if legacy:
        if any(
            value is not None
            for value in (
                run.runtime_profile_sha256,
                run.runtime_attestation_sha256,
                run.layout_invocation_id,
            )
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        manifest_schema = TECHNICAL_EXTRACTION_MANIFEST_SCHEMA_V1
        expected_page_schema = TECHNICAL_EXTRACTION_PAGE_SCHEMA_V1
    else:
        runtime_profile_sha256 = _canonical_sha256(
            run.runtime_profile_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        )
        runtime_attestation_sha256 = _canonical_sha256(
            run.runtime_attestation_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        )
        layout_invocation_id = _canonical_uuid4(
            run.layout_invocation_id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        )
        manifest_schema = TECHNICAL_EXTRACTION_MANIFEST_SCHEMA
        expected_page_schema = TECHNICAL_EXTRACTION_PAGE_SCHEMA
    layout_sha256 = _canonical_sha256(
        run.layout_sha256,
        code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
    )
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run.id)
            .order_by(TechnicalExtractionPage.page_number)
        )
    )
    artifacts = tuple(
        db.scalars(
            select(TechnicalDerivedArtifact)
            .where(TechnicalDerivedArtifact.run_id == run.id)
            .order_by(
                TechnicalDerivedArtifact.page_number,
                TechnicalDerivedArtifact.artifact_kind,
            )
        )
    )
    if (
        len(pages) != run.page_count
        or tuple(page.page_number for page in pages) != tuple(range(1, run.page_count + 1))
        or len(artifacts) != run.page_count * 2
    ):
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    artifacts_by_id = {artifact.id: artifact for artifact in artifacts}
    pages_by_id = {page.id: page for page in pages}
    if (
        len(artifacts_by_id) != len(artifacts)
        or len(pages_by_id) != len(pages)
    ):
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

    page_values: list[dict[str, object]] = []
    for page in pages:
        expected_code = (
            "PAGE_EXTRACTION_COMPLETE"
            if page.status == "completed"
            else "PAGE_EXTRACTION_NEEDS_ATTENTION"
        )
        if (
            page.status not in {"completed", "needs_attention"}
            or page.page_count != run.page_count
            or page.layout_sha256 != layout_sha256
            or page.layout_page_width_points is None
            or page.layout_page_height_points is None
            or page.page_schema != expected_page_schema
            or page.evidence_schema != TECHNICAL_PAGE_EVIDENCE_SCHEMA
            or page.validator_policy != TECHNICAL_PAGE_EVIDENCE_VALIDATOR_POLICY
            or page.outcome_code != expected_code
            or page.outcome_retryable is not False
            or page.last_outcome_at is None
            or page.completed_at is None
            or page.packet_artifact_id not in artifacts_by_id
            or page.page_image_artifact_id not in artifacts_by_id
            or page.packet_sha256 is None
            or page.packet_size_bytes is None
            or page.page_image_sha256 is None
            or page.page_image_size_bytes is None
            or page.binding_sha256 is None
            or page.human_review_required is not (page.status == "needs_attention")
            or page.ocr_low_confidence_threshold != run.ocr_low_confidence_threshold
            or page.page_width_points != page.layout_page_width_points
            or page.page_height_points != page.layout_page_height_points
            or (current and page.parser_invocation_id is None)
            or (legacy and page.parser_invocation_id is not None)
        ):
            _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
        packet = _artifact_manifest_value(
            artifacts_by_id[page.packet_artifact_id],
            artifact_storage_root=artifact_storage_root,
            run_id=run.id,
            page_number=page.page_number,
            kind="page_evidence_json",
            sha256=page.packet_sha256,
            size_bytes=page.packet_size_bytes,
        )
        image = _artifact_manifest_value(
            artifacts_by_id[page.page_image_artifact_id],
            artifact_storage_root=artifact_storage_root,
            run_id=run.id,
            page_number=page.page_number,
            kind="page_image_png",
            sha256=page.page_image_sha256,
            size_bytes=page.page_image_size_bytes,
        )
        page_value: dict[str, object] = {
            "binding_sha256": _canonical_sha256(
                page.binding_sha256,
                code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            ),
            "extraction_mode": page.extraction_mode,
            "human_review_required": page.human_review_required,
            "image_height_pixels": page.image_height_pixels,
            "image_width_pixels": page.image_width_pixels,
            "layout_page_height_points": _decimal_text(page.layout_page_height_points),
            "layout_page_width_points": _decimal_text(page.layout_page_width_points),
            "layout_sha256": layout_sha256,
            "minimum_ocr_confidence": _decimal_text(page.minimum_ocr_confidence),
            "native_block_count": page.native_block_count,
            "ocr_block_count": page.ocr_block_count,
            "ocr_low_confidence_threshold": _decimal_text(page.ocr_low_confidence_threshold),
            "ocr_status": page.ocr_status,
            "outcome_code": page.outcome_code,
            "packet_artifact": packet,
            "page_height_points": _decimal_text(page.page_height_points),
            "page_image_artifact": image,
            "page_number": page.page_number,
            "page_width_points": _decimal_text(page.page_width_points),
            "status": page.status,
        }
        if current:
            page_value["parser_invocation_id"] = _canonical_uuid4(
                page.parser_invocation_id,
                code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            )
        page_values.append(page_value)

    payload = {
        "extraction_policy": run.extraction_policy,
        "extraction_policy_sha256": _canonical_sha256(
            run.extraction_policy_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "layout_schema": run.layout_schema,
        "layout_sha256": layout_sha256,
        "layout_size_bytes": run.layout_size_bytes,
        "ocr_low_confidence_threshold": _decimal_text(
            _ocr_threshold(
                run.ocr_low_confidence_threshold,
                code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
            )
        ),
        "page_count": run.page_count,
        "page_evidence_schema": run.page_evidence_schema,
        "pages": page_values,
        "run_id": _canonical_uuid4(
            run.id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "schema": manifest_schema,
        "source_sha256": _canonical_sha256(
            run.source_sha256,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "source_size_bytes": run.source_size_bytes,
        "source_stored_file_id": _canonical_uuid4(
            run.source_stored_file_id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "technical_document_id": _canonical_uuid4(
            run.technical_document_id,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
        "worker_image_digest": _canonical_sha256(
            run.worker_image_digest,
            code="EXTRACTION_RUN_PERSISTENCE_CONFLICT",
        ),
    }
    if current:
        invocations = tuple(
            db.scalars(
                select(TechnicalParserInvocation)
                .where(TechnicalParserInvocation.run_id == run.id)
                .order_by(
                    TechnicalParserInvocation.run_attempt_count,
                    TechnicalParserInvocation.operation,
                    TechnicalParserInvocation.page_number,
                    TechnicalParserInvocation.attempt_count,
                    TechnicalParserInvocation.id,
                )
            )
        )
        receipts = tuple(
            db.scalars(
                select(TechnicalParserInvocationReceipt)
                .where(TechnicalParserInvocationReceipt.run_id == run.id)
                .order_by(TechnicalParserInvocationReceipt.invocation_id)
            )
        )
        receipts_by_id = {receipt.invocation_id: receipt for receipt in receipts}
        if (
            not invocations
            or len(receipts_by_id) != len(receipts)
            or len(invocations) != len(receipts)
        ):
            _fail("EXTRACTION_INVOCATION_PENDING")
        invocation_values: list[dict[str, object]] = []
        invocations_by_id: dict[str, TechnicalParserInvocation] = {}
        expected_layout_request = encode_technical_parser_layout_request(
            technical_document_id=run.technical_document_id,
            source_sha256=run.source_sha256,
            source_size_bytes=run.source_size_bytes,
            extraction_policy=run.extraction_policy,
            extraction_policy_sha256=run.extraction_policy_sha256,
            worker_image_digest=run.worker_image_digest,
            ocr_low_confidence_threshold=run.ocr_low_confidence_threshold,
        )
        for invocation in invocations:
            receipt = receipts_by_id.get(invocation.id)
            if receipt is None:
                _fail("EXTRACTION_INVOCATION_PENDING")
            validated_receipt = _validated_persisted_execution_receipt(
                invocation,
                receipt,
            )
            if invocation.operation == "layout":
                expected_request = expected_layout_request
            else:
                invocation_page = pages_by_id.get(invocation.page_id or "")
                if (
                    invocation_page is None
                    or invocation_page.layout_page_width_points is None
                    or invocation_page.layout_page_height_points is None
                ):
                    _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
                expected_request = encode_technical_parser_request(
                    technical_document_id=run.technical_document_id,
                    source_sha256=run.source_sha256,
                    source_size_bytes=run.source_size_bytes,
                    page_number=invocation_page.page_number,
                    page_count=invocation_page.page_count,
                    page_width_points=invocation_page.layout_page_width_points,
                    page_height_points=invocation_page.layout_page_height_points,
                    layout_sha256=invocation_page.layout_sha256,
                    extraction_policy=run.extraction_policy,
                    extraction_policy_sha256=run.extraction_policy_sha256,
                    worker_image_digest=run.worker_image_digest,
                    ocr_low_confidence_threshold=run.ocr_low_confidence_threshold,
                )
            if (
                invocation.runtime_profile_sha256 != runtime_profile_sha256
                or invocation.worker_image_digest != run.worker_image_digest
                or invocation.runtime_attestation_sha256
                != runtime_attestation_sha256
                or receipt.run_id != run.id
                or receipt.operation != invocation.operation
                or receipt.page_number != invocation.page_number
                or receipt.request_sha256 != invocation.request_sha256
                or receipt.runtime_attestation_sha256
                != runtime_attestation_sha256
                or invocation.request_sha256
                != hashlib.sha256(expected_request).hexdigest()
                or invocation.request_size_bytes != len(expected_request)
            ):
                _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
            invocations_by_id[invocation.id] = invocation
            invocation_values.append(
                {
                    "attempt_count": invocation.attempt_count,
                    "attempt_token": invocation.attempt_token,
                    "invocation_id": invocation.id,
                    "operation": invocation.operation,
                    "page_attempt_count": invocation.page_attempt_count,
                    "page_attempt_token": invocation.page_attempt_token,
                    "page_id": invocation.page_id,
                    "page_number": invocation.page_number,
                    "request_sha256": invocation.request_sha256,
                    "request_size_bytes": invocation.request_size_bytes,
                    "run_attempt_count": invocation.run_attempt_count,
                    "run_attempt_token": invocation.run_attempt_token,
                    "runtime_attestation_sha256": runtime_attestation_sha256,
                    "terminal_receipt": validated_receipt.as_dict(),
                    "terminal_receipt_sha256": receipt.receipt_sha256,
                }
            )
        layout_invocation = invocations_by_id.get(layout_invocation_id)
        layout_receipt = receipts_by_id.get(layout_invocation_id)
        if (
            layout_invocation is None
            or layout_receipt is None
            or layout_invocation.operation != "layout"
            or layout_invocation.page_number != 0
            or layout_receipt.execution_state != "succeeded"
            or layout_receipt.cleanup_confirmed is not True
            or layout_receipt.stdout_sha256 != layout_sha256
            or layout_receipt.stdout_size_bytes != run.layout_size_bytes
        ):
            _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        for page in pages:
            page_invocation = invocations_by_id.get(page.parser_invocation_id or "")
            page_receipt = receipts_by_id.get(page.parser_invocation_id or "")
            if (
                page_invocation is None
                or page_receipt is None
                or page_invocation.operation != "page"
                or page_invocation.page_id != page.id
                or page_invocation.page_number != page.page_number
                or page_invocation.attempt_count != page.attempt_count
                or page_invocation.page_attempt_count != page.attempt_count
                or page_receipt.execution_state != "succeeded"
                or page_receipt.cleanup_confirmed is not True
            ):
                _fail("EXTRACTION_INVOCATION_RECEIPT_INVALID")
        payload.update(
            {
                "invocations": invocation_values,
                "layout_invocation_id": layout_invocation_id,
                "runtime_attestation": invocations[0].runtime_attestation_json,
                "runtime_attestation_sha256": runtime_attestation_sha256,
                "runtime_profile_sha256": runtime_profile_sha256,
            }
        )
    canonical = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return TechnicalExtractionManifest(
        schema=manifest_schema,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def reconstruct_technical_extraction_manifest(
    db: Session,
    *,
    run_id: object,
) -> TechnicalExtractionManifest:
    """Reconstruct the metadata manifest without claiming byte availability."""

    safe_run_id = _canonical_uuid4(
        run_id,
        code="EXTRACTION_RUN_NOT_FOUND",
    )
    run = db.get(TechnicalExtractionRun, safe_run_id)
    if run is None:
        _fail("EXTRACTION_RUN_NOT_FOUND")
    return _manifest_for_run(db, run)


def verify_technical_extraction_manifest(
    db: Session,
    *,
    run_id: object,
    artifact_storage_root: Path,
) -> TechnicalExtractionManifest:
    safe_run_id = _canonical_uuid4(
        run_id,
        code="EXTRACTION_RUN_NOT_FOUND",
    )
    run = db.get(TechnicalExtractionRun, safe_run_id)
    if run is None:
        _fail("EXTRACTION_RUN_NOT_FOUND")
    if run.status not in {"completed", "completed_with_attention"} or run.manifest_sha256 is None:
        _fail("EXTRACTION_AGGREGATION_NOT_READY")
    manifest = _manifest_for_run(
        db,
        run,
        artifact_storage_root=artifact_storage_root,
    )
    if manifest.sha256 != run.manifest_sha256:
        _fail("EXTRACTION_MANIFEST_MISMATCH")
    return manifest


def _aggregate_technical_extraction_run(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    source_snapshot: TechnicalExtractionSourceSnapshot,
    artifact_storage_root: Path,
    now: datetime | None = None,
) -> TechnicalExtractionAggregateResult:
    """CAS-finalize a run from its exact terminal page set."""

    current = _utc(now)
    _lock_and_confirm_source_snapshot(
        db,
        claim=claim,
        snapshot=source_snapshot,
    )
    run = db.scalar(
        select(TechnicalExtractionRun)
        .where(
            TechnicalExtractionRun.id == claim.run_id,
            TechnicalExtractionRun.status == "processing",
            TechnicalExtractionRun.attempt_token == claim.attempt_token,
            TechnicalExtractionRun.record_version == claim.record_version,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if run is None:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    if run.page_count is None or run.page_count != claim.page_count:
        db.rollback()
        _fail("EXTRACTION_PAGE_COUNT_CONFLICT")
    pages = tuple(
        db.scalars(
            select(TechnicalExtractionPage)
            .where(TechnicalExtractionPage.run_id == run.id)
            .order_by(TechnicalExtractionPage.page_number)
            .with_for_update()
        )
    )
    if len(pages) != run.page_count or tuple(page.page_number for page in pages) != tuple(
        range(1, run.page_count + 1)
    ):
        db.rollback()
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

    fatal = any(page.status == "failed" and page.outcome_retryable is False for page in pages)
    not_ready = any(
        page.status in {"pending", "processing"}
        or (page.status == "failed" and page.outcome_retryable is True)
        for page in pages
    )
    if not_ready:
        db.rollback()
        _fail("EXTRACTION_AGGREGATION_NOT_READY")
    if not fatal and any(page.status not in {"completed", "needs_attention"} for page in pages):
        db.rollback()
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")

    manifest: TechnicalExtractionManifest | None = None
    if fatal:
        status = "failed"
        outcome_code = "EXTRACTION_PAGE_FAILED"
    else:
        manifest = _manifest_for_run(
            db,
            run,
            artifact_storage_root=artifact_storage_root,
        )
        attention = any(page.status == "needs_attention" for page in pages)
        status = "completed_with_attention" if attention else "completed"
        outcome_code = "EXTRACTION_COMPLETE_WITH_ATTENTION" if attention else "EXTRACTION_COMPLETE"
    try:
        aggregated = db.execute(
            update(TechnicalExtractionRun)
            .where(
                TechnicalExtractionRun.id == claim.run_id,
                TechnicalExtractionRun.status == "processing",
                TechnicalExtractionRun.attempt_token == claim.attempt_token,
                TechnicalExtractionRun.record_version == claim.record_version,
            )
            .values(
                status=status,
                attempt_token=None,
                attempt_started_at=None,
                manifest_sha256=manifest.sha256 if manifest is not None else None,
                outcome_code=outcome_code,
                outcome_retryable=False,
                last_outcome_at=current,
                completed_at=current,
                record_version=TechnicalExtractionRun.record_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")
    if getattr(aggregated, "rowcount", 0) != 1:
        db.rollback()
        _fail("EXTRACTION_RUN_CLAIM_LOST")
    _system_audit(
        db,
        action="aggregate_technical_extraction_run",
        run_id=claim.run_id,
        previous_value={
            "status": "processing",
            "record_version": claim.record_version,
        },
        new_value={
            "status": status,
            "record_version": claim.record_version + 1,
            "outcome_code": outcome_code,
            "manifest_sha256": manifest.sha256 if manifest is not None else None,
        },
        reason="Aggregated the exact terminal extraction page set",
    )
    _flush(db)
    _commit(db)
    return TechnicalExtractionAggregateResult(
        run_id=claim.run_id,
        status=status,
        outcome_code=outcome_code,
        manifest_sha256=manifest.sha256 if manifest is not None else None,
    )


def aggregate_technical_extraction_run(
    db: Session,
    *,
    claim: TechnicalExtractionRunClaim,
    source_snapshot: TechnicalExtractionSourceSnapshot,
    artifact_storage_root: Path,
    now: datetime | None = None,
) -> TechnicalExtractionAggregateResult:
    """Own and close every transaction used to terminalize an extraction run."""

    try:
        return _aggregate_technical_extraction_run(
            db,
            claim=claim,
            source_snapshot=source_snapshot,
            artifact_storage_root=artifact_storage_root,
            now=now,
        )
    except TechnicalExtractionError:
        _rollback(db)
        raise
    except SQLAlchemyError:
        _rollback(db)
        _fail("EXTRACTION_RUN_PERSISTENCE_CONFLICT")


__all__ = [
    "TECHNICAL_EXTRACTION_LAYOUT_MAX_BYTES",
    "TECHNICAL_EXTRACTION_LAYOUT_SCHEMA",
    "TECHNICAL_EXTRACTION_MANIFEST_SCHEMA",
    "TECHNICAL_EXTRACTION_MANIFEST_SCHEMA_V1",
    "TECHNICAL_EXTRACTION_PAGE_SCHEMA",
    "TECHNICAL_EXTRACTION_PAGE_SCHEMA_V1",
    "TECHNICAL_EXTRACTION_PAGE_CLAIM_TTL",
    "TECHNICAL_EXTRACTION_RUN_SCHEMA",
    "TECHNICAL_EXTRACTION_RUN_SCHEMA_V1",
    "TECHNICAL_EXTRACTION_RUN_CLAIM_TTL",
    "TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL",
    "TechnicalExtractionAbortResult",
    "TechnicalExtractionAggregateResult",
    "TechnicalExtractionError",
    "TechnicalExtractionLayoutBinding",
    "TechnicalExtractionManifest",
    "TechnicalExtractionPageClaim",
    "TechnicalExtractionPageCompletion",
    "TechnicalExtractionPageInitialization",
    "TechnicalExtractionPageLayoutBinding",
    "TechnicalExtractionRequestResult",
    "TechnicalExtractionRunClaim",
    "TechnicalExtractionSourceSnapshot",
    "TechnicalParserInvocationReceiptBinding",
    "TechnicalParserInvocationReconciliationClaim",
    "TechnicalParserInvocationReconciliationResult",
    "TechnicalParserInvocationReservation",
    "abort_technical_extraction_run",
    "aggregate_technical_extraction_run",
    "claim_next_technical_extraction_run",
    "claim_next_stale_technical_parser_invocation",
    "claim_technical_extraction_page",
    "complete_technical_extraction_page",
    "confirm_technical_extraction_source_snapshot",
    "count_unsettled_technical_parser_invocations",
    "fail_technical_extraction_page",
    "fail_technical_extraction_run",
    "finalize_technical_parser_invocation_reconciliation",
    "get_claimed_technical_extraction_source_snapshot",
    "heartbeat_technical_extraction_page",
    "heartbeat_technical_extraction_run",
    "initialize_technical_extraction_pages",
    "reconstruct_technical_extraction_manifest",
    "record_technical_parser_invocation_receipt",
    "release_technical_extraction_run_for_retry",
    "reserve_technical_parser_invocation",
    "request_technical_extraction_run",
    "verify_technical_extraction_manifest",
]
