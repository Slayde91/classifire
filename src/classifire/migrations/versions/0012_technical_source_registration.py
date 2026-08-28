"""Add governed technical-source registration metadata and summary lineage."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_technical_source_registration"
down_revision = "0011_technical_document_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("technical_documents") as batch:
        batch.add_column(sa.Column("declared_source_role", sa.String(50), nullable=True))
        batch.add_column(sa.Column("sponsor_organisation", sa.String(300), nullable=True))
        batch.add_column(
            sa.Column("artifact_provenance_status", sa.String(50), nullable=True)
        )
        batch.add_column(sa.Column("artifact_provenance_note", sa.Text(), nullable=True))
        batch.add_column(sa.Column("evidence_scope", sa.String(50), nullable=True))
        batch.add_column(sa.Column("evidence_limitations", sa.Text(), nullable=True))
        batch.create_check_constraint(
            "ck_technical_document_declared_source_role",
            "declared_source_role IS NULL OR declared_source_role IN ("
            "'primary_test', 'assessment', 'regulatory_summary', "
            "'supporting_reference', 'manufacturer_information', "
            "'administrative_notice'"
            ")",
        )
        batch.create_check_constraint(
            "ck_technical_document_artifact_provenance_status",
            "artifact_provenance_status IS NULL OR artifact_provenance_status IN ("
            "'issuer_original', 'issuer_copy', 'transformed_derivative', 'unknown'"
            ")",
        )
        batch.create_check_constraint(
            "ck_technical_document_evidence_scope",
            "evidence_scope IS NULL OR evidence_scope IN ("
            "'full_source', 'summary_only', 'bibliographic_only'"
            ")",
        )
        batch.create_index(
            "ix_technical_documents_declared_source_role",
            ["declared_source_role"],
        )
        batch.create_index(
            "ix_technical_documents_artifact_provenance_status",
            ["artifact_provenance_status"],
        )
        batch.create_index(
            "ix_technical_documents_evidence_scope",
            ["evidence_scope"],
        )

    with op.batch_alter_table("technical_document_relationships") as batch:
        batch.drop_constraint(
            "ck_technical_document_relationship_type",
            type_="check",
        )
        batch.create_check_constraint(
            "ck_technical_document_relationship_type",
            "relationship_type IN ("
            "'revision_of', 'assessment_of', 'amendment_to', 'replaces', "
            "'retirement_notice_for', 'summary_of'"
            ")",
        )


def downgrade() -> None:
    raise RuntimeError("Technical source registration cannot be downgraded")
