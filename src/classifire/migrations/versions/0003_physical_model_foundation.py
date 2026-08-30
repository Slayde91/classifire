from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

revision = "0003_physical_model_foundation"
down_revision = "0002_estimate_release_pins"
branch_labels = None
depends_on = None

_RETAINED_LAYER_TWO_TABLES = (
    "defects",
    "evidence_sources",
    "service_opening_links",
    "physical_model_locks",
)


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _index_names(table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table)}


def _has_fk(table: str, constrained: list[str], referred_table: str) -> bool:
    return any(
        foreign_key.get("constrained_columns") == constrained
        and foreign_key.get("referred_table") == referred_table
        for foreign_key in sa.inspect(op.get_bind()).get_foreign_keys(table)
    )


def _record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def _create_index_if_missing(name: str, table: str, columns: list[str]) -> None:
    if name not in _index_names(table):
        op.create_index(name, table, columns)


def _retained_layer_two_tables(tables: set[str]) -> list[str]:
    bind = op.get_bind()
    return [
        table
        for table in _RETAINED_LAYER_TWO_TABLES
        if table in tables
        and bind.execute(sa.select(sa.literal(1)).select_from(sa.table(table)).limit(1)).first()
        is not None
    ]


def upgrade() -> None:
    tables = _table_names()

    if "defects" not in tables:
        op.create_table(
            "defects",
            *_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("external_defect_id", sa.String(150), nullable=True),
            sa.Column("defect_code", sa.String(150), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("location", sa.Text(), nullable=True),
            sa.Column("classification", sa.String(100), nullable=True),
            sa.Column(
                "evidence_status",
                sa.String(30),
                nullable=False,
                server_default=sa.text("'provisional'"),
            ),
            sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'draft'")),
            sa.Column("source_json", sa.JSON(), nullable=True),
            sa.UniqueConstraint(
                "estimate_id", "external_defect_id", name="uq_defect_estimate_external"
            ),
        )
    _create_index_if_missing("ix_defects_estimate_id", "defects", ["estimate_id"])
    _create_index_if_missing("ix_defects_external_defect_id", "defects", ["external_defect_id"])
    _create_index_if_missing("ix_defects_defect_code", "defects", ["defect_code"])
    _create_index_if_missing("ix_defects_classification", "defects", ["classification"])
    _create_index_if_missing("ix_defects_evidence_status", "defects", ["evidence_status"])
    _create_index_if_missing("ix_defects_status", "defects", ["status"])

    if "evidence_sources" not in tables:
        op.create_table(
            "evidence_sources",
            *_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("defect_id", sa.String(36), sa.ForeignKey("defects.id"), nullable=True),
            sa.Column(
                "stored_file_id", sa.String(36), sa.ForeignKey("stored_files.id"), nullable=True
            ),
            sa.Column("evidence_type", sa.String(100), nullable=False),
            sa.Column("source_reference", sa.Text(), nullable=True),
            sa.Column("page_number", sa.String(100), nullable=True),
            sa.Column("region_reference", sa.String(300), nullable=True),
            sa.Column("sha256", sa.String(64), nullable=True),
            sa.Column(
                "evidence_class",
                sa.String(50),
                nullable=False,
                server_default=sa.text("'observed'"),
            ),
            sa.Column("confidence", sa.Numeric(9, 6), nullable=True),
            sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'active'")),
            sa.Column("source_json", sa.JSON(), nullable=True),
        )
    _create_index_if_missing("ix_evidence_sources_estimate_id", "evidence_sources", ["estimate_id"])
    _create_index_if_missing("ix_evidence_sources_defect_id", "evidence_sources", ["defect_id"])
    _create_index_if_missing(
        "ix_evidence_sources_stored_file_id", "evidence_sources", ["stored_file_id"]
    )
    _create_index_if_missing(
        "ix_evidence_sources_evidence_type", "evidence_sources", ["evidence_type"]
    )
    _create_index_if_missing("ix_evidence_sources_sha256", "evidence_sources", ["sha256"])
    _create_index_if_missing(
        "ix_evidence_sources_evidence_class", "evidence_sources", ["evidence_class"]
    )
    _create_index_if_missing("ix_evidence_sources_status", "evidence_sources", ["status"])

    if "service_opening_links" not in tables:
        op.create_table(
            "service_opening_links",
            *_record_columns(),
            sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=False),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False),
            sa.Column(
                "link_type",
                sa.String(50),
                nullable=False,
                server_default=sa.text("'penetrates'"),
            ),
            sa.Column(
                "relationship_status",
                sa.String(30),
                nullable=False,
                server_default=sa.text("'confirmed'"),
            ),
            sa.Column(
                "evidence_status",
                sa.String(30),
                nullable=False,
                server_default=sa.text("'provisional'"),
            ),
            sa.Column("confidence", sa.Numeric(9, 6), nullable=True),
            sa.Column("source_reference", sa.Text(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.UniqueConstraint("service_id", "opening_id", name="uq_service_opening_link"),
        )
    _create_index_if_missing(
        "ix_service_opening_links_service_id", "service_opening_links", ["service_id"]
    )
    _create_index_if_missing(
        "ix_service_opening_links_opening_id", "service_opening_links", ["opening_id"]
    )
    _create_index_if_missing(
        "ix_service_opening_links_relationship_status",
        "service_opening_links",
        ["relationship_status"],
    )
    _create_index_if_missing(
        "ix_service_opening_links_evidence_status",
        "service_opening_links",
        ["evidence_status"],
    )
    _create_index_if_missing(
        "ix_service_opening_pair", "service_opening_links", ["opening_id", "service_id"]
    )

    if "physical_model_locks" not in tables:
        op.create_table(
            "physical_model_locks",
            *_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
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
    _create_index_if_missing(
        "ix_physical_model_locks_project_id", "physical_model_locks", ["project_id"]
    )
    _create_index_if_missing(
        "ix_physical_model_locks_estimate_id", "physical_model_locks", ["estimate_id"]
    )
    _create_index_if_missing(
        "ix_physical_model_locks_validator_result", "physical_model_locks", ["validator_result"]
    )
    _create_index_if_missing(
        "ix_physical_model_locks_content_hash", "physical_model_locks", ["content_hash"]
    )
    if "uq_physical_model_locks_active_estimate" not in _index_names("physical_model_locks"):
        op.create_index(
            "uq_physical_model_locks_active_estimate",
            "physical_model_locks",
            ["estimate_id"],
            unique=True,
            sqlite_where=sa.text("invalidated_at IS NULL"),
            postgresql_where=sa.text("invalidated_at IS NULL"),
        )

    # Additive compatibility fields retain the legacy one-opening and string defect links.
    opening_columns = _column_names("openings")
    if "canonical_defect_id" not in opening_columns:
        with op.batch_alter_table("openings") as batch:
            batch.add_column(sa.Column("canonical_defect_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_openings_canonical_defect_id_defects",
                "defects",
                ["canonical_defect_id"],
                ["id"],
            )
    _create_index_if_missing("ix_openings_canonical_defect_id", "openings", ["canonical_defect_id"])

    service_columns = _column_names("services")
    if "primary_opening_legacy" not in service_columns:
        with op.batch_alter_table("services") as batch:
            batch.add_column(
                sa.Column(
                    "primary_opening_legacy",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.true(),
                )
            )

    bind = op.get_bind()

    # Preserve legacy defect IDs while creating one canonical Defect per estimate/value pair.
    if "defect_id" in opening_columns:
        rows = bind.execute(
            sa.text(
                "SELECT id, estimate_id, defect_id FROM openings "
                "WHERE defect_id IS NOT NULL AND TRIM(defect_id) <> ''"
            )
        ).mappings()
        defect_ids: dict[tuple[str, str], str] = {}
        for row in rows:
            key = (row["estimate_id"], row["defect_id"])
            canonical_id = defect_ids.get(key)
            if canonical_id is None:
                canonical_id = bind.execute(
                    sa.text(
                        "SELECT id FROM defects "
                        "WHERE estimate_id=:estimate_id "
                        "AND external_defect_id=:external_defect_id"
                    ),
                    {"estimate_id": key[0], "external_defect_id": key[1]},
                ).scalar()
                if canonical_id is None:
                    canonical_id = str(uuid.uuid4())
                    bind.execute(
                        sa.text(
                            "INSERT INTO defects "
                            "(id, created_at, updated_at, record_version, estimate_id, "
                            "external_defect_id, defect_code, evidence_status, status) "
                            "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                            ":estimate_id, :external_defect_id, :defect_code, "
                            "'provisional', 'draft')"
                        ),
                        {
                            "id": canonical_id,
                            "estimate_id": key[0],
                            "external_defect_id": key[1],
                            "defect_code": key[1],
                        },
                    )
                defect_ids[key] = canonical_id
            bind.execute(
                sa.text(
                    "UPDATE openings SET canonical_defect_id=:canonical_id "
                    "WHERE id=:opening_id AND canonical_defect_id IS NULL"
                ),
                {"canonical_id": canonical_id, "opening_id": row["id"]},
            )

    # Preserve legacy service/opening links and add an equivalent canonical link when absent.
    if "opening_id" in service_columns:
        service_rows = bind.execute(
            sa.text(
                "SELECT id, opening_id, evidence_status, confidence FROM services "
                "WHERE opening_id IS NOT NULL"
            )
        ).mappings()
        for row in service_rows:
            exists = bind.execute(
                sa.text(
                    "SELECT 1 FROM service_opening_links "
                    "WHERE service_id=:service_id AND opening_id=:opening_id"
                ),
                {"service_id": row["id"], "opening_id": row["opening_id"]},
            ).scalar()
            if exists is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO service_opening_links "
                        "(id, created_at, updated_at, record_version, service_id, opening_id, "
                        "link_type, relationship_status, evidence_status, confidence) "
                        "VALUES (:id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1, "
                        ":service_id, :opening_id, 'penetrates', 'confirmed', "
                        ":evidence_status, :confidence)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "service_id": row["id"],
                        "opening_id": row["opening_id"],
                        "evidence_status": row["evidence_status"] or "provisional",
                        "confidence": row["confidence"],
                    },
                )


def downgrade() -> None:
    retained_tables = _retained_layer_two_tables(_table_names())
    if retained_tables:
        raise RuntimeError(
            "Refusing to downgrade the physical-model foundation while retained Layer 2 "
            "records exist in: " + ", ".join(retained_tables)
        )

    # Remove new dependent tables before changing their legacy parents. SQLite
    # batch mode recreates tables, so this ordering also minimizes the period in
    # which a recreated parent has still-live Layer 2 child references.
    for table in ["physical_model_locks", "service_opening_links", "evidence_sources"]:
        if table in _table_names():
            op.drop_table(table)

    if "openings" in _table_names() and "canonical_defect_id" in _column_names("openings"):
        with op.batch_alter_table("openings") as batch:
            if _has_fk("openings", ["canonical_defect_id"], "defects"):
                batch.drop_constraint("fk_openings_canonical_defect_id_defects", type_="foreignkey")
            if "ix_openings_canonical_defect_id" in _index_names("openings"):
                batch.drop_index("ix_openings_canonical_defect_id")
            batch.drop_column("canonical_defect_id")

    if "services" in _table_names() and "primary_opening_legacy" in _column_names("services"):
        with op.batch_alter_table("services") as batch:
            batch.drop_column("primary_opening_legacy")

    if "defects" in _table_names():
        op.drop_table("defects")
