from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from test_migrations_physical_foundation import _migration_environment, _upgrade


def test_technical_document_lineage_migration_upgrades_0015_database(tmp_path: Path) -> None:
    database_path = tmp_path / "technical-document-lineage.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    environment = _migration_environment(tmp_path, database_url)

    _upgrade(database_url, environment, "0015_proposal_review_reader_assignments")
    _upgrade(database_url, environment, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("technical_documents")}
    assert {"source_lineage_json", "source_lineage_sha256"}.issubset(columns)
    constraints = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("technical_documents")
    }
    assert "supersedes_document_id IS NOT NULL" in constraints[
        "ck_technical_document_source_lineage"
    ]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "0039_draft_pdf_suggestions"
        )
    engine.dispose()