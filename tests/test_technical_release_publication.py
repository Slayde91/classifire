from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import Request

from classifire import physical_models, release_admin  # noqa: F401
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalVariant,
    User,
)
from classifire.services.release_scope import active_technical_release_ids
from classifire.services.technical_release_publication import (
    TECHNICAL_RELEASE_MANIFEST_SCHEMA,
    TechnicalReleasePublicationError,
    publish_governed_technical_release,
)

NOW = datetime(2026, 9, 5, 1, 2, 3, tzinfo=UTC)


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _actor(db: Session, *, role: str = "technical_reviewer", active: bool = True) -> User:
    actor = User(
        email=f"{role}-{active}@example.test",
        full_name="Synthetic technical release reviewer",
        password_hash="not-used",  # noqa: S106 - non-authenticating fixture
        role=role,
        is_active=active,
    )
    db.add(actor)
    db.flush()
    return actor


def _bound_variant(
    db: Session,
    storage_root: Path,
    *,
    suffix: str = "001",
    document_status: str = "approved",
    document_expiry: date | None = None,
    variant_expiry: date | None = None,
    original_variant_id: str | None = None,
) -> tuple[TechnicalVariant, Path]:
    storage_root.mkdir(parents=True, exist_ok=True)
    payload = f"synthetic technical evidence {suffix}".encode()
    source_path = (storage_root / f"source-{suffix}.pdf").resolve()
    source_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    stored = StoredFile(
        original_filename=source_path.name,
        media_type="application/pdf",
        storage_path=str(source_path),
        sha256=digest,
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=f"TECH-DOC-{suffix}",
        stored_file_id=stored.id,
        document_type="assessment",
        title=f"Synthetic technical assessment {suffix}",
        reference=f"ASSESSMENT-{suffix}",
        revision="1",
        status=document_status,
        expiry_date=document_expiry,
    )
    db.add(document)
    db.flush()
    source_json = {"fixture": "governed-technical-release"}
    if original_variant_id:
        source_json["original_variant_id"] = original_variant_id
    variant = TechnicalVariant(
        variant_id=f"VAR-{suffix}",
        system_id=f"SYSTEM-{suffix}",
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page="4",
        source_table="Table 2",
        source_figure="Figure 1",
        manufacturer="Synthetic Manufacturer",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        status="active",
        effective_date=None,
        expiry_date=variant_expiry,
        expert_review_required=False,
        source_hash=digest,
        source_json=source_json,
        component_requirements={"sealant": {"unit": "cartridge"}},
        labour_requirements=["Install sealant"],
    )
    db.add(variant)
    db.flush()
    return variant, source_path


def _publish(
    db: Session,
    *,
    actor: User,
    storage_root: Path,
    version: str = "TECH-2026.09",
) -> LibraryRelease:
    return publish_governed_technical_release(
        db,
        version=version,
        notes="Synthetic governed technical publication",
        actor=actor,
        storage_root=storage_root.resolve(),
        now=NOW,
        source_ip="127.0.0.1",
    )


def test_publication_snapshots_every_active_variant_and_supersedes_atomically(
    db: Session, tmp_path: Path
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    previous = LibraryRelease(
        library_type="technical",
        version="TECH-2026.08",
        status="active",
        release_hash="a" * 64,
        source_manifest={"legacy": True},
    )
    db.add(previous)
    db.flush()
    variant, _path = _bound_variant(db, storage_root)
    variant.release_id = previous.id
    draft = TechnicalVariant(
        variant_id="DRAFT-001",
        system_id="DRAFT-SYSTEM-001",
        status="draft",
        expert_review_required=True,
        source_json={"fixture": "must-not-activate"},
    )
    db.add(draft)
    db.flush()

    release = _publish(db, actor=actor, storage_root=storage_root)

    assert previous.status == "superseded"
    assert release.status == "active"
    assert release.supersedes_release_id == previous.id
    assert release.approved_by_id == actor.id
    assert release.source_manifest is not None
    assert release.source_manifest["schema"] == TECHNICAL_RELEASE_MANIFEST_SCHEMA
    assert release.source_manifest["activated_draft_ids"] == []
    assert release.source_manifest["record_count"] == 1
    assert [record["id"] for record in release.source_manifest["records"]] == [variant.id]
    binding = release.source_manifest["records"][0]["source_binding"]
    recipe = release.source_manifest["records"][0]["recipe_snapshot"]
    assert recipe["availability"] == "available"
    assert [item["kind"] for item in recipe["requirements"]] == ["component", "activity"]
    assert binding["state"] == "bound"
    assert binding["technical_document"]["stored_file"]["sha256"] == variant.source_hash
    assert draft.status == "draft"
    assert active_technical_release_ids(db, release) == {variant.id}
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.action == "publish_governed_technical_release"
        )
    )
    assert audit is not None
    assert audit.entity_id == release.id
    assert audit.new_value is not None
    assert audit.new_value["technical_selection_authority_granted"] is False
    assert audit.new_value["human_release_authority_granted"] is False


def test_publication_rejects_changed_retained_source_bytes_without_writing(
    db: Session, tmp_path: Path
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    _variant, source_path = _bound_variant(db, storage_root)
    source_path.write_bytes(b"x" * source_path.stat().st_size)

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_SOURCE_BYTES_INVALID"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_publication_rejects_invalid_recipe_without_writing(db: Session, tmp_path: Path) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    variant, _ = _bound_variant(db, storage_root)
    variant.component_requirements = {"oversized": "x" * 17000}
    db.flush()

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_RECIPE_INVALID"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize(
    "document_status,document_expiry,variant_expiry",
    [
        ("draft", None, None),
        ("approved", NOW.date() - timedelta(days=1), None),
        ("approved", None, NOW.date() - timedelta(days=1)),
    ],
)
def test_publication_rejects_any_ineligible_active_variant_instead_of_omitting_it(
    db: Session,
    tmp_path: Path,
    document_status: str,
    document_expiry: date | None,
    variant_expiry: date | None,
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    _bound_variant(db, storage_root, suffix="eligible")
    _bound_variant(
        db,
        storage_root,
        suffix="blocked",
        document_status=document_status,
        document_expiry=document_expiry,
        variant_expiry=variant_expiry,
    )

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_ACTIVE_VARIANT_INELIGIBLE"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_publication_rejects_two_active_revisions_for_one_logical_variant(
    db: Session, tmp_path: Path
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    _bound_variant(db, storage_root, suffix="001", original_variant_id="LOGICAL-001")
    _bound_variant(db, storage_root, suffix="002", original_variant_id="LOGICAL-001")

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_ACTIVE_VARIANT_AMBIGUOUS"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


@pytest.mark.parametrize("role,active", [("estimator", True), ("technical_reviewer", False)])
def test_publication_requires_an_active_technical_approver(
    db: Session, tmp_path: Path, role: str, active: bool
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db, role=role, active=active)
    _bound_variant(db, storage_root)

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_PUBLICATION_PERMISSION_DENIED"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 0


def test_publication_rolls_back_supersession_release_and_audit_together(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    previous = LibraryRelease(
        library_type="technical",
        version="TECH-2026.08",
        status="active",
        release_hash="a" * 64,
        source_manifest={"legacy": True},
    )
    db.add(previous)
    db.flush()
    _bound_variant(db, storage_root)

    def fail_audit(*_args: object, **_kwargs: object) -> None:
        raise SQLAlchemyError("synthetic audit failure")

    monkeypatch.setattr(
        "classifire.services.technical_release_publication.record_audit",
        fail_audit,
    )

    with pytest.raises(TechnicalReleasePublicationError) as rejected:
        _publish(db, actor=actor, storage_root=storage_root)

    assert rejected.value.code == "TECHNICAL_RELEASE_PUBLICATION_WRITE_FAILED"
    db.refresh(previous)
    assert previous.status == "active"
    assert db.scalar(select(func.count()).select_from(LibraryRelease)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


def test_publication_manifest_hash_is_exact_and_stable(
    db: Session, tmp_path: Path
) -> None:
    storage_root = tmp_path / "storage"
    actor = _actor(db)
    _bound_variant(db, storage_root)

    release = _publish(db, actor=actor, storage_root=storage_root)

    assert release.source_manifest is not None
    expected = hashlib.sha256(
        json.dumps(
            release.source_manifest,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()
    assert release.release_hash == expected


def test_technical_publish_route_uses_governed_transaction(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage_root = (tmp_path / "storage").resolve()
    actor = _actor(db)
    _bound_variant(db, storage_root)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/releases/publish",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 50000),
        }
    )
    monkeypatch.setattr(release_admin, "verify_csrf", lambda *_args: None)
    monkeypatch.setattr(release_admin, "_require", lambda *_args: actor)
    settings = type("SyntheticSettings", (), {"storage_root": storage_root})()
    monkeypatch.setattr(release_admin, "get_settings", lambda: settings)

    response = release_admin.publish_release(
        request,
        db,
        csrf_token="synthetic-csrf",  # noqa: S106 - non-authenticating fixture
        release_type="technical",
        version="TECH-ROUTE-001",
        notes="Synthetic route publication",
        activate_drafts=None,
    )

    assert response.status_code == 303
    release = db.scalar(
        select(LibraryRelease).where(LibraryRelease.version == "TECH-ROUTE-001")
    )
    assert release is not None
    assert response.headers["location"] == (
        f"/releases/{release.id}?success=Release+published"
    )
    assert release.source_manifest is not None
    assert release.source_manifest["schema"] == TECHNICAL_RELEASE_MANIFEST_SCHEMA
