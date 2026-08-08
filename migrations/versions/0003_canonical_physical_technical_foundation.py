from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa

revision = "0003_canonical_physical_technical_foundation"
down_revision = "0002_estimate_release_pins"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _has_fk(table: str, constrained: list[str], referred_table: str) -> bool:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk.get("constrained_columns") == constrained and fk.get("referred_table") == referred_table:
            return True
    return False


def _create_record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    tables = _table_names()

    if "defects" not in tables:
        op.create_table(
            "defects",
            *_create_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("external_defect_id", sa.String(150), nullable=True),
            sa.Column("defect_code", sa.String(150), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("classification", sa.String(100), nullable=True),
            sa.Column("evidence_status", sa.String(30), nullable=False, server_default="provisional"),
            sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
            sa.Column("source_json", sa.JSON(), nullable=True),
            sa.UniqueConstraint("estimate_id", "external_defect_id", name="uq_defect_estimate_external"),
        )
        op.create_index("ix_defects_estimate_id", "defects", ["estimate_id"])
        op.create_index("ix_defects_external_defect_id", "defects", ["external_defect_id"])
        op.create_index("ix_defects_defect_code", "defects", ["defect_code"])

    if "evidence_sources" not in tables:
        op.create_table(
            "evidence_sources",
            *_create_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("defect_id", sa.String(36), sa.ForeignKey("defects.id"), nullable=True),
            sa.Column("stored_file_id", sa.String(36), sa.ForeignKey("stored_files.id"), nullable=True),
            sa.Column("evidence_type", sa.String(100), nullable=False),
            sa.Column("source_reference", sa.Text(), nullable=True),
            sa.Column("page_number", sa.String(100), nullable=True),
            sa.Column("region_reference", sa.String(300), nullable=True),
            sa.Column("sha256", sa.String(64), nullable=True),
            sa.Column("evidence_class", sa.String(50), nullable=False, server_default="observed"),
            sa.Column("confidence", sa.Numeric(9, 6), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="active"),
            sa.Column("source_json", sa.JSON(), nullable=True),
        )
        op.create_index("ix_evidence_sources_estimate_id", "evidence_sources", ["estimate_id"])
        op.create_index("ix_evidence_sources_defect_id", "evidence_sources", ["defect_id"])
        op.create_index("ix_evidence_sources_stored_file_id", "evidence_sources", ["stored_file_id"])

    if "service_opening_links" not in tables:
        op.create_table(
            "service_opening_links",
            *_create_record_columns(),
            sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=False),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False),
            sa.Column("link_type", sa.String(50), nullable=False, server_default="penetrates"),
            sa.Column("relationship_status", sa.String(30), nullable=False, server_default="confirmed"),
            sa.Column("evidence_status", sa.String(30), nullable=False, server_default="provisional"),
            sa.Column("confidence", sa.Numeric(9, 6), nullable=True),
            sa.Column("source_reference", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("service_id", "opening_id", name="uq_service_opening_link"),
        )
        op.create_index("ix_service_opening_pair", "service_opening_links", ["opening_id", "service_id"])

    if "service_material_hypotheses" not in tables:
        op.create_table(
            "service_material_hypotheses",
            *_create_record_columns(),
            sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=False),
            sa.Column("material", sa.String(200), nullable=False),
            sa.Column("evidence_status", sa.String(50), nullable=False),
            sa.Column("evidence_ids", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.Numeric(9, 6), nullable=True),
            sa.Column("technical_consequence", sa.Text(), nullable=True),
            sa.Column("pricing_consequence", sa.Text(), nullable=True),
            sa.Column("final_status", sa.String(50), nullable=False, server_default="provisional"),
        )
        op.create_index("ix_service_material_hypotheses_service_id", "service_material_hypotheses", ["service_id"])

    if "physical_model_locks" not in tables:
        op.create_table(
            "physical_model_locks",
            *_create_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=True),
            sa.Column("defect_ids", sa.JSON(), nullable=True),
            sa.Column("evidence_hashes", sa.JSON(), nullable=True),
            sa.Column("service_ids", sa.JSON(), nullable=False),
            sa.Column("opening_ids", sa.JSON(), nullable=False),
            sa.Column("service_count_status", sa.String(50), nullable=True),
            sa.Column("material_hypothesis_status", sa.String(50), nullable=True),
            sa.Column("critical_unknowns", sa.JSON(), nullable=True),
            sa.Column("validator_result", sa.String(50), nullable=False),
            sa.Column("permitted_classes", sa.JSON(), nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("signature", sa.Text(), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidation_reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_physical_model_locks_project_id", "physical_model_locks", ["project_id"])
        op.create_index("ix_physical_model_locks_estimate_id", "physical_model_locks", ["estimate_id"])

    if "repair_strategies" not in tables:
        op.create_table(
            "repair_strategies",
            *_create_record_columns(),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False),
            sa.Column("physical_model_lock_id", sa.String(36), sa.ForeignKey("physical_model_locks.id"), nullable=True),
            sa.Column("candidate_id", sa.String(300), nullable=True),
            sa.Column("selected_technical_variant_id", sa.String(36), sa.ForeignKey("technical_variants.id"), nullable=True),
            sa.Column("package15_release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=True),
            sa.Column("match_classification", sa.String(100), nullable=True),
            sa.Column("treatment_description", sa.Text(), nullable=True),
            sa.Column("technical_basis", sa.JSON(), nullable=True),
            sa.Column("assumptions", sa.JSON(), nullable=True),
            sa.Column("limitations", sa.JSON(), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default="draft"),
        )
        op.create_index("ix_repair_strategies_opening_id", "repair_strategies", ["opening_id"])

    if "package15_candidate_requirements" not in tables:
        op.create_table(
            "package15_candidate_requirements",
            *_create_record_columns(),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=True),
            sa.Column("candidate_id", sa.String(300), nullable=False),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("source_field", sa.String(300), nullable=True),
            sa.Column("source_document_id", sa.String(300), nullable=True),
            sa.Column("source_page", sa.String(100), nullable=True),
            sa.Column("source_row", sa.String(150), nullable=True),
            sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("exclusion", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        op.create_index("ix_package15_candidate_requirements_candidate_id", "package15_candidate_requirements", ["candidate_id"])

    if "system_required_components" not in tables:
        op.create_table(
            "system_required_components",
            *_create_record_columns(),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False),
            sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=True),
            sa.Column("candidate_id", sa.String(300), nullable=False),
            sa.Column("category", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("technical_requirement_id", sa.String(300), nullable=True),
            sa.Column("quantity_formula_id", sa.String(300), nullable=True),
            sa.Column("required_labour_activity_ids", sa.JSON(), nullable=True),
            sa.Column("candidate_status", sa.String(100), nullable=True),
            sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
        op.create_index("ix_system_required_components_candidate_id", "system_required_components", ["candidate_id"])

    if "repair_strategy_locks" not in tables:
        op.create_table(
            "repair_strategy_locks",
            *_create_record_columns(),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False),
            sa.Column("repair_strategy_id", sa.String(36), sa.ForeignKey("repair_strategies.id"), nullable=True),
            sa.Column("candidate_id", sa.String(300), nullable=False),
            sa.Column("candidate_status", sa.String(100), nullable=False),
            sa.Column("required_component_ids", sa.JSON(), nullable=False),
            sa.Column("dependencies", sa.JSON(), nullable=True),
            sa.Column("mismatches", sa.JSON(), nullable=True),
            sa.Column("assumptions", sa.JSON(), nullable=True),
            sa.Column("validator_result", sa.String(50), nullable=False),
            sa.Column("permitted_classes", sa.JSON(), nullable=True),
            sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("signature", sa.Text(), nullable=True),
            sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("invalidation_reason", sa.Text(), nullable=True),
        )
        op.create_index("ix_repair_strategy_locks_opening_id", "repair_strategy_locks", ["opening_id"])

    # Additive compatibility links: keep the legacy string/one-opening fields for now.
    opening_cols = _column_names("openings")
    if "canonical_defect_id" not in opening_cols:
        with op.batch_alter_table("openings") as batch:
            batch.add_column(sa.Column("canonical_defect_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_openings_canonical_defect_id_defects",
                "defects",
                ["canonical_defect_id"],
                ["id"],
            )

    service_cols = _column_names("services")
    if "primary_opening_legacy" not in service_cols:
        with op.batch_alter_table("services") as batch:
            batch.add_column(sa.Column("primary_opening_legacy", sa.Boolean(), nullable=False, server_default=sa.true()))

    bind = op.get_bind()
    now_expr = sa.func.current_timestamp()

    # Backfill canonical Defects from legacy Opening.defect_id without destroying legacy values.
    if "defect_id" in opening_cols:
        rows = bind.execute(sa.text(
            "SELECT id, estimate_id, defect_id FROM openings WHERE defect_id IS NOT NULL AND TRIM(defect_id) <> ''"
        )).mappings().all()
        defect_key_to_id: dict[tuple[str, str], str] = {}
        for row in rows:
            key = (row["estimate_id"], row["defect_id"])
            defect_id = defect_key_to_id.get(key)
            if defect_id is None:
                existing = bind.execute(sa.text(
                    "SELECT id FROM defects WHERE estimate_id=:estimate_id AND external_defect_id=:external_defect_id"
                ), {"estimate_id": key[0], "external_defect_id": key[1]}).scalar()
                defect_id = existing or str(uuid.uuid4())
                if existing is None:
                    bind.execute(sa.text(
                        "INSERT INTO defects (id, created_at, updated_at, record_version, estimate_id, external_defect_id, defect_code, evidence_status, status) "
                        "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :estimate_id, :external_defect_id, :defect_code, 'provisional', 'draft')"
                    ), {
                        "id": defect_id,
                        "estimate_id": key[0],
                        "external_defect_id": key[1],
                        "defect_code": key[1],
                    })
                defect_key_to_id[key] = defect_id
            bind.execute(sa.text(
                "UPDATE openings SET canonical_defect_id=:defect_id WHERE id=:opening_id AND canonical_defect_id IS NULL"
            ), {"defect_id": defect_id, "opening_id": row["id"]})

    # Backfill the legacy one-opening Service relationship into the new many-to-many link table.
    if "opening_id" in service_cols:
        service_rows = bind.execute(sa.text(
            "SELECT id, opening_id, evidence_status, confidence FROM services WHERE opening_id IS NOT NULL"
        )).mappings().all()
        for row in service_rows:
            exists = bind.execute(sa.text(
                "SELECT 1 FROM service_opening_links WHERE service_id=:service_id AND opening_id=:opening_id"
            ), {"service_id": row["id"], "opening_id": row["opening_id"]}).scalar()
            if not exists:
                bind.execute(sa.text(
                    "INSERT INTO service_opening_links "
                    "(id, created_at, updated_at, record_version, service_id, opening_id, link_type, relationship_status, evidence_status, confidence) "
                    "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, :service_id, :opening_id, 'penetrates', 'confirmed', :evidence_status, :confidence)"
                ), {
                    "id": str(uuid.uuid4()),
                    "service_id": row["id"],
                    "opening_id": row["opening_id"],
                    "evidence_status": row["evidence_status"] or "provisional",
                    "confidence": row["confidence"],
                })


def downgrade() -> None:
    tables = _table_names()

    if "services" in tables and "primary_opening_legacy" in _column_names("services"):
        with op.batch_alter_table("services") as batch:
            batch.drop_column("primary_opening_legacy")

    if "openings" in tables and "canonical_defect_id" in _column_names("openings"):
        with op.batch_alter_table("openings") as batch:
            if _has_fk("openings", ["canonical_defect_id"], "defects"):
                batch.drop_constraint("fk_openings_canonical_defect_id_defects", type_="foreignkey")
            batch.drop_column("canonical_defect_id")

    for table in [
        "repair_strategy_locks",
        "system_required_components",
        "package15_candidate_requirements",
        "repair_strategies",
        "physical_model_locks",
        "service_material_hypotheses",
        "service_opening_links",
        "evidence_sources",
        "defects",
    ]:
        if table in _table_names():
            op.drop_table(table)
