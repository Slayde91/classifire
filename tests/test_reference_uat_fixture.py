from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.db import Base
from classifire.models import Estimate, Opening
from classifire.services.commercial import derive_commercial_pricing
from classifire.services.quantity_labour_runtime import derive_quantity_and_labour_runtime
from classifire.services.repair_strategy import create_repair_strategy_lock, select_repair_strategy
from classifire.services.validated_snapshot import lock_validated_snapshot
from classifire.services.validation import run_independent_validation
from classifire.services.workflow_db import assess_estimate_workflow
from classifire.uat_reference import UAT_RATE, inspect_reference_uat, prepare_reference_uat


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def test_reference_uat_fixture_reaches_validated_snapshot_through_real_services() -> None:
    with _session() as db:
        fixture = prepare_reference_uat(db, run_id="fixture-001")
        estimate = db.get(Estimate, fixture.estimate_id)
        opening = db.get(Opening, fixture.opening_id)
        assert estimate is not None
        assert opening is not None
        assert assess_estimate_workflow(db, estimate).stage == "opening_specific_technical_search"

        strategy = select_repair_strategy(db, opening, variant_id=fixture.variant_id)
        assert strategy.status == "candidate_selected"
        repair_lock, created, components = create_repair_strategy_lock(db, opening)
        assert created
        assert repair_lock.validator_result == "PASS"
        assert len(components) == 1
        assert components[0].category == "COLLAR"
        assert components[0].candidate_status == "CONFIRMED_TECHNICAL_MATCH"
        assert assess_estimate_workflow(db, estimate).stage == "quantity_and_labour"

        quantity_result = derive_quantity_and_labour_runtime(db, estimate)
        assert len(quantity_result.quantities) == 1
        assert quantity_result.quantities[0].numeric_value == 1
        assert quantity_result.quantities[0].unit_basis == "each"
        assert quantity_result.quantities[0].status == "validated"
        assert quantity_result.labour_activities == ()
        assert assess_estimate_workflow(db, estimate).stage == "commercial_pricing_and_recovery"

        commercial = derive_commercial_pricing(db, estimate)
        assert len(commercial.pricing_components) == 1
        assert commercial.pricing_components[0].extended_cost == UAT_RATE
        assert commercial.pricing_components[0].status == "validated"
        assert len(commercial.method_locks) == 1
        assert commercial.method_locks[0].selected_pricing_method == "Exact Library Match"
        assert commercial.method_locks[0].validator_outcome == "PASS"
        assert assess_estimate_workflow(db, estimate).stage == "independent_validation"

        validation = run_independent_validation(db, estimate)
        assert validation.passed
        assert validation.gate_evidence.result == "PASS"
        assert validation.gate_evidence.exception_count == 0
        assert assess_estimate_workflow(db, estimate).stage == "validated_snapshot"

        snapshot, created = lock_validated_snapshot(db, estimate)
        assert created
        assert snapshot["estimate"]["subtotal_ex_tax"] == "275.00"
        assert assess_estimate_workflow(db, estimate).stage == "output_rendering"

        inspection = inspect_reference_uat(
            db,
            estimate_id=estimate.id,
            expected_stage="output_rendering",
        )
        assert inspection["ok"], inspection["errors"]
