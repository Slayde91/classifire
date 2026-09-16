from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from test_draft_scope import sample_payload, uid
from test_draft_scope import setup as _setup

from classifire.config import Settings
from classifire.models import DraftWorkRecord, DraftWorkRecordRevision, User
from classifire.services import draft_scope as scopes
from classifire.services import draft_work_records as work

setup = _setup


@pytest.fixture
def case(setup, tmp_path):
    with setup() as db:
        actor = db.get(User, uid(100))
        draft = scopes.create_draft_project(db, actor, "WORK-SYNTHETIC", "Synthetic work log")
        scope = scopes.save_revision(db, actor, draft.id, 1, sample_payload())
        db.commit()
        identity = draft.id
    content = dict(
        record_id=str(uuid4()),
        expected_revision=0,
        scope_revision=scope["revision"],
        opening_id=uid(2),
        service_id=uid(6),
        note="Reported patching; inspection unknown.",
        reported_by="",
        reported_role="unknown",
        observed_at="",
        unknowns="System and quantity unknown.",
        evidence_indices=[],
    )
    return setup, identity, content, Settings(_env_file=None, storage_root=tmp_path / "storage")


def test_preview_save_append_restart_exact_export_and_no_canonical_writes(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        statements = []

        def observe(_c, _cur, statement, _params, _ctx, _many):
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                statements.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", observe)
        proposed = work.preview(db, actor, identity, content, settings=settings)
        assert not statements
        first = work.save(db, actor, identity, content, proposed["sha256"], settings=settings)
        assert first["state"] == "Draft" and first["review_status"] == "unverified"
        assert first["content"]["observed_at"] == "" and first["content"]["reported_by"] == ""
        assert all(
            any(
                name in sql.lower()
                for name in ("draft_work_records", "draft_work_record_revisions", "audit_events")
            )
            for sql in statements
        )
        event.remove(db.get_bind(), "before_cursor_execute", observe)
        db.commit()
        original = work.report_archive(
            db, actor, identity, content["record_id"], 1, settings=settings
        )
        amended = content | {
            "expected_revision": 1,
            "note": "Reported correction; still unverified.",
        }
        preview = work.preview(db, actor, identity, amended, settings=settings)
        second = work.save(db, actor, identity, amended, preview["sha256"], settings=settings)
        db.commit()
        assert second["parent_hash"] == first["sha256"]
    with factory() as db:
        actor = db.get(User, uid(100))
        assert (
            work.read(db, actor, identity, content["record_id"], 1, settings=settings)["record"]
            == first
        )
        assert (
            work.report_archive(
                db,
                actor,
                identity,
                content["record_id"],
                1,
                settings=settings,
            )
            == original
        )
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            assert archive.testzip() is None
            assert set(archive.namelist()) == {"manifest.json", "report.html", "work-record.json"}
            assert json.loads(archive.read("work-record.json")) == first
            for name, spec in json.loads(archive.read("manifest.json"))["members"].items():
                raw = archive.read(name)
                assert len(raw) == spec["size_bytes"]
                assert hashlib.sha256(raw).hexdigest() == spec["sha256"]
        assert len(work.history(db, actor, identity)) == 2


def test_changed_preview_replay_scope_race_and_history_staleness(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        proposed = work.preview(db, actor, identity, content, settings=settings)
        with pytest.raises(scopes.DraftScopeError, match="PREVIEW_CHANGED"):
            work.save(
                db,
                actor,
                identity,
                content | {"note": "changed"},
                proposed["sha256"],
                settings=settings,
            )
        assert db.scalars(select(DraftWorkRecord)).all() == []
        saved = work.save(db, actor, identity, content, proposed["sha256"], settings=settings)
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="REVISION_CONFLICT"):
            work.save(db, actor, identity, content, proposed["sha256"], settings=settings)
        another = content | {"record_id": str(uuid4())}
        pending = work.preview(db, actor, identity, another, settings=settings)
        scopes.save_revision(db, actor, identity, 2, sample_payload())
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="SCOPE_STALE"):
            work.save(db, actor, identity, another, pending["sha256"], settings=settings)
        historical = work.read(db, actor, identity, content["record_id"], 1, settings=settings)
        assert historical["stale"] is True and historical["record"] == saved
        with pytest.raises(scopes.DraftScopeError, match="SCOPE_STALE"):
            work.report_archive(db, actor, identity, content["record_id"], 1, settings=settings)


@pytest.mark.parametrize(
    "changes",
    [
        {"note": " "},
        {"inspection_approved": True},
        {"quantity": 1},
        {"observed_at": "2026-09-16T10:00:00"},
        {"evidence_indices": [True]},
        {"evidence_indices": [0, 0]},
        {"evidence_indices": [-1]},
        {"scope_revision": True},
        {"reported_role": "inspector_approved"},
        {"record_id": "bad"},
    ],
)
def test_invalid_or_authority_fields_fail_closed(case, changes):
    factory, identity, content, settings = case
    with factory() as db:
        with pytest.raises(scopes.DraftScopeError, match="INPUT_INVALID"):
            work.preview(db, db.get(User, uid(100)), identity, content | changes, settings=settings)
        assert db.scalars(select(DraftWorkRecord)).all() == []


@pytest.mark.parametrize("user_id", [101, 103])
def test_foreign_or_readonly_cannot_preview(case, user_id):
    factory, identity, content, settings = case
    with factory() as db:
        with pytest.raises(scopes.DraftScopeError):
            work.preview(db, db.get(User, uid(user_id)), identity, content, settings=settings)


def test_shared_blank_and_unlinked_targets_are_not_inferred(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        for opening, service, blank in [
            (uid(2), uid(5), False),
            (uid(3), uid(5), False),
            (uid(4), None, True),
        ]:
            proposed = work.preview(
                db,
                actor,
                identity,
                content | {"opening_id": opening, "service_id": service},
                settings=settings,
            )
            assert proposed["dependencies"]["selection"]["blank"] is blank
            assert proposed["dependencies"]["selection"]["opening_id"] == opening
        with pytest.raises(scopes.DraftScopeError, match="SELECTION_INVALID"):
            work.preview(db, actor, identity, content | {"opening_id": uid(4)}, settings=settings)
        with pytest.raises(scopes.DraftScopeError, match="EVIDENCE_UNAVAILABLE"):
            work.preview(
                db, actor, identity, content | {"evidence_indices": [0]}, settings=settings
            )


def test_revocation_and_corrupt_history_are_not_disclosed(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        p = work.preview(db, actor, identity, content, settings=settings)
        work.save(db, actor, identity, content, p["sha256"], settings=settings)
        db.commit()
        actor.is_active = False
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="PERMISSION_DENIED"):
            work.read(db, actor, identity, content["record_id"], 1, settings=settings)
        actor.is_active = True
        db.commit()
        row = db.scalar(select(DraftWorkRecordRevision))
        row.envelope_json = row.envelope_json.replace("Reported patching", "Changed assertion")
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="INTEGRITY_FAILED"):
            work.read(db, actor, identity, content["record_id"], 1, settings=settings)


def test_amendment_cannot_retarget_and_timestamp_is_explicit(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        content = copy.deepcopy(content) | {"observed_at": "2026-09-16T14:30:00+10:00"}
        p = work.preview(db, actor, identity, content, settings=settings)
        assert p["content"]["observed_at"] == "2026-09-16T04:30:00+00:00"
        work.save(db, actor, identity, content, p["sha256"], settings=settings)
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="TARGET_CHANGED"):
            work.preview(
                db,
                actor,
                identity,
                content | {"expected_revision": 1, "service_id": None},
                settings=settings,
            )


def test_pre_photo_schema_record_remains_readable_and_exportable(case):
    factory, identity, content, settings = case
    with factory() as db:
        actor = db.get(User, uid(100))
        proposed = work.preview(db, actor, identity, content, settings=settings)
        saved = work.save(db, actor, identity, content, proposed["sha256"], settings=settings)
        row = db.scalar(select(DraftWorkRecordRevision))
        legacy = copy.deepcopy(saved)
        legacy["content"].pop("photo_source_ids")
        legacy["dependencies"].pop("photos")
        legacy["schema_version"] = work.SCHEMA_V1
        legacy.pop("sha256")
        legacy["sha256"] = work._hash(legacy)
        row.content_hash = legacy["sha256"]
        row.envelope_json = work._json(legacy).decode("utf-8")
        db.commit()
    with factory() as db:
        actor = db.get(User, uid(100))
        assert work.read(
            db, actor, identity, content["record_id"], 1, settings=settings
        )["record"] == legacy
        with zipfile.ZipFile(
            io.BytesIO(
                work.report_archive(
                    db, actor, identity, content["record_id"], 1, settings=settings
                )
            )
        ) as archive:
            assert archive.testzip() is None
            report = archive.read("report.html").decode("utf-8")
            assert "Selected direct photos" not in report
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema_version"] == work.SCHEMA_V1
            assert "Unselected direct photos" not in manifest["exclusions"]
