"""Read-only deployment database lineage assessment."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

CLEAN_STACK_HEAD = "0032_draft_pdf_sources"
PREVIOUS_CLEAN_STACK_HEAD = "0031_draft_estimate_reports"
# Preserve recognized upgrade lineages as the current head advances.
MIGRATION_REQUIRED_HEADS = frozenset(
    {"0029_draft_system_matches", "0030_draft_estimates", "0031_draft_estimate_reports"}
)
LEGACY_CLEAN_STACK_HEAD = "0007_reconcile_adjudicated_admission_lineages"
LEGACY_ADJUDICATED_HEAD = "0006_adjudicated_canonical_admissions"
REQUIRED_TABLES = frozenset(
    {
        "draft_pdf_sources",
        "draft_estimate_reports",
        "draft_estimates",
        "draft_estimate_revisions",
        "draft_system_matches",
        "draft_system_match_revisions",
        "draft_scope_reports",
        "draft_scopes",
        "draft_scope_revisions",
        "physical_model_admissions",
        "physical_model_lock_amendment_admissions",
        "physical_model_lock_amendment_outcomes",
        "physical_model_lock_replacement_admissions",
        "physical_model_lock_replacement_outcomes",
        "physical_model_submission_receipts",
        "project_evidence",
        "proposal_review_annotations",
        "proposal_review_package_redactions",
        "proposal_review_packages",
        "report_defect_scopes",
        "report_expected_label_manifests",
        "report_evidence_family_manifests",
        "report_evidence_family_members",
        "report_evidence_locators",
        "visual_validation_receipts",
    }
)
RETIRED_TABLES = frozenset({"physical_model_initial_submissions"})


@dataclass(frozen=True)
class DeploymentLineageAssessment:
    status: str
    code: str
    alembic_revisions: tuple[str, ...]
    missing_tables: tuple[str, ...]
    unexpected_tables: tuple[str, ...] = ()
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
    unexpected_tables = tuple(sorted(RETIRED_TABLES & tables))
    if revisions == (CLEAN_STACK_HEAD,) and not missing_tables and not unexpected_tables:
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
            unexpected_tables=unexpected_tables,
        )
    if len(revisions) == 1 and revisions[0] in MIGRATION_REQUIRED_HEADS:
        return DeploymentLineageAssessment(
            status="BLOCKED",
            code="DATABASE_MIGRATION_REQUIRED",
            alembic_revisions=revisions,
            missing_tables=missing_tables,
            unexpected_tables=unexpected_tables,
        )
    if revisions == (LEGACY_CLEAN_STACK_HEAD,):
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
    "LEGACY_CLEAN_STACK_HEAD",
    "PREVIOUS_CLEAN_STACK_HEAD",
    "RETIRED_TABLES",
    "DeploymentLineageAssessment",
    "assess_deployment_lineage",
]
