from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from physical_foundation_support import add_estimate, physical_session
from sqlalchemy import func, select

from classifire.physical_models import (
    PhysicalModelAdmission,
    PhysicalModelLock,
    PhysicalModelSubmissionReceipt,
    VisualValidationReceipt,
)
from classifire.services.visual_validation_receipt import (
    VISUAL_VALIDATION_RECEIPT_APPROVED,
    VISUAL_VALIDATION_RECEIPT_SCHEMA,
    VISUAL_VALIDATION_RECEIPT_WITHHELD,
    VisualValidationReceiptError,
    register_visual_validation_receipt,
    require_semantically_approved_visual_validation_receipt,
    verify_visual_validation_receipt,
)


def _receipt(estimate, *, status: str = VISUAL_VALIDATION_RECEIPT_APPROVED) -> dict:  # type: ignore[no-untyped-def]
    unresolved_items: list[str] = []
    if status == VISUAL_VALIDATION_RECEIPT_WITHHELD:
        unresolved_items = ["OPPOSITE_FACE_CONTINUITY"]
    return {
        "schema": VISUAL_VALIDATION_RECEIPT_SCHEMA,
        "receipt_id": str(uuid4()),
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": "visual-run-001",
        "candidate_submission_payload_sha256": "A" * 64,
        "controller_receipt_sha256": "B" * 64,
        "evidence_manifest_sha256": "C" * 64,
        "evidence_family_inventory_sha256": "D" * 64,
        "evidence_family_review_sha256": "0" * 64,
        "human_review_request_sha256": "E" * 64,
        "human_review_response_sha256": "F" * 64,
        "approval_reference": "HUMAN-SEMANTIC-001",
        "reviewed_at": "2026-08-24T12:00:00Z",
        "status": status,
        "reviewed_defect_references": ["D-001"],
        "unresolved_items": unresolved_items,
        "policy_versions": {
            "human_review": "CLASSIFIRE-PHASE8-HUMAN-REVIEW-v2",
            "visual_validation": "CLASSIFIRE-PHASE8-VISUAL-VALIDATION-POLICY-v1",
        },
        "implementation_revision": "a" * 40,
    }


def _eligibility_kwargs(estimate, receipt_sha256: str) -> dict:  # type: ignore[no-untyped-def]
    return {
        "receipt_sha256": receipt_sha256,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "candidate_submission_payload_sha256": "A" * 64,
        "controller_receipt_sha256": "B" * 64,
        "evidence_manifest_sha256": "C" * 64,
        "evidence_family_inventory_sha256": "D" * 64,
        "evidence_family_review_sha256": "0" * 64,
        "human_review_request_sha256": "E" * 64,
        "human_review_response_sha256": "F" * 64,
    }


def test_valid_receipt_is_canonical_and_hash_bound() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)

        verified = verify_visual_validation_receipt(json.dumps(receipt, indent=2))

    assert verified.receipt == receipt
    assert json.loads(verified.receipt_json) == receipt
    assert len(verified.receipt_sha256) == 64
    assert verified.receipt_sha256 == verified.receipt_sha256.upper()


def test_receipt_requires_reviewed_evidence_family_binding() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)
        del receipt["evidence_family_review_sha256"]

        with pytest.raises(VisualValidationReceiptError) as rejected:
            verify_visual_validation_receipt(receipt)

    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_INVALID"


def test_registration_is_idempotent_and_creates_no_model_or_lock() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)

        first, created = register_visual_validation_receipt(
            db,
            receipt=receipt,
            operator_reference="Synthetic governance reviewer",
        )
        second, created_again = register_visual_validation_receipt(
            db,
            receipt=json.dumps(receipt),
            operator_reference="Synthetic governance reviewer",
        )

        assert created is True
        assert created_again is False
        assert second.id == first.id
        assert db.scalar(select(func.count(VisualValidationReceipt.id))) == 1
        assert db.scalar(select(func.count(PhysicalModelAdmission.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelSubmissionReceipt.id))) == 0
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == 0


def test_registration_rejects_wrong_estimate_project_without_writing() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)
        receipt["project_id"] = str(uuid4())

        with pytest.raises(VisualValidationReceiptError) as rejected:
            register_visual_validation_receipt(
                db,
                receipt=receipt,
                operator_reference="Synthetic governance reviewer",
            )

        assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_ESTIMATE_BINDING_INVALID"
        assert db.scalar(select(func.count(VisualValidationReceipt.id))) == 0


def test_approved_receipt_rejects_unresolved_items() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)
        receipt["unresolved_items"] = ["SUBSTRATE_TYPE"]

        with pytest.raises(VisualValidationReceiptError) as rejected:
            verify_visual_validation_receipt(receipt)

    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_UNRESOLVED"


def test_withheld_receipt_is_durable_but_never_lock_eligible() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate, status=VISUAL_VALIDATION_RECEIPT_WITHHELD)
        stored, created = register_visual_validation_receipt(
            db,
            receipt=receipt,
            operator_reference="Synthetic governance reviewer",
        )

        with pytest.raises(VisualValidationReceiptError) as rejected:
            require_semantically_approved_visual_validation_receipt(
                db,
                **_eligibility_kwargs(estimate, stored.receipt_sha256),
            )

    assert created is True
    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_NOT_APPROVED"


def test_eligibility_requires_exact_stored_bindings() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        stored, _ = register_visual_validation_receipt(
            db,
            receipt=_receipt(estimate),
            operator_reference="Synthetic governance reviewer",
        )

        eligible = require_semantically_approved_visual_validation_receipt(
            db,
            **_eligibility_kwargs(estimate, stored.receipt_sha256),
        )
        for field_name in (
            "evidence_family_inventory_sha256",
            "evidence_family_review_sha256",
            "human_review_request_sha256",
        ):
            mismatch = _eligibility_kwargs(estimate, stored.receipt_sha256)
            mismatch[field_name] = "9" * 64
            with pytest.raises(VisualValidationReceiptError) as rejected:
                require_semantically_approved_visual_validation_receipt(db, **mismatch)
        missing = _eligibility_kwargs(estimate, "0" * 64)
        with pytest.raises(VisualValidationReceiptError) as missing_rejected:
            require_semantically_approved_visual_validation_receipt(db, **missing)

    assert eligible.id == stored.id
    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_BINDING_MISMATCH"
    assert missing_rejected.value.code == "VISUAL_VALIDATION_RECEIPT_REQUIRED"


def test_eligibility_detects_tampered_stored_receipt() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        stored, _ = register_visual_validation_receipt(
            db,
            receipt=_receipt(estimate),
            operator_reference="Synthetic governance reviewer",
        )
        stored.receipt_json = json.dumps({"tampered": True})
        db.flush()

        with pytest.raises(VisualValidationReceiptError) as rejected:
            require_semantically_approved_visual_validation_receipt(
                db,
                **_eligibility_kwargs(estimate, stored.receipt_sha256),
            )

    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_CORRUPT"


def test_receipt_id_cannot_be_reused_for_different_content() -> None:
    with physical_session() as db:
        estimate = add_estimate(db)
        receipt = _receipt(estimate)
        register_visual_validation_receipt(
            db,
            receipt=receipt,
            operator_reference="Synthetic governance reviewer",
        )
        changed = deepcopy(receipt)
        changed["approval_reference"] = "HUMAN-SEMANTIC-002"

        with pytest.raises(VisualValidationReceiptError) as rejected:
            register_visual_validation_receipt(
                db,
                receipt=changed,
                operator_reference="Synthetic governance reviewer",
            )

    assert rejected.value.code == "VISUAL_VALIDATION_RECEIPT_REPLAY_CONFLICT"
