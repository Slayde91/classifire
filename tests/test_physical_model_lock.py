from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import (
    EvidenceSource,
    RepairStrategyLock,
    ServiceOpeningLink,
)
from classifire.db import Base
from classifire.main import app
from classifire.models import Estimate, Opening, Project, Service
from classifire.services.physical_model import (
    PhysicalModelLockError,
    create_physical_model_lock,
)
from classifire.services.workflow import WorkflowTransitionError


@dataclass(frozen=True)
class _RouteView:
    path: str
    methods: frozenset[str]
    endpoint: Callable[..., Any] | None


def _iter_effective_routes() -> Iterator[_RouteView]:
    """Yield effective FastAPI routes across 0.141 included-router boundaries.

    FastAPI 0.141 represents included routers as private _IncludedRouter objects.
    Their effective_route_contexts() iterator supplies the resolved path/endpoint,
    while HTTP methods remain on context.original_route.
    """
    for route in app.routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            for context in contexts():
                original = context.original_route
                yield _RouteView(
                    path=getattr(context, "path", "") or getattr(original, "path", ""),
                    methods=frozenset(getattr(original, "methods", set()) or set()),
                    endpoint=getattr(context, "endpoint", None)
                    or getattr(original, "endpoint", None),
                )
            continue
        yield _RouteView(
            path=getattr(route, "path", ""),
            methods=frozenset(getattr(route, "methods", set()) or set()),
            endpoint=getattr(route, "endpoint", None),
        )


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _estimate(db: Session) -> Estimate:
    project = Project(reference="PML-001", name="Physical Model Lock Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="PML-001-R1",
        title="Physical Model Lock Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    return estimate


def _physical_model(
    db: Session, estimate: Estimate, *, evidence: bool = True
) -> tuple[Opening, Service]:
    if evidence:
        db.add(
            EvidenceSource(
                estimate_id=estimate.id,
                evidence_type="test_fixture",
                source_reference="fixture://physical-model",
                sha256="1" * 64,
            )
        )
    opening = Opening(
        estimate_id=estimate.id,
        opening_code="O-001",
        substrate_type="concrete",
        substrate_plane="wall",
        orientation="vertical",
        opening_type="rectangular",
        width_mm=300,
        height_mm=200,
        frl="-/120/120",
    )
    db.add(opening)
    db.flush()
    service = Service(
        opening_id=opening.id,
        service_code="S-001",
        service_type="pipe",
        material="copper",
        nominal_size_mm=50,
    )
    db.add(service)
    db.flush()
    db.add(ServiceOpeningLink(service_id=service.id, opening_id=opening.id))
    db.flush()
    return opening, service


def test_physical_model_lock_requires_evidence() -> None:
    with _session() as db:
        estimate = _estimate(db)
        _physical_model(db, estimate, evidence=False)
        with pytest.raises(WorkflowTransitionError, match="evidence intake"):
            create_physical_model_lock(db, estimate)


def test_physical_model_lock_is_created_and_idempotent() -> None:
    with _session() as db:
        estimate = _estimate(db)
        _physical_model(db, estimate)
        lock, created = create_physical_model_lock(db, estimate)
        assert created
        assert lock.validator_result == "PASS"
        assert lock.opening_ids
        assert lock.service_ids

        same_lock, created_again = create_physical_model_lock(db, estimate)
        assert not created_again
        assert same_lock.id == lock.id
        assert same_lock.content_hash == lock.content_hash


def test_physical_model_relock_supersedes_old_lock_before_downstream_lock() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening, _ = _physical_model(db, estimate)
        first, created = create_physical_model_lock(db, estimate)
        assert created

        opening.orientation = "horizontal"
        db.flush()
        second, created_second = create_physical_model_lock(db, estimate)
        assert created_second
        assert second.id != first.id
        assert second.content_hash != first.content_hash
        assert first.invalidated_at is not None


def test_physical_model_relock_fails_closed_when_downstream_repair_lock_exists() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening, _ = _physical_model(db, estimate)
        first, _ = create_physical_model_lock(db, estimate)
        db.add(
            RepairStrategyLock(
                opening_id=opening.id,
                candidate_id="CAND-001",
                candidate_status="reviewed",
                required_component_ids=["RC-001"],
                validator_result="PASS",
                content_hash="2" * 64,
            )
        )
        db.flush()
        opening.orientation = "horizontal"
        db.flush()

        with pytest.raises(PhysicalModelLockError, match="cascade invalidation"):
            create_physical_model_lock(db, estimate)
        assert first.invalidated_at is None


def test_guarded_technical_route_precedes_legacy_route_and_workflow_routes_are_registered() -> None:
    routes = list(_iter_effective_routes())
    technical_path = "/api/v1/openings/{opening_id}/technical-search"
    matching = [
        route for route in routes if route.path == technical_path and "GET" in route.methods
    ]
    assert matching
    assert matching[0].endpoint is not None
    assert matching[0].endpoint.__module__ == "classifire.api.guarded_technical"

    paths = {route.path for route in routes if route.path}
    assert "/api/v1/estimates/{estimate_id}/workflow" in paths
    assert "/api/v1/estimates/{estimate_id}/workflow/actions/{action}" in paths
    assert "/api/v1/estimates/{estimate_id}/physical-model/lock" in paths
    assert "/api/v1/estimates/{estimate_id}/evidence-sources" in paths
