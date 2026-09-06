"""Retain foreign package origins separately from native library authority."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_draft_package_imports"
down_revision = "0034_draft_project_packages"
branch_labels = None
depends_on = None


def _record_columns():
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "draft_package_imports",
        *_record_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("archive_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("archive_hash", sa.String(64), nullable=False),
        sa.Column("mapping_json", sa.Text(), nullable=False),
        sa.Column("mapping_hash", sa.String(64), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("draft_scope_id", name="uq_draft_import_scope"),
        sa.CheckConstraint(
            "length(archive_bytes) > 0 AND length(archive_bytes) <= 134217728",
            name="ck_draft_import_size",
        ),
    )
    op.create_index(
        "ix_draft_package_imports_draft_scope_id", "draft_package_imports", ["draft_scope_id"]
    )
    op.create_table(
        "draft_imported_report_sources",
        *_record_columns(),
        sa.Column(
            "draft_scope_id", sa.String(36), sa.ForeignKey("draft_scopes.id"), nullable=False
        ),
        sa.Column("stored_file_id", sa.String(36), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(200), nullable=False),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("scan_json", sa.Text()),
        sa.Column("document_json", sa.Text()),
        sa.Column("document_sha256", sa.String(64)),
        sa.Column("processing_error", sa.String(80)),
        sa.UniqueConstraint("draft_scope_id", "stored_file_id", name="uq_import_report_file"),
        sa.ForeignKeyConstraint(
            ["stored_file_id", "source_sha256", "source_size_bytes"],
            ["stored_files.id", "stored_files.sha256", "stored_files.size_bytes"],
            name="fk_imported_report_source_bytes",
        ),
        sa.CheckConstraint(
            "source_size_bytes > 0 AND source_size_bytes <= 10485760",
            name="ck_imported_report_source_size",
        ),
    )
    op.create_index(
        "ix_draft_imported_report_sources_draft_scope_id",
        "draft_imported_report_sources",
        ["draft_scope_id"],
    )
    with op.batch_alter_table("draft_system_matches") as batch:
        batch.add_column(sa.Column("import_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_draft_match_import", "draft_package_imports", ["import_id"], ["id"]
        )
        batch.alter_column("release_id", existing_type=sa.String(36), nullable=True)
        batch.create_check_constraint(
            "ck_draft_match_origin",
            "(release_id IS NOT NULL AND import_id IS NULL) OR "
            "(release_id IS NULL AND import_id IS NOT NULL)",
        )
    with op.batch_alter_table("draft_estimates") as batch:
        batch.add_column(sa.Column("import_id", sa.String(36)))
        batch.create_foreign_key(
            "fk_draft_estimate_import", "draft_package_imports", ["import_id"], ["id"]
        )

    with op.batch_alter_table("draft_project_packages") as batch:
        batch.drop_constraint("ck_draft_package_size", type_="check")
        batch.create_check_constraint(
            "ck_draft_package_size",
            "length(archive_bytes) > 0 AND length(archive_bytes) <= 134217728",
        )


def downgrade() -> None:
    raise RuntimeError("Retained foreign package history cannot be downgraded")
