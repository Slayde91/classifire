"""Record a verified signed lock-amendment admission without executing it.

This is an additive journal boundary, not the signed lock-amendment writer. It
persists the exact signed manifest, canonical prospective payload, and a fresh
preflight receipt in one caller-owned transaction, while leaving the active
Physical Model Lock and all canonical physical rows untouched.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import PhysicalModelLockAmendmentAdmission
from .signed_physical_model_lock_amendment_preflight import (
    SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA,
    SignedPhysicalModelLockAmendmentPreflightError,
    SignedPhysicalModelLockAmendmentPreflightReceipt,
    preflight_signed_physical_model_lock_amendment,
)


class SignedPhysicalModelLockAmendmentAdmissionError(RuntimeError):
    """Safe-code failure while recording a signed amendment admission."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed Physical Model Lock amendment admission failed: {code}.")


@dataclass(frozen=True, slots=True)
class PreflightedRegisteredSignedPhysicalModelLockAmendment:
    """An intact registered candidate freshly rechecked for a future writer."""

    admission_record_id: str
    amendment_submission: InitialCanonicalPhysicalSubmission
    preflight_receipt: SignedPhysicalModelLockAmendmentPreflightReceipt


def preflight_registered_signed_physical_model_lock_amendment(
    db: Session,
    *,
    amendment_admission_id: str,
    expected_amendment_envelope_sha256: str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> PreflightedRegisteredSignedPhysicalModelLockAmendment:
    """Reload one journal record and freshly recheck it without executing it.

    The caller owns the transaction. The returned binding is suitable only for
    a future writer that keeps this transaction open and separately records its
    exact canonical mutation outcome. This function performs no mutation,
    invalidation, replacement lock, audit event, or authority grant.
    """

    admission = db.scalar(
        select(PhysicalModelLockAmendmentAdmission)
        .where(PhysicalModelLockAmendmentAdmission.amendment_admission_id == amendment_admission_id)
        .with_for_update()
    )
    if admission is None:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_NOT_FOUND")
    if admission.amendment_envelope_sha256 != expected_amendment_envelope_sha256:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_BINDING_INVALID")

    try:
        manifest_json = _canonical_manifest_text(admission.amendment_envelope_json)
        payload = InitialCanonicalPhysicalSubmission.model_validate_json(
            admission.amendment_submission_payload_json
        )
        canonical_payload_json = _canonical_json(payload.model_dump(mode="json"))
    except (SignedPhysicalModelLockAmendmentAdmissionError, ValidationError, ValueError) as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT") from exc
    if (
        manifest_json != admission.amendment_envelope_json
        or _sha256(manifest_json) != admission.amendment_envelope_sha256
        or canonical_payload_json != admission.amendment_submission_payload_json
        or _sha256(canonical_payload_json) != admission.amendment_submission_payload_sha256
    ):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")

    try:
        preflight = preflight_signed_physical_model_lock_amendment(
            db,
            manifest=manifest_json,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            amendment_submission_payload=payload.model_dump(mode="json"),
            now=now,
        )
    except SignedPhysicalModelLockAmendmentPreflightError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError(exc.code) from exc
    envelope = _manifest_object(manifest_json)
    _require_intact_replay(
        admission,
        preflight=preflight,
        envelope=envelope,
        manifest_json=manifest_json,
        canonical_payload_json=canonical_payload_json,
    )
    return PreflightedRegisteredSignedPhysicalModelLockAmendment(
        admission_record_id=admission.id,
        amendment_submission=payload,
        preflight_receipt=preflight,
    )


def register_signed_physical_model_lock_amendment_admission(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    amendment_submission_payload: object,
    operator_reference: str,
    now: datetime | None = None,
) -> tuple[PhysicalModelLockAmendmentAdmission, bool]:
    """Record one fresh, verified signed amendment admission.

    The caller owns the surrounding transaction. This function first runs the
    locked no-write preflight, then stores only evidence of that admission. It
    does not invalidate a lock, edit physical rows, create a replacement lock,
    create an execution receipt, or confer technical, commercial, or release
    authority. Exact signed-manifest replays are idempotent while still eligible.
    """

    operator = _operator_reference(operator_reference)
    manifest_json = _canonical_manifest_text(manifest)
    try:
        payload = InitialCanonicalPhysicalSubmission.model_validate(amendment_submission_payload)
    except ValidationError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_PAYLOAD_INVALID") from exc
    canonical_payload = payload.model_dump(mode="json")

    try:
        preflight = preflight_signed_physical_model_lock_amendment(
            db,
            manifest=manifest_json,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            amendment_submission_payload=canonical_payload,
            now=now,
        )
    except SignedPhysicalModelLockAmendmentPreflightError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError(exc.code) from exc

    envelope = _manifest_object(manifest_json)
    manifest_sha256 = _sha256(manifest_json)
    if manifest_sha256 != preflight.canonical_manifest_sha256:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_CORRUPT")
    if envelope["amendment_submission_payload_sha256"] != (
        preflight.amendment_submission_payload_sha256
    ):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_PREFLIGHT_BINDING_INVALID")
    if envelope["visual_validation_receipt_sha256"] != preflight.visual_validation_receipt_sha256:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_PREFLIGHT_BINDING_INVALID")

    existing = db.scalar(
        select(PhysicalModelLockAmendmentAdmission)
        .where(
            PhysicalModelLockAmendmentAdmission.amendment_admission_id
            == preflight.amendment_admission_id
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.amendment_envelope_sha256 != manifest_sha256:
            raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_REPLAY_CONFLICT")
        _require_intact_replay(
            existing,
            preflight=preflight,
            envelope=envelope,
            manifest_json=manifest_json,
            canonical_payload_json=_canonical_json(canonical_payload),
        )
        return existing, False

    preflight_receipt_json = _canonical_json(preflight.as_dict())
    admission = PhysicalModelLockAmendmentAdmission(
        amendment_admission_id=preflight.amendment_admission_id,
        project_id=preflight.project_id,
        estimate_id=preflight.estimate_id,
        target_lock_id=preflight.target_lock_id,
        target_lock_content_hash=preflight.target_lock_content_hash,
        target_lock_signature_sha256=envelope["target_lock_signature_sha256"],
        current_physical_model_content_hash=envelope["current_physical_model_content_hash"],
        amendment_submission_payload_sha256=preflight.amendment_submission_payload_sha256,
        amendment_submission_payload_json=_canonical_json(canonical_payload),
        visual_validation_receipt_sha256=preflight.visual_validation_receipt_sha256,
        amendment_reason=envelope["amendment_reason"],
        policy_versions=envelope["policy_versions"],
        amendment_envelope_json=manifest_json,
        amendment_envelope_sha256=manifest_sha256,
        issuer_id=envelope["issuer"],
        signing_key_id=envelope["key_id"],
        signature_algorithm=envelope["signature_algorithm"],
        issued_at=_timestamp(envelope["issued_at"]),
        expires_at=_timestamp(envelope["expires_at"]),
        preflight_receipt_json=preflight_receipt_json,
        preflight_receipt_sha256=_sha256(preflight_receipt_json),
    )
    try:
        with db.begin_nested():
            db.add(admission)
            db.flush()
    except IntegrityError as exc:
        replay = db.scalar(
            select(PhysicalModelLockAmendmentAdmission)
            .where(
                PhysicalModelLockAmendmentAdmission.amendment_admission_id
                == preflight.amendment_admission_id
            )
            .with_for_update()
        )
        if replay is not None and replay.amendment_envelope_sha256 == manifest_sha256:
            _require_intact_replay(
                replay,
                preflight=preflight,
                envelope=envelope,
                manifest_json=manifest_json,
                canonical_payload_json=_canonical_json(canonical_payload),
            )
            return replay, False
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_REPLAY_CONFLICT") from exc

    record_audit(
        db,
        actor=None,
        actor_type="human_governance",
        actor_name=operator,
        action="register_signed_physical_model_lock_amendment_admission",
        entity_type="physical_model_lock_amendment_admission",
        entity_id=admission.id,
        project_id=admission.project_id,
        new_value={
            "amendment_admission_id": admission.amendment_admission_id,
            "target_lock_id": admission.target_lock_id,
            "amendment_envelope_sha256": admission.amendment_envelope_sha256,
            "preflight_receipt_sha256": admission.preflight_receipt_sha256,
            "canonical_write_performed": False,
            "physical_model_lock_invalidated": False,
            "physical_model_lock_created": False,
            "execution_authority_granted": False,
        },
        reason=(
            "Verified signed amendment admission recorded without lock invalidation, "
            "physical-model mutation, replacement lock, or execution authority."
        ),
    )
    return admission, True


def _require_intact_replay(
    admission: PhysicalModelLockAmendmentAdmission,
    *,
    preflight: SignedPhysicalModelLockAmendmentPreflightReceipt,
    envelope: dict[str, Any],
    manifest_json: str,
    canonical_payload_json: str,
) -> None:
    """Reject a replay if any retained journal binding has drifted."""

    expected = {
        "project_id": preflight.project_id,
        "estimate_id": preflight.estimate_id,
        "target_lock_id": preflight.target_lock_id,
        "target_lock_content_hash": preflight.target_lock_content_hash,
        "target_lock_signature_sha256": envelope["target_lock_signature_sha256"],
        "current_physical_model_content_hash": envelope["current_physical_model_content_hash"],
        "amendment_submission_payload_sha256": preflight.amendment_submission_payload_sha256,
        "amendment_submission_payload_json": canonical_payload_json,
        "visual_validation_receipt_sha256": preflight.visual_validation_receipt_sha256,
        "amendment_reason": envelope["amendment_reason"],
        "policy_versions": envelope["policy_versions"],
        "amendment_envelope_json": manifest_json,
        "issuer_id": envelope["issuer"],
        "signing_key_id": envelope["key_id"],
        "signature_algorithm": envelope["signature_algorithm"],
    }
    if any(getattr(admission, field) != value for field, value in expected.items()):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")
    if not _same_timestamp(admission.issued_at, _timestamp(envelope["issued_at"])) or not (
        _same_timestamp(admission.expires_at, _timestamp(envelope["expires_at"]))
    ):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")
    if _sha256(admission.amendment_envelope_json) != admission.amendment_envelope_sha256:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")
    if _sha256(admission.amendment_submission_payload_json) != (
        admission.amendment_submission_payload_sha256
    ):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")

    try:
        retained_preflight = _manifest_object(admission.preflight_receipt_json)
        canonical_preflight = _canonical_json(retained_preflight)
    except SignedPhysicalModelLockAmendmentAdmissionError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT") from exc
    if (
        admission.preflight_receipt_json != canonical_preflight
        or _sha256(admission.preflight_receipt_json) != admission.preflight_receipt_sha256
    ):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")
    expected_preflight = {
        "schema": SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA,
        "amendment_admission_id": admission.amendment_admission_id,
        "project_id": admission.project_id,
        "estimate_id": admission.estimate_id,
        "target_lock_id": admission.target_lock_id,
        "target_lock_content_hash": admission.target_lock_content_hash,
        "amendment_submission_payload_sha256": admission.amendment_submission_payload_sha256,
        "visual_validation_receipt_sha256": admission.visual_validation_receipt_sha256,
        "canonical_manifest_sha256": admission.amendment_envelope_sha256,
    }
    if any(retained_preflight.get(field) != value for field, value in expected_preflight.items()):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_ADMISSION_CORRUPT")


def _same_timestamp(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None or left.utcoffset() is None:
        left = left.replace(tzinfo=right.tzinfo)
    return left == right


def _operator_reference(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_OPERATOR_INVALID")
    return value.strip()


def _canonical_manifest_text(value: Mapping[str, Any] | bytes | str) -> str:
    if isinstance(value, bytes):
        try:
            raw = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SignedPhysicalModelLockAmendmentAdmissionError(
                "AMENDMENT_MANIFEST_INVALID"
            ) from exc
    elif isinstance(value, str):
        raw = value
    elif isinstance(value, Mapping):
        raw = None
        parsed: object = dict(value)
    else:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID")
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SignedPhysicalModelLockAmendmentAdmissionError(
                "AMENDMENT_MANIFEST_INVALID"
            ) from exc
    if not isinstance(parsed, dict):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID")
    return _canonical_json(parsed)


def _manifest_object(manifest_json: str) -> dict[str, Any]:
    try:
        value = json.loads(manifest_json)
    except json.JSONDecodeError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID") from exc
    if not isinstance(value, dict):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID")
    return value


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID") from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SignedPhysicalModelLockAmendmentAdmissionError("AMENDMENT_MANIFEST_INVALID")
    return parsed


__all__ = [
    "PreflightedRegisteredSignedPhysicalModelLockAmendment",
    "SignedPhysicalModelLockAmendmentAdmissionError",
    "preflight_registered_signed_physical_model_lock_amendment",
    "register_signed_physical_model_lock_amendment_admission",
]
