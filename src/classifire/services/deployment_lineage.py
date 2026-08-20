"""Read-only deployment database lineage assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

CLEAN_STACK_HEAD = "0007_reconcile_adjudicated_admission_lineages"
LEGACY_ADJUDICATED_HEAD = "0006_adjudicated_canonical_admissions"
REQUIRED_TABLES = frozenset(
    {
        "physical_model_admissions",
        "physical_model_submission_receipts",
    }
)


@dataclass(frozen=True)
class DeploymentLineageAssessment:
    status: str
    code: str
    alembic_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]
    expected_head: str = CLEAN_STACK_HEAD
    database_write_performed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_deployment_lineage(db: Session) -> DeploymentLineageAssessment:
    """Inspect only schema metadata; never stamp or migrate the database."""

    bind = db.connection()
    tables = set(inspect(bind).get_table_names())
    if "alembic_version" not in tables:
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="ALEMBIC_VERSION_TABLE_MISSING",
            alembic_revisions=(),
            missing_tables=tuple(sorted(REQUIRED_TABLES - tables)),
        )
    revisions = tuple(
        sorted(str(row[0]) for row in db.execute(text("SELECT version_num FROM alembic_version")))
    )
    missing_tables = tuple(sorted(REQUIRED_TABLES - tables))
    if revisions == (CLEAN_STACK_HEAD,) and not missing_tables:
        return DeploymentLineageAssessment(
            status="READY",
            code="CLEAN_STACK_HEAD_CONFIRMED",
            alembic_revisions=revisions,
            missing_tables=(),
        )
    if revisions == (LEGACY_ADJUDICATED_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="LEGACY_LINEAGE_REHEARSAL_REQUIRED",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
        )
    return DeploymentLineageAssessment(
        status="BLOCKED",
        code="DEPLOYMENT_LINEAGE_UNRECOGNISED",
        alembic_revisions=revisions,
        missing_tables=missing_tables,
    )


__all__ = [
    "CLEAN_STACK_HEAD",
    "LEGACY_ADJUDICATED_HEAD",
    "DeploymentLineageAssessment",
    "assess_deployment_lineage",
]
