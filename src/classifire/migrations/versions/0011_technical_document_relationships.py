"""Add immutable typed provenance between technical source documents."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011_technical_document_relationships"
down_revision = "0010_release_publication_slot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "technical_document_relationships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("technical_documents.id"),
            nullable=False,
        ),
        sa.Column(
            "related_document_id",
            sa.String(36),
            sa.ForeignKey("technical_documents.id"),
            nullable=False,
        ),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column(
            "created_by_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "relationship_type IN ("
            "'revision_of', 'assessment_of', 'amendment_to', 'replaces', "
            "'retirement_notice_for'"
            ")",
            name="ck_technical_document_relationship_type",
        ),
        sa.CheckConstraint(
            "document_id <> related_document_id",
            name="ck_technical_document_relationship_not_self",
        ),
        sa.UniqueConstraint(
            "document_id",
            "related_document_id",
            "relationship_type",
            name="uq_technical_document_relationship_edge",
        ),
    )
    for name, columns in (
        ("ix_technical_document_relationship_document_id", ["document_id"]),
        ("ix_technical_document_relationship_related_id", ["related_document_id"]),
        ("ix_technical_document_relationship_type", ["relationship_type"]),
        ("ix_technical_document_relationship_created_by_id", ["created_by_id"]),
    ):
        op.create_index(
            name,
            "technical_document_relationships",
            columns,
        )


def downgrade() -> None:
    raise RuntimeError("Technical document provenance relationships cannot be downgraded")
