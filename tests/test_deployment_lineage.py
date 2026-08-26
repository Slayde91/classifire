from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace

import pytest
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    DefaultClause,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm import Session

from classifire.db import Base
from classifire.services import deployment_lineage as deployment_lineage_module
from classifire.services.deployment_lineage import (
    CLEAN_STACK_HEAD,
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
    malware_table_mutator: Callable[[Table], None] | None = None,
    database_tamper: Callable[[Connection], None] | None = None,
    alembic_version_length: int = 32,
    alembic_version_nullable: bool = False,
    alembic_version_primary_key: bool = True,
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

    include_malware_table = (
        revision == CLEAN_STACK_HEAD and missing_mapped_table != "malware_scan_attestations"
    )
    omitted_tables: set[str] = set()
    if not human_session_table:
        omitted_tables.add("human_sessions")
    if not receipt_table:
        omitted_tables.update({"physical_model_submission_receipts", "visual_validation_receipts"})
    if missing_mapped_table is not None:
        omitted_tables.add(missing_mapped_table)
    if not include_malware_table:
        omitted_tables.add("malware_scan_attestations")
    for table_name, model_table in Base.metadata.tables.items():
        if table_name in omitted_tables:
            continue
        if table_name == "malware_scan_attestations":
            test_table = model_table.to_metadata(metadata)
            if malware_table_mutator is not None:
                malware_table_mutator(test_table)
            continue
        if table_name in metadata.tables:
            test_table = metadata.tables[table_name]
        else:
            test_table = Table(table_name, metadata)
        for model_column in model_table.columns:
            qualified_name = f"{table_name}.{model_column.name}"
            if qualified_name == "users.auth_generation" and not user_auth_generation:
                continue
            if model_column.name not in test_table.c and qualified_name != missing_mapped_column:
                test_table.append_column(Column(model_column.name, String()))

    metadata.create_all(engine)
    with engine.begin() as connection:
        if include_malware_table:
            trigger_names = set(
                connection.execute(
                    text(
                        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                        "AND tbl_name = 'malware_scan_attestations'"
                    )
                ).scalars()
            )
            if "trg_malware_scan_attestations_no_update" not in trigger_names:
                connection.execute(
                    text(
                        "CREATE TRIGGER trg_malware_scan_attestations_no_update "
                        "BEFORE UPDATE ON malware_scan_attestations "
                        "BEGIN SELECT RAISE(ABORT, "
                        "'Malware scan attestations are append-only and cannot be updated'); END"
                    )
                )
            if "trg_malware_scan_attestations_no_delete" not in trigger_names:
                connection.execute(
                    text(
                        "CREATE TRIGGER trg_malware_scan_attestations_no_delete "
                        "BEFORE DELETE ON malware_scan_attestations "
                        "BEGIN SELECT RAISE(ABORT, "
                        "'Malware scan attestations are append-only and cannot be deleted'); END"
                    )
                )
        version_column = f"version_num VARCHAR({alembic_version_length})"
        if not alembic_version_nullable:
            version_column += " NOT NULL"
        if alembic_version_primary_key:
            version_column += " PRIMARY KEY"
        connection.execute(text(f"CREATE TABLE alembic_version ({version_column})"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )
        if database_tamper is not None:
            database_tamper(connection)
    with Session(engine) as db:
        return assess_deployment_lineage(db)


def _tamper_malware_receipt_column(table: Table) -> None:
    table.c.receipt_sha256.type = String(63)
    table.c.receipt_sha256.nullable = True


def _tamper_malware_receipt_type(table: Table) -> None:
    table.c.receipt_sha256.type = CHAR(64)


def _tamper_malware_sequence_type(table: Table) -> None:
    table.c.scan_sequence.type = SmallInteger()


def _tamper_malware_sequence_default(table: Table) -> None:
    table.c.scan_sequence.server_default = DefaultClause("1")


def _tamper_malware_check(table: Table) -> None:
    constraint = next(
        item for item in table.constraints if item.name == "ck_malware_scan_attestation_verdict"
    )
    table.constraints.remove(constraint)
    table.append_constraint(CheckConstraint("1 = 1", name="ck_malware_scan_attestation_verdict"))


def _remove_malware_file_sequence_unique(table: Table) -> None:
    constraint = next(
        item
        for item in table.constraints
        if item.name == "uq_malware_scan_attestation_file_sequence"
    )
    table.constraints.remove(constraint)


def _tamper_malware_foreign_key(table: Table) -> None:
    constraint = next(item for item in table.constraints if isinstance(item, ForeignKeyConstraint))
    constraint.ondelete = "CASCADE"


def _remove_malware_verdict_index(table: Table) -> None:
    index = next(
        item for item in table.indexes if item.name == "ix_malware_scan_attestations_verdict"
    )
    table.indexes.remove(index)


def _drop_malware_delete_trigger(connection: Connection) -> None:
    connection.execute(text("DROP TRIGGER trg_malware_scan_attestations_no_delete"))


def _replace_malware_update_trigger(connection: Connection) -> None:
    connection.execute(text("DROP TRIGGER trg_malware_scan_attestations_no_update"))
    connection.execute(
        text(
            "CREATE TRIGGER trg_malware_scan_attestations_no_update "
            "BEFORE UPDATE ON malware_scan_attestations BEGIN SELECT 1; END"
        )
    )


def _add_malware_extra_column(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE malware_scan_attestations ADD COLUMN unexpected TEXT"))


def _rename_alembic_version_column(connection: Connection) -> None:
    connection.execute(text("ALTER TABLE alembic_version RENAME COLUMN version_num TO wrong_name"))


def _valid_postgresql_trigger_rows() -> list[tuple[object, ...]]:
    function_source = (
        "BEGIN RAISE EXCEPTION "
        "'Malware scan attestations are append-only and cannot be mutated' "
        "USING ERRCODE = '55000'; END;"
    )
    return [
        (
            "trg_malware_scan_attestations_no_mutation",
            "O",
            27,
            "classifire_reject_malware_scan_attestation_mutation",
            "plpgsql",
            0,
            0,
            True,
            function_source,
            True,
            True,
        ),
        (
            "trg_malware_scan_attestations_no_truncate",
            "A",
            34,
            "classifire_reject_malware_scan_attestation_mutation",
            "plpgsql",
            0,
            0,
            True,
            function_source,
            True,
            True,
        ),
    ]


def _valid_postgresql_constraint_catalog_rows() -> list[tuple[object, ...]]:
    check_names = sorted(
        str(constraint.name)
        for constraint in Base.metadata.tables["malware_scan_attestations"].constraints
        if isinstance(constraint, CheckConstraint) and constraint.name is not None
    )
    return [(name, "c", True, False, False, False, True) for name in check_names] + [
        (
            "malware_scan_attestations_stored_file_id_fkey",
            "f",
            True,
            True,
            False,
            False,
            True,
        ),
        (
            "malware_scan_attestations_pkey",
            "p",
            True,
            True,
            False,
            False,
            True,
        ),
        *(
            (name, "u", True, True, False, False, True)
            for name in (
                "uq_malware_scan_attestation_file_sequence",
                "uq_malware_scan_attestation_receipt_sha256",
            )
        ),
    ]


def _valid_postgresql_check_dependency_rows() -> list[tuple[object, ...]]:
    return [(True, "a", True, 26), (True, "n", True, 26)]


def _valid_postgresql_relation_column_rows() -> list[tuple[object, ...]]:
    return [
        (name, False, False, "", "")
        for name in sorted(REQUIRED_COLUMNS["malware_scan_attestations"])
    ]


def _valid_postgresql_foreign_key_trigger_rows(
    schema_name: str = "main",
) -> list[tuple[object, ...]]:
    def row(
        trigger_table: str,
        trigger_type: int,
        procedure_name: str,
        related_table: str,
    ) -> tuple[object, ...]:
        return (
            schema_name,
            trigger_table,
            "O",
            trigger_type,
            True,
            False,
            False,
            0,
            True,
            True,
            "pg_catalog",
            procedure_name,
            "internal",
            0,
            True,
            schema_name,
            related_table,
            schema_name,
            "stored_files_pkey",
        )

    return [
        row(
            "malware_scan_attestations",
            5,
            "RI_FKey_check_ins",
            "stored_files",
        ),
        row(
            "malware_scan_attestations",
            17,
            "RI_FKey_check_upd",
            "stored_files",
        ),
        row(
            "stored_files",
            9,
            "RI_FKey_restrict_del",
            "malware_scan_attestations",
        ),
        row(
            "stored_files",
            17,
            "RI_FKey_noaction_upd",
            "malware_scan_attestations",
        ),
    ]


def _valid_postgresql_index_catalog_rows(
    schema_name: str = "main",
) -> list[tuple[object, ...]]:
    qualified_table = f"{schema_name}.malware_scan_attestations"

    def row(
        name: str,
        definition: str,
        *,
        unique: bool,
        primary: bool,
    ) -> tuple[object, ...]:
        return (
            name,
            definition,
            True,
            True,
            True,
            True,
            unique,
            primary,
            True,
            True,
            True,
            True,
            "btree",
        )

    return [
        row(
            "ix_malware_scan_attestations_receipt_sha256",
            "CREATE UNIQUE INDEX ix_malware_scan_attestations_receipt_sha256 "
            f"ON {qualified_table} USING btree (receipt_sha256)",
            unique=True,
            primary=False,
        ),
        row(
            "ix_malware_scan_attestations_stored_file_id",
            "CREATE INDEX ix_malware_scan_attestations_stored_file_id "
            f"ON {qualified_table} USING btree (stored_file_id)",
            unique=False,
            primary=False,
        ),
        row(
            "ix_malware_scan_attestations_verdict",
            "CREATE INDEX ix_malware_scan_attestations_verdict "
            f"ON {qualified_table} USING btree (verdict)",
            unique=False,
            primary=False,
        ),
        row(
            "malware_scan_attestations_pkey",
            "CREATE UNIQUE INDEX malware_scan_attestations_pkey "
            f"ON {qualified_table} USING btree (id)",
            unique=True,
            primary=True,
        ),
        row(
            "uq_malware_scan_attestation_file_sequence",
            "CREATE UNIQUE INDEX uq_malware_scan_attestation_file_sequence "
            f"ON {qualified_table} USING btree (stored_file_id, scan_sequence)",
            unique=True,
            primary=False,
        ),
        row(
            "uq_malware_scan_attestation_receipt_sha256",
            "CREATE UNIQUE INDEX uq_malware_scan_attestation_receipt_sha256 "
            f"ON {qualified_table} USING btree (receipt_sha256)",
            unique=True,
            primary=False,
        ),
    ]


def test_required_inventory_matches_every_registered_model() -> None:
    expected_columns = {
        table_name: frozenset(str(column.name) for column in table.columns)
        for table_name, table in Base.metadata.tables.items()
    }

    assert REQUIRED_COLUMNS == expected_columns
    assert REQUIRED_TABLES == frozenset(expected_columns)
    assert {"customers", "defects"} <= REQUIRED_TABLES


def test_clean_stack_head_is_ready_only_with_required_session_and_journal_schema() -> None:
    assert CLEAN_STACK_HEAD == "0011_malware_scan_attestations"
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
    )
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"
    assert result.database_write_performed is False


@pytest.mark.parametrize(
    ("overrides", "expected_violation"),
    [
        (
            {"alembic_version_length": 31},
            "alembic_version.version_num:unexpected_type",
        ),
        (
            {"alembic_version_nullable": True},
            "alembic_version.version_num:unexpected_nullability",
        ),
        (
            {"alembic_version_primary_key": False},
            "alembic_version.version_num:primary_key_required",
        ),
    ],
)
def test_current_head_requires_exact_alembic_version_contract(
    overrides: dict[str, object],
    expected_violation: str,
) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        **overrides,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert expected_violation in result.schema_violations


def test_malformed_alembic_version_column_returns_unrecognised_lineage() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        database_tamper=_rename_alembic_version_column,
    )

    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
    assert result.alembic_revisions == ()
    assert result.schema_violations == ("alembic_version:column_contract_required",)


@pytest.mark.parametrize(
    ("length", "expected"),
    [
        (64, []),
        (32, ["alembic_version.version_num:unexpected_type"]),
    ],
    ids=("postgresql-varchar-64", "postgresql-varchar-32"),
)
def test_postgresql_alembic_version_contract_requires_varchar_64(
    length: int,
    expected: list[str],
) -> None:
    inspector = SimpleNamespace(
        bind=SimpleNamespace(dialect=postgresql.dialect()),
        get_columns=lambda _table_name: [
            {
                "name": "version_num",
                "type": String(length),
                "nullable": False,
                "default": None,
                "identity": None,
                "computed": None,
            }
        ],
        get_pk_constraint=lambda _table_name: {"constrained_columns": ["version_num"]},
    )

    assert (
        deployment_lineage_module._alembic_version_contract_violations(
            inspector,
            {"alembic_version"},
        )
        == expected
    )


@pytest.mark.parametrize(
    "missing_mapped_table",
    ("customers", "defects", "malware_scan_attestations"),
)
def test_current_head_requires_every_mapped_table(missing_mapped_table: str) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        missing_mapped_table=missing_mapped_table,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_tables == (missing_mapped_table,)


@pytest.mark.parametrize("missing_mapped_column", ("customers.legal_name", "defects.description"))
def test_current_head_requires_every_mapped_column(missing_mapped_column: str) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
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
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        additional_table="monitoring_extensions",
    )
    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"


def test_current_head_ignores_indexes_reflected_as_unique_constraint_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_get_indexes = Inspector.get_indexes

    def get_indexes_with_constraint_duplicates(
        inspector: Inspector,
        table_name: str,
        schema: str | None = None,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        indexes = list(original_get_indexes(inspector, table_name, schema=schema, **kwargs))
        if table_name == "malware_scan_attestations":
            indexes.extend(
                [
                    {
                        "name": "uq_malware_scan_attestation_file_sequence",
                        "column_names": ["stored_file_id", "scan_sequence"],
                        "unique": True,
                        "duplicates_constraint": ("uq_malware_scan_attestation_file_sequence"),
                    },
                    {
                        "name": "uq_malware_scan_attestation_receipt_sha256",
                        "column_names": ["receipt_sha256"],
                        "unique": True,
                        "duplicates_constraint": ("uq_malware_scan_attestation_receipt_sha256"),
                    },
                ]
            )
        return indexes

    monkeypatch.setattr(Inspector, "get_indexes", get_indexes_with_constraint_duplicates)

    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
    )

    assert result.status == "READY"
    assert result.code == "CLEAN_STACK_HEAD_CONFIRMED"


def test_current_head_rejects_cross_schema_malware_stored_file_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_get_foreign_keys = Inspector.get_foreign_keys

    def get_foreign_keys_with_remote_schema(
        inspector: Inspector,
        table_name: str,
        schema: str | None = None,
        **kwargs: object,
    ) -> list[dict[str, object]]:
        foreign_keys = [
            dict(item)
            for item in original_get_foreign_keys(
                inspector,
                table_name,
                schema=schema,
                **kwargs,
            )
        ]
        if table_name == "malware_scan_attestations":
            foreign_keys[0]["referred_schema"] = "untrusted"
        return foreign_keys

    monkeypatch.setattr(
        Inspector,
        "get_foreign_keys",
        get_foreign_keys_with_remote_schema,
    )

    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "malware_scan_attestations.stored_file_id:restrict_foreign_key_required",
    )


def test_postgresql_append_only_trigger_catalog_contract_accepts_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch_rows(
        _bind: object,
        statement: str,
        _parameters: object = None,
    ) -> list[tuple[object, ...]]:
        assert "trigger.tgnargs" in statement
        assert "trigger.tgqual IS NULL" in statement
        assert "trigger.tgattr = ''::pg_catalog.int2vector" in statement
        return _valid_postgresql_trigger_rows()

    monkeypatch.setattr(deployment_lineage_module, "_fetch_rows", fetch_rows)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert (
        deployment_lineage_module._malware_scan_trigger_violations(
            engine,
            dialect_name="postgresql",
        )
        == []
    )


@pytest.mark.parametrize(
    "field_index",
    (9, 10),
    ids=("when-clause", "column-list"),
)
def test_postgresql_append_only_trigger_catalog_contract_rejects_partial_trigger(
    monkeypatch: pytest.MonkeyPatch,
    field_index: int,
) -> None:
    rows = _valid_postgresql_trigger_rows()
    altered_row = list(rows[0])
    altered_row[field_index] = False
    rows[0] = tuple(altered_row)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert deployment_lineage_module._malware_scan_trigger_violations(
        engine,
        dialect_name="postgresql",
    ) == ["malware_scan_attestations:append_only:postgresql_trigger_contract_required"]


def test_current_head_rejects_wrong_malware_column_contract() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        malware_table_mutator=_tamper_malware_receipt_column,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "malware_scan_attestations.receipt_sha256:unexpected_length",
        "malware_scan_attestations.receipt_sha256:unexpected_nullability",
    )


@pytest.mark.parametrize(
    ("mutator", "expected_violation"),
    [
        (
            _tamper_malware_receipt_type,
            "malware_scan_attestations.receipt_sha256:unexpected_type",
        ),
        (
            _tamper_malware_sequence_type,
            "malware_scan_attestations.scan_sequence:unexpected_type",
        ),
    ],
    ids=("char-for-varchar", "smallint-for-integer"),
)
def test_current_head_rejects_noncanonical_malware_column_types(
    mutator: Callable[[Table], None],
    expected_violation: str,
) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        malware_table_mutator=mutator,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert expected_violation in result.schema_violations


def test_current_head_rejects_malware_server_default() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        malware_table_mutator=_tamper_malware_sequence_default,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "malware_scan_attestations.scan_sequence:generated_value_forbidden",
    )


def test_current_head_rejects_extra_malware_column() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        database_tamper=_add_malware_extra_column,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == ("malware_scan_attestations:column_contract_required",)


@pytest.mark.parametrize(
    ("name", "sqltext", "expected"),
    [
        ("ck_malware_scan_attestation_positive_sequence", "scan_sequence > 0", True),
        (
            "ck_malware_scan_attestation_verdict",
            "verdict::text = ANY (ARRAY['clean'::character varying, "
            "'infected'::character varying]::text[])",
            True,
        ),
        (
            "ck_malware_scan_attestation_verdict",
            "verdict::text = ANY (ARRAY['CLEAN'::character varying, "
            "'infected'::character varying]::text[])",
            False,
        ),
        (
            "ck_malware_scan_attestation_scanner_contract",
            "scanner_engine::text = 'CLAMAV'::text AND "
            "protocol::text = 'clamd-idsession-instream-v1'::text",
            False,
        ),
        ("ck_malware_scan_attestation_positive_sequence", "TRUE", False),
    ],
)
def test_postgresql_check_constraint_signatures_fail_closed(
    name: str,
    sqltext: str,
    expected: bool,
) -> None:
    assert (
        deployment_lineage_module._malware_check_constraint_matches(
            dialect_name="postgresql",
            name=name,
            sqltext=sqltext,
        )
        is expected
    )


def test_sql_normalisation_preserves_literals_and_token_boundaries() -> None:
    normalise = deployment_lineage_module._normalise_sql

    assert normalise("value = 'clean'") != normalise("value = 'CLEAN'")
    assert normalise("value = ' '") != normalise("value = ''")
    assert normalise("value IS NULL") != normalise("valueisnull")


@pytest.mark.parametrize(
    ("field_index", "replacement"),
    [(2, False), (3, True), (4, True), (5, True), (6, False)],
    ids=(
        "not-valid",
        "no-inherit",
        "deferrable",
        "initially-deferred",
        "not-enforced",
    ),
)
def test_postgresql_check_constraint_catalog_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    field_index: int,
    replacement: bool,
) -> None:
    rows = _valid_postgresql_constraint_catalog_rows()
    altered = list(rows[0])
    altered[field_index] = replacement
    rows[0] = tuple(altered)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_constraint_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == [f"malware_scan_attestations.{rows[0][0]}:check_constraint_invalid"]


def test_postgresql_foreign_key_catalog_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _valid_postgresql_constraint_catalog_rows()
    foreign_key_index = next(index for index, row in enumerate(rows) if row[1] == "f")
    foreign_key = list(rows[foreign_key_index])
    foreign_key[2] = False
    rows[foreign_key_index] = tuple(foreign_key)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_constraint_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == ["malware_scan_attestations.stored_file_id:restrict_foreign_key_required"]


def test_postgresql_unique_constraint_catalog_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _valid_postgresql_constraint_catalog_rows()
    unique_index = next(index for index, row in enumerate(rows) if row[1] == "u")
    unique = list(rows[unique_index])
    unique[4] = True
    rows[unique_index] = tuple(unique)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_constraint_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == ["malware_scan_attestations:unique_constraint_contract_required"]


def test_postgresql_check_dependency_catalog_accepts_only_table_bindings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: _valid_postgresql_check_dependency_rows(),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert (
        deployment_lineage_module._postgresql_malware_check_dependency_catalog_violations(
            engine,
            schema_name="main",
        )
        == []
    )


def test_postgresql_check_dependency_catalog_rejects_shadow_function_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [*_valid_postgresql_check_dependency_rows(), (False, "n", False, 1)]
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_check_dependency_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == ["malware_scan_attestations:check_constraint_dependency_contract_required"]


def test_postgresql_relation_and_column_catalog_contract_accepts_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch_rows(
        _bind: object,
        statement: str,
        _parameters: object = None,
    ) -> list[tuple[object, ...]]:
        if "relation.relpersistence" in statement:
            return [("p", "r", False, False, False, False, True)]
        assert "attribute.atthasmissing" in statement
        return _valid_postgresql_relation_column_rows()

    monkeypatch.setattr(deployment_lineage_module, "_fetch_rows", fetch_rows)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert (
        deployment_lineage_module._postgresql_malware_relation_catalog_violations(
            engine,
            schema_name="main",
        )
        == []
    )


@pytest.mark.parametrize(
    ("field_index", "replacement"),
    [(0, "u"), (3, True), (5, True), (6, False)],
    ids=(
        "unlogged",
        "row-level-security",
        "rewrite-rule",
        "inherits-or-is-inherited",
    ),
)
def test_postgresql_relation_catalog_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    field_index: int,
    replacement: object,
) -> None:
    relation_row: list[object] = ["p", "r", False, False, False, False, True]
    relation_row[field_index] = replacement

    def fetch_rows(
        _bind: object,
        statement: str,
        _parameters: object = None,
    ) -> list[tuple[object, ...]]:
        if "relation.relpersistence" in statement:
            return [tuple(relation_row)]
        return _valid_postgresql_relation_column_rows()

    monkeypatch.setattr(deployment_lineage_module, "_fetch_rows", fetch_rows)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_relation_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == ["malware_scan_attestations:permanent_plain_relation_required"]


@pytest.mark.parametrize(
    "field_index",
    (1, 2, 3, 4),
    ids=("server-default", "missing-value", "identity", "generated"),
)
def test_postgresql_column_catalog_generated_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    field_index: int,
) -> None:
    column_rows = _valid_postgresql_relation_column_rows()
    altered = list(column_rows[0])
    altered[field_index] = True if field_index < 3 else "x"
    column_rows[0] = tuple(altered)

    def fetch_rows(
        _bind: object,
        statement: str,
        _parameters: object = None,
    ) -> list[tuple[object, ...]]:
        if "relation.relpersistence" in statement:
            return [("p", "r", False, False, False, False, True)]
        return column_rows

    monkeypatch.setattr(deployment_lineage_module, "_fetch_rows", fetch_rows)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_relation_catalog_violations(
        engine,
        schema_name="main",
    )

    assert violations == [
        f"malware_scan_attestations.{column_rows[0][0]}:generated_value_forbidden"
    ]


def test_postgresql_foreign_key_internal_trigger_contract_accepts_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fetch_rows(
        _bind: object,
        statement: str,
        parameters: object = None,
    ) -> list[tuple[object, ...]]:
        assert "trigger_record.tgconstraint = constraint_record.oid" in statement
        assert parameters == {
            "schema_name": "main",
            "table_name": "malware_scan_attestations",
            "constraint_name": "malware_scan_attestations_stored_file_id_fkey",
        }
        return _valid_postgresql_foreign_key_trigger_rows()

    monkeypatch.setattr(deployment_lineage_module, "_fetch_rows", fetch_rows)
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert (
        deployment_lineage_module._postgresql_malware_foreign_key_trigger_catalog_violations(
            engine,
            schema_name="main",
        )
        == []
    )


def test_postgresql_foreign_key_disabled_internal_trigger_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _valid_postgresql_foreign_key_trigger_rows()
    disabled = list(rows[0])
    disabled[2] = "D"
    rows[0] = tuple(disabled)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = (
        deployment_lineage_module._postgresql_malware_foreign_key_trigger_catalog_violations(
            engine,
            schema_name="main",
        )
    )

    assert violations == ["malware_scan_attestations.stored_file_id:restrict_foreign_key_required"]


def test_postgresql_index_catalog_contract_accepts_exact_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: _valid_postgresql_index_catalog_rows(),
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    assert (
        deployment_lineage_module._postgresql_malware_index_catalog_violations(
            inspect(engine),
            engine,
            schema_name="main",
        )
        == []
    )


@pytest.mark.parametrize(
    ("field_index", "replacement"),
    [
        (
            1,
            "CREATE INDEX ix_malware_scan_attestations_verdict ON "
            "main.malware_scan_attestations USING btree (verdict) WHERE verdict = 'clean'",
        ),
        (2, False),
        (9, False),
        (12, "hash"),
    ],
    ids=("altered-definition", "not-valid", "included-column", "wrong-access-method"),
)
def test_postgresql_index_catalog_state_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    field_index: int,
    replacement: object,
) -> None:
    rows = _valid_postgresql_index_catalog_rows()
    altered = list(rows[2])
    altered[field_index] = replacement
    rows[2] = tuple(altered)
    monkeypatch.setattr(
        deployment_lineage_module,
        "_fetch_rows",
        lambda *_args, **_kwargs: rows,
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")

    violations = deployment_lineage_module._postgresql_malware_index_catalog_violations(
        inspect(engine),
        engine,
        schema_name="main",
    )

    assert violations == ["malware_scan_attestations:index_contract_required"]


@pytest.mark.parametrize(
    ("mutator", "expected_violation"),
    [
        (
            _tamper_malware_check,
            "malware_scan_attestations.ck_malware_scan_attestation_verdict:check_constraint_invalid",
        ),
        (
            _remove_malware_file_sequence_unique,
            "malware_scan_attestations:unique_constraint_contract_required",
        ),
        (
            _remove_malware_verdict_index,
            "malware_scan_attestations:index_contract_required",
        ),
        (
            _tamper_malware_foreign_key,
            "malware_scan_attestations.stored_file_id:restrict_foreign_key_required",
        ),
    ],
)
def test_current_head_rejects_malware_constraint_index_and_fk_drift(
    mutator: Callable[[Table], None],
    expected_violation: str,
) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        malware_table_mutator=mutator,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert expected_violation in result.schema_violations


@pytest.mark.parametrize(
    "tamper",
    [_drop_malware_delete_trigger, _replace_malware_update_trigger],
)
def test_current_head_rejects_missing_or_ineffective_append_only_trigger(
    tamper: Callable[[Connection], None],
) -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        database_tamper=tamper,
    )

    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == (
        "malware_scan_attestations:append_only:sqlite_trigger_contract_required",
    )


def test_previous_head_requires_human_session_migration() -> None:
    result = _assessment("0009_visual_validation_receipts", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"
    assert result.missing_tables == (
        "human_sessions",
        "malware_scan_attestations",
    )
    assert result.missing_columns == ("users.auth_generation",)


def test_0008_requires_known_clean_stack_migrations() -> None:
    result = _assessment(
        "0008_retire_legacy_initial_submissions",
        receipt_table=True,
    )

    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"


def test_0010_requires_malware_scan_attestation_migration() -> None:
    result = _assessment(
        "0010_human_sessions",
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
    )

    assert result.status == "BLOCKED"
    assert result.code == "DATABASE_MIGRATION_REQUIRED"
    assert result.missing_tables == ("malware_scan_attestations",)
    assert result.expected_head == CLEAN_STACK_HEAD


def test_current_head_missing_auth_generation_fails_as_schema_drift() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.missing_columns == ("users.auth_generation",)


def test_current_head_rejects_wrong_security_column_contracts() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
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
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        token_hash_unique_index=False,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == ("human_sessions.token_hash:unique_index_required",)


def test_current_head_requires_nonunique_user_lookup_index() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        user_id_index_unique=True,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == ("human_sessions.user_id:nonunique_index_required",)


def test_current_head_requires_cascading_user_foreign_key() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        user_auth_generation=True,
        user_fk_ondelete=None,
    )
    assert result.status == "BLOCKED"
    assert result.schema_violations == ("human_sessions.user_id:cascading_users_fk_required",)


def test_current_head_requires_exact_human_session_id_primary_key() -> None:
    result = _assessment(
        CLEAN_STACK_HEAD,
        receipt_table=True,
        human_session_table=True,
        human_session_primary_key=False,
        user_auth_generation=True,
    )
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_SCHEMA_DRIFT"
    assert result.schema_violations == ("human_sessions.id:primary_key_required",)


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
        CLEAN_STACK_HEAD,
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
        "malware_scan_attestations",
        "physical_model_submission_receipts",
        "visual_validation_receipts",
    )


def test_unknown_revision_fails_closed() -> None:
    result = _assessment("unexpected_revision", receipt_table=True)
    assert result.status == "BLOCKED"
    assert result.code == "DEPLOYMENT_LINEAGE_UNRECOGNISED"
