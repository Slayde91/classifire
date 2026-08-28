"""Engine-neutral, canonical runtime and parser-invocation receipts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Never, cast
from uuid import UUID

TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1 = (
    "technical-parser-runtime-attestation-v1"
)
TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2 = (
    "technical-parser-runtime-attestation-v2"
)
# Compatibility name for existing v1 producers and persisted rows. New OCI
# runtime attestations opt into v2 explicitly once they bind daemon and fence
# identity.
TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA = (
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1
)
TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA = (
    "technical-parser-invocation-receipt-v1"
)
# Compatibility name for callers that treat this as the generic execution receipt.
TECHNICAL_PARSER_EXECUTION_RECEIPT_SCHEMA = (
    TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA
)
TECHNICAL_PARSER_EXECUTION_SUCCESS = "PARSER_EXECUTION_SUCCEEDED"
TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN = "PARSER_EXECUTION_OUTCOME_UNKNOWN"

TechnicalParserOperation = Literal["layout", "page"]
TechnicalParserExecutionState = Literal[
    "not_started",
    "succeeded",
    "failed",
    "execution_unknown",
    "containment_lost",
]

_ATTESTATION_MAX_BYTES = 64 * 1024
_RECEIPT_MAX_BYTES = 128 * 1024
_JSON_MAX_DEPTH = 8
_JSON_MAX_COLLECTION_ITEMS = 256
_JSON_MAX_STRING_LENGTH = 16 * 1024
_MAX_STDOUT_BYTES = 30_412_804
_ENGINE = re.compile(r"^[a-z][a-z0-9._-]{0,31}$")
_CLAIM_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")
_OUTCOME_CODE = re.compile(r"^[A-Z][A-Z0-9_]{0,99}$")

_TECHNICAL_PARSER_EXECUTION_ERROR_CODES = frozenset(
    {
        "PARSER_EXECUTION_CONTAINMENT_LOST",
        "PARSER_EXECUTION_FAILED",
        "PARSER_EXECUTION_OUTPUT_OVERFLOW",
        "PARSER_EXECUTION_SOURCE_INVALID",
        "PARSER_EXECUTION_TIMEOUT",
        "PARSER_EXECUTION_UNAVAILABLE",
    }
)


def _fail_validation() -> Never:
    raise ValueError("Invalid technical parser execution evidence")


def _canonical_uuid4(value: object) -> str:
    if not isinstance(value, str):
        _fail_validation()
    try:
        parsed = UUID(value)
    except (ValueError, AttributeError, TypeError):
        _fail_validation()
    if parsed.version != 4 or str(parsed) != value:
        _fail_validation()
    return value


def _canonical_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail_validation()
    return value


def _canonical_datetime(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail_validation()
    safe = value.astimezone(UTC)
    if safe.utcoffset() != UTC.utcoffset(safe):
        _fail_validation()
    return safe


def _datetime_text(value: datetime) -> str:
    return _canonical_datetime(value).isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


def _parse_datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail_validation()
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        _fail_validation()
    if _datetime_text(parsed) != value:
        _fail_validation()
    return parsed


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > _JSON_MAX_DEPTH:
        _fail_validation()
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not -(2**63) <= value <= 2**63 - 1:
            _fail_validation()
        return
    if isinstance(value, str):
        if len(value) > _JSON_MAX_STRING_LENGTH:
            _fail_validation()
        return
    if isinstance(value, list):
        if len(value) > _JSON_MAX_COLLECTION_ITEMS:
            _fail_validation()
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > _JSON_MAX_COLLECTION_ITEMS:
            _fail_validation()
        for key, item in value.items():
            if not isinstance(key, str) or _CLAIM_KEY.fullmatch(key) is None:
                _fail_validation()
            _validate_json_value(item, depth=depth + 1)
        return
    _fail_validation()


def _canonical_json(value: object, *, maximum_bytes: int) -> bytes:
    _validate_json_value(value)
    try:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        _fail_validation()
    if not encoded or len(encoded) > maximum_bytes:
        _fail_validation()
    return encoded


def _reject_number(_value: str) -> Never:
    _fail_validation()


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            _fail_validation()
        value[key] = item
    return value


def _strict_json(raw: object, *, maximum_bytes: int) -> dict[str, object]:
    if not isinstance(raw, bytes) or not raw or len(raw) > maximum_bytes:
        _fail_validation()
    try:
        value = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_strict_object,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        _fail_validation()
    if not isinstance(value, dict):
        _fail_validation()
    value = cast(dict[str, object], value)
    if _canonical_json(value, maximum_bytes=maximum_bytes) != raw:
        _fail_validation()
    return value


@dataclass(frozen=True, slots=True)
class TechnicalParserRuntimeAttestation:
    """Canonical engine-neutral envelope around exact runtime claims."""

    schema: str
    engine: str
    canonical_json: bytes
    sha256: str

    def __post_init__(self) -> None:
        value = _strict_json(
            self.canonical_json,
            maximum_bytes=_ATTESTATION_MAX_BYTES,
        )
        if (
            self.schema
            not in {
                TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1,
                TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
            }
            or not isinstance(self.engine, str)
            or _ENGINE.fullmatch(self.engine) is None
            or set(value) != {"claims", "engine", "schema"}
            or value.get("schema") != self.schema
            or value.get("engine") != self.engine
            or not isinstance(value.get("claims"), dict)
            or not cast(dict[str, object], value["claims"])
            or hashlib.sha256(self.canonical_json).hexdigest()
            != _canonical_sha256(self.sha256)
        ):
            _fail_validation()

    def as_dict(self) -> dict[str, object]:
        """Return a new strictly parsed copy of the canonical payload."""

        return _strict_json(
            self.canonical_json,
            maximum_bytes=_ATTESTATION_MAX_BYTES,
        )


def create_technical_parser_runtime_attestation(
    *,
    engine: object,
    claims: Mapping[str, object],
    schema: object = TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA,
) -> TechnicalParserRuntimeAttestation:
    if (
        not isinstance(engine, str)
        or _ENGINE.fullmatch(engine) is None
        or not isinstance(claims, Mapping)
        or not claims
        or schema
        not in {
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1,
            TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
        }
    ):
        _fail_validation()
    payload = {
        "claims": dict(claims),
        "engine": engine,
        "schema": schema,
    }
    canonical = _canonical_json(payload, maximum_bytes=_ATTESTATION_MAX_BYTES)
    return TechnicalParserRuntimeAttestation(
        schema=cast(str, schema),
        engine=engine,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def parse_technical_parser_runtime_attestation(
    raw: object,
    *,
    expected_sha256: object | None = None,
) -> TechnicalParserRuntimeAttestation:
    value = _strict_json(raw, maximum_bytes=_ATTESTATION_MAX_BYTES)
    if set(value) != {"claims", "engine", "schema"}:
        _fail_validation()
    canonical = cast(bytes, raw)
    digest = hashlib.sha256(canonical).hexdigest()
    if expected_sha256 is not None and digest != _canonical_sha256(expected_sha256):
        _fail_validation()
    engine = value.get("engine")
    schema = value.get("schema")
    if not isinstance(engine, str) or not isinstance(schema, str):
        _fail_validation()
    return TechnicalParserRuntimeAttestation(
        schema=schema,
        engine=engine,
        canonical_json=canonical,
        sha256=digest,
    )


@dataclass(frozen=True, slots=True)
class TechnicalParserExecutionReceipt:
    """Canonical receipt for one exact parser invocation outcome."""

    receipt_schema: str
    execution_state: TechnicalParserExecutionState
    operation: TechnicalParserOperation
    invocation_id: str
    expected_attestation_sha256: str
    attestation: TechnicalParserRuntimeAttestation
    outcome_code: str
    container_id: str | None
    started_at: datetime | None
    completed_at: datetime
    exit_code: int | None
    stdout_sha256: str | None
    stdout_size_bytes: int | None
    cleanup_confirmed: bool
    canonical_json: bytes
    sha256: str

    def __post_init__(self) -> None:
        value = _strict_json(self.canonical_json, maximum_bytes=_RECEIPT_MAX_BYTES)
        if (
            self.receipt_schema != TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA
            or self.execution_state
            not in {
                "not_started",
                "succeeded",
                "failed",
                "execution_unknown",
                "containment_lost",
            }
            or self.operation not in {"layout", "page"}
            or _canonical_uuid4(self.invocation_id) != self.invocation_id
            or _canonical_sha256(self.expected_attestation_sha256)
            != self.expected_attestation_sha256
            or not isinstance(self.attestation, TechnicalParserRuntimeAttestation)
            or not isinstance(self.outcome_code, str)
            or _OUTCOME_CODE.fullmatch(self.outcome_code) is None
            or self.container_id is not None
            and (
                not isinstance(self.container_id, str)
                or _CONTAINER_ID.fullmatch(self.container_id) is None
            )
            or self.started_at is not None
            and _canonical_datetime(self.started_at) != self.started_at
            or _canonical_datetime(self.completed_at) != self.completed_at
            or self.exit_code is not None
            and (
                not isinstance(self.exit_code, int)
                or isinstance(self.exit_code, bool)
                or not 0 <= self.exit_code <= 255
            )
            or self.stdout_sha256 is not None
            and _canonical_sha256(self.stdout_sha256) != self.stdout_sha256
            or self.stdout_size_bytes is not None
            and (
                not isinstance(self.stdout_size_bytes, int)
                or isinstance(self.stdout_size_bytes, bool)
                or not 0 <= self.stdout_size_bytes <= _MAX_STDOUT_BYTES
            )
            or (self.stdout_sha256 is None) != (self.stdout_size_bytes is None)
            or not isinstance(self.cleanup_confirmed, bool)
            or self.started_at is not None
            and self.completed_at < self.started_at
            or hashlib.sha256(self.canonical_json).hexdigest()
            != _canonical_sha256(self.sha256)
        ):
            _fail_validation()
        expected_keys = {
            "cleanup_confirmed",
            "completed_at",
            "container_id",
            "execution_state",
            "exit_code",
            "expected_attestation_sha256",
            "invocation_id",
            "operation",
            "outcome_code",
            "receipt_schema",
            "runtime_attestation",
            "runtime_attestation_sha256",
            "started_at",
            "stdout_sha256",
            "stdout_size_bytes",
        }
        if (
            set(value) != expected_keys
            or value.get("receipt_schema") != self.receipt_schema
            or value.get("execution_state") != self.execution_state
            or value.get("operation") != self.operation
            or value.get("invocation_id") != self.invocation_id
            or value.get("expected_attestation_sha256")
            != self.expected_attestation_sha256
            or value.get("runtime_attestation_sha256") != self.attestation.sha256
            or value.get("runtime_attestation") != self.attestation.as_dict()
            or value.get("outcome_code") != self.outcome_code
            or value.get("container_id") != self.container_id
            or value.get("started_at")
            != (None if self.started_at is None else _datetime_text(self.started_at))
            or value.get("completed_at") != _datetime_text(self.completed_at)
            or value.get("exit_code") != self.exit_code
            or value.get("stdout_sha256") != self.stdout_sha256
            or value.get("stdout_size_bytes") != self.stdout_size_bytes
            or value.get("cleanup_confirmed") is not self.cleanup_confirmed
        ):
            _fail_validation()
        if self.execution_state == "not_started":
            if (
                any(
                    value is not None
                    for value in (
                        self.container_id,
                        self.started_at,
                        self.exit_code,
                        self.stdout_sha256,
                        self.stdout_size_bytes,
                    )
                )
                or self.cleanup_confirmed is not True
                or (self.outcome_code not in _TECHNICAL_PARSER_EXECUTION_ERROR_CODES)
            ):
                _fail_validation()
        elif self.execution_state == "succeeded":
            if (
                self.expected_attestation_sha256 != self.attestation.sha256
                or self.outcome_code != TECHNICAL_PARSER_EXECUTION_SUCCESS
                or self.container_id is None
                or self.started_at is None
                or self.exit_code != 0
                or self.stdout_sha256 is None
                or self.stdout_size_bytes is None
                or not 1 <= self.stdout_size_bytes <= _MAX_STDOUT_BYTES
                or self.cleanup_confirmed is not True
            ):
                _fail_validation()
        elif self.execution_state == "failed":
            if (
                self.outcome_code not in _TECHNICAL_PARSER_EXECUTION_ERROR_CODES
                or self.outcome_code == TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN
                or self.container_id is None
                or self.started_at is None
                or self.cleanup_confirmed is not True
            ):
                _fail_validation()
        elif self.execution_state == "containment_lost":
            if (
                self.outcome_code != "PARSER_EXECUTION_CONTAINMENT_LOST"
                or self.cleanup_confirmed is not False
            ):
                _fail_validation()
        elif self.execution_state == "execution_unknown":
            if (
                self.outcome_code != TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN
                or self.started_at is not None
                or self.exit_code is not None
                or self.stdout_sha256 is not None
                or self.stdout_size_bytes is not None
                or self.cleanup_confirmed is not True
            ):
                _fail_validation()

    def as_dict(self) -> dict[str, object]:
        """Return a new strictly parsed copy of the canonical receipt."""

        return _strict_json(self.canonical_json, maximum_bytes=_RECEIPT_MAX_BYTES)


def create_technical_parser_execution_receipt(
    *,
    execution_state: TechnicalParserExecutionState,
    operation: TechnicalParserOperation,
    invocation_id: object,
    expected_attestation_sha256: object,
    attestation: TechnicalParserRuntimeAttestation,
    outcome_code: object,
    container_id: object | None,
    started_at: datetime | None,
    completed_at: datetime,
    exit_code: object | None,
    stdout_sha256: object | None,
    stdout_size_bytes: object | None,
    cleanup_confirmed: object,
) -> TechnicalParserExecutionReceipt:
    invocation = _canonical_uuid4(invocation_id)
    expected = _canonical_sha256(expected_attestation_sha256)
    if not isinstance(attestation, TechnicalParserRuntimeAttestation):
        _fail_validation()
    if not isinstance(outcome_code, str) or _OUTCOME_CODE.fullmatch(outcome_code) is None:
        _fail_validation()
    if container_id is not None and (
        not isinstance(container_id, str) or _CONTAINER_ID.fullmatch(container_id) is None
    ):
        _fail_validation()
    safe_started = None if started_at is None else _canonical_datetime(started_at)
    safe_completed = _canonical_datetime(completed_at)
    if exit_code is not None and (
        not isinstance(exit_code, int)
        or isinstance(exit_code, bool)
        or not 0 <= exit_code <= 255
    ):
        _fail_validation()
    if stdout_sha256 is not None:
        stdout_sha256 = _canonical_sha256(stdout_sha256)
    if stdout_size_bytes is not None and (
        not isinstance(stdout_size_bytes, int)
        or isinstance(stdout_size_bytes, bool)
        or not 0 <= stdout_size_bytes <= _MAX_STDOUT_BYTES
    ):
        _fail_validation()
    if not isinstance(cleanup_confirmed, bool):
        _fail_validation()
    payload = {
        "cleanup_confirmed": cleanup_confirmed,
        "completed_at": _datetime_text(safe_completed),
        "container_id": container_id,
        "execution_state": execution_state,
        "exit_code": exit_code,
        "expected_attestation_sha256": expected,
        "invocation_id": invocation,
        "operation": operation,
        "outcome_code": outcome_code,
        "receipt_schema": TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA,
        "runtime_attestation": attestation.as_dict(),
        "runtime_attestation_sha256": attestation.sha256,
        "started_at": None if safe_started is None else _datetime_text(safe_started),
        "stdout_sha256": stdout_sha256,
        "stdout_size_bytes": stdout_size_bytes,
    }
    canonical = _canonical_json(payload, maximum_bytes=_RECEIPT_MAX_BYTES)
    return TechnicalParserExecutionReceipt(
        receipt_schema=TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA,
        execution_state=execution_state,
        operation=operation,
        invocation_id=invocation,
        expected_attestation_sha256=expected,
        attestation=attestation,
        outcome_code=outcome_code,
        container_id=cast(str | None, container_id),
        started_at=safe_started,
        completed_at=safe_completed,
        exit_code=cast(int | None, exit_code),
        stdout_sha256=cast(str | None, stdout_sha256),
        stdout_size_bytes=cast(int | None, stdout_size_bytes),
        cleanup_confirmed=cleanup_confirmed,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


def parse_technical_parser_execution_receipt(
    raw: object,
    *,
    expected_sha256: object | None = None,
) -> TechnicalParserExecutionReceipt:
    value = _strict_json(raw, maximum_bytes=_RECEIPT_MAX_BYTES)
    canonical = cast(bytes, raw)
    digest = hashlib.sha256(canonical).hexdigest()
    if expected_sha256 is not None and digest != _canonical_sha256(expected_sha256):
        _fail_validation()
    attestation_value = value.get("runtime_attestation")
    if not isinstance(attestation_value, dict):
        _fail_validation()
    attestation = parse_technical_parser_runtime_attestation(
        _canonical_json(attestation_value, maximum_bytes=_ATTESTATION_MAX_BYTES),
        expected_sha256=value.get("runtime_attestation_sha256"),
    )
    execution_state = value.get("execution_state")
    operation = value.get("operation")
    if execution_state not in {
        "not_started",
        "succeeded",
        "failed",
        "execution_unknown",
        "containment_lost",
    } or operation not in {"layout", "page"}:
        _fail_validation()
    started_text = value.get("started_at")
    completed_text = value.get("completed_at")
    return TechnicalParserExecutionReceipt(
        receipt_schema=cast(str, value.get("receipt_schema")),
        execution_state=cast(TechnicalParserExecutionState, execution_state),
        operation=cast(TechnicalParserOperation, operation),
        invocation_id=cast(str, value.get("invocation_id")),
        expected_attestation_sha256=cast(
            str,
            value.get("expected_attestation_sha256"),
        ),
        attestation=attestation,
        outcome_code=cast(str, value.get("outcome_code")),
        container_id=cast(str | None, value.get("container_id")),
        started_at=None if started_text is None else _parse_datetime(started_text),
        completed_at=_parse_datetime(completed_text),
        exit_code=cast(int | None, value.get("exit_code")),
        stdout_sha256=cast(str | None, value.get("stdout_sha256")),
        stdout_size_bytes=cast(int | None, value.get("stdout_size_bytes")),
        cleanup_confirmed=cast(bool, value.get("cleanup_confirmed")),
        canonical_json=canonical,
        sha256=digest,
    )


@dataclass(frozen=True, slots=True)
class TechnicalParserExecutionSuccess:
    """Verified parser bytes paired with their exact durable receipt."""

    output: bytes
    receipt: TechnicalParserExecutionReceipt

    def __post_init__(self) -> None:
        if (
            not isinstance(self.output, bytes)
            or not self.output
            or not isinstance(self.receipt, TechnicalParserExecutionReceipt)
            or self.receipt.execution_state != "succeeded"
            or self.receipt.stdout_size_bytes != len(self.output)
            or self.receipt.stdout_sha256 != hashlib.sha256(self.output).hexdigest()
        ):
            _fail_validation()


class TechnicalParserExecutionError(RuntimeError):
    """Stable host-owned failure raised by a bounded runner implementation."""

    def __init__(
        self,
        code: str,
        *,
        receipt: TechnicalParserExecutionReceipt | None = None,
    ) -> None:
        if code not in _TECHNICAL_PARSER_EXECUTION_ERROR_CODES:
            raise ValueError("Unknown technical parser execution error code")
        if receipt is not None and (
            not isinstance(receipt, TechnicalParserExecutionReceipt)
            or receipt.execution_state == "succeeded"
            or receipt.outcome_code != code
        ):
            raise ValueError("Failure receipt does not match parser execution error")
        self.code = code
        self.receipt = receipt
        super().__init__(code)


__all__ = [
    "TECHNICAL_PARSER_EXECUTION_RECEIPT_SCHEMA",
    "TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN",
    "TECHNICAL_PARSER_EXECUTION_SUCCESS",
    "TECHNICAL_PARSER_INVOCATION_RECEIPT_SCHEMA",
    "TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA",
    "TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1",
    "TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2",
    "TechnicalParserExecutionError",
    "TechnicalParserExecutionReceipt",
    "TechnicalParserExecutionState",
    "TechnicalParserExecutionSuccess",
    "TechnicalParserOperation",
    "TechnicalParserRuntimeAttestation",
    "create_technical_parser_execution_receipt",
    "create_technical_parser_runtime_attestation",
    "parse_technical_parser_execution_receipt",
    "parse_technical_parser_runtime_attestation",
]
