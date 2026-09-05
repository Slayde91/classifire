from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_replacement_lock_outcome_migration_upgrades_existing_0024_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "replacement-lock-outcomes.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(
        database_url,
        environment,
        "0024_signed_physical_model_lock_replacement_admissions",
    )
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    table = "physical_model_lock_replacement_outcomes"
    assert table in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns(table)}
    assert {
        "admission_record_id",
        "replacement_lock_admission_id",
        "project_id",
        "estimate_id",
        "amendment_outcome_id",
        "superseded_lock_id",
        "replacement_lock_id",
        "replacement_lock_content_hash",
        "replacement_lock_envelope_sha256",
        "preflight_receipt_sha256",
        "created_by_user_id",
        "locked_at",
        "physical_model_lock_created",
        "downstream_authority_granted",
        "execution_receipt_json",
        "execution_receipt_sha256",
    }.issubset(columns)
    unique_sets = {
        tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints(table)
    }
    for expected in (
        ("admission_record_id",),
        ("replacement_lock_admission_id",),
        ("amendment_outcome_id",),
        ("superseded_lock_id",),
        ("replacement_lock_id",),
        ("replacement_lock_content_hash",),
        ("replacement_lock_envelope_sha256",),
        ("execution_receipt_sha256",),
    ):
        assert expected in unique_sets
    foreign_keys = inspector.get_foreign_keys(table)
    assert any(
        foreign_key["constrained_columns"] == ["admission_record_id"]
        and foreign_key["referred_table"] == "physical_model_lock_replacement_admissions"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["replacement_lock_id"]
        and foreign_key["referred_table"] == "physical_model_locks"
        for foreign_key in foreign_keys
    )
    checks = {constraint["name"] for constraint in inspector.get_check_constraints(table)}
    assert "ck_pm_lock_replacement_outcome_created" in checks
    assert "ck_pm_lock_replacement_outcome_no_authority" in checks
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0029_draft_system_matches"
        )
    engine.dispose()
