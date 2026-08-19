from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.agent_security import provision_agent_principal
from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelAdmission,
    PhysicalModelInitialSubmission,
    PhysicalModelLock,
    ServiceOpeningLink,
)
from classifire.config import Settings, get_settings
from classifire.db import Base, get_db
from classifire.models import Estimate, Opening, Project, Service
from classifire.physical_model_submission_schema import AgentInitialPhysicalModelInput
from classifire.services.adjudicated_admission import (
    ADJUDICATED_ADMISSION_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
    ADJUDICATED_ADMISSION_PURPOSE,
    ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM,
    admission_signing_bytes,
    normalised_submission_payload_sha256,
)
from classifire.services.adjudicated_physical_submission import (
    CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_STATUS,
    ControlledPhysicalSubmissionError,
    controlled_writer_implementation_hashes,
    execute_adjudicated_initial_submission,
    preflight_admission_binding,
    register_adjudicated_admission,
)
from classifire.services.protected_state_fingerprint import (
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)

NOW = datetime(2026, 8, 18, 0, 30, tzinfo=UTC)
ISSUER = "governance.classifire"
KEY_ID = "physical-admission-v1"
IDEMPOTENCY_KEY = "local-only-admission-test-key-0001"


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed(db: Session) -> tuple[Estimate, str, str]:
    project = Project(reference="ADMISSION-PROJECT", name="Admission test project")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="ADMISSION-ESTIMATE",
        title="Admission test estimate",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    defect = Defect(
        estimate_id=estimate.id,
        external_defect_id="D-001",
        defect_code="D-001",
        description="Synthetic defect",
        location="Synthetic location",
    )
    db.add(defect)
    db.flush()
    db.add(
        EvidenceSource(
            estimate_id=estimate.id,
            defect_id=defect.id,
            evidence_type="report",
            source_reference="synthetic-report",
            sha256="A" * 64,
        )
    )
    principal, _token = provision_agent_principal(
        db,
        agent_id="cf-adjudicated-physical-writer",
    )
    db.commit()
    return estimate, principal.id, principal.agent_id


def _payload() -> dict[str, object]:
    return {
        "openings": [
            {
                "opening_code": "O-001",
                "external_defect_id": "D-001",
                "location": "Synthetic location",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
                "diameter_mm": "100",
                "frl": "-/60/60",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "service_type": "pipe",
                "material": "PVC",
                "outside_diameter_mm": "25",
                "quantity": "1",
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
            }
        ],
    }


def _preflight_bytes(db: Session, estimate: Estimate) -> bytes:
    # Model a separately generated, persisted preflight receipt rather than
    # relying on unrounded Decimal values still held by a newly seeded ORM row.
    db.flush()
    db.expire(
        estimate,
        attribute_names=["tax_rate", "subtotal_ex_tax", "tax_total", "total_incl_tax"],
    )
    snapshot = protected_state_snapshot_from_session(db, estimate.id)
    payload = _payload()
    receipt = {
        "schema": PREFLIGHT_SCHEMA,
        "status": PREFLIGHT_STATUS,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": "source-run-001",
        "adjudicated_receipt_run_id": "source-run-001-adjudicated-v1",
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "candidate_eligible": True,
        "submission_eligible": False,
        "lock_eligible": False,
        "controlled_writer_implemented": True,
        "controlled_writer_policy_version": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "normalised_submission_payload": payload,
        "normalised_submission_payload_sha256": normalised_submission_payload_sha256(
            AgentInitialPhysicalModelInput.model_validate(payload).model_dump(mode="json")
        ),
        "protected_state": {
            "fingerprint_version": snapshot["fingerprint_version"],
            "fingerprint": protected_state_fingerprint(snapshot),
            "component_fingerprints": protected_component_fingerprints(snapshot),
            "counts": protected_state_counts(snapshot),
        },
        "artifact_references": {"adjudicated_proposal": {"sha256": "B" * 64}},
        "full_resolution_visual_evidence": {"verified_full_resolution_count": 1},
        "visual_adjudication_basis": {"status": "PASS"},
        "implementation": controlled_writer_implementation_hashes(),
    }
    return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _new_private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _public_key(private_key: ec.EllipticCurvePrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _base64url(raw)


def _signed_manifest(
    *,
    private_key: ec.EllipticCurvePrivateKey,
    estimate: Estimate,
    preflight_bytes: bytes,
    now: datetime = NOW,
) -> dict[str, object]:
    binding = preflight_admission_binding(preflight_bytes)
    timestamp = now.astimezone(UTC).replace(microsecond=0)
    manifest: dict[str, object] = {
        "schema": ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
        "admission_id": "c14663d4-ae8d-4a77-8ae9-51a4402520f1",
        "purpose": ADJUDICATED_ADMISSION_PURPOSE,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "preflight_receipt_sha256": binding.raw_sha256,
        "normalised_submission_payload_sha256": binding.payload_sha256,
        "protected_state_fingerprint": binding.protected_state_fingerprint,
        "protected_state_fingerprint_version": binding.protected_state_fingerprint_version,
        "source_run_id": binding.source_run_id,
        "adjudicated_run_id": binding.adjudicated_run_id,
        "artifact_digests": binding.artifact_digests,
        "policy_versions": binding.policy_versions,
        "issuer": ISSUER,
        "key_id": KEY_ID,
        "issued_at": (timestamp - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (timestamp + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "signature_algorithm": ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
        "signature": _base64url(b"\x30\x06\x02\x01\x01\x02\x01\x01"),
    }
    manifest["signature"] = _base64url(
        private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    )
    return manifest


def _registered_admission(
    db: Session,
    *,
    estimate: Estimate,
    private_key: ec.EllipticCurvePrivateKey,
    now: datetime = NOW,
) -> PhysicalModelAdmission:
    preflight_bytes = _preflight_bytes(db, estimate)
    admission = register_adjudicated_admission(
        db,
        manifest=_signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
            now=now,
        ),
        preflight_receipt_bytes=preflight_bytes,
        pinned_public_keys={KEY_ID: _public_key(private_key)},
        issuer_key_ids={ISSUER: [KEY_ID]},
        now=now,
    )
    db.commit()
    return admission


def _execute(
    db: Session,
    *,
    estimate: Estimate,
    principal_id: str,
    principal_agent_id: str,
    private_key: ec.EllipticCurvePrivateKey,
    admission_id: str,
    idempotency_key: str = IDEMPOTENCY_KEY,
) -> object:
    return execute_adjudicated_initial_submission(
        db,
        estimate_id=estimate.id,
        admission_id=admission_id,
        idempotency_key=idempotency_key,
        principal_id=principal_id,
        principal_agent_id=principal_agent_id,
        pinned_public_keys={KEY_ID: _public_key(private_key)},
        issuer_key_ids={ISSUER: [KEY_ID]},
        now=NOW,
    )


def test_signed_admission_creates_exact_model_once_replays_and_never_locks() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)

        result = _execute(
            db,
            estimate=estimate,
            principal_id=principal_id,
            principal_agent_id=agent_id,
            private_key=private_key,
            admission_id=admission.admission_id,
        )
        replay = _execute(
            db,
            estimate=estimate,
            principal_id=principal_id,
            principal_agent_id=agent_id,
            private_key=private_key,
            admission_id=admission.admission_id,
        )

        assert result.replayed is False
        assert replay.replayed is True
        assert replay.submission_id == result.submission_id
        assert result.receipt["physical_model_lock_created"] is False
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is not None
        assert db.scalar(select(Service)) is not None
        assert db.scalar(select(ServiceOpeningLink)) is not None
        assert (
            db.scalar(select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate.id))
            is None
        )
        journal = db.scalar(select(PhysicalModelInitialSubmission))
        assert journal is not None
        assert journal.admission_record_id == admission.id
        assert admission.state == "consumed"


def test_registration_rejects_legacy_ed25519_manifest_without_journalling() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, _principal_id, _agent_id = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        binding = preflight_admission_binding(preflight_bytes)
        legacy_key = Ed25519PrivateKey.generate()
        manifest: dict[str, object] = {
            "schema": ADJUDICATED_ADMISSION_MANIFEST_SCHEMA,
            "admission_id": "d14663d4-ae8d-4a77-8ae9-51a4402520f1",
            "purpose": ADJUDICATED_ADMISSION_PURPOSE,
            "project_id": estimate.project_id,
            "estimate_id": estimate.id,
            "preflight_receipt_sha256": binding.raw_sha256,
            "normalised_submission_payload_sha256": binding.payload_sha256,
            "protected_state_fingerprint": binding.protected_state_fingerprint,
            "protected_state_fingerprint_version": binding.protected_state_fingerprint_version,
            "source_run_id": binding.source_run_id,
            "adjudicated_run_id": binding.adjudicated_run_id,
            "artifact_digests": dict(binding.artifact_digests),
            "policy_versions": dict(binding.policy_versions),
            "issuer": ISSUER,
            "key_id": KEY_ID,
            "issued_at": "2026-08-18T00:29:00Z",
            "expires_at": "2026-08-18T00:35:00Z",
            "signature_algorithm": ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM,
            "signature": _base64url(b"\x00" * 64),
        }
        manifest["signature"] = _base64url(legacy_key.sign(admission_signing_bytes(manifest)))

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            register_adjudicated_admission(
                db,
                manifest=manifest,
                preflight_receipt_bytes=preflight_bytes,
                pinned_public_keys={KEY_ID: _public_key(_new_private_key())},
                issuer_key_ids={ISSUER: [KEY_ID]},
                now=NOW,
            )

        assert raised.value.code == "ADMISSION_PROTOCOL_UNSUPPORTED"
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_state_drift_burns_admission_without_creating_canonical_rows() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)
        estimate.title = "Changed after signed preflight"
        db.commit()

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            _execute(
                db,
                estimate=estimate,
                principal_id=principal_id,
                principal_agent_id=agent_id,
                private_key=private_key,
                admission_id=admission.admission_id,
            )

        assert raised.value.code == "ADMISSION_STATE_DRIFT"
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is None
        db.refresh(admission)
        assert admission.state == "stale"


def test_persisted_payload_tamper_is_rejected_without_model_rows() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)
        tampered = json.loads(admission.normalised_submission_payload_json)
        tampered["services"][0]["material"] = "STEEL"
        db.execute(
            update(PhysicalModelAdmission)
            .where(PhysicalModelAdmission.id == admission.id)
            .values(normalised_submission_payload_json=json.dumps(tampered, sort_keys=True))
        )
        db.commit()

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            _execute(
                db,
                estimate=estimate,
                principal_id=principal_id,
                principal_agent_id=agent_id,
                private_key=private_key,
                admission_id=admission.admission_id,
            )

        assert raised.value.code == "ADMISSION_BINDING_MISMATCH"
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is None
        db.refresh(admission)
        assert admission.state == "rejected"


@pytest.mark.parametrize(
    "implementation_key",
    tuple(controlled_writer_implementation_hashes()),
)
def test_preflight_generated_for_another_writer_implementation_is_rejected(
    implementation_key: str,
) -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, _principal_id, _agent_id = _seed(db)
        receipt = json.loads(_preflight_bytes(db, estimate).decode("utf-8"))
        receipt["implementation"][implementation_key] = "F" * 64

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            preflight_admission_binding(
                json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
            )

        assert raised.value.code == "PREFLIGHT_IMPLEMENTATION_MISMATCH"


def test_writer_implementation_hashes_pin_current_preflight_script() -> None:
    expected_hash = (
        hashlib.sha256(
            (
                Path(__file__).resolve().parents[1]
                / "scripts"
                / "preflight_adjudicated_canonicalisation.py"
            ).read_bytes()
        )
        .hexdigest()
        .upper()
    )

    assert controlled_writer_implementation_hashes()["preflight_script_sha256"] == expected_hash


def test_issuer_cannot_use_a_key_pinned_only_for_another_issuer() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, _principal_id, _agent_id = _seed(db)
        private_key = _new_private_key()
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
        manifest["issuer"] = "other.governance.classifire"
        manifest["signature"] = _base64url(
            private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
        )

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            register_adjudicated_admission(
                db,
                manifest=manifest,
                preflight_receipt_bytes=preflight_bytes,
                pinned_public_keys={KEY_ID: _public_key(private_key)},
                issuer_key_ids={
                    ISSUER: [KEY_ID],
                    "other.governance.classifire": ["other-governance-key"],
                },
                now=NOW,
            )

        assert raised.value.code == "ADMISSION_SIGNER_UNTRUSTED"


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("project_id", "b8c30c4a-48c8-4ee9-a69c-1d21df7fd65f"),
        ("estimate_id", "c8c30c4a-48c8-4ee9-a69c-1d21df7fd65f"),
    ),
)
def test_manifest_identity_must_match_the_hash_bound_preflight(
    field: str,
    value: str,
) -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, _principal_id, _agent_id = _seed(db)
        private_key = _new_private_key()
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
        manifest[field] = value
        manifest["signature"] = _base64url(
            private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
        )

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            register_adjudicated_admission(
                db,
                manifest=manifest,
                preflight_receipt_bytes=preflight_bytes,
                pinned_public_keys={KEY_ID: _public_key(private_key)},
                issuer_key_ids={ISSUER: [KEY_ID]},
                now=NOW,
            )

        assert raised.value.code == "ADMISSION_BINDING_MISMATCH"


def _test_app() -> tuple[FastAPI, sessionmaker[Session]]:
    from classifire.api.agent_intake_physical import router

    factory = _session_factory()
    app = FastAPI()
    app.include_router(router)

    def override_db():  # type: ignore[no-untyped-def]
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    return app, factory


def _headers(agent_id: str, token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Classifire-Agent-ID": agent_id}


def test_api_rejects_bare_generic_payload_and_only_allows_bound_request() -> None:
    app, factory = _test_app()
    with factory() as db:
        estimate, _writer_id, _writer_agent = _seed(db)
        legacy_principal, legacy_token = provision_agent_principal(db, agent_id="cf-physical-model")
        writer_principal, writer_token = provision_agent_principal(
            db, agent_id="cf-adjudicated-physical-writer"
        )
        private_key = _new_private_key()
        admission = _registered_admission(
            db,
            estimate=estimate,
            private_key=private_key,
            now=datetime.now(UTC),
        )

    settings = Settings(
        adjudicated_initial_submission_enabled=True,
        adjudicated_admission_public_keys={KEY_ID: _public_key(private_key)},
        adjudicated_admission_issuer_key_ids={ISSUER: [KEY_ID]},
    )
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as client:
        raw = client.post(
            f"/api/v1/agent/estimates/{estimate.id}/physical-model/initial",
            headers=_headers(legacy_principal.agent_id, legacy_token),
            json=_payload(),
        )
        bound = client.post(
            f"/api/v1/agent/estimates/{estimate.id}/physical-model/initial",
            headers=_headers(writer_principal.agent_id, writer_token),
            json={"admission_id": admission.admission_id, "idempotency_key": IDEMPOTENCY_KEY},
        )
        lock = client.post(
            f"/api/v1/agent/estimates/{estimate.id}/physical-model/lock",
            headers=_headers(writer_principal.agent_id, writer_token),
            json={"reason": "must not lock"},
        )

    assert raw.status_code == 403
    assert bound.status_code == 200, bound.text
    assert bound.json()["receipt"]["physical_model_lock_created"] is False
    assert lock.status_code == 403
    with factory() as db:
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is not None


def test_replay_with_a_different_idempotency_key_is_rejected_without_second_write() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)
        _execute(
            db,
            estimate=estimate,
            principal_id=principal_id,
            principal_agent_id=agent_id,
            private_key=private_key,
            admission_id=admission.admission_id,
        )

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            _execute(
                db,
                estimate=estimate,
                principal_id=principal_id,
                principal_agent_id=agent_id,
                private_key=private_key,
                admission_id=admission.admission_id,
                idempotency_key="local-only-admission-test-key-different",
            )

        assert raised.value.code == "SUBMISSION_IDEMPOTENCY_CONFLICT"
        assert db.scalar(select(PhysicalModelInitialSubmission)) is not None
        assert len(list(db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)))) == 1


def test_replay_cannot_be_retrieved_through_another_estimate_route() -> None:
    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)
        _execute(
            db,
            estimate=estimate,
            principal_id=principal_id,
            principal_agent_id=agent_id,
            private_key=private_key,
            admission_id=admission.admission_id,
        )
        other_estimate = Estimate(
            project_id=estimate.project_id,
            revision=2,
            reference="ADMISSION-OTHER-ESTIMATE",
            title="Other estimate",
            status="draft",
        )
        db.add(other_estimate)
        db.commit()

        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            _execute(
                db,
                estimate=other_estimate,
                principal_id=principal_id,
                principal_agent_id=agent_id,
                private_key=private_key,
                admission_id=admission.admission_id,
            )

        assert raised.value.code == "ADMISSION_ESTIMATE_MISMATCH"
        assert db.scalar(select(Opening).where(Opening.estimate_id == other_estimate.id)) is None


def test_persistence_failure_rolls_back_rows_and_leaves_admission_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import classifire.services.adjudicated_physical_submission as submission_service

    factory = _session_factory()
    with factory() as db:
        estimate, principal_id, agent_id = _seed(db)
        private_key = _new_private_key()
        admission = _registered_admission(db, estimate=estimate, private_key=private_key)

        def fail_write(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("synthetic persistence failure")

        monkeypatch.setattr(submission_service, "_create_canonical_model", fail_write)
        with pytest.raises(ControlledPhysicalSubmissionError) as raised:
            _execute(
                db,
                estimate=estimate,
                principal_id=principal_id,
                principal_agent_id=agent_id,
                private_key=private_key,
                admission_id=admission.admission_id,
            )

        assert raised.value.code == "SUBMISSION_TRANSACTION_FAILED"
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is None
        assert db.scalar(select(PhysicalModelInitialSubmission)) is None
        db.refresh(admission)
        assert admission.state == "issued"


def test_api_feature_flag_rejects_even_a_dedicated_writer_principal() -> None:
    app, factory = _test_app()
    with factory() as db:
        estimate, _principal_id, agent_id = _seed(db)
        principal, token = provision_agent_principal(db, agent_id=agent_id)
        db.commit()

    app.dependency_overrides[get_settings] = lambda: Settings(
        adjudicated_initial_submission_enabled=False
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/agent/estimates/{estimate.id}/physical-model/initial",
            headers=_headers(principal.agent_id, token),
            json={
                "admission_id": "c14663d4-ae8d-4a77-8ae9-51a4402520f1",
                "idempotency_key": IDEMPOTENCY_KEY,
            },
        )

    assert response.status_code == 503
    with factory() as db:
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is None
