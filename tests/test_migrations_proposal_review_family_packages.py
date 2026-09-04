from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_proposal_review_family_package_migration_upgrades_existing_0019_database(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "proposal-review-family-packages.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0019_report_evidence_family_manifests")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    columns = {
        column["name"]: column for column in inspector.get_columns("proposal_review_packages")
    }
    assert {
        "package_kind",
        "report_evidence_family_manifest_id",
        "report_evidence_family_manifest_sha256",
        "report_evidence_family_manifest_approval_reference",
    }.issubset(columns)
    assert columns["project_evidence_id"]["nullable"] is True
    assert columns["report_sha256"]["nullable"] is True
    assert columns["approved_expected_label_manifest_id"]["nullable"] is True
    assert columns["approved_expected_label_manifest_sha256"]["nullable"] is True
    foreign_keys = inspector.get_foreign_keys("proposal_review_packages")
    assert any(
        foreign_key["constrained_columns"] == ["report_evidence_family_manifest_id"]
        and foreign_key["referred_table"] == "report_evidence_family_manifests"
        for foreign_key in foreign_keys
    )
    constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("proposal_review_packages")
    }
    assert (
        "package_kind = 'single_report'" in constraints["ck_proposal_review_package_kind_binding"]
    )
    assert (
        "package_kind = 'report_evidence_family'"
        in constraints["ck_proposal_review_package_kind_binding"]
    )
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0026_single_active_technical_release"
        )
    engine.dispose()
