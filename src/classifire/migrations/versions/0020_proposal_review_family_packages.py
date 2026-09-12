"""Retain approved report-family review packages in the governed review register."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_proposal_review_family_packages"
down_revision = "0019_report_evidence_family_manifests"
branch_labels = None
depends_on = None


_SINGLE_REPORT = (
    "(package_kind = 'single_report' "
    "AND project_evidence_id IS NOT NULL "
    "AND report_sha256 IS NOT NULL "
    "AND approved_expected_label_manifest_id IS NOT NULL "
    "AND approved_expected_label_manifest_sha256 IS NOT NULL "
    "AND report_evidence_family_manifest_id IS NULL "
    "AND report_evidence_family_manifest_sha256 IS NULL "
    "AND report_evidence_family_manifest_approval_reference IS NULL)"
)
_REPORT_FAMILY = (
    "(package_kind = 'report_evidence_family' "
    "AND project_evidence_id IS NULL "
    "AND report_sha256 IS NULL "
    "AND approved_expected_label_manifest_id IS NULL "
    "AND approved_expected_label_manifest_sha256 IS NULL "
    "AND report_evidence_family_manifest_id IS NOT NULL "
    "AND report_evidence_family_manifest_sha256 IS NOT NULL "
    "AND report_evidence_family_manifest_approval_reference IS NOT NULL)"
)


def upgrade() -> None:
    # SQLite needs a table copy for nullable-column changes. PostgreSQL must
    # retain the existing parent table and its incoming reader/redaction keys.
    with op.batch_alter_table(
        "proposal_review_packages",
        recreate="always" if op.get_bind().dialect.name == "sqlite" else "auto",
    ) as batch_op:
        batch_op.add_column(
            sa.Column(
                "package_kind",
                sa.String(30),
                nullable=False,
                server_default="single_report",
            )
        )
        batch_op.add_column(sa.Column("report_evidence_family_manifest_id", sa.String(36)))
        batch_op.add_column(sa.Column("report_evidence_family_manifest_sha256", sa.String(64)))
        batch_op.add_column(
            sa.Column("report_evidence_family_manifest_approval_reference", sa.String(500))
        )
        batch_op.alter_column("project_evidence_id", existing_type=sa.String(36), nullable=True)
        batch_op.alter_column("report_sha256", existing_type=sa.String(64), nullable=True)
        batch_op.alter_column(
            "approved_expected_label_manifest_id",
            existing_type=sa.String(36),
            nullable=True,
        )
        batch_op.alter_column(
            "approved_expected_label_manifest_sha256",
            existing_type=sa.String(64),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_proposal_review_package_family_manifest",
            "report_evidence_family_manifests",
            ["report_evidence_family_manifest_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_proposal_review_package_kind_binding",
            f"{_SINGLE_REPORT} OR {_REPORT_FAMILY}",
        )
        batch_op.create_index(
            "ix_proposal_review_package_family_manifest_id",
            ["report_evidence_family_manifest_id"],
        )


def downgrade() -> None:
    raise RuntimeError("Approved report-family review packages cannot be downgraded")
