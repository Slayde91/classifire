"""Journal an exact signed replacement-lock approval without creating a lock.

The caller owns the transaction. Registration reruns the locked no-write
preflight and stores the canonical signed envelope plus its preflight receipt.
No Physical Model Lock or downstream authority is created here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..physical_models import PhysicalModelLockReplacementAdmission
from .signed_physical_model_lock_replacement import (
    SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA,
    SignedPhysicalModelLockReplacementError,
    SignedReplacementLockPreflightReceipt,
    preflight_signed_replacement_physical_model_lock,
)


class SignedPhysicalModelLockReplacementAdmissionError(RuntimeError):
    """Safe-code failure while recording replacement-lock approval evidence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed replacement-lock admission failed: {code}.")


@dataclass(frozen=True, slots=True)
class PreflightedRegisteredSignedPhysicalModelLockReplacement:
    """One intact registered approval freshly rechecked for a future writer."""

    admission_record_id: str
    preflight_receipt: SignedReplacementLockPreflightReceipt


def preflight_registered_signed_physical_model_lock_replacement(
    db: Session,
    *,
    replacement_lock_admission_id: str,
    expected_replacement_lock_envelope_sha256: str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    now: datetime | None = None,
) -> PreflightedRegisteredSignedPhysicalModelLockReplacement:
    """Lock, reload, and freshly recheck one retained approval without writing."""

    admission = db.scalar(
        select(PhysicalModelLockReplacementAdmission)
        .where(
            PhysicalModelLockReplacementAdmission.replacement_lock_admission_id
            == replacement_lock_admission_id
        )
        .with_for_update()
    )
    if admission is None:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_NOT_FOUND"
        )
    if admission.replacement_lock_envelope_sha256 != (
        expected_replacement_lock_envelope_sha256
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_BINDING_INVALID"
        )

    try:
        manifest_json = _canonical_manifest_text(admission.replacement_lock_envelope_json)
    except SignedPhysicalModelLockReplacementAdmissionError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        ) from exc
    if (
        manifest_json != admission.replacement_lock_envelope_json
        or _sha256(manifest_json) != admission.replacement_lock_envelope_sha256
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )

    try:
        preflight = preflight_signed_replacement_physical_model_lock(
            db,
            manifest=manifest_json,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            now=now,
        )
    except SignedPhysicalModelLockReplacementError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(exc.code) from exc
    envelope = _manifest_object(manifest_json)
    _require_intact_replay(
        admission,
        preflight=preflight,
        envelope=envelope,
        manifest_json=manifest_json,
    )
    return PreflightedRegisteredSignedPhysicalModelLockReplacement(
        admission_record_id=admission.id,
        preflight_receipt=preflight,
    )


def register_signed_physical_model_lock_replacement_admission(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    operator_reference: str,
    now: datetime | None = None,
) -> tuple[PhysicalModelLockReplacementAdmission, bool]:
    """Record one fresh approval after locked preflight, without creating a lock."""

    operator = _operator_reference(operator_reference)
    manifest_json = _canonical_manifest_text(manifest)
    try:
        preflight = preflight_signed_replacement_physical_model_lock(
            db,
            manifest=manifest_json,
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            now=now,
        )
    except SignedPhysicalModelLockReplacementError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(exc.code) from exc

    envelope = _manifest_object(manifest_json)
    manifest_sha256 = _sha256(manifest_json)
    if manifest_sha256 != preflight.signed_manifest_sha256:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_CORRUPT"
        )

    existing = db.scalar(
        select(PhysicalModelLockReplacementAdmission)
        .where(
            PhysicalModelLockReplacementAdmission.replacement_lock_admission_id
            == preflight.replacement_lock_admission_id
        )
        .with_for_update()
    )
    if existing is not None:
        if existing.replacement_lock_envelope_sha256 != manifest_sha256:
            raise SignedPhysicalModelLockReplacementAdmissionError(
                "REPLACEMENT_LOCK_REPLAY_CONFLICT"
            )
        _require_intact_replay(
            existing,
            preflight=preflight,
            envelope=envelope,
            manifest_json=manifest_json,
        )
        return existing, False

    preflight_receipt_json = _canonical_json(preflight.as_dict())
    admission = PhysicalModelLockReplacementAdmission(
        replacement_lock_admission_id=preflight.replacement_lock_admission_id,
        project_id=preflight.project_id,
        estimate_id=preflight.estimate_id,
        amendment_outcome_id=preflight.amendment_outcome_id,
        amendment_admission_id=envelope["amendment_admission_id"],
        amendment_envelope_sha256=envelope["amendment_envelope_sha256"],
        amendment_execution_receipt_sha256=envelope[
            "amendment_execution_receipt_sha256"
        ],
        visual_validation_receipt_sha256=envelope["visual_validation_receipt_sha256"],
        superseded_lock_id=preflight.superseded_lock_id,
        superseded_lock_content_hash=envelope["superseded_lock_content_hash"],
        replacement_lock_content_hash=preflight.replacement_lock_content_hash,
        replacement_lock_reason=envelope["replacement_lock_reason"],
        policy_versions=envelope["policy_versions"],
        replacement_lock_envelope_json=manifest_json,
        replacement_lock_envelope_sha256=manifest_sha256,
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
            select(PhysicalModelLockReplacementAdmission)
            .where(
                PhysicalModelLockReplacementAdmission.replacement_lock_admission_id
                == preflight.replacement_lock_admission_id
            )
            .with_for_update()
        )
        if replay is not None and replay.replacement_lock_envelope_sha256 == manifest_sha256:
            _require_intact_replay(
                replay,
                preflight=preflight,
                envelope=envelope,
                manifest_json=manifest_json,
            )
            return replay, False
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_REPLAY_CONFLICT"
        ) from exc

    record_audit(
        db,
        actor=None,
        actor_type="human_governance",
        actor_name=operator,
        action="register_signed_physical_model_lock_replacement_admission",
        entity_type="physical_model_lock_replacement_admission",
        entity_id=admission.id,
        project_id=admission.project_id,
        new_value={
            "replacement_lock_admission_id": admission.replacement_lock_admission_id,
            "amendment_outcome_id": admission.amendment_outcome_id,
            "superseded_lock_id": admission.superseded_lock_id,
            "replacement_lock_content_hash": admission.replacement_lock_content_hash,
            "replacement_lock_envelope_sha256": (
                admission.replacement_lock_envelope_sha256
            ),
            "preflight_receipt_sha256": admission.preflight_receipt_sha256,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
            "downstream_authority_granted": False,
        },
        reason=(
            "Verified signed replacement-lock admission recorded without creating "
            "a Physical Model Lock or granting downstream authority."
        ),
    )
    return admission, True


def _require_intact_replay(
    admission: PhysicalModelLockReplacementAdmission,
    *,
    preflight: SignedReplacementLockPreflightReceipt,
    envelope: dict[str, Any],
    manifest_json: str,
) -> None:
    expected = {
        "project_id": preflight.project_id,
        "estimate_id": preflight.estimate_id,
        "amendment_outcome_id": preflight.amendment_outcome_id,
        "amendment_admission_id": envelope["amendment_admission_id"],
        "amendment_envelope_sha256": envelope["amendment_envelope_sha256"],
        "amendment_execution_receipt_sha256": envelope[
            "amendment_execution_receipt_sha256"
        ],
        "visual_validation_receipt_sha256": envelope[
            "visual_validation_receipt_sha256"
        ],
        "superseded_lock_id": preflight.superseded_lock_id,
        "superseded_lock_content_hash": envelope["superseded_lock_content_hash"],
        "replacement_lock_content_hash": preflight.replacement_lock_content_hash,
        "replacement_lock_reason": envelope["replacement_lock_reason"],
        "policy_versions": envelope["policy_versions"],
        "replacement_lock_envelope_json": manifest_json,
        "issuer_id": envelope["issuer"],
        "signing_key_id": envelope["key_id"],
        "signature_algorithm": envelope["signature_algorithm"],
    }
    if any(getattr(admission, field) != value for field, value in expected.items()):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )
    if not _same_timestamp(admission.issued_at, _timestamp(envelope["issued_at"])) or not (
        _same_timestamp(admission.expires_at, _timestamp(envelope["expires_at"]))
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )
    if _sha256(admission.replacement_lock_envelope_json) != (
        admission.replacement_lock_envelope_sha256
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )

    try:
        retained_preflight = _manifest_object(admission.preflight_receipt_json)
        canonical_preflight = _canonical_json(retained_preflight)
    except SignedPhysicalModelLockReplacementAdmissionError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        ) from exc
    if (
        admission.preflight_receipt_json != canonical_preflight
        or _sha256(admission.preflight_receipt_json) != admission.preflight_receipt_sha256
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )
    expected_preflight = {
        "schema": SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA,
        "replacement_lock_admission_id": admission.replacement_lock_admission_id,
        "project_id": admission.project_id,
        "estimate_id": admission.estimate_id,
        "amendment_outcome_id": admission.amendment_outcome_id,
        "superseded_lock_id": admission.superseded_lock_id,
        "replacement_lock_content_hash": admission.replacement_lock_content_hash,
        "signed_manifest_sha256": admission.replacement_lock_envelope_sha256,
        "opening_count": preflight.opening_count,
        "service_count": preflight.service_count,
        "service_opening_link_count": preflight.service_opening_link_count,
        "physical_model_lock_created": False,
        "downstream_authority_granted": False,
    }
    if set(retained_preflight) != set(preflight.as_dict()) or any(
        retained_preflight.get(field) != value for field, value in expected_preflight.items()
    ):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )
    try:
        retained_preflighted_at = _timestamp(retained_preflight["preflighted_at"])
    except (KeyError, SignedPhysicalModelLockReplacementAdmissionError) as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        ) from exc
    issued_at = admission.issued_at
    expires_at = admission.expires_at
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        issued_at = issued_at.replace(tzinfo=retained_preflighted_at.tzinfo)
    if expires_at.tzinfo is None or expires_at.utcoffset() is None:
        expires_at = expires_at.replace(tzinfo=retained_preflighted_at.tzinfo)
    if not (issued_at <= retained_preflighted_at < expires_at):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_ADMISSION_CORRUPT"
        )


def _same_timestamp(left: datetime, right: datetime) -> bool:
    if left.tzinfo is None or left.utcoffset() is None:
        left = left.replace(tzinfo=right.tzinfo)
    return left == right


def _operator_reference(value: object) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_OPERATOR_INVALID"
        )
    return value.strip()


def _canonical_manifest_text(value: Mapping[str, Any] | bytes | str) -> str:
    if isinstance(value, bytes):
        try:
            raw = value.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SignedPhysicalModelLockReplacementAdmissionError(
                "REPLACEMENT_LOCK_MANIFEST_INVALID"
            ) from exc
    elif isinstance(value, str):
        raw = value
    elif isinstance(value, Mapping):
        raw = None
        parsed: object = dict(value)
    else:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        )
    if raw is not None:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SignedPhysicalModelLockReplacementAdmissionError(
                "REPLACEMENT_LOCK_MANIFEST_INVALID"
            ) from exc
    if not isinstance(parsed, dict):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        )
    return _canonical_json(parsed)


def _manifest_object(manifest_json: str) -> dict[str, Any]:
    try:
        value = json.loads(manifest_json)
    except json.JSONDecodeError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        ) from exc
    if not isinstance(value, dict):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        )
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
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        ) from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SignedPhysicalModelLockReplacementAdmissionError(
            "REPLACEMENT_LOCK_MANIFEST_INVALID"
        )
    return parsed


__all__ = [
    "PreflightedRegisteredSignedPhysicalModelLockReplacement",
    "SignedPhysicalModelLockReplacementAdmissionError",
    "preflight_registered_signed_physical_model_lock_replacement",
    "register_signed_physical_model_lock_replacement_admission",
]
