from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False),
    ]


def _baseline_metadata() -> sa.MetaData:
    """Frozen schema that existed immediately before Alembic was introduced.

    Source: repository commit db511b5e32c9f79ce9fb8758cc36d96ae7976478,
    src/quantifire/models.py. Keep this migration historical and self-contained;
    do not import current CLASSIFIRE ORM metadata here.
    """

    md = sa.MetaData()

    sa.Table(
        "users",
        md,
        *_record_columns(),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, index=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )

    sa.Table(
        "audit_events",
        md,
        *_record_columns(),
        sa.Column(
            "actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True, index=True
        ),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_name", sa.String(200), nullable=False),
        sa.Column("action", sa.String(100), nullable=False, index=True),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", sa.String(100), nullable=True, index=True),
        sa.Column("project_id", sa.String(36), nullable=True, index=True),
        sa.Column("previous_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_ip", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True, index=True),
        sa.Column("event_hash", sa.String(64), nullable=False),
    )

    sa.Table(
        "library_releases",
        md,
        *_record_columns(),
        sa.Column("library_type", sa.String(50), nullable=False, index=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("release_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("source_manifest", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "supersedes_release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("library_type", "version", name="uq_library_release_type_version"),
    )

    sa.Table(
        "markup_profiles",
        md,
        *_record_columns(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("scope_type", sa.String(30), nullable=False, index=True),
        sa.Column("scope_id", sa.String(100), nullable=True, index=True),
        sa.Column("product_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("material_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("labour_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("created_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )

    sa.Table(
        "products",
        md,
        *_record_columns(),
        sa.Column("sku", sa.String(100), nullable=False, index=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False, index=True),
        sa.Column("item_type", sa.String(30), nullable=False, index=True),
        sa.Column("category", sa.String(150), nullable=True, index=True),
        sa.Column("manufacturer", sa.String(200), nullable=True, index=True),
        sa.Column("supplier", sa.String(200), nullable=True, index=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("pack_size", sa.Numeric(18, 6), nullable=False),
        sa.Column("minimum_order_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("base_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tax_treatment", sa.String(30), nullable=False),
        sa.Column("waste_factor", sa.Numeric(9, 6), nullable=False),
        sa.Column("default_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("regional_pricing", sa.JSON(), nullable=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("supporting_attachment_id", sa.String(36), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=True),
        sa.Column(
            "release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
            index=True,
        ),
        sa.Column("supersedes_id", sa.String(36), sa.ForeignKey("products.id"), nullable=True),
        sa.UniqueConstraint("sku", "revision", name="uq_product_sku_revision"),
    )

    sa.Table(
        "labour_components",
        md,
        *_record_columns(),
        sa.Column("code", sa.String(100), nullable=False, index=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("trade_or_grade", sa.String(150), nullable=True, index=True),
        sa.Column("category", sa.String(150), nullable=True, index=True),
        sa.Column("unit", sa.String(30), nullable=False),
        sa.Column("base_rate", sa.Numeric(18, 4), nullable=False),
        sa.Column("default_hours", sa.Numeric(18, 6), nullable=False),
        sa.Column("crew_size", sa.Numeric(9, 3), nullable=False),
        sa.Column("default_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("productivity_source", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "supersedes_id", sa.String(36), sa.ForeignKey("labour_components.id"), nullable=True
        ),
        sa.UniqueConstraint("code", "revision", name="uq_labour_code_revision"),
    )

    sa.Table(
        "pricing_library_records",
        md,
        *_record_columns(),
        sa.Column("pkb_entry_id", sa.String(100), nullable=False, index=True),
        sa.Column("entry_version", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("system_description", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(100), nullable=False),
        sa.Column("rate_ex_tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("direct_labour_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("direct_material_cost", sa.Numeric(18, 4), nullable=True),
        sa.Column("material_markup", sa.Numeric(9, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tax_basis", sa.String(50), nullable=False),
        sa.Column("service_type", sa.String(200), nullable=True, index=True),
        sa.Column("service_class", sa.String(200), nullable=True, index=True),
        sa.Column("service_material", sa.String(200), nullable=True, index=True),
        sa.Column("substrate", sa.String(200), nullable=True, index=True),
        sa.Column("substrate_plane", sa.String(100), nullable=True, index=True),
        sa.Column("orientation", sa.String(100), nullable=True, index=True),
        sa.Column("frl", sa.String(100), nullable=True, index=True),
        sa.Column("manufacturer", sa.String(200), nullable=True, index=True),
        sa.Column("repair_family", sa.String(300), nullable=True, index=True),
        sa.Column("rate_inclusions", sa.JSON(), nullable=True),
        sa.Column("rate_exclusions", sa.JSON(), nullable=True),
        sa.Column("applicability", sa.JSON(), nullable=True),
        sa.Column("commercial_confidence", sa.String(100), nullable=True),
        sa.Column("technical_status", sa.String(200), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column(
            "release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "supersedes_id",
            sa.String(36),
            sa.ForeignKey("pricing_library_records.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "pkb_entry_id", "entry_version", "release_id", name="uq_pkb_entry_release"
        ),
        sa.Index("ix_pricing_search", "service_type", "service_material", "substrate", "frl"),
    )

    sa.Table(
        "stored_files",
        md,
        *_record_columns(),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=True),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(100), nullable=False, index=True),
        sa.Column("malware_scan_status", sa.String(30), nullable=False),
        sa.Column("uploaded_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("immutable", sa.Boolean(), nullable=False),
    )

    sa.Table(
        "technical_documents",
        md,
        *_record_columns(),
        sa.Column("document_id", sa.String(200), nullable=False, unique=True, index=True),
        sa.Column(
            "stored_file_id", sa.String(36), sa.ForeignKey("stored_files.id"), nullable=False
        ),
        sa.Column("document_type", sa.String(100), nullable=False, index=True),
        sa.Column("manufacturer", sa.String(200), nullable=True, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("reference", sa.String(300), nullable=True, index=True),
        sa.Column("revision", sa.String(100), nullable=True),
        sa.Column("issuing_organisation", sa.String(300), nullable=True),
        sa.Column("publication_date", sa.Date(), nullable=True),
        sa.Column("review_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("jurisdiction", sa.String(200), nullable=True, index=True),
        sa.Column("standards", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("extraction_status", sa.String(50), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column(
            "supersedes_document_id",
            sa.String(36),
            sa.ForeignKey("technical_documents.id"),
            nullable=True,
        ),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )

    sa.Table(
        "technical_variants",
        md,
        *_record_columns(),
        sa.Column("variant_id", sa.String(300), nullable=False, unique=True, index=True),
        sa.Column("system_id", sa.String(300), nullable=False, index=True),
        sa.Column(
            "technical_document_id",
            sa.String(36),
            sa.ForeignKey("technical_documents.id"),
            nullable=True,
        ),
        sa.Column("source_document_reference", sa.String(300), nullable=True, index=True),
        sa.Column("source_page", sa.String(100), nullable=True),
        sa.Column("source_table", sa.String(300), nullable=True),
        sa.Column("source_figure", sa.String(300), nullable=True),
        sa.Column("manufacturer", sa.String(200), nullable=True, index=True),
        sa.Column("product_family", sa.String(300), nullable=True, index=True),
        sa.Column("service_type", sa.String(300), nullable=True, index=True),
        sa.Column("service_material", sa.String(300), nullable=True, index=True),
        sa.Column("minimum_service_size_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("maximum_service_size_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("permitted_service_quantity", sa.String(100), nullable=True),
        sa.Column("insulation_type", sa.Text(), nullable=True),
        sa.Column("insulation_thickness_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("substrate_type", sa.Text(), nullable=True, index=True),
        sa.Column("minimum_substrate_thickness_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("maximum_substrate_thickness_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("orientation", sa.Text(), nullable=True, index=True),
        sa.Column("installation_face", sa.Text(), nullable=True),
        sa.Column("opening_type", sa.Text(), nullable=True, index=True),
        sa.Column("opening_dimensions", sa.Text(), nullable=True),
        sa.Column("annular_gap_min_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("annular_gap_max_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("service_spacing_rules", sa.Text(), nullable=True),
        sa.Column("edge_distance_rules", sa.Text(), nullable=True),
        sa.Column("support_rules", sa.Text(), nullable=True),
        sa.Column("fixing_rules", sa.Text(), nullable=True),
        sa.Column("component_requirements", sa.JSON(), nullable=True),
        sa.Column("labour_requirements", sa.JSON(), nullable=True),
        sa.Column("hard_exclusions", sa.Text(), nullable=True),
        sa.Column("dependencies", sa.Text(), nullable=True),
        sa.Column("frl", sa.String(100), nullable=True, index=True),
        sa.Column("jurisdiction", sa.String(200), nullable=True, index=True),
        sa.Column("quality_score", sa.Numeric(9, 3), nullable=True),
        sa.Column("confidence_cap", sa.Numeric(9, 3), nullable=True),
        sa.Column("search_eligibility", sa.String(100), nullable=True, index=True),
        sa.Column("expert_review_required", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("source_json", sa.JSON(), nullable=False),
        sa.Column(
            "release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "supersedes_id", sa.String(36), sa.ForeignKey("technical_variants.id"), nullable=True
        ),
        sa.Index("ix_technical_search", "service_type", "service_material", "frl", "status"),
    )

    sa.Table(
        "estimating_rules",
        md,
        *_record_columns(),
        sa.Column("rule_code", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("category", sa.String(100), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False, index=True),
        sa.Column("jurisdiction", sa.String(200), nullable=True, index=True),
        sa.Column("source_reference", sa.Text(), nullable=True),
        sa.Column("source_page", sa.String(100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("conflict_resolution", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("test_cases", sa.JSON(), nullable=True),
        sa.Column("author_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approver_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "supersedes_id", sa.String(36), sa.ForeignKey("estimating_rules.id"), nullable=True
        ),
        sa.UniqueConstraint("rule_code", "version", name="uq_rule_code_version"),
    )

    sa.Table(
        "change_proposals",
        md,
        *_record_columns(),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", sa.String(100), nullable=True, index=True),
        sa.Column("proposal_type", sa.String(50), nullable=False),
        sa.Column("proposed_data", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("submitted_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )

    sa.Table(
        "customers",
        md,
        *_record_columns(),
        sa.Column("name", sa.String(300), nullable=False, index=True),
        sa.Column("legal_name", sa.String(300), nullable=True),
        sa.Column("tax_identifier", sa.String(100), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("billing_address", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
    )

    sa.Table(
        "contacts",
        md,
        *_record_columns(),
        sa.Column(
            "customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=False, index=True
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("position", sa.String(200), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
    )

    sa.Table(
        "projects",
        md,
        *_record_columns(),
        sa.Column(
            "customer_id", sa.String(36), sa.ForeignKey("customers.id"), nullable=True, index=True
        ),
        sa.Column("reference", sa.String(100), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("site_address", sa.Text(), nullable=True),
        sa.Column("jurisdiction", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("product_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("material_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("labour_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    sa.Table(
        "estimates",
        md,
        *_record_columns(),
        sa.Column(
            "project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False, index=True
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reference", sa.String(150), nullable=False, unique=True, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("tax_name", sa.String(30), nullable=False),
        sa.Column("tax_rate", sa.Numeric(9, 6), nullable=False),
        sa.Column("product_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("material_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("labour_markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("assumptions", sa.JSON(), nullable=True),
        sa.Column("exclusions", sa.JSON(), nullable=True),
        sa.Column("qualifications", sa.JSON(), nullable=True),
        sa.Column(
            "pricing_release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=True
        ),
        sa.Column(
            "technical_release_id",
            sa.String(36),
            sa.ForeignKey("library_releases.id"),
            nullable=True,
        ),
        sa.Column(
            "rules_release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=True
        ),
        sa.Column(
            "formula_release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=True
        ),
        sa.Column(
            "brand_release_id", sa.String(36), sa.ForeignKey("library_releases.id"), nullable=True
        ),
        sa.Column("subtotal_ex_tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("tax_total", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_incl_tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("project_id", "revision", name="uq_project_estimate_revision"),
    )

    sa.Table(
        "openings",
        md,
        *_record_columns(),
        sa.Column(
            "estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False, index=True
        ),
        sa.Column("defect_id", sa.String(100), nullable=True, index=True),
        sa.Column("opening_code", sa.String(100), nullable=False, index=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("substrate_type", sa.String(200), nullable=True, index=True),
        sa.Column("substrate_plane", sa.String(50), nullable=True, index=True),
        sa.Column("substrate_thickness_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("orientation", sa.String(100), nullable=True, index=True),
        sa.Column("opening_type", sa.String(100), nullable=True),
        sa.Column("width_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("height_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("diameter_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("frl", sa.String(100), nullable=True, index=True),
        sa.Column("physical_model_status", sa.String(30), nullable=False),
        sa.Column("technical_status", sa.String(50), nullable=False),
        sa.Column(
            "selected_technical_variant_id",
            sa.String(36),
            sa.ForeignKey("technical_variants.id"),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("estimate_id", "opening_code", name="uq_estimate_opening_code"),
    )

    sa.Table(
        "services",
        md,
        *_record_columns(),
        sa.Column(
            "opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=False, index=True
        ),
        sa.Column("service_code", sa.String(100), nullable=False, index=True),
        sa.Column("service_type", sa.String(200), nullable=False, index=True),
        sa.Column("material", sa.String(200), nullable=True, index=True),
        sa.Column("nominal_size_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("outside_diameter_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("width_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("height_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("insulation_type", sa.String(200), nullable=True),
        sa.Column("insulation_thickness_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("centre_x_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("centre_y_mm", sa.Numeric(18, 4), nullable=True),
        sa.Column("evidence_status", sa.String(30), nullable=False),
        sa.Column("confidence", sa.Numeric(9, 4), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("opening_id", "service_code", name="uq_opening_service_code"),
    )

    sa.Table(
        "estimate_lines",
        md,
        *_record_columns(),
        sa.Column(
            "estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False, index=True
        ),
        sa.Column(
            "opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=True, index=True
        ),
        sa.Column(
            "service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=True, index=True
        ),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("component_type", sa.String(50), nullable=False, index=True),
        sa.Column("component_reference", sa.String(200), nullable=True, index=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("base_unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("waste_factor", sa.Numeric(9, 6), nullable=False),
        sa.Column("markup_override", sa.Numeric(9, 6), nullable=True),
        sa.Column("applied_markup", sa.Numeric(9, 6), nullable=False),
        sa.Column("markup_source", sa.String(100), nullable=False),
        sa.Column("unit_sell", sa.Numeric(18, 4), nullable=False),
        sa.Column("subtotal_ex_tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_incl_tax", sa.Numeric(18, 4), nullable=False),
        sa.Column("pricing_method", sa.String(80), nullable=False),
        sa.Column("commercial_recovery_status", sa.String(80), nullable=False),
        sa.Column("rate_source", sa.String(300), nullable=True),
        sa.Column("formula_version", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("estimate_id", "line_number", name="uq_estimate_line_number"),
    )

    sa.Table(
        "rule_evaluations",
        md,
        *_record_columns(),
        sa.Column(
            "estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False, index=True
        ),
        sa.Column(
            "opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=True, index=True
        ),
        sa.Column(
            "rule_id",
            sa.String(36),
            sa.ForeignKey("estimating_rules.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("result", sa.String(30), nullable=False, index=True),
        sa.Column("severity", sa.String(30), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("rule_version", sa.Integer(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=True),
    )

    sa.Table(
        "approvals",
        md,
        *_record_columns(),
        sa.Column("entity_type", sa.String(100), nullable=False, index=True),
        sa.Column("entity_id", sa.String(100), nullable=False, index=True),
        sa.Column("approval_type", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("requested_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_by_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(64), nullable=True),
    )

    sa.Table(
        "background_jobs",
        md,
        *_record_columns(),
        sa.Column("job_type", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    return md


def upgrade() -> None:
    _baseline_metadata().create_all(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    _baseline_metadata().drop_all(bind=op.get_bind(), checkfirst=True)
