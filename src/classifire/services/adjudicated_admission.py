"""Fail-closed verification for signed adjudicated-canonicalisation admissions.

This module deliberately has no database, HTTP, filesystem, configuration, or
private-key dependency.  A caller supplies the immutable admission manifest,
the exact values it has independently reconstructed, and one pinned public
key.  The verifier then either returns a fully bound admission or a sanitised
error code; it never accepts a best-effort or unsigned equivalent.

The legacy v1 Ed25519 parser remains available solely to inspect historical
test material.  The controlled canonical writer admits only the v2 P-256
protocol defined below; it never falls back from a v2 P-256 manifest to v1.

The signed representation is canonical UTF-8 JSON with lexicographically
sorted object keys, compact separators, no NaN/Infinity values, and the
``signature`` member omitted.  Lists preserve their declared order.  This is a
CLASSIFIRE-specific canonicalisation contract, not an attempt to silently
normalise human-facing strings or numeric meanings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Any, Mapping, NoReturn, TypeAlias
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

ADJUDICATED_ADMISSION_MANIFEST_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v1"
ADJUDICATED_ADMISSION_PURPOSE = "initial_adjudicated_canonicalisation"
ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM = "Ed25519"
ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA = "CLASSIFIRE-ADJUDICATED-CANONICALISATION-ADMISSION-v2"
ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM = "ECDSA_P256_SHA256"

_P256_PUBLIC_KEY_SPKI_LENGTH = 91
_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)

MAX_ADMISSION_MANIFEST_BYTES = 128 * 1024
MAX_NORMALISED_PAYLOAD_BYTES = 5 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_ADMISSION_CLOCK_SKEW = timedelta(minutes=5)

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
_ARTIFACT_NAME_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_RFC3339_UTC_SECONDS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_MANIFEST_FIELDS = frozenset(
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

JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class AdmissionVerificationError(RuntimeError):
    """A deliberately sanitised admission verification failure.

    ``code`` is safe to persist or expose to a caller.  It intentionally never
    includes raw manifests, hashes, signatures, public-key material, paths, or
    underlying cryptography/parser exception text.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Admission verification failed: {code}.")


@dataclass(frozen=True)
class ParsedAdjudicatedAdmission:
    """The strict, signature-unverified contents of an admission manifest."""

    schema: str
    signature_algorithm: str
    admission_id: str
    purpose: str
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
    signature: bytes
    signing_bytes: bytes
    canonical_manifest_sha256: str


@dataclass(frozen=True)
class VerifiedAdjudicatedAdmission:
    """An admission whose signature, expiry, and full binding all matched."""

    admission_id: str
    purpose: str
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
    """Return the CLASSIFIRE canonical upper-case SHA-256 representation."""

    if not isinstance(value, bytes):
        _fail("ADMISSION_INPUT_INVALID")
    return hashlib.sha256(value).hexdigest().upper()


def normalised_submission_payload_bytes(payload: object) -> bytes:
    """Encode a submission payload with the fixed v1 canonical JSON contract.

    The payload must be a JSON object.  It is copied while validating JSON-only
    values so caller-side mutation cannot change the returned bytes.
    """

    if not isinstance(payload, dict):
        _fail("ADMISSION_PAYLOAD_INVALID")
    normalised = _normalise_json_value(payload, code="ADMISSION_PAYLOAD_INVALID")
    if not isinstance(normalised, dict):  # Defensive; the root check is above.
        _fail("ADMISSION_PAYLOAD_INVALID")
    encoded = _canonical_json_bytes(normalised, code="ADMISSION_PAYLOAD_INVALID")
    if not encoded or len(encoded) > MAX_NORMALISED_PAYLOAD_BYTES:
        _fail("ADMISSION_PAYLOAD_INVALID")
    return encoded


def normalised_submission_payload_sha256(payload: object) -> str:
    """Return the SHA-256 bound to a v1 normalised submission payload."""

    return sha256_hex(normalised_submission_payload_bytes(payload))


# The codebase uses British spelling in the existing preflight receipt.  The
# aliases make the non-mutating utility straightforward to find for callers
# accustomed to American spelling without introducing a second contract.
normalized_submission_payload_bytes = normalised_submission_payload_bytes
normalized_submission_payload_sha256 = normalised_submission_payload_sha256


def parse_adjudicated_admission_manifest(
    manifest: Mapping[str, Any] | bytes | str,
) -> ParsedAdjudicatedAdmission:
    """Strictly parse one v1 manifest without trusting its signature yet."""

    raw_manifest = _decode_manifest(manifest)
    _require_exact_fields(raw_manifest)

    schema = raw_manifest["schema"]
    signature_algorithm = raw_manifest["signature_algorithm"]
    if schema == ADJUDICATED_ADMISSION_MANIFEST_SCHEMA:
        if signature_algorithm != ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM:
            _fail("ADMISSION_MANIFEST_INVALID")
        signature = _decode_base64url(raw_manifest["signature"], expected_length=64)
    elif schema == ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA:
        if signature_algorithm != ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM:
            _fail("ADMISSION_MANIFEST_INVALID")
        signature = _decode_base64url(raw_manifest["signature"], min_length=8, max_length=80)
        _validate_p256_der_signature(signature)
    else:
        _fail("ADMISSION_MANIFEST_INVALID")

    admission_id = _require_uuid(raw_manifest["admission_id"])
    purpose = raw_manifest["purpose"]
    if purpose != ADJUDICATED_ADMISSION_PURPOSE:
        _fail("ADMISSION_MANIFEST_INVALID")

    project_id = _require_uuid(raw_manifest["project_id"])
    estimate_id = _require_uuid(raw_manifest["estimate_id"])
    source_run_id = _require_identifier(raw_manifest["source_run_id"])
    adjudicated_run_id = _require_identifier(raw_manifest["adjudicated_run_id"])
    preflight_receipt_sha256 = _require_sha256(raw_manifest["preflight_receipt_sha256"])
    payload_sha256 = _require_sha256(raw_manifest["normalised_submission_payload_sha256"])
    protected_state_fingerprint = _require_sha256(raw_manifest["protected_state_fingerprint"])
    protected_state_fingerprint_version = _require_identifier(
        raw_manifest["protected_state_fingerprint_version"]
    )
    artifact_digests = _require_digest_map(raw_manifest["artifact_digests"])
    policy_versions = _require_policy_map(raw_manifest["policy_versions"])
    issuer = _require_identifier(raw_manifest["issuer"])
    key_id = _require_identifier(raw_manifest["key_id"])

    issued_at = _require_utc_timestamp(raw_manifest["issued_at"])
    expires_at = _require_utc_timestamp(raw_manifest["expires_at"])
    if expires_at <= issued_at:
        _fail("ADMISSION_MANIFEST_INVALID")

    unsigned_manifest = dict(raw_manifest)
    del unsigned_manifest["signature"]
    signing_bytes = _canonical_json_bytes(unsigned_manifest, code="ADMISSION_MANIFEST_INVALID")
    canonical_manifest_sha256 = sha256_hex(
        _canonical_json_bytes(raw_manifest, code="ADMISSION_MANIFEST_INVALID")
    )

    return ParsedAdjudicatedAdmission(
        schema=schema,
        signature_algorithm=signature_algorithm,
        admission_id=admission_id,
        purpose=purpose,
        project_id=project_id,
        estimate_id=estimate_id,
        source_run_id=source_run_id,
        adjudicated_run_id=adjudicated_run_id,
        preflight_receipt_sha256=preflight_receipt_sha256,
        normalised_submission_payload_sha256=payload_sha256,
        protected_state_fingerprint=protected_state_fingerprint,
        protected_state_fingerprint_version=protected_state_fingerprint_version,
        artifact_digests=MappingProxyType(artifact_digests),
        policy_versions=MappingProxyType(policy_versions),
        issuer=issuer,
        key_id=key_id,
        issued_at=issued_at,
        expires_at=expires_at,
        signature=signature,
        signing_bytes=signing_bytes,
        canonical_manifest_sha256=canonical_manifest_sha256,
    )


def admission_signing_bytes(manifest: Mapping[str, Any] | bytes | str) -> bytes:
    """Return the exact public manifest bytes an external signer must sign.

    This function never signs anything and deliberately exposes no private-key
    handling.  A manifest must still include a syntactically valid placeholder
    signature because the signature field is part of the strict v1 schema, even
    though that field is omitted from the returned bytes.
    """

    return parse_adjudicated_admission_manifest(manifest).signing_bytes


def verify_adjudicated_admission(
    manifest: Mapping[str, Any] | bytes | str,
    *,
    pinned_public_key: bytes | bytearray | str | Ed25519PublicKey | EllipticCurvePublicKey,
    expected_project_id: str,
    expected_estimate_id: str,
    expected_source_run_id: str,
    expected_adjudicated_run_id: str,
    expected_preflight_receipt_sha256: str,
    submission_payload: object,
    expected_protected_state_fingerprint: str,
    expected_protected_state_fingerprint_version: str,
    expected_artifact_digests: Mapping[str, str],
    expected_policy_versions: Mapping[str, str],
    expected_issuer: str,
    expected_key_id: str,
    max_ttl_seconds: int | None = None,
    now: datetime | None = None,
) -> VerifiedAdjudicatedAdmission:
    """Verify a signed admission against the exact current write context.

    ``pinned_public_key`` is injected by the caller and is never read from the
    manifest.  Legacy v1 accepts raw 32-byte Ed25519 material. The production
    v2 protocol accepts only canonical 91-byte DER SubjectPublicKeyInfo
    encoding for a P-256 public key, supplied as unpadded base64url text or a
    matching ``cryptography`` public-key object. Private keys are neither
    accepted nor imported by this module.
    """

    parsed = parse_adjudicated_admission_manifest(manifest)
    public_key = _load_pinned_public_key(pinned_public_key, schema=parsed.schema)
    _verify_signature(
        public_key,
        parsed.signature,
        parsed.signing_bytes,
        schema=parsed.schema,
    )

    current_time = _normalise_now(now)
    if parsed.issued_at > current_time + MAX_ADMISSION_CLOCK_SKEW:
        _fail("ADMISSION_NOT_YET_VALID")
    if current_time >= parsed.expires_at:
        _fail("ADMISSION_EXPIRED")
    if max_ttl_seconds is not None:
        if (
            not isinstance(max_ttl_seconds, int)
            or isinstance(max_ttl_seconds, bool)
            or max_ttl_seconds <= 0
        ):
            _fail("ADMISSION_TTL_INVALID")
        if parsed.expires_at - parsed.issued_at > timedelta(seconds=max_ttl_seconds):
            _fail("ADMISSION_TTL_EXCEEDED")

    expected_project = _require_uuid(expected_project_id)
    expected_estimate = _require_uuid(expected_estimate_id)
    expected_source_run = _require_identifier(expected_source_run_id)
    expected_adjudicated_run = _require_identifier(expected_adjudicated_run_id)
    expected_preflight = _require_sha256(expected_preflight_receipt_sha256)
    expected_payload = normalised_submission_payload_sha256(submission_payload)
    expected_fingerprint = _require_sha256(expected_protected_state_fingerprint)
    expected_fingerprint_version = _require_identifier(expected_protected_state_fingerprint_version)
    expected_artifacts = _require_digest_map(expected_artifact_digests)
    expected_policies = _require_policy_map(expected_policy_versions)
    issuer = _require_identifier(expected_issuer)
    key_id = _require_identifier(expected_key_id)

    if (
        parsed.purpose != ADJUDICATED_ADMISSION_PURPOSE
        or not hmac.compare_digest(parsed.project_id, expected_project)
        or not hmac.compare_digest(parsed.estimate_id, expected_estimate)
        or not hmac.compare_digest(parsed.source_run_id, expected_source_run)
        or not hmac.compare_digest(parsed.adjudicated_run_id, expected_adjudicated_run)
        or not hmac.compare_digest(parsed.preflight_receipt_sha256, expected_preflight)
        or not hmac.compare_digest(parsed.normalised_submission_payload_sha256, expected_payload)
        or not hmac.compare_digest(parsed.protected_state_fingerprint, expected_fingerprint)
        or not hmac.compare_digest(
            parsed.protected_state_fingerprint_version,
            expected_fingerprint_version,
        )
        or not _mapping_matches(parsed.artifact_digests, expected_artifacts)
        or not _mapping_matches(parsed.policy_versions, expected_policies)
        or not hmac.compare_digest(parsed.issuer, issuer)
        or not hmac.compare_digest(parsed.key_id, key_id)
    ):
        _fail("ADMISSION_BINDING_MISMATCH")

    return VerifiedAdjudicatedAdmission(
        admission_id=parsed.admission_id,
        purpose=parsed.purpose,
        project_id=parsed.project_id,
        estimate_id=parsed.estimate_id,
        source_run_id=parsed.source_run_id,
        adjudicated_run_id=parsed.adjudicated_run_id,
        preflight_receipt_sha256=parsed.preflight_receipt_sha256,
        normalised_submission_payload_sha256=parsed.normalised_submission_payload_sha256,
        protected_state_fingerprint=parsed.protected_state_fingerprint,
        protected_state_fingerprint_version=parsed.protected_state_fingerprint_version,
        artifact_digests=parsed.artifact_digests,
        policy_versions=parsed.policy_versions,
        issuer=parsed.issuer,
        key_id=parsed.key_id,
        issued_at=parsed.issued_at,
        expires_at=parsed.expires_at,
        canonical_manifest_sha256=parsed.canonical_manifest_sha256,
    )


def _fail(code: str) -> NoReturn:
    raise AdmissionVerificationError(code)


def _decode_manifest(manifest: Mapping[str, Any] | bytes | str) -> dict[str, JSONValue]:
    if isinstance(manifest, bytes):
        if not manifest or len(manifest) > MAX_ADMISSION_MANIFEST_BYTES:
            _fail("ADMISSION_MANIFEST_INVALID")
        try:
            text = manifest.decode("utf-8")
        except UnicodeDecodeError:
            _fail("ADMISSION_MANIFEST_INVALID")
        return _decode_manifest_json(text)

    if isinstance(manifest, str):
        try:
            encoded = manifest.encode("utf-8")
        except UnicodeEncodeError:
            _fail("ADMISSION_MANIFEST_INVALID")
        if not encoded or len(encoded) > MAX_ADMISSION_MANIFEST_BYTES:
            _fail("ADMISSION_MANIFEST_INVALID")
        return _decode_manifest_json(manifest)

    if not isinstance(manifest, Mapping):
        _fail("ADMISSION_MANIFEST_INVALID")
    normalised = _normalise_json_value(dict(manifest), code="ADMISSION_MANIFEST_INVALID")
    if not isinstance(normalised, dict):  # Defensive; dict(manifest) is an object.
        _fail("ADMISSION_MANIFEST_INVALID")
    encoded = _canonical_json_bytes(normalised, code="ADMISSION_MANIFEST_INVALID")
    if not encoded or len(encoded) > MAX_ADMISSION_MANIFEST_BYTES:
        _fail("ADMISSION_MANIFEST_INVALID")
    return normalised


def _decode_manifest_json(text: str) -> dict[str, JSONValue]:
    try:
        decoded = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_non_json_constant,
        )
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError):
        _fail("ADMISSION_MANIFEST_INVALID")
    normalised = _normalise_json_value(decoded, code="ADMISSION_MANIFEST_INVALID")
    if not isinstance(normalised, dict):
        _fail("ADMISSION_MANIFEST_INVALID")
    return normalised


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_non_json_constant(_: str) -> None:
    raise ValueError("non-JSON numeric constant")


def _normalise_json_value(value: object, *, code: str, depth: int = 0) -> JSONValue:
    if depth > MAX_JSON_DEPTH:
        _fail(code)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail(code)
        return value
    if isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            _fail(code)
        return value
    if isinstance(value, list):
        return [_normalise_json_value(item, code=code, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        result: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in result:
                _fail(code)
            try:
                key.encode("utf-8")
            except UnicodeEncodeError:
                _fail(code)
            result[key] = _normalise_json_value(item, code=code, depth=depth + 1)
        return result
    _fail(code)


def _canonical_json_bytes(
    value: JSONValue,
    *,
    code: str = "ADMISSION_MANIFEST_INVALID",
) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError):
        _fail(code)


def _require_exact_fields(manifest: Mapping[str, JSONValue]) -> None:
    if set(manifest) != _MANIFEST_FIELDS:
        _fail("ADMISSION_MANIFEST_INVALID")


def _require_uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail("ADMISSION_MANIFEST_INVALID")
    try:
        parsed = UUID(value)
    except (AttributeError, ValueError):
        _fail("ADMISSION_MANIFEST_INVALID")
    if parsed.int == 0 or str(parsed) != value:
        _fail("ADMISSION_MANIFEST_INVALID")
    return value


def _require_sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    return value


def _require_identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    return value


def _require_digest_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("ADMISSION_MANIFEST_INVALID")
    result: dict[str, str] = {}
    for key, digest in value.items():
        if not isinstance(key, str) or _ARTIFACT_NAME_RE.fullmatch(key) is None or key in result:
            _fail("ADMISSION_MANIFEST_INVALID")
        result[key] = _require_sha256(digest)
    return dict(sorted(result.items()))


def _require_policy_map(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("ADMISSION_MANIFEST_INVALID")
    result: dict[str, str] = {}
    for key, policy_version in value.items():
        if not isinstance(key, str) or _ARTIFACT_NAME_RE.fullmatch(key) is None or key in result:
            _fail("ADMISSION_MANIFEST_INVALID")
        result[key] = _require_identifier(policy_version)
    return dict(sorted(result.items()))


def _require_utc_timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _RFC3339_UTC_SECONDS_RE.fullmatch(value) is None:
        _fail("ADMISSION_MANIFEST_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _fail("ADMISSION_MANIFEST_INVALID")


def _decode_base64url(
    value: object,
    *,
    expected_length: int | None = None,
    min_length: int | None = None,
    max_length: int | None = None,
    code: str = "ADMISSION_MANIFEST_INVALID",
) -> bytes:
    if expected_length is not None:
        min_length = expected_length
        max_length = expected_length
    if min_length is None or max_length is None or min_length <= 0 or max_length < min_length:
        _fail(code)
    if not isinstance(value, str) or _BASE64URL_RE.fullmatch(value) is None or "=" in value:
        _fail(code)
    padded = value + ("=" * (-len(value) % 4))
    try:
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except (UnicodeEncodeError, ValueError):
        _fail(code)
    if len(decoded) < min_length or len(decoded) > max_length:
        _fail(code)
    if base64.urlsafe_b64encode(decoded).decode("ascii").rstrip("=") != value:
        _fail(code)
    return decoded


def _load_pinned_public_key(
    pinned_public_key: bytes | bytearray | str | Ed25519PublicKey | EllipticCurvePublicKey,
    *,
    schema: str,
) -> Ed25519PublicKey | EllipticCurvePublicKey:
    if schema == ADJUDICATED_ADMISSION_MANIFEST_SCHEMA:
        return _load_legacy_ed25519_public_key(pinned_public_key)
    if schema == ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA:
        return _load_p256_public_key(pinned_public_key)
    _fail("ADMISSION_PINNED_KEY_INVALID")


def _load_legacy_ed25519_public_key(
    pinned_public_key: bytes | bytearray | str | Ed25519PublicKey | EllipticCurvePublicKey,
) -> Ed25519PublicKey:

    if isinstance(pinned_public_key, bytearray):
        public_key_bytes = bytes(pinned_public_key)
    elif isinstance(pinned_public_key, bytes):
        public_key_bytes = pinned_public_key
    elif isinstance(pinned_public_key, str):
        public_key_bytes = _decode_base64url(
            pinned_public_key,
            expected_length=32,
            code="ADMISSION_PINNED_KEY_INVALID",
        )
    elif isinstance(pinned_public_key, Ed25519PublicKey):
        return pinned_public_key
    else:
        _fail("ADMISSION_PINNED_KEY_INVALID")

    if len(public_key_bytes) != 32:
        _fail("ADMISSION_PINNED_KEY_INVALID")
    try:
        return Ed25519PublicKey.from_public_bytes(public_key_bytes)
    except ValueError:
        _fail("ADMISSION_PINNED_KEY_INVALID")


def _load_p256_public_key(
    pinned_public_key: bytes | bytearray | str | Ed25519PublicKey | EllipticCurvePublicKey,
) -> EllipticCurvePublicKey:
    encoded_public_key: bytes | None = None
    if isinstance(pinned_public_key, EllipticCurvePublicKey):
        public_key = pinned_public_key
    else:
        if isinstance(pinned_public_key, bytearray):
            public_key_bytes = bytes(pinned_public_key)
        elif isinstance(pinned_public_key, bytes):
            public_key_bytes = pinned_public_key
        elif isinstance(pinned_public_key, str):
            public_key_bytes = _decode_base64url(
                pinned_public_key,
                expected_length=_P256_PUBLIC_KEY_SPKI_LENGTH,
                code="ADMISSION_PINNED_KEY_INVALID",
            )
        else:
            _fail("ADMISSION_PINNED_KEY_INVALID")
        if len(public_key_bytes) != _P256_PUBLIC_KEY_SPKI_LENGTH:
            _fail("ADMISSION_PINNED_KEY_INVALID")
        encoded_public_key = public_key_bytes
        try:
            public_key = serialization.load_der_public_key(public_key_bytes)
        except ValueError:
            _fail("ADMISSION_PINNED_KEY_INVALID")
    if not isinstance(public_key, EllipticCurvePublicKey) or not isinstance(
        public_key.curve, ec.SECP256R1
    ):
        _fail("ADMISSION_PINNED_KEY_INVALID")
    try:
        canonical = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except ValueError:
        _fail("ADMISSION_PINNED_KEY_INVALID")
    if len(canonical) != _P256_PUBLIC_KEY_SPKI_LENGTH:
        _fail("ADMISSION_PINNED_KEY_INVALID")
    if encoded_public_key is not None and not hmac.compare_digest(canonical, encoded_public_key):
        _fail("ADMISSION_PINNED_KEY_INVALID")
    return public_key


def _verify_signature(
    public_key: Ed25519PublicKey | EllipticCurvePublicKey,
    signature: bytes,
    signing_bytes: bytes,
    *,
    schema: str,
) -> None:
    try:
        if schema == ADJUDICATED_ADMISSION_MANIFEST_SCHEMA:
            if not isinstance(public_key, Ed25519PublicKey):
                _fail("ADMISSION_PINNED_KEY_INVALID")
            public_key.verify(signature, signing_bytes)
            return
        if schema == ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA:
            if not isinstance(public_key, EllipticCurvePublicKey) or not isinstance(
                public_key.curve, ec.SECP256R1
            ):
                _fail("ADMISSION_PINNED_KEY_INVALID")
            public_key.verify(signature, signing_bytes, ec.ECDSA(hashes.SHA256()))
            return
        _fail("ADMISSION_MANIFEST_INVALID")
    except (InvalidSignature, ValueError):
        _fail("ADMISSION_SIGNATURE_INVALID")


def _validate_p256_der_signature(signature: bytes) -> None:
    try:
        r, s = decode_dss_signature(signature)
        if (
            r <= 0
            or r >= _P256_ORDER
            or s <= 0
            or s >= _P256_ORDER
            or encode_dss_signature(r, s) != signature
        ):
            _fail("ADMISSION_MANIFEST_INVALID")
    except ValueError:
        _fail("ADMISSION_MANIFEST_INVALID")


def _normalise_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        _fail("ADMISSION_INPUT_INVALID")
    return now.astimezone(timezone.utc)


def _mapping_matches(actual: Mapping[str, str], expected: Mapping[str, str]) -> bool:
    if set(actual) != set(expected):
        return False
    return all(
        isinstance(expected[key], str) and hmac.compare_digest(actual[key], expected[key])
        for key in actual
    )


__all__ = [
    "ADJUDICATED_ADMISSION_MANIFEST_SCHEMA",
    "ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA",
    "ADJUDICATED_ADMISSION_PURPOSE",
    "ADJUDICATED_ADMISSION_SIGNATURE_ALGORITHM",
    "ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM",
    "AdmissionVerificationError",
    "ParsedAdjudicatedAdmission",
    "VerifiedAdjudicatedAdmission",
    "admission_signing_bytes",
    "normalised_submission_payload_bytes",
    "normalised_submission_payload_sha256",
    "normalized_submission_payload_bytes",
    "normalized_submission_payload_sha256",
    "parse_adjudicated_admission_manifest",
    "sha256_hex",
    "verify_adjudicated_admission",
]
