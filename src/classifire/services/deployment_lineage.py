"""Read-only deployment database lineage assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import DateTime, Integer, String, Text, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.orm import Session

CLEAN_STACK_HEAD = "0010_human_sessions"
PREVIOUS_CLEAN_STACK_HEAD = "0009_visual_validation_receipts"
LEGACY_RETIREMENT_HEAD = "0007_reconcile_adjudicated_admission_lineages"
LEGACY_ADJUDICATED_HEAD = "0006_adjudicated_canonical_admissions"
REQUIRED_TABLES = frozenset(
    {
        "human_sessions",
        "physical_model_admissions",
        "physical_model_submission_receipts",
        "users",
        "visual_validation_receipts",
    }
)
REQUIRED_COLUMNS = {
    "human_sessions": frozenset(
        {
            "auth_generation",
            "created_at",
            "expires_at",
            "id",
            "record_version",
            "revoked_at",
            "revoked_reason",
            "token_hash",
            "token_hint",
            "updated_at",
            "user_id",
        }
    ),
    "users": frozenset({"auth_generation"}),
}
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
}


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


def _column_contract_violations(inspector: Inspector, tables: set[str]) -> list[str]:
    violations: list[str] = []
    for table_name, contracts in _COLUMN_CONTRACTS.items():
        if table_name not in tables:
            continue
        columns = {
            str(column["name"]): column for column in inspector.get_columns(table_name)
        }
        for column_name, (expected_type, expected_length, expected_nullable) in contracts.items():
            column = columns.get(column_name)
            if column is None:
                continue
            actual_type = column["type"]
            if not isinstance(actual_type, expected_type):
                violations.append(f"{table_name}.{column_name}:unexpected_type")
            elif (
                expected_length is not None
                and getattr(actual_type, "length", None) != expected_length
            ):
                violations.append(f"{table_name}.{column_name}:unexpected_length")
            if bool(column["nullable"]) is not expected_nullable:
                violations.append(f"{table_name}.{column_name}:unexpected_nullability")
    return violations


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
        item in missing_columns
        for item in ("human_sessions.token_hash", "human_sessions.user_id")
    ):
        return violations

    indexes = inspector.get_indexes("human_sessions")
    if not any(
        tuple(index.get("column_names") or ()) == ("token_hash",)
        and bool(index.get("unique"))
        for index in indexes
    ):
        violations.append("human_sessions.token_hash:unique_index_required")
    if not any(
        tuple(index.get("column_names") or ()) == ("user_id",)
        and not bool(index.get("unique"))
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


def assess_deployment_schema(bind: Connection | Engine) -> DeploymentSchemaAssessment:
    """Inspect the current security-critical schema without performing writes."""

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
            + _human_session_constraint_violations(inspector, tables, missing_columns)
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
    if revisions == (PREVIOUS_CLEAN_STACK_HEAD,):
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
    "LEGACY_ADJUDICATED_HEAD",
    "LEGACY_RETIREMENT_HEAD",
    "PREVIOUS_CLEAN_STACK_HEAD",
    "RETIRED_TABLES",
    "DeploymentLineageAssessment",
    "DeploymentSchemaAssessment",
    "assess_deployment_schema",
    "assess_deployment_lineage",
]
