from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_replacement_lock_admission_migration_upgrades_existing_0023_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "replacement-lock-admissions.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0023_signed_physical_model_lock_amendment_outcomes")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    table = "physical_model_lock_replacement_admissions"
    assert table in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns(table)}
    assert {
        "replacement_lock_admission_id",
        "project_id",
        "estimate_id",
        "amendment_outcome_id",
        "amendment_admission_id",
        "amendment_envelope_sha256",
        "amendment_execution_receipt_sha256",
        "visual_validation_receipt_sha256",
        "superseded_lock_id",
        "superseded_lock_content_hash",
        "replacement_lock_content_hash",
        "replacement_lock_reason",
        "policy_versions",
        "replacement_lock_envelope_json",
        "replacement_lock_envelope_sha256",
        "issuer_id",
        "signing_key_id",
        "signature_algorithm",
        "issued_at",
        "expires_at",
        "preflight_receipt_json",
        "preflight_receipt_sha256",
    }.issubset(columns)
    unique_sets = {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table)
    }
    assert ("replacement_lock_admission_id",) in unique_sets
    assert ("replacement_lock_envelope_sha256",) in unique_sets
    assert ("preflight_receipt_sha256",) in unique_sets
    foreign_keys = inspector.get_foreign_keys(table)
    assert any(
        foreign_key["constrained_columns"] == ["amendment_outcome_id"]
        and foreign_key["referred_table"] == "physical_model_lock_amendment_outcomes"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["superseded_lock_id"]
        and foreign_key["referred_table"] == "physical_model_locks"
        for foreign_key in foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0030_draft_estimates"
        )
    engine.dispose()
