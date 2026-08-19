from __future__ import annotations

import base64
from collections import OrderedDict
from datetime import datetime, timezone

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from classifire.services.adjudicated_admission import (
    ADJUDICATED_ADMISSION_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
    ADJUDICATED_ADMISSION_PURPOSE,
    ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM,
    AdmissionVerificationError,
    admission_signing_bytes,
    normalised_submission_payload_bytes,
    normalised_submission_payload_sha256,
    sha256_hex,
    verify_adjudicated_admission,
)

PROJECT_ID = "a8c30c4a-48c8-4ee9-a69c-1d21df7fd65f"
ESTIMATE_ID = "e333e8de-a3b8-40ce-8997-1a1204a573da"
ADMISSION_ID = "c14663d4-ae8d-4a77-8ae9-51a4402520f1"
SOURCE_RUN_ID = "uat-source-run-20260816"
ADJUDICATED_RUN_ID = "adjudicated-run-20260816"
ISSUER = "governance.classifire"
KEY_ID = "physical-admission-v1"
FINGERPRINT = "C" * 64
FINGERPRINT_VERSION = "CLASSIFIRE-PROTECTED-CANONICAL-STATE-v1"
ARTIFACT_DIGESTS = {
    "adjudicated_proposal": "A" * 64,
    "human_adjudication": "B" * 64,
}
POLICY_VERSIONS = {
    "preflight": "CLASSIFIRE-ADJUDICATED-PREFLIGHT-v1",
    "topology": "CLASSIFIRE-FIRESEAL-PHYSICAL-v8",
}
NOW = datetime(2026, 8, 18, 0, 30, tzinfo=timezone.utc)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _payload() -> dict[str, object]:
    return {
        "openings": [
            {
                "opening_code": "O-001",
                "external_defect_id": "147042",
                "opening_type": "core_hole",
                "diameter_mm": 100,
            }
        ],
        "services": [],
    }


def _manifest(payload: object, **overrides: object) -> dict[str, object]:
    manifest: dict[str, object] = {
        "schema": ADJUDICATED_ADMISSION_MANIFEST_SCHEMA,
        "admission_id": ADMISSION_ID,
        "purpose": ADJUDICATED_ADMISSION_PURPOSE,
        "project_id": PROJECT_ID,
        "estimate_id": ESTIMATE_ID,
        "source_run_id": SOURCE_RUN_ID,
        "adjudicated_run_id": ADJUDICATED_RUN_ID,
        "preflight_receipt_sha256": sha256_hex(b'{"schema":"preflight"}'),
        "normalised_submission_payload_sha256": normalised_submission_payload_sha256(payload),
        "protected_state_fingerprint": FINGERPRINT,
        "protected_state_fingerprint_version": FINGERPRINT_VERSION,
        "artifact_digests": ARTIFACT_DIGESTS,
        "policy_versions": POLICY_VERSIONS,
        "issuer": ISSUER,
        "key_id": KEY_ID,
        "issued_at": "2026-08-18T00:00:00Z",
        "expires_at": "2026-08-18T01:00:00Z",
        "signature_algorithm": ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM,
        "signature": _base64url(b"\x00" * 64),
    }
    manifest.update(overrides)
    return manifest


def _signed_manifest(
    private_key: Ed25519PrivateKey,
    payload: object,
    **overrides: object,
) -> dict[str, object]:
    manifest = _manifest(payload, **overrides)
    manifest["signature"] = _base64url(private_key.sign(admission_signing_bytes(manifest)))
    return manifest


def _public_key_bytes(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _verify(
    manifest: object,
    payload: object,
    private_key: Ed25519PrivateKey,
    **overrides: object,
):
    values: dict[str, object] = {
        "pinned_public_key": _public_key_bytes(private_key),
        "expected_project_id": PROJECT_ID,
        "expected_estimate_id": ESTIMATE_ID,
        "expected_source_run_id": SOURCE_RUN_ID,
        "expected_adjudicated_run_id": ADJUDICATED_RUN_ID,
        "expected_preflight_receipt_sha256": sha256_hex(b'{"schema":"preflight"}'),
        "submission_payload": payload,
        "expected_protected_state_fingerprint": FINGERPRINT,
        "expected_protected_state_fingerprint_version": FINGERPRINT_VERSION,
        "expected_artifact_digests": ARTIFACT_DIGESTS,
        "expected_policy_versions": POLICY_VERSIONS,
        "expected_issuer": ISSUER,
        "expected_key_id": KEY_ID,
        "now": NOW,
    }
    values.update(overrides)
    return verify_adjudicated_admission(manifest, **values)  # type: ignore[arg-type]


def test_valid_signature_and_full_binding_return_verified_admission() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)

    verified = _verify(manifest, payload, private_key)

    assert verified.admission_id == ADMISSION_ID
    assert verified.estimate_id == ESTIMATE_ID
    assert verified.project_id == PROJECT_ID
    assert verified.source_run_id == SOURCE_RUN_ID
    assert verified.adjudicated_run_id == ADJUDICATED_RUN_ID
    assert verified.normalised_submission_payload_sha256 == normalised_submission_payload_sha256(
        payload
    )
    manifest_hash = verified.canonical_manifest_sha256
    manifest["issuer"] = "mutated.after.verification"
    assert verified.canonical_manifest_sha256 == manifest_hash
    assert dict(verified.artifact_digests) == ARTIFACT_DIGESTS
    assert dict(verified.policy_versions) == POLICY_VERSIONS


def test_p256_v2_signature_uses_canonical_der_public_key_and_signature() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    payload = _payload()
    manifest = _manifest(
        payload,
        schema=ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
        signature_algorithm=ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
        signature=_base64url(b"\x30\x06\x02\x01\x01\x02\x01\x01"),
    )
    manifest["signature"] = _base64url(
        private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    )
    pinned_key = _base64url(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    verified = verify_adjudicated_admission(
        manifest,
        pinned_public_key=pinned_key,
        expected_project_id=PROJECT_ID,
        expected_estimate_id=ESTIMATE_ID,
        expected_source_run_id=SOURCE_RUN_ID,
        expected_adjudicated_run_id=ADJUDICATED_RUN_ID,
        expected_preflight_receipt_sha256=sha256_hex(b'{"schema":"preflight"}'),
        submission_payload=payload,
        expected_protected_state_fingerprint=FINGERPRINT,
        expected_protected_state_fingerprint_version=FINGERPRINT_VERSION,
        expected_artifact_digests=ARTIFACT_DIGESTS,
        expected_policy_versions=POLICY_VERSIONS,
        expected_issuer=ISSUER,
        expected_key_id=KEY_ID,
        now=NOW,
    )

    assert verified.admission_id == ADMISSION_ID

    manifest["signature"] = _base64url(b"\x30\x06\x02\x01\x01\x02\x01\x01")
    with pytest.raises(AdmissionVerificationError) as raised:
        verify_adjudicated_admission(
            manifest,
            pinned_public_key=pinned_key,
            expected_project_id=PROJECT_ID,
            expected_estimate_id=ESTIMATE_ID,
            expected_source_run_id=SOURCE_RUN_ID,
            expected_adjudicated_run_id=ADJUDICATED_RUN_ID,
            expected_preflight_receipt_sha256=sha256_hex(b'{"schema":"preflight"}'),
            submission_payload=payload,
            expected_protected_state_fingerprint=FINGERPRINT,
            expected_protected_state_fingerprint_version=FINGERPRINT_VERSION,
            expected_artifact_digests=ARTIFACT_DIGESTS,
            expected_policy_versions=POLICY_VERSIONS,
            expected_issuer=ISSUER,
            expected_key_id=KEY_ID,
            now=NOW,
        )
    assert raised.value.code == "ADMISSION_SIGNATURE_INVALID"


def test_payload_hash_is_deterministic_for_equivalent_object_key_order() -> None:
    first = {"services": [], "openings": [{"b": 2, "a": 1}]}
    second = {"openings": [{"a": 1, "b": 2}], "services": []}

    assert normalised_submission_payload_bytes(first) == normalised_submission_payload_bytes(second)
    assert normalised_submission_payload_sha256(first) == normalised_submission_payload_sha256(
        second
    )


def test_signature_tampering_fails_without_exposing_manifest_details() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)
    manifest["issuer"] = "other.governance"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, private_key)

    assert raised.value.code == "ADMISSION_SIGNATURE_INVALID"
    assert FINGERPRINT not in str(raised.value)
    assert "other.governance" not in str(raised.value)


def test_payload_substitution_is_rejected_after_a_valid_signature() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)
    substituted_payload = _payload()
    substituted_payload["openings"] = []

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, substituted_payload, private_key)

    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"


def test_preflight_fingerprint_artifact_and_policy_substitution_are_rejected() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(
            manifest,
            payload,
            private_key,
            expected_preflight_receipt_sha256="D" * 64,
        )
    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(
            manifest,
            payload,
            private_key,
            expected_source_run_id="other-source-run",
        )
    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(
            manifest,
            payload,
            private_key,
            expected_adjudicated_run_id="other-adjudicated-run",
        )
    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(
            manifest,
            payload,
            private_key,
            expected_artifact_digests={"adjudicated_proposal": "A" * 64},
        )
    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(
            manifest,
            payload,
            private_key,
            expected_policy_versions={"preflight": POLICY_VERSIONS["preflight"]},
        )
    assert raised.value.code == "ADMISSION_BINDING_MISMATCH"


def test_expired_and_future_manifest_times_fail_closed() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    expired = _signed_manifest(
        private_key,
        payload,
        issued_at="2026-08-17T22:00:00Z",
        expires_at="2026-08-17T23:00:00Z",
    )
    future = _signed_manifest(
        private_key,
        payload,
        issued_at="2026-08-18T00:36:00Z",
        expires_at="2026-08-18T01:36:00Z",
    )

    with pytest.raises(AdmissionVerificationError) as expired_error:
        _verify(expired, payload, private_key)
    with pytest.raises(AdmissionVerificationError) as future_error:
        _verify(future, payload, private_key)

    assert expired_error.value.code == "ADMISSION_EXPIRED"
    assert future_error.value.code == "ADMISSION_NOT_YET_VALID"


def test_admission_ttl_is_enforced_by_the_calling_security_boundary() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, private_key, max_ttl_seconds=900)

    assert raised.value.code == "ADMISSION_TTL_EXCEEDED"


def test_pinned_key_is_required_and_a_different_key_cannot_verify() -> None:
    signing_key = Ed25519PrivateKey.generate()
    other_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(signing_key, payload)

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, other_key)
    assert raised.value.code == "ADMISSION_SIGNATURE_INVALID"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, signing_key, pinned_public_key=b"\x00" * 31)
    assert raised.value.code == "ADMISSION_PINNED_KEY_INVALID"

    verified = _verify(
        manifest,
        payload,
        signing_key,
        pinned_public_key=_base64url(_public_key_bytes(signing_key)),
    )
    assert verified.key_id == KEY_ID

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, signing_key, pinned_public_key="not-a-valid-ed25519-key")
    assert raised.value.code == "ADMISSION_PINNED_KEY_INVALID"


def test_manifest_parser_rejects_duplicate_unknown_and_noncanonical_fields() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)
    manifest["unexpected"] = "value"

    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(manifest, payload, private_key)
    assert raised.value.code == "ADMISSION_MANIFEST_INVALID"

    duplicate_schema = (
        b'{"schema":"CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v1",'
        b'"schema":"CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v1"}'
    )
    with pytest.raises(AdmissionVerificationError) as raised:
        _verify(duplicate_schema, payload, private_key)
    assert raised.value.code == "ADMISSION_MANIFEST_INVALID"


def test_signing_bytes_are_order_independent_but_exactly_bound_to_fields() -> None:
    private_key = Ed25519PrivateKey.generate()
    payload = _payload()
    manifest = _signed_manifest(private_key, payload)
    reordered = OrderedDict(reversed(list(manifest.items())))

    assert admission_signing_bytes(manifest) == admission_signing_bytes(reordered)

    reordered["signature"] = manifest["signature"]
    _verify(reordered, payload, private_key)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"value": float("nan")},
        {"value": ("not", "a", "json", "array")},
    ],
)
def test_payload_normalisation_rejects_noncanonical_json_inputs(payload: object) -> None:
    with pytest.raises(AdmissionVerificationError) as raised:
        normalised_submission_payload_bytes(payload)

    assert raised.value.code == "ADMISSION_PAYLOAD_INVALID"
