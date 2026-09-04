"""Atomically create one exact signed replacement Physical Model Lock.

The caller owns the transaction. The writer consumes only a freshly rechecked
registered admission, creates one lock over the unchanged approved physical
snapshot, and retains an immutable outcome plus audit event. It performs no
technical selection, pricing, deployment, or release.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate, User
from ..physical_models import (
    PhysicalModelLock,
    PhysicalModelLockReplacementAdmission,
    PhysicalModelLockReplacementOutcome,
)
from ..security import has_permission
from .physical_model import (
    build_current_physical_model_lock_payload,
    build_current_physical_model_lock_snapshot,
)
from .signed_physical_model_lock_replacement_admission import (
    SignedPhysicalModelLockReplacementAdmissionError,
    preflight_registered_signed_physical_model_lock_replacement,
)

REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA = (
    "CLASSIFIRE-SIGNED-PHYSICAL-MODEL-REPLACEMENT-LOCK-EXECUTION-v1"
)


class SignedPhysicalModelLockReplacementExecutionError(RuntimeError):
    """Safe-code failure while executing one replacement-lock admission."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Signed replacement-lock execution failed: {code}.")


def execute_registered_signed_physical_model_lock_replacement(
    db: Session,
    *,
    replacement_lock_admission_id: str,
    expected_replacement_lock_envelope_sha256: str,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    actor: User | None,
    now: datetime | None = None,
    source_ip: str | None = None,
) -> tuple[PhysicalModelLockReplacementOutcome, bool]:
    """Create one exact replacement lock inside the caller-owned transaction."""

    current_time = _normalise_now(now)
    authorised_actor = _authorised_actor(db, actor)
    existing = db.scalar(
        select(PhysicalModelLockReplacementOutcome)
        .where(
            PhysicalModelLockReplacementOutcome.replacement_lock_admission_id
            == replacement_lock_admission_id
        )
        .with_for_update()
    )
    if existing is not None:
        _require_intact_outcome(
            db,
            existing,
            expected_replacement_lock_envelope_sha256=(expected_replacement_lock_envelope_sha256),
        )
        return existing, False

    try:
        registered = preflight_registered_signed_physical_model_lock_replacement(
            db,
            replacement_lock_admission_id=replacement_lock_admission_id,
            expected_replacement_lock_envelope_sha256=(expected_replacement_lock_envelope_sha256),
            pinned_public_key=pinned_public_key,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            now=current_time,
        )
    except SignedPhysicalModelLockReplacementAdmissionError as exc:
        # A concurrent exact execution can commit while this transaction waits
        # for the admission row. Return only its intact immutable outcome.
        replay = db.scalar(
            select(PhysicalModelLockReplacementOutcome)
            .where(
                PhysicalModelLockReplacementOutcome.replacement_lock_admission_id
                == replacement_lock_admission_id
            )
            .with_for_update()
        )
        if replay is not None:
            _require_intact_outcome(
                db,
                replay,
                expected_replacement_lock_envelope_sha256=(
                    expected_replacement_lock_envelope_sha256
                ),
            )
            return replay, False
        raise SignedPhysicalModelLockReplacementExecutionError(exc.code) from exc

    admission = db.get(PhysicalModelLockReplacementAdmission, registered.admission_record_id)
    if admission is None:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_ADMISSION_NOT_FOUND"
        )
    estimate = db.scalar(
        select(Estimate).where(Estimate.id == admission.estimate_id).with_for_update()
    )
    superseded_lock = db.scalar(
        select(PhysicalModelLock)
        .where(PhysicalModelLock.id == admission.superseded_lock_id)
        .with_for_update()
    )
    if estimate is None or superseded_lock is None:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_BINDING_INVALID"
        )

    snapshot = build_current_physical_model_lock_snapshot(db, estimate)
    payload = build_current_physical_model_lock_payload(db, estimate)
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
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_ACTIVE_LOCK_PRESENT"
        )
    if not (
        admission.project_id == estimate.project_id
        and admission.estimate_id == estimate.id
        and admission.replacement_lock_content_hash == snapshot.content_hash
        and admission.replacement_lock_content_hash
        == registered.preflight_receipt.replacement_lock_content_hash
        and admission.replacement_lock_envelope_sha256 == expected_replacement_lock_envelope_sha256
        and superseded_lock.id == registered.preflight_receipt.superseded_lock_id
        and superseded_lock.invalidated_at is not None
        and payload["content_hash"] == snapshot.content_hash
        and payload["validator_result"] == "PASS"
        and not payload["critical_unknowns"]
    ):
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_BINDING_INVALID"
        )

    try:
        with db.begin_nested():
            lock_payload = dict(payload)
            # Preserve the complete canonical signed envelope, not only its
            # detached signature, so future amendment binding covers context.
            lock_payload["signature"] = admission.replacement_lock_envelope_json
            replacement_lock = PhysicalModelLock(**lock_payload)
            db.add(replacement_lock)
            db.flush()

            outcome_id = str(uuid.uuid4())
            receipt = {
                "schema": REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA,
                "outcome_id": outcome_id,
                "replacement_lock_admission_id": admission.replacement_lock_admission_id,
                "admission_record_id": admission.id,
                "project_id": admission.project_id,
                "estimate_id": admission.estimate_id,
                "amendment_outcome_id": admission.amendment_outcome_id,
                "superseded_lock_id": admission.superseded_lock_id,
                "replacement_lock_id": replacement_lock.id,
                "replacement_lock_content_hash": replacement_lock.content_hash,
                "replacement_lock_envelope_sha256": (admission.replacement_lock_envelope_sha256),
                "preflight_receipt_sha256": admission.preflight_receipt_sha256,
                "opening_count": len(payload["opening_ids"]),
                "service_count": len(payload["service_ids"]),
                "service_opening_link_count": (
                    registered.preflight_receipt.service_opening_link_count
                ),
                "created_by_user_id": authorised_actor.id,
                "locked_at": _timestamp_text(current_time),
                "physical_model_lock_created": True,
                "downstream_authority_granted": False,
                "technical_selection_performed": False,
                "pricing_performed": False,
                "deployment_performed": False,
                "release_performed": False,
            }
            receipt_json = _canonical_json(receipt)
            outcome = PhysicalModelLockReplacementOutcome(
                id=outcome_id,
                admission_record_id=admission.id,
                replacement_lock_admission_id=admission.replacement_lock_admission_id,
                project_id=admission.project_id,
                estimate_id=admission.estimate_id,
                amendment_outcome_id=admission.amendment_outcome_id,
                superseded_lock_id=admission.superseded_lock_id,
                replacement_lock_id=replacement_lock.id,
                replacement_lock_content_hash=replacement_lock.content_hash,
                replacement_lock_envelope_sha256=(admission.replacement_lock_envelope_sha256),
                preflight_receipt_sha256=admission.preflight_receipt_sha256,
                created_by_user_id=authorised_actor.id,
                locked_at=current_time,
                physical_model_lock_created=True,
                downstream_authority_granted=False,
                execution_receipt_json=receipt_json,
                execution_receipt_sha256=_sha256(receipt_json),
            )
            db.add(outcome)
            record_audit(
                db,
                actor=authorised_actor,
                action="execute_signed_physical_model_lock_replacement",
                entity_type="physical_model_lock_replacement_outcome",
                entity_id=outcome.id,
                project_id=outcome.project_id,
                source_ip=source_ip,
                correlation_id=outcome.replacement_lock_admission_id,
                previous_value={
                    "superseded_lock_id": admission.superseded_lock_id,
                    "active_physical_model_lock_id": None,
                },
                new_value={
                    "replacement_lock_id": replacement_lock.id,
                    "replacement_lock_content_hash": replacement_lock.content_hash,
                    "replacement_lock_envelope_sha256": (
                        admission.replacement_lock_envelope_sha256
                    ),
                    "physical_model_lock_created": True,
                    "downstream_authority_granted": False,
                    "technical_selection_performed": False,
                    "pricing_performed": False,
                    "deployment_performed": False,
                    "release_performed": False,
                },
                reason=admission.replacement_lock_reason,
            )
            db.flush()
    except SignedPhysicalModelLockReplacementExecutionError:
        raise
    except SQLAlchemyError as exc:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_WRITE_FAILED"
        ) from exc
    return outcome, True


def _authorised_actor(db: Session, actor: User | None) -> User:
    if actor is None or not actor.id:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_PERMISSION_DENIED"
        )
    retained = db.scalar(select(User).where(User.id == actor.id).with_for_update())
    if retained is None or not retained.is_active or not has_permission(retained, "estimate:write"):
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_PERMISSION_DENIED"
        )
    return retained


def _require_intact_outcome(
    db: Session,
    outcome: PhysicalModelLockReplacementOutcome,
    *,
    expected_replacement_lock_envelope_sha256: str,
) -> None:
    if outcome.replacement_lock_envelope_sha256 != (expected_replacement_lock_envelope_sha256):
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_BINDING_INVALID"
        )
    admission = db.get(PhysicalModelLockReplacementAdmission, outcome.admission_record_id)
    replacement_lock = db.get(PhysicalModelLock, outcome.replacement_lock_id)
    superseded_lock = db.get(PhysicalModelLock, outcome.superseded_lock_id)
    estimate = db.get(Estimate, outcome.estimate_id)
    if admission is None or replacement_lock is None or superseded_lock is None or estimate is None:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_OUTCOME_CORRUPT"
        )
    expected_bindings = {
        "replacement_lock_admission_id": admission.replacement_lock_admission_id,
        "project_id": admission.project_id,
        "estimate_id": admission.estimate_id,
        "amendment_outcome_id": admission.amendment_outcome_id,
        "superseded_lock_id": admission.superseded_lock_id,
        "replacement_lock_content_hash": admission.replacement_lock_content_hash,
        "replacement_lock_envelope_sha256": (admission.replacement_lock_envelope_sha256),
        "preflight_receipt_sha256": admission.preflight_receipt_sha256,
    }
    if any(getattr(outcome, key) != value for key, value in expected_bindings.items()):
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_OUTCOME_CORRUPT"
        )

    try:
        receipt = _canonical_object(outcome.execution_receipt_json)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_OUTCOME_CORRUPT"
        ) from exc
    current_snapshot = build_current_physical_model_lock_snapshot(db, estimate)
    current_payload = build_current_physical_model_lock_payload(db, estimate)
    expected_lock_values = dict(current_payload)
    expected_lock_values["signature"] = admission.replacement_lock_envelope_json
    expected_receipt = {
        "schema": REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA,
        "outcome_id": outcome.id,
        "replacement_lock_admission_id": outcome.replacement_lock_admission_id,
        "admission_record_id": outcome.admission_record_id,
        "project_id": outcome.project_id,
        "estimate_id": outcome.estimate_id,
        "amendment_outcome_id": outcome.amendment_outcome_id,
        "superseded_lock_id": outcome.superseded_lock_id,
        "replacement_lock_id": outcome.replacement_lock_id,
        "replacement_lock_content_hash": outcome.replacement_lock_content_hash,
        "replacement_lock_envelope_sha256": (outcome.replacement_lock_envelope_sha256),
        "preflight_receipt_sha256": outcome.preflight_receipt_sha256,
        "opening_count": len(current_payload["opening_ids"]),
        "service_count": len(current_payload["service_ids"]),
        "service_opening_link_count": len(current_snapshot.as_dict()["service_opening_links"]),
        "created_by_user_id": outcome.created_by_user_id,
        "locked_at": _timestamp_text(_aware_utc(outcome.locked_at)),
        "physical_model_lock_created": True,
        "downstream_authority_granted": False,
        "technical_selection_performed": False,
        "pricing_performed": False,
        "deployment_performed": False,
        "release_performed": False,
    }
    if not (
        _sha256(admission.replacement_lock_envelope_json)
        == admission.replacement_lock_envelope_sha256
        and _sha256(admission.preflight_receipt_json) == admission.preflight_receipt_sha256
        and replacement_lock.invalidated_at is None
        and superseded_lock.invalidated_at is not None
        and replacement_lock.content_hash == current_snapshot.content_hash
        and all(
            getattr(replacement_lock, field) == value
            for field, value in expected_lock_values.items()
        )
        and _sha256(outcome.execution_receipt_json) == outcome.execution_receipt_sha256
        and receipt == expected_receipt
        and outcome.physical_model_lock_created is True
        and outcome.downstream_authority_granted is False
    ):
        raise SignedPhysicalModelLockReplacementExecutionError(
            "REPLACEMENT_LOCK_EXECUTION_OUTCOME_CORRUPT"
        )


def require_intact_signed_physical_model_lock_replacement_outcome(
    db: Session,
    outcome: PhysicalModelLockReplacementOutcome,
    *,
    expected_replacement_lock_envelope_sha256: str,
) -> None:
    """Recheck immutable replacement-lock evidence for a downstream gate."""

    _require_intact_outcome(
        db,
        outcome,
        expected_replacement_lock_envelope_sha256=(expected_replacement_lock_envelope_sha256),
    )


def _canonical_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value)
    if not isinstance(parsed, dict) or _canonical_json(parsed) != value:
        raise ValueError("not a canonical JSON object")
    return parsed


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().upper()


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _timestamp_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _normalise_now(now: datetime | None) -> datetime:
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise SignedPhysicalModelLockReplacementExecutionError("REPLACEMENT_LOCK_TIME_INVALID")
    return current.astimezone(UTC)


__all__ = [
    "REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA",
    "SignedPhysicalModelLockReplacementExecutionError",
    "execute_registered_signed_physical_model_lock_replacement",
    "require_intact_signed_physical_model_lock_replacement_outcome",
]
