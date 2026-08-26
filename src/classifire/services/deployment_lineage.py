"""Read-only deployment database lineage assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Integer, String, Text, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm import Session

from .. import models as _models  # noqa: F401
from .. import physical_models as _physical_models  # noqa: F401
from ..db import Base

CLEAN_STACK_HEAD = "0011_malware_scan_attestations"
PREVIOUS_CLEAN_STACK_HEAD = "0010_human_sessions"
EARLIER_MIGRATION_REQUIRED_HEADS = frozenset(
    {
        "0008_retire_legacy_initial_submissions",
        "0009_visual_validation_receipts",
    }
)
LEGACY_RETIREMENT_HEAD = "0007_reconcile_adjudicated_admission_lineages"
LEGACY_ADJUDICATED_HEAD = "0006_adjudicated_canonical_admissions"
REQUIRED_COLUMNS: dict[str, frozenset[str]] = {
    table_name: frozenset(str(column.name) for column in table.columns)
    for table_name, table in Base.metadata.tables.items()
}
REQUIRED_TABLES = frozenset(REQUIRED_COLUMNS)
RETIRED_TABLES = frozenset({"physical_model_initial_submissions"})

_COLUMN_CONTRACTS: dict[str, dict[str, tuple[type[object], int | None, bool]]] = {
    "human_sessions": {
        "auth_generation": (String, 64, False),
        "created_at": (DateTime, None, False),
        "expires_at": (DateTime, None, False),
        "id": (String, 36, False),
        "record_version": (Integer, None, False),
        "revoked_at": (DateTime, None, True),
        "revoked_reason": (Text, None, True),
        "token_hash": (String, 64, False),
        "token_hint": (String, 12, False),
        "updated_at": (DateTime, None, False),
        "user_id": (String, 36, False),
    },
    "users": {
        "auth_generation": (String, 64, False),
    },
    "malware_scan_attestations": {
        "content_sha256": (String, 64, False),
        "content_size_bytes": (Integer, None, False),
        "created_at": (DateTime, None, False),
        "definition_timestamp": (String, 24, False),
        "definition_version": (BigInteger, None, False),
        "engine_version": (String, 64, False),
        "id": (String, 36, False),
        "metadata_status": (String, 20, False),
        "post_scan_definition_timestamp": (String, 24, True),
        "post_scan_definition_version": (BigInteger, None, True),
        "post_scan_engine_version": (String, 64, True),
        "previous_receipt_sha256": (String, 64, True),
        "protocol": (String, 80, False),
        "receipt_json": (Text, None, False),
        "receipt_sha256": (String, 64, False),
        "scan_sequence": (Integer, None, False),
        "scan_source": (String, 40, False),
        "scanned_at": (DateTime, None, False),
        "scanner_engine": (String, 50, False),
        "stored_file_id": (String, 36, False),
        "verdict": (String, 20, False),
    },
}


def _dollar_quote_delimiter(source: str, start: int) -> str | None:
    if source[start] != "$":
        return None
    end = source.find("$", start + 1)
    if end < 0:
        return None
    tag = source[start + 1 : end]
    if tag and (
        not (tag[0].isalpha() or tag[0] == "_")
        or not all(character.isalnum() or character == "_" for character in tag)
    ):
        return None
    return source[start : end + 1]


def _normalise_sql(value: object) -> str:
    """Normalise layout and unquoted case without changing quoted SQL tokens."""

    source = ("" if value is None else str(value)).strip().rstrip(";")
    result: list[str] = []
    quote: str | None = None
    dollar_delimiter: str | None = None
    pending_space = False
    index = 0
    while index < len(source):
        if dollar_delimiter is not None:
            if source.startswith(dollar_delimiter, index):
                result.append(dollar_delimiter)
                index += len(dollar_delimiter)
                dollar_delimiter = None
            else:
                result.append(source[index])
                index += 1
            continue

        character = source[index]
        if quote is not None:
            result.append(character)
            if character == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    result.append(source[index + 1])
                    index += 2
                    continue
                quote = None
            elif character == chr(92) and index + 1 < len(source):
                result.append(source[index + 1])
                index += 2
                continue
            index += 1
            continue

        delimiter = _dollar_quote_delimiter(source, index) if character == "$" else None
        if delimiter is not None:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            result.append(delimiter)
            dollar_delimiter = delimiter
            index += len(delimiter)
            continue
        if character in {"'", '"'}:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            quote = character
            result.append(character)
        elif character.isspace():
            pending_space = True
        else:
            if pending_space and result:
                result.append(" ")
            pending_space = False
            result.append(character.casefold())
        index += 1
    return "".join(result).rstrip()


_MALWARE_SCAN_ATTESTATION_TABLE = "malware_scan_attestations"
_MALWARE_SCAN_ATTESTATION_CHECKS = {
    str(constraint.name): _normalise_sql(constraint.sqltext)
    for constraint in Base.metadata.tables[_MALWARE_SCAN_ATTESTATION_TABLE].constraints
    if isinstance(constraint, CheckConstraint) and constraint.name is not None
}
_POSTGRESQL_MALWARE_SCAN_ATTESTATION_CHECK_SHA256 = {
    "ck_malware_scan_attestation_content_sha256": (
        "102007384a08abf4b3ed1ea2a4d8a1546b237cdd9563365e9aa50910fe8520ab"
    ),
    "ck_malware_scan_attestation_definition_timestamp_shape": (
        "977b0dcc0a930e8ff7d873182432566dbb51bcd88a587348000f210c885fd92e"
    ),
    "ck_malware_scan_attestation_engine_version_length": (
        "2baaae5b11c54cae8bac7f7e22f2dd62a0989e7247cdbd9b47c0d91b5fa0c6a5"
    ),
    "ck_malware_scan_attestation_metadata_consistency": (
        "0c2d185cece8786bae15e093744f27aadedceae1bd2ec00e72d970f9d83e79f2"
    ),
    "ck_malware_scan_attestation_metadata_status": (
        "713b1a18a6d3c213358ae41f4f61582646572376c63bcf65e23400ad806bdd87"
    ),
    "ck_malware_scan_attestation_nonnegative_size": (
        "d3fdc4bbfced727aa014d3a2be06694b2cd700f2b546f6caad0f7b23047ed81e"
    ),
    "ck_malware_scan_attestation_positive_definition_version": (
        "af730ab0474e231b687b2c6903d05db5c236f3a09908ea37f799d6ab4980a607"
    ),
    "ck_malware_scan_attestation_positive_sequence": (
        "01ce3a19280f5ff85d2e6e5b50511e640f7fb8a0f47a1758ceb3366a22870414"
    ),
    "ck_malware_scan_attestation_post_definition_timestamp_shape": (
        "411f17afb8b02b8ef510adfabebe71c0dd1fd71b808e31b875970e09b57decf0"
    ),
    "ck_malware_scan_attestation_post_definition_version": (
        "e6a45d5480387eff311dc1c1dc0977b5bf7a7cecd112dd32cf819eaef7101bc0"
    ),
    "ck_malware_scan_attestation_previous_receipt": (
        "a954826b77d9075a492b419c7cd0620adcf9ee68c13b5c75b3c1d04d613bd6be"
    ),
    "ck_malware_scan_attestation_previous_receipt_sha256": (
        "09f105e6cd150502796049c8693b59a11f63f487824827637a9091fab9769269"
    ),
    "ck_malware_scan_attestation_receipt_sha256": (
        "10db39f421cc6df122f6aba7bf104291b88fbc7ee4f6fef818996a3d79f3785d"
    ),
    "ck_malware_scan_attestation_scan_source": (
        "ca112778c9ba8e6c89794b5f146fabfd68ec04e556547a12cd9a10c43612088a"
    ),
    "ck_malware_scan_attestation_scanner_contract": (
        "194756fa12ea3338fc52dd090b9e96abf57fcd87d9624702903a44c4303a0def"
    ),
    "ck_malware_scan_attestation_verdict": (
        "63cafbe20be74b875f9dfe903dc0a09da9637f2d083d6f78a8b5db0c0a74726a"
    ),
}
_MALWARE_SCAN_ATTESTATION_UNIQUES = {
    "uq_malware_scan_attestation_file_sequence": ("stored_file_id", "scan_sequence"),
    "uq_malware_scan_attestation_receipt_sha256": ("receipt_sha256",),
}
_MALWARE_SCAN_ATTESTATION_INDEXES = {
    "ix_malware_scan_attestations_receipt_sha256": (("receipt_sha256",), True),
    "ix_malware_scan_attestations_stored_file_id": (("stored_file_id",), False),
    "ix_malware_scan_attestations_verdict": (("verdict",), False),
}
_SQLITE_APPEND_ONLY_TRIGGERS = {
    "trg_malware_scan_attestations_no_update": (
        "CREATE TRIGGER trg_malware_scan_attestations_no_update "
        "BEFORE UPDATE ON malware_scan_attestations "
        "BEGIN SELECT RAISE(ABORT, "
        "'Malware scan attestations are append-only and cannot be updated'); END"
    ),
    "trg_malware_scan_attestations_no_delete": (
        "CREATE TRIGGER trg_malware_scan_attestations_no_delete "
        "BEFORE DELETE ON malware_scan_attestations "
        "BEGIN SELECT RAISE(ABORT, "
        "'Malware scan attestations are append-only and cannot be deleted'); END"
    ),
}
_POSTGRESQL_APPEND_ONLY_TRIGGERS = {
    "trg_malware_scan_attestations_no_mutation": 27,
    "trg_malware_scan_attestations_no_truncate": 34,
}
_POSTGRESQL_APPEND_ONLY_FUNCTION = (
    "BEGIN RAISE EXCEPTION "
    "'Malware scan attestations are append-only and cannot be mutated' "
    "USING ERRCODE = '55000'; END;"
)


@dataclass(frozen=True)
class DeploymentSchemaAssessment:
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...]
    schema_violations: tuple[str, ...]
    unexpected_tables: tuple[str, ...]

    @property
    def is_current(self) -> bool:
        return not (
            self.missing_tables
            or self.missing_columns
            or self.schema_violations
            or self.unexpected_tables
        )


@dataclass(frozen=True)
class DeploymentLineageAssessment:
    status: str
    code: str
    alembic_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...] = ()
    schema_violations: tuple[str, ...] = ()
    unexpected_tables: tuple[str, ...] = ()
    expected_head: str = CLEAN_STACK_HEAD
    database_write_performed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalise_type_declaration(value: object) -> str:
    return " ".join(str(value).strip().casefold().split())


def _column_contract_violations(inspector: Inspector, tables: set[str]) -> list[str]:
    violations: list[str] = []
    for table_name, contracts in _COLUMN_CONTRACTS.items():
        if table_name not in tables:
            continue
        columns = {str(column["name"]): column for column in inspector.get_columns(table_name)}
        for column_name, (_expected_type, expected_length, expected_nullable) in contracts.items():
            column = columns.get(column_name)
            if column is None:
                continue
            actual_type = column["type"]
            expected_model_type = Base.metadata.tables[table_name].columns[column_name].type
            actual_declaration = _normalise_type_declaration(
                actual_type.compile(dialect=inspector.bind.dialect)
            )
            expected_declaration = _normalise_type_declaration(
                expected_model_type.compile(dialect=inspector.bind.dialect)
            )
            if actual_declaration != expected_declaration:
                same_type_family = (
                    actual_declaration.partition("(")[0] == (expected_declaration.partition("(")[0])
                )
                if expected_length is not None and same_type_family:
                    violations.append(f"{table_name}.{column_name}:unexpected_length")
                elif (
                    table_name == _MALWARE_SCAN_ATTESTATION_TABLE
                    and column_name in {"created_at", "scanned_at"}
                    and inspector.bind.dialect.name == "postgresql"
                    and actual_declaration.startswith("timestamp")
                    and expected_declaration.startswith("timestamp")
                ):
                    violations.append(f"{table_name}.{column_name}:timezone_required")
                else:
                    violations.append(f"{table_name}.{column_name}:unexpected_type")
            elif (
                expected_length is not None
                and getattr(actual_type, "length", None) != expected_length
            ):
                violations.append(f"{table_name}.{column_name}:unexpected_length")
            if bool(column["nullable"]) is not expected_nullable:
                violations.append(f"{table_name}.{column_name}:unexpected_nullability")
    return violations


def _alembic_version_contract_violations(
    inspector: Inspector,
    tables: set[str],
) -> list[str]:
    table_name = "alembic_version"
    if table_name not in tables:
        return []
    columns = inspector.get_columns(table_name)
    if {str(column["name"]) for column in columns} != {"version_num"}:
        return [f"{table_name}:column_contract_required"]

    column = columns[0]
    expected_length = 64 if inspector.bind.dialect.name == "postgresql" else 32
    expected_declaration = _normalise_type_declaration(
        String(expected_length).compile(dialect=inspector.bind.dialect)
    )
    actual_type = column["type"]
    actual_declaration = _normalise_type_declaration(
        actual_type.compile(dialect=inspector.bind.dialect)
    )
    violations: list[str] = []
    if actual_declaration != expected_declaration:
        violations.append(f"{table_name}.version_num:unexpected_type")
    if bool(column["nullable"]):
        violations.append(f"{table_name}.version_num:unexpected_nullability")
    if (
        column.get("default") is not None
        or column.get("identity") is not None
        or column.get("computed") is not None
    ):
        violations.append(f"{table_name}.version_num:generated_value_forbidden")
    primary_key = inspector.get_pk_constraint(table_name)
    if tuple(primary_key.get("constrained_columns") or ()) != ("version_num",):
        violations.append(f"{table_name}.version_num:primary_key_required")
    return violations


def _malware_check_constraint_matches(
    *,
    dialect_name: str,
    name: str,
    sqltext: object,
) -> bool:
    normalised = _normalise_sql(sqltext)
    if dialect_name == "sqlite":
        return normalised == _MALWARE_SCAN_ATTESTATION_CHECKS.get(name)
    if dialect_name == "postgresql":
        expected_sha256 = _POSTGRESQL_MALWARE_SCAN_ATTESTATION_CHECK_SHA256.get(name)
        return expected_sha256 is not None and sha256(normalised.encode("utf-8")).hexdigest() == (
            expected_sha256
        )
    return False


def _fetch_rows(
    bind: Connection | Engine,
    statement: str,
    parameters: dict[str, object] | None = None,
) -> list[tuple[object, ...]]:
    if isinstance(bind, Connection):
        return [tuple(row) for row in bind.execute(text(statement), parameters or {}).all()]
    with bind.connect() as connection:
        return [tuple(row) for row in connection.execute(text(statement), parameters or {}).all()]


def _postgresql_malware_relation_catalog_violations(
    bind: Connection | Engine,
    *,
    schema_name: str,
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    relation_rows = _fetch_rows(
        bind,
        "SELECT relation.relpersistence::text, relation.relkind::text, "
        "relation.relispartition, relation.relrowsecurity, relation.relforcerowsecurity, "
        "relation.relhasrules, "
        "NOT EXISTS (SELECT 1 FROM pg_catalog.pg_inherits AS inheritance "
        "WHERE inheritance.inhparent = relation.oid "
        "OR inheritance.inhrelid = relation.oid) "
        "FROM pg_catalog.pg_class AS relation "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = :schema_name AND relation.relname = :table_name",
        {"schema_name": schema_name, "table_name": table_name},
    )
    violations: list[str] = []
    if relation_rows != [("p", "r", False, False, False, False, True)]:
        violations.append(f"{table_name}:permanent_plain_relation_required")

    column_rows = _fetch_rows(
        bind,
        "SELECT attribute.attname, attribute.atthasdef, attribute.atthasmissing, "
        "attribute.attidentity::text, attribute.attgenerated::text "
        "FROM pg_catalog.pg_attribute AS attribute "
        "JOIN pg_catalog.pg_class AS relation ON relation.oid = attribute.attrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = :schema_name AND relation.relname = :table_name "
        "AND attribute.attnum > 0 AND NOT attribute.attisdropped",
        {"schema_name": schema_name, "table_name": table_name},
    )
    column_states = {
        str(name): (has_default, has_missing, str(identity), str(generated))
        for name, has_default, has_missing, identity, generated in column_rows
    }
    if set(column_states) != set(REQUIRED_COLUMNS[table_name]):
        violations.append(f"{table_name}:column_contract_required")
    for name, state in column_states.items():
        if name in REQUIRED_COLUMNS[table_name] and state != (False, False, "", ""):
            violations.append(f"{table_name}.{name}:generated_value_forbidden")
    return violations


def _postgresql_malware_constraint_catalog_violations(
    bind: Connection | Engine,
    *,
    schema_name: str,
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    rows = _fetch_rows(
        bind,
        "SELECT constraint_record.conname, constraint_record.contype::text, "
        "constraint_record.convalidated, constraint_record.connoinherit, "
        "constraint_record.condeferrable, constraint_record.condeferred, "
        "COALESCE((pg_catalog.to_jsonb(constraint_record) ->> 'conenforced')::boolean, TRUE) "
        "FROM pg_catalog.pg_constraint AS constraint_record "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.oid = constraint_record.conrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = :schema_name "
        "AND relation.relname = :table_name "
        "AND constraint_record.contype IN ('c', 'f', 'p', 'u')",
        {"schema_name": schema_name, "table_name": table_name},
    )
    check_states: dict[str, tuple[object, ...]] = {}
    foreign_key_states: dict[str, tuple[object, ...]] = {}
    primary_key_states: dict[str, tuple[object, ...]] = {}
    unique_states: dict[str, tuple[object, ...]] = {}
    for (
        name,
        constraint_type,
        validated,
        no_inherit,
        deferrable,
        deferred,
        enforced,
    ) in rows:
        state = (validated, no_inherit, deferrable, deferred, enforced)
        if str(constraint_type) == "c":
            check_states[str(name)] = state
        elif str(constraint_type) == "f":
            foreign_key_states[str(name)] = state
        elif str(constraint_type) == "p":
            primary_key_states[str(name)] = state
        elif str(constraint_type) == "u":
            unique_states[str(name)] = state

    violations: list[str] = []
    if set(check_states) != set(_MALWARE_SCAN_ATTESTATION_CHECKS):
        violations.append(f"{table_name}:check_constraint_set_invalid")
    else:
        for name, catalog_state in check_states.items():
            if catalog_state != (True, False, False, False, True):
                violations.append(f"{table_name}.{name}:check_constraint_invalid")
    if foreign_key_states != {
        "malware_scan_attestations_stored_file_id_fkey": (
            True,
            True,
            False,
            False,
            True,
        )
    }:
        violations.append(f"{table_name}.stored_file_id:restrict_foreign_key_required")
    if primary_key_states != {"malware_scan_attestations_pkey": (True, True, False, False, True)}:
        violations.append(f"{table_name}.id:primary_key_required")
    expected_uniques = {
        name: (True, True, False, False, True) for name in _MALWARE_SCAN_ATTESTATION_UNIQUES
    }
    if unique_states != expected_uniques:
        violations.append(f"{table_name}:unique_constraint_contract_required")
    return violations


def _postgresql_malware_check_dependency_catalog_violations(
    bind: Connection | Engine,
    *,
    schema_name: str,
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    rows = _fetch_rows(
        bind,
        "SELECT dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass, "
        "dependency.deptype::text, dependency.refobjid = relation.oid, COUNT(*) "
        "FROM pg_catalog.pg_depend AS dependency "
        "JOIN pg_catalog.pg_constraint AS constraint_record "
        "ON dependency.classid = 'pg_catalog.pg_constraint'::pg_catalog.regclass "
        "AND dependency.objid = constraint_record.oid "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.oid = constraint_record.conrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "WHERE namespace.nspname = :schema_name AND relation.relname = :table_name "
        "AND constraint_record.contype = 'c' "
        "GROUP BY dependency.refclassid, dependency.deptype, "
        "dependency.refobjid, relation.oid",
        {"schema_name": schema_name, "table_name": table_name},
    )
    if len(rows) != 2 or set(rows) != {
        (True, "a", True, 26),
        (True, "n", True, 26),
    }:
        return [f"{table_name}:check_constraint_dependency_contract_required"]
    return []


def _postgresql_malware_foreign_key_trigger_catalog_violations(
    bind: Connection | Engine,
    *,
    schema_name: str,
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    constraint_name = "malware_scan_attestations_stored_file_id_fkey"
    rows = _fetch_rows(
        bind,
        "SELECT trigger_namespace.nspname, trigger_relation.relname, "
        "trigger_record.tgenabled::text, trigger_record.tgtype, "
        "trigger_record.tgisinternal, trigger_record.tgdeferrable, "
        "trigger_record.tginitdeferred, trigger_record.tgnargs, "
        "trigger_record.tgqual IS NULL, "
        "trigger_record.tgattr = ''::pg_catalog.int2vector, "
        "procedure_namespace.nspname, procedure_record.proname, "
        "language_record.lanname, procedure_record.pronargs, "
        "procedure_record.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype, "
        "related_namespace.nspname, related_relation.relname, "
        "index_namespace.nspname, index_relation.relname "
        "FROM pg_catalog.pg_constraint AS constraint_record "
        "JOIN pg_catalog.pg_class AS constrained_relation "
        "ON constrained_relation.oid = constraint_record.conrelid "
        "JOIN pg_catalog.pg_namespace AS constrained_namespace "
        "ON constrained_namespace.oid = constrained_relation.relnamespace "
        "JOIN pg_catalog.pg_trigger AS trigger_record "
        "ON trigger_record.tgconstraint = constraint_record.oid "
        "JOIN pg_catalog.pg_class AS trigger_relation "
        "ON trigger_relation.oid = trigger_record.tgrelid "
        "JOIN pg_catalog.pg_namespace AS trigger_namespace "
        "ON trigger_namespace.oid = trigger_relation.relnamespace "
        "JOIN pg_catalog.pg_proc AS procedure_record "
        "ON procedure_record.oid = trigger_record.tgfoid "
        "JOIN pg_catalog.pg_namespace AS procedure_namespace "
        "ON procedure_namespace.oid = procedure_record.pronamespace "
        "JOIN pg_catalog.pg_language AS language_record "
        "ON language_record.oid = procedure_record.prolang "
        "LEFT JOIN pg_catalog.pg_class AS related_relation "
        "ON related_relation.oid = trigger_record.tgconstrrelid "
        "LEFT JOIN pg_catalog.pg_namespace AS related_namespace "
        "ON related_namespace.oid = related_relation.relnamespace "
        "LEFT JOIN pg_catalog.pg_class AS index_relation "
        "ON index_relation.oid = trigger_record.tgconstrindid "
        "LEFT JOIN pg_catalog.pg_namespace AS index_namespace "
        "ON index_namespace.oid = index_relation.relnamespace "
        "WHERE constrained_namespace.nspname = :schema_name "
        "AND constrained_relation.relname = :table_name "
        "AND constraint_record.contype = 'f' "
        "AND constraint_record.conname = :constraint_name",
        {
            "schema_name": schema_name,
            "table_name": table_name,
            "constraint_name": constraint_name,
        },
    )
    expected_roles = {
        (table_name, 5, "RI_FKey_check_ins", "stored_files"),
        (table_name, 17, "RI_FKey_check_upd", "stored_files"),
        ("stored_files", 9, "RI_FKey_restrict_del", table_name),
        ("stored_files", 17, "RI_FKey_noaction_upd", table_name),
    }
    actual_roles: set[tuple[str, int, str, str]] = set()
    for row in rows:
        (
            trigger_schema,
            trigger_table,
            enabled,
            trigger_type,
            is_internal,
            deferrable,
            initially_deferred,
            trigger_argument_count,
            has_no_when_clause,
            applies_to_all_columns,
            procedure_schema,
            procedure_name,
            language_name,
            procedure_argument_count,
            returns_trigger,
            related_schema,
            related_table,
            index_schema,
            index_name,
        ) = row
        if (
            str(trigger_schema) != schema_name
            or str(enabled) not in {"O", "A"}
            or not isinstance(trigger_type, int)
            or isinstance(trigger_type, bool)
            or is_internal is not True
            or deferrable is not False
            or initially_deferred is not False
            or not isinstance(trigger_argument_count, int)
            or isinstance(trigger_argument_count, bool)
            or trigger_argument_count != 0
            or has_no_when_clause is not True
            or applies_to_all_columns is not True
            or procedure_schema != "pg_catalog"
            or language_name != "internal"
            or not isinstance(procedure_argument_count, int)
            or isinstance(procedure_argument_count, bool)
            or procedure_argument_count != 0
            or returns_trigger is not True
            or str(related_schema) != schema_name
            or str(index_schema) != schema_name
            or index_name != "stored_files_pkey"
        ):
            return [f"{table_name}.stored_file_id:restrict_foreign_key_required"]
        actual_roles.add(
            (
                str(trigger_table),
                trigger_type,
                str(procedure_name),
                str(related_table),
            )
        )
    if len(rows) != 4 or actual_roles != expected_roles:
        return [f"{table_name}.stored_file_id:restrict_foreign_key_required"]
    return []


def _postgresql_malware_index_catalog_violations(
    inspector: Inspector,
    bind: Connection | Engine,
    *,
    schema_name: str,
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    rows = _fetch_rows(
        bind,
        "SELECT index_relation.relname, "
        "pg_catalog.pg_get_indexdef(index_record.indexrelid), "
        "index_record.indisvalid, index_record.indisready, index_record.indislive, "
        "index_record.indimmediate, index_record.indisunique, "
        "index_record.indisprimary, NOT index_record.indisexclusion, "
        "index_record.indnkeyatts = index_record.indnatts, "
        "index_record.indpred IS NULL, index_record.indexprs IS NULL, "
        "access_method.amname "
        "FROM pg_catalog.pg_index AS index_record "
        "JOIN pg_catalog.pg_class AS relation "
        "ON relation.oid = index_record.indrelid "
        "JOIN pg_catalog.pg_namespace AS namespace "
        "ON namespace.oid = relation.relnamespace "
        "JOIN pg_catalog.pg_class AS index_relation "
        "ON index_relation.oid = index_record.indexrelid "
        "JOIN pg_catalog.pg_am AS access_method "
        "ON access_method.oid = index_relation.relam "
        "WHERE namespace.nspname = :schema_name AND relation.relname = :table_name",
        {"schema_name": schema_name, "table_name": table_name},
    )
    actual = {
        str(name): (
            _normalise_sql(definition),
            valid,
            ready,
            live,
            immediate,
            unique,
            primary,
            not_exclusion,
            all_columns_are_keys,
            has_no_predicate,
            has_no_expression,
            str(access_method),
        )
        for (
            name,
            definition,
            valid,
            ready,
            live,
            immediate,
            unique,
            primary,
            not_exclusion,
            all_columns_are_keys,
            has_no_predicate,
            has_no_expression,
            access_method,
        ) in rows
    }
    preparer = inspector.bind.dialect.identifier_preparer
    qualified_table = (
        f"{preparer.quote_schema(schema_name)}.{preparer.quote(table_name)}"
        if schema_name
        else preparer.quote(table_name)
    )

    def expected(definition: str, *, unique: bool, primary: bool) -> tuple[object, ...]:
        return (
            _normalise_sql(definition),
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

    expected_indexes = {
        "ix_malware_scan_attestations_receipt_sha256": expected(
            "CREATE UNIQUE INDEX ix_malware_scan_attestations_receipt_sha256 "
            f"ON {qualified_table} USING btree (receipt_sha256)",
            unique=True,
            primary=False,
        ),
        "ix_malware_scan_attestations_stored_file_id": expected(
            "CREATE INDEX ix_malware_scan_attestations_stored_file_id "
            f"ON {qualified_table} USING btree (stored_file_id)",
            unique=False,
            primary=False,
        ),
        "ix_malware_scan_attestations_verdict": expected(
            "CREATE INDEX ix_malware_scan_attestations_verdict "
            f"ON {qualified_table} USING btree (verdict)",
            unique=False,
            primary=False,
        ),
        "malware_scan_attestations_pkey": expected(
            "CREATE UNIQUE INDEX malware_scan_attestations_pkey "
            f"ON {qualified_table} USING btree (id)",
            unique=True,
            primary=True,
        ),
        "uq_malware_scan_attestation_file_sequence": expected(
            "CREATE UNIQUE INDEX uq_malware_scan_attestation_file_sequence "
            f"ON {qualified_table} USING btree (stored_file_id, scan_sequence)",
            unique=True,
            primary=False,
        ),
        "uq_malware_scan_attestation_receipt_sha256": expected(
            "CREATE UNIQUE INDEX uq_malware_scan_attestation_receipt_sha256 "
            f"ON {qualified_table} USING btree (receipt_sha256)",
            unique=True,
            primary=False,
        ),
    }
    if actual != expected_indexes:
        return [f"{table_name}:index_contract_required"]
    return []


def _malware_scan_trigger_violations(
    bind: Connection | Engine,
    *,
    dialect_name: str,
) -> list[str]:
    prefix = f"{_MALWARE_SCAN_ATTESTATION_TABLE}:append_only"
    if dialect_name == "sqlite":
        rows = _fetch_rows(
            bind,
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' AND tbl_name = :table_name",
            {"table_name": _MALWARE_SCAN_ATTESTATION_TABLE},
        )
        actual = {str(name): _normalise_sql(sql) for name, sql in rows}
        expected = {name: _normalise_sql(sql) for name, sql in _SQLITE_APPEND_ONLY_TRIGGERS.items()}
        if actual != expected:
            return [f"{prefix}:sqlite_trigger_contract_required"]
        return []
    if dialect_name == "postgresql":
        rows = _fetch_rows(
            bind,
            "SELECT trigger.tgname, trigger.tgenabled, trigger.tgtype, "
            "procedure.proname, language.lanname, procedure.pronargs, "
            "trigger.tgnargs, "
            "procedure.prorettype = 'pg_catalog.trigger'::pg_catalog.regtype, "
            "procedure.prosrc, trigger.tgqual IS NULL, "
            "trigger.tgattr = ''::pg_catalog.int2vector "
            "FROM pg_catalog.pg_trigger AS trigger "
            "JOIN pg_catalog.pg_class AS relation ON relation.oid = trigger.tgrelid "
            "JOIN pg_catalog.pg_namespace AS namespace "
            "ON namespace.oid = relation.relnamespace "
            "JOIN pg_catalog.pg_proc AS procedure ON procedure.oid = trigger.tgfoid "
            "JOIN pg_catalog.pg_language AS language "
            "ON language.oid = procedure.prolang "
            "WHERE namespace.nspname = :schema_name "
            "AND relation.relname = :table_name AND NOT trigger.tgisinternal",
            {
                "schema_name": inspect(bind).default_schema_name,
                "table_name": _MALWARE_SCAN_ATTESTATION_TABLE,
            },
        )
        if {str(row[0]) for row in rows} != set(_POSTGRESQL_APPEND_ONLY_TRIGGERS):
            return [f"{prefix}:postgresql_trigger_contract_required"]
        expected_function = _normalise_sql(_POSTGRESQL_APPEND_ONLY_FUNCTION)
        for row in rows:
            (
                name,
                enabled,
                trigger_type,
                procedure_name,
                language_name,
                procedure_argument_count,
                trigger_argument_count,
                returns_trigger,
                procedure_source,
                has_no_when_clause,
                applies_to_all_columns,
            ) = row
            if (
                not isinstance(trigger_type, int)
                or isinstance(trigger_type, bool)
                or trigger_type != _POSTGRESQL_APPEND_ONLY_TRIGGERS[str(name)]
                or str(enabled) not in {"O", "A"}
                or procedure_name != "classifire_reject_malware_scan_attestation_mutation"
                or language_name != "plpgsql"
                or not isinstance(procedure_argument_count, int)
                or isinstance(procedure_argument_count, bool)
                or procedure_argument_count != 0
                or not isinstance(trigger_argument_count, int)
                or isinstance(trigger_argument_count, bool)
                or trigger_argument_count != 0
                or returns_trigger is not True
                or _normalise_sql(procedure_source) != expected_function
                or has_no_when_clause is not True
                or applies_to_all_columns is not True
            ):
                return [f"{prefix}:postgresql_trigger_contract_required"]
        return []
    return [f"{prefix}:unsupported_dialect"]


def _human_session_constraint_violations(
    inspector: Inspector, tables: set[str], missing_columns: tuple[str, ...]
) -> list[str]:
    if "human_sessions" not in tables:
        return []

    violations: list[str] = []
    if "human_sessions.id" not in missing_columns:
        primary_key = inspector.get_pk_constraint("human_sessions")
        if tuple(primary_key.get("constrained_columns") or ()) != ("id",):
            violations.append("human_sessions.id:primary_key_required")

    if any(
        item in missing_columns for item in ("human_sessions.token_hash", "human_sessions.user_id")
    ):
        return violations

    indexes = inspector.get_indexes("human_sessions")
    if not any(
        tuple(index.get("column_names") or ()) == ("token_hash",) and bool(index.get("unique"))
        for index in indexes
    ):
        violations.append("human_sessions.token_hash:unique_index_required")
    if not any(
        tuple(index.get("column_names") or ()) == ("user_id",) and not bool(index.get("unique"))
        for index in indexes
    ):
        violations.append("human_sessions.user_id:nonunique_index_required")

    foreign_keys = inspector.get_foreign_keys("human_sessions")
    has_cascading_user_fk = any(
        tuple(foreign_key.get("constrained_columns") or ()) == ("user_id",)
        and foreign_key.get("referred_table") == "users"
        and tuple(foreign_key.get("referred_columns") or ()) == ("id",)
        and str((foreign_key.get("options") or {}).get("ondelete", "")).upper() == "CASCADE"
        for foreign_key in foreign_keys
    )
    if not has_cascading_user_fk:
        violations.append("human_sessions.user_id:cascading_users_fk_required")
    return violations


def _malware_scan_attestation_constraint_violations(
    inspector: Inspector,
    bind: Connection | Engine,
    tables: set[str],
    missing_columns: tuple[str, ...],
) -> list[str]:
    table_name = _MALWARE_SCAN_ATTESTATION_TABLE
    if table_name not in tables:
        return []

    violations: list[str] = []
    column_records = {str(column["name"]): column for column in inspector.get_columns(table_name)}
    if set(column_records) != set(REQUIRED_COLUMNS[table_name]):
        violations.append(f"{table_name}:column_contract_required")
    for column_name in set(column_records) & set(REQUIRED_COLUMNS[table_name]):
        column = column_records[column_name]
        if (
            column.get("default") is not None
            or column.get("identity") is not None
            or column.get("computed") is not None
            or column.get("autoincrement") not in {None, False}
        ):
            violations.append(f"{table_name}.{column_name}:generated_value_forbidden")
    if any(value.startswith(f"{table_name}.") for value in missing_columns):
        return sorted(set(violations))

    primary_key = inspector.get_pk_constraint(table_name)
    if tuple(primary_key.get("constrained_columns") or ()) != ("id",):
        violations.append(f"{table_name}.id:primary_key_required")

    check_records = {
        str(constraint.get("name") or ""): constraint
        for constraint in inspector.get_check_constraints(table_name)
    }
    if set(check_records) != set(_MALWARE_SCAN_ATTESTATION_CHECKS):
        violations.append(f"{table_name}:check_constraint_set_invalid")
    else:
        for name, constraint in check_records.items():
            if constraint.get("dialect_options") or not _malware_check_constraint_matches(
                dialect_name=inspector.bind.dialect.name,
                name=name,
                sqltext=constraint.get("sqltext"),
            ):
                violations.append(f"{table_name}.{name}:check_constraint_invalid")

    unique_constraints = {
        str(constraint.get("name") or ""): tuple(constraint.get("column_names") or ())
        for constraint in inspector.get_unique_constraints(table_name)
    }
    if unique_constraints != _MALWARE_SCAN_ATTESTATION_UNIQUES:
        violations.append(f"{table_name}:unique_constraint_contract_required")

    indexes = {
        str(index.get("name") or ""): (
            tuple(index.get("column_names") or ()),
            bool(index.get("unique")),
        )
        for index in inspector.get_indexes(table_name)
        if not index.get("duplicates_constraint")
    }
    if indexes != _MALWARE_SCAN_ATTESTATION_INDEXES:
        violations.append(f"{table_name}:index_contract_required")

    if inspector.bind.dialect.name == "postgresql":
        foreign_keys = inspector.get_foreign_keys(
            table_name,
            postgresql_ignore_search_path=True,
        )
    else:
        foreign_keys = inspector.get_foreign_keys(table_name)
    if len(foreign_keys) != 1:
        violations.append(f"{table_name}.stored_file_id:restrict_foreign_key_required")
    else:
        foreign_key = foreign_keys[0]
        if not (
            tuple(foreign_key.get("constrained_columns") or ()) == ("stored_file_id",)
            and foreign_key.get("referred_table") == "stored_files"
            and foreign_key.get("referred_schema") is None
            and tuple(foreign_key.get("referred_columns") or ()) == ("id",)
            and str((foreign_key.get("options") or {}).get("ondelete", "")).upper() == "RESTRICT"
        ):
            violations.append(f"{table_name}.stored_file_id:restrict_foreign_key_required")

    if inspector.bind.dialect.name == "postgresql":
        violations.extend(
            _postgresql_malware_relation_catalog_violations(
                bind,
                schema_name=inspector.default_schema_name or "",
            )
        )
        violations.extend(
            _postgresql_malware_constraint_catalog_violations(
                bind,
                schema_name=inspector.default_schema_name or "",
            )
        )
        violations.extend(
            _postgresql_malware_check_dependency_catalog_violations(
                bind,
                schema_name=inspector.default_schema_name or "",
            )
        )
        violations.extend(
            _postgresql_malware_foreign_key_trigger_catalog_violations(
                bind,
                schema_name=inspector.default_schema_name or "",
            )
        )
        violations.extend(
            _postgresql_malware_index_catalog_violations(
                inspector,
                bind,
                schema_name=inspector.default_schema_name or "",
            )
        )
    violations.extend(
        _malware_scan_trigger_violations(
            bind,
            dialect_name=inspector.bind.dialect.name,
        )
    )
    return sorted(set(violations))


def assess_deployment_schema(bind: Connection | Engine) -> DeploymentSchemaAssessment:
    """Inspect the complete mapped schema and critical constraints without writes."""

    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    missing_tables = tuple(sorted(REQUIRED_TABLES - tables))
    missing_columns = tuple(
        sorted(
            f"{table_name}.{column_name}"
            for table_name, required_columns in REQUIRED_COLUMNS.items()
            if table_name in tables
            for column_name in (
                required_columns
                - {str(column["name"]) for column in inspector.get_columns(table_name)}
            )
        )
    )
    schema_violations = tuple(
        sorted(
            _column_contract_violations(inspector, tables)
            + _alembic_version_contract_violations(inspector, tables)
            + _human_session_constraint_violations(inspector, tables, missing_columns)
            + _malware_scan_attestation_constraint_violations(
                inspector,
                bind,
                tables,
                missing_columns,
            )
        )
    )
    return DeploymentSchemaAssessment(
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        schema_violations=schema_violations,
        unexpected_tables=tuple(sorted(RETIRED_TABLES & tables)),
    )


def assess_deployment_lineage(db: Session) -> DeploymentLineageAssessment:
    """Inspect only schema metadata; never stamp or migrate the database."""

    bind = db.connection()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    schema = assess_deployment_schema(bind)
    missing_tables = schema.missing_tables
    missing_columns = schema.missing_columns
    schema_violations = schema.schema_violations
    if "alembic_version" not in tables:
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="ALEMBIC_VERSION_TABLE_MISSING",
            alembic_revisions=(),
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
        )
    if "alembic_version:column_contract_required" in schema_violations:
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DEPLOYMENT_LINEAGE_UNRECOGNISED",
            alembic_revisions=(),
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
            unexpected_tables=schema.unexpected_tables,
        )
    revisions = tuple(
        sorted(str(row[0]) for row in db.execute(text("SELECT version_num FROM alembic_version")))
    )
    unexpected_tables = schema.unexpected_tables
    if (
        revisions == (CLEAN_STACK_HEAD,)
        and not missing_tables
        and not missing_columns
        and not schema_violations
        and not unexpected_tables
    ):
        return DeploymentLineageAssessment(
            status="READY",
            code="CLEAN_STACK_HEAD_CONFIRMED",
            alembic_revisions=revisions,
            missing_tables=(),
            missing_columns=(),
            schema_violations=(),
        )
    if revisions == (CLEAN_STACK_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DEPLOYMENT_SCHEMA_DRIFT",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
            unexpected_tables=unexpected_tables,
        )
    if revisions == (PREVIOUS_CLEAN_STACK_HEAD,) or (
        len(revisions) == 1 and revisions[0] in EARLIER_MIGRATION_REQUIRED_HEADS
    ):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DATABASE_MIGRATION_REQUIRED",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
            unexpected_tables=unexpected_tables,
        )
    if revisions == (LEGACY_RETIREMENT_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code=(
                "LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED"
                if unexpected_tables
                else "DATABASE_MIGRATION_REQUIRED"
            ),
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
            unexpected_tables=unexpected_tables,
        )
    if revisions == (LEGACY_ADJUDICATED_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="LEGACY_LINEAGE_REHEARSAL_REQUIRED",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            schema_violations=schema_violations,
        )
    return DeploymentLineageAssessment(
        status="BLOCKED",
        code="DEPLOYMENT_LINEAGE_UNRECOGNISED",
        alembic_revisions=revisions,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        schema_violations=schema_violations,
        unexpected_tables=unexpected_tables,
    )


__all__ = [
    "CLEAN_STACK_HEAD",
    "EARLIER_MIGRATION_REQUIRED_HEADS",
    "LEGACY_ADJUDICATED_HEAD",
    "LEGACY_RETIREMENT_HEAD",
    "PREVIOUS_CLEAN_STACK_HEAD",
    "RETIRED_TABLES",
    "DeploymentLineageAssessment",
    "DeploymentSchemaAssessment",
    "assess_deployment_schema",
    "assess_deployment_lineage",
]
