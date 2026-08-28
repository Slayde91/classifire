from __future__ import annotations

from datetime import UTC, datetime

import pytest

from classifire.services.technical_parser_execution import (
    TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
    TECHNICAL_PARSER_EXECUTION_SUCCESS,
    create_technical_parser_execution_receipt,
    create_technical_parser_runtime_attestation,
)

_INVOCATION_ID = "10000000-0000-4000-8000-000000000001"
_NOT_STARTED_FAILURE_OUTCOMES = (
    "PARSER_EXECUTION_CONTAINMENT_LOST",
    "PARSER_EXECUTION_FAILED",
    "PARSER_EXECUTION_OUTPUT_OVERFLOW",
    "PARSER_EXECUTION_SOURCE_INVALID",
    "PARSER_EXECUTION_TIMEOUT",
    "PARSER_EXECUTION_UNAVAILABLE",
)


def _create_not_started_receipt(outcome_code: str):
    attestation = create_technical_parser_runtime_attestation(
        engine="test",
        claims={"profile": "not-started-validation"},
    )
    return create_technical_parser_execution_receipt(
        execution_state="not_started",
        operation="layout",
        invocation_id=_INVOCATION_ID,
        expected_attestation_sha256=attestation.sha256,
        attestation=attestation,
        outcome_code=outcome_code,
        container_id=None,
        started_at=None,
        completed_at=datetime.now(UTC),
        exit_code=None,
        stdout_sha256=None,
        stdout_size_bytes=None,
        cleanup_confirmed=True,
    )


@pytest.mark.parametrize("outcome_code", _NOT_STARTED_FAILURE_OUTCOMES)
def test_not_started_receipt_accepts_only_defined_failure_outcomes(
    outcome_code: str,
) -> None:
    receipt = _create_not_started_receipt(outcome_code)

    assert receipt.execution_state == "not_started"
    assert receipt.outcome_code == outcome_code


@pytest.mark.parametrize(
    "outcome_code",
    (
        TECHNICAL_PARSER_EXECUTION_SUCCESS,
        TECHNICAL_PARSER_EXECUTION_OUTCOME_UNKNOWN,
        "PARSER_EXECUTION_ARBITRARY",
    ),
)
def test_not_started_receipt_rejects_non_failure_outcomes(
    outcome_code: str,
) -> None:
    with pytest.raises(ValueError, match="Invalid technical parser execution evidence"):
        _create_not_started_receipt(outcome_code)
