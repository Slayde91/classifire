# ruff: noqa: S106
from __future__ import annotations

import hashlib
from collections.abc import Iterator, Mapping
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO

import pytest
from fastapi import UploadFile
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.datastructures import Headers

from classifire import models, physical_models  # noqa: F401
from classifire.config import Settings
from classifire.db import Base
from classifire.models import (
    AuditEvent,
    StoredFile,
    TechnicalDocument,
    TechnicalIntakeBatch,
    TechnicalIntakeBatchItem,
    User,
)
from classifire.services import storage as storage_service
from classifire.services import technical_intake as intake_service
from classifire.services.malware_scanning import (
    CLEAN_VERDICT,
    MalwareScanError,
    MalwareScanResult,
)
from classifire.services.technical_intake import (
    TechnicalIntakeError,
    TechnicalIntakeResult,
    create_technical_document_draft,
)
from classifire.services.technical_intake_batch import (
    TECHNICAL_INTAKE_CLAIM_TTL,
    TechnicalIntakeBatchClaim,
    TechnicalIntakeBatchCreateResult,
    TechnicalIntakeBatchError,
    canonical_json_sha256,
    claim_technical_intake_batch_item,
    create_technical_intake_batch,
    get_owned_technical_intake_batch,
    serialize_technical_intake_batch,
)

_REQUEST_A = "11111111-1111-4111-8111-111111111111"
_REQUEST_B = "11111111-1111-4111-8111-111111111112"
_ITEM_A = "22222222-2222-4222-8222-222222222221"
_ITEM_B = "22222222-2222-4222-8222-222222222222"


class _ContentScanner:
    def __init__(self, *, transient_failures: int = 0) -> None:
        self.calls: list[bytes] = []
        self.transient_failures = transient_failures

    def scan_stream(self, stream: BinaryIO) -> MalwareScanResult:
        payload = stream.read()
        self.calls.append(payload)
        if self.transient_failures:
            self.transient_failures -= 1
            raise OSError("scanner endpoint details must not escape")
        return MalwareScanResult(
            CLEAN_VERDICT,
            hashlib.sha256(payload).hexdigest(),
            len(payload),
        )


@pytest.fixture
def db() -> Iterator[Session]:
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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        storage_root=tmp_path / "storage",
        clamav_host="scanner.internal",
        max_upload_mb=2,
    )


def _install_scanner(
    monkeypatch: pytest.MonkeyPatch,
    scanner: _ContentScanner,
) -> None:
    monkeypatch.setattr(
        storage_service,
        "configured_malware_scanner",
        lambda _settings: scanner,
    )


def _user(db: Session, email: str) -> User:
    actor = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="not-used-in-batch-upload-tests",
        role="technical_reviewer",
        is_active=True,
    )
    db.add(actor)
    db.commit()
    db.refresh(actor)
    return actor


def _pdf(label: str) -> bytes:
    return b"%PDF-1.7\n" + label.encode("ascii") + b"\n%%EOF\n"


def _upload(payload: bytes, filename: str) -> UploadFile:
    return UploadFile(
        BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": "application/pdf"}),
    )


def _registration(document_id: str) -> dict[str, object]:
    return {
        "artifact_provenance_note": None,
        "artifact_provenance_status": "unknown",
        "declared_source_role": "primary_test",
        "document_id": document_id,
        "document_type": "fire_test_report",
        "evidence_limitations": None,
        "evidence_scope": "full_source",
        "expiry_date": None,
        "issuing_organisation": "Example Test Laboratory",
        "jurisdiction": "Australia",
        "manufacturer": "Example Manufacturer",
        "publication_date": "2026-08-01",
        "reference": document_id,
        "related_document_id": None,
        "relationship_effective_date": None,
        "relationship_reason": None,
        "relationship_scope": None,
        "relationship_type": None,
        "review_date": None,
        "revision": "R1",
        "sponsor_organisation": "Example Sponsor",
        "standards": ["AS 1530.4:2014", "AS 4072.1:2005"],
        "title": f"Report {document_id}",
    }


def _create_batch(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    request_id: str,
    item_id: str,
    document_id: str,
    payload: bytes,
    filename: str = "report.pdf",
    registration: dict[str, object] | None = None,
) -> TechnicalIntakeBatchCreateResult:
    return create_technical_intake_batch(
        db,
        settings,
        actor=actor,
        client_request_id=request_id,
        items=[
            {
                "client_item_id": item_id,
                "expected_sha256": hashlib.sha256(payload).hexdigest(),
                "filename": filename,
                "ordinal": 1,
                "registration": registration or _registration(document_id),
                "size_bytes": len(payload),
            }
        ],
        source_ip="127.0.0.1",
    )


def _claim(
    db: Session,
    actor: User,
    created: TechnicalIntakeBatchCreateResult,
) -> TechnicalIntakeBatchClaim:
    item = created.items[0]
    return claim_technical_intake_batch_item(
        db,
        actor=actor,
        batch_id=created.batch.id,
        item_id=item.id,
        filename=item.original_filename,
        registration_snapshot=item.registration_snapshot,
    )


def _accept_batch(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    request_id: str,
    item_id: str,
    document_id: str,
    payload: bytes,
) -> tuple[
    TechnicalIntakeBatchCreateResult,
    TechnicalIntakeBatchClaim,
    TechnicalIntakeResult,
]:
    created = _create_batch(
        db,
        settings,
        actor,
        request_id=request_id,
        item_id=item_id,
        document_id=document_id,
        payload=payload,
    )
    claim = _claim(db, actor, created)
    result = _upload_claim(
        db,
        settings,
        actor,
        claim=claim,
        registration=created.items[0].registration_snapshot,
        payload=payload,
    )
    return created, claim, result


def _required_text(registration: Mapping[str, object], key: str) -> str:
    value = registration[key]
    assert isinstance(value, str)
    return value


def _optional_text(registration: Mapping[str, object], key: str) -> str | None:
    value = registration[key]
    assert value is None or isinstance(value, str)
    return value


def _standards_text(registration: Mapping[str, object]) -> str | None:
    value = registration["standards"]
    if value is None:
        return None
    assert isinstance(value, list)
    assert all(isinstance(item, str) for item in value)
    return "\n".join(value)


def _upload_claim(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    claim: TechnicalIntakeBatchClaim,
    registration: Mapping[str, object],
    payload: bytes,
) -> TechnicalIntakeResult:
    return create_technical_document_draft(
        db,
        settings,
        actor=actor,
        upload=_upload(payload, claim.original_filename),
        document_id=_required_text(registration, "document_id"),
        document_type=_required_text(registration, "document_type"),
        declared_source_role=_required_text(registration, "declared_source_role"),
        artifact_provenance_status=_required_text(
            registration, "artifact_provenance_status"
        ),
        evidence_scope=_required_text(registration, "evidence_scope"),
        title=_required_text(registration, "title"),
        manufacturer=_optional_text(registration, "manufacturer"),
        sponsor_organisation=_optional_text(
            registration, "sponsor_organisation"
        ),
        issuing_organisation=_optional_text(
            registration, "issuing_organisation"
        ),
        reference=_optional_text(registration, "reference"),
        revision=_optional_text(registration, "revision"),
        publication_date=_optional_text(registration, "publication_date"),
        review_date=_optional_text(registration, "review_date"),
        expiry_date=_optional_text(registration, "expiry_date"),
        standards=_standards_text(registration),
        jurisdiction=_optional_text(registration, "jurisdiction"),
        artifact_provenance_note=_optional_text(
            registration, "artifact_provenance_note"
        ),
        evidence_limitations=_optional_text(
            registration, "evidence_limitations"
        ),
        relationship_type=_optional_text(registration, "relationship_type"),
        related_document_id=_optional_text(
            registration, "related_document_id"
        ),
        relationship_reason=_optional_text(
            registration, "relationship_reason"
        ),
        relationship_scope=_optional_text(registration, "relationship_scope"),
        relationship_effective_date=_optional_text(
            registration, "relationship_effective_date"
        ),
        correlation_id=claim.batch_id,
        source_ip="127.0.0.1",
        batch_claim=claim,
    )


def _upload_direct(
    db: Session,
    settings: Settings,
    actor: User,
    *,
    document_id: str,
    payload: bytes,
) -> TechnicalIntakeResult:
    return create_technical_document_draft(
        db,
        settings,
        actor=actor,
        upload=_upload(payload, 'direct-report.pdf'),
        document_id=document_id,
        document_type='fire_test_report',
        declared_source_role='primary_test',
        artifact_provenance_status='unknown',
        evidence_scope='full_source',
        title=f'Report {document_id}',
        issuing_organisation='Example Test Laboratory',
        correlation_id='33333333-3333-4333-8333-333333333333',
        source_ip='127.0.0.1',
    )


def _count(db: Session, model: type[object]) -> int:
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


def _audits(db: Session, *, action: str, batch_id: str) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.action == action,
                AuditEvent.entity_type == "technical_document",
                AuditEvent.correlation_id == batch_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()
    )


def _containment_audits(
    db: Session,
    *,
    entity_type: str,
) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.action == 'shared_malware_containment',
                AuditEvent.entity_type == entity_type,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
        ).all()
    )


def test_exact_upload_accepts_atomically_and_exact_replay_has_no_new_side_effects(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "owner@example.test")
    payload = _pdf("governed exact report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-BATCH-EXACT",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot

    claim = _claim(db, owner, created)
    result = _upload_claim(
        db,
        settings,
        owner,
        claim=claim,
        registration=registration,
        payload=payload,
    )

    item = db.get(TechnicalIntakeBatchItem, claim.item_id)
    batch = db.get(TechnicalIntakeBatch, claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "accepted"
    assert item.attempt_token is None
    assert item.attempt_started_at is None
    assert item.technical_document_id == result.document.id
    assert item.retained_file_sha256 == hashlib.sha256(payload).hexdigest()
    assert isinstance(result.receipt, dict)
    assert result.receipt["ok"] is True
    assert result.receipt["batch_id"] == batch.id
    assert result.receipt["item_id"] == item.id
    assert item.receipt_json == result.receipt
    assert item.receipt_sha256 == result.receipt_sha256
    assert result.receipt_sha256 == canonical_json_sha256(result.receipt)
    assert result.idempotent_replay is False
    assert batch.status == "completed"
    assert batch.completed_at is not None
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    upload_audits = _audits(db, action="upload", batch_id=batch.id)
    assert len(upload_audits) == 1
    assert upload_audits[0].entity_id == result.document.id
    assert upload_audits[0].new_value is not None
    assert upload_audits[0].new_value["batch_item_id"] == item.id

    replay_claim = _claim(db, owner, created)
    assert replay_claim.accepted_replay is True
    replay = _upload_claim(
        db,
        settings,
        owner,
        claim=replay_claim,
        registration=registration,
        payload=payload,
    )

    assert replay.idempotent_replay is True
    assert replay.document.id == result.document.id
    assert replay.stored_file.id == result.stored_file.id
    assert replay.receipt == result.receipt
    assert replay.receipt_sha256 == result.receipt_sha256
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    assert len(_audits(db, action="upload", batch_id=batch.id)) == 1
    assert len(_audits(db, action="upload_rejected", batch_id=batch.id)) == 0
    assert scanner.calls == [payload, payload]


@pytest.mark.parametrize(
    "code",
    [
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "UPLOAD_CONTENT_SIGNATURE_INVALID",
        "UPLOAD_STAGED_BYTES_CHANGED",
    ],
)
def test_accepted_replay_integrity_failure_retains_evidence_and_requires_attention(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, f"accepted-replay-{code.lower()}@example.test")
    payload = _pdf("accepted replay integrity report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-ACCEPTED-REPLAY-INTEGRITY",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    first_claim = _claim(db, owner, created)
    accepted = _upload_claim(
        db,
        settings,
        owner,
        claim=first_claim,
        registration=registration,
        payload=payload,
    )
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    prior_receipt = deepcopy(item.receipt_json)
    prior_receipt_sha256 = item.receipt_sha256
    accepted_document_id = item.technical_document_id
    accepted_file_sha256 = item.retained_file_sha256
    accepted_attempt_count = item.attempt_count
    assert prior_receipt == accepted.receipt
    assert prior_receipt_sha256 == accepted.receipt_sha256
    assert batch.status == "completed"
    assert batch.completed_at is not None

    replay_claim = _claim(db, owner, created)
    assert replay_claim.accepted_replay is True

    def integrity_failure(*_args: object, **_kwargs: object) -> None:
        if code == "MALWARE_DETECTED":
            raise MalwareScanError(code)
        raise storage_service.StoredFileSecurityError(code)

    monkeypatch.setattr(
        "classifire.services.technical_intake.save_verified_upload",
        integrity_failure,
    )
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=registration,
            payload=payload,
        )

    assert caught.value.code == code
    assert caught.value.retryable is False
    assert caught.value.fatal is True
    assert caught.value.operator_attention is True
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "needs_attention"
    assert item.attempt_count == accepted_attempt_count
    assert item.technical_document_id == accepted_document_id
    assert item.retained_file_sha256 == accepted_file_sha256
    assert item.outcome_code == code
    assert item.outcome_retryable is False
    assert item.receipt_json is not None
    assert item.receipt_json["code"] == code
    assert item.receipt_json["operator_attention"] is True
    assert item.receipt_sha256 == canonical_json_sha256(item.receipt_json)
    assert batch.status == "needs_attention"
    assert batch.completed_at is None
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    retained_file = db.get(StoredFile, accepted.stored_file.id)
    assert retained_file is not None
    assert retained_file.malware_scan_status == (
        "quarantined" if code == "MALWARE_DETECTED" else "clean"
    )
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    audit = rejection_audits[0]
    assert audit.previous_value is not None
    assert audit.previous_value["receipt"] == prior_receipt
    assert audit.previous_value["receipt_sha256"] == prior_receipt_sha256
    assert audit.previous_value["technical_document_id"] == accepted_document_id
    assert audit.previous_value["retained_file_sha256"] == accepted_file_sha256
    if code == "MALWARE_DETECTED":
        assert audit.previous_value["stored_file_malware_scan_status"] == "clean"
    assert audit.new_value is not None
    assert audit.new_value["batch_item_transition_recorded"] is True
    if code == "MALWARE_DETECTED":
        assert audit.new_value["stored_file_malware_scan_status"] == "quarantined"
    serialized = serialize_technical_intake_batch(batch, (item,))
    serialized_item = serialized["items"][0]
    assert serialized_item["status"] == "needs_attention"
    assert serialized_item["technical_document_id"] == accepted_document_id
    assert serialized_item["retained_file_sha256"] == accepted_file_sha256
    assert serialized_item["receipt"] == item.receipt_json


def test_bound_direct_duplicate_contains_all_shared_acceptances_across_owners(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner_a = _user(db, 'containment-owner-a@example.test')
    owner_b = _user(db, 'containment-owner-b@example.test')
    detector = _user(db, 'containment-detector@example.test')
    payload = _pdf('shared multi-owner malware containment')
    _created_a, claim_a, accepted_a = _accept_batch(
        db,
        settings,
        owner_a,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-CONTAINMENT-OWNER-A',
        payload=payload,
    )
    _created_b, claim_b, accepted_b = _accept_batch(
        db,
        settings,
        owner_b,
        request_id=_REQUEST_B,
        item_id=_ITEM_B,
        document_id='DOC-CONTAINMENT-OWNER-B',
        payload=payload,
    )
    assert accepted_a.stored_file.id == accepted_b.stored_file.id
    digest = hashlib.sha256(payload).hexdigest()
    prior_items: dict[str, dict[str, object]] = {}
    for claim in (claim_a, claim_b):
        item = db.get(TechnicalIntakeBatchItem, claim.item_id)
        assert item is not None
        prior_items[item.id] = {
            'attempt_count': item.attempt_count,
            'document_id': item.technical_document_id,
            'receipt': deepcopy(item.receipt_json),
            'receipt_sha256': item.receipt_sha256,
            'record_version': item.record_version,
        }
    retained_path = Path(accepted_a.stored_file.storage_path)
    retained_bytes = retained_path.read_bytes()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    monkeypatch.setattr(
        'classifire.services.technical_intake.save_verified_upload',
        bound_malware,
    )
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_direct(
            db,
            settings,
            detector,
            document_id='DOC-CONTAINMENT-DIRECT-TRIGGER',
            payload=payload,
        )

    assert caught.value.code == 'MALWARE_DETECTED'
    public_error = str(caught.value)
    for private_id in (
        claim_a.batch_id,
        claim_b.batch_id,
        claim_a.item_id,
        claim_b.item_id,
        'DOC-CONTAINMENT-OWNER-A',
        'DOC-CONTAINMENT-OWNER-B',
    ):
        assert private_id not in public_error
    db.expire_all()
    stored = db.get(StoredFile, accepted_a.stored_file.id)
    assert stored is not None
    assert stored.malware_scan_status == 'quarantined'
    assert retained_path.exists()
    assert retained_path.read_bytes() == retained_bytes == payload
    for claim in (claim_a, claim_b):
        item = db.get(TechnicalIntakeBatchItem, claim.item_id)
        batch = db.get(TechnicalIntakeBatch, claim.batch_id)
        prior = prior_items[claim.item_id]
        assert item is not None
        assert batch is not None
        assert item.status == 'needs_attention'
        assert item.outcome_code == 'MALWARE_DETECTED'
        assert item.attempt_count == prior['attempt_count']
        assert item.technical_document_id == prior['document_id']
        assert item.retained_file_sha256 == digest
        assert item.receipt_json is not None
        assert item.receipt_json['operator_attention'] is True
        assert item.receipt_sha256 == canonical_json_sha256(item.receipt_json)
        assert batch.status == 'needs_attention'
        assert batch.completed_at is None
    for owner, claim in ((owner_a, claim_a), (owner_b, claim_b)):
        owned_batch, owned_items = get_owned_technical_intake_batch(
            db,
            actor=owner,
            batch_id=claim.batch_id,
        )
        assert owned_batch.status == 'needs_attention'
        assert owned_items[0].status == 'needs_attention'
    item_audits = _containment_audits(
        db, entity_type='technical_intake_batch_item'
    )
    batch_audits = _containment_audits(
        db, entity_type='technical_intake_batch'
    )
    stored_audits = _containment_audits(db, entity_type='stored_file')
    assert len(item_audits) == 2
    assert len(batch_audits) == 2
    assert len(stored_audits) == 1
    for audit in item_audits:
        assert audit.previous_value is not None
        prior = prior_items[audit.entity_id]
        assert audit.previous_value['receipt'] == prior['receipt']
        assert audit.previous_value['receipt_sha256'] == prior['receipt_sha256']
        assert audit.previous_value['retained_file_sha256'] == digest
    for audit in batch_audits:
        assert audit.previous_value is not None
        assert audit.previous_value['completed_at'] is not None


def test_processing_duplicate_is_rejected_after_shared_acceptances_are_contained(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'processing-containment-owner@example.test')
    detector = _user(db, 'processing-containment-detector@example.test')
    payload = _pdf('processing duplicate containment')
    _accepted_batch, accepted_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-PROCESSING-CONTAINMENT-ACCEPTED',
        payload=payload,
    )
    trigger_batch = _create_batch(
        db,
        settings,
        detector,
        request_id=_REQUEST_B,
        item_id=_ITEM_B,
        document_id='DOC-PROCESSING-CONTAINMENT-TRIGGER',
        payload=payload,
    )
    trigger_claim = _claim(db, detector, trigger_batch)
    digest = hashlib.sha256(payload).hexdigest()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    monkeypatch.setattr(intake_service, 'save_verified_upload', bound_malware)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            detector,
            claim=trigger_claim,
            registration=trigger_batch.items[0].registration_snapshot,
            payload=payload,
        )
    assert caught.value.code == 'MALWARE_DETECTED'

    db.expire_all()
    accepted_item = db.get(TechnicalIntakeBatchItem, accepted_claim.item_id)
    accepted_batch = db.get(TechnicalIntakeBatch, accepted_claim.batch_id)
    trigger_item = db.get(TechnicalIntakeBatchItem, trigger_claim.item_id)
    refreshed_trigger_batch = db.get(
        TechnicalIntakeBatch, trigger_claim.batch_id
    )
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert accepted_item is not None
    assert accepted_batch is not None
    assert trigger_item is not None
    assert refreshed_trigger_batch is not None
    assert stored is not None
    assert accepted_item.status == 'needs_attention'
    assert accepted_batch.status == 'needs_attention'
    assert trigger_item.status == 'rejected'
    assert trigger_item.outcome_code == 'MALWARE_DETECTED'
    assert trigger_item.technical_document_id is None
    assert trigger_item.retained_file_sha256 is None
    assert refreshed_trigger_batch.status == 'completed_with_rejections'
    assert refreshed_trigger_batch.completed_at is not None
    assert stored.malware_scan_status == 'quarantined'


def test_containment_locks_shared_rows_in_stable_order(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'lock-order-owner@example.test')
    detector = _user(db, 'lock-order-detector@example.test')
    payload = _pdf('shared malware lock order')
    _created, _claim_value, _accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-MALWARE-LOCK-ORDER',
        payload=payload,
    )
    digest = hashlib.sha256(payload).hexdigest()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    expected_entities = (
        StoredFile,
        TechnicalDocument,
        TechnicalIntakeBatch,
        TechnicalIntakeBatchItem,
    )
    locked_entities: list[type[object]] = []

    def observe_lock(execute_state: Any) -> None:
        statement = execute_state.statement
        if getattr(statement, '_for_update_arg', None) is None:
            return
        entities = tuple(
            description.get('entity')
            for description in getattr(statement, 'column_descriptions', ())
        )
        for entity in expected_entities:
            if entity in entities:
                locked_entities.append(entity)
                break

    monkeypatch.setattr(intake_service, 'save_verified_upload', bound_malware)
    event.listen(db, 'do_orm_execute', observe_lock)
    try:
        with pytest.raises(TechnicalIntakeError):
            _upload_direct(
                db,
                settings,
                detector,
                document_id='DOC-MALWARE-LOCK-TRIGGER',
                payload=payload,
            )
    finally:
        event.remove(db, 'do_orm_execute', observe_lock)

    assert tuple(locked_entities) == expected_entities


def test_bound_accepted_replay_contains_once_and_repeat_is_idempotent(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'bound-replay@example.test')
    detector = _user(db, 'bound-replay-detector@example.test')
    payload = _pdf('bound accepted replay containment')
    created, first_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-BOUND-ACCEPTED-REPLAY',
        payload=payload,
    )
    stored_id = accepted.stored_file.id
    digest = hashlib.sha256(payload).hexdigest()
    replay_claim = _claim(db, owner, created)
    assert replay_claim.accepted_replay is True

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    monkeypatch.setattr(
        'classifire.services.technical_intake.save_verified_upload',
        bound_malware,
    )
    with pytest.raises(TechnicalIntakeError) as first_error:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )
    assert first_error.value.code == 'MALWARE_DETECTED'
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, stored_id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert item.status == 'needs_attention'
    assert batch.status == 'needs_attention'
    assert stored.malware_scan_status == 'quarantined'
    contained_versions = (
        item.record_version,
        batch.record_version,
        stored.record_version,
    )
    contained_receipt = deepcopy(item.receipt_json)
    item_audit_count = len(
        _containment_audits(db, entity_type='technical_intake_batch_item')
    )
    batch_audit_count = len(
        _containment_audits(db, entity_type='technical_intake_batch')
    )

    with pytest.raises(TechnicalIntakeError) as repeated_error:
        _upload_direct(
            db,
            settings,
            detector,
            document_id='DOC-BOUND-REPEAT-TRIGGER',
            payload=payload,
        )
    assert repeated_error.value.code == 'MALWARE_DETECTED'
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, stored_id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert (item.record_version, batch.record_version, stored.record_version) == (
        contained_versions
    )
    assert item.receipt_json == contained_receipt
    assert len(
        _containment_audits(db, entity_type='technical_intake_batch_item')
    ) == item_audit_count
    assert len(
        _containment_audits(db, entity_type='technical_intake_batch')
    ) == batch_audit_count
    stored_audits = _containment_audits(db, entity_type='stored_file')
    assert len(stored_audits) == 2
    assert stored_audits[-1].new_value is not None
    assert stored_audits[-1].new_value['state_changed'] is False
    assert stored_audits[-1].new_value['transitioned_item_count'] == 0


@pytest.mark.parametrize('binding_case', ['unbound', 'digest', 'size'])
def test_unbound_or_mismatched_malware_replay_preserves_accepted_evidence(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    binding_case: str,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, f'untrusted-malware-{binding_case}@example.test')
    payload = _pdf(f'untrusted malware binding {binding_case}')
    created, first_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id=f'DOC-UNTRUSTED-MALWARE-{binding_case.upper()}',
        payload=payload,
    )
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    accepted_state = {
        'item_version': item.record_version,
        'batch_version': batch.record_version,
        'completed_at': batch.completed_at,
        'receipt': deepcopy(item.receipt_json),
        'receipt_sha256': item.receipt_sha256,
        'technical_document_id': item.technical_document_id,
    }
    digest: str | None = hashlib.sha256(payload).hexdigest()
    size: int | None = len(payload)
    if binding_case == 'unbound':
        digest = None
        size = None
    elif binding_case == 'digest':
        digest = '0' * 64
    else:
        size += 1

    def invalid_binding(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=size,
        )

    monkeypatch.setattr(
        'classifire.services.technical_intake.save_verified_upload',
        invalid_binding,
    )
    replay_claim = _claim(db, owner, created)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )

    assert caught.value.code == 'INTAKE_BATCH_ITEM_ACKNOWLEDGEMENT_UNKNOWN'
    assert caught.value.prior_code == 'MALWARE_DETECTED'
    assert caught.value.fatal is True
    assert caught.value.operator_attention is True
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert item.status == 'accepted'
    assert item.record_version == accepted_state['item_version']
    assert item.receipt_json == accepted_state['receipt']
    assert item.receipt_sha256 == accepted_state['receipt_sha256']
    assert item.technical_document_id == accepted_state['technical_document_id']
    assert batch.status == 'completed'
    assert batch.record_version == accepted_state['batch_version']
    assert batch.completed_at == accepted_state['completed_at']
    assert stored.malware_scan_status == 'clean'
    assert _containment_audits(db, entity_type='stored_file') == []
    rejection_audits = _audits(
        db, action='upload_rejected', batch_id=first_claim.batch_id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].new_value is not None
    assert 'shared_malware_containment_matched' not in (
        rejection_audits[0].new_value
    )


def test_cleanup_failure_does_not_erase_bound_malware_containment(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'malware-cleanup@example.test')
    payload = _pdf('malware containment survives cleanup failure')
    created, first_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-MALWARE-CLEANUP-FAILURE',
        payload=payload,
    )
    digest = hashlib.sha256(payload).hexdigest()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    def cleanup_failure(
        _upload: object,
        *,
        prior_code: str,
    ) -> storage_service.StoredFileSecurityError:
        return storage_service.StoredFileSecurityError(
            'UPLOAD_TEMP_CLEANUP_FAILED',
            prior_code=prior_code,
            cleanup_codes=('UPLOAD_TEMP_CLEANUP_FAILED',),
        )

    monkeypatch.setattr(
        'classifire.services.technical_intake.save_verified_upload',
        bound_malware,
    )
    monkeypatch.setattr(
        'classifire.services.technical_intake.cleanup_uncommitted_upload',
        cleanup_failure,
    )
    replay_claim = _claim(db, owner, created)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )

    assert caught.value.code == 'UPLOAD_TEMP_CLEANUP_FAILED'
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert item.status == 'needs_attention'
    assert item.outcome_code == 'MALWARE_DETECTED'
    assert batch.status == 'needs_attention'
    assert stored.malware_scan_status == 'quarantined'
    rejection_audits = _audits(
        db, action='upload_rejected', batch_id=first_claim.batch_id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].new_value is not None
    assert rejection_audits[0].new_value['prior_outcome'] == 'MALWARE_DETECTED'
    assert (
        rejection_audits[0].new_value['shared_malware_containment_matched']
        is True
    )


def test_storage_wrapped_bound_malware_still_contains_shared_acceptance(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'wrapped-malware-owner@example.test')
    payload = _pdf('storage wrapped malware containment')
    created, first_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-WRAPPED-MALWARE',
        payload=payload,
    )
    digest = hashlib.sha256(payload).hexdigest()

    def wrapped_malware(*_args: object, **_kwargs: object) -> None:
        raise storage_service.StoredFileSecurityError(
            'UPLOAD_TEMP_CLEANUP_FAILED',
            prior_code='MALWARE_DETECTED',
            cleanup_codes=('UPLOAD_TEMP_CLEANUP_FAILED',),
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    monkeypatch.setattr(intake_service, 'save_verified_upload', wrapped_malware)
    replay_claim = _claim(db, owner, created)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )

    assert caught.value.code == 'UPLOAD_TEMP_CLEANUP_FAILED'
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert item.status == 'needs_attention'
    assert item.outcome_code == 'MALWARE_DETECTED'
    assert batch.status == 'needs_attention'
    assert stored.malware_scan_status == 'quarantined'
    stored_audits = _containment_audits(db, entity_type='stored_file')
    assert len(stored_audits) == 1


@pytest.mark.parametrize(
    ('drift_direction', 'expected_binding'),
    [
        (
            'retained_sha_points_to_malware',
            {
                'document_references_malware_file': False,
                'retained_sha_references_malware_bytes': True,
            },
        ),
        (
            'document_points_to_malware',
            {
                'document_references_malware_file': True,
                'retained_sha_references_malware_bytes': False,
            },
        ),
    ],
)
def test_bound_malware_quarantines_despite_one_way_accepted_item_drift(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    drift_direction: str,
    expected_binding: dict[str, bool],
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, f'one-way-drift-{drift_direction}@example.test')
    detector = _user(db, f'one-way-detector-{drift_direction}@example.test')
    malware_payload = _pdf(f'one-way malware bytes {drift_direction}')
    other_payload = _pdf(f'one-way other bytes {drift_direction}')

    if drift_direction == 'retained_sha_points_to_malware':
        _created, claim, accepted = _accept_batch(
            db,
            settings,
            owner,
            request_id=_REQUEST_A,
            item_id=_ITEM_A,
            document_id='DOC-DRIFT-RETAINED-MALWARE',
            payload=malware_payload,
        )
        other = _upload_direct(
            db,
            settings,
            owner,
            document_id='DOC-DRIFT-DOCUMENT-OTHER',
            payload=other_payload,
        )
        malware_stored = accepted.stored_file
        other_stored = other.stored_file
        drifted_document_id = other.document.id
        item = db.get(TechnicalIntakeBatchItem, claim.item_id)
        assert item is not None
        item.technical_document_id = drifted_document_id
    else:
        _created, claim, accepted = _accept_batch(
            db,
            settings,
            owner,
            request_id=_REQUEST_A,
            item_id=_ITEM_A,
            document_id='DOC-DRIFT-RETAINED-OTHER',
            payload=other_payload,
        )
        malware = _upload_direct(
            db,
            settings,
            owner,
            document_id='DOC-DRIFT-DOCUMENT-MALWARE',
            payload=malware_payload,
        )
        malware_stored = malware.stored_file
        other_stored = accepted.stored_file
        drifted_document_id = malware.document.id
        item = db.get(TechnicalIntakeBatchItem, claim.item_id)
        assert item is not None
        item.technical_document_id = drifted_document_id
    db.commit()

    malware_stored_id = malware_stored.id
    other_stored_id = other_stored.id
    retained_sha256 = item.retained_file_sha256
    expected_sha256 = item.expected_sha256
    declared_size_bytes = item.declared_size_bytes
    digest = hashlib.sha256(malware_payload).hexdigest()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(malware_payload),
        )

    monkeypatch.setattr(intake_service, 'save_verified_upload', bound_malware)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_direct(
            db,
            settings,
            detector,
            document_id='DOC-DRIFT-MALWARE-TRIGGER',
            payload=malware_payload,
        )

    assert caught.value.code == 'MALWARE_DETECTED'
    db.expire_all()
    malware_stored = db.get(StoredFile, malware_stored_id)
    other_stored = db.get(StoredFile, other_stored_id)
    item = db.get(TechnicalIntakeBatchItem, claim.item_id)
    batch = db.get(TechnicalIntakeBatch, claim.batch_id)
    assert malware_stored is not None
    assert other_stored is not None
    assert item is not None
    assert batch is not None
    assert malware_stored.malware_scan_status == 'quarantined'
    assert Path(malware_stored.storage_path).read_bytes() == malware_payload
    assert other_stored.malware_scan_status == 'clean'
    assert item.status == 'needs_attention'
    assert item.outcome_code == 'STORED_FILE_CONTEXT_CONFLICT'
    assert item.technical_document_id == drifted_document_id
    assert item.retained_file_sha256 == retained_sha256
    assert item.expected_sha256 == expected_sha256
    assert item.declared_size_bytes == declared_size_bytes
    assert item.receipt_json is not None
    assert item.receipt_json['code'] == 'STORED_FILE_CONTEXT_CONFLICT'
    assert item.receipt_sha256 == canonical_json_sha256(item.receipt_json)
    assert batch.status == 'needs_attention'
    assert batch.completed_at is None
    with pytest.raises(storage_service.StoredFileBindingError):
        storage_service.open_verified_stored_file(
            malware_stored,
            storage_root=settings.storage_root,
            required_purpose='technical_evidence',
        )

    owned_batch, owned_items = get_owned_technical_intake_batch(
        db,
        actor=owner,
        batch_id=claim.batch_id,
    )
    assert owned_batch.status == 'needs_attention'
    assert owned_items[0].outcome_code == 'STORED_FILE_CONTEXT_CONFLICT'
    item_audits = _containment_audits(
        db, entity_type='technical_intake_batch_item'
    )
    assert len(item_audits) == 1
    assert item_audits[0].new_value is not None
    binding_evaluation = item_audits[0].new_value['binding_evaluation']
    assert isinstance(binding_evaluation, dict)
    for key, expected in expected_binding.items():
        assert binding_evaluation[key] is expected


def test_containment_audit_failure_rolls_back_all_shared_state(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, 'malware-rollback-owner@example.test')
    detector = _user(db, 'malware-rollback-detector@example.test')
    payload = _pdf('atomic malware containment rollback')
    _created, first_claim, accepted = _accept_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id='DOC-MALWARE-ROLLBACK',
        payload=payload,
    )
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    prior_state = {
        'item_version': item.record_version,
        'batch_version': batch.record_version,
        'stored_version': stored.record_version,
        'completed_at': batch.completed_at,
        'receipt': deepcopy(item.receipt_json),
        'audit_count': _count(db, AuditEvent),
    }
    digest = hashlib.sha256(payload).hexdigest()

    def bound_malware(*_args: object, **_kwargs: object) -> None:
        raise MalwareScanError(
            'MALWARE_DETECTED',
            content_sha256=digest,
            content_size_bytes=len(payload),
        )

    original_record_audit = intake_service.record_audit
    audit_calls = 0

    def fail_second_audit(*args: Any, **kwargs: Any) -> AuditEvent:
        nonlocal audit_calls
        audit_calls += 1
        if audit_calls == 2:
            raise RuntimeError('injected containment audit failure')
        return original_record_audit(*args, **kwargs)

    monkeypatch.setattr(intake_service, 'save_verified_upload', bound_malware)
    monkeypatch.setattr(intake_service, 'record_audit', fail_second_audit)
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_direct(
            db,
            settings,
            detector,
            document_id='DOC-MALWARE-ROLLBACK-TRIGGER',
            payload=payload,
        )

    assert caught.value.code == 'TECHNICAL_INTAKE_AUDIT_FAILURE'
    assert caught.value.prior_code == 'MALWARE_DETECTED'
    db.expire_all()
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    stored = db.get(StoredFile, accepted.stored_file.id)
    assert item is not None
    assert batch is not None
    assert stored is not None
    assert item.status == 'accepted'
    assert item.record_version == prior_state['item_version']
    assert item.receipt_json == prior_state['receipt']
    assert batch.status == 'completed'
    assert batch.record_version == prior_state['batch_version']
    assert batch.completed_at == prior_state['completed_at']
    assert stored.malware_scan_status == 'clean'
    assert stored.record_version == prior_state['stored_version']
    assert _count(db, AuditEvent) == prior_state['audit_count']
    assert _containment_audits(db, entity_type='stored_file') == []


def test_accepted_replay_transient_scanner_failure_preserves_accepted_state(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "accepted-replay-transient@example.test")
    payload = _pdf("accepted replay transient report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-ACCEPTED-REPLAY-TRANSIENT",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    first_claim = _claim(db, owner, created)
    _upload_claim(
        db,
        settings,
        owner,
        claim=first_claim,
        registration=registration,
        payload=payload,
    )
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    accepted_state = {
        "record_version": item.record_version,
        "technical_document_id": item.technical_document_id,
        "retained_file_sha256": item.retained_file_sha256,
        "receipt": deepcopy(item.receipt_json),
        "receipt_sha256": item.receipt_sha256,
        "completed_at": batch.completed_at,
    }
    scanner.transient_failures = 1
    replay_claim = _claim(db, owner, created)

    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=registration,
            payload=payload,
        )

    assert caught.value.code == "MALWARE_SCANNER_UNAVAILABLE"
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "accepted"
    assert item.record_version == accepted_state["record_version"]
    assert item.technical_document_id == accepted_state["technical_document_id"]
    assert item.retained_file_sha256 == accepted_state["retained_file_sha256"]
    assert item.receipt_json == accepted_state["receipt"]
    assert item.receipt_sha256 == accepted_state["receipt_sha256"]
    assert batch.status == "completed"
    assert batch.completed_at == accepted_state["completed_at"]
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].previous_value is None
    assert rejection_audits[0].new_value is not None
    assert (
        rejection_audits[0].new_value["batch_item_transition_recorded"]
        is False
    )
    assert scanner.calls == [payload, payload]


def test_accepted_replay_transient_storage_failure_preserves_accepted_state(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "accepted-replay-storage-failure@example.test")
    payload = _pdf("accepted replay storage failure report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-ACCEPTED-REPLAY-STORAGE-FAILURE",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    first_claim = _claim(db, owner, created)
    _upload_claim(
        db,
        settings,
        owner,
        claim=first_claim,
        registration=registration,
        payload=payload,
    )
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    accepted_record_version = item.record_version
    accepted_receipt = deepcopy(item.receipt_json)
    accepted_receipt_sha256 = item.receipt_sha256
    accepted_completed_at = batch.completed_at
    replay_claim = _claim(db, owner, created)

    def transient_storage_failure(*_args: object, **_kwargs: object) -> None:
        raise storage_service.StoredFileSecurityError("STORED_FILE_STORAGE_FAILURE")

    monkeypatch.setattr(
        "classifire.services.technical_intake.save_verified_upload",
        transient_storage_failure,
    )
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=replay_claim,
            registration=registration,
            payload=payload,
        )

    assert caught.value.code == "STORED_FILE_STORAGE_FAILURE"
    assert caught.value.fatal is True
    item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "accepted"
    assert item.record_version == accepted_record_version
    assert item.receipt_json == accepted_receipt
    assert item.receipt_sha256 == accepted_receipt_sha256
    assert batch.status == "completed"
    assert batch.completed_at == accepted_completed_at
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].previous_value is None
    assert rejection_audits[0].new_value is not None
    assert (
        rejection_audits[0].new_value["batch_item_transition_recorded"]
        is False
    )


def test_accepted_replay_rejects_an_internally_rehashed_misbound_receipt(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "receipt-binding@example.test")
    payload = _pdf("receipt binding report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-RECEIPT-BINDING",
        payload=payload,
    )
    claim = _claim(db, owner, created)
    _upload_claim(
        db,
        settings,
        owner,
        claim=claim,
        registration=created.items[0].registration_snapshot,
        payload=payload,
    )

    item = db.get(TechnicalIntakeBatchItem, claim.item_id)
    assert item is not None
    assert isinstance(item.receipt_json, dict)
    tampered_receipt = dict(item.receipt_json)
    tampered_receipt["batch_id"] = _REQUEST_B
    item.receipt_json = tampered_receipt
    item.receipt_sha256 = canonical_json_sha256(tampered_receipt)
    db.commit()

    with pytest.raises(
        TechnicalIntakeBatchError,
        match="INTAKE_BATCH_PERSISTENCE_CONFLICT",
    ) as caught:
        _claim(db, owner, created)

    assert caught.value.code == "INTAKE_BATCH_PERSISTENCE_CONFLICT"
    persisted = db.get(TechnicalIntakeBatchItem, claim.item_id)
    assert persisted is not None
    assert persisted.status == "accepted"


@pytest.mark.parametrize(
    ("attribute", "tampered_value"),
    [
        ("reason", "A different relationship reason"),
        ("scope", "A different relationship scope"),
        ("effective_date", date(2026, 8, 29)),
    ],
)
def test_accepted_replay_rejects_mutated_relationship_provenance(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    attribute: str,
    tampered_value: object,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "relationship-replay@example.test")
    create_technical_document_draft(
        db,
        settings,
        actor=owner,
        upload=_upload(_pdf("related source"), "related.pdf"),
        document_id="DOC-RELATED-SOURCE",
        document_type="fire_test_report",
        declared_source_role="primary_test",
        artifact_provenance_status="unknown",
        evidence_scope="full_source",
        title="Related source",
        jurisdiction="Australia",
    )
    payload = _pdf("relationship-bound report")
    registration = _registration("DOC-RELATIONSHIP-BOUND")
    registration.update(
        {
            "related_document_id": "DOC-RELATED-SOURCE",
            "relationship_effective_date": "2026-08-28",
            "relationship_reason": "The assessment evaluates the source",
            "relationship_scope": "Systems listed in section 4",
            "relationship_type": "assessment_of",
        }
    )
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-RELATIONSHIP-BOUND",
        payload=payload,
        registration=registration,
    )
    claim = _claim(db, owner, created)
    accepted = _upload_claim(
        db,
        settings,
        owner,
        claim=claim,
        registration=created.items[0].registration_snapshot,
        payload=payload,
    )
    assert accepted.relationship is not None
    setattr(accepted.relationship, attribute, tampered_value)
    db.commit()

    with pytest.raises(
        TechnicalIntakeBatchError,
        match="INTAKE_BATCH_PERSISTENCE_CONFLICT",
    ) as caught:
        _claim(db, owner, created)

    assert caught.value.code == "INTAKE_BATCH_PERSISTENCE_CONFLICT"
    persisted = db.get(TechnicalIntakeBatchItem, claim.item_id)
    assert persisted is not None
    assert persisted.status == "accepted"


def test_manifest_admitted_size_survives_a_later_configuration_reduction(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "admitted-size-policy@example.test")
    payload = b"%PDF-1.7\n" + (b"x" * 1_100_000) + b"\n%%EOF\n"
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-ADMITTED-SIZE-POLICY",
        payload=payload,
    )
    reduced_limit_settings = Settings(
        _env_file=None,
        env="test",
        storage_root=settings.storage_root,
        clamav_host=settings.clamav_host,
        max_upload_mb=1,
    )
    registration = created.items[0].registration_snapshot

    first = _upload_claim(
        db,
        reduced_limit_settings,
        owner,
        claim=_claim(db, owner, created),
        registration=registration,
        payload=payload,
    )
    replay = _upload_claim(
        db,
        reduced_limit_settings,
        owner,
        claim=_claim(db, owner, created),
        registration=registration,
        payload=payload,
    )

    assert first.idempotent_replay is False
    assert replay.idempotent_replay is True
    assert replay.document.id == first.document.id
    assert scanner.calls == [payload, payload]


def test_wrong_bytes_restore_pending_retryable_state(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_scanner(monkeypatch, _ContentScanner())
    owner = _user(db, "owner@example.test")
    payload = _pdf("expected report")
    wrong_payload = payload.replace(b"expected", b"expectfd")
    assert len(wrong_payload) == len(payload)
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-BATCH-WRONG-BYTES",
        payload=payload,
    )
    claim = _claim(db, owner, created)

    with pytest.raises(TechnicalIntakeError) as captured:
        _upload_claim(
            db,
            settings,
            owner,
            claim=claim,
            registration=created.items[0].registration_snapshot,
            payload=wrong_payload,
        )
    assert captured.value.code == "UPLOAD_EXPECTED_CONTENT_MISMATCH"

    batch, items = get_owned_technical_intake_batch(
        db, actor=owner, batch_id=created.batch.id
    )
    item = items[0]
    serialized = serialize_technical_intake_batch(batch, items)
    assert item.status == "pending"
    assert item.attempt_count == 1
    assert item.attempt_token is None
    assert item.attempt_started_at is None
    assert item.outcome_code is None
    assert item.outcome_retryable is None
    assert item.receipt_json is None
    assert item.receipt_sha256 is None
    assert serialized["items"][0]["retryable"] is True
    assert batch.status == "open"
    assert batch.completed_at is None
    assert _count(db, TechnicalDocument) == 0
    assert _count(db, StoredFile) == 0
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].new_value is not None
    assert rejection_audits[0].new_value["batch_item_transition_recorded"] is True


def test_transient_scanner_failure_keeps_receipt_and_exact_retry_accepts(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner(transient_failures=1)
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "owner@example.test")
    payload = _pdf("scanner retry report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-BATCH-SCANNER-RETRY",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    first_claim = _claim(db, owner, created)

    with pytest.raises(TechnicalIntakeError) as captured:
        _upload_claim(
            db,
            settings,
            owner,
            claim=first_claim,
            registration=registration,
            payload=payload,
        )
    assert captured.value.code == "MALWARE_SCANNER_UNAVAILABLE"

    failed_item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    failed_batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    assert failed_item is not None
    assert failed_batch is not None
    assert failed_item.status == "rejected"
    assert failed_item.outcome_code == "MALWARE_SCANNER_UNAVAILABLE"
    assert failed_item.outcome_retryable is True
    assert failed_item.receipt_json is not None
    assert failed_item.receipt_json["retryable"] is True
    assert failed_item.receipt_sha256 == canonical_json_sha256(
        failed_item.receipt_json
    )
    failed_receipt = dict(failed_item.receipt_json)
    failed_receipt_sha256 = failed_item.receipt_sha256
    assert failed_batch.status == "completed_with_rejections"
    assert failed_batch.completed_at is not None
    assert _count(db, TechnicalDocument) == 0
    assert _count(db, StoredFile) == 0

    retry_claim = _claim(db, owner, created)
    assert retry_claim.prior_status == "rejected"
    assert retry_claim.attempt_token != first_claim.attempt_token
    processing_item = db.get(TechnicalIntakeBatchItem, retry_claim.item_id)
    assert processing_item is not None
    assert processing_item.status == "processing"
    assert processing_item.receipt_json == failed_receipt
    assert processing_item.receipt_sha256 == failed_receipt_sha256

    result = _upload_claim(
        db,
        settings,
        owner,
        claim=retry_claim,
        registration=registration,
        payload=payload,
    )

    accepted_item = db.get(TechnicalIntakeBatchItem, retry_claim.item_id)
    accepted_batch = db.get(TechnicalIntakeBatch, retry_claim.batch_id)
    assert accepted_item is not None
    assert accepted_batch is not None
    assert result.idempotent_replay is False
    assert accepted_item.status == "accepted"
    assert accepted_item.attempt_count == 2
    assert accepted_item.outcome_code == "ACCEPTED"
    assert accepted_item.outcome_retryable is False
    assert accepted_item.receipt_json == result.receipt
    assert accepted_batch.status == "completed"
    assert accepted_batch.completed_at is not None
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    assert len(_audits(db, action="upload_rejected", batch_id=created.batch.id)) == 1
    assert len(_audits(db, action="upload", batch_id=created.batch.id)) == 1
    assert scanner.calls == [payload, payload]


def test_expired_retry_claim_wrong_bytes_restores_retained_rejection(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner(transient_failures=1)
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "expired-retry@example.test")
    payload = _pdf("expired retry report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-EXPIRED-RETRY",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    first_claim = _claim(db, owner, created)
    with pytest.raises(TechnicalIntakeError) as first_failure:
        _upload_claim(
            db,
            settings,
            owner,
            claim=first_claim,
            registration=registration,
            payload=payload,
        )
    assert first_failure.value.code == "MALWARE_SCANNER_UNAVAILABLE"

    rejected = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    assert rejected is not None
    assert isinstance(rejected.receipt_json, dict)
    retained_receipt = dict(rejected.receipt_json)
    retained_receipt_sha256 = rejected.receipt_sha256
    retry_claim = _claim(db, owner, created)
    processing = db.get(TechnicalIntakeBatchItem, retry_claim.item_id)
    assert processing is not None
    processing.attempt_started_at = (
        datetime.now(UTC)
        - TECHNICAL_INTAKE_CLAIM_TTL
        - timedelta(seconds=1)
    )
    db.commit()
    reclaimed = _claim(db, owner, created)
    assert reclaimed.prior_status == "rejected"
    with pytest.raises(TechnicalIntakeError) as wrong_file:
        _upload_claim(
            db,
            settings,
            owner,
            claim=reclaimed,
            registration=registration,
            payload=_pdf("different report"),
        )
    assert wrong_file.value.code == "UPLOAD_EXPECTED_CONTENT_MISMATCH"

    restored = db.get(TechnicalIntakeBatchItem, reclaimed.item_id)
    batch = db.get(TechnicalIntakeBatch, reclaimed.batch_id)
    assert restored is not None
    assert batch is not None
    assert restored.status == "rejected"
    assert restored.attempt_token is None
    assert restored.receipt_json == retained_receipt
    assert restored.receipt_sha256 == retained_receipt_sha256
    assert restored.outcome_code == "MALWARE_SCANNER_UNAVAILABLE"
    assert restored.outcome_retryable is True
    assert batch.status == "completed_with_rejections"


def test_owner_mismatch_cannot_use_another_users_claim(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "owner@example.test")
    attacker = _user(db, "other@example.test")
    payload = _pdf("owner bound report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-BATCH-OWNER",
        payload=payload,
    )
    claim = _claim(db, owner, created)

    with pytest.raises(TechnicalIntakeError) as captured:
        _upload_claim(
            db,
            settings,
            attacker,
            claim=claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )
    assert captured.value.code == "INTAKE_BATCH_ITEM_CLAIM_INVALID"

    item = db.get(TechnicalIntakeBatchItem, claim.item_id)
    batch = db.get(TechnicalIntakeBatch, claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "processing"
    assert item.attempt_token == claim.attempt_token
    assert item.technical_document_id is None
    assert batch.status == "in_progress"
    assert _count(db, TechnicalDocument) == 0
    assert _count(db, StoredFile) == 0
    assert scanner.calls == []
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].actor_user_id == attacker.id
    assert rejection_audits[0].new_value is not None
    assert rejection_audits[0].new_value["batch_item_transition_recorded"] is False


@pytest.mark.parametrize(
    "code",
    [
        "STORED_FILE_CONTENT_COLLISION",
        "STORED_FILE_CONTEXT_CONFLICT",
        "UPLOAD_STAGED_BYTES_CHANGED",
    ],
)
def test_evidence_store_integrity_failure_requires_operator_attention(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    code: str,
) -> None:
    owner = _user(db, f"integrity-{code.lower()}@example.test")
    payload = _pdf("content collision report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-CONTENT-COLLISION",
        payload=payload,
    )
    claim = _claim(db, owner, created)

    def integrity_failure(*_args: object, **_kwargs: object) -> None:
        raise storage_service.StoredFileSecurityError(code)

    monkeypatch.setattr(
        "classifire.services.technical_intake.save_verified_upload",
        integrity_failure,
    )
    with pytest.raises(TechnicalIntakeError) as caught:
        _upload_claim(
            db,
            settings,
            owner,
            claim=claim,
            registration=created.items[0].registration_snapshot,
            payload=payload,
        )

    assert caught.value.code == code
    assert caught.value.retryable is False
    assert caught.value.fatal is True
    item = db.get(TechnicalIntakeBatchItem, claim.item_id)
    batch = db.get(TechnicalIntakeBatch, claim.batch_id)
    assert item is not None
    assert batch is not None
    assert item.status == "needs_attention"
    assert item.outcome_code == code
    assert item.outcome_retryable is False
    assert item.receipt_json is not None
    assert item.receipt_json["operator_attention"] is True
    assert item.receipt_json["retryable"] is False
    assert batch.status == "needs_attention"
    assert batch.completed_at is None
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].actor_user_id == owner.id
    assert rejection_audits[0].new_value is not None
    assert rejection_audits[0].new_value["outcome"] == code
    assert rejection_audits[0].new_value["batch_item_transition_recorded"] is True


def test_stale_attempt_cannot_finalize_after_item_is_reclaimed(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "owner@example.test")
    payload = _pdf("stale claim report")
    created = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-BATCH-STALE",
        payload=payload,
    )
    registration = created.items[0].registration_snapshot
    stale_claim = _claim(db, owner, created)
    item = db.get(TechnicalIntakeBatchItem, stale_claim.item_id)
    assert item is not None
    item.attempt_started_at = (
        datetime.now(UTC) - TECHNICAL_INTAKE_CLAIM_TTL - timedelta(seconds=1)
    )
    db.commit()

    current_claim = _claim(db, owner, created)
    assert current_claim.attempt_token != stale_claim.attempt_token

    with pytest.raises(TechnicalIntakeError) as captured:
        _upload_claim(
            db,
            settings,
            owner,
            claim=stale_claim,
            registration=registration,
            payload=payload,
        )
    assert captured.value.code == "INTAKE_BATCH_ITEM_CLAIM_INVALID"

    current_item = db.get(TechnicalIntakeBatchItem, current_claim.item_id)
    assert current_item is not None
    assert current_item.status == "processing"
    assert current_item.attempt_token == current_claim.attempt_token
    assert current_item.technical_document_id is None
    assert _count(db, TechnicalDocument) == 0
    assert _count(db, StoredFile) == 0
    assert scanner.calls == []

    result = _upload_claim(
        db,
        settings,
        owner,
        claim=current_claim,
        registration=registration,
        payload=payload,
    )
    accepted_item = db.get(TechnicalIntakeBatchItem, current_claim.item_id)
    assert accepted_item is not None
    assert accepted_item.status == "accepted"
    assert accepted_item.attempt_count == 2
    assert accepted_item.technical_document_id == result.document.id
    assert scanner.calls == [payload]
    rejection_audits = _audits(
        db, action="upload_rejected", batch_id=created.batch.id
    )
    assert len(rejection_audits) == 1
    assert rejection_audits[0].new_value is not None
    assert rejection_audits[0].new_value["batch_item_transition_recorded"] is False


def test_different_items_with_same_document_id_yield_one_acceptance_one_rejection(
    db: Session,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanner = _ContentScanner()
    _install_scanner(monkeypatch, scanner)
    owner = _user(db, "owner@example.test")
    payload = _pdf("duplicate document identity")
    first = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_A,
        item_id=_ITEM_A,
        document_id="DOC-SHARED-IDENTITY",
        payload=payload,
    )
    second = _create_batch(
        db,
        settings,
        owner,
        request_id=_REQUEST_B,
        item_id=_ITEM_B,
        document_id="DOC-SHARED-IDENTITY",
        payload=payload,
    )
    first_claim = _claim(db, owner, first)
    second_claim = _claim(db, owner, second)

    accepted = _upload_claim(
        db,
        settings,
        owner,
        claim=first_claim,
        registration=first.items[0].registration_snapshot,
        payload=payload,
    )
    with pytest.raises(TechnicalIntakeError) as captured:
        _upload_claim(
            db,
            settings,
            owner,
            claim=second_claim,
            registration=second.items[0].registration_snapshot,
            payload=payload,
        )
    assert captured.value.code == "DOCUMENT_ID_ALREADY_EXISTS"

    first_item = db.get(TechnicalIntakeBatchItem, first_claim.item_id)
    second_item = db.get(TechnicalIntakeBatchItem, second_claim.item_id)
    first_batch = db.get(TechnicalIntakeBatch, first_claim.batch_id)
    second_batch = db.get(TechnicalIntakeBatch, second_claim.batch_id)
    assert first_item is not None
    assert second_item is not None
    assert first_batch is not None
    assert second_batch is not None
    assert first_item.status == "accepted"
    assert first_item.technical_document_id == accepted.document.id
    assert second_item.status == "rejected"
    assert second_item.technical_document_id is None
    assert second_item.outcome_code == "DOCUMENT_ID_ALREADY_EXISTS"
    assert second_item.outcome_retryable is False
    assert second_item.receipt_json is not None
    assert second_item.receipt_json["code"] == "DOCUMENT_ID_ALREADY_EXISTS"
    assert first_batch.status == "completed"
    assert second_batch.status == "completed_with_rejections"
    assert _count(db, TechnicalDocument) == 1
    assert _count(db, StoredFile) == 1
    assert len(_audits(db, action="upload", batch_id=first_batch.id)) == 1
    assert len(_audits(db, action="upload_rejected", batch_id=second_batch.id)) == 1
    assert scanner.calls == [payload]
