from __future__ import annotations

import json
from datetime import timedelta

import pytest
from physical_foundation_support import physical_session
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from test_signed_physical_model_lock_amendment import NOW
from test_signed_physical_model_lock_replacement import (
    _executed_amendment,
    _replacement_manifest,
)
from test_signed_physical_model_lock_replacement_admission import _register

from classifire.models import AuditEvent, EstimateLine, RuleEvaluation, User
from classifire.physical_models import (
    PhysicalModelLock,
    PhysicalModelLockReplacementAdmission,
    PhysicalModelLockReplacementOutcome,
)
from classifire.services.signed_physical_model_lock_replacement_execution import (
    REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA,
    SignedPhysicalModelLockReplacementExecutionError,
    execute_registered_signed_physical_model_lock_replacement,
)
from classifire.services.workflow import WorkflowAction
from classifire.services.workflow_guard import check_estimate_action


def _replacement_actor(db, *, role: str = "estimator", active: bool = True):  # type: ignore[no-untyped-def]
    actor = User(
        email=f"replacement-{role}-{active}@example.test",
        full_name="Synthetic replacement-lock executor",
        password_hash="not-used",  # noqa: S106 - synthetic non-authenticating fixture
        role=role,
        is_active=active,
    )
    db.add(actor)
    db.flush()
    return actor


def _execute(db, admission, public_key, actor, *, now=NOW):  # type: ignore[no-untyped-def]
    return execute_registered_signed_physical_model_lock_replacement(
        db,
        replacement_lock_admission_id=admission.replacement_lock_admission_id,
        expected_replacement_lock_envelope_sha256=(admission.replacement_lock_envelope_sha256),
        pinned_public_key=public_key,
        expected_issuer="classifire-governance",
        expected_key_id="replacement-lock-p256-01",
        actor=actor,
        now=now,
        source_ip="127.0.0.1",
    )


def _registered_candidate(db):  # type: ignore[no-untyped-def]
    estimate, opening, old_lock, amendment_admission, amendment_outcome = _executed_amendment(db)
    manifest, public_key = _replacement_manifest(
        db, estimate, old_lock, amendment_admission, amendment_outcome
    )
    admission, created = _register(db, manifest, public_key)
    assert created is True
    return estimate, opening, old_lock, amendment_outcome, admission, public_key


def test_execution_atomically_creates_exact_signed_replacement_lock() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_outcome, admission, public_key = (
            _registered_candidate(db)
        )
        actor = _replacement_actor(db)
        audit_before = db.scalar(select(func.count(AuditEvent.id)))

        outcome, created = _execute(db, admission, public_key, actor)

        assert created is True
        assert outcome.admission_record_id == admission.id
        assert outcome.amendment_outcome_id == amendment_outcome.id
        assert outcome.superseded_lock_id == old_lock.id
        assert outcome.physical_model_lock_created is True
        assert outcome.downstream_authority_granted is False
        replacement_lock = db.get(PhysicalModelLock, outcome.replacement_lock_id)
        assert replacement_lock is not None
        assert replacement_lock.invalidated_at is None
        assert replacement_lock.content_hash == admission.replacement_lock_content_hash
        assert replacement_lock.signature == admission.replacement_lock_envelope_json
        assert old_lock.invalidated_at is not None
        assert (
            db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.estimate_id == estimate.id,
                    PhysicalModelLock.invalidated_at.is_(None),
                )
            )
            == 1
        )
        receipt = json.loads(outcome.execution_receipt_json)
        assert receipt["schema"] == REPLACEMENT_LOCK_EXECUTION_RECEIPT_SCHEMA
        assert receipt["replacement_lock_id"] == replacement_lock.id
        assert receipt["service_opening_link_count"] == 1
        assert receipt["physical_model_lock_created"] is True
        assert receipt["downstream_authority_granted"] is False
        assert receipt["technical_selection_performed"] is False
        assert receipt["pricing_performed"] is False
        assert receipt["deployment_performed"] is False
        assert receipt["release_performed"] is False
        assert db.scalar(select(func.count(EstimateLine.id))) == 0
        assert db.scalar(select(func.count(RuleEvaluation.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before + 1
        assert check_estimate_action(db, estimate, WorkflowAction.SEARCH_TECHNICAL).allowed is True


def test_completed_execution_replays_after_admission_expiry_without_second_write() -> None:
    with physical_session() as db:
        _estimate, _opening, _old_lock, _amendment, admission, public_key = _registered_candidate(
            db
        )
        actor = _replacement_actor(db)
        outcome, created = _execute(db, admission, public_key, actor)
        assert created is True
        audit_after_first = db.scalar(select(func.count(AuditEvent.id)))
        lock_count_after_first = db.scalar(select(func.count(PhysicalModelLock.id)))

        replay, replay_created = _execute(
            db, admission, public_key, actor, now=NOW + timedelta(days=1)
        )

        assert replay.id == outcome.id
        assert replay_created is False
        assert db.scalar(select(func.count(PhysicalModelLock.id))) == lock_count_after_first
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_after_first
        assert db.scalar(select(func.count(PhysicalModelLockReplacementOutcome.id))) == 1


@pytest.mark.parametrize("role,active", [("viewer", True), ("estimator", False)])
def test_execution_requires_active_estimate_writer(role: str, active: bool) -> None:
    with physical_session() as db:
        _estimate, _opening, _old_lock, _amendment, admission, public_key = _registered_candidate(
            db
        )
        actor = _replacement_actor(db, role=role, active=active)
        audit_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockReplacementExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "REPLACEMENT_LOCK_EXECUTION_PERMISSION_DENIED"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementOutcome.id))) == 0
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before


def test_execution_rechecks_state_drift_before_creating_lock() -> None:
    with physical_session() as db:
        _estimate, opening, _old_lock, _amendment, admission, public_key = _registered_candidate(db)
        actor = _replacement_actor(db)
        opening.notes = "Changed after the signed replacement approval."
        db.flush()
        audit_before = db.scalar(select(func.count(AuditEvent.id)))

        with pytest.raises(SignedPhysicalModelLockReplacementExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "REPLACEMENT_LOCK_CURRENT_STATE_MISMATCH"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementOutcome.id))) == 0
        assert (
            db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.invalidated_at.is_(None)
                )
            )
            == 0
        )
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before


def test_execution_replay_rejects_corrupt_immutable_outcome() -> None:
    with physical_session() as db:
        _estimate, _opening, _old_lock, _amendment, admission, public_key = _registered_candidate(
            db
        )
        actor = _replacement_actor(db)
        outcome, created = _execute(db, admission, public_key, actor)
        assert created is True
        outcome.execution_receipt_json = "{}"
        db.flush()

        with pytest.raises(SignedPhysicalModelLockReplacementExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "REPLACEMENT_LOCK_EXECUTION_OUTCOME_CORRUPT"


def test_execution_rolls_back_lock_outcome_and_audit_together(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        _estimate, _opening, _old_lock, _amendment, admission, public_key = _registered_candidate(
            db
        )
        actor = _replacement_actor(db)
        audit_before = db.scalar(select(func.count(AuditEvent.id)))

        def fail_audit(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise SQLAlchemyError("synthetic audit write failure")

        monkeypatch.setattr(
            "classifire.services.signed_physical_model_lock_replacement_execution.record_audit",
            fail_audit,
        )

        with pytest.raises(SignedPhysicalModelLockReplacementExecutionError) as rejected:
            _execute(db, admission, public_key, actor)

        assert rejected.value.code == "REPLACEMENT_LOCK_EXECUTION_WRITE_FAILED"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementOutcome.id))) == 0
        assert (
            db.scalar(
                select(func.count(PhysicalModelLock.id)).where(
                    PhysicalModelLock.invalidated_at.is_(None)
                )
            )
            == 0
        )
        assert db.scalar(select(func.count(AuditEvent.id))) == audit_before


def test_only_one_fresh_admission_can_create_the_replacement_lock() -> None:
    with physical_session() as db:
        estimate, _opening, old_lock, amendment_outcome, first, first_key = _registered_candidate(
            db
        )
        amendment_admission = db.get(PhysicalModelLockReplacementAdmission, first.id)
        assert amendment_admission is not None
        prior_amendment = amendment_admission.amendment_outcome_id
        assert prior_amendment == amendment_outcome.id
        # Register a second, independently signed candidate before either is consumed.
        from classifire.physical_models import PhysicalModelLockAmendmentAdmission

        source_admission = db.scalar(
            select(PhysicalModelLockAmendmentAdmission).where(
                PhysicalModelLockAmendmentAdmission.amendment_admission_id
                == amendment_outcome.amendment_admission_id
            )
        )
        assert source_admission is not None
        second_manifest, second_key = _replacement_manifest(
            db, estimate, old_lock, source_admission, amendment_outcome
        )
        second, second_created = _register(db, second_manifest, second_key)
        assert second_created is True
        actor = _replacement_actor(db)
        _first_outcome, created = _execute(db, first, first_key, actor)
        assert created is True

        with pytest.raises(SignedPhysicalModelLockReplacementExecutionError) as rejected:
            _execute(db, second, second_key, actor)

        assert rejected.value.code == "REPLACEMENT_LOCK_ACTIVE_LOCK_PRESENT"
        assert db.scalar(select(func.count(PhysicalModelLockReplacementOutcome.id))) == 1
