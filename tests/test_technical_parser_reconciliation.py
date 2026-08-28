from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event, func, select
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
    TechnicalExtractionRun,
    TechnicalParserInvocation,
    TechnicalParserInvocationReceipt,
    TechnicalVariant,
    User,
)
from classifire.services.technical_extraction import (
    TechnicalExtractionError,
    TechnicalExtractionRunClaim,
    TechnicalParserInvocationReconciliationClaim,
    TechnicalParserInvocationReconciliationResult,
    claim_next_technical_extraction_run,
    count_unsettled_technical_parser_invocations,
    request_technical_extraction_run,
    reserve_technical_parser_invocation,
)
from classifire.services.technical_extraction_executor import (
    TechnicalExtractionExecutionResult,
)
from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1,
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionError,
    TechnicalParserExecutionReceipt,
    TechnicalParserRuntimeAttestation,
    create_technical_parser_runtime_attestation,
)
from classifire.services.technical_parser_oci import (
    TECHNICAL_PARSER_OCI_CLEANUP_PROOF_SCHEMA,
    TechnicalParserOciCleanupProof,
)
from classifire.services.technical_parser_protocol import (
    encode_technical_parser_layout_request,
)
from classifire.services.technical_parser_reconciliation import (
    TECHNICAL_PARSER_RECONCILIATION_DISABLED,
    TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED,
    TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED,
    TECHNICAL_PARSER_RECONCILIATION_PENDING,
    TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED,
    reconcile_technical_parser_worker_startup,
    run_technical_parser_worker_cycle,
)

NOW = datetime(2026, 8, 28, 1, 2, 3, tzinfo=UTC)
SHA = "a" * 64
WORKER_SHA = "b" * 64
RUNTIME_PROFILE_SHA = "c" * 64
RUNTIME_EXECUTABLE_SHA = "d" * 64
SECCOMP_SHA = "e" * 64
DAEMON_SHA = "f" * 64
FENCE_SHA = "1" * 64
IMAGE_ID = f"sha256:{'2' * 64}"
OWNER_ID = "11111111-1111-4111-8111-111111111111"
POLICY = "technical-extraction-policy-v1"
POLICY_BYTES = b'{"schema":"technical-extraction-policy-v1"}'


def _settings(
    storage_root: Path,
    *,
    reconciliation_enabled: bool,
    execution_enabled: bool = True,
) -> Settings:
    return Settings(
        env="test",
        storage_root=storage_root,
        technical_parser_orphan_reconciliation_enabled=reconciliation_enabled,
        technical_extraction_executor_enabled=execution_enabled,
    )


def _attestation(*, schema: str) -> TechnicalParserRuntimeAttestation:
    return create_technical_parser_runtime_attestation(
        engine="oci",
        schema=schema,
        claims={"test_claim": "bounded"},
    )


def _claim(
    *,
    schema: str = TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    terminal_receipt: TechnicalParserExecutionReceipt | None = None,
) -> TechnicalParserInvocationReconciliationClaim:
    attestation = _attestation(schema=schema)
    run_claim = TechnicalExtractionRunClaim(
        run_id=str(uuid4()),
        record_version=2,
        attempt_token=str(uuid4()),
        attempt_started_at=NOW,
        attempt_count=1,
        technical_document_id=str(uuid4()),
        source_stored_file_id=str(uuid4()),
        source_sha256=SHA,
        source_size_bytes=100,
        extraction_policy="bounded-test-policy",
        extraction_policy_sha256=SHA,
        ocr_low_confidence_threshold=Decimal("0.70"),
        worker_image_digest=f"sha256:{SHA}",
        run_schema="technical-extraction-run-v2",
        runtime_profile_sha256=SHA,
        runtime_attestation_sha256=attestation.sha256,
        page_count=None,
        layout_schema=None,
        layout_sha256=None,
        layout_size_bytes=None,
        layout_invocation_id=None,
    )
    return TechnicalParserInvocationReconciliationClaim(
        invocation_id=str(uuid4()),
        operation="layout",
        page_number=0,
        invocation_created_at=NOW - timedelta(hours=1),
        run_claim=run_claim,
        page_claim=None,
        request_sha256=SHA,
        request_size_bytes=20,
        runtime_attestation=attestation,
        terminal_receipt=terminal_receipt,
        lease_started_at=NOW,
    )


def _terminal_claim(
    *,
    cleanup_confirmed: bool = True,
) -> TechnicalParserInvocationReconciliationClaim:
    placeholder = cast(
        TechnicalParserExecutionReceipt,
        SimpleNamespace(cleanup_confirmed=cleanup_confirmed),
    )
    return _claim(terminal_receipt=placeholder)


def _result(
    claim: TechnicalParserInvocationReconciliationClaim,
) -> TechnicalParserInvocationReconciliationResult:
    return TechnicalParserInvocationReconciliationResult(
        invocation_id=claim.invocation_id,
        run_id=claim.run_claim.run_id,
        operation=claim.operation,
        execution_state=(
            "failed" if claim.terminal_receipt is not None else "execution_unknown"
        ),
        receipt_sha256=SHA,
        run_outcome_code="EXTRACTION_PARSER_EXECUTION_UNKNOWN",
        page_outcome_code=None,
        cancelled_page_count=0,
        preserved_page_count=0,
    )


class _CleanupRunner:
    def __init__(
        self,
        *,
        proof: TechnicalParserOciCleanupProof,
        events: list[str] | None = None,
        error: Exception | None = None,
        call_finalize: bool = True,
        return_same_proof: bool = True,
    ) -> None:
        self.proof = proof
        self.events = events if events is not None else []
        self.error = error
        self.call_finalize = call_finalize
        self.return_same_proof = return_same_proof
        self.cleanup_calls: list[
            tuple[str, str, TechnicalParserRuntimeAttestation]
        ] = []

    def cleanup_orphan_invocation(
        self,
        *,
        invocation_id: str,
        operation: str,
        persisted_runtime_attestation: TechnicalParserRuntimeAttestation,
        finalize: Callable[[TechnicalParserOciCleanupProof], None] | None = None,
    ) -> TechnicalParserOciCleanupProof:
        self.events.append("cleanup_enter")
        self.cleanup_calls.append(
            (invocation_id, operation, persisted_runtime_attestation)
        )
        if self.error is not None:
            raise self.error
        if self.call_finalize and finalize is not None:
            finalize(self.proof)
        self.events.append("cleanup_return")
        if self.return_same_proof:
            return self.proof
        return cast(TechnicalParserOciCleanupProof, object())


def _proof() -> TechnicalParserOciCleanupProof:
    return cast(TechnicalParserOciCleanupProof, object())


def _db() -> Session:
    return cast(Session, object())


def _never(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    raise AssertionError("disabled or blocked startup touched a forbidden dependency")


@pytest.fixture
def real_db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record) -> None:  # type: ignore[no-untyped-def]
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _valid_v2_attestation(
    claim: TechnicalExtractionRunClaim,
) -> TechnicalParserRuntimeAttestation:
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


def _valid_cleanup_proof(
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
        "controller_owner_id": OWNER_ID,
        "execution_fence_sha256": FENCE_SHA,
        "invocation_id": invocation_id,
        "observed_container_id": None,
        "observed_container_state": None,
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
        observed_container_id=None,
        observed_container_state=None,
        cleanup_confirmed=True,
        completed_at=completed_at,
        canonical_json=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
    )


class _ProofRunner:
    def cleanup_orphan_invocation(
        self,
        *,
        invocation_id: str,
        operation: str,
        persisted_runtime_attestation: TechnicalParserRuntimeAttestation,
        finalize: Callable[[TechnicalParserOciCleanupProof], None] | None = None,
    ) -> TechnicalParserOciCleanupProof:
        assert operation == "layout"
        proof = _valid_cleanup_proof(
            invocation_id=invocation_id,
            attestation=persisted_runtime_attestation,
        )
        assert finalize is not None
        finalize(proof)
        return proof


def test_disabled_worker_cycle_touches_no_database_runtime_or_executor(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=False)
    runner = _CleanupRunner(proof=_proof())

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        policy_resolver=_never,
        max_reconciliations=0,
        claim_stale=_never,
        count_unsettled=_never,
        finalize_invocation=_never,
        execute_next=_never,
    )

    assert cycle.startup.state == "disabled"
    assert cycle.startup.outcome_code == TECHNICAL_PARSER_RECONCILIATION_DISABLED
    assert cycle.execution is None
    assert runner.cleanup_calls == []


def test_receiptless_v2_cleanup_finalizes_inside_runtime_callback(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _claim()
    events: list[str] = []
    claims = iter((claim, None))
    proof = _proof()
    runner = _CleanupRunner(proof=proof, events=events)

    def claim_stale(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        events.append("claim")
        return next(claims)

    def finalize_invocation(*_args, **kwargs):  # type: ignore[no-untyped-def]
        events.append("finalize")
        assert kwargs["claim"] is claim
        assert kwargs["cleanup_proof"] is proof
        assert "now" not in kwargs
        return _result(claim)

    def count_unsettled(_db: Session) -> int:
        events.append("count")
        return 0

    result = reconcile_technical_parser_worker_startup(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        now=NOW,
        claim_stale=claim_stale,
        count_unsettled=count_unsettled,
        finalize_invocation=finalize_invocation,
    )

    assert result.state == "ready"
    assert result.claimed_count == 1
    assert result.reconciled_count == 1
    assert result.remaining_count == 0
    assert runner.cleanup_calls == [
        (claim.invocation_id, claim.operation, claim.runtime_attestation)
    ]
    assert events == [
        "claim",
        "cleanup_enter",
        "finalize",
        "cleanup_return",
        "claim",
        "count",
    ]


def test_existing_terminal_receipt_finalizes_without_runtime_cleanup(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _terminal_claim()
    claims = iter((claim, None))
    runner = _CleanupRunner(proof=_proof())
    finalizations: list[dict[str, object]] = []

    def finalize_invocation(*_args, **kwargs):  # type: ignore[no-untyped-def]
        finalizations.append(kwargs)
        return _result(claim)

    result = reconcile_technical_parser_worker_startup(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        now=NOW,
        claim_stale=lambda *_args, **_kwargs: next(claims),
        count_unsettled=lambda _db: 0,
        finalize_invocation=finalize_invocation,
    )

    assert result.state == "ready"
    assert runner.cleanup_calls == []
    assert len(finalizations) == 1
    assert finalizations[0]["claim"] is claim
    assert finalizations[0]["cleanup_proof"] is None
    assert "now" not in finalizations[0]


def test_containment_lost_receipt_requires_fresh_fenced_cleanup(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _terminal_claim(cleanup_confirmed=False)
    claims = iter((claim, None))
    proof = _proof()
    events: list[str] = []
    runner = _CleanupRunner(proof=proof, events=events)

    def finalize_invocation(*_args, **kwargs):  # type: ignore[no-untyped-def]
        events.append("finalize")
        assert kwargs["claim"] is claim
        assert kwargs["cleanup_proof"] is proof
        return _result(claim)

    result = reconcile_technical_parser_worker_startup(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        claim_stale=lambda *_args, **_kwargs: next(claims),
        count_unsettled=lambda _db: 0,
        finalize_invocation=finalize_invocation,
    )

    assert result.state == "ready"
    assert result.reconciled_count == 1
    assert runner.cleanup_calls == [
        (claim.invocation_id, claim.operation, claim.runtime_attestation)
    ]
    assert events == ["cleanup_enter", "finalize", "cleanup_return"]


def test_legacy_receiptless_invocation_blocks_without_runtime_cleanup(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _claim(schema=TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V1)
    runner = _CleanupRunner(proof=_proof())

    result = reconcile_technical_parser_worker_startup(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        claim_stale=lambda *_args, **_kwargs: claim,
        count_unsettled=_never,
        finalize_invocation=_never,
    )

    assert result.state == "blocked"
    assert (
        result.outcome_code
        == TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED
    )
    assert result.invocation_id == claim.invocation_id
    assert runner.cleanup_calls == []


def test_young_unsettled_invocation_blocks_normal_execution(tmp_path: Path) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    executions: list[str] = []

    def execute_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        executions.append("execute")
        return TechnicalExtractionExecutionResult(state="idle")

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, _CleanupRunner(proof=_proof())),
        policy_resolver=_never,
        claim_stale=lambda *_args, **_kwargs: None,
        count_unsettled=lambda _db: 1,
        finalize_invocation=_never,
        execute_next=execute_next,
    )

    assert cycle.startup.state == "blocked"
    assert cycle.startup.outcome_code == TECHNICAL_PARSER_RECONCILIATION_PENDING
    assert cycle.startup.remaining_count == 1
    assert cycle.execution is None
    assert executions == []


def test_ready_startup_allows_exactly_one_normal_execution(tmp_path: Path) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    executions: list[str] = []

    def execute_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        executions.append("execute")
        return TechnicalExtractionExecutionResult(state="idle")

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, _CleanupRunner(proof=_proof())),
        policy_resolver=_never,
        claim_stale=lambda *_args, **_kwargs: None,
        count_unsettled=lambda _db: 0,
        finalize_invocation=_never,
        execute_next=execute_next,
    )

    assert cycle.startup.state == "ready"
    assert cycle.startup.remaining_count == 0
    assert cycle.execution == TechnicalExtractionExecutionResult(state="idle")
    assert executions == ["execute"]


def test_reconciliation_limit_with_remaining_work_blocks_execution(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _terminal_claim()
    executions: list[str] = []

    def execute_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        executions.append("execute")
        return TechnicalExtractionExecutionResult(state="idle")

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, _CleanupRunner(proof=_proof())),
        policy_resolver=_never,
        max_reconciliations=1,
        claim_stale=lambda *_args, **_kwargs: claim,
        count_unsettled=lambda _db: 2,
        finalize_invocation=lambda *_args, **_kwargs: _result(claim),
        execute_next=execute_next,
    )

    assert cycle.startup.state == "blocked"
    assert (
        cycle.startup.outcome_code
        == TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED
    )
    assert cycle.startup.claimed_count == 1
    assert cycle.startup.reconciled_count == 1
    assert cycle.startup.remaining_count == 2
    assert cycle.execution is None
    assert executions == []


def test_cleanup_failure_fails_closed_and_prevents_execution(tmp_path: Path) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _claim()
    runner = _CleanupRunner(
        proof=_proof(),
        error=TechnicalParserExecutionError("PARSER_EXECUTION_CONTAINMENT_LOST"),
    )
    executions: list[str] = []

    def execute_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        executions.append("execute")
        return TechnicalExtractionExecutionResult(state="idle")

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        policy_resolver=_never,
        claim_stale=lambda *_args, **_kwargs: claim,
        count_unsettled=_never,
        finalize_invocation=_never,
        execute_next=execute_next,
    )

    assert cycle.startup.state == "blocked"
    assert cycle.startup.outcome_code == "PARSER_EXECUTION_CONTAINMENT_LOST"
    assert cycle.startup.reconciled_count == 0
    assert cycle.execution is None
    assert executions == []


def test_database_commit_ambiguity_is_explicit_and_prevents_execution(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _claim()
    runner = _CleanupRunner(proof=_proof())
    executions: list[str] = []

    def finalize_invocation(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise TechnicalExtractionError(
            "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN",
            database_outcome="commit_outcome_unknown",
        )

    def execute_next(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        executions.append("execute")
        return TechnicalExtractionExecutionResult(state="idle")

    cycle = run_technical_parser_worker_cycle(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        policy_resolver=_never,
        claim_stale=lambda *_args, **_kwargs: claim,
        count_unsettled=_never,
        finalize_invocation=finalize_invocation,
        execute_next=execute_next,
    )

    assert cycle.startup.state == "commit_outcome_unknown"
    assert cycle.startup.outcome_code == "EXTRACTION_ACKNOWLEDGEMENT_UNKNOWN"
    assert cycle.startup.reconciled_count == 0
    assert cycle.execution is None
    assert executions == []


def test_cleanup_without_fenced_finalization_is_not_accepted(tmp_path: Path) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _claim()
    runner = _CleanupRunner(proof=_proof(), call_finalize=False)

    result = reconcile_technical_parser_worker_startup(
        _db(),
        settings=settings,
        runner=cast(object, runner),
        claim_stale=lambda *_args, **_kwargs: claim,
        count_unsettled=_never,
        finalize_invocation=_never,
    )

    assert result.state == "blocked"
    assert (
        result.outcome_code
        == TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED
    )
    assert result.reconciled_count == 0


def test_wrong_finalizer_type_or_binding_fails_closed(tmp_path: Path) -> None:
    settings = _settings(tmp_path, reconciliation_enabled=True)
    claim = _terminal_claim()
    valid = _result(claim)
    invalid_results = (
        object(),
        replace(valid, run_id=str(uuid4())),
        replace(valid, operation="page"),
    )

    for invalid in invalid_results:
        result = reconcile_technical_parser_worker_startup(
            _db(),
            settings=settings,
            runner=cast(object, _CleanupRunner(proof=_proof())),
            claim_stale=lambda *_args, **_kwargs: claim,
            count_unsettled=_never,
            finalize_invocation=(
                lambda *_args, _invalid=invalid, **_kwargs: _invalid
            ),
        )

        assert result.state == "blocked"
        assert (
            result.outcome_code
            == TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED
        )
        assert result.reconciled_count == 0


def test_real_database_receiptless_orphan_reaches_safe_ready_state(
    real_db: Session,
    tmp_path: Path,
) -> None:
    started_at = datetime.now(UTC) - timedelta(minutes=20)
    startup_at = datetime.now(UTC)
    actor = User(
        email="worker-startup@example.test",
        full_name="Worker Startup",
        password_hash="unused",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    real_db.add(actor)
    real_db.flush()
    stored = StoredFile(
        original_filename="startup-source.pdf",
        media_type="application/pdf",
        storage_path="retained/startup-source.pdf",
        sha256=SHA,
        size_bytes=4096,
        purpose="technical_evidence",
        malware_scan_status="clean",
        uploaded_by_id=actor.id,
        immutable=True,
    )
    real_db.add(stored)
    real_db.flush()
    document = TechnicalDocument(
        document_id="TECH-WORKER-STARTUP",
        stored_file_id=stored.id,
        document_type="assessment",
        title="Worker startup reconciliation source",
    )
    real_db.add(document)
    real_db.commit()
    requested = request_technical_extraction_run(
        real_db,
        actor=actor,
        technical_document_id=document.id,
        extraction_policy=POLICY,
        extraction_policy_bytes=POLICY_BYTES,
        ocr_low_confidence_threshold=Decimal("80"),
        worker_image_digest=WORKER_SHA,
        runtime_profile_sha256=RUNTIME_PROFILE_SHA,
    )
    run_claim = claim_next_technical_extraction_run(real_db, now=started_at)
    assert run_claim is not None
    assert run_claim.run_id == requested.run_id
    attestation = _valid_v2_attestation(run_claim)
    request = encode_technical_parser_layout_request(
        technical_document_id=run_claim.technical_document_id,
        source_sha256=run_claim.source_sha256,
        source_size_bytes=run_claim.source_size_bytes,
        extraction_policy=run_claim.extraction_policy,
        extraction_policy_sha256=run_claim.extraction_policy_sha256,
        worker_image_digest=run_claim.worker_image_digest,
        ocr_low_confidence_threshold=run_claim.ocr_low_confidence_threshold,
    )
    reservation = reserve_technical_parser_invocation(
        real_db,
        claim=run_claim,
        operation="layout",
        request=request,
        runtime_attestation=attestation,
        invocation_id=str(uuid4()),
        now=started_at,
    )
    invocation = real_db.get(
        TechnicalParserInvocation,
        reservation.invocation_id,
    )
    run = real_db.get(TechnicalExtractionRun, run_claim.run_id)
    assert invocation is not None
    assert run is not None
    invocation.created_at = started_at
    run.attempt_started_at = started_at
    real_db.commit()
    assert count_unsettled_technical_parser_invocations(real_db) == 1

    result = reconcile_technical_parser_worker_startup(
        real_db,
        settings=_settings(tmp_path, reconciliation_enabled=True),
        runner=cast(object, _ProofRunner()),
        now=startup_at,
    )

    receipt = real_db.get(
        TechnicalParserInvocationReceipt,
        reservation.invocation_id,
    )
    run = real_db.get(TechnicalExtractionRun, run_claim.run_id)
    assert result.state == "ready"
    assert result.claimed_count == 1
    assert result.reconciled_count == 1
    assert result.remaining_count == 0
    assert receipt is not None
    assert receipt.execution_state == "execution_unknown"
    assert receipt.outcome_code == "PARSER_EXECUTION_OUTCOME_UNKNOWN"
    assert receipt.cleanup_confirmed is True
    assert run is not None
    assert run.status == "failed"
    assert run.outcome_code == "EXTRACTION_PARSER_EXECUTION_UNKNOWN"
    assert run.outcome_retryable is False
    assert count_unsettled_technical_parser_invocations(real_db) == 0
    assert real_db.scalar(select(func.count(TechnicalDerivedArtifact.id))) == 0
    assert real_db.scalar(select(func.count(TechnicalVariant.id))) == 0
    assert real_db.scalar(select(func.count(Approval.id))) == 0
    assert real_db.scalar(select(func.count(LibraryRelease.id))) == 0
