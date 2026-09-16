from __future__ import annotations

from sqlalchemy import inspect, text
from test_migrations_physical_foundation import _upgrade
from test_migrations_postgresql_history import _environment
from test_migrations_postgresql_history import migration_postgresql as _postgres

migration_postgresql = _postgres


def test_work_photo_forward_migration_adds_only_bound_draft_source(
    migration_postgresql, tmp_path
):
    url, engine, schema = migration_postgresql
    environment = _environment(tmp_path, url, schema)
    _upgrade(url, environment, "0050_draft_work_records")
    before = set(inspect(engine).get_table_names())

    _upgrade(url, environment, "head")

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) - before == {"draft_work_photo_sources"}
    assert {
        "id",
        "draft_scope_id",
        "stored_file_id",
        "source_sha256",
        "source_size_bytes",
        "created_by_id",
        "original_filename",
        "scan_json",
        "processing_error",
        "document_json",
        "document_sha256",
    }.issubset({column["name"] for column in inspector.get_columns("draft_work_photo_sources")})
    assert {
        "ix_draft_work_photo_sources_draft_scope_id",
    }.issubset({index["name"] for index in inspector.get_indexes("draft_work_photo_sources")})
    assert any(
        foreign_key["constrained_columns"]
        == ["stored_file_id", "source_sha256", "source_size_bytes"]
        and foreign_key["referred_table"] == "stored_files"
        for foreign_key in inspector.get_foreign_keys("draft_work_photo_sources")
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0051_draft_work_photos"
        )
