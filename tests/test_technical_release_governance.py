# ruff: noqa: S106
from __future__ import annotations

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from classifire import (  # noqa: F401
    models,
    physical_models,
    release_admin,
    technical_admin,
    technical_retirement_admin,
)
from classifire.config import get_settings
from classifire.db import Base
from classifire.importers.technical import import_technical_variants
from classifire.models import (
    Approval,
    AuditEvent,
    Estimate,
    LibraryRelease,
    Opening,
    Project,
    StoredFile,
    TechnicalDocument,
    TechnicalDocumentRelationship,
    TechnicalVariant,
    User,
)
from classifire.release_admin import publish_release
from classifire.services import release_scope
from classifire.services.release_pinning import active_release
from classifire.services.release_scope import (
    ReleaseScopeError,
    active_release_record_ids,
    manifest_hash,
    release_record_ids,
)
from classifire.services.snapshot import lock_snapshot
from classifire.services.technical import search_variants
from classifire.services.technical_document_metadata import (
    TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
)
from classifire.services.technical_document_review import (
    TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
    TECHNICAL_DOCUMENT_REVIEW_POLICY,
    TechnicalDocumentReviewError,
    technical_document_review_reasons,
    technical_document_review_snapshot,
    technical_document_review_snapshot_hash,
)
from classifire.services.technical_governance import (
    APPROVED_RELEASE_CANDIDATE,
    GOVERNED_TECHNICAL_RELEASE_POLICY,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
    GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    PENDING_TECHNICAL_REVIEW,
    TECHNICAL_REVIEW_APPROVAL_TYPE,
    TECHNICAL_REVIEW_POLICY_V2,
    TechnicalGovernanceError,
    release_candidate_blockers,
    require_technical_source_binding,
    technical_approval_binding,
    technical_review_snapshot_hash,
    technical_variant_snapshot_hash,
)
from classifire.services.technical_retirement import (
    TECHNICAL_RETIREMENT_APPROVAL_TYPE,
    latest_technical_retirement,
    technical_retirement_decision,
)
from classifire.technical_admin import (
    technical_document_approve,
    technical_document_detail,
    technical_document_metadata_update,
    technical_document_reject,
    technical_document_relationship_create,
    technical_document_request_changes,
    technical_document_submit_review,
    technical_variant_approve,
    technical_variant_retire,
    technical_variant_revision,
    technical_variant_submit_review,
)
from classifire.technical_retirement_admin import (
    approve_technical_retirement,
    reject_technical_retirement,
    request_technical_retirement,
)


@pytest.fixture(autouse=True)
def governed_storage_root(tmp_path, monkeypatch):
    root = tmp_path / "storage"
    monkeypatch.setenv("CLASSIFIRE_STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    configured = get_settings().storage_root
    try:
        yield configured
    finally:
        get_settings.cache_clear()


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


def _user(db: Session, email: str, role: str) -> User:
    user = User(
        email=email,
        full_name=email.split("@", 1)[0].replace(".", " ").title(),
        password_hash="not-used-in-route-tests",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _request(user: User, path: str = "/") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "https",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 1234),
            "server": ("testserver", 443),
            "session": {"user_id": user.id, "csrf_token": "csrf-token"},
        }
    )


def _document(
    db: Session,
    tmp_path,
    *,
    document_id: str = "TEST-REPORT-001",
    status: str = "draft",
    scan_status: str = "clean",
    uploaded_by: User | None = None,
    approved_by: User | None = None,
) -> TechnicalDocument:
    content = f"retained evidence for {document_id}".encode()
    digest = hashlib.sha256(content).hexdigest()
    root = get_settings().storage_root
    source = root / digest[:2] / digest[2:4] / f"{digest}.pdf"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(content)
    stored = StoredFile(
        original_filename=source.name,
        media_type="application/pdf",
        storage_path=str(source),
        sha256=digest,
        size_bytes=source.stat().st_size,
        purpose="technical_evidence",
        malware_scan_status=scan_status,
        uploaded_by_id=uploaded_by.id if uploaded_by else None,
        immutable=True,
    )
    db.add(stored)
    db.flush()
    document = TechnicalDocument(
        document_id=document_id,
        stored_file_id=stored.id,
        document_type="test_report",
        declared_source_role="primary_test",
        artifact_provenance_status="unknown",
        evidence_scope="full_source",
        title=f"Test report {document_id}",
        reference=document_id,
        status=status,
        metadata_json=(
            {
                "human_review_required": True,
                "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
                "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
                "uploaded_by_id": uploaded_by.id if uploaded_by else None,
            }
            if status in {"draft", "rejected"}
            else None
        ),
        reviewed_by_id=approved_by.id if approved_by else None,
        approved_by_id=approved_by.id if approved_by else None,
        approved_at=datetime.now(UTC) if approved_by else None,
    )
    db.add(document)
    db.commit()
    return document


def _candidate(
    db: Session,
    document: TechnicalDocument,
    *,
    variant_id: str = "VAR-001",
    system_id: str = "SYS-001",
    status: str = "draft",
    supersedes_id: str | None = None,
    original_variant_id: str | None = None,
) -> TechnicalVariant:
    source_json = {"test": True}
    if original_variant_id:
        source_json["original_variant_id"] = original_variant_id
    variant = TechnicalVariant(
        variant_id=variant_id,
        system_id=system_id,
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page="12",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        search_eligibility=PENDING_TECHNICAL_REVIEW,
        expert_review_required=True,
        status=status,
        source_hash=hashlib.sha256(variant_id.encode()).hexdigest(),
        source_json=source_json,
        supersedes_id=supersedes_id,
    )
    db.add(variant)
    db.commit()
    return variant


def _submit_and_approve(
    db: Session,
    variant: TechnicalVariant,
    requester: User,
    reviewer: User,
) -> Approval:
    response = technical_variant_submit_review(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Ready for independent technical review",
    )
    assert response.status_code == 303
    db.refresh(variant)
    assert variant.status == "in_review"

    response = technical_variant_approve(
        variant.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="Evidence and structured limits reviewed",
    )
    assert response.status_code == 303
    assert "approved+for+a+future+release" in response.headers["location"]
    db.refresh(variant)
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_variant",
            Approval.entity_id == variant.id,
            Approval.approval_type == TECHNICAL_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at.desc())
    )
    assert approval is not None
    return approval


def _submit_document_review(
    db: Session,
    document: TechnicalDocument,
    requester: User,
) -> Approval:
    response = technical_document_submit_review(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Ready for independent source review",
    )
    assert response.status_code == 303
    assert "Submitted+for+independent+source+review" in response.headers["location"]
    db.refresh(document)
    assert document.status == "in_review"
    approval = db.scalar(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at.desc(), Approval.id.desc())
    )
    assert approval is not None
    assert approval.status == "pending"
    assert approval.snapshot_hash == technical_document_review_snapshot_hash(
        db,
        document.id,
    )
    return approval


def _submit_and_approve_document(
    db: Session,
    document: TechnicalDocument,
    requester: User,
    reviewer: User,
) -> Approval:
    approval = _submit_document_review(db, document, requester)
    response = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="Exact source evidence and lineage reviewed",
    )
    assert response.status_code == 303
    assert "Technical+source+document+approved" in response.headers["location"]
    db.refresh(document)
    db.refresh(approval)
    assert document.status == "approved"
    assert document.reviewed_by_id == reviewer.id
    assert document.approved_by_id == reviewer.id
    assert approval.status == "approved"
    assert approval.requested_by_id == requester.id
    assert approval.decided_by_id == reviewer.id
    assert technical_document_review_reasons(approval) == {
        "request_reason": "Ready for independent source review",
        "decision_reason": "Exact source evidence and lineage reviewed",
    }
    return approval


def _reviewed_document(
    db: Session,
    tmp_path,
    requester: User,
    reviewer: User,
    *,
    document_id: str = "TEST-REPORT-001",
) -> TechnicalDocument:
    document = _document(
        db,
        tmp_path,
        document_id=document_id,
        uploaded_by=requester,
    )
    _submit_and_approve_document(db, document, requester, reviewer)
    return document


def _publish(
    db: Session,
    publisher: User,
    *,
    version: str,
) -> LibraryRelease:
    previous = active_release(db, "technical")
    response = publish_release(
        _request(publisher, "/releases/publish"),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version=version,
        notes=f"Governed release {version}",
        expected_previous_release_id=previous.id if previous else "",
    )
    assert response.status_code == 303
    assert "success=Release+published" in response.headers["location"]
    release = db.scalar(
        select(LibraryRelease).where(
            LibraryRelease.library_type == "technical",
            LibraryRelease.version == version,
        )
    )
    assert release is not None
    return release


def _request_and_approve_retirement(
    db: Session,
    variant: TechnicalVariant,
    requester: User,
    reviewer: User,
) -> Approval:
    response = request_technical_retirement(
        variant.id,
        _request(requester),
        db,
        csrf_token='csrf-token',
        reason='Withdraw this exact technical authority record',
    )
    assert response.status_code == 303
    assert 'submitted+for+independent+review' in response.headers['location']
    db.refresh(variant)
    assert variant.status == 'active'
    approval = latest_technical_retirement(db, variant.id)
    assert approval is not None
    assert approval.status == 'pending'

    response = approve_technical_retirement(
        variant.id,
        _request(reviewer),
        db,
        csrf_token='csrf-token',
        reason='Independent withdrawal review completed',
    )
    assert response.status_code == 303
    assert 'approved+for+the+next+Technical' in response.headers['location']
    db.refresh(variant)
    db.refresh(approval)
    assert variant.status == 'active'
    assert approval.status == 'approved'
    return approval


def _historical_v2_release(
    db: Session,
    variant: TechnicalVariant,
    requester: User,
    reviewer: User,
    publisher: User,
    *,
    version: str,
) -> LibraryRelease:
    """Create an exact already-published v2 fixture without invoking the v3 route."""

    variant.status = "approved"
    variant.search_eligibility = APPROVED_RELEASE_CANDIDATE
    db.flush()
    source_binding = require_technical_source_binding(
        db,
        variant,
        binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
    )
    decided_at = datetime.now(UTC)
    approval = Approval(
        entity_type="technical_variant",
        entity_id=variant.id,
        approval_type=TECHNICAL_REVIEW_APPROVAL_TYPE,
        status="approved",
        requested_by_id=requester.id,
        decided_by_id=reviewer.id,
        requested_at=decided_at,
        decided_at=decided_at,
        decision_reason="Historical v2 independent technical review",
        snapshot_hash=technical_review_snapshot_hash(
            variant,
            source_binding,
            review_policy=TECHNICAL_REVIEW_POLICY_V2,
        ),
    )
    db.add(approval)
    db.flush()
    key = (variant.source_json or {}).get("original_variant_id") or variant.variant_id.split(
        "-QFREV"
    )[0]
    record = {
        "id": variant.id,
        "key": key,
        "variant_id": variant.variant_id,
        "system_id": variant.system_id,
        "frl": variant.frl,
        "source_document_reference": variant.source_document_reference,
        "source_page": variant.source_page,
        "source_hash": variant.source_hash,
        "technical_document_id": variant.technical_document_id,
        "source_binding": source_binding.manifest(),
        "approval_binding": technical_approval_binding(approval),
        "record_hash": technical_variant_snapshot_hash(variant),
        "record_version": variant.record_version,
        "governance_basis": "approved_technical_review",
    }
    payload = {
        "release_type": "technical",
        "version": version,
        "created_at": decided_at.isoformat(),
        "created_by_id": publisher.id,
        "record_count": 1,
        "activated_draft_ids": [],
        "previous_release_id": None,
        "records": [record],
        "notes": f"Historical governed v2 release {version}",
        "governance_policy": GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
        "activated_candidate_ids": [variant.id],
        "superseded_record_ids": [],
        "runtime_authority": "release_manifest_membership",
    }
    release = LibraryRelease(
        library_type="technical",
        version=version,
        status="active",
        effective_date=date.today(),
        release_hash=manifest_hash(payload),
        source_manifest=payload,
        notes=payload["notes"],
        created_by_id=publisher.id,
        approved_by_id=publisher.id,
        approved_at=decided_at,
        active_publication_slot="technical",
    )
    variant.status = "active"
    db.add(release)
    db.commit()
    return release


def test_draft_cannot_bypass_submission_or_self_review(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)

    response = technical_variant_approve(
        variant.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "Only+submitted+In+Review" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "draft"

    technical_variant_submit_review(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    response = technical_variant_approve(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "cannot+approve+their+own" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "in_review"


def test_document_review_uses_global_stored_file_then_document_lock_order(
    db: Session,
    tmp_path: Path,
) -> None:
    document = _document(
        db,
        tmp_path,
        document_id="REVIEW-LOCK-ORDER",
    )
    expected_entities = (
        StoredFile,
        TechnicalDocument,
        TechnicalDocumentRelationship,
    )
    locked_entities: list[type[object]] = []

    def observe_lock(execute_state: Any) -> None:
        statement = execute_state.statement
        if getattr(statement, "_for_update_arg", None) is None:
            return
        entities = tuple(
            description.get("entity")
            for description in getattr(statement, "column_descriptions", ())
        )
        for entity in expected_entities:
            if entity in entities:
                locked_entities.append(entity)
                break

    event.listen(db, "do_orm_execute", observe_lock)
    try:
        technical_document_review_snapshot(db, document.id)
    finally:
        event.remove(db, "do_orm_execute", observe_lock)

    assert tuple(locked_entities) == expected_entities


def test_document_review_rejects_binding_change_after_file_lock(
    db: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(
        db,
        tmp_path,
        document_id="REVIEW-BINDING-RACE-SOURCE",
    )
    replacement = _document(
        db,
        tmp_path,
        document_id="REVIEW-BINDING-RACE-REPLACEMENT",
    )
    original_scalars = db.scalars
    binding_changed = False

    def scalars(statement: Any, *args: Any, **kwargs: Any) -> Any:
        nonlocal binding_changed
        result = original_scalars(statement, *args, **kwargs)
        descriptions = getattr(statement, "column_descriptions", ())
        entity = descriptions[0].get("entity") if descriptions else None
        if (
            entity is StoredFile
            and getattr(statement, "_for_update_arg", None) is not None
            and not binding_changed
        ):
            binding_changed = True
            db.execute(
                update(TechnicalDocument)
                .where(TechnicalDocument.id == document.id)
                .values(stored_file_id=replacement.stored_file_id)
                .execution_options(synchronize_session=False)
            )
        return result

    monkeypatch.setattr(db, "scalars", scalars)

    with pytest.raises(
        TechnicalDocumentReviewError,
        match="SOURCE_DOCUMENT_STATE_CHANGED",
    ):
        technical_document_review_snapshot(db, document.id)
    assert binding_changed is True


def test_document_approval_requires_clean_immutable_source(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path, scan_status="not_configured")

    response = technical_document_submit_review(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_FILE_INVALID" in response.headers["location"]
    db.refresh(document)
    assert document.status == "draft"

    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    stored.malware_scan_status = "clean"
    db.commit()
    source_path = Path(stored.storage_path)
    source_path.write_bytes(b"tampered after upload")
    response = technical_document_submit_review(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_FILE_INVALID" in response.headers["location"]
    db.refresh(document)
    assert document.status == "draft"

    source_path.write_bytes(f"retained evidence for {document.document_id}".encode())
    _submit_and_approve_document(db, document, requester, reviewer)


def test_source_review_requires_submission_and_an_independent_non_uploader(db, tmp_path):
    uploader = _user(db, "uploader@example.test", "technical_reviewer")
    requester = _user(db, "coordinator@example.test", "technical_reviewer")
    reviewer = _user(db, "independent@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=uploader)

    bypass = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_DOCUMENT_NOT_REVIEWABLE" in bypass.headers["location"]
    approval = _submit_document_review(db, document, requester)

    self_decision = technical_document_approve(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "INDEPENDENT_SOURCE_REVIEWER_REQUIRED" in self_decision.headers["location"]
    uploader_decision = technical_document_approve(
        document.id,
        _request(uploader),
        db,
        csrf_token="csrf-token",
    )
    assert "INDEPENDENT_SOURCE_REVIEWER_REQUIRED" in uploader_decision.headers["location"]
    db.refresh(document)
    db.refresh(approval)
    assert document.status == "in_review"
    assert approval.status == "pending"

    approved = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "Technical+source+document+approved" in approved.headers["location"]
    db.refresh(document)
    db.refresh(approval)
    assert document.status == "approved"
    assert approval.decided_by_id == reviewer.id


def test_source_rejection_is_independent_and_resubmission_preserves_history(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    second_reviewer = _user(db, "second.reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=requester)
    first = _submit_document_review(db, document, requester)

    self_rejection = technical_document_reject(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Attempt to decide own request",
    )
    assert "INDEPENDENT_SOURCE_REVIEWER_REQUIRED" in self_rejection.headers["location"]
    rejected = technical_document_reject(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="The evidence needs a new independent review",
    )
    assert "Technical+source+document+rejected" in rejected.headers["location"]
    db.refresh(document)
    db.refresh(first)
    assert document.status == "rejected"
    assert first.status == "rejected"
    assert first.decided_by_id == reviewer.id

    second = _submit_and_approve_document(db, document, requester, second_reviewer)
    approvals = db.scalars(
        select(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
        .order_by(Approval.created_at, Approval.id)
    ).all()
    assert {item.id for item in approvals} == {first.id, second.id}
    assert {item.status for item in approvals} == {"approved", "rejected"}


def test_source_change_request_returns_to_draft_for_lineage_and_resubmission(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    target = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="CHANGE-TARGET",
    )
    document = _document(
        db,
        tmp_path,
        document_id="CHANGE-SOURCE",
        uploaded_by=requester,
    )
    first = _submit_document_review(db, document, requester)

    self_request = technical_document_request_changes(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Attempt to decide own request",
    )
    assert "INDEPENDENT_SOURCE_REVIEWER_REQUIRED" in self_request.headers["location"]
    response = technical_document_request_changes(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="Add the assessment relationship before resubmission",
    )
    assert "Source+changes+requested" in response.headers["location"]
    db.refresh(document)
    db.refresh(first)
    assert document.status == "draft"
    assert document.reviewed_by_id is None
    assert first.status == "changes_requested"
    assert technical_document_review_reasons(first)["decision_reason"] == (
        "Add the assessment relationship before resubmission"
    )

    linked = technical_document_relationship_create(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=target.document_id,
        reason="Requested relationship evidence added before resubmission.",
    )
    assert "success=Source+relationship+recorded" in linked.headers["location"]
    second = _submit_and_approve_document(db, document, requester, reviewer)
    assert first.id != second.id
    assert db.scalar(
        select(func.count())
        .select_from(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
    ) == 2


def test_source_approval_rejects_document_or_file_drift_after_submission(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=requester)
    approval = _submit_document_review(db, document, requester)

    document.title = "Changed after review submission"
    db.commit()
    response = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_REVIEW_SNAPSHOT_CHANGED" in response.headers["location"]
    db.refresh(document)
    db.refresh(approval)
    assert document.status == "in_review"
    assert approval.status == "pending"

    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    source_path = Path(stored.storage_path)
    original_bytes = source_path.read_bytes()
    source_path.write_bytes(b"changed retained bytes")
    response = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_FILE_INVALID" in response.headers["location"]
    source_path.write_bytes(original_bytes)

    rejected = technical_document_reject(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="Submitted evidence changed",
    )
    assert "Technical+source+document+rejected" in rejected.headers["location"]
    db.refresh(document)
    assert document.status == "rejected"


def test_incoming_lineage_does_not_change_submitted_source_snapshot(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    source = _document(db, tmp_path, document_id="SOURCE-UNDER-REVIEW")
    later = _document(db, tmp_path, document_id="LATER-SOURCE")
    approval = _submit_document_review(db, source, requester)
    submitted_hash = approval.snapshot_hash

    response = technical_document_relationship_create(
        later.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=source.document_id,
        reason="The later source assesses the earlier retained report.",
    )
    assert "success=Source+relationship+recorded" in response.headers["location"]
    assert technical_document_review_snapshot_hash(db, source.id) == submitted_hash

    approved = technical_document_approve(
        source.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "Technical+source+document+approved" in approved.headers["location"]


def test_duplicate_source_review_transitions_create_only_one_decision(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path)
    approval = _submit_document_review(db, document, requester)

    duplicate_submit = technical_document_submit_review(
        document.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_DOCUMENT_NOT_REVIEWABLE" in duplicate_submit.headers["location"]
    assert db.scalar(
        select(func.count())
        .select_from(Approval)
        .where(
            Approval.entity_type == "technical_document",
            Approval.entity_id == document.id,
            Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
        )
    ) == 1

    technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    duplicate_decision = technical_document_approve(
        document.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "SOURCE_DOCUMENT_NOT_REVIEWABLE" in duplicate_decision.headers["location"]
    db.refresh(approval)
    assert approval.status == "approved"


def test_two_sqlite_sessions_create_one_source_review_request(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'source-submit-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as setup:
        requester = _user(setup, "requester@example.test", "technical_reviewer")
        document = _document(setup, tmp_path)
        requester_id = requester.id
        document_id = document.id

    rendezvous = Barrier(2)

    def submit_source() -> str:
        with session_factory() as session:
            actor = session.get(User, requester_id)
            assert actor is not None
            rendezvous.wait(timeout=10)
            response = technical_document_submit_review(
                document_id,
                _request(actor),
                session,
                csrf_token="csrf-token",
            )
            return response.headers["location"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=20)
            for future in (pool.submit(submit_source), pool.submit(submit_source))
        ]

    assert sum("Submitted+for+independent+source+review" in item for item in outcomes) == 1
    assert sum(
        "SOURCE_DOCUMENT_STATE_CHANGED" in item
        or "SOURCE_DOCUMENT_NOT_REVIEWABLE" in item
        for item in outcomes
    ) == 1
    with session_factory() as check:
        current = check.get(TechnicalDocument, document_id)
        assert current is not None and current.status == "in_review"
        assert check.scalar(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document_id,
                Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
            )
        ) == 1
    engine.dispose()


def test_two_sqlite_reviewers_create_one_source_decision(tmp_path):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'source-decision-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as setup:
        requester = _user(setup, "requester@example.test", "technical_reviewer")
        approver = _user(setup, "approver@example.test", "technical_reviewer")
        rejecter = _user(setup, "rejecter@example.test", "technical_reviewer")
        document = _document(setup, tmp_path, uploaded_by=requester)
        _submit_document_review(setup, document, requester)
        document_id = document.id
        approver_id = approver.id
        rejecter_id = rejecter.id

    rendezvous = Barrier(2)

    def decide(*, approve: bool, actor_id: str) -> str:
        with session_factory() as session:
            actor = session.get(User, actor_id)
            assert actor is not None
            rendezvous.wait(timeout=10)
            if approve:
                response = technical_document_approve(
                    document_id,
                    _request(actor),
                    session,
                    csrf_token="csrf-token",
                )
            else:
                response = technical_document_reject(
                    document_id,
                    _request(actor),
                    session,
                    csrf_token="csrf-token",
                    reason="Independent rejection decision",
                )
            return response.headers["location"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=20)
            for future in (
                pool.submit(decide, approve=True, actor_id=approver_id),
                pool.submit(decide, approve=False, actor_id=rejecter_id),
            )
        ]

    assert sum(
        "Technical+source+document+approved" in item
        or "Technical+source+document+rejected" in item
        for item in outcomes
    ) == 1
    assert sum(
        "SOURCE_REVIEW_DECISION_CHANGED" in item
        or "SOURCE_DOCUMENT_NOT_REVIEWABLE" in item
        or "SOURCE_DOCUMENT_STATE_CHANGED" in item
        for item in outcomes
    ) == 1
    with session_factory() as check:
        current = check.get(TechnicalDocument, document_id)
        assert current is not None and current.status in {"approved", "rejected"}
        approval = check.scalar(
            select(Approval).where(
                Approval.entity_type == "technical_document",
                Approval.entity_id == document_id,
                Approval.approval_type == TECHNICAL_DOCUMENT_REVIEW_APPROVAL_TYPE,
            )
        )
        assert approval is not None
        assert approval.status == current.status
        assert approval.decided_by_id in {approver_id, rejecter_id}
        assert check.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.entity_type == "technical_document",
                AuditEvent.entity_id == document_id,
                AuditEvent.action.in_({"approve_source_review", "reject_source_review"}),
            )
        ) == 1
    engine.dispose()


def test_source_document_page_exposes_stateful_review_actions_and_history():
    template = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "templates"
        / "technical_document_detail.html"
    ).read_text(encoding="utf-8")

    assert "/submit-review" in template
    assert "/approve" in template
    assert "/reject" in template
    assert "/request-changes" in template
    assert "document.status in ['draft', 'rejected']" in template
    assert "document.status == 'in_review'" in template
    assert "Source approval history" in template
    assert "Request Changes" in template
    assert "approval.snapshot_hash" in template
    assert "different authorised person" in template
    assert "remain excluded from runtime use" in template


def test_source_document_page_exposes_declared_source_registration_editor():
    template = (
        Path(__file__).parents[1]
        / "src"
        / "classifire"
        / "templates"
        / "technical_document_detail.html"
    ).read_text(encoding="utf-8")

    assert "Declared source registration" in template
    assert "Identity separation" in template
    assert "/metadata" in template
    assert 'name="expected_record_version"' in template
    assert 'name="declared_source_role"' in template
    assert 'name="artifact_provenance_status"' in template
    assert 'name="evidence_scope"' in template
    assert "document.status in ['draft', 'rejected']" in template


def test_draft_source_registration_route_updates_only_declared_metadata(db, tmp_path):
    editor = _user(db, "source.editor@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=editor)
    stored_file = db.get(StoredFile, document.stored_file_id)
    assert stored_file is not None
    original_stored_file_id = document.stored_file_id
    original_stored_file_version = stored_file.record_version
    expected_record_version = document.record_version

    response = technical_document_metadata_update(
        document.id,
        _request(editor, f"/technical/documents/{document.id}/metadata"),
        db,
        csrf_token="csrf-token",
        expected_record_version=expected_record_version,
        declared_source_role="assessment",
        artifact_provenance_status="transformed_derivative",
        evidence_scope="bibliographic_only",
        reason="Correct the source classification before review.",
        sponsor_organisation="Example Sponsor",
        artifact_provenance_note="An OCR text layer was added to the retained copy.",
        evidence_limitations="Not direct configuration evidence.",
    )

    assert response.status_code == 303
    assert "success=Source+classification+updated" in response.headers["location"]
    db.refresh(document)
    db.refresh(stored_file)
    assert document.record_version == expected_record_version + 1
    assert document.status == "draft"
    assert document.stored_file_id == original_stored_file_id
    assert stored_file.record_version == original_stored_file_version
    assert document.declared_source_role == "assessment"
    assert document.artifact_provenance_status == "transformed_derivative"
    assert document.evidence_scope == "bibliographic_only"

    stale = technical_document_metadata_update(
        document.id,
        _request(editor, f"/technical/documents/{document.id}/metadata"),
        db,
        csrf_token="csrf-token",
        expected_record_version=expected_record_version,
        declared_source_role="primary_test",
        artifact_provenance_status="issuer_original",
        evidence_scope="full_source",
        reason="Attempt to submit an out-of-date form.",
    )

    assert stale.status_code == 303
    assert "error=SOURCE_METADATA_STALE" in stale.headers["location"]
    db.refresh(document)
    assert document.declared_source_role == "assessment"


def test_source_document_page_renders_review_identities_reasons_and_snapshot(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=requester)
    approval = _submit_and_approve_document(db, document, requester, reviewer)

    response = technical_document_detail(
        document.id,
        _request(reviewer),
        db,
        get_settings(),
    )
    body = response.body.decode("utf-8")

    assert requester.email in body
    assert reviewer.email in body
    assert "Ready for independent source review" in body
    assert "Exact source evidence and lineage reviewed" in body
    assert approval.snapshot_hash in body
    assert "Submit for Review" not in body


def test_document_relationship_route_preserves_predecessor_and_runtime_state(db, tmp_path):
    reviewer = _user(db, "lineage.reviewer@example.test", "technical_reviewer")
    predecessor = _document(
        db,
        tmp_path,
        document_id="SOURCE-PREDECESSOR",
        status="approved",
        approved_by=reviewer,
    )
    successor = _document(
        db,
        tmp_path,
        document_id="SOURCE-SUCCESSOR",
    )
    predecessor_binding = (
        predecessor.stored_file_id,
        predecessor.status,
        predecessor.reviewed_by_id,
        predecessor.approved_by_id,
        predecessor.approved_at,
    )

    response = technical_document_relationship_create(
        successor.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        relationship_type="revision_of",
        related_document_id=predecessor.document_id,
        reason="The issuing body identifies this as the next revision.",
    )

    assert "success=Source+relationship+recorded" in response.headers["location"]
    relationship = db.scalar(
        select(TechnicalDocumentRelationship).where(
            TechnicalDocumentRelationship.document_id == successor.id
        )
    )
    assert relationship is not None
    assert relationship.related_document_id == predecessor.id
    assert relationship.relationship_type == "revision_of"
    db.refresh(predecessor)
    db.refresh(successor)
    assert (
        predecessor.stored_file_id,
        predecessor.status,
        predecessor.reviewed_by_id,
        predecessor.approved_by_id,
        predecessor.approved_at,
    ) == predecessor_binding
    assert successor.status == "draft"
    assert active_release(db, "technical") is None
    assert db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_type == "technical_document_relationship",
            AuditEvent.entity_id == relationship.id,
        )
    ) is not None


def test_linked_source_approval_waits_for_related_source_approval(db, tmp_path):
    requester = _user(db, "lineage.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "lineage.approver@example.test", "technical_reviewer")
    related = _document(db, tmp_path, document_id="SOURCE-UNDER-REVIEW")
    linked = _document(db, tmp_path, document_id="SOURCE-LINKED")
    technical_document_relationship_create(
        linked.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=related.document_id,
        reason="This assessment relies on the related retained report.",
    )

    response = technical_document_submit_review(
        linked.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "RELATED_SOURCE_NOT_APPROVED" in response.headers["location"]
    db.refresh(linked)
    assert linked.status == "draft"

    _submit_and_approve_document(db, related, requester, reviewer)
    linked_approval = _submit_and_approve_document(db, linked, requester, reviewer)
    db.refresh(related)
    db.refresh(linked)
    assert related.status == "approved"
    assert linked.status == "approved"
    approval_audit = db.scalar(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "technical_document",
            AuditEvent.entity_id == linked.id,
            AuditEvent.action == "approve_source_review",
        )
        .order_by(AuditEvent.created_at.desc())
    )
    assert approval_audit is not None
    assert approval_audit.new_value["snapshot_hash"] == linked_approval.snapshot_hash
    snapshot = technical_document_review_snapshot(db, linked.id)
    assert snapshot["outgoing_relationships"][0]["relationship_type"] == "assessment_of"
    assert snapshot["outgoing_relationships"][0]["target_document"]["document_id"] == (
        related.document_id
    )
    assert snapshot["outgoing_relationships"][0]["target_stored_file"]["sha256"]
    assert snapshot["outgoing_relationships"][0]["target_review_receipt"][
        "snapshot_hash"
    ]


def test_lineage_bearing_source_is_v3_reviewable_but_still_rejected_by_v2(db, tmp_path):
    requester = _user(db, "lineage.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "lineage.reviewer@example.test", "technical_reviewer")
    related = _document(db, tmp_path, document_id="SOURCE-BASE")
    linked = _document(db, tmp_path, document_id="SOURCE-ASSESSMENT")
    _submit_and_approve_document(db, related, requester, reviewer)
    technical_document_relationship_create(
        linked.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=related.document_id,
        reason="Assessment depends on the base test report.",
    )
    _submit_and_approve_document(db, linked, requester, reviewer)
    variant = _candidate(db, linked, variant_id="LINEAGE-VAR-001")
    with pytest.raises(
        TechnicalGovernanceError,
        match="source_lineage_requires_v3_release_binding",
    ):
        require_technical_source_binding(
            db,
            variant,
            binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
        )
    technical_variant_submit_review(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )

    response = technical_variant_approve(
        variant.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )

    assert "approved+for+a+future+release" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    binding = require_technical_source_binding(
        db,
        variant,
        binding_policy=GOVERNED_TECHNICAL_RELEASE_POLICY_V3,
    )
    assert binding.manifest()["outgoing_relationships"][0]["relationship_type"] == (
        "assessment_of"
    )
    assert active_release(db, "technical") is None


def test_new_policy_source_requires_independent_receipt_before_runtime(db, tmp_path):
    uploader = _user(db, "uploader@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(
        db,
        tmp_path,
        status="approved",
        uploaded_by=uploader,
        approved_by=reviewer,
    )
    document.metadata_json = {
        "human_review_required": True,
        "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
        "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
        "uploaded_by_id": uploader.id,
    }
    db.commit()
    variant = _candidate(db, document)

    with pytest.raises(TechnicalGovernanceError, match="source_document_review_required"):
        require_technical_source_binding(db, variant)


def test_new_policy_source_receipt_supports_runtime_and_detects_later_drift(db, tmp_path):
    uploader = _user(db, "uploader@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=uploader)
    document.metadata_json = {
        "human_review_required": True,
        "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
        "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
        "uploaded_by_id": uploader.id,
    }
    db.commit()
    _submit_and_approve_document(db, document, uploader, reviewer)
    variant = _candidate(db, document)

    binding = require_technical_source_binding(db, variant)
    assert binding.document["document_id"] == document.document_id
    assert binding.source_review is not None
    assert binding.source_review["decided_by_id"] == reviewer.id
    assert binding.source_review["reasons"] == {
        "request_reason": "Ready for independent source review",
        "decision_reason": "Exact source evidence and lineage reviewed",
    }
    assert binding.manifest()["source_review"] == binding.source_review
    document.title = "Changed after independent source approval"
    db.commit()
    with pytest.raises(
        TechnicalGovernanceError,
        match="source_document_review_snapshot_changed",
    ):
        require_technical_source_binding(db, variant)


def test_source_receipt_projection_or_reason_drift_fails_downstream(db, tmp_path):
    uploader = _user(db, "uploader@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    replacement = _user(db, "replacement@example.test", "technical_reviewer")
    document = _document(db, tmp_path, uploaded_by=uploader)
    document.metadata_json = {
        "human_review_required": True,
        "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
        "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
        "uploaded_by_id": uploader.id,
    }
    db.commit()
    source_approval = _submit_and_approve_document(db, document, uploader, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, uploader, reviewer)

    document.approved_by_id = replacement.id
    db.commit()
    with pytest.raises(
        TechnicalGovernanceError,
        match="independent_source_document_reviewer_required",
    ):
        require_technical_source_binding(db, variant)

    document.approved_by_id = reviewer.id
    reasons = json.loads(source_approval.decision_reason)
    reasons["decision_reason"] = "Changed decision rationale after variant review"
    source_approval.decision_reason = json.dumps(
        reasons,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    db.commit()
    blockers, _approval, _binding = release_candidate_blockers(db, variant)
    assert "approved_snapshot_changed" in blockers


def test_new_policy_link_target_requires_a_valid_non_drifted_receipt(db, tmp_path):
    uploader = _user(db, "uploader@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    target = _document(db, tmp_path, document_id="POLICY-TARGET", uploaded_by=uploader)
    target.metadata_json = {
        "human_review_required": True,
        "source_review_policy": TECHNICAL_DOCUMENT_REVIEW_POLICY,
        "source_registration_schema": TECHNICAL_SOURCE_REGISTRATION_SCHEMA,
        "uploaded_by_id": uploader.id,
    }
    target.status = "approved"
    target.reviewed_by_id = reviewer.id
    target.approved_by_id = reviewer.id
    target.approved_at = datetime.now(UTC)
    source = _document(db, tmp_path, document_id="POLICY-SOURCE", uploaded_by=uploader)
    db.commit()
    technical_document_relationship_create(
        source.id,
        _request(uploader),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=target.document_id,
        reason="The assessment depends on the target report.",
    )

    missing_receipt = technical_document_submit_review(
        source.id,
        _request(uploader),
        db,
        csrf_token="csrf-token",
    )
    assert "RELATED_SOURCE_REVIEW_INVALID" in missing_receipt.headers["location"]
    db.refresh(source)
    assert source.status == "draft"

    target.status = "draft"
    target.reviewed_by_id = None
    target.approved_by_id = None
    target.approved_at = None
    db.commit()
    _submit_and_approve_document(db, target, uploader, reviewer)
    source_review = _submit_document_review(db, source, uploader)
    target.title = "Drifted after target review"
    db.commit()
    drifted_target = technical_document_approve(
        source.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )
    assert "RELATED_SOURCE_REVIEW_INVALID" in drifted_target.headers["location"]
    db.refresh(source)
    db.refresh(source_review)
    assert source.status == "in_review"
    assert source_review.status == "pending"


def test_approved_source_document_cannot_be_reapproved_or_mutated(db, tmp_path):
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    replacement_reviewer = _user(db, "replacement@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    requester = _user(db, "requester@example.test", "technical_reviewer")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version="TAR-document-binding")
    original_binding = (
        document.status,
        document.reviewed_by_id,
        document.approved_by_id,
        document.approved_at,
    )

    response = technical_document_approve(
        document.id,
        _request(replacement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Attempt to replace the bound document reviewer",
    )

    assert "SOURCE_DOCUMENT_NOT_REVIEWABLE" in response.headers["location"]
    db.refresh(document)
    assert (
        document.status,
        document.reviewed_by_id,
        document.approved_by_id,
        document.approved_at,
    ) == original_binding
    assert active_release(db, "technical") is release


def test_technical_reviewer_cannot_publish_their_own_decision(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    source_reviewer = _user(db, "source.reviewer@example.test", "technical_reviewer")
    reviewer_and_publisher = _user(db, "administrator@example.test", "administrator")
    document = _reviewed_document(
        db,
        tmp_path,
        requester,
        source_reviewer,
    )
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer_and_publisher)

    response = publish_release(
        _request(reviewer_and_publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-self-published-review",
    )

    assert "TECHNICAL_RELEASE_INDEPENDENT_PUBLISHER_REQUIRED" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert active_release(db, "technical") is None


def test_import_can_be_linked_reviewed_and_published_without_legacy_activation(
    db,
    tmp_path,
):
    author = _user(db, "author@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _document(db, tmp_path, uploaded_by=author)
    _submit_and_approve_document(db, document, author, reviewer)

    source_row = {
        "Variant_ID": "IMPORTED-VAR-001",
        "System_ID": "IMPORTED-SYS-001",
        "Source_Document_ID": document.document_id,
        "Source_Page": "12",
        "Service_Type": "pipe",
        "Service_Material": "steel",
        "FRL_Variant": "-/120/120",
        "Variant_Status": "active",
        "Search_Index_Status": "ACTIVE",
        "Search_Eligibility": "INCLUDE",
    }
    source = tmp_path / "technical.jsonl"
    source.write_text(json.dumps(source_row) + "\n", encoding="utf-8", newline="\n")
    import_technical_variants(db, source, version="intake-v1")
    imported = db.scalar(
        select(TechnicalVariant).where(TechnicalVariant.variant_id == "IMPORTED-VAR-001")
    )
    assert imported is not None
    assert imported.status == "draft"

    technical_variant_revision(
        imported.id,
        _request(author),
        db,
        csrf_token="csrf-token",
        service_type="pipe",
        service_material="steel",
        frl="-/120/120",
        technical_document_id=document.id,
        source_document_reference=document.document_id,
        source_page="12",
        reason="Link retained report and create reviewable candidate",
    )
    revision = db.scalar(
        select(TechnicalVariant).where(TechnicalVariant.supersedes_id == imported.id)
    )
    assert revision is not None
    assert revision.technical_document_id == document.id
    assert revision.search_eligibility == PENDING_TECHNICAL_REVIEW
    assert (
        db.scalar(
            select(func.count()).select_from(Approval).where(Approval.entity_id == revision.id)
        )
        == 0
    )

    approval = _submit_and_approve(db, revision, author, reviewer)
    assert revision.status == "approved"
    assert revision.search_eligibility == APPROVED_RELEASE_CANDIDATE
    assert revision.expert_review_required is True
    source_binding = require_technical_source_binding(db, revision)
    assert approval.snapshot_hash == technical_review_snapshot_hash(revision, source_binding)
    assert active_release(db, "technical") is None
    assert search_variants(db, service_type="pipe") == []

    loose_legacy = TechnicalVariant(
        variant_id="LOOSE-LEGACY-ACTIVE",
        system_id="LEGACY-SYS",
        status="active",
        expert_review_required=False,
        source_hash="legacy",
        source_json={"legacy": True},
    )
    db.add(loose_legacy)
    db.commit()

    with pytest.raises(HTTPException) as forbidden:
        publish_release(
            _request(reviewer),
            db,
            csrf_token="csrf-token",
            release_type="technical",
            version="TAR-denied",
        )
    assert forbidden.value.status_code == 403

    release = _publish(db, publisher, version="TAR-2026.08.27")
    db.refresh(revision)
    db.refresh(loose_legacy)
    assert revision.status == "active"
    assert loose_legacy.status == "active"
    assert release.source_manifest["governance_policy"] == GOVERNED_TECHNICAL_RELEASE_POLICY
    assert release.source_manifest["activated_candidate_ids"] == [revision.id]
    assert {item["id"] for item in release.source_manifest["records"]} == {revision.id}
    candidates = search_variants(db, service_type="pipe")
    assert [item.variant.id for item in candidates] == [revision.id]
    assert "expert_review_required" in candidates[0].blockers
    activation_audit = db.scalar(
        select(AuditEvent).where(AuditEvent.action == "activate_via_technical_release")
    )
    assert activation_audit is not None
    assert activation_audit.new_value["published_release_id"] == release.id
    assert activation_audit.new_value["intake_release_id"] == revision.release_id
    assert "release_id" not in activation_audit.new_value


def test_candidate_changed_after_review_cannot_be_published(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)

    variant.service_material = "copper"
    db.commit()
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-tampered-candidate",
    )
    assert "approved_snapshot_changed" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert active_release(db, "technical") is None


def test_governed_release_replacement_preserves_old_pinned_membership(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)

    first = _candidate(db, document, variant_id="VAR-ROOT")
    _submit_and_approve(db, first, requester, reviewer)
    first_release = _publish(db, publisher, version="TAR-v1")

    replacement = _candidate(
        db,
        document,
        variant_id="VAR-ROOT-QFREV01",
        supersedes_id=first.id,
        original_variant_id="VAR-ROOT",
    )
    replacement.service_material = "copper"
    db.commit()
    _submit_and_approve(db, replacement, requester, reviewer)
    second_release = _publish(db, publisher, version="TAR-v2")

    db.refresh(first)
    db.refresh(replacement)
    db.refresh(first_release)
    assert first.status == "superseded"
    assert replacement.status == "active"
    assert first_release.status == "superseded"
    assert second_release.status == "active"
    old_estimate = SimpleNamespace(technical_release_id=first_release.id)
    assert release_record_ids(db, old_estimate, "technical") == {first.id}
    assert [item.variant.id for item in search_variants(db)] == [replacement.id]


def test_published_record_drift_fails_closed_for_current_and_pinned_search(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version="TAR-v1")

    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    source_path = Path(stored.storage_path)
    original_bytes = source_path.read_bytes()
    source_path.write_bytes(b"tampered after publication")
    assert active_release(db, "technical") is None
    estimate = SimpleNamespace(technical_release_id=release.id)
    with pytest.raises(ReleaseScopeError, match="source evidence mismatch"):
        release_record_ids(db, estimate, "technical")
    source_path.write_bytes(original_bytes)
    assert active_release(db, "technical") is release

    variant.frl = "-/60/60"
    db.commit()
    assert active_release(db, "technical") is None
    assert search_variants(db) == []
    with pytest.raises(ReleaseScopeError, match="changed after publication"):
        release_record_ids(db, estimate, "technical")


@pytest.mark.parametrize(
    "drift_status",
    ["draft", "in_review", "approved", "rejected", "retired", "superseded"],
)
def test_active_release_rejects_member_lifecycle_drift(db, tmp_path, drift_status):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version=f"TAR-status-{drift_status}")
    estimate = SimpleNamespace(technical_release_id=release.id)

    variant.status = drift_status
    db.commit()

    assert active_release(db, "technical") is None
    assert search_variants(db) == []
    with pytest.raises(ReleaseScopeError, match="invalid lifecycle state"):
        release_record_ids(db, estimate, "technical")


def test_runtime_rechecks_variant_effective_and_expiry_dates(db, tmp_path, monkeypatch):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    variant.effective_date = date.today()
    variant.expiry_date = date.today()
    db.commit()
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version="TAR-date-window")
    estimate = SimpleNamespace(technical_release_id=release.id)

    class Yesterday(date):
        @classmethod
        def today(cls):
            return date.today() - timedelta(days=1)

    monkeypatch.setattr(release_scope, "date", Yesterday)
    assert active_release(db, "technical") is None
    with pytest.raises(ReleaseScopeError, match="not yet effective"):
        release_record_ids(db, estimate, "technical")

    class Tomorrow(date):
        @classmethod
        def today(cls):
            return date.today() + timedelta(days=1)

    monkeypatch.setattr(release_scope, "date", Tomorrow)
    assert active_release(db, "technical") is None
    with pytest.raises(ReleaseScopeError, match="expired"):
        release_record_ids(db, estimate, "technical")


def test_raw_hash_legacy_import_release_is_not_runtime_authority(db):
    release = LibraryRelease(
        library_type="technical",
        version="legacy-import",
        status="active",
        release_hash="a" * 64,
        source_manifest={"filename": "legacy.jsonl", "sha256": "a" * 64},
    )
    db.add(release)
    db.commit()

    assert active_release(db, "technical") is None
    assert search_variants(db) == []


def test_source_reference_must_match_linked_technical_document(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    variant.source_document_reference = "DIFFERENT-REPORT"
    db.commit()

    technical_variant_submit_review(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    response = technical_variant_approve(
        variant.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
    )

    assert "source_document_reference_mismatch" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "in_review"


def test_reviewed_document_cannot_be_rebound_before_publication(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    reviewed = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="REVIEWED-REPORT",
    )
    replacement = _document(
        db,
        tmp_path,
        document_id="UNREVIEWED-REPLACEMENT",
        status="approved",
        approved_by=reviewer,
    )
    variant = _candidate(db, reviewed)
    _submit_and_approve(db, variant, requester, reviewer)

    reviewed.stored_file_id = replacement.stored_file_id
    db.commit()
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-source-rebound",
    )

    assert "source_document_review_snapshot_changed" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert active_release(db, "technical") is None


def test_reviewer_cannot_retire_runtime_active_variant(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version="TAR-active-retirement")

    response = technical_variant_retire(
        variant.id,
        _request(reviewer),
        db,
        csrf_token="csrf-token",
        reason="Attempt reviewer-only live retirement",
    )

    assert "governed+Technical+Authority+Registry+release" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "active"
    assert active_release(db, "technical") is release


def test_stale_retirement_cannot_overwrite_newly_published_variant(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'publish-retire-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
        connection.exec_driver_sql("PRAGMA busy_timeout=5000")
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as setup:
        requester = _user(setup, "requester@example.test", "technical_reviewer")
        reviewer = _user(setup, "reviewer@example.test", "technical_reviewer")
        publisher = _user(setup, "publisher@example.test", "technical_release_manager")
        document = _reviewed_document(setup, tmp_path, requester, reviewer)
        variant = _candidate(setup, document)
        _submit_and_approve(setup, variant, requester, reviewer)
        variant_id = variant.id

    retire_ready = Event()
    publication_done = Event()
    real_update = technical_admin.update

    def delay_retirement_update(model):
        if model is TechnicalVariant:
            retire_ready.set()
            if not publication_done.wait(timeout=10):
                raise RuntimeError("publication did not complete before retirement timeout")
        return real_update(model)

    monkeypatch.setattr(technical_admin, "update", delay_retirement_update)

    def retire_candidate() -> str:
        with session_factory() as session:
            response = technical_variant_retire(
                variant_id,
                _request(reviewer),
                session,
                csrf_token="csrf-token",
                reason="Concurrent stale retirement",
            )
            return response.headers["location"]

    with ThreadPoolExecutor(max_workers=1) as pool:
        retire_future = pool.submit(retire_candidate)
        assert retire_ready.wait(timeout=10)
        try:
            with session_factory() as publishing:
                response = publish_release(
                    _request(publisher),
                    publishing,
                    csrf_token="csrf-token",
                    release_type="technical",
                    version="TAR-publish-retire-race",
                )
                assert "success=Release+published" in response.headers["location"]
        finally:
            publication_done.set()
        retire_location = retire_future.result(timeout=20)

    assert "Active+variants+can+only+be+removed" in retire_location
    with session_factory() as check:
        current = check.get(TechnicalVariant, variant_id)
        assert current is not None and current.status == "active"
        assert active_release(check, "technical") is not None
        assert (
            check.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "retire")
            )
            == 0
        )
    engine.dispose()


def test_final_source_revalidation_rolls_back_publication(db, tmp_path, monkeypatch):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    stored = db.get(StoredFile, document.stored_file_id)
    assert stored is not None
    source_path = Path(stored.storage_path)
    real_validate = release_admin.validate_release

    def tamper_then_validate(*args, **kwargs):
        source_path.write_bytes(b"changed between preflight and commit")
        return real_validate(*args, **kwargs)

    monkeypatch.setattr(release_admin, "validate_release", tamper_then_validate)
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-final-validation",
    )

    assert "TECHNICAL_RELEASE_FINAL_VALIDATION_FAILED" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-final-validation")
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action.in_({"activate_via_technical_release", "publish_release"}))
        )
        == 0
    )


def test_late_exception_rolls_back_every_publication_mutation(db, tmp_path, monkeypatch):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    real_record_audit = release_admin.record_audit

    def fail_final_audit(*args, **kwargs):
        if kwargs.get("action") == "publish_release":
            raise RuntimeError("injected late publication failure")
        return real_record_audit(*args, **kwargs)

    monkeypatch.setattr(release_admin, "record_audit", fail_final_audit)
    with pytest.raises(RuntimeError, match="injected late publication failure"):
        publish_release(
            _request(publisher),
            db,
            csrf_token="csrf-token",
            release_type="technical",
            version="TAR-late-failure",
        )

    db.refresh(variant)
    assert variant.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-late-failure")
        )
        == 0
    )
    assert (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "activate_via_technical_release")
        )
        == 0
    )
    assert db.scalar(select(func.count()).select_from(User)) == 3


def test_failed_replacement_restores_previous_release_and_variant_states(
    db,
    tmp_path,
    monkeypatch,
):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    first = _candidate(db, document, variant_id="ROLLBACK-ROOT")
    _submit_and_approve(db, first, requester, reviewer)
    first_release = _publish(db, publisher, version="TAR-rollback-v1")
    replacement = _candidate(
        db,
        document,
        variant_id="ROLLBACK-ROOT-QFREV01",
        supersedes_id=first.id,
        original_variant_id="ROLLBACK-ROOT",
    )
    replacement.service_material = "copper"
    db.commit()
    _submit_and_approve(db, replacement, requester, reviewer)
    audit_count_before = db.scalar(select(func.count()).select_from(AuditEvent))
    real_record_audit = release_admin.record_audit

    def fail_final_audit(*args, **kwargs):
        if kwargs.get("action") == "publish_release":
            raise RuntimeError("injected replacement publication failure")
        return real_record_audit(*args, **kwargs)

    monkeypatch.setattr(release_admin, "record_audit", fail_final_audit)
    with pytest.raises(RuntimeError, match="injected replacement publication failure"):
        publish_release(
            _request(publisher),
            db,
            csrf_token="csrf-token",
            release_type="technical",
            version="TAR-rollback-v2",
            expected_previous_release_id=first_release.id,
        )

    db.expire_all()
    restored_release = db.get(LibraryRelease, first_release.id)
    restored_first = db.get(TechnicalVariant, first.id)
    restored_replacement = db.get(TechnicalVariant, replacement.id)
    assert restored_release is not None
    assert restored_release.status == "active"
    assert restored_release.active_publication_slot == "technical"
    assert restored_first is not None and restored_first.status == "active"
    assert restored_replacement is not None and restored_replacement.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-rollback-v2")
        )
        == 0
    )
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count_before
    assert active_release(db, "technical") is restored_release


def test_database_allows_only_one_governed_technical_publication_slot(db):
    first = LibraryRelease(
        library_type="technical",
        version="TAR-slot-1",
        status="active",
        release_hash="1" * 64,
        source_manifest={"records": [{"id": "first"}]},
        active_publication_slot="technical",
    )
    db.add(first)
    db.commit()
    db.add(
        LibraryRelease(
            library_type="technical",
            version="TAR-slot-2",
            status="active",
            release_hash="2" * 64,
            source_manifest={"records": [{"id": "second"}]},
            active_publication_slot="technical",
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.active_publication_slot == "technical")
        )
        == 1
    )


def test_publication_slot_conflict_rolls_back_and_returns_retry(db, tmp_path, monkeypatch):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    _submit_and_approve(db, variant, requester, reviewer)
    real_flush = db.flush

    def conflicting_flush(*args, **kwargs):
        if any(isinstance(item, LibraryRelease) and item.version == "TAR-raced" for item in db.new):
            raise IntegrityError(
                "INSERT library_releases",
                {},
                RuntimeError("UNIQUE constraint failed: library_releases.active_publication_slot"),
            )
        return real_flush(*args, **kwargs)

    monkeypatch.setattr(db, "flush", conflicting_flush)
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-raced",
    )

    assert "TECHNICAL_RELEASE_PUBLICATION_CONFLICT_RETRY" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-raced")
        )
        == 0
    )


def test_two_sqlite_sessions_cannot_publish_competing_technical_releases(
    tmp_path,
    monkeypatch,
):
    engine = create_engine(
        f"sqlite+pysqlite:///{(tmp_path / 'publication-race.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 2},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(engine, expire_on_commit=False)
    with session_factory() as setup:
        requester = _user(setup, "requester@example.test", "technical_reviewer")
        reviewer = _user(setup, "reviewer@example.test", "technical_reviewer")
        publisher_one = _user(setup, "publisher.one@example.test", "technical_release_manager")
        publisher_two = _user(setup, "publisher.two@example.test", "technical_release_manager")
        document = _reviewed_document(setup, tmp_path, requester, reviewer)
        variant = _candidate(setup, document)
        _submit_and_approve(setup, variant, requester, reviewer)
        variant_id = variant.id

    rendezvous = Barrier(2)
    real_snapshot = release_admin._technical_release_snapshot

    def synchronized_snapshot(*args, **kwargs):
        snapshot = real_snapshot(*args, **kwargs)
        rendezvous.wait(timeout=10)
        return snapshot

    monkeypatch.setattr(release_admin, "_technical_release_snapshot", synchronized_snapshot)

    def publish_as(user: User, version: str) -> str:
        with session_factory() as session:
            response = publish_release(
                _request(user),
                session,
                csrf_token="csrf-token",
                release_type="technical",
                version=version,
            )
            return response.headers["location"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [
            future.result(timeout=20)
            for future in (
                pool.submit(publish_as, publisher_one, "TAR-race-one"),
                pool.submit(publish_as, publisher_two, "TAR-race-two"),
            )
        ]

    assert sum("success=Release+published" in outcome for outcome in outcomes) == 1
    assert (
        sum("TECHNICAL_RELEASE_PUBLICATION_CONFLICT_RETRY" in outcome for outcome in outcomes) == 1
    )
    with session_factory() as check:
        releases = check.scalars(
            select(LibraryRelease).where(
                LibraryRelease.library_type == "technical",
                LibraryRelease.version.in_({"TAR-race-one", "TAR-race-two"}),
            )
        ).all()
        assert len(releases) == 1
        assert releases[0].status == "active"
        assert releases[0].active_publication_slot == "technical"
        assert check.get(TechnicalVariant, variant_id).status == "active"
        assert (
            check.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "publish_release")
            )
            == 1
        )
        assert (
            check.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "activate_via_technical_release")
            )
            == 1
        )
    engine.dispose()


def test_canonical_legacy_release_cannot_supply_runtime_or_pinned_authority(db):
    variant = TechnicalVariant(
        variant_id="LEGACY-PINNED",
        system_id="LEGACY-SYSTEM",
        status="active",
        source_hash="legacy-source",
        source_json={"legacy": True},
    )
    db.add(variant)
    db.flush()
    manifest = {
        "release_type": "technical",
        "records": [
            {
                "id": variant.id,
                "key": variant.variant_id,
                "variant_id": variant.variant_id,
                "system_id": variant.system_id,
                "frl": variant.frl,
                "source_document_reference": variant.source_document_reference,
                "source_page": variant.source_page,
                "source_hash": variant.source_hash,
                "record_version": variant.record_version,
            }
        ],
    }
    release = LibraryRelease(
        library_type="technical",
        version="legacy-canonical",
        status="active",
        release_hash=manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.commit()

    existing_estimate = SimpleNamespace(technical_release_id=release.id)
    with pytest.raises(
        ReleaseScopeError,
        match="Legacy Technical release cannot be used",
    ):
        release_record_ids(db, existing_estimate, "technical")
    assert active_release(db, "technical") is None
    with pytest.raises(ReleaseScopeError, match="No active technical release"):
        active_release_record_ids(db, "technical")
    assert search_variants(db) == []

    variant.frl = "-/30/30"
    variant.source_hash = "changed-after-legacy-publication"
    db.commit()
    with pytest.raises(ReleaseScopeError, match="Legacy Technical release cannot be used"):
        release_record_ids(db, existing_estimate, "technical")


def test_legacy_release_without_canonical_field_bindings_fails_closed(db):
    variant = TechnicalVariant(
        variant_id="LEGACY-INCOMPLETE",
        system_id="LEGACY-INCOMPLETE-SYSTEM",
        status="active",
        source_hash="legacy-source",
        source_json={"legacy": True},
    )
    db.add(variant)
    db.flush()
    manifest = {
        "release_type": "technical",
        "records": [
            {
                "id": variant.id,
                "variant_id": variant.variant_id,
                "system_id": variant.system_id,
            }
        ],
    }
    release = LibraryRelease(
        library_type="technical",
        version="legacy-incomplete",
        status="superseded",
        release_hash=manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.commit()

    estimate = SimpleNamespace(technical_release_id=release.id)
    with pytest.raises(ReleaseScopeError, match="Legacy Technical release cannot be used"):
        release_record_ids(db, estimate, "technical")


def test_published_approval_and_document_binding_drift_fail_closed(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document)
    approval = _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version="TAR-binding-drift")
    estimate = SimpleNamespace(technical_release_id=release.id)

    original_requester = approval.requested_by_id
    approval.requested_by_id = approval.decided_by_id
    db.commit()
    assert active_release(db, "technical") is None
    with pytest.raises(ReleaseScopeError, match="approval mismatch"):
        release_record_ids(db, estimate, "technical")

    approval.requested_by_id = original_requester
    db.commit()
    assert active_release(db, "technical") is release

    replacement = _document(
        db,
        tmp_path,
        document_id="POST-PUBLISH-REPLACEMENT",
        status="approved",
        approved_by=reviewer,
    )
    document.stored_file_id = replacement.stored_file_id
    db.commit()
    assert active_release(db, "technical") is None
    with pytest.raises(ReleaseScopeError, match="source evidence mismatch"):
        release_record_ids(db, estimate, "technical")


def test_snapshot_lock_rejects_selected_variant_outside_pinned_manifest(db, tmp_path):
    requester = _user(db, "requester@example.test", "technical_reviewer")
    reviewer = _user(db, "reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    governed = _candidate(db, document, variant_id="GOVERNED-VARIANT")
    _submit_and_approve(db, governed, requester, reviewer)
    technical_release = _publish(db, publisher, version="TAR-lock-scope")

    outside = TechnicalVariant(
        variant_id="OUTSIDE-PIN",
        system_id="OUTSIDE-SYSTEM",
        status="active",
        source_hash="outside",
        source_json={"legacy": True},
    )
    db.add(outside)
    project = Project(reference="PROJECT-LOCK-SCOPE", name="Lock scope")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="ESTIMATE-LOCK-SCOPE",
        title="Lock scope",
        technical_release_id=technical_release.id,
    )
    db.add(estimate)
    db.flush()
    db.add(
        Opening(
            estimate_id=estimate.id,
            opening_code="OPENING-001",
            selected_technical_variant_id=outside.id,
        )
    )
    for kind, field in (
        ("pricing", "pricing_release_id"),
        ("rules", "rules_release_id"),
        ("products", "products_release_id"),
        ("labour", "labour_release_id"),
        ("markups", "markups_release_id"),
    ):
        manifest = {"records": [{"id": f"{kind}-record"}]}
        release = LibraryRelease(
            library_type=kind,
            version=f"{kind}-lock-scope",
            status="active",
            release_hash=manifest_hash(manifest),
            source_manifest=manifest,
        )
        db.add(release)
        db.flush()
        setattr(estimate, field, release.id)
    db.commit()

    with pytest.raises(ValueError, match="not in the pinned Technical release"):
        lock_snapshot(db, estimate)

    assert estimate.status == "draft"
    assert estimate.snapshot_hash is None
    assert estimate.snapshot_json is None
    assert estimate.locked_at is None


def test_ui_no_longer_offers_approve_and_activate():
    detail = Path("src/classifire/templates/technical_variant_detail.html").read_text(
        encoding="utf-8"
    )
    assert "Approve & Activate" not in detail
    assert "Approve for Release" in detail
    assert "/retirement/request" in detail
    assert "/retirement/approve" in detail
    assert "/retirement/reject" in detail
    assert "Retirement approved, not yet effective" in detail
    releases = Path("src/classifire/templates/releases.html").read_text(encoding="utf-8")
    assert 'name="expected_previous_release_id"' in releases
    assert "Technical retirement publication review" in releases
    release_detail_template = Path(
        "src/classifire/templates/release_detail.html"
    ).read_text(encoding="utf-8")
    assert "Technical authority bindings" in release_detail_template
    assert "Governed retirement receipts" in release_detail_template
    assert "Source review receipt" in release_detail_template
    assert "Typed outgoing lineage" in release_detail_template


def test_exact_v2_hash_and_pin_survive_explicit_v3_carry_forward(db, tmp_path):
    requester = _user(db, "v2.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "v2.reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "v2.publisher@example.test", "technical_release_manager")
    old_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="V2-SOURCE",
    )
    old_variant = _candidate(db, old_document, variant_id="V2-RECORD")
    old_release = _historical_v2_release(
        db,
        old_variant,
        requester,
        reviewer,
        publisher,
        version="TAR-v2-golden",
    )
    original_manifest = copy.deepcopy(old_release.source_manifest)
    original_hash = old_release.release_hash
    assert "record_binding_policy" not in original_manifest["records"][0]
    old_estimate = SimpleNamespace(technical_release_id=old_release.id)
    assert release_record_ids(db, old_estimate, "technical") == {old_variant.id}

    new_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="V3-SOURCE",
    )
    new_variant = _candidate(db, new_document, variant_id="V3-RECORD")
    _submit_and_approve(db, new_variant, requester, reviewer)
    new_release = _publish(db, publisher, version="TAR-v3-carry")

    db.refresh(old_release)
    assert old_release.status == "superseded"
    assert old_release.source_manifest == original_manifest
    assert old_release.release_hash == original_hash
    assert manifest_hash(old_release.source_manifest) == original_hash
    assert release_record_ids(db, old_estimate, "technical") == {old_variant.id}
    assert new_release.source_manifest["previous_release"] == {
        "id": old_release.id,
        "hash": original_hash,
        "policy": GOVERNED_TECHNICAL_RELEASE_POLICY_V2,
    }
    assert new_release.source_manifest["carried_forward_v2_record_ids"] == [
        old_variant.id
    ]
    records = {item["id"]: item for item in new_release.source_manifest["records"]}
    assert records[old_variant.id]["record_binding_policy"] == (
        GOVERNED_TECHNICAL_RELEASE_POLICY_V2
    )
    assert records[new_variant.id]["record_binding_policy"] == (
        GOVERNED_TECHNICAL_RELEASE_POLICY_V3
    )


def test_v3_release_binds_exact_review_receipt_and_sorted_typed_lineage(db, tmp_path):
    requester = _user(db, "graph.requester@example.test", "technical_reviewer")
    source_reviewer = _user(db, "graph.source@example.test", "technical_reviewer")
    technical_reviewer = _user(db, "graph.technical@example.test", "technical_reviewer")
    publisher = _user(db, "graph.publisher@example.test", "technical_release_manager")
    first_target = _reviewed_document(
        db,
        tmp_path,
        requester,
        source_reviewer,
        document_id="GRAPH-TARGET-A",
    )
    second_target = _reviewed_document(
        db,
        tmp_path,
        requester,
        source_reviewer,
        document_id="GRAPH-TARGET-B",
    )
    root = _document(db, tmp_path, document_id="GRAPH-ROOT", uploaded_by=requester)
    technical_document_relationship_create(
        root.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="revision_of",
        related_document_id=second_target.document_id,
        reason="Bind the earlier revision.",
    )
    technical_document_relationship_create(
        root.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=first_target.document_id,
        reason="Bind the supporting assessment basis.",
    )
    root_review = _submit_and_approve_document(db, root, requester, source_reviewer)
    variant = _candidate(db, root, variant_id="GRAPH-VARIANT")
    _submit_and_approve(db, variant, requester, technical_reviewer)

    release = _publish(db, publisher, version="TAR-v3-graph")

    record = release.source_manifest["records"][0]
    source_binding = record["source_binding"]
    assert source_binding["binding_policy"] == GOVERNED_TECHNICAL_RELEASE_POLICY_V3
    assert source_binding["source_review"]["id"] == root_review.id
    assert source_binding["source_review"]["snapshot_hash"] == root_review.snapshot_hash
    assert source_binding["outgoing_relationships"] == technical_document_review_snapshot(
        db,
        root.id,
    )["outgoing_relationships"]
    lineage_order = [
        (item["relationship_type"], item["related_document_id"], item["id"])
        for item in source_binding["outgoing_relationships"]
    ]
    assert lineage_order == sorted(lineage_order)
    assert manifest_hash(release.source_manifest) == release.release_hash

    root.extraction_status = "complete"
    db.commit()
    assert active_release(db, "technical") is release


def test_nested_legacy_source_without_current_receipt_is_rejected(db, tmp_path):
    requester = _user(db, "legacy.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "legacy.reviewer@example.test", "technical_reviewer")
    legacy_target = _document(
        db,
        tmp_path,
        document_id="LEGACY-NESTED-TARGET",
        status="approved",
        approved_by=reviewer,
    )
    source = _document(db, tmp_path, document_id="CURRENT-GRAPH-SOURCE")
    technical_document_relationship_create(
        source.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=legacy_target.document_id,
        reason="Attempt to rely on a marker-less historical approval.",
    )

    response = technical_document_submit_review(
        source.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )

    assert "RELATED_SOURCE_REVIEW_INVALID" in response.headers["location"]
    db.refresh(source)
    assert source.status == "draft"


def test_legacy_document_supersession_requires_exact_typed_relationship(db, tmp_path):
    requester = _user(db, "supersedes.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "supersedes.reviewer@example.test", "technical_reviewer")
    predecessor = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="SUPERSEDED-SOURCE",
    )
    successor = _document(
        db,
        tmp_path,
        document_id="SUCCESSOR-SOURCE",
        uploaded_by=requester,
    )
    successor.supersedes_document_id = predecessor.id
    db.commit()

    rejected = technical_document_submit_review(
        successor.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
    )
    assert "RELATED_SOURCE_REVIEW_INVALID" in rejected.headers["location"]

    technical_document_relationship_create(
        successor.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="revision_of",
        related_document_id=predecessor.document_id,
        reason="The retained source identifies the exact prior revision.",
    )
    _submit_and_approve_document(db, successor, requester, reviewer)
    assert successor.status == "approved"


@pytest.mark.parametrize("publisher_reviewed", ["root", "nested"])
def test_v3_publisher_cannot_be_any_source_graph_reviewer(
    db,
    tmp_path,
    publisher_reviewed,
):
    requester = _user(db, "independence.requester@example.test", "technical_reviewer")
    other_source_reviewer = _user(
        db,
        "independence.source@example.test",
        "technical_reviewer",
    )
    technical_reviewer = _user(
        db,
        "independence.technical@example.test",
        "technical_reviewer",
    )
    publisher = _user(db, "independence.publisher@example.test", "administrator")
    nested_reviewer = publisher if publisher_reviewed == "nested" else other_source_reviewer
    root_reviewer = publisher if publisher_reviewed == "root" else other_source_reviewer
    target = _reviewed_document(
        db,
        tmp_path,
        requester,
        nested_reviewer,
        document_id=f"INDEPENDENCE-TARGET-{publisher_reviewed}",
    )
    root = _document(
        db,
        tmp_path,
        document_id=f"INDEPENDENCE-ROOT-{publisher_reviewed}",
        uploaded_by=requester,
    )
    technical_document_relationship_create(
        root.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        relationship_type="assessment_of",
        related_document_id=target.document_id,
        reason="Bind the target into the source authority graph.",
    )
    _submit_and_approve_document(db, root, requester, root_reviewer)
    variant = _candidate(db, root, variant_id=f"INDEPENDENCE-{publisher_reviewed}")
    _submit_and_approve(db, variant, requester, technical_reviewer)

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version=f"TAR-source-independence-{publisher_reviewed}",
    )

    assert "TECHNICAL_RELEASE_INDEPENDENT_SOURCE_PUBLISHER_REQUIRED" in (
        response.headers["location"]
    )
    assert active_release(db, "technical") is None


def test_stale_predecessor_token_aborts_without_mutating_release_state(db, tmp_path):
    requester = _user(db, "stale.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "stale.reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "stale.publisher@example.test", "technical_release_manager")
    first_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="STALE-FIRST",
    )
    first = _candidate(db, first_document, variant_id="STALE-FIRST")
    _submit_and_approve(db, first, requester, reviewer)
    first_release = _publish(db, publisher, version="TAR-stale-first")
    second_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="STALE-SECOND",
    )
    second = _candidate(db, second_document, variant_id="STALE-SECOND")
    _submit_and_approve(db, second, requester, reviewer)

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-stale-attempt",
        expected_previous_release_id="",
    )

    assert "TECHNICAL_RELEASE_PREDECESSOR_CHANGED_RETRY" in response.headers["location"]
    assert not db.in_transaction()
    db.refresh(first_release)
    db.refresh(second)
    assert first_release.status == "active"
    assert first_release.active_publication_slot == "technical"
    assert second.status == "approved"


def test_publication_uses_only_the_fixed_locked_candidate_set(db, tmp_path, monkeypatch):
    requester = _user(db, "fixed.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "fixed.reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "fixed.publisher@example.test", "technical_release_manager")
    first_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="FIXED-FIRST",
    )
    second_document = _reviewed_document(
        db,
        tmp_path,
        requester,
        reviewer,
        document_id="FIXED-SECOND",
    )
    first = _candidate(db, first_document, variant_id="FIXED-FIRST")
    second = _candidate(db, second_document, variant_id="FIXED-SECOND")
    _submit_and_approve(db, first, requester, reviewer)
    _submit_and_approve(db, second, requester, reviewer)
    real_lock = release_admin._lock_technical_publication_state

    def fixed_lock(*args, **kwargs):
        locked = real_lock(*args, **kwargs)
        return [variant for variant in locked if variant.id == first.id]

    monkeypatch.setattr(release_admin, "_lock_technical_publication_state", fixed_lock)
    release = _publish(db, publisher, version="TAR-fixed-set")

    assert {item["id"] for item in release.source_manifest["records"]} == {first.id}
    db.refresh(second)
    assert second.status == "approved"


def test_candidate_compare_and_set_prevents_stale_state_resurrection(
    db,
    tmp_path,
    monkeypatch,
):
    requester = _user(db, "cas.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "cas.reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "cas.publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document, variant_id="CAS-CANDIDATE")
    _submit_and_approve(db, variant, requester, reviewer)
    real_snapshot = release_admin._technical_release_snapshot

    def retire_after_snapshot(*args, **kwargs):
        snapshot = real_snapshot(*args, **kwargs)
        db.execute(
            update(TechnicalVariant)
            .where(TechnicalVariant.id == variant.id)
            .values(status="retired")
            .execution_options(synchronize_session=False)
        )
        db.flush()
        return snapshot

    monkeypatch.setattr(release_admin, "_technical_release_snapshot", retire_after_snapshot)
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-cas-attempt",
    )

    assert "TECHNICAL_RELEASE_CANDIDATE_STATE_CHANGED_RETRY" in response.headers["location"]
    db.refresh(variant)
    assert variant.status == "approved"
    assert active_release(db, "technical") is None


def test_publication_lock_revalidates_publisher_authority(db):
    publisher = _user(db, "revoked.publisher@example.test", "technical_release_manager")
    publisher.is_active = False
    db.commit()

    with pytest.raises(ValueError, match="PUBLISHER_AUTHORITY_CHANGED"):
        release_admin._lock_technical_publication_state(db, publisher_id=publisher.id)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("unknown_policy", "governance policy is unknown"),
        ("partition_overlap", "record partitions are inconsistent"),
        ("timestamp", "timestamp binding is invalid"),
        ("v2_laundering", "binding-policy partitions are inconsistent"),
    ],
)
def test_v3_manifest_tampering_fails_closed(db, tmp_path, mutation, expected_error):
    requester = _user(db, f"{mutation}.requester@example.test", "technical_reviewer")
    reviewer = _user(db, f"{mutation}.reviewer@example.test", "technical_reviewer")
    publisher = _user(
        db,
        f"{mutation}.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    variant = _candidate(db, document, variant_id=f"TAMPER-{mutation}")
    _submit_and_approve(db, variant, requester, reviewer)
    release = _publish(db, publisher, version=f"TAR-{mutation}")
    manifest = copy.deepcopy(release.source_manifest)
    if mutation == "unknown_policy":
        manifest["governance_policy"] = "technical-authority-registry-v999"
    elif mutation == "partition_overlap":
        manifest["retired_record_ids"] = [variant.id]
    elif mutation == "timestamp":
        manifest["created_at"] = "2000-01-01T00:00:00+00:00"
    else:
        manifest["records"][0]["record_binding_policy"] = (
            GOVERNED_TECHNICAL_RELEASE_POLICY_V2
        )
        manifest["records"][0].pop("unpublished_supersedes_binding")
    release.source_manifest = manifest
    release.release_hash = manifest_hash(manifest)
    db.commit()

    with pytest.raises(ReleaseScopeError, match=expected_error):
        release_scope.validate_release(
            db,
            release,
            "technical",
            allowed_statuses={"active"},
        )


def test_unpublished_same_key_intake_ancestor_is_bound_and_revalidated(db, tmp_path):
    requester = _user(db, "ancestor.requester@example.test", "technical_reviewer")
    reviewer = _user(db, "ancestor.reviewer@example.test", "technical_reviewer")
    publisher = _user(db, "ancestor.publisher@example.test", "technical_release_manager")
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    ancestor = _candidate(db, document, variant_id="ANCESTOR-ROOT")
    revision = _candidate(
        db,
        document,
        variant_id="ANCESTOR-ROOT-QFREV01",
        supersedes_id=ancestor.id,
        original_variant_id="ANCESTOR-ROOT",
    )
    revision.service_material = "copper"
    db.commit()
    _submit_and_approve(db, revision, requester, reviewer)

    release = _publish(db, publisher, version="TAR-unpublished-ancestor")
    binding = release.source_manifest["records"][0]["unpublished_supersedes_binding"]
    assert binding == {
        "id": ancestor.id,
        "key": "ANCESTOR-ROOT",
        "record_hash": technical_variant_snapshot_hash(ancestor),
    }
    carried_release = _publish(db, publisher, version="TAR-unpublished-ancestor-carry")
    assert carried_release.source_manifest["carried_record_ids"] == [revision.id]
    assert carried_release.source_manifest["records"][0][
        "unpublished_supersedes_binding"
    ] == binding

    ancestor.service_material = "plastic"
    db.commit()
    assert active_release(db, "technical") is None


@pytest.mark.parametrize("replacement_case", ["missing_exact", "different_key"])
def test_v3_replacement_rejects_published_predecessor_laundering(
    db,
    tmp_path,
    replacement_case,
):
    requester = _user(db, f"{replacement_case}.requester@example.test", "technical_reviewer")
    reviewer = _user(db, f"{replacement_case}.reviewer@example.test", "technical_reviewer")
    publisher = _user(
        db,
        f"{replacement_case}.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, reviewer)
    first = _candidate(db, document, variant_id="PUBLISHED-ROOT")
    _submit_and_approve(db, first, requester, reviewer)
    first_release = _publish(db, publisher, version=f"TAR-{replacement_case}-first")
    if replacement_case == "missing_exact":
        candidate = _candidate(
            db,
            document,
            variant_id="PUBLISHED-ROOT-QFREV01",
            original_variant_id="PUBLISHED-ROOT",
        )
        expected = "TECHNICAL_RELEASE_REPLACEMENT_LINEAGE_MISMATCH"
    else:
        candidate = _candidate(
            db,
            document,
            variant_id="DIFFERENT-ROOT",
            supersedes_id=first.id,
        )
        expected = "TECHNICAL_RELEASE_REPLACEMENT_KEY_MISMATCH"
    candidate.service_material = "copper"
    db.commit()
    _submit_and_approve(db, candidate, requester, reviewer)

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version=f"TAR-{replacement_case}-attempt",
        expected_previous_release_id=first_release.id,
    )

    assert expected in response.headers["location"]
    db.refresh(first_release)
    assert first_release.status == "active"


# Governed active-record retirement regressions.


def test_retirement_requires_independent_reviewer_and_publisher(db, tmp_path):
    admin_requester = _user(db, "retire.admin@example.test", "administrator")
    source_requester = _user(
        db,
        "retire.source.request@example.test",
        "technical_reviewer",
    )
    source_reviewer = _user(
        db,
        "retire.source.review@example.test",
        "technical_reviewer",
    )
    retirement_reviewer = _user(
        db,
        "retire.review@example.test",
        "administrator",
    )
    first_publisher = _user(
        db,
        "retire.first.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(
        db,
        tmp_path,
        source_requester,
        source_reviewer,
    )
    variant = _candidate(db, document, variant_id="RETIRE-INDEPENDENCE")
    _submit_and_approve(db, variant, source_requester, source_reviewer)
    predecessor = _publish(db, first_publisher, version="TAR-retirement-independence")

    request_technical_retirement(
        variant.id,
        _request(admin_requester),
        db,
        csrf_token="csrf-token",
        reason="Administrator requests a governed withdrawal",
    )
    response = approve_technical_retirement(
        variant.id,
        _request(admin_requester),
        db,
        csrf_token="csrf-token",
        reason="Attempt self approval",
    )
    assert "INDEPENDENT_REVIEWER_REQUIRED" in response.headers["location"]
    approval = latest_technical_retirement(db, variant.id)
    assert approval is not None and approval.status == "pending"

    approve_technical_retirement(
        variant.id,
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Different reviewer approves withdrawal",
    )
    response = publish_release(
        _request(admin_requester),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-self-publish-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "INDEPENDENT_PUBLISHER_REQUIRED" in response.headers["location"]
    response = publish_release(
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-reviewer-publish-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "INDEPENDENT_PUBLISHER_REQUIRED" in response.headers["location"]
    db.refresh(predecessor)
    db.refresh(variant)
    assert predecessor.status == "active"
    assert variant.status == "active"


def test_retirement_and_same_key_replacement_cannot_share_a_release(db, tmp_path):
    requester = _user(db, "collision.requester@example.test", "technical_reviewer")
    source_reviewer = _user(db, "collision.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "collision.retire@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "collision.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    original = _candidate(db, document, variant_id="RETIRE-COLLISION")
    _submit_and_approve(db, original, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-collision-source")
    _request_and_approve_retirement(
        db,
        original,
        requester,
        retirement_reviewer,
    )
    replacement = _candidate(
        db,
        document,
        variant_id="RETIRE-COLLISION-QFREV01",
        supersedes_id=original.id,
        original_variant_id="RETIRE-COLLISION",
    )
    replacement.service_material = "copper"
    db.commit()
    _submit_and_approve(db, replacement, requester, source_reviewer)

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-collision-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "RETIREMENT_REPLACEMENT_CONFLICT" in response.headers["location"]
    db.refresh(predecessor)
    db.refresh(original)
    db.refresh(replacement)
    assert predecessor.status == "active"
    assert original.status == "active"
    assert replacement.status == "approved"


def test_governed_retirement_is_inactive_until_release_and_then_fails_old_pin(
    db,
    tmp_path,
):
    requester = _user(db, "retire.requester@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    first = _candidate(db, document, variant_id="RETIRE-A", system_id="SYS-A")
    second = _candidate(db, document, variant_id="RETIRE-B", system_id="SYS-B")
    first.expiry_date = date.today() + timedelta(days=365)
    db.commit()
    _submit_and_approve(db, first, requester, source_reviewer)
    _submit_and_approve(db, second, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-source")
    predecessor_manifest = copy.deepcopy(predecessor.source_manifest)
    predecessor_hash = predecessor.release_hash

    response = request_technical_retirement(
        first.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Withdraw RETIRE-A after reviewed technical notice",
    )
    assert "submitted+for+independent+review" in response.headers["location"]
    db.refresh(first)
    assert first.status == "active"
    assert active_release_record_ids(db, "technical") == {first.id, second.id}

    approval = latest_technical_retirement(db, first.id)
    assert approval is not None
    context, decision_reason = technical_retirement_decision(approval)
    assert approval.approval_type == TECHNICAL_RETIREMENT_APPROVAL_TYPE
    assert approval.status == "pending"
    assert context["predecessor_release_id"] == predecessor.id
    assert context["predecessor_release_hash"] == predecessor_hash
    assert decision_reason is None

    response = approve_technical_retirement(
        first.id,
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Independent evidence review supports withdrawal",
    )
    assert "approved+for+the+next+Technical" in response.headers["location"]
    db.refresh(first)
    assert first.status == "active"
    assert active_release_record_ids(db, "technical") == {first.id, second.id}

    successor = _publish(db, publisher, version="TAR-retirement-successor")
    db.refresh(first)
    db.refresh(second)
    db.refresh(predecessor)
    assert first.status == "retired"
    assert first.expiry_date == date.today() + timedelta(days=365)
    assert second.status == "active"
    assert predecessor.source_manifest == predecessor_manifest
    assert predecessor.release_hash == predecessor_hash
    assert successor.source_manifest["retired_record_ids"] == [first.id]
    assert successor.source_manifest["carried_record_ids"] == [second.id]
    assert len(successor.source_manifest["retirement_bindings"]) == 1
    created_at = successor.created_at
    approved_at = successor.approved_at
    assert approved_at is not None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    if approved_at.tzinfo is None:
        approved_at = approved_at.replace(tzinfo=UTC)
    assert successor.source_manifest["created_at"] == created_at.astimezone(UTC).isoformat()
    assert successor.source_manifest["created_at"] == approved_at.astimezone(UTC).isoformat()
    assert active_release_record_ids(db, "technical") == {second.id}
    assert [item.variant.id for item in search_variants(db)] == [second.id]
    old_estimate = SimpleNamespace(technical_release_id=predecessor.id)
    with pytest.raises(ReleaseScopeError, match="invalid lifecycle state"):
        release_record_ids(db, old_estimate, "technical")


def test_last_v2_member_can_be_retired_into_explicit_empty_v3_registry(db, tmp_path):
    requester = _user(db, "v2.retire.requester@example.test", "technical_reviewer")
    source_reviewer = _user(
        db,
        "v2.retire.source@example.test",
        "technical_reviewer",
    )
    retirement_reviewer = _user(
        db,
        "v2.retire.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "v2.retire.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="V2-RETIRE-ONLY")
    predecessor = _historical_v2_release(
        db,
        variant,
        requester,
        source_reviewer,
        publisher,
        version="TAR-v2-retirement-source",
    )
    predecessor_bytes = json.dumps(
        predecessor.source_manifest,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    predecessor_hash = predecessor.release_hash

    _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    successor = _publish(db, publisher, version="TAR-v3-empty-authority")

    db.refresh(predecessor)
    db.refresh(variant)
    assert variant.status == "retired"
    assert predecessor.release_hash == predecessor_hash
    assert json.dumps(
        predecessor.source_manifest,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode() == predecessor_bytes
    assert successor.source_manifest["records"] == []
    assert successor.source_manifest["record_count"] == 0
    assert successor.source_manifest["retired_record_ids"] == [variant.id]
    assert active_release(db, "technical") is successor
    assert active_release_record_ids(db, "technical") == set()
    assert search_variants(db) == []
    old_estimate = SimpleNamespace(technical_release_id=predecessor.id)
    with pytest.raises(ReleaseScopeError, match="invalid lifecycle state"):
        release_record_ids(db, old_estimate, "technical")


def test_pending_retirement_is_carried_and_becomes_stale_after_successor(
    db,
    tmp_path,
):
    requester = _user(db, "pending.retire.request@example.test", "technical_reviewer")
    source_reviewer = _user(
        db,
        "pending.retire.source@example.test",
        "technical_reviewer",
    )
    retirement_reviewer = _user(
        db,
        "pending.retire.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "pending.retire.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-PENDING")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-pending-source")

    request_technical_retirement(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="Request remains pending during an unrelated registry publication",
    )
    successor = _publish(db, publisher, version="TAR-retirement-pending-carry")
    db.refresh(variant)
    assert variant.status == "active"
    assert successor.source_manifest["carried_record_ids"] == [variant.id]
    assert successor.source_manifest["retired_record_ids"] == []
    assert successor.source_manifest["retirement_bindings"] == []

    response = approve_technical_retirement(
        variant.id,
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Attempt to approve the predecessor-bound stale request",
    )
    assert "TECHNICAL_RETIREMENT_REQUEST_STALE" in response.headers["location"]
    approval = latest_technical_retirement(db, variant.id)
    assert approval is not None and approval.status == "pending"
    db.refresh(variant)
    assert variant.status == "active"

    response = reject_technical_retirement(
        variant.id,
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Close the stale request without changing runtime authority",
    )
    assert "Retirement+request+rejected" in response.headers["location"]
    db.refresh(approval)
    db.refresh(variant)
    assert approval.status == "rejected"
    assert variant.status == "active"
    carried_again = _publish(db, publisher, version="TAR-retirement-rejected-carry")
    assert carried_again.source_manifest["carried_record_ids"] == [variant.id]
    assert carried_again.source_manifest["retired_record_ids"] == []
    assert active_release_record_ids(db, "technical") == {variant.id}
    assert predecessor.status == "superseded"


def test_stale_pending_retirement_can_close_after_governed_replacement(db, tmp_path):
    requester = _user(db, "retire.replace.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.replace.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.replace.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.replace.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    original = _candidate(db, document, variant_id="RETIRE-REPLACED")
    _submit_and_approve(db, original, requester, source_reviewer)
    _publish(db, publisher, version="TAR-retirement-replaced-source")
    request_technical_retirement(
        original.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="This request will become stale after exact replacement",
    )
    approval = latest_technical_retirement(db, original.id)
    assert approval is not None and approval.status == "pending"

    replacement = _candidate(
        db,
        document,
        variant_id="RETIRE-REPLACED-QFREV01",
        supersedes_id=original.id,
        original_variant_id="RETIRE-REPLACED",
    )
    replacement.service_material = "replacement material"
    db.commit()
    _submit_and_approve(db, replacement, requester, source_reviewer)
    _publish(db, publisher, version="TAR-retirement-replaced-successor")
    db.refresh(original)
    db.refresh(replacement)
    assert original.status == "superseded"
    assert replacement.status == "active"

    response = reject_technical_retirement(
        original.id,
        _request(retirement_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Close the stale request after governed replacement",
    )
    assert "Retirement+request+rejected" in response.headers["location"]
    db.refresh(approval)
    db.refresh(original)
    db.refresh(replacement)
    assert approval.status == "rejected"
    assert original.status == "superseded"
    assert replacement.status == "active"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing", "retirement binding partition is invalid"),
        ("duplicate", "retirement binding partition is invalid"),
        ("extra", "retirement binding partition is invalid"),
        ("receipt", "retirement receipt is invalid"),
    ],
)
def test_retirement_manifest_tampering_fails_closed(
    db,
    tmp_path,
    mutation,
    expected_error,
):
    requester = _user(
        db,
        f"retirement.{mutation}.request@example.test",
        "technical_reviewer",
    )
    source_reviewer = _user(
        db,
        f"retirement.{mutation}.source@example.test",
        "technical_reviewer",
    )
    retirement_reviewer = _user(
        db,
        f"retirement.{mutation}.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        f"retirement.{mutation}.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(
        db,
        document,
        variant_id=f"RETIRE-TAMPER-{mutation.upper()}",
    )
    _submit_and_approve(db, variant, requester, source_reviewer)
    _publish(db, publisher, version=f"TAR-retirement-{mutation}-source")
    _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    release = _publish(db, publisher, version=f"TAR-retirement-{mutation}-active")

    manifest = copy.deepcopy(release.source_manifest)
    binding = manifest["retirement_bindings"][0]
    if mutation == "missing":
        manifest["retirement_bindings"] = []
    elif mutation == "duplicate":
        manifest["retirement_bindings"].append(copy.deepcopy(binding))
    elif mutation == "extra":
        extra = copy.deepcopy(binding)
        extra["request_context"]["predecessor_record_id"] = "not-a-member"
        manifest["retirement_bindings"].append(extra)
    else:
        binding["decision_reason"] = "Tampered after publication"
    release.source_manifest = manifest
    release.release_hash = manifest_hash(manifest)
    db.commit()

    with pytest.raises(ReleaseScopeError, match=expected_error):
        release_scope.validate_release(
            db,
            release,
            "technical",
            allowed_statuses={"active"},
        )


def test_retirement_compare_and_set_failure_rolls_back_all_publication_state(
    db,
    tmp_path,
    monkeypatch,
):
    requester = _user(db, "retire.cas.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.cas.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.cas.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.cas.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-CAS")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-cas-source")
    approval = _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    audit_count_before = db.scalar(select(func.count()).select_from(AuditEvent))
    real_snapshot = release_admin._technical_release_snapshot

    def change_target_after_snapshot(*args, **kwargs):
        snapshot = real_snapshot(*args, **kwargs)
        variant.status = "superseded"
        db.flush()
        return snapshot

    monkeypatch.setattr(
        release_admin,
        "_technical_release_snapshot",
        change_target_after_snapshot,
    )
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-cas-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "TECHNICAL_RELEASE_RETIRED_STATE_CHANGED_RETRY" in response.headers["location"]

    db.expire_all()
    restored_predecessor = db.get(LibraryRelease, predecessor.id)
    restored_variant = db.get(TechnicalVariant, variant.id)
    restored_approval = db.get(Approval, approval.id)
    assert restored_predecessor is not None
    assert restored_predecessor.status == "active"
    assert restored_predecessor.active_publication_slot == "technical"
    assert restored_variant is not None and restored_variant.status == "active"
    assert restored_approval is not None and restored_approval.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-retirement-cas-attempt")
        )
        == 0
    )
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count_before


def test_retired_variant_drift_invalidates_active_retirement_receipt(db, tmp_path):
    requester = _user(db, "retire.drift.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.drift.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.drift.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.drift.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-DRIFT")
    _submit_and_approve(db, variant, requester, source_reviewer)
    _publish(db, publisher, version="TAR-retirement-drift-source")
    _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    successor = _publish(db, publisher, version="TAR-retirement-drift-active")

    variant.service_material = "tampered after governed retirement"
    db.commit()
    with pytest.raises(ReleaseScopeError, match="retirement receipt is invalid"):
        release_scope.validate_release(
            db,
            successor,
            "technical",
            allowed_statuses={"active"},
        )
    assert active_release(db, "technical") is None


def test_retirement_publisher_cannot_be_the_retired_source_reviewer(db, tmp_path):
    requester = _user(
        db,
        "retire.source.publisher.request@example.test",
        "technical_reviewer",
    )
    source_reviewer = _user(
        db,
        "retire.source.publisher@example.test",
        "administrator",
    )
    retirement_reviewer = _user(
        db,
        "retire.source.publisher.decision@example.test",
        "technical_reviewer",
    )
    first_publisher = _user(
        db,
        "retire.source.publisher.first@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-SOURCE-PUBLISHER")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(
        db,
        first_publisher,
        version="TAR-retirement-source-publisher-source",
    )
    _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )

    response = publish_release(
        _request(source_reviewer),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-source-publisher-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "INDEPENDENT_SOURCE_PUBLISHER_REQUIRED" in response.headers["location"]
    db.refresh(predecessor)
    db.refresh(variant)
    assert predecessor.status == "active"
    assert variant.status == "active"


def test_duplicate_current_retirement_receipts_block_request_and_publication(
    db,
    tmp_path,
):
    requester = _user(db, "retire.duplicate.request@example.test", "technical_reviewer")
    source_reviewer = _user(
        db,
        "retire.duplicate.source@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.duplicate.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-DUPLICATE")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-duplicate-source")
    request_technical_retirement(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="First exact-current request",
    )
    original = latest_technical_retirement(db, variant.id)
    assert original is not None
    db.add(
        Approval(
            entity_type=original.entity_type,
            entity_id=original.entity_id,
            approval_type=original.approval_type,
            status=original.status,
            requested_by_id=original.requested_by_id,
            decision_reason=original.decision_reason,
            snapshot_hash=original.snapshot_hash,
        )
    )
    db.commit()

    preview = release_admin._technical_retirement_preview(db, predecessor)
    assert len(preview) == 1
    assert preview[0]["valid"] is False
    assert preview[0]["error"] == "TECHNICAL_RETIREMENT_DUPLICATE_CURRENT_RECEIPTS"
    detail_response = technical_admin.technical_variant_detail(
        variant.id,
        _request(requester),
        db,
    )
    assert "Invalid retirement receipt" in detail_response.body.decode("utf-8")

    response = reject_technical_retirement(
        variant.id,
        _request(source_reviewer),
        db,
        csrf_token="csrf-token",
        reason="Rejecting one duplicate must not expose the other",
    )
    assert "DUPLICATE_CURRENT_RECEIPTS" in response.headers["location"]

    response = request_technical_retirement(
        variant.id,
        _request(requester),
        db,
        csrf_token="csrf-token",
        reason="A duplicate must not be accepted",
    )
    assert "DUPLICATE_CURRENT_RECEIPTS" in response.headers["location"]
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-duplicate-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "DUPLICATE_CURRENT_RECEIPTS" in response.headers["location"]
    db.refresh(predecessor)
    db.refresh(variant)
    assert predecessor.status == "active"
    assert variant.status == "active"


def test_whitespace_only_retirement_decision_receipt_fails_closed(db, tmp_path):
    requester = _user(db, "retire.reason.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.reason.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.reason.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.reason.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-REASON")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-reason-source")
    approval = _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    decision = json.loads(approval.decision_reason or "")
    decision["decision_reason"] = "   "
    approval.decision_reason = json.dumps(
        decision,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    db.commit()

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-reason-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "TECHNICAL_RETIREMENT_APPROVAL_INVALID" in response.headers["location"]
    db.refresh(predecessor)
    db.refresh(variant)
    assert predecessor.status == "active"
    assert variant.status == "active"


def test_empty_registry_requires_retirement_but_can_accept_new_authority(db, tmp_path):
    requester = _user(db, "empty.registry.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "empty.registry.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "empty.registry.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "empty.registry.publisher@example.test",
        "technical_release_manager",
    )
    db.commit()
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-empty-first-attempt",
    )
    assert "No+eligible+records" in response.headers["location"]
    assert active_release(db, "technical") is None

    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    original = _candidate(db, document, variant_id="EMPTY-REGISTRY-ROOT")
    _submit_and_approve(db, original, requester, source_reviewer)
    _publish(db, publisher, version="TAR-empty-v3-source")
    _request_and_approve_retirement(
        db,
        original,
        requester,
        retirement_reviewer,
    )
    empty_release = _publish(db, publisher, version="TAR-empty-v3-governed")
    assert empty_release.source_manifest["records"] == []
    assert active_release_record_ids(db, "technical") == set()

    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-empty-noop-attempt",
        expected_previous_release_id=empty_release.id,
    )
    assert "No+eligible+records" in response.headers["location"]
    db.refresh(empty_release)
    assert empty_release.status == "active"
    assert empty_release.active_publication_slot == "technical"

    new_variant = _candidate(db, document, variant_id="EMPTY-REGISTRY-NEW")
    _submit_and_approve(db, new_variant, requester, source_reviewer)
    restored = _publish(db, publisher, version="TAR-empty-restored")
    assert restored.source_manifest["activated_candidate_ids"] == [new_variant.id]
    assert restored.source_manifest["records"][0]["id"] == new_variant.id
    assert active_release_record_ids(db, "technical") == {new_variant.id}
    db.refresh(original)
    assert original.status == "retired"


def test_reordered_retirement_bindings_fail_closed(db, tmp_path):
    requester = _user(db, "retire.order.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.order.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.order.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.order.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    first = _candidate(db, document, variant_id="RETIRE-ORDER-A", system_id="ORDER-A")
    second = _candidate(db, document, variant_id="RETIRE-ORDER-B", system_id="ORDER-B")
    _submit_and_approve(db, first, requester, source_reviewer)
    _submit_and_approve(db, second, requester, source_reviewer)
    _publish(db, publisher, version="TAR-retirement-order-source")
    _request_and_approve_retirement(db, first, requester, retirement_reviewer)
    _request_and_approve_retirement(db, second, requester, retirement_reviewer)
    release = _publish(db, publisher, version="TAR-retirement-order-active")
    manifest = copy.deepcopy(release.source_manifest)
    assert len(manifest["retirement_bindings"]) == 2
    manifest["retirement_bindings"].reverse()
    release.source_manifest = manifest
    release.release_hash = manifest_hash(manifest)
    db.commit()

    with pytest.raises(
        ReleaseScopeError,
        match="retirement binding partition is invalid",
    ):
        release_scope.validate_release(
            db,
            release,
            "technical",
            allowed_statuses={"active"},
        )


def test_final_retirement_validation_failure_restores_predecessor_and_record(
    db,
    tmp_path,
    monkeypatch,
):
    requester = _user(db, "retire.final.request@example.test", "technical_reviewer")
    source_reviewer = _user(db, "retire.final.source@example.test", "technical_reviewer")
    retirement_reviewer = _user(
        db,
        "retire.final.decision@example.test",
        "technical_reviewer",
    )
    publisher = _user(
        db,
        "retire.final.publisher@example.test",
        "technical_release_manager",
    )
    document = _reviewed_document(db, tmp_path, requester, source_reviewer)
    variant = _candidate(db, document, variant_id="RETIRE-FINAL")
    _submit_and_approve(db, variant, requester, source_reviewer)
    predecessor = _publish(db, publisher, version="TAR-retirement-final-source")
    approval = _request_and_approve_retirement(
        db,
        variant,
        requester,
        retirement_reviewer,
    )
    audit_count_before = db.scalar(select(func.count()).select_from(AuditEvent))
    real_validate = release_admin.validate_release

    def fail_new_release(database, release, *args, **kwargs):
        if release.version == "TAR-retirement-final-attempt":
            raise ReleaseScopeError("injected retirement final-validation failure")
        return real_validate(database, release, *args, **kwargs)

    monkeypatch.setattr(release_admin, "validate_release", fail_new_release)
    response = publish_release(
        _request(publisher),
        db,
        csrf_token="csrf-token",
        release_type="technical",
        version="TAR-retirement-final-attempt",
        expected_previous_release_id=predecessor.id,
    )
    assert "TECHNICAL_RELEASE_FINAL_VALIDATION_FAILED" in response.headers["location"]

    db.expire_all()
    restored_predecessor = db.get(LibraryRelease, predecessor.id)
    restored_variant = db.get(TechnicalVariant, variant.id)
    restored_approval = db.get(Approval, approval.id)
    assert restored_predecessor is not None
    assert restored_predecessor.status == "active"
    assert restored_predecessor.active_publication_slot == "technical"
    assert restored_variant is not None and restored_variant.status == "active"
    assert restored_approval is not None and restored_approval.status == "approved"
    assert (
        db.scalar(
            select(func.count())
            .select_from(LibraryRelease)
            .where(LibraryRelease.version == "TAR-retirement-final-attempt")
        )
        == 0
    )
    assert db.scalar(select(func.count()).select_from(AuditEvent)) == audit_count_before
