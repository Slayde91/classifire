"""Read-only deployment database lineage assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from .. import models, physical_models  # noqa: F401
from ..db import Base

CLEAN_STACK_HEAD = "0018_shared_malware_containment"
PREVIOUS_CLEAN_STACK_HEAD = "0017_technical_intake_drafts"
PRE_TECHNICAL_INTAKE_DRAFT_CLEAN_STACK_HEAD = "0016_parser_attestation_v2"
PRE_PARSER_ATTESTATION_CLEAN_STACK_HEAD = "0015_technical_parser_invocation_provenance"
PRE_PARSER_PROVENANCE_CLEAN_STACK_HEAD = "0014_technical_extraction_foundation"
PRE_TECHNICAL_EXTRACTION_CLEAN_STACK_HEAD = "0013_technical_intake_batches"
PRE_SOURCE_EXTRACTION_CLEAN_STACK_HEAD = "0012_technical_source_registration"
PRE_SOURCE_REGISTRATION_CLEAN_STACK_HEAD = "0011_technical_document_relationships"
PRE_RELATIONSHIP_CLEAN_STACK_HEAD = "0010_release_publication_slot"
PRE_PUBLICATION_CLEAN_STACK_HEAD = "0009_visual_validation_receipts"
PRE_RETIREMENT_CLEAN_STACK_HEAD = "0007_reconcile_adjudicated_admission_lineages"
LEGACY_ADJUDICATED_HEAD = "0006_adjudicated_canonical_admissions"
REQUIRED_TABLES = frozenset(Base.metadata.tables)
REQUIRED_COLUMNS = {
    table_name: frozenset(column.name for column in table.columns)
    for table_name, table in Base.metadata.tables.items()
}
RETIRED_TABLES = frozenset({"physical_model_initial_submissions"})


@dataclass(frozen=True)
class DeploymentLineageAssessment:
    status: str
    code: str
    alembic_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]
    missing_columns: tuple[str, ...] = ()
    unexpected_tables: tuple[str, ...] = ()
    expected_head: str = CLEAN_STACK_HEAD
    database_write_performed: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def assess_deployment_lineage(db: Session) -> DeploymentLineageAssessment:
    """Inspect only schema metadata; never stamp or migrate the database."""

    bind = db.connection()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
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
    missing_columns = tuple(
        sorted(
            f"{table_name}.{column_name}"
            for table_name, required_columns in REQUIRED_COLUMNS.items()
            if table_name in tables
            for column_name in (
                required_columns - {column["name"] for column in inspector.get_columns(table_name)}
            )
        )
    )
    unexpected_tables = tuple(sorted(RETIRED_TABLES & tables))
    release_columns = (
        {column["name"] for column in inspector.get_columns("library_releases")}
        if "library_releases" in tables
        else set()
    )
    release_indexes = (
        {index["name"]: index for index in inspector.get_indexes("library_releases")}
        if "library_releases" in tables
        else {}
    )
    publication_index = release_indexes.get("uq_library_release_active_publication_slot")
    publication_guard_present = (
        "active_publication_slot" in release_columns
        and publication_index is not None
        and bool(publication_index.get("unique"))
    )
    if (
        revisions == (CLEAN_STACK_HEAD,)
        and not missing_tables
        and not missing_columns
        and not unexpected_tables
        and publication_guard_present
    ):
        return DeploymentLineageAssessment(
            status="READY",
            code="CLEAN_STACK_HEAD_CONFIRMED",
            alembic_revisions=revisions,
            missing_tables=(),
        )
    if revisions == (CLEAN_STACK_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DEPLOYMENT_SCHEMA_DRIFT",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            missing_columns=missing_columns,
            unexpected_tables=unexpected_tables,
        )
    if revisions in {
        (PREVIOUS_CLEAN_STACK_HEAD,),
        (PRE_TECHNICAL_INTAKE_DRAFT_CLEAN_STACK_HEAD,),
        (PRE_PARSER_ATTESTATION_CLEAN_STACK_HEAD,),
        (PRE_PARSER_PROVENANCE_CLEAN_STACK_HEAD,),
        (PRE_TECHNICAL_EXTRACTION_CLEAN_STACK_HEAD,),
        (PRE_SOURCE_EXTRACTION_CLEAN_STACK_HEAD,),
        (PRE_SOURCE_REGISTRATION_CLEAN_STACK_HEAD,),
        (PRE_RELATIONSHIP_CLEAN_STACK_HEAD,),
        (PRE_PUBLICATION_CLEAN_STACK_HEAD,),
    }:
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DATABASE_MIGRATION_REQUIRED",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            unexpected_tables=unexpected_tables,
        )
    if revisions == (PRE_RETIREMENT_CLEAN_STACK_HEAD,):
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code=(
                "LEGACY_INITIAL_SUBMISSION_RETIREMENT_REQUIRED"
                if unexpected_tables
                else "DATABASE_MIGRATION_REQUIRED"
            ),
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            unexpected_tables=unexpected_tables,
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
        unexpected_tables=unexpected_tables,
    )


__all__ = [
    "CLEAN_STACK_HEAD",
    "LEGACY_ADJUDICATED_HEAD",
    "PRE_PARSER_ATTESTATION_CLEAN_STACK_HEAD",
    "PRE_PARSER_PROVENANCE_CLEAN_STACK_HEAD",
    "PRE_RETIREMENT_CLEAN_STACK_HEAD",
    "PRE_SOURCE_EXTRACTION_CLEAN_STACK_HEAD",
    "PRE_TECHNICAL_EXTRACTION_CLEAN_STACK_HEAD",
    "PRE_TECHNICAL_INTAKE_DRAFT_CLEAN_STACK_HEAD",
    "PRE_PUBLICATION_CLEAN_STACK_HEAD",
    "PRE_RELATIONSHIP_CLEAN_STACK_HEAD",
    "PRE_SOURCE_REGISTRATION_CLEAN_STACK_HEAD",
    "PREVIOUS_CLEAN_STACK_HEAD",
    "REQUIRED_COLUMNS",
    "REQUIRED_TABLES",
    "RETIRED_TABLES",
    "DeploymentLineageAssessment",
    "assess_deployment_lineage",
]
