from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from test_signed_physical_model_lock_amendment import NOW
from test_signed_physical_model_lock_replacement import (
    _executed_amendment,
    _replacement_manifest,
)

from classifire.models import AuditEvent, Opening, Service
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentOutcome,
    PhysicalModelLockReplacementAdmission,
    ServiceOpeningLink,
)
from classifire.services.signed_physical_model_lock_replacement_admission import (
    SignedPhysicalModelLockReplacementAdmissionError,
    preflight_registered_signed_physical_model_lock_replacement,
    register_signed_physical_model_lock_replacement_admission,
)


def _register(db, manifest, public_key, *, now=NOW):  # type: ignore[no-untyped-def]
    return register_signed_physical_model_lock_replacement_admission(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="replacement-lock-p256-01",
        operator_reference="Synthetic human replacement-lock registrar",
        now=now,
    )


def test_replacement_lock_admission_records_exact_evidence_without_creating_lock() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        lock_count_before = db.scalar(select(func.count(PhysicalModelLock.id)))
        outcome_count_before = db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id)))
        opening_count_before = db.scalar(select(func.count(Opening.id)))
        service_count_before = db.scalar(select(func.count(Service.id)))
        link_count_before = db.scalar(select(func.count(ServiceOpeningLink.id)))

        admission, created = _register(db, manifest, public_key)

        assert created is True
        assert admission.replacement_lock_admission_id == manifest[
            "replacement_lock_admission_id"
        ]
        assert admission.amendment_outcome_id == outcome.id
        assert admission.superseded_lock_id == old_lock.id
        assert admission.replacement_lock_content_hash == outcome.post_physical_model_content_hash
        assert admission.replacement_lock_envelope_sha256 == hashlib.sha256(
            admission.replacement_lock_envelope_json.encode("utf-8")
        ).hexdigest().upper()
        assert admission.preflight_receipt_sha256 == hashlib.sha256(
            admission.preflight_receipt_json.encode("utf-8")
        ).hexdigest().upper()
        receipt = json.loads(admission.preflight_receipt_json)
        assert receipt["schema"] == (
            "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-REPLACEMENT-LOCK-PREFLIGHT-v1"
        )
        assert receipt["physical_model_lock_created"] is False
        assert receipt["downstream_authority_granted"] is False
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_before == 1
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id))) == (
            outcome_count_before
        )
        assert db.scalar(select(func.count(Opening.id))) == opening_count_before
        assert db.scalar(select(func.count(Service.id))) == service_count_before
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == link_count_before
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before + 1
        assert old_lock.invalidated_at is not None
        assert not db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.invalidated_at.is_(None))
        ).all()

        replay, replay_created = _register(db, manifest, public_key)

        assert replay.id == admission.id
        assert replay_created is False
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before + 1


def test_registered_replacement_lock_admission_rehydrates_without_writing() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        admission, created = _register(db, manifest, public_key)
        assert created is True
        db.commit()
        db.expire_all()
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        binding = preflight_registered_signed_physical_model_lock_replacement(
            db,
            replacement_lock_admission_id=admission.replacement_lock_admission_id,
            expected_replacement_lock_envelope_sha256=(
                admission.replacement_lock_envelope_sha256
            ),
            pinned_public_key=public_key,
            expected_issuer="classifire-governance",
            expected_key_id="replacement-lock-p256-01",
            now=NOW,
        )

        assert binding.admission_record_id == admission.id
        assert binding.preflight_receipt.amendment_outcome_id == outcome.id
        assert binding.preflight_receipt.replacement_lock_content_hash == (
            outcome.post_physical_model_content_hash
        )
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as mismatch:
            preflight_registered_signed_physical_model_lock_replacement(
                db,
                replacement_lock_admission_id=admission.replacement_lock_admission_id,
                expected_replacement_lock_envelope_sha256="0" * 64,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="replacement-lock-p256-01",
                now=NOW,
            )
        assert mismatch.value.code == "REPLACEMENT_LOCK_ADMISSION_BINDING_INVALID"


def test_replacement_lock_admission_rejects_conflicting_manifest_for_same_id() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        _record, created = _register(db, manifest, public_key)
        assert created is True
        conflicting, conflicting_public_key = _replacement_manifest(
            db,
            estimate,
            old_lock,
            amendment_admission,
            outcome,
            replacement_lock_admission_id=manifest["replacement_lock_admission_id"],
            replacement_lock_reason="A different signed replacement approval is not a replay.",
        )

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as rejected:
            _register(db, conflicting, conflicting_public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_REPLAY_CONFLICT"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 1


def test_replacement_lock_admission_allows_fresh_separately_signed_reapproval() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        _record, created = _register(db, manifest, public_key)
        assert created is True
        second, second_public_key = _replacement_manifest(
            db,
            estimate,
            old_lock,
            amendment_admission,
            outcome,
            replacement_lock_reason="A second approval cannot replace the first journal record.",
        )

        second_record, second_created = _register(db, second, second_public_key)

        assert second_created is True
        assert second_record.id != _record.id
        assert second_record.amendment_outcome_id == _record.amendment_outcome_id
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 2


def test_replacement_lock_admission_replay_rejects_corrupt_retained_receipt() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        admission, created = _register(db, manifest, public_key)
        assert created is True
        admission.preflight_receipt_json = "{}"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as rejected:
            _register(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_ADMISSION_CORRUPT"


def test_replacement_lock_admission_reconstructs_receipt_semantics() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        admission, created = _register(db, manifest, public_key)
        assert created is True
        receipt = json.loads(admission.preflight_receipt_json)
        receipt["service_count"] = 999
        admission.preflight_receipt_json = json.dumps(
            receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        admission.preflight_receipt_sha256 = hashlib.sha256(
            admission.preflight_receipt_json.encode("utf-8")
        ).hexdigest().upper()
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as rejected:
            _register(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_ADMISSION_CORRUPT"


def test_replacement_lock_admission_rejects_expired_candidate_before_journaling() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as rejected:
            _register(db, manifest, public_key, now=NOW + timedelta(minutes=11))

        assert rejected.value.code == "REPLACEMENT_LOCK_EXPIRED"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_replacement_lock_admission_requires_accountable_operator_before_writing() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(
            db, estimate, old_lock, amendment_admission, outcome
        )
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockReplacementAdmissionError) as rejected:
            register_signed_physical_model_lock_replacement_admission(
                db,
                manifest=manifest,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="replacement-lock-p256-01",
                operator_reference=" ",
                now=NOW,
            )

        assert rejected.value.code == "REPLACEMENT_LOCK_OPERATOR_INVALID"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementAdmission.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before
