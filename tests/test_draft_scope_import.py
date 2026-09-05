from __future__ import annotations

import copy
import hashlib
import json
from contextlib import contextmanager

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker
from test_draft_scope import sample_payload, uid

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import AuditEvent, DraftScopeRevision, Estimate, Opening, Service, User
from classifire.physical_models import PhysicalModelLock
from classifire.services.draft_scope import (
    IMPORTED_SCHEMA_VERSION,
    MAX_ARTIFACT_BYTES,
    MAX_IMPORT_LINEAGE,
    SCHEMA_VERSION,
    DraftScopeError,
    apply_import,
    create_draft_project,
    preview_import,
    read_revision,
    revision_bytes,
    save_revision,
    validate_portable_artifact,
)


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def reseal(envelope):
    result = copy.deepcopy(envelope)
    result.pop("sha256", None)
    result["sha256"] = hashlib.sha256(encoded(result)).hexdigest()
    return encoded(result)


@pytest.fixture
def case(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "scope-import.sqlite"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        users = [
            User(
                id=uid(number),
                email=f"import-{number}@example.test",
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
        actor = db.get(User, uid(100))
        origin = create_draft_project(db, actor, "ORIGIN", "Synthetic source")
        save_revision(db, actor, origin.id, 1, sample_payload())
        raw = revision_bytes(db, actor, origin.id)
        target = create_draft_project(db, actor, "TARGET", "Synthetic target")
        target_id, origin_id = target.id, origin.id
        db.commit()
    yield factory, target_id, origin_id, raw
    engine.dispose()


def counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (AuditEvent, DraftScopeRevision, Estimate, Opening, Service, PhysicalModelLock)
    }


@contextmanager
def connected(case):
    factory, target_id, origin_id, raw = case
    with factory() as db:
        yield db, db.get(User, uid(100)), target_id, origin_id, raw


def test_preview_is_no_write_and_reports_whole_content_replacement(case):
    with connected(case) as (db, actor, target, _origin, raw):
        before = counts(db)
        statements = []
        connection = db.connection()
        event.listen(
            connection,
            "before_cursor_execute",
            lambda _c, _u, statement, _p, _x, _m: statements.append(statement),
        )
        preview = preview_import(db, actor, target, raw)
        assert counts(db) == before
        assert not any(
            sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
        )
        assert preview["expected_revision"] == 1
        assert preview["current_hash"] == read_revision(db, actor, target)["sha256"]
        assert preview["source_file_sha256"] == hashlib.sha256(raw).hexdigest()
        assert preview["before_counts"]["services"] == 0
        assert preview["after_counts"]["services"] == 2
        assert {finding["code"] for finding in preview["findings"]} >= {
            "IMPORT_HISTORY_UNTRUSTED",
            "QUANTITY_UNRESOLVED",
        }


def test_import_localizes_identity_preserves_v1_bytes_and_records_untrusted_source(case):
    with connected(case) as (db, actor, target, origin, raw):
        original_target = revision_bytes(db, actor, target)
        foreign = json.loads(raw)
        foreign.update(
            artifact_id=uid(900),
            project_id=uid(901),
            created_by=uid(902),
            revision=42,
            parent_hash="a" * 64,
        )
        raw = reseal(foreign)
        preview = preview_import(db, actor, target, raw)
        before = counts(db)
        imported = apply_import(db, actor, target, 1, raw, preview["source_file_sha256"])
        assert imported["schema_version"] == IMPORTED_SCHEMA_VERSION
        assert imported["provenance"] == "imported"
        assert imported["state"] == "Draft"
        assert imported["review_status"] == "unreviewed"
        assert imported["artifact_id"] == target
        assert imported["project_id"] != foreign["project_id"]
        assert imported["created_by"] == actor.id
        assert imported["revision"] == 2
        assert imported["parent_hash"] == json.loads(original_target)["sha256"]
        assert imported["content"] == foreign["content"]
        observed = imported["import_lineage"][0]
        assert observed == {
            key: json.loads(raw)[key]
            for key in (
                "schema_version",
                "artifact_id",
                "project_id",
                "revision",
                "created_by",
                "created_at",
                "sha256",
            )
        } | {"file_sha256": hashlib.sha256(raw).hexdigest()}
        assert revision_bytes(db, actor, target, 1) == original_target
        assert read_revision(db, actor, origin)["schema_version"] == SCHEMA_VERSION
        after = counts(db)
        for name in ("estimates", "openings", "services", "physical_model_locks"):
            assert after[name] == before[name] == 0
        db.commit()
    with connected(case) as (db, actor, target, _origin, _raw):
        assert read_revision(db, actor, target) == imported
        assert validate_portable_artifact(revision_bytes(db, actor, target)) == imported
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "draft_scope.import"))
        assert audit.actor_user_id == actor.id
        assert audit.new_value == {
            "revision": 2,
            "sha256": imported["sha256"],
            "source_file_sha256": hashlib.sha256(raw).hexdigest(),
            "source_sha256": json.loads(raw)["sha256"],
        }
        assert "Synthetic" not in json.dumps(audit.new_value)


def test_v2_download_reimport_and_manual_edits_keep_lineage(case):
    with connected(case) as (db, actor, target, _origin, raw):
        imported = apply_import(db, actor, target, 1, raw, hashlib.sha256(raw).hexdigest())
        imported_bytes = revision_bytes(db, actor, target)
        edited = save_revision(
            db, actor, target, 2, {"assumptions": ["Manual change after import"]}
        )
        assert edited["schema_version"] == IMPORTED_SCHEMA_VERSION
        assert edited["provenance"] == "manual_edit"
        assert edited["import_lineage"] == imported["import_lineage"]
        assert revision_bytes(db, actor, target, 2) == imported_bytes
        edited_bytes = revision_bytes(db, actor, target)
        other = create_draft_project(db, actor, "REIMPORT", "Another synthetic target")
        result = apply_import(
            db, actor, other.id, 1, edited_bytes, hashlib.sha256(edited_bytes).hexdigest()
        )
        assert result["content"] == edited["content"]
        assert result["import_lineage"][:-1] == edited["import_lineage"]
        assert result["import_lineage"][-1]["sha256"] == edited["sha256"]
        assert (
            result["import_lineage"][-1]["file_sha256"] == hashlib.sha256(edited_bytes).hexdigest()
        )
        assert result["parent_hash"] != edited["sha256"]


def test_pure_manual_successors_keep_v1_shape(case):
    with connected(case) as (db, actor, target, _origin, _raw):
        result = save_revision(db, actor, target, 1, sample_payload())
        assert result["schema_version"] == SCHEMA_VERSION
        assert result["provenance"] == "manual"
        assert "import_lineage" not in result


def test_import_requires_exact_file_bytes_and_rejects_stale_replay(case):
    with connected(case) as (db, actor, target, _origin, raw):
        preview = preview_import(db, actor, target, raw)
        before = counts(db)
        reformatted = json.dumps(json.loads(raw), indent=2).encode()
        assert validate_portable_artifact(reformatted)["sha256"] == preview["source"]["sha256"]
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_SOURCE_CHANGED"):
            apply_import(db, actor, target, 1, reformatted, preview["source_file_sha256"])
        assert counts(db) == before
        apply_import(db, actor, target, 1, raw, preview["source_file_sha256"])
        saved = revision_bytes(db, actor, target)
        with pytest.raises(DraftScopeError, match="DRAFT_REVISION_CONFLICT"):
            apply_import(db, actor, target, 1, raw, preview["source_file_sha256"])
        assert revision_bytes(db, actor, target) == saved


def test_permission_owner_and_inactive_boundaries(case):
    with connected(case) as (db, actor, target, _origin, raw):
        digest = hashlib.sha256(raw).hexdigest()
        before = counts(db)
        for number, code in ((101, "DRAFT_NOT_FOUND"), (103, "DRAFT_PERMISSION_DENIED")):
            user = db.get(User, uid(number))
            with pytest.raises(DraftScopeError, match=code):
                preview_import(db, user, target, raw)
            with pytest.raises(DraftScopeError, match=code):
                apply_import(db, user, target, 1, raw, digest)
        assert counts(db) == before
        actor.is_active = False
        db.commit()
        with pytest.raises(DraftScopeError, match="DRAFT_PERMISSION_DENIED"):
            preview_import(db, actor, target, raw)
        admin = db.get(User, uid(102))
        assert preview_import(db, admin, target, raw)["expected_revision"] == 1
        result = apply_import(db, admin, target, 1, raw, digest)
        assert result["created_by"] == admin.id


@pytest.mark.parametrize(
    "mutate",
    [
        lambda e: e.update(revision=True),
        lambda e: e.update(revision=0),
        lambda e: e.update(revision="2"),
        lambda e: e.update(artifact_id="not-a-uuid"),
        lambda e: e.update(created_by={"id": uid(100)}),
        lambda e: e.update(created_at="2026-09-05"),
        lambda e: e.update(created_at="2026-09-05T12:00:00+10:00"),
        lambda e: e.update(parent_hash=None),
        lambda e: e.update(state="Approved"),
        lambda e: e.update(review_status="approved"),
        lambda e: e.update(provenance="verified"),
        lambda e: e.update(schema_version="CLASSIFIRE-DRAFT-SCOPE-v99"),
        lambda e: e.update(signature="foreign approval"),
        lambda e: e["content"]["services"][0].update(quantity="2.00"),
        lambda e: e["content"]["services"][0].update(opening_ids=[uid(999)]),
    ],
)
def test_source_claims_and_graph_are_validated_even_with_recomputed_checksum(case, mutate):
    with connected(case) as (db, actor, target, _origin, raw):
        before = counts(db)
        envelope = json.loads(raw)
        mutate(envelope)
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_INVALID"):
            preview_import(db, actor, target, reseal(envelope))
        assert counts(db) == before


@pytest.mark.parametrize(
    "bad",
    [b"\xff", b'{"a":1,"a":2}', b'{"a":NaN}', b"[1,2]", b"", b" " * (MAX_ARTIFACT_BYTES + 1)],
    ids=["invalid-utf8", "duplicate-keys", "nonfinite", "wrong-root", "empty", "oversized"],
)
def test_unsafe_or_oversized_artifact_bytes_fail_before_mutation(case, bad):
    with connected(case) as (db, actor, target, _origin, _raw):
        before = counts(db)
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_INVALID"):
            apply_import(db, actor, target, 1, bad, hashlib.sha256(bad).hexdigest())
        assert counts(db) == before


def test_untrusted_inherited_metadata_is_retained_but_bounded(case):
    with connected(case) as (db, actor, target, _origin, raw):
        result = apply_import(db, actor, target, 1, raw, hashlib.sha256(raw).hexdigest())
        inherited = copy.deepcopy(result)
        inherited["import_lineage"][0].update(created_by=uid(777), file_sha256="f" * 64)
        observed = reseal(inherited)
        output = apply_import(db, actor, target, 2, observed, hashlib.sha256(observed).hexdigest())
        assert output["import_lineage"][0]["created_by"] == uid(777)
        assert output["created_by"] == actor.id
        assert output["review_status"] == "unreviewed"
        inherited["import_lineage"] = [inherited["import_lineage"][0]] * MAX_IMPORT_LINEAGE
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_LINEAGE_LIMIT"):
            preview_import(db, actor, target, reseal(inherited))
        inherited["import_lineage"] = [dict(inherited["import_lineage"][0], approved=True)]
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_INVALID"):
            preview_import(db, actor, target, reseal(inherited))


def test_corrupted_target_blocks_preview_and_import_and_rollback_keeps_history(case):
    with connected(case) as (db, actor, target, _origin, raw):
        before = counts(db)
        apply_import(db, actor, target, 1, raw, hashlib.sha256(raw).hexdigest())
        db.rollback()
        assert counts(db) == before
        assert read_revision(db, actor, target)["revision"] == 1
        db.execute(
            text(
                "UPDATE draft_scope_revisions SET content_hash = :hash "
                "WHERE draft_scope_id = :target"
            ),
            {"hash": "0" * 64, "target": target},
        )
        db.commit()
        for call in (
            lambda: preview_import(db, actor, target, raw),
            lambda: apply_import(db, actor, target, 1, raw, hashlib.sha256(raw).hexdigest()),
        ):
            with pytest.raises(DraftScopeError, match="DRAFT_REVISION_INTEGRITY_FAILED"):
                call()


def test_source_checksum_detects_altered_content_without_resealing(case):
    with connected(case) as (db, actor, target, _origin, raw):
        altered = json.loads(raw)
        altered["content"]["assumptions"].append("Changed after export")
        before = counts(db)
        with pytest.raises(DraftScopeError, match="DRAFT_IMPORT_INVALID"):
            preview_import(db, actor, target, encoded(altered))
        assert counts(db) == before


def test_preview_does_not_flush_unrelated_pending_work(case):
    with connected(case) as (db, actor, target, _origin, raw):
        pending = User(
            email="pending@example.test",
            full_name="Unflushed unrelated work",
            password_hash="unused",  # noqa: S106 - synthetic non-authenticating fixture
            role="estimator",
            is_active=True,
        )  # noqa: S106
        db.add(pending)
        statements = []
        event.listen(
            db.connection(),
            "before_cursor_execute",
            lambda _c, _u, statement, _p, _x, _m: statements.append(statement),
        )
        preview_import(db, actor, target, raw)
        assert pending in db.new
        assert not any(
            sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) for sql in statements
        )
        db.rollback()
