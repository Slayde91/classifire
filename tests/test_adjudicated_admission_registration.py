from __future__ import annotations

import pytest
from physical_foundation_support import add_estimate, physical_session
from sqlalchemy import func, select
from test_adjudicated_admission import NOW, _fixture

from classifire.models import AuditEvent, Opening, Service
from classifire.physical_models import PhysicalModelAdmission, PhysicalModelLock, ServiceOpeningLink
from classifire.services.adjudicated_admission_registration import (
    AdmissionRegistrationError,
    register_verified_admission,
)


def _register(db, estimate, manifest, public_key, payload):  # type: ignore[no-untyped-def]
    return register_verified_admission(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_project_id=estimate.project_id,
        expected_estimate_id=estimate.id,
        expected_preflight_receipt_sha256="A" * 64,
        submission_payload=payload,
        expected_protected_state_fingerprint="B" * 64,
        expected_protected_state_fingerprint_version="CLASSIFIRE-PROTECTED-STATE-v1",
        expected_artifact_digests={"adjudicated_proposal": "C" * 64},
        expected_policy_versions={"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
        expected_issuer="slayde-tana",
        expected_key_id="android-p256-production-1",
        operator_reference="CHG-ADMISSION-001",
        now=NOW,
    )


def test_registration_records_only_verified_admission_and_audit() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        manifest, public_key, payload = _fixture(
            project_id=estimate.project_id, estimate_id=estimate.id
        )
        record, created = _register(db, estimate, manifest, public_key, payload)

        assert created
        assert record.state == "issued"
        assert db.scalar(select(func.count(PhysicalModelAdmission.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == 1
        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(Service.id))) == 0
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0

        replay, replay_created = _register(db, estimate, manifest, public_key, payload)
        assert replay.id == record.id
        assert replay_created is False


def test_registration_rejects_wrong_project_before_any_journal_write() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        manifest, public_key, payload = _fixture(
            project_id=estimate.project_id, estimate_id=estimate.id
        )
        with pytest.raises(AdmissionRegistrationError) as rejected:
            register_verified_admission(
                db,
                manifest=manifest,
                pinned_public_key=public_key,
                expected_project_id="00000000-0000-0000-0000-000000000000",
                expected_estimate_id=estimate.id,
                expected_preflight_receipt_sha256="A" * 64,
                submission_payload=payload,
                expected_protected_state_fingerprint="B" * 64,
                expected_protected_state_fingerprint_version="CLASSIFIRE-PROTECTED-STATE-v1",
                expected_artifact_digests={"adjudicated_proposal": "C" * 64},
                expected_policy_versions={"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
                expected_issuer="slayde-tana",
                expected_key_id="android-p256-production-1",
                operator_reference="CHG-ADMISSION-002",
                now=NOW,
            )
        assert rejected.value.code == "ADMISSION_BINDING_MISMATCH"
        assert db.scalar(select(func.count(PhysicalModelAdmission.id))) == 0
