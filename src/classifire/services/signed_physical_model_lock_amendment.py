"""Verify a future signed Physical Model Lock amendment without executing it.

The module deliberately has no path that invalidates a lock, edits physical rows,
creates a replacement lock, submits canonical state, or grants a downstream
technical, commercial, snapshot, or release authority.  It only proves that a
short-lived external P-256 signature, the currently active signed lock, the
current retained physical hash, a prospective amendment payload, and an exact
semantically-approved visual-validation receipt all agree.  A future dedicated
writer must recheck this result and all write-time dependencies in its own
transaction before it can make any canonical mutation.
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
from typing import Any, NoReturn
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ec import EllipticCurvePublicKey
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..models import Estimate
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import PhysicalModelLock
from .physical_model import build_current_physical_model_lock_payload
from .visual_validation_receipt import (
    VisualValidationReceiptError,
    require_semantically_approved_visual_validation_receipt,
)

SIGNED_LOCK_AMENDMENT_SCHEMA = "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-LOCK-AMENDMENT-v1"
SIGNED_LOCK_AMENDMENT_PURPOSE = "reopen_signed_physical_model_lock"
SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM = "ECDSA_P256_SHA256"
MAX_SIGNED_LOCK_AMENDMENT_BYTES = 128 * 1024
_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_PHYSICAL_MODEL_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FIELDS = frozenset(
    {
        "schema",
        "amendment_admission_id",
        "purpose",
        "project_id",
        "estimate_id",
        "target_lock_id",
        "target_lock_content_hash",
        "target_lock_signature_sha256",
        "current_physical_model_content_hash",
        "amendment_submission_payload_sha256",
        "visual_validation_receipt_sha256",
        "controller_receipt_sha256",
        "evidence_manifest_sha256",
        "evidence_family_inventory_sha256",
        "evidence_family_review_sha256",
        "human_review_request_sha256",
        "human_review_response_sha256",
        "amendment_reason",
        "policy_versions",
        "issuer",
        "key_id",
        "issued_at",
        "expires_at",
        "signature_algorithm",
        "signature",
    }
)
_REQUIRED_POLICY_VERSIONS = {
    "signed_lock_amendment": (
        f"{SIGNED_LOCK_AMENDMENT_SCHEMA}:{SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM}"
    ),
    "visual_validation_receipt": "CLASSIFIRE-PHASE8-VISUAL-VALIDATION-RECEIPT-v1",
}


class SignedPhysicalModelLockAmendmentError(RuntimeError):
    """Safe-code failure while verifying a future signed amendment admission."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed Physical Model Lock amendment failed: {code}.")


@dataclass(frozen=True, slots=True)
class VerifiedSignedPhysicalModelLockAmendment:
    """Exact, verified facts that a future writer must recheck before mutation."""

    amendment_admission_id: str
    project_id: str
    estimate_id: str
    target_lock_id: str
    target_lock_content_hash: str
    target_lock_signature_sha256: str
    current_physical_model_content_hash: str
    amendment_submission_payload_sha256: str
    visual_validation_receipt_sha256: str
    amendment_reason: str
    policy_versions: Mapping[str, str]
    issuer: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    canonical_manifest_sha256: str


def signed_lock_amendment_signing_bytes(manifest: Mapping[str, Any] | bytes | str) -> bytes:
    """Return canonical unsigned bytes for the exact amendment manifest."""

    raw = _raw_manifest(manifest)
    _parse_manifest(raw)
    unsigned = dict(raw)
    del unsigned["signature"]
    return _canonical_json_bytes(unsigned)


def verify_signed_physical_model_lock_amendment(
    manifest: Mapping[str, Any] | bytes | str,
    *,
    pinned_public_key: str,
    expected_project_id: str,
    expected_estimate_id: str,
    expected_target_lock_id: str,
    expected_target_lock_content_hash: str,
    expected_target_lock_signature_sha256: str,
    expected_current_physical_model_content_hash: str,
    amendment_submission_payload: object,
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> VerifiedSignedPhysicalModelLockAmendment:
    """Verify one exact external signature against independently supplied facts.

    This function is side-effect free.  It cannot inspect or mutate canonical
    database state, and it intentionally does not treat verification as a lock
    reopening decision.
    """

    raw = _raw_manifest(manifest)
    signing_bytes = signed_lock_amendment_signing_bytes(raw)
    item = _parse_manifest(raw)
    payload_hash = _canonical_submission_payload_sha256(amendment_submission_payload)

    _require_equal(item["project_id"], _uuid(expected_project_id), "AMENDMENT_BINDING_MISMATCH")
    _require_equal(item["estimate_id"], _uuid(expected_estimate_id), "AMENDMENT_BINDING_MISMATCH")
    _require_equal(
        item["target_lock_id"], _uuid(expected_target_lock_id), "AMENDMENT_BINDING_MISMATCH"
    )
    _require_equal(
        item["target_lock_content_hash"],
        _physical_model_hash(expected_target_lock_content_hash),
        "AMENDMENT_BINDING_MISMATCH",
    )
    _require_equal(
        item["target_lock_signature_sha256"],
        _sha(expected_target_lock_signature_sha256),
        "AMENDMENT_BINDING_MISMATCH",
    )
    _require_equal(
        item["current_physical_model_content_hash"],
        _physical_model_hash(expected_current_physical_model_content_hash),
        "AMENDMENT_BINDING_MISMATCH",
    )
    _require_equal(
        item["amendment_submission_payload_sha256"], payload_hash, "AMENDMENT_BINDING_MISMATCH"
    )
    _require_equal(item["issuer"], _identifier(expected_issuer), "AMENDMENT_ISSUER_MISMATCH")
    _require_equal(item["key_id"], _identifier(expected_key_id), "AMENDMENT_KEY_MISMATCH")

    current_time = _normalise_now(now)
    if item["expires_at"] <= current_time or item["issued_at"] > current_time:
        _fail("AMENDMENT_EXPIRED")

    key = _load_p256_public_key(pinned_public_key)
    signature = _base64url(item["signature"], code="AMENDMENT_SIGNATURE_INVALID")
    _validate_low_s_signature(signature)
    try:
        key.verify(signature, signing_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        _fail("AMENDMENT_SIGNATURE_INVALID")

    return VerifiedSignedPhysicalModelLockAmendment(
        amendment_admission_id=item["amendment_admission_id"],
        project_id=item["project_id"],
        estimate_id=item["estimate_id"],
        target_lock_id=item["target_lock_id"],
        target_lock_content_hash=item["target_lock_content_hash"],
        target_lock_signature_sha256=item["target_lock_signature_sha256"],
        current_physical_model_content_hash=item["current_physical_model_content_hash"],
        amendment_submission_payload_sha256=item["amendment_submission_payload_sha256"],
        visual_validation_receipt_sha256=item["visual_validation_receipt_sha256"],
        amendment_reason=item["amendment_reason"],
        policy_versions=MappingProxyType(dict(item["policy_versions"])),
        issuer=item["issuer"],
        key_id=item["key_id"],
        issued_at=item["issued_at"],
        expires_at=item["expires_at"],
        canonical_manifest_sha256=_sha256_hex(_canonical_json_bytes(raw)),
    )


def require_signed_physical_model_lock_amendment(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    amendment_submission_payload: object,
    now: datetime | None = None,
) -> VerifiedSignedPhysicalModelLockAmendment:
    """Revalidate a signature and exact approved visual receipt without writing.

    A future writer must invoke this gate in the same transaction as its own
    lock invalidation, then independently verify lifecycle and downstream
    dependencies.  This verifier never creates an admission record or changes
    the lock because verification is not execution authority.
    """

    item = _parse_manifest(_raw_manifest(manifest))
    estimate = db.get(Estimate, item["estimate_id"])
    if estimate is None or estimate.project_id != item["project_id"]:
        _fail("AMENDMENT_ESTIMATE_BINDING_INVALID")
    lock = db.get(PhysicalModelLock, item["target_lock_id"])
    if lock is None:
        _fail("AMENDMENT_TARGET_LOCK_MISSING")
    if lock.project_id != estimate.project_id or lock.estimate_id != estimate.id:
        _fail("AMENDMENT_TARGET_LOCK_BINDING_INVALID")
    if lock.invalidated_at is not None:
        _fail("AMENDMENT_TARGET_LOCK_NOT_ACTIVE")
    if not isinstance(lock.signature, str) or not lock.signature.strip():
        _fail("AMENDMENT_TARGET_LOCK_NOT_SIGNED")

    current_payload = build_current_physical_model_lock_payload(db, estimate)
    current_content_hash = str(current_payload["content_hash"])
    if lock.content_hash != current_content_hash:
        _fail("AMENDMENT_CURRENT_PHYSICAL_MODEL_MISMATCH")
    verified = verify_signed_physical_model_lock_amendment(
        manifest,
        pinned_public_key=pinned_public_key,
        expected_project_id=estimate.project_id,
        expected_estimate_id=estimate.id,
        expected_target_lock_id=lock.id,
        expected_target_lock_content_hash=lock.content_hash,
        expected_target_lock_signature_sha256=_sha256_hex(lock.signature.encode("utf-8")),
        expected_current_physical_model_content_hash=current_content_hash,
        amendment_submission_payload=amendment_submission_payload,
        expected_issuer=expected_issuer,
        expected_key_id=expected_key_id,
        now=now,
    )
    try:
        require_semantically_approved_visual_validation_receipt(
            db,
            receipt_sha256=verified.visual_validation_receipt_sha256,
            project_id=verified.project_id,
            estimate_id=verified.estimate_id,
            candidate_submission_payload_sha256=verified.amendment_submission_payload_sha256,
            controller_receipt_sha256=item["controller_receipt_sha256"],
            evidence_manifest_sha256=item["evidence_manifest_sha256"],
            evidence_family_inventory_sha256=item["evidence_family_inventory_sha256"],
            evidence_family_review_sha256=item["evidence_family_review_sha256"],
            human_review_request_sha256=item["human_review_request_sha256"],
            human_review_response_sha256=item["human_review_response_sha256"],
        )
    except VisualValidationReceiptError as exc:
        raise SignedPhysicalModelLockAmendmentError(
            "AMENDMENT_VISUAL_RECEIPT_INELIGIBLE"
        ) from exc
    return verified


def _parse_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    if set(item) != _FIELDS:
        _fail("AMENDMENT_MANIFEST_INVALID")
    if (
        item["schema"] != SIGNED_LOCK_AMENDMENT_SCHEMA
        or item["purpose"] != SIGNED_LOCK_AMENDMENT_PURPOSE
        or item["signature_algorithm"] != SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM
    ):
        _fail("AMENDMENT_MANIFEST_INVALID")
    for field_name in ("amendment_admission_id", "project_id", "estimate_id", "target_lock_id"):
        item[field_name] = _uuid(item[field_name])
    for field_name in (
        "target_lock_signature_sha256",
        "amendment_submission_payload_sha256",
        "visual_validation_receipt_sha256",
        "controller_receipt_sha256",
        "evidence_manifest_sha256",
        "evidence_family_inventory_sha256",
        "evidence_family_review_sha256",
        "human_review_request_sha256",
        "human_review_response_sha256",
    ):
        item[field_name] = _sha(item[field_name])
    for field_name in ("target_lock_content_hash", "current_physical_model_content_hash"):
        item[field_name] = _physical_model_hash(item[field_name])
    item["amendment_reason"] = _text(item["amendment_reason"], maximum=2000)
    item["policy_versions"] = _policy_versions(item["policy_versions"])
    item["issuer"] = _identifier(item["issuer"])
    item["key_id"] = _identifier(item["key_id"])
    item["issued_at"] = _timestamp(item["issued_at"])
    item["expires_at"] = _timestamp(item["expires_at"])
    if item["expires_at"] <= item["issued_at"]:
        _fail("AMENDMENT_MANIFEST_INVALID")
    _base64url(item["signature"], code="AMENDMENT_MANIFEST_INVALID")
    return item


def _canonical_submission_payload_sha256(payload: object) -> str:
    try:
        canonical_payload = InitialCanonicalPhysicalSubmission.model_validate(payload).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_PAYLOAD_INVALID") from exc
    return _sha256_hex(_canonical_json_bytes(canonical_payload))


def _raw_manifest(value: Mapping[str, Any] | bytes | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        item = dict(value)
    elif isinstance(value, bytes):
        if not value or len(value) > MAX_SIGNED_LOCK_AMENDMENT_BYTES:
            _fail("AMENDMENT_MANIFEST_INVALID")
        try:
            item = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SignedPhysicalModelLockAmendmentError("AMENDMENT_MANIFEST_INVALID") from exc
    elif isinstance(value, str):
        return _raw_manifest(value.encode("utf-8"))
    else:
        _fail("AMENDMENT_MANIFEST_INVALID")
    if not isinstance(item, dict):
        _fail("AMENDMENT_MANIFEST_INVALID")
    return item


def _canonical_json_bytes(value: object) -> bytes:
    _validate_json(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_MANIFEST_INVALID") from exc


def _validate_json(value: object, *, depth: int = 0) -> None:
    if depth > 64:
        _fail("AMENDMENT_MANIFEST_INVALID")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        _fail("AMENDMENT_MANIFEST_INVALID")
    if isinstance(value, list):
        for item in value:
            _validate_json(item, depth=depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item, depth=depth + 1)
        return
    _fail("AMENDMENT_MANIFEST_INVALID")


def _policy_versions(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("AMENDMENT_MANIFEST_INVALID")
    result = {_identifier(key): _identifier(item) for key, item in value.items()}
    if len(result) != len(value) or any(
        result.get(key) != policy for key, policy in _REQUIRED_POLICY_VERSIONS.items()
    ):
        _fail("AMENDMENT_POLICY_MISMATCH")
    return dict(sorted(result.items()))


def _load_p256_public_key(value: object) -> EllipticCurvePublicKey:
    raw = _base64url(value, code="AMENDMENT_PUBLIC_KEY_INVALID")
    try:
        key = serialization.load_der_public_key(raw)
    except ValueError as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_PUBLIC_KEY_INVALID") from exc
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        _fail("AMENDMENT_PUBLIC_KEY_INVALID")
    return key


def _validate_low_s_signature(signature: bytes) -> None:
    try:
        _unused_r, s = decode_dss_signature(signature)
    except ValueError as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_SIGNATURE_INVALID") from exc
    if s <= 0 or s > _P256_ORDER // 2:
        _fail("AMENDMENT_SIGNATURE_INVALID")


def _normalise_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        _fail("AMENDMENT_TIME_INVALID")
    return current.astimezone(UTC)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail("AMENDMENT_MANIFEST_INVALID")
    try:
        parsed = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_MANIFEST_INVALID") from exc
    if parsed != value:
        _fail("AMENDMENT_MANIFEST_INVALID")
    return parsed


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("AMENDMENT_MANIFEST_INVALID")
    return value


def _physical_model_hash(value: object) -> str:
    if not isinstance(value, str) or _PHYSICAL_MODEL_HASH.fullmatch(value) is None:
        _fail("AMENDMENT_MANIFEST_INVALID")
    return value

def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _fail("AMENDMENT_MANIFEST_INVALID")
    return value


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("AMENDMENT_MANIFEST_INVALID")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        _fail("AMENDMENT_MANIFEST_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SignedPhysicalModelLockAmendmentError("AMENDMENT_MANIFEST_INVALID") from exc


def _base64url(value: object, *, code: str) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        _fail(code)
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError as exc:
        raise SignedPhysicalModelLockAmendmentError(code) from exc


def _sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _require_equal(actual: object, expected: object, code: str) -> None:
    if actual != expected:
        _fail(code)


def _fail(code: str) -> NoReturn:
    raise SignedPhysicalModelLockAmendmentError(code)


__all__ = [
    "MAX_SIGNED_LOCK_AMENDMENT_BYTES",
    "SIGNED_LOCK_AMENDMENT_PURPOSE",
    "SIGNED_LOCK_AMENDMENT_SCHEMA",
    "SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM",
    "SignedPhysicalModelLockAmendmentError",
    "VerifiedSignedPhysicalModelLockAmendment",
    "require_signed_physical_model_lock_amendment",
    "signed_lock_amendment_signing_bytes",
    "verify_signed_physical_model_lock_amendment",
]
