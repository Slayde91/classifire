from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from physical_foundation_support import (
    add_estimate,
    add_evidence,
    add_opening,
    add_service,
    add_service_link,
    physical_session,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from classifire.models import Estimate, Opening
from classifire.physical_models import Defect, EvidenceSource, PhysicalModelLock
from classifire.services.physical_model import (
    PhysicalModelLockError,
    build_current_physical_model_lock_payload,
    build_current_physical_model_lock_snapshot,
    create_physical_model_lock,
)
from classifire.services.physical_mutation_guard import (
    PhysicalMutationError,
    require_physical_model_mutation,
)
from classifire.services.workflow import WorkflowAction, WorkflowTransitionError
from classifire.services.workflow_guard import check_estimate_action, require_estimate_action


@contextmanager
def complete_service_penetration() -> Iterator[tuple[Session, Estimate, Opening]]:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate)
        service = add_service(session, opening)
        add_service_link(session, service, opening)
        add_evidence(session, estimate)
        yield session, estimate, opening


def test_lock_content_snapshot_is_the_exact_hash_preimage_with_row_identities() -> None:
    with complete_service_penetration() as (session, estimate, opening):
        lock, created = create_physical_model_lock(session, estimate)
        assert created is True

        snapshot = build_current_physical_model_lock_snapshot(session, estimate)
        payload = snapshot.as_dict()

        assert hashlib.sha256(snapshot.canonical_payload_json.encode("utf-8")).hexdigest() == (
            snapshot.content_hash
        )
        assert snapshot.content_hash == lock.content_hash
        assert payload["schema"] == "CLASSIFIRE-PhysicalModelLock-v1"
        assert payload["project_id"] == estimate.project_id
        assert payload["estimate_id"] == estimate.id
        assert [item["id"] for item in payload["openings"]] == [opening.id]
        assert [item["canonical_defect_id"] for item in payload["openings"]] == [
            opening.canonical_defect_id
        ]
        assert len(payload["defects"]) == 1
        assert len(payload["evidence"]) == 1
        assert len(payload["services"]) == 1
        assert len(payload["service_opening_links"]) == 1
        assert payload["service_opening_links"][0]["opening_id"] == opening.id
        assert not session.new
        assert not session.dirty
        assert not session.deleted

        payload["openings"][0]["frl"] = "tampered detached copy"
        assert snapshot.as_dict()["openings"][0]["frl"] == "-/120/120"


def test_technical_search_is_blocked_until_a_valid_physical_model_lock_exists() -> None:
    with complete_service_penetration() as (session, estimate, _opening):
        before_lock = check_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert not before_lock.allowed
        assert "Physical Model Lock is not valid" in before_lock.blockers

        lock, created = create_physical_model_lock(session, estimate)
        assert created
        assert lock.validator_result == "PASS"

        require_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        after_lock = check_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert after_lock.allowed


def test_physical_model_lock_is_idempotent_but_changed_active_content_fails_closed() -> None:
    with complete_service_penetration() as (session, estimate, opening):
        first, created = create_physical_model_lock(session, estimate)
        assert created

        same, created = create_physical_model_lock(session, estimate)
        assert not created
        assert same.id == first.id
        assert same.content_hash == first.content_hash

        opening.frl = "-/90/90"
        session.flush()

        with pytest.raises(PhysicalModelLockError):
            create_physical_model_lock(session, estimate)

        assert first.invalidated_at is None


def test_lock_hash_is_stable_when_database_numeric_scale_is_refreshed() -> None:
    with complete_service_penetration() as (session, estimate, _opening):
        lock, created = create_physical_model_lock(session, estimate)
        assert created is True
        original_snapshot = build_current_physical_model_lock_snapshot(session, estimate)
        session.flush()
        session.expire_all()
        refreshed_estimate = session.get(Estimate, estimate.id)
        assert refreshed_estimate is not None

        current = build_current_physical_model_lock_payload(session, refreshed_estimate)
        refreshed_snapshot = build_current_physical_model_lock_snapshot(session, refreshed_estimate)

        assert current["content_hash"] == lock.content_hash
        assert refreshed_snapshot.content_hash == original_snapshot.content_hash
        assert refreshed_snapshot.canonical_payload_json == original_snapshot.canonical_payload_json


def test_stale_active_lock_blocks_technical_search_until_a_future_governed_reopen() -> None:
    with complete_service_penetration() as (session, estimate, opening):
        create_physical_model_lock(session, estimate)

        opening.frl = "-/90/90"
        session.flush()

        receipt = check_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert not receipt.allowed
        assert receipt.diagnostics["valid_physical_model_lock_count"] == 0
        assert receipt.diagnostics["stale_or_unverifiable_active_physical_model_lock_count"] == 1
        with pytest.raises(WorkflowTransitionError) as blocked:
            require_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert "Physical Model Lock is not valid" in str(blocked.value)


def test_canonical_defect_change_invalidates_the_active_lock_for_workflow_purposes() -> None:
    with complete_service_penetration() as (session, estimate, opening):
        create_physical_model_lock(session, estimate)
        defect = session.get(Defect, opening.canonical_defect_id)
        assert defect is not None

        defect.description = "Different observed defect condition"
        session.flush()

        receipt = check_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert not receipt.allowed
        assert receipt.diagnostics["valid_physical_model_lock_count"] == 0


def test_opening_note_change_invalidates_the_active_lock_for_workflow_purposes() -> None:
    with complete_service_penetration() as (session, estimate, opening):
        create_physical_model_lock(session, estimate)

        opening.notes = "Observed condition clarified after lock"
        session.flush()

        receipt = check_estimate_action(session, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert not receipt.allowed
        assert receipt.diagnostics["valid_physical_model_lock_count"] == 0


def test_lock_rejects_crossed_legacy_service_opening_links() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        first_opening = add_opening(session, estimate, opening_code="OP-001", defect_id="D-001")
        second_opening = add_opening(session, estimate, opening_code="OP-002", defect_id="D-002")
        first_service = add_service(session, first_opening, service_code="SVC-001")
        second_service = add_service(session, second_opening, service_code="SVC-002")
        add_service_link(session, first_service, second_opening)
        add_service_link(session, second_service, first_opening)
        add_evidence(session, estimate)

        with pytest.raises(PhysicalModelLockError, match="service/opening pairs"):
            create_physical_model_lock(session, estimate)


def test_lock_rejects_active_evidence_without_a_retained_digest() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate)
        service = add_service(session, opening)
        add_service_link(session, service, opening)
        session.add(
            EvidenceSource(
                estimate_id=estimate.id,
                evidence_type="inspection_photo",
                status="active",
            )
        )
        session.flush()

        with pytest.raises(PhysicalModelLockError, match="retained SHA-256"):
            create_physical_model_lock(session, estimate)


def test_lock_requires_each_opening_to_have_a_canonical_defect_binding() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        opening = add_opening(session, estimate, defect_id=None)
        service = add_service(session, opening)
        add_service_link(session, service, opening)
        add_evidence(session, estimate)

        with pytest.raises(PhysicalModelLockError, match="canonical Defect"):
            create_physical_model_lock(session, estimate)


def test_database_permits_only_one_active_lock_for_an_estimate() -> None:
    with physical_session() as session:
        estimate = add_estimate(session)
        session.add(
            PhysicalModelLock(
                project_id=estimate.project_id,
                estimate_id=estimate.id,
                service_ids=[],
                opening_ids=[],
                validator_result="PASS",
                content_hash="c" * 64,
            )
        )
        session.flush()
        session.add(
            PhysicalModelLock(
                project_id=estimate.project_id,
                estimate_id=estimate.id,
                service_ids=[],
                opening_ids=[],
                validator_result="PASS",
                content_hash="d" * 64,
            )
        )

        with pytest.raises(IntegrityError):
            session.flush()


def test_physical_mutation_is_rejected_after_an_active_lock() -> None:
    with complete_service_penetration() as (session, estimate, _opening):
        create_physical_model_lock(session, estimate)

        with pytest.raises(PhysicalMutationError):
            require_physical_model_mutation(session, estimate)
