from __future__ import annotations

import pytest
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    text,
)
from sqlalchemy.orm import Session

from classifire.db import Base
from classifire.services.deployment_lineage import (
    REQUIRED_COLUMNS,
    REQUIRED_TABLES,
    assess_deployment_lineage,
)


def _assessment(  # type: ignore[no-untyped-def]
    revision: str,
    *,
    receipt_table: bool,
    human_session_table: bool = False,
    human_session_primary_key: bool = True,
    user_auth_generation: bool = False,
    user_auth_generation_length: int = 64,
    user_auth_generation_nullable: bool = False,
    session_token_hint_length: int = 12,
    session_expires_nullable: bool = False,
    token_hash_unique_index: bool = True,
    user_id_index: bool = True,
    user_id_index_unique: bool = False,
    user_fk_ondelete: str | None = "CASCADE",
    legacy_submission_table: bool = False,
    missing_mapped_table: str | None = None,
    missing_mapped_column: str | None = None,
    additional_table: str | None = None,
):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    user_columns = [Column("id", String(36), primary_key=True)]
    if user_auth_generation:
        user_columns.append(
            Column(
                "auth_generation",
                String(user_auth_generation_length),
                nullable=user_auth_generation_nullable,
            )
        )
    Table("users", metadata, *user_columns)
    Table("physical_model_admissions", metadata, Column("id", String(36)))
    if receipt_table:
        Table("physical_model_submission_receipts", metadata, Column("id", String(36)))
        Table("visual_validation_receipts", metadata, Column("id", String(36)))
    if human_session_table:
        human_sessions = Table(
            "human_sessions",
            metadata,
            Column(
                "id",
                String(36),
                primary_key=human_session_primary_key,
                nullable=False,
            ),
            Column("created_at", DateTime(), nullable=False),
            Column("updated_at", DateTime(), nullable=False),
            Column("record_version", Integer(), nullable=False),
            Column(
                "user_id",
                String(36),
                ForeignKey("users.id", ondelete=user_fk_ondelete),
                nullable=False,
            ),
            Column("token_hash", String(64), nullable=False),
            Column("token_hint", String(session_token_hint_length), nullable=False),
            Column("auth_generation", String(64), nullable=False),
            Column("expires_at", DateTime(), nullable=session_expires_nullable),
            Column("revoked_at", DateTime(), nullable=True),
            Column("revoked_reason", Text(), nullable=True),
        )
        if token_hash_unique_index:
            Index("ix_human_sessions_token_hash", human_sessions.c.token_hash, unique=True)
        if user_id_index:
            Index(
                "ix_human_sessions_user_id",
                human_sessions.c.user_id,
                unique=user_id_index_unique,
            )
    if legacy_submission_table:
        Table("physical_model_initial_submissions", metadata, Column("id", String(36)))
    if additional_table:
        Table(additional_table, metadata, Column("id", String(36)))

    omitted_tables: set[str] = set()
    if not human_session_table:
        omitted_tables.add("human_sessions")
    if not receipt_table:
        omitted_tables.update(
            {"physical_model_submission_receipts", "visual_validation_receipts"}
        )
    if missing_mapped_table is not None:
        omitted_tables.add(missing_mapped_table)
    for table_name, model_table in Base.metadata.tables.items():
        if table_name in omitted_tables:
            continue
        if table_name in metadata.tables:
            test_table = metadata.tables[table_name]
        else:
            test_table = Table(table_name, metadata)
        for model_column in model_table.columns:
            qualified_name = f"{table_name}.{model_column.name}"
            if qualified_name == "users.auth_generation" and not user_auth_generation:
                continue
            if (
                model_column.name not in test_table.c
                and qualified_name != missing_mapped_column
            ):
                test_table.append_column(Column(model_column.name, String()))

    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
    with Session(engine) as db:
        return assess_deployment_lineage(db)


def test_required_inventory_matches_every_registered_model() -> None:
    expected_columns = {
        table_name: frozenset(str(column.name) for column in table.columns)
        for table_name, table in Base.metadata.tables.items()
    }

    assert REQUIRED_COLUMNS == expected_columns
    assert REQUIRED_TABLES == frozenset(expected_columns)
    assert {"customers", "defects"} <= REQUIRED_TABLES


def test_clean_stack_head_is_ready_only_with_required_session_and_journal_schema() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
    )
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"
    assert result.database_write_performed is False


@pytest.mark.parametrize("missing_mapped_table", ("customers", "defects"))
def test_current_head_requires_every_mapped_table(missing_mapped_table: str) -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        missing_mapped_table=missing_mapped_table,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_tables == (missing_mapped_table,)


@pytest.mark.parametrize(
    "missing_mapped_column", ("customers.legal_name", "defects.description")
)
def test_current_head_requires_every_mapped_column(missing_mapped_column: str) -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        missing_mapped_column=missing_mapped_column,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_columns == (missing_mapped_column,)


def test_current_head_allows_unrelated_extension_table() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        additional_table="monitoring_extensions",
    )
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"


def test_previous_head_requires_human_session_migration() -> None:
    result = _assessment("0009_visual_validation_receipts", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"
    assert result.missing_tables == ("human_sessions",)
    assert result.missing_columns == ("users.auth_generation",)


def test_current_head_missing_auth_generation_fails_as_schema_drift() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_columns == ("users.auth_generation",)


def test_current_head_rejects_wrong_security_column_contracts() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        user_auth_generation_length=63,
        user_auth_generation_nullable=True,
        session_token_hint_length=11,
        session_expires_nullable=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "human_sessions.expires_at:unexpected_nullability",
        "human_sessions.token_hint:unexpected_length",
        "users.auth_generation:unexpected_length",
        "users.auth_generation:unexpected_nullability",
    )


def test_current_head_requires_unique_token_hash_index() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        token_hash_unique_index=False,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == (
        "human_sessions.token_hash:unique_index_required",
    )


def test_current_head_requires_nonunique_user_lookup_index() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        user_id_index_unique=True,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == (
        "human_sessions.user_id:nonunique_index_required",
    )


def test_current_head_requires_cascading_user_foreign_key() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        user_fk_ondelete=None,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == (
        "human_sessions.user_id:cascading_users_fk_required",
    )


def test_current_head_requires_exact_human_session_id_primary_key() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        human_session_primary_key=False,
        user_auth_generation=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "human_sessions.id:primary_key_required",
    )


def test_previous_head_with_stray_legacy_table_requires_retirement() -> None:
    result = _assessment(
        "0007_reconcile_adjudicated_admission_lineages",
        receipt_table=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED"
    assert result.unexpected_tables == ("physical_model_initial_submissions",)


def test_current_head_with_stray_legacy_table_fails_as_schema_drift() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        legacy_submission_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"


def test_legacy_adjudicated_head_fails_closed_for_rehearsal() -> None:
    result = _assessment("0006_adjudicated_canonical_admissions", receipt_table=False)
    assert result.status == "BLOCKED"
    assert result.code == "LEGACY_LINEAGE_REHEARSAL_REQUIRED"
    assert result.missing_tables == (
        "human_sessions",
        "physical_model_submission_receipts",
        "visual_validation_receipts",
    )


def test_unknown_revision_fails_closed() -> None:
    result = _assessment("unexpected_revision", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
