from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from physical_foundation_support import add_estimate, physical_session
from sqlalchemy import func, select, text
from test_phase8_adjudicated_payload import _artifacts as _phase8_artifacts

from classifire.models import Opening
from classifire.physical_models import PhysicalModelAdmission, PhysicalModelLock
from classifire.services.adjudicated_admission import (
    ADMISSION_MANIFEST_SCHEMA,
    ADMISSION_PURPOSE,
    ADMISSION_SIGNATURE_ALGORITHM,
    admission_signing_bytes,
)
from classifire.services.adjudicated_admission_registration import (
    AdmissionRegistrationError,
    register_verified_admission_from_preflight,
)
from classifire.services.adjudicated_preflight import (
    PREFLIGHT_SCHEMA,
    AdjudicatedPreflightError,
    build_adjudicated_preflight,
    parse_adjudicated_preflight,
    preflight_receipt_bytes,
)
from classifire.services.phase8_adjudicated_payload import derive_phase8_adjudicated_payload
from classifire.services.physical_defects import bind_canonical_defect

NOW = datetime(2026, 8, 20, 8, 0, tzinfo=UTC)


def _mark_clean_lineage(db) -> None:  # type: ignore[no-untyped-def]
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(64))"))
    db.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
        {"revision": "0045_draft_pricing_recipe_links"},
    )
    db.commit()


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signing_fixture(binding):  # type: ignore[no-untyped-def]
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = _base64url(
        private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    manifest = {
        "schema": ADMISSION_MANIFEST_SCHEMA,
        "admission_id": str(uuid4()),
        "purpose": ADMISSION_PURPOSE,
        "project_id": binding.project_id,
        "estimate_id": binding.estimate_id,
        "source_run_id": binding.source_run_id,
        "adjudicated_run_id": binding.adjudicated_run_id,
        "preflight_receipt_sha256": binding.receipt_sha256,
        "normalised_submission_payload_sha256": binding.submission_payload_sha256,
        "protected_state_fingerprint": binding.protected_state_fingerprint,
        "protected_state_fingerprint_version": binding.protected_state_fingerprint_version,
        "artifact_digests": binding.artifact_digests,
        "policy_versions": binding.policy_versions,
        "issuer": "classifire-governance",
        "key_id": "governance-p256-test-01",
        "issued_at": "2026-08-20T07:59:00Z",
        "expires_at": "2026-08-20T08:10:00Z",
        "signature_algorithm": ADMISSION_SIGNATURE_ALGORITHM,
        "signature": "AA",
    }
    signature = private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(signature)
    order = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
    if s > order // 2:
        signature = encode_dss_signature(r, order - s)
    manifest["signature"] = _base64url(signature)
    return manifest, public_key


def _build(db, estimate, tmp_path):  # type: ignore[no-untyped-def]
    _mark_clean_lineage(db)
    bind_canonical_defect(db, estimate, "D-001")
    proposal, final_state, diff, comparison = _phase8_artifacts(tmp_path, estimate.id)
    derived = derive_phase8_adjudicated_payload(
        db,
        estimate_id=estimate.id,
        adjudicated_proposal_path=proposal,
        adjudicated_final_state_path=final_state,
        adjudicated_diff_path=diff,
        human_comparison_path=comparison,
    )
    payload = derived.payload
    artifact_files = {
        "adjudicated_proposal": proposal,
        "adjudicated_final_state": final_state,
        "adjudicated_diff": diff,
        "human_adjudication_comparison": comparison,
    }
    payload_artifact = tmp_path / "canonical_submission_payload.json"
    payload_artifact.write_text(
        preflight_receipt_bytes(payload).decode("utf-8"),
        encoding="utf-8",
    )
    artifact_files["canonical_submission_payload"] = payload_artifact
    return build_adjudicated_preflight(
        db,
        estimate_id=estimate.id,
        submission_payload=payload,
        source_run_id=derived.source_run_id,
        adjudicated_run_id=derived.adjudicated_run_id,
        artifact_files=artifact_files,
        policy_versions={"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
        now=NOW,
    )


def test_preflight_is_no_write_and_binds_current_stack(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _build(db, estimate, tmp_path)
        raw = preflight_receipt_bytes(receipt)
        binding = parse_adjudicated_preflight(raw, now=NOW)

        assert receipt["schema"] == PREFLIGHT_SCHEMA
        assert receipt["canonical_write_performed"] is False
        assert receipt["database_write_performed"] is False
        assert receipt["gateway_call_performed"] is False
        assert receipt["lock_eligible"] is False
        assert binding.estimate_id == estimate.id
        assert binding.submission_payload_sha256 == receipt["normalised_submission_payload_sha256"]
        assert "preflight_implementation" in binding.artifact_digests
        assert db.query(Opening).filter(Opening.estimate_id == estimate.id).count() == 0


def test_preflight_rejects_implementation_pin_change(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _build(db, estimate, tmp_path)
        receipt["implementation_hashes"]["controlled_writer_module_sha256"] = "A" * 64
        with pytest.raises(AdjudicatedPreflightError) as rejected:
            parse_adjudicated_preflight(preflight_receipt_bytes(receipt), now=NOW)
        assert rejected.value.code == "PREFLIGHT_IMPLEMENTATION_MISMATCH"


def test_preflight_rejects_expired_receipt(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _build(db, estimate, tmp_path)
        with pytest.raises(AdjudicatedPreflightError) as rejected:
            parse_adjudicated_preflight(
                preflight_receipt_bytes(receipt),
                now=NOW + timedelta(minutes=16),
            )
        assert rejected.value.code == "PREFLIGHT_EXPIRED"


def test_preflight_rejects_nonempty_canonical_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        _mark_clean_lineage(db)
        defect = bind_canonical_defect(db, estimate, "D-001")
        db.add(
            Opening(
                estimate_id=estimate.id,
                opening_code="EXISTING",
                canonical_defect_id=defect.id,
            )
        )
        db.flush()
        proposal, final_state, diff, comparison = _phase8_artifacts(tmp_path, estimate.id)
        payload = {
            "openings": [
                {
                    "opening_code": "O-001",
                    "canonical_defect_id": defect.id,
                    "opening_type": "service_penetration",
                }
            ],
            "services": [
                {
                    "service_code": "S-001",
                    "service_type": "pipe",
                    "material": "PVC",
                    "quantity": "1",
                    "evidence_status": "confirmed",
                }
            ],
            "service_opening_links": [
                {
                    "service_code": "S-001",
                    "opening_code": "O-001",
                    "link_type": "penetrates",
                    "relationship_status": "confirmed",
                    "evidence_status": "confirmed",
                }
            ],
        }
        artifact_files = {
            "adjudicated_proposal": proposal,
            "adjudicated_final_state": final_state,
            "adjudicated_diff": diff,
            "human_adjudication_comparison": comparison,
        }
        payload_artifact = tmp_path / "canonical_submission_payload.json"
        payload_artifact.write_text(
            preflight_receipt_bytes(payload).decode("utf-8"),
            encoding="utf-8",
        )
        artifact_files["canonical_submission_payload"] = payload_artifact
        with pytest.raises(AdjudicatedPreflightError) as rejected:
            build_adjudicated_preflight(
                db,
                estimate_id=estimate.id,
                submission_payload=payload,
                source_run_id="source-run-001",
                adjudicated_run_id="adjudicated-run-001",
                artifact_files=artifact_files,
                policy_versions={"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
                now=NOW,
            )
        assert rejected.value.code == "PREFLIGHT_CANONICAL_STATE_NOT_EMPTY"


def test_registration_derives_all_bindings_from_current_preflight(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _build(db, estimate, tmp_path)
        raw = preflight_receipt_bytes(receipt)
        binding = parse_adjudicated_preflight(raw, now=NOW)
        manifest, public_key = _signing_fixture(binding)

        admission, created = register_verified_admission_from_preflight(
            db,
            manifest=manifest,
            preflight_receipt=raw,
            pinned_public_key=public_key,
            expected_issuer="classifire-governance",
            expected_key_id="governance-p256-test-01",
            operator_reference="CHG-PREFLIGHT-TEST-001",
            now=NOW,
        )

        assert created is True
        assert admission.admission_id == manifest["admission_id"]
        assert db.scalar(select(func.count(PhysicalModelAdmission.id))) == 1
        assert db.scalar(select(func.count(Opening.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0


def test_registration_rechecks_live_state_after_preflight(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _build(db, estimate, tmp_path)
        raw = preflight_receipt_bytes(receipt)
        binding = parse_adjudicated_preflight(raw, now=NOW)
        manifest, public_key = _signing_fixture(binding)
        defect_id = binding.submission_payload["openings"][0]["canonical_defect_id"]
        db.add(
            Opening(
                estimate_id=estimate.id,
                opening_code="STATE-DRIFT",
                canonical_defect_id=defect_id,
            )
        )
        db.flush()

        with pytest.raises(AdmissionRegistrationError) as rejected:
            register_verified_admission_from_preflight(
                db,
                manifest=manifest,
                preflight_receipt=raw,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="governance-p256-test-01",
                operator_reference="CHG-PREFLIGHT-TEST-002",
                now=NOW,
            )
        assert rejected.value.code == "INITIAL_SUBMISSION_STATE_CHANGED"
        assert db.scalar(select(func.count(PhysicalModelAdmission.id))) == 0
