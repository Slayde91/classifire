"""Persist one verified admission without creating a model or a lock."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..models import Estimate
from ..physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from ..physical_models import PhysicalModelAdmission, PhysicalModelLock
from .adjudicated_admission import (
    ADMISSION_PURPOSE,
    ADMISSION_SIGNATURE_ALGORITHM,
    AdmissionVerificationError,
    VerifiedAdmission,
    verify_adjudicated_admission,
)
from .adjudicated_preflight import (
    AdjudicatedPreflightError,
    parse_adjudicated_preflight,
)
from .canonical_submission_state import (
    CanonicalSubmissionStateError,
    require_initial_submission_state,
)
from .deployment_lineage import assess_deployment_lineage


class AdmissionRegistrationError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Admission registration failed: {code}.")


def register_verified_admission_from_preflight(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
    preflight_receipt: bytes,
    pinned_public_key: str,
    expected_issuer: str,
    expected_key_id: str,
    operator_reference: str,
    now: datetime | None = None,
) -> tuple[PhysicalModelAdmission, bool]:
    """Derive every signed fact from one canonical, current preflight receipt."""

    try:
        binding = parse_adjudicated_preflight(preflight_receipt, now=now)
    except AdjudicatedPreflightError as exc:
        raise AdmissionRegistrationError(exc.code) from exc
    lineage = assess_deployment_lineage(db)
    if lineage.status != "READY":
        raise AdmissionRegistrationError(lineage.code)
    try:
        require_initial_submission_state(
            db,
            estimate_id=binding.estimate_id,
            expected_fingerprint=binding.protected_state_fingerprint,
        )
    except CanonicalSubmissionStateError as exc:
        raise AdmissionRegistrationError(exc.code) from exc
    return register_verified_admission(
        db,
        manifest=manifest,
        pinned_public_key=pinned_public_key,
        expected_project_id=binding.project_id,
        expected_estimate_id=binding.estimate_id,
        expected_preflight_receipt_sha256=binding.receipt_sha256,
        submission_payload=binding.submission_payload,
        expected_protected_state_fingerprint=binding.protected_state_fingerprint,
        expected_protected_state_fingerprint_version=(
            binding.protected_state_fingerprint_version
        ),
        expected_artifact_digests=binding.artifact_digests,
        expected_policy_versions=binding.policy_versions,
        expected_issuer=expected_issuer,
        expected_key_id=expected_key_id,
        operator_reference=operator_reference,
        now=now,
    )


def register_verified_admission(
    db: Session,
    *,
    manifest: Mapping[str, Any] | bytes | str,
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
    operator_reference: str,
    now: datetime | None = None,
) -> tuple[PhysicalModelAdmission, bool]:
    """Verify then persist one admission; return ``(record, created)``.

    This boundary has no opening/service/link/lock creation code.  It also
    rejects any estimate that already has an active Physical Model Lock.
    """
    if not isinstance(operator_reference, str) or not operator_reference.strip():
        raise AdmissionRegistrationError("ADMISSION_OPERATOR_INVALID")
    try:
        payload_model = InitialCanonicalPhysicalSubmission.model_validate(submission_payload)
        canonical_payload = payload_model.model_dump(mode="json")
        verified = verify_adjudicated_admission(
            manifest,
            pinned_public_key=pinned_public_key,
            expected_project_id=expected_project_id,
            expected_estimate_id=expected_estimate_id,
            expected_preflight_receipt_sha256=expected_preflight_receipt_sha256,
            submission_payload=canonical_payload,
            expected_protected_state_fingerprint=expected_protected_state_fingerprint,
            expected_protected_state_fingerprint_version=expected_protected_state_fingerprint_version,
            expected_artifact_digests=expected_artifact_digests,
            expected_policy_versions=expected_policy_versions,
            expected_issuer=expected_issuer,
            expected_key_id=expected_key_id,
            now=now,
        )
    except ValidationError as exc:
        raise AdmissionRegistrationError("ADMISSION_PAYLOAD_INVALID") from exc
    except AdmissionVerificationError as exc:
        raise AdmissionRegistrationError(exc.code) from exc
    return _persist_verified_admission(
        db,
        verified=verified,
        manifest=manifest,
        canonical_payload=canonical_payload,
        operator_reference=operator_reference,
    )


def _persist_verified_admission(
    db: Session,
    *,
    verified: VerifiedAdmission,
    manifest: Mapping[str, Any] | bytes | str,
    canonical_payload: dict[str, Any],
    operator_reference: str,
) -> tuple[PhysicalModelAdmission, bool]:
    estimate = db.get(Estimate, verified.estimate_id)
    if estimate is None or estimate.project_id != verified.project_id:
        raise AdmissionRegistrationError("ADMISSION_ESTIMATE_BINDING_INVALID")
    if db.scalar(
        select(PhysicalModelLock.id).where(
            PhysicalModelLock.estimate_id == estimate.id,
            PhysicalModelLock.invalidated_at.is_(None),
        )
    ):
        raise AdmissionRegistrationError("ADMISSION_ACTIVE_PHYSICAL_LOCK_PRESENT")

    existing = db.scalar(
        select(PhysicalModelAdmission).where(
            PhysicalModelAdmission.admission_id == verified.admission_id
        )
    )
    if existing is not None:
        if existing.admission_envelope_sha256 != verified.canonical_manifest_sha256:
            raise AdmissionRegistrationError("ADMISSION_REPLAY_CONFLICT")
        return existing, False

    envelope = _canonical_manifest_text(manifest)
    admission = PhysicalModelAdmission(
        admission_id=verified.admission_id,
        project_id=verified.project_id,
        estimate_id=verified.estimate_id,
        purpose=ADMISSION_PURPOSE,
        preflight_receipt_sha256=verified.preflight_receipt_sha256,
        normalised_submission_payload_sha256=verified.normalised_submission_payload_sha256,
        normalised_submission_payload_json=json.dumps(
            canonical_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        protected_state_fingerprint=verified.protected_state_fingerprint,
        protected_state_fingerprint_version=verified.protected_state_fingerprint_version,
        source_run_id=verified.source_run_id,
        adjudicated_run_id=verified.adjudicated_run_id,
        artifact_digests=dict(verified.artifact_digests),
        policy_versions=dict(verified.policy_versions),
        admission_envelope_json=envelope,
        admission_envelope_sha256=verified.canonical_manifest_sha256,
        issuer_id=verified.issuer,
        signing_key_id=verified.key_id,
        signature_algorithm=ADMISSION_SIGNATURE_ALGORITHM,
        issued_at=verified.issued_at,
        expires_at=verified.expires_at,
        state="issued",
    )
    db.add(admission)
    try:
        db.flush()
    except IntegrityError as exc:
        raise AdmissionRegistrationError("ADMISSION_REPLAY_CONFLICT") from exc
    record_audit(
        db,
        actor=None,
        actor_type="human_governance",
        actor_name=operator_reference.strip(),
        action="register_adjudicated_physical_model_admission",
        entity_type="physical_model_admission",
        entity_id=admission.id,
        project_id=admission.project_id,
        new_value={
            "admission_id": admission.admission_id,
            "state": admission.state,
            "issuer": admission.issuer_id,
            "key_id": admission.signing_key_id,
            "admission_envelope_sha256": admission.admission_envelope_sha256,
            "canonical_write_performed": False,
            "physical_model_lock_created": False,
        },
        reason="Verified signed admission recorded without model submission or physical lock.",
    )
    return admission, True


def _canonical_manifest_text(manifest: Mapping[str, Any] | bytes | str) -> str:
    if isinstance(manifest, bytes):
        try:
            value = json.loads(manifest.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AdmissionRegistrationError("ADMISSION_MANIFEST_INVALID") from exc
    elif isinstance(manifest, str):
        try:
            value = json.loads(manifest)
        except json.JSONDecodeError as exc:
            raise AdmissionRegistrationError("ADMISSION_MANIFEST_INVALID") from exc
    elif isinstance(manifest, Mapping):
        value = dict(manifest)
    else:
        raise AdmissionRegistrationError("ADMISSION_MANIFEST_INVALID")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
