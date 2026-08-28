from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from classifire import models, physical_models  # noqa: F401
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    LibraryRelease,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
    User,
)
from classifire.services.technical_document_lineage import (
    TECHNICAL_DOCUMENT_RELATIONSHIP_REASON_MAX_LENGTH,
    TECHNICAL_DOCUMENT_RELATIONSHIP_SCOPE_MAX_LENGTH,
    TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES,
    TechnicalDocumentLineageError,
    create_technical_document_relationship,
)
from classifire.services.technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, email: str = "lineage.author@example.test") -> User:
    user = User(
        email=email,
        full_name="Lineage Author",
        password_hash="not-used-in-service-tests",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _document(
    db: Session,
    document_id: str,
    *,
    status: str = "draft",
) -> TechnicalDocument:
    payload = f"retained source bytes for {document_id}".encode()
    digest = hashlib.sha256(payload).hexdigest()
    stored = StoredFile(
        original_filename=f"{document_id}.pdf",
        media_type="application/pdf",
        storage_path=f"C:/governed-test-storage/{digest}.pdf",
        sha256=digest,
        size_bytes=len(payload),
        purpose="technical_evidence",
        malware_scan_status="clean",
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="fire_test_report",
        declared_source_role="primary_test",
        artifact_provenance_status="unknown",
        evidence_scope="full_source",
        title=f"Source {document_id}",
        status=status,
        extraction_status="not_started",
        metadata_json={
            "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY_V2,
        },
    )
    db.add(document)
    db.flush()
    return document


def _create(
    db: Session,
    actor: User,
    document: TechnicalDocument,
    related: TechnicalDocument,
    *,
    relationship_type: str = "revision_of",
    reason: str = "A later retained issue explicitly revises this source.",
    scope: str | None = "Whole document",
    effective_date: date | None = date(2026, 8, 27),
) -> TechnicalDocumentRelationship:
    return create_technical_document_relationship(
        db,
        actor=actor,
        document=document,
        related_document_id=related.document_id,
        relationship_type=relationship_type,
        reason=reason,
        scope=scope,
        effective_date=effective_date,
        source_ip="192.0.2.10",
        correlation_id="lineage-test-correlation",
    )


@pytest.mark.parametrize("relationship_type", sorted(TECHNICAL_DOCUMENT_RELATIONSHIP_TYPES))
def test_each_governed_relationship_type_resolves_public_id_and_records_audit(
    db: Session,
    relationship_type: str,
) -> None:
    actor = _user(db, f"{relationship_type}@example.test")
    related = _document(db, f"RELATED-{relationship_type}", status="approved")
    document = _document(db, f"NEW-{relationship_type}")
    db.commit()

    relationship = _create(
        db,
        actor,
        document,
        related,
        relationship_type=relationship_type,
    )
    db.flush()

    assert relationship.document_id == document.id
    assert relationship.related_document_id == related.id
    assert relationship.relationship_type == relationship_type
    assert relationship.created_by_id == actor.id
    assert relationship.scope == "Whole document"
    assert relationship.effective_date == date(2026, 8, 27)
    audit = db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "technical_document_relationship",
            AuditEvent.entity_id == relationship.id,
        )
    )
    assert audit is not None
    assert audit.action == "create_lineage_relationship"
    assert audit.new_value == {
        "document_id": document.document_id,
        "related_document_id": related.document_id,
        "relationship_type": relationship_type,
        "scope": "Whole document",
        "effective_date": "2026-08-27",
        "runtime_eligible": False,
    }
    assert audit.reason == relationship.reason
    assert audit.source_ip == "192.0.2.10"
    assert audit.correlation_id == "lineage-test-correlation"


def test_service_does_not_commit_or_mutate_sources_or_runtime_state(db: Session) -> None:
    actor = _user(db)
    related = _document(db, "BASE-IMMUTABLE", status="approved")
    document = _document(db, "REVISION-DRAFT")
    release = LibraryRelease(
        library_type="technical",
        version="existing-runtime-release",
        status="active",
        release_hash="a" * 64,
        source_manifest={"existing": True},
        active_publication_slot="technical",
    )
    variant = TechnicalVariant(
        variant_id="EXISTING-RUNTIME-VARIANT",
        system_id="EXISTING-RUNTIME-SYSTEM",
        technical_document_id=related.id,
        source_document_reference=related.document_id,
        source_page="1",
        expert_review_required=True,
        search_eligibility="INCLUDE_APPROVED_RELEASE_CANDIDATE",
        status="active",
        source_json={"existing": True},
    )
    db.add_all([release, variant])
    db.commit()
    document_state = {
        column.name: getattr(document, column.name)
        for column in TechnicalDocument.__table__.columns
    }
    related_state = {
        column.name: getattr(related, column.name)
        for column in TechnicalDocument.__table__.columns
    }
    release_state = (release.status, release.release_hash, release.active_publication_slot)
    variant_state = (variant.status, variant.search_eligibility, variant.technical_document_id)

    _create(db, actor, document, related, relationship_type="replaces")

    assert {
        column.name: getattr(document, column.name)
        for column in TechnicalDocument.__table__.columns
    } == document_state
    assert {
        column.name: getattr(related, column.name)
        for column in TechnicalDocument.__table__.columns
    } == related_state
    assert (release.status, release.release_hash, release.active_publication_slot) == release_state
    assert (
        variant.status,
        variant.search_eligibility,
        variant.technical_document_id,
    ) == variant_state

    db.rollback()
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 0
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "create_lineage_relationship")
        )
        == 0
    )
    assert db.get(TechnicalDocument, document.id) is not None
    assert db.get(TechnicalDocument, related.id) is not None
    assert db.get(LibraryRelease, release.id).status == "active"
    assert db.get(TechnicalVariant, variant.id).status == "active"


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"related_document_id": ""}, "RELATED_DOCUMENT_ID_INVALID"),
        ({"relationship_type": "supersedes"}, "RELATIONSHIP_TYPE_INVALID"),
        ({"reason": "  "}, "RELATIONSHIP_REASON_INVALID"),
        (
            {"reason": "x" * (TECHNICAL_DOCUMENT_RELATIONSHIP_REASON_MAX_LENGTH + 1)},
            "RELATIONSHIP_REASON_INVALID",
        ),
        (
            {"scope": "x" * (TECHNICAL_DOCUMENT_RELATIONSHIP_SCOPE_MAX_LENGTH + 1)},
            "RELATIONSHIP_SCOPE_INVALID",
        ),
        ({"reason": "unsafe\x00text"}, "RELATIONSHIP_REASON_INVALID"),
        (
            {"effective_date": datetime(2026, 8, 27, tzinfo=UTC)},
            "RELATIONSHIP_EFFECTIVE_DATE_INVALID",
        ),
    ],
)
def test_invalid_relationship_input_is_rejected_without_writes(
    db: Session,
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    actor = _user(db)
    related = _document(db, "INPUT-BASE", status="approved")
    document = _document(db, "INPUT-NEW")
    db.commit()
    values: dict[str, object] = {
        "actor": actor,
        "document": document,
        "related_document_id": related.document_id,
        "relationship_type": "revision_of",
        "reason": "Valid reason",
        "scope": None,
        "effective_date": None,
    }
    values.update(overrides)

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        create_technical_document_relationship(db, **values)  # type: ignore[arg-type]

    assert caught.value.code == expected_code
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 0
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 0


@pytest.mark.parametrize("evidence_scope", ["summary_only", "bibliographic_only"])
def test_summary_relationship_requires_a_v2_full_source_target(
    db: Session,
    evidence_scope: str,
) -> None:
    actor = _user(db)
    related = _document(db, "SUMMARY-TARGET", status="approved")
    related.evidence_scope = evidence_scope
    document = _document(db, "SUMMARY-SOURCE")
    document.document_type = "regulatory_information_report"
    document.declared_source_role = "regulatory_summary"
    document.evidence_scope = "summary_only"
    db.commit()

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(
            db,
            actor,
            document,
            related,
            relationship_type="summary_of",
        )

    assert caught.value.code == "SUMMARY_SOURCE_TARGET_INVALID"
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 0


def test_relationship_requires_persisted_actor_and_draft_source(db: Session) -> None:
    actor = _user(db)
    related = _document(db, "AUTHORITY-BASE", status="approved")
    approved_source = _document(db, "AUTHORITY-NEW", status="approved")
    db.commit()

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(db, actor, approved_source, related)
    assert caught.value.code == "SOURCE_DOCUMENT_NOT_DRAFT"

    transient_actor = User(
        email="transient@example.test",
        full_name="Transient",
        password_hash="unused",  # noqa: S106
        role="technical_reviewer",
        is_active=True,
    )
    approved_source.status = "draft"
    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(db, transient_actor, approved_source, related)
    assert caught.value.code == "RELATIONSHIP_FIELDS_INCOMPLETE"

    transient_document = TechnicalDocument(
        document_id="TRANSIENT-DOCUMENT",
        stored_file_id=related.stored_file_id,
        document_type="fire_test_report",
        title="Transient",
        status="draft",
        extraction_status="not_started",
    )
    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(db, actor, transient_document, related)
    assert caught.value.code == "RELATIONSHIP_FIELDS_INCOMPLETE"
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 0


def test_missing_and_self_related_sources_are_rejected(db: Session) -> None:
    actor = _user(db)
    document = _document(db, "SELF-DOCUMENT")
    db.commit()

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        create_technical_document_relationship(
            db,
            actor=actor,
            document=document,
            related_document_id="MISSING-DOCUMENT",
            relationship_type="revision_of",
            reason="Target should exist",
        )
    assert caught.value.code == "RELATED_DOCUMENT_NOT_FOUND"

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        create_technical_document_relationship(
            db,
            actor=actor,
            document=document,
            related_document_id=document.document_id,
            relationship_type="revision_of",
            reason="Self links are invalid",
        )
    assert caught.value.code == "RELATIONSHIP_SELF_REFERENCE"
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 0


def test_duplicate_edge_is_rejected_without_duplicate_audit(db: Session) -> None:
    actor = _user(db)
    related = _document(db, "DUPLICATE-BASE", status="approved")
    document = _document(db, "DUPLICATE-NEW")
    db.commit()
    first = _create(db, actor, document, related, relationship_type="amendment_to")
    db.flush()

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(db, actor, document, related, relationship_type="amendment_to")

    assert caught.value.code == "RELATIONSHIP_ALREADY_EXISTS"
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 1
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 1
    assert db.get(TechnicalDocumentRelationship, first.id) is first


def test_transitive_cycle_is_rejected_across_relationship_types(db: Session) -> None:
    actor = _user(db)
    first = _document(db, "CYCLE-A")
    second = _document(db, "CYCLE-B")
    third = _document(db, "CYCLE-C")
    db.commit()
    _create(db, actor, first, second, relationship_type="assessment_of")
    _create(db, actor, second, third, relationship_type="amendment_to")
    db.flush()

    with pytest.raises(TechnicalDocumentLineageError) as caught:
        _create(db, actor, third, first, relationship_type="revision_of")

    assert caught.value.code == "RELATIONSHIP_CYCLE"
    assert db.scalar(select(func.count()).select_from(TechnicalDocumentRelationship)) == 2
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == 2
