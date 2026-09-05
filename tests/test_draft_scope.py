from __future__ import annotations

import copy
import hashlib
import json
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    DraftScope,
    DraftScopeRevision,
    Estimate,
    Opening,
    Project,
    Service,
    User,
)
from classifire.physical_models import PhysicalModelLock
from classifire.services.draft_scope import (
    DraftScopeError,
    create_draft_project,
    create_for_existing_project,
    get_draft,
    list_drafts,
    read_revision,
    revision_bytes,
    save_revision,
    validate_payload,
)


def uid(number):
    return str(UUID(int=number))


def sample_payload():
    return {
        "defects": [{"id": uid(1), "label": "D-1", "description": "Synthetic mixed scope"}],
        "openings": [
            {
                "id": uid(2),
                "label": "O-1",
                "defect_id": uid(1),
                "plane": "wall",
                "substrate": "Unknown",
            },
            {"id": uid(3), "label": "O-2", "defect_id": uid(1), "plane": "floor"},
            {"id": uid(4), "label": "Blank opening", "blank": True},
        ],
        "services": [
            {
                "id": uid(5),
                "label": "S-1",
                "opening_ids": [uid(2), uid(3)],
                "service_type": "cable bundle",
                "quantity": "2.00",
                "unit": "each",
                "state": "Inferred",
            },
            {"id": uid(6), "label": "S-2", "opening_ids": [uid(2)]},
        ],
        "observations": [{"id": uid(7), "text": "Site verification required"}],
        "assumptions": ["Manual input without source evidence"],
        "exclusions": ["No technical system or price selected"],
    }


@pytest.fixture
def setup(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "drafts.sqlite"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        users = [
            User(
                id=uid(number),
                email=f"draft-{number}@example.test",
                full_name=f"User {number}",
                password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
                role=role,
                is_active=True,
            )  # noqa: S106
            for number, role in (
                (100, "estimator"),
                (101, "estimator"),
                (102, "administrator"),
                (103, "read_only"),
            )
        ]
        db.add_all(users)
        db.commit()
    yield factory
    engine.dispose()


def test_create_edit_reopen_historical_download_and_canonical_separation(setup, tmp_path):
    with setup() as db:
        owner = db.get(User, uid(100))
        draft = create_draft_project(db, owner, "SYNTHETIC-DRAFT", "Synthetic prototype")
        assert draft.latest_revision == 1
        first_bytes = revision_bytes(db, owner, draft.id)
        original = json.loads(first_bytes)
        assert original["state"] == "Draft"
        assert original["provenance"] == "manual"
        assert original["review_status"] == "unreviewed"
        assert original["parent_hash"] is None
        second = save_revision(db, owner, draft.id, 1, sample_payload())
        assert second["parent_hash"] == original["sha256"]
        assert second["content"]["services"][0]["quantity"] == "2"
        assert second["content"]["services"][1]["quantity"] is None
        assert second["content"]["services"][0]["opening_ids"] == [uid(2), uid(3)]
        assert draft.latest_revision == 2
        draft_id = draft.id
        db.commit()
    with setup() as db:
        owner = db.get(User, uid(100))
        assert read_revision(db, owner, draft_id) == second
        assert revision_bytes(db, owner, draft_id, 1) == first_bytes
        blob = revision_bytes(db, owner, draft_id, 2)
        (tmp_path / "synthetic-draft-scope.json").write_bytes(blob)
        parsed = json.loads(blob)
        digest = parsed.pop("sha256")
        assert (
            hashlib.sha256(
                json.dumps(
                    parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            ).hexdigest()
            == digest
        )
        assert list_drafts(db, owner)[0].id == draft_id
        for model in (Estimate, Opening, Service, PhysicalModelLock):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        audits = db.scalars(select(AuditEvent)).all()
        assert {event.action for event in audits} == {"draft_scope.save", "draft_scope.download"}
        assert all(set(event.new_value) == {"revision", "sha256"} for event in audits)


def test_caller_rollback_removes_project_draft_revision_and_audit(setup):
    with setup() as db:
        create_draft_project(db, db.get(User, uid(100)), "ROLLBACK", "Must not persist")
        db.rollback()
    with setup() as db:
        for model in (Project, DraftScope, DraftScopeRevision, AuditEvent):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_stale_save_refused_without_mutating_saved_history(setup):
    with setup() as db:
        draft = create_draft_project(db, db.get(User, uid(100)), "CONFLICT", "Conflict")
        db.commit()
        draft_id = draft.id
    with setup() as first, setup() as stale:
        actor1, actor2 = first.get(User, uid(100)), stale.get(User, uid(100))
        assert read_revision(stale, actor2, draft_id)["revision"] == 1
        saved = save_revision(first, actor1, draft_id, 1, sample_payload())
        first.commit()
        with pytest.raises(DraftScopeError, match="DRAFT_REVISION_CONFLICT"):
            save_revision(stale, actor2, draft_id, 1, {})
        assert read_revision(stale, actor2, draft_id) == saved
        assert stale.scalar(select(func.count()).select_from(DraftScopeRevision)) == 2
        stale.rollback()


def test_role_and_object_boundaries_and_existing_project_policy(setup):
    with setup() as db:
        owner, stranger, admin, reader = [
            db.get(User, uid(number)) for number in (100, 101, 102, 103)
        ]
        draft = create_draft_project(db, owner, "PRIVATE", "Private draft")
        db.commit()
        assert list_drafts(db, stranger) == []
        for action in (
            lambda: get_draft(db, stranger, draft.id),
            lambda: read_revision(db, stranger, draft.id),
            lambda: revision_bytes(db, stranger, draft.id),
            lambda: save_revision(db, stranger, draft.id, 1, {}),
        ):
            with pytest.raises(DraftScopeError, match="DRAFT_NOT_FOUND"):
                action()
        assert get_draft(db, admin, draft.id).id == draft.id
        for actor in (reader,):
            with pytest.raises(DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
                create_draft_project(db, actor, "DENIED", "Denied")
        with pytest.raises(DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            create_for_existing_project(db, owner, draft.project_id)
        other = create_for_existing_project(db, admin, draft.project_id)
        assert other.owner_user_id == admin.id
        owner.is_active = False
        db.commit()
        with pytest.raises(DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            read_revision(db, owner, draft.id)
        with pytest.raises(DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            create_draft_project(db, object(), "AGENT", "Not human")


def test_duplicate_project_reference_rolls_back_only_attempt(setup):
    with setup() as db:
        owner = db.get(User, uid(100))
        draft = create_draft_project(db, owner, "UNIQUE", "First")
        with pytest.raises(DraftScopeError, match="DRAFT_PROJECT_CONFLICT"):
            create_draft_project(db, owner, "UNIQUE", "Second")
        assert get_draft(db, owner, draft.id).project.name == "First"
        assert db.scalar(select(func.count()).select_from(Project)) == 1
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


@pytest.mark.parametrize(
    "mutation,code",
    [
        (lambda p: p["services"][0].update(quantity="NaN"), "DRAFT_PAYLOAD_INVALID"),
        (lambda p: p["services"][0].update(quantity=1), "DRAFT_PAYLOAD_INVALID"),
        (lambda p: p["services"][0].update(quantity="-1"), "DRAFT_PAYLOAD_INVALID"),
        (lambda p: p["services"][0].update(opening_ids=[uid(999)]), "DRAFT_INVALID_REFERENCE"),
        (lambda p: p["services"][0].update(opening_ids=[uid(2), uid(2)]), "DRAFT_DUPLICATE_LINK"),
        (
            lambda p: p["services"][0].update(opening_ids=[uid(4)]),
            "DRAFT_BLANK_OPENING_HAS_SERVICE",
        ),
        (lambda p: p["openings"][0].update(defect_id=uid(999)), "DRAFT_INVALID_REFERENCE"),
        (lambda p: p["defects"][0].update(id=uid(2)), "DRAFT_DUPLICATE_ID"),
        (lambda p: p.update(approved=True), "DRAFT_PAYLOAD_INVALID"),
        (lambda p: p["openings"][0].update(source_file_id=uid(55)), "DRAFT_PAYLOAD_INVALID"),
        (lambda p: p.update(assumptions=["a" * 270000]), "DRAFT_PAYLOAD_INVALID"),
    ],
)
def test_invalid_payload_fails_before_persistence(setup, mutation, code):
    with setup() as db:
        owner = db.get(User, uid(100))
        draft = create_draft_project(db, owner, "INVALID", "Invalid")
        payload = sample_payload()
        mutation(payload)
        with pytest.raises(DraftScopeError, match=code):
            save_revision(db, owner, draft.id, 1, payload)
        assert draft.latest_revision == 1
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


def test_validation_is_pure_missing_data_saveable_and_no_quantity_assumption():
    payload = sample_payload()
    before = copy.deepcopy(payload)
    model, findings = validate_payload(payload)
    assert payload == before
    assert model.services[1].quantity is None
    assert {row["code"] for row in findings} >= {
        "MANUAL_UNREVIEWED",
        "QUANTITY_UNRESOLVED",
        "OPENING_FACTS_MISSING",
    }
    assert all(row["severity"] == "warning" for row in findings)
    empty, findings = validate_payload({})
    assert empty.services == []
    assert "SCOPE_EMPTY" in {row["code"] for row in findings}


@pytest.mark.parametrize(
    "column,value",
    [
        ("envelope_json", "{}"),
        ("content_hash", "0" * 64),
        ("created_by_id", uid(101)),
        ("parent_hash", "1" * 64),
    ],
)
def test_tampered_revision_refuses_download_and_successor(setup, column, value):
    with setup() as db:
        owner = db.get(User, uid(100))
        draft = create_draft_project(db, owner, "TAMPER", "Tamper")
        db.execute(text(f"UPDATE draft_scope_revisions SET {column} = :value"), {"value": value})  # noqa: S608 - parameterized values and fixed test columns
        db.commit()
        with pytest.raises(DraftScopeError, match="DRAFT_REVISION_INTEGRITY_FAILED"):
            revision_bytes(db, owner, draft.id)
        with pytest.raises(DraftScopeError, match="DRAFT_REVISION_INTEGRITY_FAILED"):
            save_revision(db, owner, draft.id, 1, {})
        assert get_draft(db, owner, draft.id).latest_revision == 1


def test_saved_revision_caller_rollback_restores_latest_and_history(setup):
    with setup() as db:
        owner = db.get(User, uid(100))
        draft = create_draft_project(db, owner, "SAVE-ROLLBACK", "Save rollback")
        db.commit()
        save_revision(db, owner, draft.id, 1, sample_payload())
        db.rollback()
        assert read_revision(db, owner, draft.id)["revision"] == 1
        assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 1


@pytest.mark.parametrize("backend", ["sqlite", "postgresql"])
def test_simultaneous_saves_keep_one_complete_successor(tmp_path, backend):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from test_shared_file_containment import _postgres_test_url

    url = (
        _postgres_test_url()
        if backend == "postgresql"
        else "sqlite:///" + str(tmp_path / "race.sqlite")
    )
    engine = create_engine(url)
    if backend == "postgresql":
        # Helper permits only the explicitly configured loopback disposable DB.
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        with factory() as db:
            actor = User(
                id=uid(100),
                email="concurrent@example.test",
                full_name="Synthetic owner",
                password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
                role="estimator",
                is_active=True,
            )  # noqa: S106
            db.add(actor)
            db.flush()
            draft = create_draft_project(db, actor, "RACE", "Concurrent prototype")
            draft_id = draft.id
            db.commit()
        barrier = Barrier(2)

        def contender(label):
            with factory() as db:
                actor = db.get(User, uid(100))
                barrier.wait(timeout=5)
                try:
                    saved = save_revision(db, actor, draft_id, 1, {"assumptions": [label]})
                    db.commit()
                    return saved
                except DraftScopeError as exc:
                    db.rollback()
                    return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(contender, label) for label in ("First", "Second")]
            results = [task.result(timeout=15) for task in pending]
        assert results.count("DRAFT_REVISION_CONFLICT") == 1
        winner = next(result for result in results if isinstance(result, dict))
        with factory() as db:
            assert read_revision(db, db.get(User, uid(100)), draft_id) == winner
            assert db.scalar(select(func.count()).select_from(DraftScopeRevision)) == 2
            assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2
    finally:
        if backend == "postgresql":
            Base.metadata.drop_all(engine)
        engine.dispose()
