from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from physical_foundation_support import (
    add_estimate,
    add_evidence,
    add_opening,
    add_service,
    add_service_link,
    physical_session,
)
from sqlalchemy import func, select

from classifire.models import AuditEvent
from classifire.physical_model_submission_schema import InitialCanonicalPhysicalSubmission
from classifire.physical_models import PhysicalModelLock
from classifire.services.adjudicated_admission import normalised_submission_payload_sha256
from classifire.services.physical_model import (
    build_current_physical_model_lock_payload,
    create_physical_model_lock,
)
from classifire.services.signed_physical_model_lock_amendment import (
    SIGNED_LOCK_AMENDMENT_PURPOSE,
    SIGNED_LOCK_AMENDMENT_SCHEMA,
    SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM,
    SignedPhysicalModelLockAmendmentError,
    require_signed_physical_model_lock_amendment,
    signed_lock_amendment_signing_bytes,
    verify_signed_physical_model_lock_amendment,
)
from classifire.services.visual_validation_receipt import (
    VISUAL_VALIDATION_RECEIPT_APPROVED,
    VISUAL_VALIDATION_RECEIPT_SCHEMA,
    VISUAL_VALIDATION_RECEIPT_WITHHELD,
    register_visual_validation_receipt,
)

NOW = datetime(2026, 9, 4, 6, 0, tzinfo=UTC)
_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _signed_lock(db):  # type: ignore[no-untyped-def]
    estimate = add_estimate(db)
    opening = add_opening(db, estimate)
    service = add_service(db, opening)
    add_service_link(db, service, opening)
    add_evidence(db, estimate)
    lock, created = create_physical_model_lock(db, estimate)
    assert created
    lock.signature = "future-signed-lock-evidence"
    db.flush()
    return estimate, opening, lock


def _amendment_payload(opening):  # type: ignore[no-untyped-def]
    return InitialCanonicalPhysicalSubmission.model_validate(
        {
            "openings": [
                {
                    "opening_code": opening.opening_code,
                    "canonical_defect_id": opening.canonical_defect_id,
                    "opening_type": opening.opening_type,
                    "substrate_type": opening.substrate_type,
                    "substrate_plane": opening.substrate_plane,
                    "orientation": opening.orientation,
                    "frl": opening.frl,
                }
            ],
            "services": [
                {
                    "service_code": "SVC-001",
                    "service_type": "pipe",
                    "material": "PVC",
                    "nominal_size_mm": "100",
                    "quantity": "1",
                }
            ],
            "service_opening_links": [
                {
                    "service_code": "SVC-001",
                    "opening_code": opening.opening_code,
                    "evidence_status": "confirmed",
                    "relationship_status": "confirmed",
                }
            ],
        }
    ).model_dump(mode="json")


def _visual_receipt(estimate, payload, *, status: str = VISUAL_VALIDATION_RECEIPT_APPROVED):  # type: ignore[no-untyped-def]
    return {
        "schema": VISUAL_VALIDATION_RECEIPT_SCHEMA,
        "receipt_id": str(uuid4()),
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": "visual-run-amendment-001",
        "candidate_submission_payload_sha256": normalised_submission_payload_sha256(payload),
        "controller_receipt_sha256": "A" * 64,
        "evidence_manifest_sha256": "B" * 64,
        "evidence_family_inventory_sha256": "C" * 64,
        "evidence_family_review_sha256": "D" * 64,
        "human_review_request_sha256": "E" * 64,
        "human_review_response_sha256": "F" * 64,
        "approval_reference": "HUMAN-SIGNED-AMENDMENT-001",
        "reviewed_at": "2026-09-04T05:00:00Z",
        "status": status,
        "reviewed_defect_references": ["D-001"],
        "unresolved_items": [] if status == VISUAL_VALIDATION_RECEIPT_APPROVED else ["FRL"],
        "policy_versions": {
            "human_review": "CLASSIFIRE-PHASE8-HUMAN-REVIEW-v2",
            "visual_validation": "CLASSIFIRE-PHASE8-VISUAL-VALIDATION-POLICY-v1",
        },
        "implementation_revision": "a" * 40,
    }


def _manifest(db, estimate, lock, payload, visual_receipt_sha256):  # type: ignore[no-untyped-def]
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = _base64url(
        private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    current_hash = build_current_physical_model_lock_payload(db, estimate)["content_hash"]
    manifest: dict[str, object] = {
        "schema": SIGNED_LOCK_AMENDMENT_SCHEMA,
        "amendment_admission_id": str(uuid4()),
        "purpose": SIGNED_LOCK_AMENDMENT_PURPOSE,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "target_lock_id": lock.id,
        "target_lock_content_hash": lock.content_hash,
        "target_lock_signature_sha256": hashlib.sha256(
            lock.signature.encode("utf-8")
        ).hexdigest().upper(),
        "current_physical_model_content_hash": current_hash,
        "amendment_submission_payload_sha256": normalised_submission_payload_sha256(payload),
        "visual_validation_receipt_sha256": visual_receipt_sha256,
        "controller_receipt_sha256": "A" * 64,
        "evidence_manifest_sha256": "B" * 64,
        "evidence_family_inventory_sha256": "C" * 64,
        "evidence_family_review_sha256": "D" * 64,
        "human_review_request_sha256": "E" * 64,
        "human_review_response_sha256": "F" * 64,
        "amendment_reason": "A human-approved physical correction needs a new signed path.",
        "policy_versions": {
            "signed_lock_amendment": (
                f"{SIGNED_LOCK_AMENDMENT_SCHEMA}:{SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM}"
            ),
            "visual_validation_receipt": VISUAL_VALIDATION_RECEIPT_SCHEMA,
        },
        "issuer": "classifire-governance",
        "key_id": "amendment-p256-01",
        "issued_at": "2026-09-04T05:50:00Z",
        "expires_at": "2026-09-04T06:10:00Z",
        "signature_algorithm": SIGNED_LOCK_AMENDMENT_SIGNATURE_ALGORITHM,
        "signature": "AA",
    }
    signature = private_key.sign(
        signed_lock_amendment_signing_bytes(manifest),
        ec.ECDSA(hashes.SHA256()),
    )
    r, s = decode_dss_signature(signature)
    if s > _P256_ORDER // 2:
        signature = encode_dss_signature(r, _P256_ORDER - s)
    manifest["signature"] = _base64url(signature)
    return manifest, public_key


def _require(db, estimate, lock, payload, manifest, public_key):  # type: ignore[no-untyped-def]
    return require_signed_physical_model_lock_amendment(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="amendment-p256-01",
        amendment_submission_payload=payload,
        now=NOW,
    )


def test_signed_amendment_requires_exact_approved_visual_receipt_without_writing() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        payload = _amendment_payload(opening)
        stored_receipt, created = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, stored_receipt.receipt_sha256)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        verified = _require(db, estimate, lock, payload, manifest, public_key)

        assert created is True
        assert verified.target_lock_id == lock.id
        assert verified.visual_validation_receipt_sha256 == stored_receipt.receipt_sha256
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 1
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_rejects_unsigned_or_stale_current_lock_without_writing() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        payload = _amendment_payload(opening)
        stored_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, stored_receipt.receipt_sha256)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        lock.signature = None
        with pytest.raises(SignedPhysicalModelLockAmendmentError) as unsigned:
            _require(db, estimate, lock, payload, manifest, public_key)
        assert unsigned.value.code == "AMENDMENT_TARGET_LOCK_NOT_SIGNED"
        assert lock.invalidated_at is None

        lock.signature = "future-signed-lock-evidence"
        opening.notes = "A direct drift simulation must fail closed."
        db.flush()
        with pytest.raises(SignedPhysicalModelLockAmendmentError) as stale:
            _require(db, estimate, lock, payload, manifest, public_key)
        assert stale.value.code == "AMENDMENT_CURRENT_PHYSICAL_MODEL_MISMATCH"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_rejects_withheld_or_mismatched_visual_evidence() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        payload = _amendment_payload(opening)
        stored_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload, status=VISUAL_VALIDATION_RECEIPT_WITHHELD),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, stored_receipt.receipt_sha256)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockAmendmentError) as withheld:
            _require(db, estimate, lock, payload, manifest, public_key)

        assert withheld.value.code == "AMENDMENT_VISUAL_RECEIPT_INELIGIBLE"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_manifest_rejects_changed_binding_or_signature() -> None:
    with physical_session() as db:
        estimate, opening, lock = _signed_lock(db)
        payload = _amendment_payload(opening)
        stored_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, stored_receipt.receipt_sha256)

        changed_hash = dict(manifest)
        changed_hash["target_lock_content_hash"] = "0" * 64
        with pytest.raises(SignedPhysicalModelLockAmendmentError) as mismatched:
            _require(db, estimate, lock, payload, changed_hash, public_key)
        assert mismatched.value.code == "AMENDMENT_BINDING_MISMATCH"

        changed_signature = dict(manifest)
        changed_signature["amendment_reason"] = "Changed after the external signer approved it."
        with pytest.raises(SignedPhysicalModelLockAmendmentError) as tampered:
            verify_signed_physical_model_lock_amendment(
                changed_signature,
                pinned_public_key=public_key,
                expected_project_id=estimate.project_id,
                expected_estimate_id=estimate.id,
                expected_target_lock_id=lock.id,
                expected_target_lock_content_hash=lock.content_hash,
                expected_target_lock_signature_sha256=hashlib.sha256(
                    lock.signature.encode("utf-8")
                ).hexdigest().upper(),
                expected_current_physical_model_content_hash=lock.content_hash,
                amendment_submission_payload=payload,
                expected_issuer="classifire-governance",
                expected_key_id="amendment-p256-01",
                now=NOW,
            )
        assert tampered.value.code == "AMENDMENT_SIGNATURE_INVALID"
