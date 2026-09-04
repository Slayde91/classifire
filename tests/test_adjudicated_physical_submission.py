from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from physical_foundation_support import add_estimate, add_evidence, physical_session
from sqlalchemy import func, select

from classifire.models import Opening, Service
from classifire.physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from classifire.physical_models import (
    PhysicalModelAdmission,
    PhysicalModelLock,
    PhysicalModelSubmissionReceipt,
    ServiceOpeningLink,
)
from classifire.services.adjudicated_admission import normalised_submission_payload_sha256
from classifire.services.adjudicated_physical_submission import (
    ControlledPhysicalSubmissionError,
    submit_recorded_initial_physical_model,
)
from classifire.services.canonical_submission_state import initial_submission_state
from classifire.services.physical_defects import bind_canonical_defect
from classifire.services.physical_scope import assess_physical_model_completeness


def _record_admission(
    db,
    estimate,
    payload: InitialCanonicalPhysicalSubmission,  # type: ignore[no-untyped-def]
):
    """Record a synthetic sealed admission after its actual state preflight."""
    state = initial_submission_state(db, estimate_id=estimate.id)
    now = datetime.now(UTC)
    admission = PhysicalModelAdmission(
        admission_id=str(uuid4()),
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        purpose="initial_adjudicated_canonicalisation",
        preflight_receipt_sha256="A" * 64,
        normalised_submission_payload_sha256=normalised_submission_payload_sha256(
            payload.model_dump(mode="json")
        ),
        normalised_submission_payload_json=json.dumps(payload.model_dump(mode="json")),
        protected_state_fingerprint=state.fingerprint,
        protected_state_fingerprint_version="CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1",
        source_run_id="source-run-1",
        adjudicated_run_id="adjudicated-run-1",
        artifact_digests={"proposal": "C" * 64},
        policy_versions={"physical": "v1"},
        admission_envelope_json="{}",
        admission_envelope_sha256="D" * 64,
        issuer_id="slayde-tana",
        signing_key_id="test-key",
        signature_algorithm="ECDSA_P256_SHA256",
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        state="issued",
    )
    db.add(admission)
    db.flush()
    return admission


def _admission(db, estimate):  # type: ignore[no-untyped-def]
    defect = bind_canonical_defect(db, estimate, "D-001")
    assert defect is not None
    add_evidence(db, estimate)
    payload = InitialCanonicalPhysicalSubmission.model_validate(
        {
            "openings": [
                {
                    "opening_code": "O-001",
                    "canonical_defect_id": defect.id,
                    "opening_type": "service_penetration",
                }
            ],
            "services": [{"service_code": "S-001", "service_type": "pipe"}],
            "service_opening_links": [{"service_code": "S-001", "opening_code": "O-001"}],
        }
    )
    return _record_admission(db, estimate, payload)


def test_writer_creates_only_the_sealed_model_once() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        admission_id = admission.admission_id
        db.commit()
        db.expire_all()
        result = submit_recorded_initial_physical_model(db, admission_id=admission_id)
        assert result["opening_count"] == 1
        assert result["canonical_write_performed"] is True
        assert result["physical_model_lock_created"] is False
        assert isinstance(result["receipt_sha256"], str) and len(result["receipt_sha256"]) == 64
        assert db.scalar(select(func.count(Opening.id))) == 1
        assert db.scalar(select(func.count(Service.id))) == 1
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 1
        stored_receipt = db.scalar(select(PhysicalModelSubmissionReceipt))
        assert stored_receipt is not None
        assert stored_receipt.admission_id == admission.admission_id
        assert stored_receipt.receipt_sha256 == result["receipt_sha256"]
        assert json.loads(stored_receipt.receipt_json)["canonical_write_performed"] is True
        assert admission.state == "consumed"
        with pytest.raises(ControlledPhysicalSubmissionError, match="NOT_AVAILABLE"):
            submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)


def test_writer_accepts_an_all_blank_sealed_model_without_inventing_services() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        defect = bind_canonical_defect(db, estimate, "D-BLANK")
        assert defect is not None
        add_evidence(db, estimate)
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            {
                "openings": [
                    {
                        "opening_code": "O-BLANK-001",
                        "canonical_defect_id": defect.id,
                        "opening_type": "blank opening seal",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "orientation": "horizontal",
                        "frl": "-/120/120",
                    },
                    {
                        "opening_code": "O-BLANK-002",
                        "canonical_defect_id": defect.id,
                        "opening_type": "blank_core_hole",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "orientation": "horizontal",
                        "frl": "-/120/120",
                    },
                ],
                "services": [],
                "service_opening_links": [],
            }
        )
        admission = _record_admission(db, estimate, payload)
        db.commit()

        result = submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)

        assert result["opening_count"] == 2
        assert result["service_count"] == 0
        assert result["service_opening_link_count"] == 0
        assert result["physical_model_lock_created"] is False
        assert db.scalar(select(func.count(Opening.id))) == 2
        assert db.scalar(select(func.count(Service.id))) == 0
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0
        completeness = assess_physical_model_completeness(db, estimate.id)
        assert completeness.complete
        assert {item.opening_type for item in completeness.openings} == {
            "blank_opening",
            "blank_core_hole",
        }
        assert all(item.blank_opening for item in completeness.openings)
        assert all(item.service_link_count == 0 for item in completeness.openings)


def test_writer_accepts_mixed_blank_and_multi_service_sealed_model() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        defect = bind_canonical_defect(db, estimate, "D-MIXED")
        assert defect is not None
        add_evidence(db, estimate)
        payload = InitialCanonicalPhysicalSubmission.model_validate(
            {
                "openings": [
                    {
                        "opening_code": "O-BLANK",
                        "canonical_defect_id": defect.id,
                        "opening_type": "blank_core_hole",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "orientation": "horizontal",
                        "frl": "-/120/120",
                    },
                    {
                        "opening_code": "O-SHARED",
                        "canonical_defect_id": defect.id,
                        "opening_type": "service_penetration",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "orientation": "horizontal",
                        "frl": "-/120/120",
                    },
                ],
                "services": [
                    {"service_code": "S-PIPE", "service_type": "pipe"},
                    {"service_code": "S-CONDUIT", "service_type": "conduit"},
                ],
                "service_opening_links": [
                    {"service_code": "S-PIPE", "opening_code": "O-SHARED"},
                    {"service_code": "S-CONDUIT", "opening_code": "O-SHARED"},
                ],
            }
        )
        admission = _record_admission(db, estimate, payload)
        db.commit()

        result = submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)

        assert result["opening_count"] == 2
        assert result["service_count"] == 2
        assert result["service_opening_link_count"] == 2
        openings = {
            item.opening_code: item
            for item in db.scalars(select(Opening).order_by(Opening.opening_code))
        }
        services = {item.service_code: item for item in db.scalars(select(Service))}
        assert services["S-PIPE"].opening_id == openings["O-SHARED"].id
        assert services["S-CONDUIT"].opening_id == openings["O-SHARED"].id
        links = list(db.scalars(select(ServiceOpeningLink)))
        assert {item.opening_id for item in links} == {openings["O-SHARED"].id}
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0
        completeness = assess_physical_model_completeness(db, estimate.id)
        assert completeness.complete
        rows = {item.opening_code: item for item in completeness.openings}
        assert rows["O-BLANK"].blank_opening
        assert rows["O-BLANK"].service_link_count == 0
        assert not rows["O-SHARED"].blank_opening
        assert rows["O-SHARED"].service_link_count == 2


def test_writer_refuses_when_the_preflight_state_changed() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        add_evidence(db, estimate)
        with pytest.raises(ControlledPhysicalSubmissionError, match="STATE_CHANGED"):
            submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)
        assert db.scalar(select(func.count(Opening.id))) == 0


def test_writer_refuses_expired_admission_without_writes() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        with pytest.raises(ControlledPhysicalSubmissionError) as rejected:
            submit_recorded_initial_physical_model(
                db, admission_id=admission.admission_id, now=admission.expires_at
            )
        assert rejected.value.code == "ADMISSION_EXPIRED"
        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 0
        assert admission.state == "issued"


def test_writer_refuses_modified_stored_payload_even_when_valid_json() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        changed = json.loads(admission.normalised_submission_payload_json)
        changed["services"][0]["material"] = "copper"
        admission.normalised_submission_payload_json = json.dumps(changed)
        with pytest.raises(ControlledPhysicalSubmissionError) as rejected:
            submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)
        assert rejected.value.code == "ADMISSION_PAYLOAD_HASH_MISMATCH"
        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(Service.id))) == 0
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 0
        assert admission.state == "issued"


def test_writer_rolls_back_all_changes_when_receipt_flush_fails() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        admission = _admission(db, estimate)
        db.add(
            PhysicalModelSubmissionReceipt(
                admission_record_id=admission.id,
                admission_id=admission.admission_id,
                project_id=admission.project_id,
                estimate_id=admission.estimate_id,
                normalised_submission_payload_sha256=admission.normalised_submission_payload_sha256,
                protected_state_fingerprint_before=admission.protected_state_fingerprint,
                opening_count=0,
                service_count=0,
                service_opening_link_count=0,
                canonical_write_performed=False,
                physical_model_lock_created=False,
                receipt_json="{}",
                receipt_sha256="E" * 64,
            )
        )
        db.flush()

        with pytest.raises(ControlledPhysicalSubmissionError) as rejected:
            submit_recorded_initial_physical_model(db, admission_id=admission.admission_id)
        assert rejected.value.code == "ADMISSION_WRITE_FAILED"

        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(Service.id))) == 0
        assert db.scalar(select(func.count(ServiceOpeningLink.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0
        assert admission.state == "issued"
