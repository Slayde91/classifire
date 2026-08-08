from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import (
    EvidenceSource,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from classifire.commercial_models import (
    LabourActivity,
    ProductivitySource,
    Quantity,
    QuantityFormulaInput,
)
from classifire.db import Base
from classifire.models import Estimate, Opening, Project, Service
from classifire.services.quantity_labour import QuantityLabourError, derive_quantity_and_labour
from classifire.services.workflow import WorkflowStage
from classifire.services.workflow_db import assess_estimate_workflow


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _fixture(
    db: Session,
    *,
    category: str,
    formula_id: str,
    labour_activities: list[str] | None = None,
) -> tuple[Estimate, Opening, Service, SystemRequiredComponent]:
    project = Project(reference=f"QL-{category}", name="Quantity Labour Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference=f"QL-{category}-R1",
        title="Quantity Labour Test",
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
        nominal_size_mm=50,
        outside_diameter_mm=50,
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
        content_hash=(category.lower()[:1] or "x") * 64,
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
        service_id=(
            service.id
            if category
            in {
                "MASTIC_SEALANT",
                "SUPPORT",
                "COLLAR",
                "SLEEVE",
                "WRAP_MATERIAL",
                "MECHANICAL_FIXING",
                "PIGTAIL_FIXING",
                "CABLE_TIE",
            }
            else None
        ),
        candidate_id="VAR-001",
        category=category,
        description=f"Required {category}",
        technical_requirement_id="REQ-001",
        quantity_formula_id=formula_id,
        required_labour_activity_ids=labour_activities or [],
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
            content_hash=(category.lower()[-1:] or "y") * 64,
        )
    )
    db.flush()
    return estimate, opening, service, component


def test_batt_area_uses_opening_geometry_and_persists_formula_inputs() -> None:
    with _session() as db:
        estimate, _, _, component = _fixture(
            db, category="BATT", formula_id="QF-BATT-BOARD-AREA"
        )
        result = derive_quantity_and_labour(db, estimate)
        assert len(result.quantities) == 1
        quantity = result.quantities[0]
        assert quantity.numeric_value == Decimal("0.069000")
        assert quantity.unit_basis == "m2"
        assert quantity.status == "validated"
        assert quantity.formula_id == "QF-BATT-BOARD-AREA"
        assert (quantity.provenance or {})["engine_version"] == "QUANTIFIRE-QUANTITY-ENGINE-v1.0"

        inputs = list(
            db.scalars(
                select(QuantityFormulaInput).where(
                    QuantityFormulaInput.quantity_record_id == quantity.id
                )
            ).all()
        )
        assert {item.input_name for item in inputs} == {
            "height_mm",
            "layers",
            "waste_factor",
            "width_mm",
        }
        assert all(item.validator_status == "PASS" for item in inputs)
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.quantity_and_labour_complete
        assert assessment.stage == WorkflowStage.COMMERCIAL_PRICING_AND_RECOVERY.value


def test_unverified_explicit_input_keeps_quantity_stage_provisional() -> None:
    with _session() as db:
        estimate, _, _, component = _fixture(
            db, category="SUPPORT", formula_id="QF-EACH"
        )
        result = derive_quantity_and_labour(
            db,
            estimate,
            component_inputs={component.id: {"count": 2}},
        )
        quantity = result.quantities[0]
        assert quantity.numeric_value == Decimal("2.000000")
        assert quantity.status == "provisional"
        assessment = assess_estimate_workflow(db, estimate)
        assert not assessment.facts.quantity_and_labour_complete
        assert assessment.stage == WorkflowStage.QUANTITY_AND_LABOUR.value


def test_missing_required_formula_input_fails_without_partial_quantity_write() -> None:
    with _session() as db:
        estimate, _, _, _ = _fixture(
            db, category="MASTIC_SEALANT", formula_id="QF-MASTIC-ANNULAR-VOLUME"
        )
        with pytest.raises(QuantityLabourError, match="opening_diameter_mm"):
            derive_quantity_and_labour(db, estimate)
        assert db.scalar(select(func.count()).select_from(Quantity)) == 0


def test_required_labour_fails_closed_without_approved_productivity_source() -> None:
    with _session() as db:
        estimate, _, _, _ = _fixture(
            db,
            category="BATT",
            formula_id="QF-BATT-BOARD-AREA",
            labour_activities=["MEASURE_BATT"],
        )
        with pytest.raises(QuantityLabourError, match="No approved ProductivitySource"):
            derive_quantity_and_labour(db, estimate)
        assert db.scalar(select(func.count()).select_from(Quantity)) == 0
        assert db.scalar(select(func.count()).select_from(LabourActivity)) == 0


def test_approved_productivity_derives_rate_free_person_hours_and_completes_stage() -> None:
    with _session() as db:
        estimate, _, _, component = _fixture(
            db,
            category="BATT",
            formula_id="QF-BATT-BOARD-AREA",
            labour_activities=["MEASURE_BATT"],
        )
        productivity = ProductivitySource(
            activity="MEASURE_BATT",
            quantity_unit="m2",
            base_hours_per_unit=Decimal("2"),
            source_record_id="PROD-001",
            source_version="1",
            executable_formula_id="QF-LABOUR-ACTIVITY",
            evidence_class="CONTROLLED_BENCHMARK",
            confidence="HIGH",
            approval_status="APPROVED",
        )
        db.add(productivity)
        db.flush()

        result = derive_quantity_and_labour(db, estimate)
        assert len(result.quantities) == 1
        assert len(result.labour_activities) == 1
        labour = result.labour_activities[0]
        assert labour.required_component_id == component.id
        assert labour.activity_name == "MEASURE_BATT"
        assert labour.labour_quantity_hours == Decimal("0.138000")
        assert labour.status == "validated"
        assert labour.unit_rate is None
        assert labour.extended_cost is None
        assert (labour.provenance or {})["engine_version"] == "QUANTIFIRE-LABOUR-ENGINE-v1.0"

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.quantity_and_labour_complete
        assert assessment.stage == WorkflowStage.COMMERCIAL_PRICING_AND_RECOVERY.value


def test_quantity_and_labour_derivation_is_idempotent() -> None:
    with _session() as db:
        estimate, _, _, _ = _fixture(
            db,
            category="BATT",
            formula_id="QF-BATT-BOARD-AREA",
            labour_activities=["MEASURE_BATT"],
        )
        db.add(
            ProductivitySource(
                activity="MEASURE_BATT",
                quantity_unit="m2",
                base_hours_per_unit=Decimal("2"),
                source_record_id="PROD-001",
                executable_formula_id="QF-LABOUR-ACTIVITY",
                approval_status="APPROVED",
            )
        )
        db.flush()
        first = derive_quantity_and_labour(db, estimate)
        second = derive_quantity_and_labour(db, estimate)
        assert second.quantities[0].id == first.quantities[0].id
        assert second.labour_activities[0].id == first.labour_activities[0].id
        assert db.scalar(
            select(func.count()).select_from(Quantity).where(Quantity.status != "superseded")
        ) == 1
        assert db.scalar(
            select(func.count()).select_from(LabourActivity).where(
                LabourActivity.status != "superseded"
            )
        ) == 1
