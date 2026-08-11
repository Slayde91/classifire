from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import EvidenceSource, ServiceOpeningLink
from classifire.db import Base
from classifire.models import Estimate, Opening, Project, Service
from classifire.services.physical_scope import (
    assess_physical_model_completeness,
    canonical_opening_type,
    is_blank_opening_type,
)
from classifire.services.workflow import WorkflowAction
from classifire.services.workflow_guard import check_estimate_action


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _estimate(db: Session) -> Estimate:
    project = Project(reference="BLANK-OPENING-001", name="Blank Opening Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="BLANK-OPENING-001-R1",
        title="Blank Opening Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    db.add(EvidenceSource(estimate_id=estimate.id, evidence_type="test_fixture"))
    db.flush()
    return estimate


def _complete_opening(estimate: Estimate, **kwargs) -> Opening:
    values = {
        "estimate_id": estimate.id,
        "opening_code": "O-001",
        "substrate_type": "concrete",
        "substrate_plane": "floor",
        "orientation": "horizontal",
        "frl": "-/120/120",
    }
    values.update(kwargs)
    return Opening(**values)


def test_blank_opening_aliases_normalise_to_canonical_types() -> None:
    assert canonical_opening_type("redundant core hole") == "blank_core_hole"
    assert canonical_opening_type("empty_core_hole") == "blank_core_hole"
    assert canonical_opening_type("blank aperture") == "blank_opening"
    assert is_blank_opening_type("blank core hole") is True
    assert is_blank_opening_type("service_penetration") is False


def test_blank_core_hole_is_complete_without_service_link() -> None:
    with _session() as db:
        estimate = _estimate(db)
        db.add(_complete_opening(estimate, opening_type="blank_core_hole"))
        db.flush()

        assessment = assess_physical_model_completeness(db, estimate.id)
        assert assessment.complete is True
        assert assessment.openings[0].blank_opening is True
        assert assessment.openings[0].service_link_count == 0

        guard = check_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)
        assert guard.allowed is True


def test_service_penetration_without_service_link_fails_closed() -> None:
    with _session() as db:
        estimate = _estimate(db)
        db.add(_complete_opening(estimate, opening_type="service_penetration"))
        db.flush()

        assessment = assess_physical_model_completeness(db, estimate.id)
        assert assessment.complete is False
        assert "service_opening_link_or_blank_opening_classification" in assessment.openings[0].missing_fields

        guard = check_estimate_action(db, estimate, WorkflowAction.LOCK_PHYSICAL_MODEL)
        assert guard.allowed is False


def test_service_penetration_with_service_link_is_complete() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening = _complete_opening(
            estimate,
            opening_type="service_penetration",
            substrate_plane="wall",
            orientation="vertical",
        )
        db.add(opening)
        db.flush()
        service = Service(
            opening_id=opening.id,
            service_code="S-001",
            service_type="pipe",
            material="copper",
            quantity=1,
        )
        db.add(service)
        db.flush()
        db.add(ServiceOpeningLink(service_id=service.id, opening_id=opening.id))
        db.flush()

        assessment = assess_physical_model_completeness(db, estimate.id)
        assert assessment.complete is True
        assert assessment.openings[0].blank_opening is False
        assert assessment.openings[0].service_link_count == 1


def test_blank_opening_still_requires_substrate_plane_type_orientation_and_frl() -> None:
    with _session() as db:
        estimate = _estimate(db)
        db.add(
            Opening(
                estimate_id=estimate.id,
                opening_code="O-001",
                opening_type="blank_core_hole",
                substrate_type=None,
                substrate_plane=None,
                orientation=None,
                frl=None,
            )
        )
        db.flush()

        assessment = assess_physical_model_completeness(db, estimate.id)
        assert assessment.complete is False
        assert set(assessment.openings[0].missing_fields) == {
            "substrate_type",
            "substrate_plane",
            "orientation",
            "frl",
        }
