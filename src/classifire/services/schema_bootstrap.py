"""Fail-closed application startup schema preparation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from .. import models as _models  # noqa: F401
from .. import physical_models as _physical_models  # noqa: F401
from ..db import Base
from .deployment_lineage import (
    CLEAN_STACK_HEAD,
    assess_deployment_lineage,
    assess_deployment_schema,
)

Environment = Literal["development", "test", "production"]


@dataclass(frozen=True)
class SchemaPreparation:
    code: str
    schema_created: bool
    governed_lineage: bool


class SchemaBootstrapError(RuntimeError):
    """Raised before seeding when the database is unsafe to start against."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


def _unversioned_model_violations(bind: Engine) -> tuple[str, ...]:
    inspector = inspect(bind)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables)
    violations = [
        *(f"missing_table:{table_name}" for table_name in expected_tables - actual_tables),
        *(f"unexpected_table:{table_name}" for table_name in actual_tables - expected_tables),
    ]
    for table_name in expected_tables & actual_tables:
        expected_columns = set(Base.metadata.tables[table_name].columns.keys())
        actual_columns = {str(column["name"]) for column in inspector.get_columns(table_name)}
        violations.extend(
            f"missing_column:{table_name}.{column_name}"
            for column_name in expected_columns - actual_columns
        )
        violations.extend(
            f"unexpected_column:{table_name}.{column_name}"
            for column_name in actual_columns - expected_columns
        )

    critical = assess_deployment_schema(bind)
    violations.extend(f"missing_table:{item}" for item in critical.missing_tables)
    violations.extend(f"missing_column:{item}" for item in critical.missing_columns)
    violations.extend(critical.schema_violations)
    violations.extend(f"unexpected_table:{item}" for item in critical.unexpected_tables)
    return tuple(sorted(set(violations)))


def prepare_application_schema(
    bind: Engine,
    environment: Environment,
    *,
    create_empty: bool = True,
) -> SchemaPreparation:
    """Prepare an empty local DB or verify an existing DB without changing it.

    Production always requires the governed current Alembic head. Development
    and test may create a completely empty schema, or reuse an exact current
    ``create_all`` schema that predates Alembic stamping. Existing databases
    are never repaired implicitly at application startup. Callers performing
    diagnostics can set ``create_empty=False`` to make even empty-database
    inspection strictly read-only.
    """

    tables = set(inspect(bind).get_table_names())
    if not tables:
        if environment == "production":
            raise SchemaBootstrapError(
                "EMPTY_PRODUCTION_DATABASE",
                f"run governed Alembic migrations through {CLEAN_STACK_HEAD} before startup",
            )
        if not create_empty:
            raise SchemaBootstrapError(
                "EMPTY_LOCAL_DATABASE",
                "database is empty; run the explicit create-admin and init "
                "bootstrap sequence before startup",
            )
        Base.metadata.create_all(bind=bind)
        violations = _unversioned_model_violations(bind)
        if violations:
            raise SchemaBootstrapError(
                "CREATED_SCHEMA_INVALID",
                f"new local schema does not match the current model: {', '.join(violations)}",
            )
        return SchemaPreparation(
            code="EMPTY_LOCAL_SCHEMA_CREATED",
            schema_created=True,
            governed_lineage=False,
        )

    if "alembic_version" in tables:
        with Session(bind) as db:
            assessment = assess_deployment_lineage(db)
        if assessment.status != "READY":
            details = [
                f"expected Alembic head {assessment.expected_head}",
                f"found {assessment.alembic_revisions or ('no revision',)}",
            ]
            if assessment.missing_tables:
                details.append(f"missing tables {assessment.missing_tables}")
            if assessment.missing_columns:
                details.append(f"missing columns {assessment.missing_columns}")
            if assessment.schema_violations:
                details.append(f"schema violations {assessment.schema_violations}")
            if assessment.unexpected_tables:
                details.append(f"unexpected tables {assessment.unexpected_tables}")
            raise SchemaBootstrapError(assessment.code, "; ".join(details))
        return SchemaPreparation(
            code="GOVERNED_SCHEMA_CONFIRMED",
            schema_created=False,
            governed_lineage=True,
        )

    if environment == "production":
        raise SchemaBootstrapError(
            "ALEMBIC_VERSION_TABLE_MISSING",
            f"production requires governed Alembic head {CLEAN_STACK_HEAD}",
        )

    violations = _unversioned_model_violations(bind)
    if violations:
        raise SchemaBootstrapError(
            "UNVERSIONED_SCHEMA_NOT_CURRENT",
            "existing local database requires an explicit migration or replacement; "
            f"startup made no schema changes ({', '.join(violations)})",
        )
    return SchemaPreparation(
        code="CURRENT_UNVERSIONED_SCHEMA_REUSED",
        schema_created=False,
        governed_lineage=False,
    )


__all__ = [
    "Environment",
    "SchemaBootstrapError",
    "SchemaPreparation",
    "prepare_application_schema",
]
