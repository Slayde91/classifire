from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import EvidenceSource, PhysicalModelLock, ServiceOpeningLink
from classifire.db import Base
from classifire.models import Estimate, Opening, Project, Service
from classifire.services.workflow import WorkflowAction, WorkflowTransitionError
from classifire.services.workflow_guard import check_estimate_action, require_estimate_action


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _estimate(db: Session) -> Estimate:
    project = Project(reference="WF-GUARD-001", name="Workflow Guard Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="WF-GUARD-001-R1",
        title="Workflow Guard Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    return estimate


def _locked_physical_model(db: Session, estimate: Estimate) -> tuple[Opening, Service]:
    db.add(EvidenceSource(estimate_id=estimate.id, evidence_type="test_fixture"))
    opening = Opening(
        estimate_id=estimate.id,
        opening_code="O-001",
        substrate_type="concrete",
        substrate_plane="wall",
        orientation="vertical",
        frl="-/120/120",
    )
    db.add(opening)
    db.flush()
    service = Service(
        opening_id=opening.id,
        service_code="S-001",
        service_type="pipe",
        material="copper",
    )
    db.add(service)
    db.flush()
    db.add(ServiceOpeningLink(service_id=service.id, opening_id=opening.id))
    db.flush()
    db.add(
        PhysicalModelLock(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            service_ids=[service.id],
            opening_ids=[opening.id],
            validator_result="PASS",
            content_hash="1" * 64,
        )
    )
    db.flush()
    return opening, service


def test_preflight_is_fail_closed_for_technical_search() -> None:
    with _session() as db:
        estimate = _estimate(db)
        receipt = check_estimate_action(db, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert not receipt.allowed
        assert receipt.stage == "evidence_intake"
        assert any("Physical Model Lock" in item for item in receipt.blockers)


def test_preflight_allows_technical_search_after_retained_physical_lock() -> None:
    with _session() as db:
        estimate = _estimate(db)
        _locked_physical_model(db, estimate)
        receipt = check_estimate_action(db, estimate, WorkflowAction.SEARCH_TECHNICAL)
        assert receipt.allowed
        assert receipt.blockers == ()
        assert receipt.stage == "opening_specific_technical_search"


def test_require_estimate_action_raises_same_transition_error_as_state_machine() -> None:
    with _session() as db:
        estimate = _estimate(db)
        with pytest.raises(WorkflowTransitionError, match="quantity and labour"):
            require_estimate_action(db, estimate, WorkflowAction.PRICE_AND_RECOVER)


def test_snapshot_action_remains_blocked_without_final_independent_validation() -> None:
    with _session() as db:
        estimate = _estimate(db)
        receipt = check_estimate_action(db, estimate, WorkflowAction.CREATE_VALIDATED_SNAPSHOT)
        assert not receipt.allowed
        assert "independent validation has not passed" in receipt.blockers
