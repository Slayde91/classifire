"""Fail-closed startup boundary for the dedicated technical parser worker.

The web application and generic workers must remain write-free with respect to
parser orphan recovery.  A dedicated extraction worker may call this module at
startup, but normal extraction is allowed only after every current-attempt
invocation has a terminal database disposition.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from ..config import Settings
from .technical_extraction import (
    TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL,
    TechnicalExtractionError,
    TechnicalParserInvocationReconciliationClaim,
    TechnicalParserInvocationReconciliationResult,
    claim_next_stale_technical_parser_invocation,
    count_unsettled_technical_parser_invocations,
    finalize_technical_parser_invocation_reconciliation,
)
from .technical_extraction_executor import (
    TechnicalExtractionExecutionResult,
    TechnicalExtractionPolicyResolver,
    TechnicalParserRunner,
    execute_next_technical_extraction,
)
from .technical_parser_execution import (
    TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2,
    TechnicalParserExecutionError,
    TechnicalParserRuntimeAttestation,
)
from .technical_parser_oci import TechnicalParserOciCleanupProof

TECHNICAL_PARSER_RECONCILIATION_DISABLED = (
    "TECHNICAL_PARSER_RECONCILIATION_DISABLED"
)
TECHNICAL_PARSER_RECONCILIATION_PENDING = "TECHNICAL_PARSER_RECONCILIATION_PENDING"
TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED = (
    "TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED"
)
TECHNICAL_PARSER_RECONCILIATION_FAILED = "TECHNICAL_PARSER_RECONCILIATION_FAILED"
TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED = (
    "TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED"
)
TECHNICAL_PARSER_RECONCILIATION_CONFIGURATION_INVALID = (
    "TECHNICAL_PARSER_RECONCILIATION_CONFIGURATION_INVALID"
)
TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED = (
    "TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED"
)

DEFAULT_STARTUP_RECONCILIATION_LIMIT = 32
MAX_STARTUP_RECONCILIATION_LIMIT = 256


class TechnicalParserReconciledRunner(TechnicalParserRunner, Protocol):
    """Parser runner whose orphan cleanup shares the normal execution fence."""

    def cleanup_orphan_invocation(
        self,
        *,
        invocation_id: str,
        operation: Literal["layout", "page"],
        persisted_runtime_attestation: TechnicalParserRuntimeAttestation,
        finalize: Callable[[TechnicalParserOciCleanupProof], None] | None = None,
    ) -> TechnicalParserOciCleanupProof: ...


@dataclass(frozen=True, slots=True)
class TechnicalParserWorkerStartupResult:
    """One explicit startup disposition for the dedicated parser worker."""

    state: Literal["disabled", "ready", "blocked", "commit_outcome_unknown"]
    claimed_count: int = 0
    reconciled_count: int = 0
    remaining_count: int | None = None
    outcome_code: str | None = None
    invocation_id: str | None = None


@dataclass(frozen=True, slots=True)
class TechnicalParserWorkerCycleResult:
    """Startup result plus an optional, reconciliation-authorised execution."""

    startup: TechnicalParserWorkerStartupResult
    execution: TechnicalExtractionExecutionResult | None = None


ClaimStaleInvocation = Callable[
    ...,
    TechnicalParserInvocationReconciliationClaim | None,
]
CountUnsettledInvocations = Callable[[Session], int]
FinalizeInvocation = Callable[..., TechnicalParserInvocationReconciliationResult]
ExecuteNextExtraction = Callable[..., TechnicalExtractionExecutionResult]


def _blocked(
    *,
    code: str,
    claimed_count: int,
    reconciled_count: int,
    invocation_id: str | None,
    remaining_count: int | None = None,
    commit_outcome_unknown: bool = False,
) -> TechnicalParserWorkerStartupResult:
    return TechnicalParserWorkerStartupResult(
        state=("commit_outcome_unknown" if commit_outcome_unknown else "blocked"),
        claimed_count=claimed_count,
        reconciled_count=reconciled_count,
        remaining_count=remaining_count,
        outcome_code=code,
        invocation_id=invocation_id,
    )


def _dependency_failure(
    error: Exception,
    *,
    claimed_count: int,
    reconciled_count: int,
    invocation_id: str | None,
) -> TechnicalParserWorkerStartupResult:
    if isinstance(error, TechnicalExtractionError):
        return _blocked(
            code=error.code,
            claimed_count=claimed_count,
            reconciled_count=reconciled_count,
            invocation_id=invocation_id,
            commit_outcome_unknown=(
                error.database_outcome == "commit_outcome_unknown"
            ),
        )
    if isinstance(error, TechnicalParserExecutionError):
        return _blocked(
            code=error.code,
            claimed_count=claimed_count,
            reconciled_count=reconciled_count,
            invocation_id=invocation_id,
        )
    return _blocked(
        code=TECHNICAL_PARSER_RECONCILIATION_FAILED,
        claimed_count=claimed_count,
        reconciled_count=reconciled_count,
        invocation_id=invocation_id,
    )


def _remaining_result(
    db: Session,
    *,
    claimed_count: int,
    reconciled_count: int,
    invocation_id: str | None,
    no_claim_code: str,
    count_unsettled: CountUnsettledInvocations,
) -> TechnicalParserWorkerStartupResult:
    try:
        remaining = count_unsettled(db)
    except Exception as error:
        return _dependency_failure(
            error,
            claimed_count=claimed_count,
            reconciled_count=reconciled_count,
            invocation_id=invocation_id,
        )
    if (
        not isinstance(remaining, int)
        or isinstance(remaining, bool)
        or remaining < 0
    ):
        return _blocked(
            code=TECHNICAL_PARSER_RECONCILIATION_FAILED,
            claimed_count=claimed_count,
            reconciled_count=reconciled_count,
            invocation_id=invocation_id,
        )
    if remaining == 0:
        return TechnicalParserWorkerStartupResult(
            state="ready",
            claimed_count=claimed_count,
            reconciled_count=reconciled_count,
            remaining_count=0,
            invocation_id=invocation_id,
        )
    return _blocked(
        code=no_claim_code,
        claimed_count=claimed_count,
        reconciled_count=reconciled_count,
        remaining_count=remaining,
        invocation_id=invocation_id,
    )


def reconcile_technical_parser_worker_startup(
    db: Session,
    *,
    settings: Settings,
    runner: TechnicalParserReconciledRunner,
    now: datetime | None = None,
    claim_ttl: timedelta = TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL,
    max_reconciliations: int = DEFAULT_STARTUP_RECONCILIATION_LIMIT,
    claim_stale: ClaimStaleInvocation = claim_next_stale_technical_parser_invocation,
    count_unsettled: CountUnsettledInvocations = (
        count_unsettled_technical_parser_invocations
    ),
    finalize_invocation: FinalizeInvocation = (
        finalize_technical_parser_invocation_reconciliation
    ),
) -> TechnicalParserWorkerStartupResult:
    """Resolve bounded stale attempts and refuse startup unless none remain.

    The settings check deliberately precedes validation and every database or
    runtime dependency call.  Receiptless attempts require runtime attestation
    v2 and are finalized only through the cleanup callback while the OCI fence
    is still held.  Existing terminal receipts need no runtime side effect.
    """

    if not settings.technical_parser_orphan_reconciliation_runtime_allowed:
        return TechnicalParserWorkerStartupResult(
            state="disabled",
            outcome_code=TECHNICAL_PARSER_RECONCILIATION_DISABLED,
        )
    if (
        not isinstance(max_reconciliations, int)
        or isinstance(max_reconciliations, bool)
        or not 1 <= max_reconciliations <= MAX_STARTUP_RECONCILIATION_LIMIT
        or not isinstance(claim_ttl, timedelta)
        or claim_ttl <= timedelta(0)
    ):
        return _blocked(
            code=TECHNICAL_PARSER_RECONCILIATION_CONFIGURATION_INVALID,
            claimed_count=0,
            reconciled_count=0,
            invocation_id=None,
        )

    claimed_count = 0
    reconciled_count = 0
    invocation_id: str | None = None
    for _item in range(max_reconciliations):
        try:
            claim = claim_stale(db, now=now, claim_ttl=claim_ttl)
        except Exception as error:
            return _dependency_failure(
                error,
                claimed_count=claimed_count,
                reconciled_count=reconciled_count,
                invocation_id=invocation_id,
            )
        if claim is None:
            return _remaining_result(
                db,
                claimed_count=claimed_count,
                reconciled_count=reconciled_count,
                invocation_id=invocation_id,
                no_claim_code=TECHNICAL_PARSER_RECONCILIATION_PENDING,
                count_unsettled=count_unsettled,
            )

        active_claim: TechnicalParserInvocationReconciliationClaim = claim
        claimed_count += 1
        invocation_id = active_claim.invocation_id
        try:
            cleanup_required = (
                active_claim.terminal_receipt is None
                or active_claim.terminal_receipt.cleanup_confirmed is not True
            )
            if not cleanup_required:
                finalized = finalize_invocation(
                    db,
                    claim=active_claim,
                    cleanup_proof=None,
                )
            else:
                if (
                    active_claim.runtime_attestation.schema
                    != TECHNICAL_PARSER_RUNTIME_ATTESTATION_SCHEMA_V2
                ):
                    return _blocked(
                        code=(
                            TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED
                        ),
                        claimed_count=claimed_count,
                        reconciled_count=reconciled_count,
                        invocation_id=invocation_id,
                    )
                fenced_finalizations: list[
                    tuple[
                        TechnicalParserOciCleanupProof,
                        TechnicalParserInvocationReconciliationResult,
                    ]
                ] = []

                def _finalize_under_fence(
                    proof: TechnicalParserOciCleanupProof,
                    *,
                    _claim: TechnicalParserInvocationReconciliationClaim = (
                        active_claim
                    ),
                    _finalizations: list[
                        tuple[
                            TechnicalParserOciCleanupProof,
                            TechnicalParserInvocationReconciliationResult,
                        ]
                    ] = fenced_finalizations,
                ) -> None:
                    if _finalizations:
                        raise RuntimeError(
                            TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED
                        )
                    result = finalize_invocation(
                        db,
                        claim=_claim,
                        cleanup_proof=proof,
                    )
                    _finalizations.append((proof, result))

                returned_proof = runner.cleanup_orphan_invocation(
                    invocation_id=active_claim.invocation_id,
                    operation=active_claim.operation,
                    persisted_runtime_attestation=active_claim.runtime_attestation,
                    finalize=_finalize_under_fence,
                )
                if (
                    len(fenced_finalizations) != 1
                    or returned_proof is not fenced_finalizations[0][0]
                ):
                    return _blocked(
                        code=(
                            TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED
                        ),
                        claimed_count=claimed_count,
                        reconciled_count=reconciled_count,
                        invocation_id=invocation_id,
                    )
                finalized = fenced_finalizations[0][1]
        except Exception as error:
            return _dependency_failure(
                error,
                claimed_count=claimed_count,
                reconciled_count=reconciled_count,
                invocation_id=invocation_id,
            )
        if (
            not isinstance(
                finalized,
                TechnicalParserInvocationReconciliationResult,
            )
            or finalized.invocation_id != active_claim.invocation_id
            or finalized.run_id != active_claim.run_claim.run_id
            or finalized.operation != active_claim.operation
        ):
            return _blocked(
                code=TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED,
                claimed_count=claimed_count,
                reconciled_count=reconciled_count,
                invocation_id=invocation_id,
            )
        reconciled_count += 1

    return _remaining_result(
        db,
        claimed_count=claimed_count,
        reconciled_count=reconciled_count,
        invocation_id=invocation_id,
        no_claim_code=TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED,
        count_unsettled=count_unsettled,
    )


def run_technical_parser_worker_cycle(
    db: Session,
    *,
    settings: Settings,
    runner: TechnicalParserReconciledRunner,
    policy_resolver: TechnicalExtractionPolicyResolver,
    max_page_attempts: int = 3,
    now: datetime | None = None,
    claim_ttl: timedelta = TECHNICAL_PARSER_RECONCILIATION_CLAIM_TTL,
    max_reconciliations: int = DEFAULT_STARTUP_RECONCILIATION_LIMIT,
    claim_stale: ClaimStaleInvocation = claim_next_stale_technical_parser_invocation,
    count_unsettled: CountUnsettledInvocations = (
        count_unsettled_technical_parser_invocations
    ),
    finalize_invocation: FinalizeInvocation = (
        finalize_technical_parser_invocation_reconciliation
    ),
    execute_next: ExecuteNextExtraction = execute_next_technical_extraction,
) -> TechnicalParserWorkerCycleResult:
    """Run reconciliation first, then at most one normal extraction if ready."""

    startup = reconcile_technical_parser_worker_startup(
        db,
        settings=settings,
        runner=runner,
        now=now,
        claim_ttl=claim_ttl,
        max_reconciliations=max_reconciliations,
        claim_stale=claim_stale,
        count_unsettled=count_unsettled,
        finalize_invocation=finalize_invocation,
    )
    if startup.state != "ready":
        return TechnicalParserWorkerCycleResult(startup=startup)
    execution = execute_next(
        db,
        settings=settings,
        runner=runner,
        policy_resolver=policy_resolver,
        max_page_attempts=max_page_attempts,
    )
    return TechnicalParserWorkerCycleResult(startup=startup, execution=execution)


__all__ = [
    "DEFAULT_STARTUP_RECONCILIATION_LIMIT",
    "MAX_STARTUP_RECONCILIATION_LIMIT",
    "TECHNICAL_PARSER_RECONCILIATION_CONFIGURATION_INVALID",
    "TECHNICAL_PARSER_RECONCILIATION_DISABLED",
    "TECHNICAL_PARSER_RECONCILIATION_FAILED",
    "TECHNICAL_PARSER_RECONCILIATION_FINALIZATION_NOT_CONFIRMED",
    "TECHNICAL_PARSER_RECONCILIATION_LIMIT_REACHED",
    "TECHNICAL_PARSER_RECONCILIATION_PENDING",
    "TECHNICAL_PARSER_RECONCILIATION_RUNTIME_PROVENANCE_REQUIRED",
    "TechnicalParserReconciledRunner",
    "TechnicalParserWorkerCycleResult",
    "TechnicalParserWorkerStartupResult",
    "reconcile_technical_parser_worker_startup",
    "run_technical_parser_worker_cycle",
]
