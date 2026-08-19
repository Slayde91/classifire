from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from classifire.services.adjudicated_admission import (
    ADMISSION_MANIFEST_SCHEMA,
    ADMISSION_PURPOSE,
    ADMISSION_SIGNATURE_ALGORITHM,
    AdmissionVerificationError,
    admission_signing_bytes,
    normalised_submission_payload_sha256,
    verify_adjudicated_admission,
)

NOW = datetime(2026, 8, 20, 1, 0, tzinfo=UTC)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _fixture(
    *, project_id: str | None = None, estimate_id: str | None = None
) -> tuple[dict[str, object], str, dict[str, object]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = _b64(
        private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    payload = {"openings": [{"opening_code": "O-001"}], "services": []}
    digest = "A" * 64
    manifest: dict[str, object] = {
        "schema": ADMISSION_MANIFEST_SCHEMA,
        "admission_id": str(uuid4()),
        "purpose": ADMISSION_PURPOSE,
        "project_id": project_id or str(uuid4()),
        "estimate_id": estimate_id or str(uuid4()),
        "source_run_id": "source-run-1",
        "adjudicated_run_id": "adjudicated-run-1",
        "preflight_receipt_sha256": digest,
        "normalised_submission_payload_sha256": normalised_submission_payload_sha256(payload),
        "protected_state_fingerprint": "B" * 64,
        "protected_state_fingerprint_version": "CLASSIFIRE-PROTECTED-STATE-v1",
        "artifact_digests": {"adjudicated_proposal": "C" * 64},
        "policy_versions": {"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
        "issuer": "slayde-tana",
        "key_id": "android-p256-production-1",
        "issued_at": "2026-08-20T00:59:00Z",
        "expires_at": "2026-08-20T01:10:00Z",
        "signature_algorithm": ADMISSION_SIGNATURE_ALGORITHM,
        "signature": "AA",
    }
    signature = private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(signature)
    order = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
    if s > order // 2:
        signature = encode_dss_signature(r, order - s)
    manifest["signature"] = _b64(signature)
    return manifest, public_key, payload


def _verify(manifest: dict[str, object], public_key: str, payload: dict[str, object]):
    return verify_adjudicated_admission(
        manifest,
        pinned_public_key=public_key,
        expected_project_id=str(manifest["project_id"]),
        expected_estimate_id=str(manifest["estimate_id"]),
        expected_preflight_receipt_sha256="A" * 64,
        submission_payload=payload,
        expected_protected_state_fingerprint="B" * 64,
        expected_protected_state_fingerprint_version="CLASSIFIRE-PROTECTED-STATE-v1",
        expected_artifact_digests={"adjudicated_proposal": "C" * 64},
        expected_policy_versions={"physical_policy": "CLASSIFIRE-PHYSICAL-v1"},
        expected_issuer="slayde-tana",
        expected_key_id="android-p256-production-1",
        now=NOW,
    )


def test_p256_manifest_verifies_exact_bindings() -> None:
    manifest, public_key, payload = _fixture()
    verified = _verify(manifest, public_key, payload)
    assert verified.admission_id == manifest["admission_id"]
    assert verified.issuer == "slayde-tana"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("issuer", "other", "ADMISSION_ISSUER_MISMATCH"),
        ("expires_at", "2026-08-20T01:00:00Z", "ADMISSION_EXPIRED"),
    ],
)
def test_manifest_binding_and_expiry_fail_closed(field: str, value: str, code: str) -> None:
    manifest, public_key, payload = _fixture()
    manifest[field] = value
    with pytest.raises(AdmissionVerificationError) as rejected:
        _verify(manifest, public_key, payload)
    assert rejected.value.code == code


def test_signature_and_payload_tampering_fail_closed() -> None:
    manifest, public_key, payload = _fixture()
    manifest["artifact_digests"] = {"adjudicated_proposal": "D" * 64}
    with pytest.raises(AdmissionVerificationError) as rejected:
        _verify(manifest, public_key, payload)
    assert rejected.value.code == "ADMISSION_BINDING_MISMATCH"

    manifest, public_key, payload = _fixture()
    manifest["signature"] = "AQ"
    with pytest.raises(AdmissionVerificationError) as rejected:
        _verify(manifest, public_key, payload)
    assert rejected.value.code == "ADMISSION_SIGNATURE_INVALID"
