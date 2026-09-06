from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_proposal_review_annotation_migration_upgrades_existing_0020_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "proposal-review-annotations.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0020_proposal_review_family_packages")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "proposal_review_annotations" in inspector.get_table_names()
    columns = {
        column["name"] for column in inspector.get_columns("proposal_review_annotations")
    }
    assert {
        "annotation_id",
        "proposal_review_package_id",
        "proposal_review_package_redaction_id",
        "package_manifest_sha256",
        "reviewer_summary_sha256",
        "annotation_sha256",
        "scope_id",
        "finding_state",
        "reason_code",
        "proposal_only",
        "reviewed_by_user_id",
        "recorded_at",
    }.issubset(columns)
    foreign_keys = inspector.get_foreign_keys("proposal_review_annotations")
    assert any(
        foreign_key["constrained_columns"] == ["proposal_review_package_id"]
        and foreign_key["referred_table"] == "proposal_review_packages"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    )
    assert any(
        foreign_key["constrained_columns"] == ["proposal_review_package_redaction_id"]
        and foreign_key["referred_table"] == "proposal_review_package_redactions"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    )
    constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("proposal_review_annotations")
    }
    assert "human_verification_required" in constraints[
        "ck_proposal_review_annotation_finding_state"
    ]
    assert "proposal_only = true" in constraints[
        "ck_proposal_review_annotation_proposal_only"
    ]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0036_draft_client_requests"
        )
    engine.dispose()