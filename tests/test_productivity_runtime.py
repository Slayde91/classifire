from __future__ import annotations

import hashlib
import json
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quantifire import canonical_models, commercial_models  # noqa: F401
from quantifire.canonical_models import (
    EvidenceSource,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from quantifire.commercial_models import ProductivitySource
from quantifire.db import Base
from quantifire.models import Estimate, LibraryRelease, Opening, Project, Service
from quantifire.release_admin import _snapshot_records
from quantifire.services.productivity import (
    ProductivitySourceError,
    approve_productivity_source,
    create_productivity_source,
)
from quantifire.services.quantity_labour import QuantityLabourError
from quantifire.services.quantity_labour_runtime import derive_quantity_and_labour_runtime
from quantifire.services.release_scope import pinned_productivity_source


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _hash_manifest(manifest: dict[str, object]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _approved_source(
    db: Session,
    *,
    version: str,
    base_hours: Decimal,
) -> ProductivitySource:
    source = create_productivity_source(
        db,
        activity="MEASURE_BATT",
        quantity_unit="m2",
        base_hours_per_unit=base_hours,
        source_record_id="PROD-MEASURE-BATT",
        source_version=version,
        executable_formula_id="QF-LABOUR-ACTIVITY",
        source_quantity="2",
        source_hours=base_hours * Decimal("2"),
        evidence_class="CONTROLLED_BENCHMARK",
        confidence="HIGH",
    )
    source, _ = approve_productivity_source(db, source)
    return source


def _runtime_fixture(db: Session) -> tuple[Estimate, SystemRequiredComponent]:
    project = Project(reference="PROD-RUNTIME", name="Productivity Runtime Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="PROD-RUNTIME-R1",
        title="Productivity Runtime Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    db.add(EvidenceSource(estimate_id=estimate.id, evidence_type="test_fixture"))

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
        quantity=1,
    )
    db.add(service)
    db.flush()
    db.add(ServiceOpeningLink(service_id=service.id, opening_id=opening.id))
    db.flush()

    physical_lock = PhysicalModelLock(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        service_ids=[service.id],
        opening_ids=[opening.id],
        validator_result="PASS",
        content_hash="a" * 64,
    )
    db.add(physical_lock)
    db.flush()
    strategy = RepairStrategy(
        opening_id=opening.id,
        physical_model_lock_id=physical_lock.id,
        candidate_id="VAR-001",
        status="locked",
    )
    db.add(strategy)
    db.flush()
    component = SystemRequiredComponent(
        opening_id=opening.id,
        candidate_id="VAR-001",
        category="BATT",
        description="Required batt",
        technical_requirement_id="REQ-001",
        quantity_formula_id="QF-BATT-BOARD-AREA",
        required_labour_activity_ids=["MEASURE_BATT"],
        candidate_status="CONFIRMED_TECHNICAL_MATCH",
        mandatory=True,
    )
    db.add(component)
    db.flush()
    db.add(
        RepairStrategyLock(
            opening_id=opening.id,
            repair_strategy_id=strategy.id,
            candidate_id="VAR-001",
            candidate_status="CONFIRMED_TECHNICAL_MATCH",
            required_component_ids=[component.id],
            validator_result="PASS",
            content_hash="b" * 64,
        )
    )
    db.flush()
    return estimate, component


def _labour_release(db: Session, source: ProductivitySource, version: str) -> LibraryRelease:
    manifest: dict[str, object] = {
        "release_type": "labour",
        "version": version,
        "records": [
            {
                "id": source.id,
                "record_type": "productivity_source",
                "key": source.activity,
                "source_record_id": source.source_record_id,
                "source_version": source.source_version,
            }
        ],
    }
    release = LibraryRelease(
        library_type="labour",
        version=version,
        status="active",
        release_hash=_hash_manifest(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.flush()
    return release


def test_productivity_source_reconciles_source_hours_and_quantity() -> None:
    with _session() as db:
        source = create_productivity_source(
            db,
            activity="MEASURE_BATT",
            quantity_unit="m2",
            base_hours_per_unit=Decimal("2"),
            source_record_id="PROD-001",
            source_version="1",
            source_quantity="2",
            source_hours=Decimal("4"),
            evidence_class="CONTROLLED_BENCHMARK",
            confidence="HIGH",
        )
        assert source.approval_status == "DRAFT"
        approved, changed = approve_productivity_source(db, source)
        assert changed
        assert approved.approval_status == "APPROVED"


def test_productivity_source_rejects_inconsistent_base_hours() -> None:
    with _session() as db:
        with pytest.raises(ProductivitySourceError, match="does not reconcile"):
            create_productivity_source(
                db,
                activity="MEASURE_BATT",
                quantity_unit="m2",
                base_hours_per_unit=Decimal("3"),
                source_record_id="PROD-001",
                source_version="1",
                source_quantity="2",
                source_hours=Decimal("4"),
            )


def test_labour_release_snapshot_contains_approved_productivity_source() -> None:
    with _session() as db:
        source = _approved_source(db, version="1", base_hours=Decimal("2"))
        rows = _snapshot_records(db, "labour")
        matches = [row for row in rows if row.get("record_type") == "productivity_source"]
        assert len(matches) == 1
        assert matches[0]["id"] == source.id
        assert matches[0]["activity"] == "MEASURE_BATT"


def test_historical_labour_release_keeps_superseded_productivity_version() -> None:
    with _session() as db:
        estimate, _ = _runtime_fixture(db)
        v1 = _approved_source(db, version="1", base_hours=Decimal("2"))
        release_v1 = _labour_release(db, v1, "LAB-1")
        estimate.labour_release_id = release_v1.id
        db.flush()

        v2 = _approved_source(db, version="2", base_hours=Decimal("3"))
        assert v1.approval_status == "SUPERSEDED"
        assert v2.approval_status == "APPROVED"

        pinned = pinned_productivity_source(db, estimate, "MEASURE_BATT")
        assert pinned.id == v1.id
        assert pinned.base_hours_per_unit == Decimal("2.000000")

        result = derive_quantity_and_labour_runtime(db, estimate)
        labour = result.labour_activities[0]
        assert labour.productivity_source_id == v1.id
        assert labour.labour_quantity_hours == Decimal("0.138000")
        assert labour.unit_rate is None
        assert labour.extended_cost is None


def test_runtime_derivation_fails_closed_without_pinned_labour_release() -> None:
    with _session() as db:
        estimate, _ = _runtime_fixture(db)
        _approved_source(db, version="1", base_hours=Decimal("2"))
        with pytest.raises(QuantityLabourError, match="pinned labour release"):
            derive_quantity_and_labour_runtime(db, estimate)
