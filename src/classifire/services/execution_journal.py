"""Durable, sealed execution records; no default producer or runtime wiring."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from functools import wraps
from typing import Any, ParamSpec, Protocol, TypeVar
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from classifire.models import BackgroundJob
from classifire.services.phase8_openresponses_transport import (
    ExecutionCompletionContext,
    ExecutionCompletionEvidence,
    Phase8OpenResponsesTransportError,
    _is_agent_id,
    _is_sha256,
    validate_execution_completion,
)
from classifire.services.phase8_visual_proposal import canonical_json_sha256

JOB_TYPE = "execution_completion_v1"


class ExecutionJournalError(RuntimeError):
    """Content-safe application error; never contains producer or database text."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


P = ParamSpec("P")
T = TypeVar("T")


def _storage_boundary(method: Callable[P, T]) -> Callable[P, T]:
    @wraps(method)
    def safe(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return method(*args, **kwargs)
        except SQLAlchemyError:
            raise ExecutionJournalError("JOURNAL_STORAGE_UNAVAILABLE") from None

    return safe


@dataclass(frozen=True, slots=True)
class ExecutionBinding:
    agent_id: str
    session_id_sha256: str
    request_sha256: str
    request_body_sha256: str
    attestation_receipt_sha256: str


@dataclass(frozen=True, slots=True)
class CaptureStart:
    receipt_sha256: str
    started_at_ms: int


class TrustedExecutionProducer(Protocol):
    """Application-owned port, responsible for authenticating capture assurance.

    Never implement this by treating an empty remote audit page as completion.
    The journal key authenticates storage, not this producer's remote assertions.
    """

    def start_capture(self, binding: ExecutionBinding) -> CaptureStart: ...

    def execute(
        self, binding: ExecutionBinding, capture: CaptureStart, started_at_ms: int
    ) -> tuple[ExecutionCompletionContext, ExecutionCompletionEvidence]: ...


class ExecutionJournal:
    def __init__(
        self,
        *,
        sessions: Callable[[], Session],
        authentication_key: bytes,
        producer_id: str,
        producer: TrustedExecutionProducer,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        if (
            type(authentication_key) is not bytes
            or len(authentication_key) < 32
            or not _is_agent_id(producer_id)
        ):
            raise ExecutionJournalError("JOURNAL_CONFIGURATION_INVALID")
        self._sessions = sessions
        self._key = authentication_key
        self._producer_id = producer_id
        self._producer = producer
        self._clock = clock_ms or (lambda: time.time_ns() // 1_000_000)

    @_storage_boundary
    def execute(
        self, *, run_id: str, owner_id: str, binding: ExecutionBinding
    ) -> ExecutionCompletionEvidence:
        """One durable attempt. Replays never redispatch a producer."""
        self._identity(run_id)
        self._identity(owner_id)
        self._binding(binding)
        payload = {
            "schema": JOB_TYPE,
            "owner_id": owner_id,
            "producer_id": self._producer_id,
            "binding": asdict(binding),
        }
        data: dict[str, Any] = {"reserved_at_ms": self._now()}
        initial = self._envelope(run_id, "preparing", 1, payload, data)
        try:
            with self._sessions() as db, db.begin():
                db.add(
                    BackgroundJob(
                        id=run_id,
                        job_type=JOB_TYPE,
                        status="preparing",
                        payload=payload,
                        result=initial,
                        record_version=1,
                        attempts=1,
                    )
                )
        except IntegrityError:
            record = self._read(run_id, owner_id)
            if record["payload"] != payload:
                raise ExecutionJournalError("JOURNAL_INVOCATION_MISMATCH") from None
            return self._completed(record)
        # Any crash from this point leaves a durable non-replayable attempt.
        try:
            capture = self._producer.start_capture(binding)
            started = self._now()
            if (
                type(capture) is not CaptureStart
                or not _is_sha256(capture.receipt_sha256)
                or type(capture.started_at_ms) is not int
                or not data["reserved_at_ms"] <= capture.started_at_ms <= started
            ):
                raise ExecutionJournalError("JOURNAL_CAPTURE_INVALID")
            running_data = {
                **data,
                "capture": asdict(capture),
                "started_at_ms": started,
            }
            self._transition(run_id, owner_id, "preparing", 1, "running", running_data)
            context, evidence = self._producer.execute(binding, capture, started)
            self._check_outcome(binding, capture, started, context, evidence)
            if context.observed_at_ms > self._now():
                raise ExecutionJournalError("JOURNAL_CLOCK_INVALID")
            terminal_data = {
                **running_data,
                "context": asdict(context),
                "evidence": asdict(evidence),
            }
            self._transition(run_id, owner_id, "running", 2, "complete", terminal_data)
        except Exception:
            # Error persistence can itself fail. A preparing/running record remains
            # unverified and cannot replay. Never retain arbitrary exception text.
            self._fail(run_id, owner_id)
            raise ExecutionJournalError("JOURNAL_EXECUTION_FAILED") from None
        return self.verify(run_id=run_id, owner_id=owner_id, context=context)

    @_storage_boundary
    def verify(
        self, *, run_id: str, owner_id: str, context: ExecutionCompletionContext
    ) -> ExecutionCompletionEvidence:
        record = self._read(run_id, owner_id)
        evidence = self._completed(record)
        if type(context) is not ExecutionCompletionContext or (
            record["data"]["context"] != asdict(context)
        ):
            raise ExecutionJournalError("JOURNAL_INVOCATION_MISMATCH")
        return evidence

    @_storage_boundary
    def interrupt_expired(self, *, run_id: str, owner_id: str, minimum_age_ms: int) -> None:
        """Stop local acceptance after timeout; does not promise remote cancellation."""
        if type(minimum_age_ms) is not int or minimum_age_ms <= 0:
            raise ExecutionJournalError("JOURNAL_TIMEOUT_INVALID")
        record = self._read(run_id, owner_id)
        if record["status"] not in {"preparing", "running"}:
            raise ExecutionJournalError("JOURNAL_STATE_INVALID")
        now = self._now()
        reserved = record["data"]["reserved_at_ms"]
        if type(reserved) is not int or now - reserved < minimum_age_ms:
            raise ExecutionJournalError("JOURNAL_NOT_EXPIRED")
        self._transition(
            run_id,
            owner_id,
            record["status"],
            record["version"],
            "interrupted",
            {**record["data"], "error_code": "EXECUTION_OUTCOME_UNKNOWN"},
        )

    def _completed(self, record: dict[str, Any]) -> ExecutionCompletionEvidence:
        if record["status"] != "complete":
            raise ExecutionJournalError("JOURNAL_OUTCOME_UNAVAILABLE")
        try:
            data = record["data"]
            binding = ExecutionBinding(**record["payload"]["binding"])
            capture = CaptureStart(**data["capture"])
            context = ExecutionCompletionContext(**data["context"])
            evidence = ExecutionCompletionEvidence(**data["evidence"])
            self._check_outcome(binding, capture, data["started_at_ms"], context, evidence)
            # The durable hash includes the upstream receipt; no circular digest.
            durable_sha256 = canonical_json_sha256(
                {
                    "schema": "CLASSIFIRE-DURABLE-EXECUTION-v1",
                    "run_id": record["id"],
                    "payload": record["payload"],
                    "data": data,
                }
            )
            result = replace(evidence, receipt_sha256=durable_sha256)
            validate_execution_completion(result, context)
            return result
        except (TypeError, ValueError, KeyError, Phase8OpenResponsesTransportError):
            raise ExecutionJournalError("JOURNAL_RECORD_INVALID") from None

    def _read(self, run_id: str, owner_id: str) -> dict[str, Any]:
        self._identity(run_id)
        self._identity(owner_id)
        with self._sessions() as db:
            row = db.get(BackgroundJob, run_id)
            if row is None or row.job_type != JOB_TYPE:
                raise ExecutionJournalError("JOURNAL_RECORD_UNAVAILABLE")
            result = row.result
            if (
                type(row.payload) is not dict
                or type(result) is not dict
                or set(result) != {"data", "mac"}
                or type(result["data"]) is not dict
                or not _is_sha256(result["mac"])
                or type(row.record_version) is not int
            ):
                raise ExecutionJournalError("JOURNAL_RECORD_INVALID")
            try:
                expected = self._envelope(
                    run_id, row.status, row.record_version, row.payload, result["data"]
                )
            except (TypeError, ValueError, OverflowError):
                raise ExecutionJournalError("JOURNAL_RECORD_INVALID") from None
            if not hmac.compare_digest(result["mac"], expected["mac"]):
                raise ExecutionJournalError("JOURNAL_RECORD_INVALID")
            if (
                row.payload.get("owner_id") != owner_id
                or row.payload.get("producer_id") != self._producer_id
            ):
                raise ExecutionJournalError("JOURNAL_OWNER_MISMATCH")
            return {
                "id": run_id,
                "status": row.status,
                "version": row.record_version,
                "payload": row.payload,
                "data": result["data"],
            }

    def _transition(
        self,
        run_id: str,
        owner_id: str,
        status: str,
        version: int,
        next_status: str,
        data: dict[str, Any],
    ) -> None:
        record = self._read(run_id, owner_id)
        if record["status"] != status or record["version"] != version:
            raise ExecutionJournalError("JOURNAL_STATE_CONFLICT")
        result = self._envelope(run_id, next_status, version + 1, record["payload"], data)
        with self._sessions() as db, db.begin():
            changed = db.execute(
                update(BackgroundJob)
                .where(
                    BackgroundJob.id == run_id,
                    BackgroundJob.job_type == JOB_TYPE,
                    BackgroundJob.status == status,
                    BackgroundJob.record_version == version,
                )
                .values(
                    status=next_status,
                    record_version=version + 1,
                    result=result,
                    started_at=(
                        datetime.fromtimestamp(data["started_at_ms"] / 1000, UTC)
                        if "started_at_ms" in data
                        else None
                    ),
                    finished_at=(
                        datetime.fromtimestamp(self._now() / 1000, UTC)
                        if next_status in {"complete", "failed", "interrupted"}
                        else None
                    ),
                )
            )
            if changed.rowcount != 1:  # type: ignore[attr-defined]
                raise ExecutionJournalError("JOURNAL_STATE_CONFLICT")

    def _fail(self, run_id: str, owner_id: str) -> None:
        record = self._read(run_id, owner_id)
        if record["status"] in {"preparing", "running"}:
            self._transition(
                run_id,
                owner_id,
                record["status"],
                record["version"],
                "failed",
                {**record["data"], "error_code": "PRODUCER_FAILED"},
            )

    def _envelope(
        self,
        run_id: str,
        status: str,
        version: int,
        payload: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        serialized = json.dumps(
            {
                "id": run_id,
                "job_type": JOB_TYPE,
                "status": status,
                "version": version,
                "payload": payload,
                "data": data,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        return {"data": data, "mac": hmac.new(self._key, serialized, hashlib.sha256).hexdigest()}

    def _now(self) -> int:
        value = self._clock()
        if type(value) is not int or value < 0:
            raise ExecutionJournalError("JOURNAL_CLOCK_INVALID")
        return value

    @staticmethod
    def _identity(value: str) -> None:
        try:
            if type(value) is not str or str(UUID(value)) != value:
                raise ValueError
        except (ValueError, AttributeError):
            raise ExecutionJournalError("JOURNAL_IDENTITY_INVALID") from None

    @staticmethod
    def _binding(binding: ExecutionBinding) -> None:
        if type(binding) is not ExecutionBinding or not _is_agent_id(binding.agent_id):
            raise ExecutionJournalError("JOURNAL_BINDING_INVALID")
        if any(
            not _is_sha256(value) for name, value in asdict(binding).items() if name != "agent_id"
        ):
            raise ExecutionJournalError("JOURNAL_BINDING_INVALID")

    @classmethod
    def _check_outcome(
        cls,
        binding: ExecutionBinding,
        capture: CaptureStart,
        started: int,
        context: ExecutionCompletionContext,
        evidence: ExecutionCompletionEvidence,
    ) -> None:
        cls._binding(binding)
        validate_execution_completion(evidence, context)
        if (
            any(getattr(context, name) != value for name, value in asdict(binding).items())
            or context.started_at_ms != started
            or evidence.coverage_from_ms > capture.started_at_ms
        ):
            raise ExecutionJournalError("JOURNAL_INVOCATION_MISMATCH")
