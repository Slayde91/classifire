from __future__ import annotations

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _migration_environment, _upgrade

from classifire.models import User
from classifire.services import draft_project_packages as packages
from classifire.services import draft_scope as scopes
from classifire.services.deployment_lineage import assess_deployment_lineage


def test_upgrade_preserves_scope_and_retains_packages(tmp_path):
    url = "sqlite:///" + (tmp_path / "package-upgrade.sqlite").as_posix()
    environment = _migration_environment(tmp_path, url)
    _upgrade(url, environment, "0033_draft_pricing_sources")
    engine = create_engine(url)
    with Session(engine) as db:
        actor = User(
            id=uid(100),
            email="package@example.test",
            full_name="Synthetic owner",
            password_hash="unused",  # noqa: S106 - synthetic migration fixture
            role="administrator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.commit()
        draft = scopes.create_draft_project(db, actor, "PACKAGE-UPGRADE", "Synthetic package")
        scopes.save_revision(db, actor, draft.id, 1, sample_payload())
        old = scopes.read_revision(db, actor, draft.id, 2)
        draft_id = draft.id
        db.commit()
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    _upgrade(url, environment, "head", enforce_sqlite_foreign_keys=True)
    assert "draft_project_packages" in inspect(engine).get_table_names()
    with Session(engine) as db:
        actor = db.get(User, uid(100))
        assert scopes.read_revision(db, actor, draft_id, 2) == old
        assert assess_deployment_lineage(db).code == "CLEAN_STACK_HEAD_CONFIRMED"
        preview = packages.preview(db, actor, draft_id, {"scope_revision": 2})
        row = packages.create_package(
            db, actor, draft_id, {"scope_revision": 2}, 0, preview["preview_hash"]
        )
        identifier = row.id
        content = packages.package_bytes(db, actor, draft_id, identifier)
        db.commit()
    with Session(engine) as db:
        assert packages.package_bytes(db, db.get(User, uid(100)), draft_id, identifier) == content
