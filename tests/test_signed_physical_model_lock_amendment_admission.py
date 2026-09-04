from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from test_signed_physical_model_lock_amendment import NOW, _manifest
from test_signed_physical_model_lock_amendment_preflight import _prepared_preflight

from classifire.models import AuditEvent, Opening, Service
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentAdmission,
    ServiceOpeningLink,
)
from classifire.services.signed_physical_model_lock_amendment_admission import (
    SignedPhysicalModelLockAmendmentAdmissionError,
    preflight_registered_signed_physical_model_lock_amendment,
    register_signed_physical_model_lock_amendment_admission,
)


def _register(db, payload, manifest, public_key, *, now=NOW):  # type: ignore[no-untyped-def]
    return register_signed_physical_model_lock_amendment_admission(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="amendment-p256-01",
        amendment_submission_payload=payload,
        operator_reference="Synthetic human governance registrar",
        now=now,
    )


def test_signed_amendment_admission_records_exact_evidence_without_execution() -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        lock_count_before = db.scalar(select(func.count(PhysicalModelLock.id)))
        opening_count_before = db.scalar(select(func.count(Opening.id)))
        service_count_before = db.scalar(select(func.count(Service.id)))
        link_count_before = db.scalar(select(func.count(ServiceOpeningLink.id)))

        admission, created = _register(db, payload, manifest, public_key)

        assert created is True
        assert admission.amendment_admission_id == manifest["amendment_admission_id"]
        assert admission.target_lock_id == lock.id
        assert admission.target_lock_content_hash == lock.content_hash
        assert (
            admission.amendment_envelope_sha256
            == hashlib.sha256(admission.amendment_envelope_json.encode("utf-8")).hexdigest().upper()
        )
        assert (
            admission.preflight_receipt_sha256
            == hashlib.sha256(admission.preflight_receipt_json.encode("utf-8")).hexdigest().upper()
        )
        assert json.loads(admission.preflight_receipt_json)["schema"] == (
            "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-LOCK-AMENDMENT-PREFLIGHT-v1"
        )
        assert json.loads(admission.amendment_submission_payload_json) == payload
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_before
        assert db.scalar(select(func.count(Opening.id))) == opening_count_before
        assert db.scalar(select(func.count(Service.id))) == service_count_before
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == link_count_before
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before + 1

        replay, replay_created = _register(db, payload, manifest, public_key)

        assert replay.id == admission.id
        assert replay_created is False
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before + 1


def test_registered_signed_amendment_preflight_rehydrates_without_writing() -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, created = _register(db, payload, manifest, public_key)
        assert created is True
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        binding = preflight_registered_signed_physical_model_lock_amendment(
            db,
            amendment_admission_id=admission.amendment_admission_id,
            expected_amendment_envelope_sha256=admission.amendment_envelope_sha256,
            pinned_public_key=public_key,
            expected_issuer="classifire-governance",
            expected_key_id="amendment-p256-01",
            now=NOW,
        )

        assert binding.admission_record_id == admission.id
        assert binding.amendment_submission.model_dump(mode="json") == payload
        assert binding.preflight_receipt.target_lock_id == lock.id
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before
        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as mismatched:
            preflight_registered_signed_physical_model_lock_amendment(
                db,
                amendment_admission_id=admission.amendment_admission_id,
                expected_amendment_envelope_sha256="0" * 64,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="amendment-p256-01",
                now=NOW,
            )
        assert mismatched.value.code == "AMENDMENT_ADMISSION_BINDING_INVALID"
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_admission_rejects_a_new_manifest_for_the_same_id() -> None:
    with physical_session() as db:
        estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        _record, created = _register(db, payload, manifest, public_key)
        assert created is True
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        conflicting, conflicting_public_key = _manifest(
            db,
            estimate,
            lock,
            payload,
            manifest["visual_validation_receipt_sha256"],
            amendment_admission_id=manifest["amendment_admission_id"],
            amendment_reason="A separately signed but conflicting correction is not a replay.",
        )

        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as rejected:
            _register(db, payload, conflicting, conflicting_public_key)

        assert rejected.value.code == "AMENDMENT_REPLAY_CONFLICT"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_admission_replay_rejects_corrupt_retained_payload() -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        admission, created = _register(db, payload, manifest, public_key)
        assert created is True
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        admission.amendment_submission_payload_json = "{}"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as rejected:
            _register(db, payload, manifest, public_key)

        assert rejected.value.code == "AMENDMENT_ADMISSION_CORRUPT"
        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as retained:
            preflight_registered_signed_physical_model_lock_amendment(
                db,
                amendment_admission_id=admission.amendment_admission_id,
                expected_amendment_envelope_sha256=admission.amendment_envelope_sha256,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="amendment-p256-01",
                now=NOW,
            )
        assert retained.value.code == "AMENDMENT_ADMISSION_CORRUPT"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_admission_rejects_expired_candidate_before_journaling() -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as rejected:
            _register(db, payload, manifest, public_key, now=NOW + timedelta(minutes=11))

        assert rejected.value.code == "AMENDMENT_EXPIRED"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_admission_requires_an_accountable_operator_before_writing() -> None:
    with physical_session() as db:
        _estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockAmendmentAdmissionError) as rejected:
            register_signed_physical_model_lock_amendment_admission(
                db,
                manifest=manifest,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="amendment-p256-01",
                amendment_submission_payload=payload,
                operator_reference=" ",
                now=NOW,
            )

        assert rejected.value.code == "AMENDMENT_OPERATOR_INVALID"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLockAmendmentAdmission.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before
