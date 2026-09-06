from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_proposal_review_reader_assignment_migration_upgrades_0014_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "proposal-review-reader-assignments.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0014_proposal_review_package_lifecycle")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "proposal_review_reader_assignments" in inspector.get_table_names()
    columns = {
        column["name"] for column in inspector.get_columns("proposal_review_reader_assignments")
    }
    assert {
        "user_id",
        "scope_kind",
        "project_id",
        "proposal_review_package_id",
        "active",
        "granted_by_user_id",
        "granted_at",
        "revoked_by_user_id",
        "revoked_at",
        "revocation_reason_code",
    }.issubset(columns)
    constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("proposal_review_reader_assignments")
    }
    assert "scope_kind = 'project'" in constraints["ck_proposal_review_reader_assignment_scope"]
    assert "active = true" in constraints["ck_proposal_review_reader_assignment_lifecycle"]
    foreign_keys = inspector.get_foreign_keys("proposal_review_reader_assignments")
    assert any(
        foreign_key["constrained_columns"] == ["proposal_review_package_id"]
        and foreign_key["referred_table"] == "proposal_review_packages"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0036_draft_client_requests"
        )
    engine.dispose()