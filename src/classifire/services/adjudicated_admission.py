"""Strict, side-effect-free verification for P-256 admission manifests.

The verifier receives a pinned public key from a later configuration boundary.
It never reads configuration, handles a private key, writes a database row, or
performs an HTTP request.  A caller must reconstruct every signed binding and
pass it explicitly; mismatches fail closed with a sanitised code.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

ADMISSION_MANIFEST_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v2"
ADMISSION_PURPOSE = "initial_adjudicated_canonicalisation"
ADMISSION_SIGNATURE_ALGORITHM = "ECDSA_P256_SHA256"
MAX_ADMISSION_MANIFEST_BYTES = 128 * 1024
MAX_ADMISSION_PAYLOAD_BYTES = 5 * 1024 * 1024
_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FIELDS = frozenset(
    {
        "schema",
        "admission_id",
        "purpose",
        "project_id",
        "estimate_id",
        "source_run_id",
        "adjudicated_run_id",
        "preflight_receipt_sha256",
        "normalised_submission_payload_sha256",
        "protected_state_fingerprint",
        "protected_state_fingerprint_version",
        "artifact_digests",
        "policy_versions",
        "issuer",
        "key_id",
        "issued_at",
        "expires_at",
        "signature_algorithm",
        "signature",
    }
)


class AdmissionVerificationError(RuntimeError):
    """Safe error type; ``code`` is suitable for a later audit receipt."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Admission verification failed: {code}.")


@dataclass(frozen=True)
class VerifiedAdmission:
    admission_id: str
    project_id: str
    estimate_id: str
    source_run_id: str
    adjudicated_run_id: str
    preflight_receipt_sha256: str
    normalised_submission_payload_sha256: str
    protected_state_fingerprint: str
    protected_state_fingerprint_version: str
    artifact_digests: Mapping[str, str]
    policy_versions: Mapping[str, str]
    issuer: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    canonical_manifest_sha256: str


def sha256_hex(value: bytes) -> str:
    if not isinstance(value, bytes):
        _fail("ADMISSION_INPUT_INVALID")
    return hashlib.sha256(value).hexdigest().upper()


def normalised_submission_payload_bytes(payload: object) -> bytes:
    if not isinstance(payload, dict):
        _fail("ADMISSION_PAYLOAD_INVALID")
    encoded = _canonical_json_bytes(payload, code="ADMISSION_PAYLOAD_INVALID")
    if not encoded or len(encoded) > MAX_ADMISSION_PAYLOAD_BYTES:
        _fail("ADMISSION_PAYLOAD_INVALID")
    return encoded


def normalised_submission_payload_sha256(payload: object) -> str:
    return sha256_hex(normalised_submission_payload_bytes(payload))


def admission_signing_bytes(manifest: Mapping[str, Any] | bytes | str) -> bytes:
    # Sign the declared JSON representation, not the internal parsed form:
    # parsed timestamps are datetime instances and must never enter the
    # canonical JSON contract.
    raw = _raw_manifest(manifest)
    _parse_manifest(raw)
    unsigned = dict(raw)
    del unsigned["signature"]
    return _canonical_json_bytes(unsigned, code="ADMISSION_MANIFEST_INVALID")


def verify_adjudicated_admission(
    manifest: Mapping[str, Any] | bytes | str,
    *,
    pinned_public_key: str,
    expected_project_id: str,
    expected_estimate_id: str,
    expected_preflight_receipt_sha256: str,
    submission_payload: object,
    expected_protected_state_fingerprint: str,
    expected_protected_state_fingerprint_version: str,
    expected_artifact_digests: Mapping[str, str],
    expected_policy_versions: Mapping[str, str],
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> VerifiedAdmission:
    """Verify one exact P-256 admission against independently reconstructed facts."""
    raw_manifest = _raw_manifest(manifest)
    signing_bytes = admission_signing_bytes(raw_manifest)
    item = _parse_manifest(raw_manifest)
    _require_equal(item["project_id"], _uuid(expected_project_id), "ADMISSION_BINDING_MISMATCH")
    _require_equal(item["estimate_id"], _uuid(expected_estimate_id), "ADMISSION_BINDING_MISMATCH")
    _require_equal(
        item["preflight_receipt_sha256"],
        _sha(expected_preflight_receipt_sha256),
        "ADMISSION_BINDING_MISMATCH",
    )
    _require_equal(
        item["normalised_submission_payload_sha256"],
        normalised_submission_payload_sha256(submission_payload),
        "ADMISSION_BINDING_MISMATCH",
    )
    _require_equal(
        item["protected_state_fingerprint"],
        _sha(expected_protected_state_fingerprint),
        "ADMISSION_BINDING_MISMATCH",
    )
    _require_equal(
        item["protected_state_fingerprint_version"],
        _identifier(expected_protected_state_fingerprint_version),
        "ADMISSION_BINDING_MISMATCH",
    )
    _require_equal(item["issuer"], _identifier(expected_issuer), "ADMISSION_ISSUER_MISMATCH")
    _require_equal(item["key_id"], _identifier(expected_key_id), "ADMISSION_KEY_MISMATCH")
    _require_equal(
        item["artifact_digests"],
        _digest_map(expected_artifact_digests),
        "ADMISSION_BINDING_MISMATCH",
    )
    _require_equal(
        item["policy_versions"], _string_map(expected_policy_versions), "ADMISSION_BINDING_MISMATCH"
    )
    current_time = now or datetime.now(UTC)
    if current_time.tzinfo is None:
        _fail("ADMISSION_TIME_INVALID")
    current_time = current_time.astimezone(UTC)
    if item["expires_at"] <= current_time or item["issued_at"] > current_time:
        _fail("ADMISSION_EXPIRED")

    key = _load_p256_public_key(pinned_public_key)
    signature = _base64url(item["signature"], code="ADMISSION_SIGNATURE_INVALID")
    _validate_low_s_signature(signature)
    try:
        key.verify(signature, signing_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        _fail("ADMISSION_SIGNATURE_INVALID")

    full_bytes = _canonical_json_bytes(raw_manifest, code="ADMISSION_MANIFEST_INVALID")
    return VerifiedAdmission(
        admission_id=item["admission_id"],
        project_id=item["project_id"],
        estimate_id=item["estimate_id"],
        source_run_id=item["source_run_id"],
        adjudicated_run_id=item["adjudicated_run_id"],
        preflight_receipt_sha256=item["preflight_receipt_sha256"],
        normalised_submission_payload_sha256=item["normalised_submission_payload_sha256"],
        protected_state_fingerprint=item["protected_state_fingerprint"],
        protected_state_fingerprint_version=item["protected_state_fingerprint_version"],
        artifact_digests=MappingProxyType(dict(item["artifact_digests"])),
        policy_versions=MappingProxyType(dict(item["policy_versions"])),
        issuer=item["issuer"],
        key_id=item["key_id"],
        issued_at=item["issued_at"],
        expires_at=item["expires_at"],
        canonical_manifest_sha256=sha256_hex(full_bytes),
    )


def _parse_manifest(value: Mapping[str, Any] | bytes | str) -> dict[str, Any]:
    item = _raw_manifest(value)
    if not isinstance(item, dict) or set(item) != _FIELDS:
        _fail("ADMISSION_MANIFEST_INVALID")
    if item["schema"] != ADMISSION_MANIFEST_SCHEMA or item["purpose"] != ADMISSION_PURPOSE:
        _fail("ADMISSION_MANIFEST_INVALID")
    if item["signature_algorithm"] != ADMISSION_SIGNATURE_ALGORITHM:
        _fail("ADMISSION_MANIFEST_INVALID")
    item["admission_id"] = _uuid(item["admission_id"])
    item["project_id"] = _uuid(item["project_id"])
    item["estimate_id"] = _uuid(item["estimate_id"])
    for key in (
        "source_run_id",
        "adjudicated_run_id",
        "protected_state_fingerprint_version",
        "issuer",
        "key_id",
    ):
        item[key] = _identifier(item[key])
    for key in (
        "preflight_receipt_sha256",
        "normalised_submission_payload_sha256",
        "protected_state_fingerprint",
    ):
        item[key] = _sha(item[key])
    item["artifact_digests"] = _digest_map(item["artifact_digests"])
    item["policy_versions"] = _string_map(item["policy_versions"])
    item["issued_at"] = _timestamp(item["issued_at"])
    item["expires_at"] = _timestamp(item["expires_at"])
    if item["expires_at"] <= item["issued_at"]:
        _fail("ADMISSION_MANIFEST_INVALID")
    _base64url(item["signature"], code="ADMISSION_MANIFEST_INVALID")
    return item


def _raw_manifest(value: Mapping[str, Any] | bytes | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        item = dict(value)
    elif isinstance(value, bytes):
        if len(value) > MAX_ADMISSION_MANIFEST_BYTES:
            _fail("ADMISSION_MANIFEST_INVALID")
        try:
            item = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            _fail("ADMISSION_MANIFEST_INVALID")
    elif isinstance(value, str):
        return _raw_manifest(value.encode("utf-8"))
    else:
        _fail("ADMISSION_MANIFEST_INVALID")
    if not isinstance(item, dict):
        _fail("ADMISSION_MANIFEST_INVALID")
    return item


def _load_p256_public_key(value: str) -> EllipticCurvePublicKey:
    raw = _base64url(value, code="ADMISSION_PUBLIC_KEY_INVALID")
    try:
        key = serialization.load_der_public_key(raw)
    except ValueError:
        _fail("ADMISSION_PUBLIC_KEY_INVALID")
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        _fail("ADMISSION_PUBLIC_KEY_INVALID")
    return key


def _validate_low_s_signature(signature: bytes) -> None:
    try:
        _r, s = decode_dss_signature(signature)
    except ValueError:
        _fail("ADMISSION_SIGNATURE_INVALID")
    if s <= 0 or s > _P256_ORDER // 2:
        _fail("ADMISSION_SIGNATURE_INVALID")


def _canonical_json_bytes(value: object, *, code: str) -> bytes:
    _validate_json(value, code=code)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError):
        _fail(code)


def _validate_json(value: object, *, code: str, depth: int = 0) -> None:
    if depth > 64:
        _fail(code)
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(code)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item, code=code, depth=depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item, code=code, depth=depth + 1)
        return
    _fail(code)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail("ADMISSION_MANIFEST_INVALID")
    try:
        return str(UUID(value))
    except ValueError:
        _fail("ADMISSION_MANIFEST_INVALID")


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    return value


def _digest_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("ADMISSION_MANIFEST_INVALID")
    result = {str(key): _sha(item) for key, item in value.items()}
    if len(result) != len(value) or any(not _IDENTIFIER.fullmatch(key) for key in result):
        _fail("ADMISSION_MANIFEST_INVALID")
    return dict(sorted(result.items()))


def _string_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("ADMISSION_MANIFEST_INVALID")
    result = {str(key): _identifier(item) for key, item in value.items()}
    if len(result) != len(value) or any(not _IDENTIFIER.fullmatch(key) for key in result):
        _fail("ADMISSION_MANIFEST_INVALID")
    return dict(sorted(result.items()))


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail("ADMISSION_MANIFEST_INVALID")


def _base64url(value: object, *, code: str) -> bytes:
    if not isinstance(value, str) or not _BASE64URL.fullmatch(value):
        _fail(code)
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError:
        _fail(code)


def _require_equal(actual: object, expected: object, code: str) -> None:
    if actual != expected:
        _fail(code)


def _fail(code: str) -> None:
    raise AdmissionVerificationError(code)
