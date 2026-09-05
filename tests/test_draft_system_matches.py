from __future__ import annotations

import copy
import hashlib
from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker
from test_draft_scope import sample_payload, uid
from test_technical_release_publication import _bound_variant

from classifire import physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    DraftScopeRevision,
    DraftSystemMatch,
    DraftSystemMatchRevision,
    Estimate,
    LibraryRelease,
    Opening,
    Service,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.physical_models import PhysicalModelLock
from classifire.services.draft_scope import (
    apply_import,
    create_draft_project,
    save_revision,
)
from classifire.services.draft_scope import (
    revision_bytes as scope_bytes,
)
from classifire.services.draft_system_match_contract import canonical, envelope_hash
from classifire.services.draft_system_matches import (
    DraftSystemMatchError,
    create_match,
    list_matches,
    list_technical_releases,
    match_staleness,
    read_match_revision,
    revision_bytes,
    save_review,
)
from classifire.services.release_scope import _manifest_hash
from classifire.services.technical import search_variants
from classifire.services.technical_release_publication import publish_governed_technical_release


@pytest.fixture
def case(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "matches.sqlite"))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    storage_root = (tmp_path / "storage").resolve()
    with factory() as db:
        for number, role in (
            (100, "estimator"),
            (101, "estimator"),
            (102, "administrator"),
            (103, "read_only"),
            (104, "project_manager"),
        ):
            db.add(
                User(
                    id=uid(number),
                    email=f"match-{number}@example.test",
                    full_name="Synthetic user",
                    password_hash="unused",  # noqa: S106 - non-authenticating fixture
                    role=role,
                    is_active=True,
                )
            )  # noqa: S106 - isolated non-authenticating fixture
        db.commit()
        actor = db.get(User, uid(100))
        draft = create_draft_project(db, actor, "SYNTHETIC-MATCH", "Synthetic candidate review")
        payload = sample_payload()
        payload["services"][0]["service_type"] = "pipe"
        payload["openings"][0]["substrate"] = "masonry"
        save_revision(db, actor, draft.id, 1, payload)
        variant, source_path = _bound_variant(db, storage_root)
        variant.substrate_type = "masonry"
        variant.minimum_service_size_mm = 10
        variant.maximum_service_size_mm = 90
        variant.hard_exclusions = "Synthetic limitation requires professional review"
        variant.source_json = {"secret_marker": "must-never-export-source-json"}
        release = publish_governed_technical_release(
            db,
            version="SYNTHETIC-1",
            notes="Fixture only",
            actor=db.get(User, uid(102)),
            storage_root=storage_root,
        )
        result = {
            "factory": factory,
            "draft_id": draft.id,
            "release_id": release.id,
            "variant_id": variant.id,
            "source_path": source_path,
            "storage_root": storage_root,
        }
        db.commit()
    yield result
    engine.dispose()


def create(db, case, **kwargs):
    return create_match(
        db,
        db.get(User, uid(100)),
        case["draft_id"],
        kwargs.get("scope_revision", 2),
        kwargs.get("release_id", case["release_id"]),
        kwargs.get("opening_id", uid(2)),
        kwargs.get("service_id", uid(5)),
        storage_root=case["storage_root"],
    )


def counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in (
            DraftSystemMatch,
            DraftSystemMatchRevision,
            AuditEvent,
            Estimate,
            Opening,
            Service,
            PhysicalModelLock,
            DraftScopeRevision,
        )
    }


def test_create_review_restart_exact_download_and_no_downstream_writes(case):
    with case["factory"]() as db:
        before = counts(db)
        match = create(db, case)
        actor = db.get(User, uid(100))
        original = read_match_revision(db, actor, case["draft_id"], match.id)
        assert original["coverage"] == "selected_target_only"
        assert original["retrieval"]["inputs"] == {
            "service_type": "pipe",
            "substrate": "masonry",
            "service_material": None,
            "orientation": None,
            "frl": None,
        }
        assert {"service_material", "service_size", "frl", "insulation"} <= set(
            original["retrieval"]["missing_criteria"]
        )
        candidate = original["candidates"][0]
        assert candidate["source"]["verification"] == "exact_bytes"
        assert candidate["fields"]["maximum_service_size_mm"] == "90.0000"
        assert candidate["comparisons"]["frl"] == "UNKNOWN"
        assert original["target"]["not_assessed_opening_ids"] == [uid(3), uid(4)]
        first = revision_bytes(db, actor, case["draft_id"], match.id)
        assert b"must-never-export-source-json" not in first
        assert str(case["source_path"]).encode() not in first
        changed = save_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            1,
            [
                {
                    "candidate_id": candidate["candidate_id"],
                    "decision": "keep",
                    "notes": "Inspect the retained source; not approval",
                }
            ],
        )
        assert changed["revision"] == 2 and changed["parent_hash"] == original["sha256"]
        assert (
            changed["candidates"] == original["candidates"]
            and changed["scope"] == original["scope"]
        )
        assert changed["review_status"] == "unreviewed"
        assert revision_bytes(db, actor, case["draft_id"], match.id, 1) == first
        assert (
            match_staleness(
                db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
            )
            == []
        )
        assert list_matches(db, actor, case["draft_id"])[0].id == match.id
        assert list_technical_releases(db, actor) == [
            {"id": case["release_id"], "version": "SYNTHETIC-1"}
        ]
        after = counts(db)
        for name in (
            "estimates",
            "openings",
            "services",
            "physical_model_locks",
            "draft_scope_revisions",
        ):
            assert before[name] == after[name]
        audit = db.scalar(
            select(AuditEvent).where(AuditEvent.action == "draft_system_match.review")
        )
        assert set(audit.new_value) == {"revision", "sha256", "scope_sha256", "release_sha256"}
        match_id = match.id
        latest_bytes = revision_bytes(db, actor, case["draft_id"], match.id)
        db.commit()
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        assert revision_bytes(db, actor, case["draft_id"], match_id, 1) == first
        assert revision_bytes(db, actor, case["draft_id"], match_id) == latest_bytes


def test_stale_review_and_export_survive_upstream_scope_library_and_source_changes(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        original = revision_bytes(db, actor, case["draft_id"], match.id)
        source = read_match_revision(db, actor, case["draft_id"], match.id)
        save_revision(db, actor, case["draft_id"], 2, {"assumptions": ["New current scope"]})
        db.get(LibraryRelease, case["release_id"]).status = "superseded"
        db.get(TechnicalVariant, case["variant_id"]).maximum_service_size_mm = 100
        db.commit()
        case["source_path"].write_bytes(b"altered")
        stale = match_staleness(
            db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
        )
        assert {
            "SCOPE_CHANGED",
            "RELEASE_NO_LONGER_ACTIVE",
            "CANDIDATE_CHANGED",
            "SOURCE_BYTES_UNAVAILABLE_OR_CHANGED",
        } <= set(stale)
        assert revision_bytes(db, actor, case["draft_id"], match.id) == original
        reviewed = save_review(
            db,
            actor,
            case["draft_id"],
            match.id,
            1,
            [
                {
                    "candidate_id": case["variant_id"],
                    "decision": "reject",
                    "notes": "This history is stale",
                }
            ],
        )
        assert reviewed["scope"] == source["scope"]
        assert revision_bytes(db, actor, case["draft_id"], match.id, 1) == original


@pytest.mark.parametrize(
    "opening_id,service_id", [(None, None), (uid(4), uid(5)), (uid(99), None), (None, uid(99))]
)
def test_invalid_targets_never_create_records(case, opening_id, service_id):
    with case["factory"]() as db:
        before = counts(db)
        with pytest.raises(DraftSystemMatchError, match="MATCH_TARGET_INVALID"):
            create(db, case, opening_id=opening_id, service_id=service_id)
        assert counts(db) == before


def test_whole_opening_blank_and_service_only_targets_remain_explicit(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        whole = read_match_revision(
            db, actor, case["draft_id"], create(db, case, service_id=None).id
        )
        assert whole["target"]["service_ids"] == [uid(5), uid(6)]
        assert whole["retrieval"]["inputs"]["service_type"] is None
        blank = read_match_revision(
            db, actor, case["draft_id"], create(db, case, opening_id=uid(4), service_id=None).id
        )
        assert blank["target"]["blank_opening"] is True and blank["target"]["service_ids"] == []
        service = read_match_revision(
            db, actor, case["draft_id"], create(db, case, opening_id=None).id
        )
        assert service["target"]["opening_ids"] == [uid(2), uid(3)]
        assert service["retrieval"]["inputs"]["substrate"] is None
        assert "selected_opening" in service["retrieval"]["missing_criteria"]


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "duplicate",
        "wrong_type",
        "future_release",
        "record_version",
        "source_hash",
        "retired_variant",
        "expired_document",
        "dirty_source",
        "missing_bytes",
    ],
)
def test_invalid_current_dependencies_refuse_creation_atomically(case, change):
    with case["factory"]() as db:
        release = db.get(LibraryRelease, case["release_id"])
        variant = db.get(TechnicalVariant, case["variant_id"])
        document = db.get(TechnicalDocument, variant.technical_document_id)
        stored = db.get(StoredFile, document.stored_file_id)
        if change == "hash":
            release.release_hash = "0" * 64
        elif change == "duplicate":
            manifest = copy.deepcopy(release.source_manifest)
            manifest["records"].append(copy.deepcopy(manifest["records"][0]))
            manifest["record_count"] = 2
            release.source_manifest = manifest
            release.release_hash = _manifest_hash(manifest)
        elif change == "wrong_type":
            release.library_type = "pricing"
        elif change == "future_release":
            release.effective_date = date.today() + timedelta(days=1)
        elif change == "record_version":
            variant.record_version += 1
        elif change == "source_hash":
            stored.sha256 = "0" * 64
        elif change == "retired_variant":
            variant.status = "retired"
        elif change == "expired_document":
            document.expiry_date = date.today() - timedelta(days=1)
        elif change == "dirty_source":
            stored.malware_scan_status = "infected"
        elif change == "missing_bytes":
            case["source_path"].unlink()
        db.commit()
        before = counts(db)
        with pytest.raises(DraftSystemMatchError):
            create(db, case)
        assert counts(db) == before


def test_legacy_source_less_release_remains_explicitly_unresolved(case):
    with case["factory"]() as db:
        variant = db.get(TechnicalVariant, case["variant_id"])
        variant.technical_document_id = None
        variant.source_hash = None
        release = db.get(LibraryRelease, case["release_id"])
        release.source_manifest = {"records": [{"id": variant.id}]}
        release.release_hash = _manifest_hash(release.source_manifest)
        db.commit()
        envelope = read_match_revision(
            db, db.get(User, uid(100)), case["draft_id"], create(db, case).id
        )
        candidate = envelope["candidates"][0]
        assert candidate["source"]["state"] == "manifest_unbound"
        assert candidate["source"]["binding"]["state"] == "legacy_unbound"
        assert candidate["source"]["variant_source_hash"] is None
        assert candidate["source"]["verification"] == "unresolved"
        assert candidate["source"]["verified_at"] is None
        assert "source_binding_unresolved" in candidate["blockers"]
        assert candidate["source"]["state"] != "bound"


def test_permissions_recheck_actor_and_require_technical_read(case):
    with case["factory"]() as db:
        match = create(db, case)
        db.commit()
        for number in (101, 104):
            with pytest.raises(DraftSystemMatchError):
                read_match_revision(db, db.get(User, uid(number)), case["draft_id"], match.id)
        admin = db.get(User, uid(102))
        assert read_match_revision(db, admin, case["draft_id"], match.id)["artifact_id"] == match.id
        owner = db.get(User, uid(100))
        owner.role = "read_only"
        db.commit()
        assert read_match_revision(db, owner, case["draft_id"], match.id)["artifact_id"] == match.id
        with pytest.raises(DraftSystemMatchError):
            save_review(db, owner, case["draft_id"], match.id, 1, [])
        owner.is_active = False
        db.commit()
        with pytest.raises(DraftSystemMatchError):
            revision_bytes(db, owner, case["draft_id"], match.id)
        with pytest.raises(DraftSystemMatchError):
            read_match_revision(db, object(), case["draft_id"], match.id)


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "foreign", "approval", "long_note", "extra"]
)
def test_review_decisions_are_bounded_exact_and_never_approval(case, kind):
    with case["factory"]() as db:
        match = create(db, case)
        decision = {"candidate_id": case["variant_id"], "decision": "keep", "notes": ""}
        decisions = [decision]
        if kind == "missing":
            decisions = []
        elif kind == "duplicate":
            decisions.append(copy.deepcopy(decision))
        elif kind == "foreign":
            decision["candidate_id"] = uid(99)
        elif kind == "approval":
            decision["decision"] = "Applicable"
        elif kind == "long_note":
            decision["notes"] = "x" * 4001
        elif kind == "extra":
            decision["approval"] = True
        before = counts(db)
        with pytest.raises(DraftSystemMatchError, match="MATCH_DECISIONS_INVALID"):
            save_review(db, db.get(User, uid(100)), case["draft_id"], match.id, 1, decisions)
        assert counts(db) == before


def test_stale_saves_and_caller_rollback_do_not_leave_partial_revisions(case):
    with case["factory"]() as db:
        before = counts(db)
        create(db, case)
        db.rollback()
        assert counts(db) == before
        match = create(db, case)
        db.commit()
        actor = db.get(User, uid(100))
        decisions = [{"candidate_id": case["variant_id"], "decision": "keep", "notes": "First"}]
        save_review(db, actor, case["draft_id"], match.id, 1, decisions)
        db.commit()
        before = counts(db)
        with pytest.raises(DraftSystemMatchError, match="MATCH_REVISION_CONFLICT"):
            save_review(db, actor, case["draft_id"], match.id, 1, decisions)
        assert counts(db) == before
        save_review(db, actor, case["draft_id"], match.id, 2, decisions)
        db.rollback()
        assert counts(db) == before


@pytest.mark.parametrize(
    "column,value",
    [
        ("envelope_json", "{}"),
        ("content_hash", "0" * 64),
        ("created_by_id", uid(101)),
        ("parent_hash", "0" * 64),
    ],
)
def test_tampered_retained_revision_fails_closed(case, column, value):
    with case["factory"]() as db:
        match = create(db, case)
        db.execute(
            update(DraftSystemMatchRevision)
            .where(DraftSystemMatchRevision.match_id == match.id)
            .values({column: value})
        )
        db.commit()
        with pytest.raises(DraftSystemMatchError, match="MATCH_REVISION_INTEGRITY_FAILED"):
            revision_bytes(db, db.get(User, uid(100)), case["draft_id"], match.id)


def test_resealed_changed_basis_is_rejected_and_v2_scope_is_preserved(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        raw = scope_bytes(db, actor, case["draft_id"])
        imported = apply_import(
            db, actor, case["draft_id"], 2, raw, hashlib.sha256(raw).hexdigest()
        )
        match = create(db, case, scope_revision=3)
        envelope = read_match_revision(db, actor, case["draft_id"], match.id)
        assert envelope["scope"] == imported and envelope["scope"]["import_lineage"]
        envelope["candidates"][0]["score"] = "999"
        envelope["sha256"] = envelope_hash(envelope)
        db.execute(
            update(DraftSystemMatchRevision)
            .where(DraftSystemMatchRevision.match_id == match.id)
            .values(content_hash=envelope["sha256"], envelope_json=canonical(envelope).decode())
        )
        db.commit()
        with pytest.raises(DraftSystemMatchError, match="MATCH_REVISION_INTEGRITY_FAILED"):
            read_match_revision(db, actor, case["draft_id"], match.id)


def test_retrieval_has_stable_ties_and_explicit_result_truncation(case):
    with case["factory"]() as db:
        initial = db.get(TechnicalVariant, case["variant_id"])
        for number in range(21):
            db.add(
                TechnicalVariant(
                    id=uid(500 + number),
                    variant_id=f"VAR-{number}",
                    system_id=f"SYSTEM-{number}",
                    technical_document_id=initial.technical_document_id,
                    source_document_reference=initial.source_document_reference,
                    source_page=initial.source_page,
                    source_hash=initial.source_hash,
                    source_json={},
                    service_type="pipe",
                    status="active",
                    expert_review_required=False,
                )
            )
        db.flush()
        release = publish_governed_technical_release(
            db,
            version="SYNTHETIC-2",
            notes="Fixture only",
            actor=db.get(User, uid(102)),
            storage_root=case["storage_root"],
        )
        db.commit()
        ids = {item.id for item in db.scalars(select(TechnicalVariant))}
        results = search_variants(db, service_type="pipe", release_record_ids=ids, limit=21)
        assert [item.variant.id for item in results] == sorted(item.variant.id for item in results)
        envelope = read_match_revision(
            db, db.get(User, uid(100)), case["draft_id"], create(db, case, release_id=release.id).id
        )
        assert len(envelope["candidates"]) == 20 and envelope["retrieval"]["truncated"] is True


def test_new_release_identity_and_captured_release_metadata_changes_are_stale(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        match = create(db, case)
        original = revision_bytes(db, actor, case["draft_id"], match.id)
        previous = db.get(LibraryRelease, case["release_id"])
        previous.version = "Changed current label"
        previous.effective_date = date.today() + timedelta(days=1)
        previous.library_type = "pricing"
        db.add(
            LibraryRelease(
                library_type="technical",
                version="New active release",
                status="active",
                release_hash="f" * 64,
                source_manifest={"records": []},
            )
        )
        db.commit()
        stale = match_staleness(
            db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
        )
        assert {
            "NEW_TECHNICAL_RELEASE_AVAILABLE",
            "RELEASE_CHANGED",
            "RELEASE_NO_LONGER_ELIGIBLE",
        } <= set(stale)
        assert revision_bytes(db, actor, case["draft_id"], match.id) == original


def test_unicode_manifest_uses_existing_publication_hash_convention(case):
    with case["factory"]() as db:
        release = db.get(LibraryRelease, case["release_id"])
        manifest = copy.deepcopy(release.source_manifest)
        manifest["notes"] = "Synthetic unicode: café"
        release.source_manifest = manifest
        release.release_hash = _manifest_hash(manifest)
        db.commit()
        match = create(db, case)
        assert (
            match_staleness(
                db,
                db.get(User, uid(100)),
                case["draft_id"],
                match.id,
                storage_root=case["storage_root"],
            )
            == []
        )


def test_legacy_source_claim_changes_are_stale_without_rewriting_saved_history(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        variant = db.get(TechnicalVariant, case["variant_id"])
        variant.technical_document_id = None
        variant.source_hash = None
        release = db.get(LibraryRelease, case["release_id"])
        release.source_manifest = {"records": [{"id": variant.id}]}
        release.release_hash = _manifest_hash(release.source_manifest)
        db.commit()
        match = create(db, case)
        original = revision_bytes(db, actor, case["draft_id"], match.id)
        assert (
            match_staleness(
                db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
            )
            == []
        )
        variant.source_document_reference = "Changed legacy reference"
        variant.source_page = "99"
        variant.source_hash = "f" * 64
        db.commit()
        assert "SOURCE_BINDING_CHANGED" in match_staleness(
            db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
        )
        assert revision_bytes(db, actor, case["draft_id"], match.id) == original


def test_manifest_without_binding_captures_current_unverified_source_metadata(case):
    with case["factory"]() as db:
        actor = db.get(User, uid(100))
        release = db.get(LibraryRelease, case["release_id"])
        release.source_manifest = {"records": [{"id": case["variant_id"]}]}
        release.release_hash = _manifest_hash(release.source_manifest)
        db.commit()
        match = create(db, case)
        artifact = read_match_revision(db, actor, case["draft_id"], match.id)
        assert artifact["candidates"][0]["source"]["state"] == "manifest_unbound"
        assert artifact["candidates"][0]["source"]["verification"] == "unresolved"
        assert (
            match_staleness(
                db, actor, case["draft_id"], match.id, storage_root=case["storage_root"]
            )
            == []
        )


@pytest.mark.parametrize(
    "changed", ["write_permission", "technical_permission", "candidate_fields"]
)
def test_creation_rechecks_authority_and_candidate_identity_after_source_verification(
    case, monkeypatch, changed
):
    from classifire.services import draft_system_matches as service

    verify = service._verify_files

    def change_after_verification(db, files, storage_root):
        verify(db, files, storage_root)
        if changed == "candidate_fields":
            db.get(TechnicalVariant, case["variant_id"]).maximum_service_size_mm = 999
        else:
            db.get(User, uid(100)).role = (
                "read_only" if changed == "write_permission" else "project_manager"
            )
        db.flush()

    monkeypatch.setattr(service, "_verify_files", change_after_verification)
    with case["factory"]() as db:
        before = counts(db)
        with pytest.raises(DraftSystemMatchError):
            create(db, case)
        assert counts(db) == before
