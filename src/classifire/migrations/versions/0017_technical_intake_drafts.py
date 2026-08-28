"""Add owner-bound Draft technical intake payloads pinned to retained source bytes."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_technical_intake_drafts"
down_revision = "0016_parser_attestation_v2"
branch_labels = None
depends_on = None


def _canonical_uuid4_check(column: str) -> str:
    without_hyphens = f"replace({column}, '-', '')"
    unsupported = without_hyphens
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return (
        f"length({column}) = 36 "
        f"AND substr({column}, 9, 1) = '-' "
        f"AND substr({column}, 14, 1) = '-' "
        f"AND substr({column}, 19, 1) = '-' "
        f"AND substr({column}, 24, 1) = '-' "
        f"AND substr({column}, 15, 1) = '4' "
        f"AND substr({column}, 20, 1) IN ('8', '9', 'a', 'b') "
        f"AND {column} = lower({column}) "
        f"AND length({without_hyphens}) = 32 "
        f"AND length({unsupported}) = 0"
    )


def _canonical_sha256_check(column: str) -> str:
    unsupported = column
    for character in "0123456789abcdef":
        unsupported = f"replace({unsupported}, '{character}', '')"
    return (
        f"length({column}) = 64 "
        f"AND {column} = lower({column}) "
        f"AND length({unsupported}) = 0"
    )


def upgrade() -> None:
    op.create_table(
        "technical_intake_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column("draft_schema", sa.String(100), nullable=False),
        sa.Column("technical_document_id", sa.String(36), nullable=False),
        sa.Column("source_stored_file_id", sa.String(36), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("users.id", name="fk_technical_intake_draft_owner"),
            nullable=False,
        ),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["technical_document_id", "source_stored_file_id"],
            ["technical_documents.id", "technical_documents.stored_file_id"],
            name="fk_technical_intake_draft_document_source",
        ),
        sa.ForeignKeyConstraint(
            ["source_stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_technical_intake_draft_source_bytes",
        ),
        sa.CheckConstraint(
            _canonical_uuid4_check("id"),
            name="ck_technical_intake_draft_id",
        ),
        sa.CheckConstraint(
            "draft_schema = 'technical-intake-draft-v1'",
            name="ck_technical_intake_draft_schema",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("source_sha256"),
            name="ck_technical_intake_draft_source_sha256",
        ),
        sa.CheckConstraint(
            "source_size_bytes BETWEEN 1 AND 1073741824",
            name="ck_technical_intake_draft_source_size",
        ),
        sa.CheckConstraint(
            "status = 'draft'",
            name="ck_technical_intake_draft_status",
        ),
        sa.CheckConstraint(
            _canonical_sha256_check("payload_sha256"),
            name="ck_technical_intake_draft_payload_sha256",
        ),
        sa.CheckConstraint(
            "record_version >= 1",
            name="ck_technical_intake_draft_record_version",
        ),
        sa.UniqueConstraint(
            "owner_id",
            "technical_document_id",
            "source_sha256",
            name="uq_technical_intake_draft_owner_document_source",
        ),
    )
    op.create_index(
        "ix_technical_intake_drafts_owner_status_updated",
        "technical_intake_drafts",
        ["owner_id", "status", "updated_at"],
    )
    op.create_index(
        "ix_technical_intake_drafts_document",
        "technical_intake_drafts",
        ["technical_document_id"],
    )


def downgrade() -> None:
    drafts = sa.table("technical_intake_drafts", sa.column("id"))
    if op.get_bind().execute(sa.select(drafts.c.id).limit(1)).first() is not None:
        raise RuntimeError(
            "Technical intake Draft records are retained user data and cannot be downgraded"
        )
    op.drop_index(
        "ix_technical_intake_drafts_document",
        table_name="technical_intake_drafts",
    )
    op.drop_index(
        "ix_technical_intake_drafts_owner_status_updated",
        table_name="technical_intake_drafts",
    )
    op.drop_table("technical_intake_drafts")
