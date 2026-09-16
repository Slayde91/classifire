from __future__ import annotations

from uuid import uuid4

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from test_draft_scope import sample_payload, uid
from test_migrations_physical_foundation import _upgrade
from test_migrations_postgresql_history import _environment
from test_migrations_postgresql_history import migration_postgresql as _postgres

from classifire.config import Settings
from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_work_records as work
from classifire.services.deployment_lineage import assess_deployment_lineage

migration_postgresql = _postgres


def test_work_log_forward_migration_preserves_scope_and_appends_revision(
    migration_postgresql, tmp_path
):
    url, engine, schema = migration_postgresql
    env = _environment(tmp_path, url, schema)
    _upgrade(url, env, "0049_draft_proposal_decisions")
    with Session(engine) as db:
        actor = User(
            id=uid(900),
            email="work-migration@example.test",
            full_name="Synthetic",
            password_hash="unused",  # noqa: S106 - non-authenticating synthetic fixture
            role="estimator",
            is_active=True,
        )  # noqa: S106
        db.add(actor)
        db.flush()
        draft = scopes.create_draft_project(db, actor, "WORK-MIGRATION", "Synthetic")
        saved = scopes.save_revision(db, actor, draft.id, 1, sample_payload())
        identity = draft.id
        exact = scopes.revision_bytes(db, actor, identity, 2)
        db.commit()
        assert assess_deployment_lineage(db).code == "DATABASE_MIGRATION_REQUIRED"
    before = set(inspect(engine).get_table_names())
    _upgrade(url, env, "head")
    assert set(inspect(engine).get_table_names()) - before == {
        "draft_work_records",
        "draft_work_record_revisions",
    }
    with Session(engine) as db:
        actor = db.get(User, uid(900))
        assert scopes.revision_bytes(db, actor, identity, 2) == exact
        assert assess_deployment_lineage(db).status == "READY"
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "0050_draft_work_records"
        )
        payload = {
            "record_id": str(uuid4()),
            "expected_revision": 0,
            "scope_revision": saved["revision"],
            "opening_id": uid(4),
            "note": "Synthetic blank-opening work; inspection unknown",
        }
        settings = Settings(_env_file=None, storage_root=tmp_path / "storage")
        preview = work.preview(db, actor, identity, payload, settings=settings)
        record = work.save(db, actor, identity, payload, preview["sha256"], settings=settings)
        db.commit()
    with Session(engine) as db:
        actor = db.get(User, uid(900))
        assert (
            work.read(db, actor, identity, record["record_id"], 1, settings=settings)["record"]
            == record
        )
        assert scopes.revision_bytes(db, actor, identity, 2) == exact
