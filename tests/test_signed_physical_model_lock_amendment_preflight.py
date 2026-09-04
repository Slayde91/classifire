from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from test_signed_physical_model_lock_amendment import (
    NOW,
    _amendment_payload,
    _manifest,
    _signed_lock,
    _visual_receipt,
)

from classifire.models import AuditEvent, EstimateLine, RuleEvaluation
from classifire.physical_models import PhysicalModelLock
from classifire.services.signed_physical_model_lock_amendment_preflight import (
    SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA,
    SignedPhysicalModelLockAmendmentPreflightError,
    preflight_signed_physical_model_lock_amendment,
)
from classifire.services.visual_validation_receipt import register_visual_validation_receipt


def _preflight(db, payload, manifest, public_key):  # type: ignore[no-untyped-def]
    return preflight_signed_physical_model_lock_amendment(
        db,
        manifest=manifest,
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="amendment-p256-01",
        amendment_submission_payload=payload,
        now=NOW,
    )


def _prepared_preflight(db):  # type: ignore[no-untyped-def]
    estimate, opening, lock = _signed_lock(db)
    payload = _amendment_payload(opening)
    visual_receipt, _ = register_visual_validation_receipt(
        db,
        receipt=_visual_receipt(estimate, payload),
        operator_reference="Synthetic human governance reviewer",
    )
    manifest, public_key = _manifest(db, estimate, lock, payload, visual_receipt.receipt_sha256)
    return estimate, opening, lock, payload, manifest, public_key


def test_signed_amendment_preflight_locks_and_rechecks_without_writing() -> None:
    with physical_session() as db:
        estimate, _opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        lock_count_before = db.scalar(select(func.count(PhysicalModelLock.id)))

        receipt = _preflight(db, payload, manifest, public_key)

        assert receipt.estimate_id == estimate.id
        assert receipt.target_lock_id == lock.id
        assert receipt.current_opening_count == 1
        assert receipt.proposed_opening_count == 1
        assert receipt.proposed_service_count == 1
        assert receipt.proposed_service_opening_link_count == 1
        assert receipt.preflighted_at == "2026-09-04T06:00:00Z"
        assert receipt.as_dict()["schema"] == SIGNED_LOCK_AMENDMENT_PREFLIGHT_SCHEMA
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_before
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


@pytest.mark.parametrize(
    ("prepare", "expected_code"),
    [
        (
            lambda db, estimate, opening: setattr(estimate, "status", "released"),
            "AMENDMENT_ESTIMATE_STATUS_INVALID",
        ),
        (
            lambda db, estimate, opening: setattr(
                opening, "selected_technical_variant_id", "technical-variant-id"
            ),
            "AMENDMENT_TECHNICAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                EstimateLine(
                    estimate_id=estimate.id,
                    line_number=1,
                    component_type="labour",
                    description="Downstream commercial record",
                )
            ),
            "AMENDMENT_COMMERCIAL_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: db.add(
                RuleEvaluation(
                    estimate_id=estimate.id,
                    rule_id="rule-id",
                    result="pass",
                    severity="info",
                    explanation="Downstream rule record",
                    inputs={},
                    output={},
                    rule_version=1,
                )
            ),
            "AMENDMENT_RULE_DEPENDENCY_PRESENT",
        ),
        (
            lambda db, estimate, opening: setattr(estimate, "snapshot_hash", "s" * 64),
            "AMENDMENT_SNAPSHOT_OR_RELEASE_PRESENT",
        ),
    ],
)
def test_signed_amendment_preflight_rejects_later_lifecycle_dependencies(
    prepare, expected_code
) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate, opening, lock, payload, manifest, public_key = _prepared_preflight(db)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))
        prepare(db, estimate, opening)
        db.flush()

        with pytest.raises(SignedPhysicalModelLockAmendmentPreflightError) as rejected:
            _preflight(db, payload, manifest, public_key)

        assert rejected.value.code == expected_code
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_preflight_rejects_prospective_foreign_defect_without_writing() -> None:
    with physical_session() as db:
        estimate, opening, lock, payload, _manifest_value, _public_key = _prepared_preflight(db)
        payload["openings"][0]["canonical_defect_id"] = str(uuid4())
        visual_receipt, _ = register_visual_validation_receipt(
            db,
            receipt=_visual_receipt(estimate, payload),
            operator_reference="Synthetic human governance reviewer",
        )
        manifest, public_key = _manifest(db, estimate, lock, payload, visual_receipt.receipt_sha256)
        audit_count_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockAmendmentPreflightError) as rejected:
            _preflight(db, payload, manifest, public_key)

        assert rejected.value.code == "AMENDMENT_PROSPECTIVE_DEFECT_BINDING_INVALID"
        assert lock.invalidated_at is None
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_count_before


def test_signed_amendment_preflight_requires_an_aware_timestamp() -> None:
    with physical_session() as db:
        _estimate, _opening, _lock, payload, manifest, public_key = _prepared_preflight(db)

        with pytest.raises(SignedPhysicalModelLockAmendmentPreflightError) as rejected:
            preflight_signed_physical_model_lock_amendment(
                db,
                manifest=manifest,
                pinned_public_key=public_key,
                expected_issuer="classifire-governance",
                expected_key_id="amendment-p256-01",
                amendment_submission_payload=payload,
                now=datetime(2026, 9, 4, 6, 0),
            )

        assert rejected.value.code == "AMENDMENT_TIME_INVALID"
