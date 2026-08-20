from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from classifire.services.deployment_lineage import assess_deployment_lineage


def _assessment(revision: str, *, receipt_table: bool):  # type: ignore[no-untyped-def]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
        connection.execute(text("CREATE TABLE physical_model_admissions (id VARCHAR(36))"))
        if receipt_table:
            connection.execute(
                text("CREATE TABLE physical_model_submission_receipts (id VARCHAR(36))")
            )
    with Session(engine) as db:
        return assess_deployment_lineage(db)


def test_clean_stack_head_is_ready_only_with_both_journal_tables() -> None:
    result = _assessment("0006_physical_submission_receipts", receipt_table=True)
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"
    assert result.database_write_performed is False


def test_legacy_adjudicated_head_fails_closed_for_rehearsal() -> None:
    result = _assessment("0006_adjudicated_canonical_admissions", receipt_table=False)
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_LINEAGE_REHEARSAL_REQUIRED"
    assert result.missing_tables == ("physical_model_submission_receipts",)


def test_unknown_revision_fails_closed() -> None:
    result = _assessment("unexpected_revision", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
