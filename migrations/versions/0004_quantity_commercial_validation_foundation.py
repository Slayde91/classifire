from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_quantity_commercial_validation_foundation"
down_revision = "0003_canonical_physical_technical_foundation"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _record_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("record_version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    tables = _table_names()

    if "quantities" not in tables:
        op.create_table(
            "quantities",
            *_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("required_component_id", sa.String(36), sa.ForeignKey("system_required_components.id"), nullable=True),
            sa.Column("quantity_type", sa.String(80), nullable=False),
            sa.Column("subject_type", sa.String(100), nullable=False),
            sa.Column("subject_id", sa.String(100), nullable=True),
            sa.Column("purpose", sa.Text(), nullable=True),
            sa.Column("numeric_value", sa.Numeric(18, 6), nullable=True),
            sa.Column("range_min", sa.Numeric(18, 6), nullable=True),
            sa.Column("range_max", sa.Numeric(18, 6), nullable=True),
            sa.Column("unit_basis", sa.String(80), nullable=False),
            sa.Column("source_method", sa.String(150), nullable=True),
            sa.Column("formula_id", sa.String(300), nullable=True),
            sa.Column("precision_digits", sa.Integer(), nullable=True),
            sa.Column("rounding_method", sa.String(80), nullable=True),
            sa.Column("waste_factor", sa.Numeric(9, 6), nullable=True),
            sa.Column("conversion_factor", sa.Numeric(18, 8), nullable=True),
            sa.Column("epistemic_type", sa.String(80), nullable=True),
            sa.Column("confidence", sa.String(80), nullable=True),
            sa.Column("risk_status", sa.String(80), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
            sa.Column("provenance", sa.JSON(), nullable=True),
        )
        op.create_index("ix_quantities_estimate_id", "quantities", ["estimate_id"])
        op.create_index("ix_quantities_required_component_id", "quantities", ["required_component_id"])

    if "quantity_formula_inputs" not in tables:
        op.create_table(
            "quantity_formula_inputs",
            *_record_columns(),
            sa.Column("quantity_record_id", sa.String(36), sa.ForeignKey("quantities.id"), nullable=False),
            sa.Column("input_name", sa.String(200), nullable=False),
            sa.Column("input_value", sa.JSON(), nullable=False),
            sa.Column("unit", sa.String(80), nullable=False),
            sa.Column("evidence_class", sa.String(80), nullable=True),
            sa.Column("evidence_ids", sa.JSON(), nullable=True),
            sa.Column("assumption_id", sa.String(100), nullable=True),
            sa.Column("validator_status", sa.String(30), nullable=False),
        )
        op.create_index("ix_quantity_formula_inputs_quantity_record_id", "quantity_formula_inputs", ["quantity_record_id"])

    if "productivity_sources" not in tables:
        op.create_table(
            "productivity_sources",
            *_record_columns(),
            sa.Column("activity", sa.String(200), nullable=False),
            sa.Column("quantity_unit", sa.String(80), nullable=False),
            sa.Column("base_hours_per_unit", sa.Numeric(18, 6), nullable=False),
            sa.Column("source_record_id", sa.String(200), nullable=False),
            sa.Column("source_version", sa.String(100), nullable=True),
            sa.Column("source_quantity", sa.String(200), nullable=True),
            sa.Column("source_crew", sa.String(200), nullable=True),
            sa.Column("source_hours", sa.Numeric(18, 6), nullable=True),
            sa.Column("decomposition_formula", sa.Text(), nullable=True),
            sa.Column("adjustment_formula", sa.Text(), nullable=True),
            sa.Column("executable_formula_id", sa.String(300), nullable=False),
            sa.Column("evidence_class", sa.String(80), nullable=True),
            sa.Column("confidence", sa.String(80), nullable=True),
            sa.Column("approval_status", sa.String(80), nullable=True),
        )
        op.create_index("ix_productivity_sources_activity", "productivity_sources", ["activity"])
        op.create_index("ix_productivity_sources_source_record_id", "productivity_sources", ["source_record_id"])

    if "labour_activities" not in tables:
        op.create_table(
            "labour_activities",
            *_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("required_component_id", sa.String(36), sa.ForeignKey("system_required_components.id"), nullable=True),
            sa.Column("productivity_source_id", sa.String(36), sa.ForeignKey("productivity_sources.id"), nullable=True),
            sa.Column("activity_type", sa.String(80), nullable=False),
            sa.Column("activity_name", sa.String(300), nullable=False),
            sa.Column("scope_output", sa.Text(), nullable=True),
            sa.Column("trade_or_grade", sa.String(150), nullable=True),
            sa.Column("competence", sa.String(200), nullable=True),
            sa.Column("crew_size", sa.Numeric(9, 3), nullable=True),
            sa.Column("labour_quantity_hours", sa.Numeric(18, 6), nullable=True),
            sa.Column("working_conditions", sa.JSON(), nullable=True),
            sa.Column("rate_source", sa.String(300), nullable=True),
            sa.Column("unit_rate", sa.Numeric(18, 4), nullable=True),
            sa.Column("extended_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("included_tools_and_incidentals", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.String(80), nullable=True),
            sa.Column("risk_status", sa.String(80), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
            sa.Column("provenance", sa.JSON(), nullable=True),
        )
        op.create_index("ix_labour_activities_estimate_id", "labour_activities", ["estimate_id"])
        op.create_index("ix_labour_activities_required_component_id", "labour_activities", ["required_component_id"])

    if "pricing_components" not in tables:
        op.create_table(
            "pricing_components",
            *_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=False),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=False),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=True),
            sa.Column("service_id", sa.String(36), sa.ForeignKey("services.id"), nullable=True),
            sa.Column("required_component_id", sa.String(36), sa.ForeignKey("system_required_components.id"), nullable=True),
            sa.Column("parent_estimate_line_id", sa.String(36), sa.ForeignKey("estimate_lines.id"), nullable=True),
            sa.Column("quantity_id", sa.String(36), sa.ForeignKey("quantities.id"), nullable=True),
            sa.Column("component_type", sa.String(100), nullable=False),
            sa.Column("scope_description", sa.Text(), nullable=False),
            sa.Column("unit_basis", sa.String(80), nullable=True),
            sa.Column("rate_source", sa.String(300), nullable=True),
            sa.Column("unit_rate", sa.Numeric(18, 4), nullable=True),
            sa.Column("extended_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("inclusions", sa.JSON(), nullable=True),
            sa.Column("exclusions", sa.JSON(), nullable=True),
            sa.Column("confidence", sa.String(80), nullable=True),
            sa.Column("risk_status", sa.String(80), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="draft"),
            sa.Column("source_reference", sa.Text(), nullable=True),
            sa.Column("provenance", sa.JSON(), nullable=True),
        )
        op.create_index("ix_pricing_components_estimate_id", "pricing_components", ["estimate_id"])
        op.create_index("ix_pricing_components_required_component_id", "pricing_components", ["required_component_id"])

    if "commercial_method_locks" not in tables:
        op.create_table(
            "commercial_method_locks",
            *_record_columns(),
            sa.Column("component_id", sa.String(36), sa.ForeignKey("pricing_components.id"), nullable=False),
            sa.Column("library_search_completed", sa.Boolean(), nullable=True),
            sa.Column("exact_library_match_found", sa.Boolean(), nullable=True),
            sa.Column("parameterised_rate_found", sa.Boolean(), nullable=True),
            sa.Column("component_build_completed", sa.Boolean(), nullable=True),
            sa.Column("expert_estimate_required", sa.Boolean(), nullable=True),
            sa.Column("selected_pricing_method", sa.String(100), nullable=False),
            sa.Column("rejected_rate_candidates", sa.JSON(), nullable=True),
            sa.Column("package15_basis", sa.String(300), nullable=True),
            sa.Column("rate_applicability_result", sa.String(100), nullable=True),
            sa.Column("quantity_formula_result", sa.String(100), nullable=True),
            sa.Column("labour_build_result", sa.String(100), nullable=True),
            sa.Column("recovery_status", sa.String(150), nullable=True),
            sa.Column("provisional_status", sa.String(100), nullable=True),
            sa.Column("anomaly_result", sa.String(150), nullable=True),
            sa.Column("validator_outcome", sa.String(50), nullable=False),
            sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        )
        op.create_index("ix_commercial_method_locks_component_id", "commercial_method_locks", ["component_id"])

    if "commercial_recovery_records" not in tables:
        op.create_table(
            "commercial_recovery_records",
            *_record_columns(),
            sa.Column("component_id", sa.String(36), sa.ForeignKey("pricing_components.id"), nullable=False),
            sa.Column("pricing_line_id", sa.String(36), sa.ForeignKey("estimate_lines.id"), nullable=True),
            sa.Column("recovery_status", sa.String(180), nullable=False),
            sa.Column("economic_activity_key", sa.String(200), nullable=True),
            sa.Column("shared_component_key", sa.String(200), nullable=True),
            sa.Column("recovery_location", sa.String(300), nullable=True),
            sa.Column("allocated_amount_aud_ex_gst", sa.Numeric(18, 4), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("provenance", sa.Text(), nullable=True),
            sa.Column("proof_record_id", sa.String(200), nullable=True),
        )
        op.create_index("ix_commercial_recovery_records_component_id", "commercial_recovery_records", ["component_id"])
        op.create_index("ix_commercial_recovery_records_shared_component_key", "commercial_recovery_records", ["shared_component_key"])

    if "component_requirement_reconciliations" not in tables:
        op.create_table(
            "component_requirement_reconciliations",
            *_record_columns(),
            sa.Column("opening_id", sa.String(36), sa.ForeignKey("openings.id"), nullable=True),
            sa.Column("required_component_id", sa.String(36), sa.ForeignKey("system_required_components.id"), nullable=False),
            sa.Column("generated_component_id", sa.String(36), sa.ForeignKey("pricing_components.id"), nullable=True),
            sa.Column("quantity_record_id", sa.String(36), sa.ForeignKey("quantities.id"), nullable=True),
            sa.Column("pricing_line_id", sa.String(36), sa.ForeignKey("estimate_lines.id"), nullable=True),
            sa.Column("labour_activity_ids", sa.JSON(), nullable=True),
            sa.Column("recovery_status", sa.String(180), nullable=True),
            sa.Column("missing_status", sa.String(180), nullable=True),
            sa.Column("assumption_ids", sa.JSON(), nullable=True),
            sa.Column("technical_consequence", sa.Text(), nullable=True),
            sa.Column("commercial_consequence", sa.Text(), nullable=True),
            sa.Column("result", sa.String(120), nullable=False),
        )
        op.create_index("ix_component_requirement_reconciliations_required_component_id", "component_requirement_reconciliations", ["required_component_id"])

    if "price_anomaly_reviews" not in tables:
        op.create_table(
            "price_anomaly_reviews",
            *_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=True),
            sa.Column("comparison_type", sa.String(120), nullable=False),
            sa.Column("subject_ids", sa.JSON(), nullable=True),
            sa.Column("canonical_signatures", sa.JSON(), nullable=True),
            sa.Column("prices", sa.JSON(), nullable=True),
            sa.Column("physical_differences", sa.JSON(), nullable=True),
            sa.Column("documented_fixed_reason", sa.Text(), nullable=True),
            sa.Column("result", sa.String(180), nullable=False),
            sa.Column("required_action", sa.Text(), nullable=True),
        )
        op.create_index("ix_price_anomaly_reviews_estimate_id", "price_anomaly_reviews", ["estimate_id"])

    if "gate_evidence" not in tables:
        op.create_table(
            "gate_evidence",
            *_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=True),
            sa.Column("gate_type", sa.String(150), nullable=False),
            sa.Column("validator_id", sa.String(200), nullable=False),
            sa.Column("validator_version", sa.String(100), nullable=True),
            sa.Column("input_record_count", sa.Numeric(18, 0), nullable=True),
            sa.Column("exception_count", sa.Numeric(18, 0), nullable=True),
            sa.Column("signed_validator_json_hash", sa.String(64), nullable=True),
            sa.Column("result", sa.String(100), nullable=False),
            sa.Column("required_action", sa.Text(), nullable=True),
            sa.Column("input_table_hashes", sa.JSON(), nullable=True),
            sa.Column("run_id", sa.String(200), nullable=True),
            sa.Column("validation_timestamp", sa.String(100), nullable=True),
        )
        op.create_index("ix_gate_evidence_estimate_id", "gate_evidence", ["estimate_id"])
        op.create_index("ix_gate_evidence_gate_type", "gate_evidence", ["gate_type"])

    if "estimate_certificates" not in tables:
        op.create_table(
            "estimate_certificates",
            *_record_columns(),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=True),
            sa.Column("quantifire_version", sa.String(100), nullable=False),
            sa.Column("active_manifest_hash", sa.String(64), nullable=False),
            sa.Column("governed_table_hashes", sa.JSON(), nullable=True),
            sa.Column("gate_evidence_hash", sa.String(64), nullable=True),
            sa.Column("workbook_structure_hash", sa.String(64), nullable=True),
            sa.Column("proposal_reconciliation_result_hash", sa.String(64), nullable=True),
            sa.Column("proposal_commercial_validity_result_hash", sa.String(64), nullable=True),
            sa.Column("validator_identity", sa.String(300), nullable=True),
            sa.Column("certificate_schema_version", sa.String(100), nullable=True),
            sa.Column("final_certificate_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("signature", sa.Text(), nullable=True),
        )
        op.create_index("ix_estimate_certificates_estimate_id", "estimate_certificates", ["estimate_id"])

    if "audit_trails" not in tables:
        op.create_table(
            "audit_trails",
            *_record_columns(),
            sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id"), nullable=True),
            sa.Column("estimate_id", sa.String(36), sa.ForeignKey("estimates.id"), nullable=True),
            sa.Column("trail_type", sa.String(100), nullable=False),
            sa.Column("subject_type", sa.String(100), nullable=False),
            sa.Column("subject_id", sa.String(100), nullable=True),
            sa.Column("subject_version", sa.String(100), nullable=True),
            sa.Column("status", sa.String(50), nullable=False, server_default="active"),
            sa.Column("security_classification", sa.String(80), nullable=True),
            sa.Column("retention_status", sa.String(80), nullable=True),
            sa.Column("integrity_proof", sa.String(128), nullable=True),
            sa.Column("source_json", sa.JSON(), nullable=True),
        )
        op.create_index("ix_audit_trails_project_id", "audit_trails", ["project_id"])
        op.create_index("ix_audit_trails_estimate_id", "audit_trails", ["estimate_id"])

    if "audit_events" in tables and "audit_trail_id" not in _column_names("audit_events"):
        with op.batch_alter_table("audit_events") as batch:
            batch.add_column(sa.Column("audit_trail_id", sa.String(36), nullable=True))
            batch.create_foreign_key(
                "fk_audit_events_audit_trail_id_audit_trails",
                "audit_trails",
                ["audit_trail_id"],
                ["id"],
            )


def downgrade() -> None:
    tables = _table_names()

    if "audit_events" in tables and "audit_trail_id" in _column_names("audit_events"):
        with op.batch_alter_table("audit_events") as batch:
            batch.drop_constraint("fk_audit_events_audit_trail_id_audit_trails", type_="foreignkey")
            batch.drop_column("audit_trail_id")

    for table in [
        "audit_trails",
        "estimate_certificates",
        "gate_evidence",
        "price_anomaly_reviews",
        "component_requirement_reconciliations",
        "commercial_recovery_records",
        "commercial_method_locks",
        "pricing_components",
        "labour_activities",
        "productivity_sources",
        "quantity_formula_inputs",
        "quantities",
    ]:
        if table in _table_names():
            op.drop_table(table)
