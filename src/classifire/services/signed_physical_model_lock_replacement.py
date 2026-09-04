"""Verify a future signed replacement Physical Model Lock without creating it.

This module is read-only. It proves a short-lived P-256 signature is bound to
one intact amendment outcome, its invalidated signed lock, and the unchanged
amended physical model. It cannot create a lock or grant downstream authority.
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
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Estimate
from ..physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentAdmission,
    PhysicalModelLockAmendmentOutcome,
)
from .physical_model import (
    build_current_physical_model_lock_payload,
    build_current_physical_model_lock_snapshot,
)
from .physical_model_reopen import pretechnical_physical_amendment_dependency_code
from .signed_physical_model_lock_amendment_execution import (
    EXECUTION_RECEIPT_SCHEMA,
    SignedPhysicalModelLockAmendmentExecutionError,
    require_intact_signed_physical_model_lock_amendment_outcome,
)
from .signed_physical_model_lock_amendment_preflight import (
    lock_current_physical_model_rows,
)
from .visual_validation_receipt import (
    VISUAL_VALIDATION_RECEIPT_SCHEMA,
    VisualValidationReceiptError,
    require_semantically_approved_visual_validation_receipt,
)
from .workflow import WorkflowAction, WorkflowTransitionError
from .workflow_guard import require_estimate_action

SIGNED_REPLACEMENT_LOCK_SCHEMA = "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-REPLACEMENT-LOCK-v1"
SIGNED_REPLACEMENT_LOCK_PURPOSE = "create_replacement_physical_model_lock"
SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM = "ECDSA_P256_SHA256"
SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA = (
    "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-REPLACEMENT-LOCK-PREFLIGHT-v1"
)
MAX_SIGNED_REPLACEMENT_LOCK_BYTES = 64 * 1024
_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
_SHA256 = re.compile(r"^[0-9A-F]{64}$")
_PHYSICAL_MODEL_HASH = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@-]{0,159}$")
_BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_FIELDS = frozenset(
    {
        "schema",
        "replacement_lock_admission_id",
        "purpose",
        "project_id",
        "estimate_id",
        "amendment_outcome_id",
        "amendment_admission_id",
        "amendment_envelope_sha256",
        "amendment_execution_receipt_sha256",
        "visual_validation_receipt_sha256",
        "superseded_lock_id",
        "superseded_lock_content_hash",
        "replacement_lock_content_hash",
        "replacement_lock_reason",
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
    "amendment_execution": EXECUTION_RECEIPT_SCHEMA,
    "replacement_lock": (
        f"{SIGNED_REPLACEMENT_LOCK_SCHEMA}:{SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM}"
    ),
    "visual_validation_receipt": VISUAL_VALIDATION_RECEIPT_SCHEMA,
}


class SignedPhysicalModelLockReplacementError(RuntimeError):
    """Safe-code failure while checking replacement-lock eligibility."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed Physical Model Lock replacement failed: {code}.")


@dataclass(frozen=True, slots=True)
class VerifiedSignedPhysicalModelLockReplacement:
    replacement_lock_admission_id: str
    project_id: str
    estimate_id: str
    amendment_outcome_id: str
    amendment_admission_id: str
    amendment_envelope_sha256: str
    amendment_execution_receipt_sha256: str
    visual_validation_receipt_sha256: str
    superseded_lock_id: str
    superseded_lock_content_hash: str
    replacement_lock_content_hash: str
    replacement_lock_reason: str
    policy_versions: Mapping[str, str]
    issuer: str
    key_id: str
    issued_at: datetime
    expires_at: datetime
    canonical_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class SignedReplacementLockPreflightReceipt:
    replacement_lock_admission_id: str
    project_id: str
    estimate_id: str
    amendment_outcome_id: str
    superseded_lock_id: str
    replacement_lock_content_hash: str
    signed_manifest_sha256: str
    opening_count: int
    service_count: int
    service_opening_link_count: int
    preflighted_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "schema": SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA,
            "replacement_lock_admission_id": self.replacement_lock_admission_id,
            "project_id": self.project_id,
            "estimate_id": self.estimate_id,
            "amendment_outcome_id": self.amendment_outcome_id,
            "superseded_lock_id": self.superseded_lock_id,
            "replacement_lock_content_hash": self.replacement_lock_content_hash,
            "signed_manifest_sha256": self.signed_manifest_sha256,
            "opening_count": self.opening_count,
            "service_count": self.service_count,
            "service_opening_link_count": self.service_opening_link_count,
            "preflighted_at": self.preflighted_at,
            "physical_model_lock_created": False,
            "downstream_authority_granted": False,
        }


def signed_replacement_lock_signing_bytes(manifest: Mapping[str, Any] | bytes | str) -> bytes:
    """Return canonical unsigned bytes for one replacement-lock manifest."""

    raw = _raw_manifest(manifest)
    _parse_manifest(raw)
    unsigned = dict(raw)
    del unsigned["signature"]
    return _canonical_json_bytes(unsigned)


def verify_signed_physical_model_lock_replacement(
    manifest: Mapping[str, Any] | bytes | str,
    *,
    pinned_public_key: str,
    expected_bindings: Mapping[str, str],
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> VerifiedSignedPhysicalModelLockReplacement:
    """Verify the signature against independently supplied exact bindings."""

    raw = _raw_manifest(manifest)
    signing_bytes = signed_replacement_lock_signing_bytes(raw)
    item = _parse_manifest(raw)
    expected = {
        "project_id": _uuid(expected_bindings.get("project_id")),
        "estimate_id": _uuid(expected_bindings.get("estimate_id")),
        "amendment_outcome_id": _uuid(expected_bindings.get("amendment_outcome_id")),
        "amendment_admission_id": _uuid(expected_bindings.get("amendment_admission_id")),
        "amendment_envelope_sha256": _sha(expected_bindings.get("amendment_envelope_sha256")),
        "amendment_execution_receipt_sha256": _sha(
            expected_bindings.get("amendment_execution_receipt_sha256")
        ),
        "visual_validation_receipt_sha256": _sha(
            expected_bindings.get("visual_validation_receipt_sha256")
        ),
        "superseded_lock_id": _uuid(expected_bindings.get("superseded_lock_id")),
        "superseded_lock_content_hash": _physical_model_hash(
            expected_bindings.get("superseded_lock_content_hash")
        ),
        "replacement_lock_content_hash": _physical_model_hash(
            expected_bindings.get("replacement_lock_content_hash")
        ),
    }
    if set(expected_bindings) != set(expected) or any(
        item[field] != value for field, value in expected.items()
    ):
        _fail("REPLACEMENT_LOCK_BINDING_MISMATCH")
    if item["issuer"] != _identifier(expected_issuer):
        _fail("REPLACEMENT_LOCK_ISSUER_MISMATCH")
    if item["key_id"] != _identifier(expected_key_id):
        _fail("REPLACEMENT_LOCK_KEY_MISMATCH")
    current_time = _normalise_now(now)
    if item["expires_at"] <= current_time or item["issued_at"] > current_time:
        _fail("REPLACEMENT_LOCK_EXPIRED")
    key = _load_p256_public_key(pinned_public_key)
    signature = _base64url(item["signature"], code="REPLACEMENT_LOCK_SIGNATURE_INVALID")
    _validate_low_s_signature(signature)
    try:
        key.verify(signature, signing_bytes, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        _fail("REPLACEMENT_LOCK_SIGNATURE_INVALID")
    return VerifiedSignedPhysicalModelLockReplacement(
        replacement_lock_admission_id=item["replacement_lock_admission_id"],
        project_id=item["project_id"],
        estimate_id=item["estimate_id"],
        amendment_outcome_id=item["amendment_outcome_id"],
        amendment_admission_id=item["amendment_admission_id"],
        amendment_envelope_sha256=item["amendment_envelope_sha256"],
        amendment_execution_receipt_sha256=item["amendment_execution_receipt_sha256"],
        visual_validation_receipt_sha256=item["visual_validation_receipt_sha256"],
        superseded_lock_id=item["superseded_lock_id"],
        superseded_lock_content_hash=item["superseded_lock_content_hash"],
        replacement_lock_content_hash=item["replacement_lock_content_hash"],
        replacement_lock_reason=item["replacement_lock_reason"],
        policy_versions=MappingProxyType(dict(item["policy_versions"])),
        issuer=item["issuer"],
        key_id=item["key_id"],
        issued_at=item["issued_at"],
        expires_at=item["expires_at"],
        canonical_manifest_sha256=_sha256(_canonical_json_bytes(raw)),
    )


def preflight_signed_replacement_physical_model_lock(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> SignedReplacementLockPreflightReceipt:
    """Lock and recheck exact replacement eligibility without writing anything."""

    current_time = _normalise_now(now)
    raw = _raw_manifest(manifest)
    item = _parse_manifest(raw)
    estimate = db.scalar(
        select(Estimate).where(Estimate.id == item["estimate_id"]).with_for_update()
    )
    outcome = db.scalar(
        select(PhysicalModelLockAmendmentOutcome)
        .where(PhysicalModelLockAmendmentOutcome.id == item["amendment_outcome_id"])
        .with_for_update()
    )
    if estimate is None or outcome is None or estimate.project_id != item["project_id"]:
        _fail("REPLACEMENT_LOCK_BINDING_INVALID")
    if (estimate.status or "").strip().lower() not in {"draft", "in_review"}:
        _fail("REPLACEMENT_LOCK_ESTIMATE_STATUS_INVALID")
    openings = lock_current_physical_model_rows(db, estimate)
    admission = db.scalar(
        select(PhysicalModelLockAmendmentAdmission)
        .where(PhysicalModelLockAmendmentAdmission.id == outcome.admission_record_id)
        .with_for_update()
    )
    superseded_lock = db.scalar(
        select(PhysicalModelLock)
        .where(PhysicalModelLock.id == item["superseded_lock_id"])
        .with_for_update()
    )
    if admission is None or superseded_lock is None:
        _fail("REPLACEMENT_LOCK_BINDING_INVALID")
    active_locks = list(
        db.scalars(
            select(PhysicalModelLock)
            .where(
                PhysicalModelLock.estimate_id == estimate.id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
            .with_for_update()
        ).all()
    )
    if active_locks:
        _fail("REPLACEMENT_LOCK_ACTIVE_LOCK_PRESENT")
    try:
        require_intact_signed_physical_model_lock_amendment_outcome(
            db,
            outcome,
            expected_amendment_envelope_sha256=item["amendment_envelope_sha256"],
        )
    except SignedPhysicalModelLockAmendmentExecutionError as exc:
        raise SignedPhysicalModelLockReplacementError(
            "REPLACEMENT_LOCK_AMENDMENT_OUTCOME_INVALID"
        ) from exc
    if not (
        outcome.project_id == estimate.project_id
        and outcome.estimate_id == estimate.id
        and outcome.amendment_admission_id == item["amendment_admission_id"]
        and outcome.execution_receipt_sha256 == item["amendment_execution_receipt_sha256"]
        and outcome.target_lock_id == superseded_lock.id
        and outcome.target_lock_content_hash == superseded_lock.content_hash
        and admission.visual_validation_receipt_sha256 == item["visual_validation_receipt_sha256"]
        and isinstance(superseded_lock.signature, str)
        and bool(superseded_lock.signature.strip())
        and hashlib.sha256(superseded_lock.signature.encode("utf-8")).hexdigest().upper()
        == admission.target_lock_signature_sha256
        and superseded_lock.invalidated_at is not None
    ):
        _fail("REPLACEMENT_LOCK_BINDING_INVALID")
    try:
        amendment_envelope = json.loads(admission.amendment_envelope_json)
        if not isinstance(amendment_envelope, dict):
            raise ValueError("amendment envelope is not an object")
        require_semantically_approved_visual_validation_receipt(
            db,
            receipt_sha256=admission.visual_validation_receipt_sha256,
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            candidate_submission_payload_sha256=admission.amendment_submission_payload_sha256,
            controller_receipt_sha256=amendment_envelope["controller_receipt_sha256"],
            evidence_manifest_sha256=amendment_envelope["evidence_manifest_sha256"],
            evidence_family_inventory_sha256=(
                amendment_envelope["evidence_family_inventory_sha256"]
            ),
            evidence_family_review_sha256=amendment_envelope["evidence_family_review_sha256"],
            human_review_request_sha256=amendment_envelope["human_review_request_sha256"],
            human_review_response_sha256=amendment_envelope["human_review_response_sha256"],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        VisualValidationReceiptError,
    ) as exc:
        raise SignedPhysicalModelLockReplacementError(
            "REPLACEMENT_LOCK_VISUAL_RECEIPT_INVALID"
        ) from exc
    current_snapshot = build_current_physical_model_lock_snapshot(db, estimate)
    if not (
        current_snapshot.content_hash == outcome.post_physical_model_content_hash
        and current_snapshot.canonical_payload_json == outcome.post_physical_model_payload_json
        and current_snapshot.content_hash == item["replacement_lock_content_hash"]
        and superseded_lock.content_hash == item["superseded_lock_content_hash"]
    ):
        _fail("REPLACEMENT_LOCK_CURRENT_STATE_MISMATCH")
    current_payload = build_current_physical_model_lock_payload(db, estimate)
    if current_payload["critical_unknowns"] or current_payload["validator_result"] != "PASS":
        _fail("REPLACEMENT_LOCK_PHYSICAL_MODEL_INCOMPLETE")
    try:
        require_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)
    except WorkflowTransitionError as exc:
        raise SignedPhysicalModelLockReplacementError("REPLACEMENT_LOCK_INELIGIBLE") from exc
    dependency = pretechnical_physical_amendment_dependency_code(db, estimate, openings)
    if dependency is not None:
        _fail(
            {
                "technical": "REPLACEMENT_LOCK_TECHNICAL_DEPENDENCY_PRESENT",
                "commercial": "REPLACEMENT_LOCK_COMMERCIAL_DEPENDENCY_PRESENT",
                "rule": "REPLACEMENT_LOCK_RULE_DEPENDENCY_PRESENT",
                "snapshot_or_release": "REPLACEMENT_LOCK_SNAPSHOT_OR_RELEASE_PRESENT",
            }[dependency]
        )
    bindings = {
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "amendment_outcome_id": outcome.id,
        "amendment_admission_id": outcome.amendment_admission_id,
        "amendment_envelope_sha256": outcome.amendment_envelope_sha256,
        "amendment_execution_receipt_sha256": outcome.execution_receipt_sha256,
        "visual_validation_receipt_sha256": admission.visual_validation_receipt_sha256,
        "superseded_lock_id": superseded_lock.id,
        "superseded_lock_content_hash": superseded_lock.content_hash,
        "replacement_lock_content_hash": current_snapshot.content_hash,
    }
    verified = verify_signed_physical_model_lock_replacement(
        raw,
        pinned_public_key=pinned_public_key,
        expected_bindings=bindings,
        expected_issuer=expected_issuer,
        expected_key_id=expected_key_id,
        now=current_time,
    )
    payload = current_snapshot.as_dict()
    return SignedReplacementLockPreflightReceipt(
        replacement_lock_admission_id=verified.replacement_lock_admission_id,
        project_id=verified.project_id,
        estimate_id=verified.estimate_id,
        amendment_outcome_id=verified.amendment_outcome_id,
        superseded_lock_id=verified.superseded_lock_id,
        replacement_lock_content_hash=verified.replacement_lock_content_hash,
        signed_manifest_sha256=verified.canonical_manifest_sha256,
        opening_count=len(payload["openings"]),
        service_count=len(payload["services"]),
        service_opening_link_count=len(payload["service_opening_links"]),
        preflighted_at=_timestamp_text(current_time),
    )


def _parse_manifest(raw: Mapping[str, Any]) -> dict[str, Any]:
    item = dict(raw)
    if set(item) != _FIELDS:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    if (
        item["schema"] != SIGNED_REPLACEMENT_LOCK_SCHEMA
        or item["purpose"] != SIGNED_REPLACEMENT_LOCK_PURPOSE
        or item["signature_algorithm"] != SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM
    ):
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    for field_name in (
        "replacement_lock_admission_id",
        "project_id",
        "estimate_id",
        "amendment_outcome_id",
        "amendment_admission_id",
        "superseded_lock_id",
    ):
        item[field_name] = _uuid(item[field_name])
    for field_name in (
        "amendment_envelope_sha256",
        "amendment_execution_receipt_sha256",
        "visual_validation_receipt_sha256",
    ):
        item[field_name] = _sha(item[field_name])
    for field_name in ("superseded_lock_content_hash", "replacement_lock_content_hash"):
        item[field_name] = _physical_model_hash(item[field_name])
    item["replacement_lock_reason"] = _text(item["replacement_lock_reason"], maximum=2000)
    item["policy_versions"] = _policy_versions(item["policy_versions"])
    item["issuer"] = _identifier(item["issuer"])
    item["key_id"] = _identifier(item["key_id"])
    item["issued_at"] = _timestamp(item["issued_at"])
    item["expires_at"] = _timestamp(item["expires_at"])
    if item["expires_at"] <= item["issued_at"]:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    _base64url(item["signature"], code="REPLACEMENT_LOCK_MANIFEST_INVALID")
    return item


def _raw_manifest(value: Mapping[str, Any] | bytes | str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        item = dict(value)
    elif isinstance(value, bytes):
        if not value or len(value) > MAX_SIGNED_REPLACEMENT_LOCK_BYTES:
            _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
        try:
            item = json.loads(value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SignedPhysicalModelLockReplacementError(
                "REPLACEMENT_LOCK_MANIFEST_INVALID"
            ) from exc
    elif isinstance(value, str):
        return _raw_manifest(value.encode("utf-8"))
    else:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    if not isinstance(item, dict):
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return item


def _canonical_json_bytes(value: object) -> bytes:
    _validate_json(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SignedPhysicalModelLockReplacementError("REPLACEMENT_LOCK_MANIFEST_INVALID") from exc


def _validate_json(value: object, *, depth: int = 0) -> None:
    if depth > 64:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    if isinstance(value, list):
        for item in value:
            _validate_json(item, depth=depth + 1)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for item in value.values():
            _validate_json(item, depth=depth + 1)
        return
    _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")


def _policy_versions(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    result = {_identifier(key): _identifier(item) for key, item in value.items()}
    if len(result) != len(value) or any(
        result.get(key) != policy for key, policy in _REQUIRED_POLICY_VERSIONS.items()
    ):
        _fail("REPLACEMENT_LOCK_POLICY_MISMATCH")
    return dict(sorted(result.items()))


def _load_p256_public_key(value: object) -> EllipticCurvePublicKey:
    raw = _base64url(value, code="REPLACEMENT_LOCK_PUBLIC_KEY_INVALID")
    try:
        key = serialization.load_der_public_key(raw)
    except ValueError as exc:
        raise SignedPhysicalModelLockReplacementError(
            "REPLACEMENT_LOCK_PUBLIC_KEY_INVALID"
        ) from exc
    if not isinstance(key, EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        _fail("REPLACEMENT_LOCK_PUBLIC_KEY_INVALID")
    return key


def _validate_low_s_signature(signature: bytes) -> None:
    try:
        _unused_r, s = decode_dss_signature(signature)
    except ValueError as exc:
        raise SignedPhysicalModelLockReplacementError("REPLACEMENT_LOCK_SIGNATURE_INVALID") from exc
    if s <= 0 or s > _P256_ORDER // 2:
        _fail("REPLACEMENT_LOCK_SIGNATURE_INVALID")


def _normalise_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        _fail("REPLACEMENT_LOCK_TIME_INVALID")
    return current.astimezone(UTC)


def _uuid(value: object) -> str:
    if not isinstance(value, str):
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    try:
        parsed = str(UUID(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise SignedPhysicalModelLockReplacementError("REPLACEMENT_LOCK_MANIFEST_INVALID") from exc
    if parsed != value:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return parsed


def _sha(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return value


def _physical_model_hash(value: object) -> str:
    if not isinstance(value, str) or _PHYSICAL_MODEL_HASH.fullmatch(value) is None:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return value


def _identifier(value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return value


def _text(value: object, *, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or _TIMESTAMP.fullmatch(value) is None:
        _fail("REPLACEMENT_LOCK_MANIFEST_INVALID")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise SignedPhysicalModelLockReplacementError("REPLACEMENT_LOCK_MANIFEST_INVALID") from exc


def _base64url(value: object, *, code: str) -> bytes:
    if not isinstance(value, str) or _BASE64URL.fullmatch(value) is None:
        _fail(code)
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except ValueError as exc:
        raise SignedPhysicalModelLockReplacementError(code) from exc


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fail(code: str) -> NoReturn:
    raise SignedPhysicalModelLockReplacementError(code)


__all__ = [
    "MAX_SIGNED_REPLACEMENT_LOCK_BYTES",
    "SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA",
    "SIGNED_REPLACEMENT_LOCK_PURPOSE",
    "SIGNED_REPLACEMENT_LOCK_SCHEMA",
    "SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM",
    "SignedPhysicalModelLockReplacementError",
    "SignedReplacementLockPreflightReceipt",
    "VerifiedSignedPhysicalModelLockReplacement",
    "preflight_signed_replacement_physical_model_lock",
    "signed_replacement_lock_signing_bytes",
    "verify_signed_physical_model_lock_replacement",
]
