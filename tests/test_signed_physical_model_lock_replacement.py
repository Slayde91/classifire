from __future__ import annotations

import base64
from datetime import timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from test_signed_physical_model_lock_amendment import (
    NOW,
    _amendment_payload,
    _manifest,
    _signed_lock,
    _visual_receipt,
)
from test_signed_physical_model_lock_amendment_admission import _register
from test_signed_physical_model_lock_amendment_execution import _actor, _execute
from test_signed_physical_model_lock_amendment_preflight import _prepared_preflight

from classifire.models import AuditEvent, EstimateLine, Opening, RuleEvaluation
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockAmendmentOutcome,
    VisualValidationReceipt,
)
from classifire.services.physical_model import (
    build_current_physical_model_lock_snapshot,
    create_physical_model_lock,
)
from classifire.services.signed_physical_model_lock_amendment_execution import (
    EXECUTION_RECEIPT_SCHEMA,
)
from classifire.services.signed_physical_model_lock_replacement import (
    SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA,
    SIGNED_REPLACEMENT_LOCK_PURPOSE,
    SIGNED_REPLACEMENT_LOCK_SCHEMA,
    SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM,
    SignedPhysicalModelLockReplacementError,
    preflight_signed_replacement_physical_model_lock,
    signed_replacement_lock_signing_bytes,
)
from classifire.services.visual_validation_receipt import (
    VISUAL_VALIDATION_RECEIPT_SCHEMA,
    register_visual_validation_receipt,
)

_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _executed_amendment(db):  # type: ignore[no-untyped-def]
    estimate, opening, old_lock, payload, amendment_manifest, amendment_public_key = (
        _prepared_preflight(db)
    )
    admission, _ = _register(db, payload, amendment_manifest, amendment_public_key)
    outcome, _ = _execute(db, admission, amendment_public_key, _actor(db))
    return estimate, opening, old_lock, admission, outcome


def _replacement_manifest(
    db,
    estimate,
    old_lock,
    admission,
    outcome,
    *,
    replacement_lock_admission_id=None,
    replacement_lock_reason="Human approval for the exact amended physical model.",
):  # type: ignore[no-untyped-def]
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = _base64url(
        private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    current = build_current_physical_model_lock_snapshot(db, estimate)
    manifest: dict[str, object] = {
        "schema": SIGNED_REPLACEMENT_LOCK_SCHEMA,
        "replacement_lock_admission_id": replacement_lock_admission_id or str(uuid4()),
        "purpose": SIGNED_REPLACEMENT_LOCK_PURPOSE,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "amendment_outcome_id": outcome.id,
        "amendment_admission_id": outcome.amendment_admission_id,
        "amendment_envelope_sha256": outcome.amendment_envelope_sha256,
        "amendment_execution_receipt_sha256": outcome.execution_receipt_sha256,
        "visual_validation_receipt_sha256": admission.visual_validation_receipt_sha256,
        "superseded_lock_id": old_lock.id,
        "superseded_lock_content_hash": old_lock.content_hash,
        "replacement_lock_content_hash": current.content_hash,
        "replacement_lock_reason": replacement_lock_reason,
        "policy_versions": {
            "amendment_execution": EXECUTION_RECEIPT_SCHEMA,
            "replacement_lock": (
                f"{SIGNED_REPLACEMENT_LOCK_SCHEMA}:{SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM}"
            ),
            "visual_validation_receipt": VISUAL_VALIDATION_RECEIPT_SCHEMA,
        },
        "issuer": "classifire-governance",
        "key_id": "replacement-lock-p256-01",
        "issued_at": "2026-09-04T05:55:00Z",
        "expires_at": "2026-09-04T06:10:00Z",
        "signature_algorithm": SIGNED_REPLACEMENT_LOCK_SIGNATURE_ALGORITHM,
        "signature": "AA",
    }
    signature = private_key.sign(
        signed_replacement_lock_signing_bytes(manifest),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(signature)
    if s > _P256_ORDER // 2:
        signature = encode_dss_signature(r, _P256_ORDER - s)
    manifest["signature"] = _base64url(signature)
    return manifest, public_key


def _preflight(db, manifest, public_key, *, now=NOW):  # type: ignore[no-untyped-def]
    return preflight_signed_replacement_physical_model_lock(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="replacement-lock-p256-01",
        now=now,
    )


def test_replacement_lock_preflight_binds_exact_amended_state_without_writing() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        lock_count_before = db.scalar(select(func.count(PhysicalModelLock.id)))
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        outcome_count_before = db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id)))

        receipt = _preflight(db, manifest, public_key)

        assert receipt.as_dict()["schema"] == SIGNED_REPLACEMENT_LOCK_PREFLIGHT_SCHEMA
        assert receipt.replacement_lock_content_hash == outcome.post_physical_model_content_hash
        assert receipt.amendment_outcome_id == outcome.id
        assert receipt.superseded_lock_id == old_lock.id
        assert receipt.opening_count == 1
        assert receipt.service_count == 1
        assert receipt.service_opening_link_count == 1
        assert receipt.preflighted_at == "2026-09-04T06:00:00Z"
        assert receipt.as_dict()["physical_model_lock_created"] is False
        assert receipt.as_dict()["downstream_authority_granted"] is False
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_before == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before
        assert (
            db.scalar(select(func.count(PhysicalModelLockAmendmentOutcome.id)))
            == outcome_count_before
        )
        assert old_lock.invalidated_at == NOW
        assert not db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.invalidated_at.is_(None))
        ).all()


def test_replacement_lock_preflight_rejects_signature_tampering_without_writing() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        manifest["replacement_lock_reason"] = "Tampered after signing"
        lock_count_before = db.scalar(select(func.count(PhysicalModelLock.id)))

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_SIGNATURE_INVALID"
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_before


def test_replacement_lock_preflight_rejects_expired_signature() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key, now=NOW + timedelta(minutes=11))

        assert rejected.value.code == "REPLACEMENT_LOCK_EXPIRED"


def test_replacement_lock_preflight_rejects_changed_physical_state() -> None:
    with physical_session() as db:
        estimate, opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        retained_opening = db.get(Opening, opening.id)
        assert retained_opening is not None
        retained_opening.notes = "Changed after signed replacement-lock approval"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_CURRENT_STATE_MISMATCH"


def test_replacement_lock_preflight_rejects_corrupt_amendment_outcome() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        outcome.execution_receipt_json = "{}"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_AMENDMENT_OUTCOME_INVALID"


def test_replacement_lock_preflight_rejects_when_any_active_lock_exists() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        unexpected_lock, created = create_physical_model_lock(db, estimate)
        assert created is True

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_ACTIVE_LOCK_PRESENT"
        assert unexpected_lock.invalidated_at is None


def test_replacement_lock_preflight_rechecks_prior_lock_signature_binding() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        old_lock.signature = f"{old_lock.signature}-tampered"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_BINDING_INVALID"


def test_replacement_lock_preflight_rechecks_visual_receipt_integrity() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        visual_receipt = db.scalar(
            select(VisualValidationReceipt).where(
                VisualValidationReceipt.receipt_sha256 == admission.visual_validation_receipt_sha256
            )
        )
        assert visual_receipt is not None
        visual_receipt.receipt_json = "{}"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_VISUAL_RECEIPT_INVALID"


@pytest.mark.parametrize(
    ("prepare", "expected_code"),
    [
        (
            lambda db, estimate, opening: setattr(
                opening, "selected_technical_variant_id", "synthetic-variant-id"
            ),
            "REPLACEMENT_LOCK_TECHNICAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                EstimateLine(
                    estimate_id=estimate.id,
                    line_number=1,
                    component_type="labour",
                    description="Synthetic downstream commercial record",
                )
            ),
            "REPLACEMENT_LOCK_COMMERCIAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                RuleEvaluation(
                    estimate_id=estimate.id,
                    rule_id="synthetic-rule-id",
                    result="pass",
                    severity="info",
                    explanation="Synthetic downstream rule record",
                    inputs={},
                    output={},
                    rule_version=1,
                )
            ),
            "REPLACEMENT_LOCK_RULE_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: setattr(estimate, "snapshot_hash", "s" * 64),
            "REPLACEMENT_LOCK_SNAPSHOT_OR_RELEASE_PRESENT",
        ),
    ],
)
def test_replacement_lock_preflight_rejects_later_lifecycle_dependencies(
    prepare, expected_code
) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate, opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        prepare(db, estimate, opening)
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == expected_code


def test_replacement_lock_preflight_rejects_noneditable_estimate() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, admission, outcome = _executed_amendment(db)
        manifest, public_key = _replacement_manifest(db, estimate, old_lock, admission, outcome)
        estimate.status = "released"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, manifest, public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_ESTIMATE_STATUS_INVALID"


def test_replacement_lock_preflight_requires_scope_aware_physical_completeness() -> None:
    with physical_session() as db:
        estimate, opening, old_lock = _signed_lock(db)
        payload = _amendment_payload(opening)
        payload["openings"][0]["frl"] = None
        visual_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        amendment_manifest, amendment_public_key = _manifest(
            db, estimate, old_lock, payload, visual_receipt.receipt_sha256
        )
        admission, _ = _register(db, payload, amendment_manifest, amendment_public_key)
        outcome, _ = _execute(db, admission, amendment_public_key, _actor(db))
        replacement_manifest, replacement_public_key = _replacement_manifest(
            db, estimate, old_lock, admission, outcome
        )

        with pytest.raises(SignedPhysicalModelLockReplacementError) as rejected:
            _preflight(db, replacement_manifest, replacement_public_key)

        assert rejected.value.code == "REPLACEMENT_LOCK_INELIGIBLE"
        assert not db.scalars(
            select(PhysicalModelLock).where(PhysicalModelLock.invalidated_at.is_(None))
        ).all()
