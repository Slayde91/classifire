from __future__ import annotations

import json

import pytest
from draft_migration_fixture import fixture, verify_current
from sqlalchemy import MetaData, Table, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_draft_project_packages import base_case as _base_case
from test_draft_project_packages import case as _case
from test_draft_scope import uid
from test_migrations_physical_foundation import _run_migration, _upgrade

from classifire.config import Settings
from classifire.models import DraftSystemMatch, User
from classifire.services import draft_package_materialization as imports
from classifire.services import draft_project_packages as packages
from classifire.services import draft_system_matches as matches

base_case = _base_case
case = _case


def test_import_upgrade_preserves_all_native_work_and_separates_foreign_authority(case, tmp_path):
    url, environment, engine, source, ids, expected = fixture(
        case, tmp_path, "0034_draft_project_packages"
    )
    with engine.connect() as connection:
        before = {
            name: connection.execute(
                select(Table(name, MetaData(), autoload_with=engine))
            ).fetchall()
            for name in (
                "draft_system_matches",
                "draft_system_match_revisions",
                "draft_estimates",
                "draft_estimate_revisions",
                "draft_project_packages",
            )
        }
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    assert {"draft_package_imports", "draft_imported_report_sources"} <= set(
        inspect(engine).get_table_names()
    )
    with engine.connect() as connection:
        for name, rows in before.items():
            table = Table(name, MetaData(), autoload_with=engine)
            columns = [c for c in table.c if c.name != "import_id"]
            assert connection.execute(select(*columns)).fetchall() == rows
        assert connection.execute(text("PRAGMA foreign_key_check")).fetchall() == []
    verify_current(engine, ids, expected)
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert (
            packages.package_bytes(db, actor, ids["draft"], ids["draft_project_packages"])
            == expected["package"]
        )
        # Scope + Match import needs no local technical release for its foreign origin.
        selected = {
            "scope_revision": 2,
            "match_id": ids["draft_system_matches"],
            "match_revision": 1,
        }
        preview = packages.preview(db, actor, ids["draft"], selected)
        package = packages.create_package(
            db, actor, ids["draft"], selected, 1, preview["preview_hash"]
        )
        item = imports.create_import(
            db,
            actor,
            package.archive_bytes,
            expected_sha256=package.archive_hash,
            reference="UPGRADED-IMPORT",
            name="Upgraded import",
            settings=Settings(storage_root=case["storage_root"]),
        )
        local_id = json.loads(item.mapping_json)["match"]["local_id"]
        assert (
            matches.read_match_revision(db, actor, item.draft_scope_id, local_id)["import_origin"][
                "authority"
            ]
            == "foreign_unverified"
        )
        db.commit()
        for changes in ({"release_id": ids["draft_system_matches"]}, {"import_id": None}):
            with pytest.raises(IntegrityError):
                db.execute(
                    DraftSystemMatch.__table__.update()
                    .where(DraftSystemMatch.id == local_id)
                    .values(**changes)
                )
                db.flush()
            db.rollback()
    refusal = _run_migration(
        url, environment, "downgrade", "0034_draft_project_packages", expect_success=False
    )
    assert (
        refusal.returncode != 0
        and "Retained foreign package history cannot be downgraded" in refusal.stderr
    )
    engine.dispose()
