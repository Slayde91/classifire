"""Permit runtime attestation v2 and reconcile immutable parser receipt checks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_parser_attestation_v2"
down_revision = "0015_technical_parser_invocation_provenance"
branch_labels = None
depends_on = None

_NOT_STARTED_FAILURE_OUTCOMES = (
    "PARSER_EXECUTION_CONTAINMENT_LOST",
    "PARSER_EXECUTION_FAILED",
    "PARSER_EXECUTION_OUTPUT_OVERFLOW",
    "PARSER_EXECUTION_SOURCE_INVALID",
    "PARSER_EXECUTION_TIMEOUT",
    "PARSER_EXECUTION_UNAVAILABLE",
)
_NOT_STARTED_FAILURE_OUTCOMES_SQL = (
    "outcome_code IN ("
    "'PARSER_EXECUTION_CONTAINMENT_LOST', "
    "'PARSER_EXECUTION_FAILED', "
    "'PARSER_EXECUTION_OUTPUT_OVERFLOW', "
    "'PARSER_EXECUTION_SOURCE_INVALID', "
    "'PARSER_EXECUTION_TIMEOUT', "
    "'PARSER_EXECUTION_UNAVAILABLE')"
)


def _preflight_not_started_receipts() -> None:
    receipts = sa.table(
        "technical_parser_invocation_receipts",
        sa.column("invocation_id"),
        sa.column("execution_state"),
        sa.column("outcome_code"),
    )
    result = op.get_bind().execute(
        sa.select(receipts.c.invocation_id)
        .where(
            receipts.c.execution_state == "not_started",
            receipts.c.outcome_code.not_in(_NOT_STARTED_FAILURE_OUTCOMES),
        )
        .order_by(receipts.c.invocation_id)
    )
    invocation_ids = [str(row[0]) for row in result.fetchmany(6)]
    if not invocation_ids:
        return
    sample = ", ".join(invocation_ids[:5])
    suffix = ", ..." if len(invocation_ids) > 5 else ""
    raise RuntimeError(
        "Migration 0016 cannot tighten not_started parser receipt outcomes because "
        "immutable legacy receipts use unsupported outcome codes. No schema or receipt "
        f"evidence was changed. Affected invocation IDs include: {sample}{suffix}"
    )


def upgrade() -> None:
    _preflight_not_started_receipts()
    with op.batch_alter_table("technical_parser_invocations") as batch:
        batch.drop_constraint(
            "ck_technical_parser_invocation_runtime_attestation_schema",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_technical_parser_invocation_runtime_attestation_schema",
            "runtime_attestation_schema IN ("
            "'technical-parser-runtime-attestation-v1', "
            "'technical-parser-runtime-attestation-v2')",
        )
    with op.batch_alter_table("technical_parser_invocation_receipts") as batch:
        batch.drop_constraint(
            "ck_technical_parser_invocation_receipt_lifecycle",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_technical_parser_invocation_receipt_lifecycle",
            "(execution_state = 'not_started' "
            f"AND {_NOT_STARTED_FAILURE_OUTCOMES_SQL} "
            "AND container_id IS NULL "
            "AND started_at IS NULL "
            "AND exit_code IS NULL "
            "AND stdout_sha256 IS NULL "
            "AND stdout_size_bytes IS NULL "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'succeeded' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND exit_code = 0 "
            "AND stdout_sha256 IS NOT NULL "
            "AND stdout_size_bytes BETWEEN 1 AND 30412804 "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'failed' "
            "AND container_id IS NOT NULL "
            "AND started_at IS NOT NULL "
            "AND cleanup_confirmed = true) OR "
            # Migration 0015 allowed execution-unknown receipts to retain any
            # observed runtime fields. The immutable historical evidence must
            # remain admissible and unchanged.
            "(execution_state = 'execution_unknown' "
            "AND cleanup_confirmed = true) OR "
            "(execution_state = 'containment_lost' "
            "AND cleanup_confirmed = false)",
        )


def downgrade() -> None:
    raise RuntimeError(
        "Technical parser runtime attestation v2 may already be retained and cannot be downgraded"
    )
