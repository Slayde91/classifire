from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Iterator

import pytest
from sqlalchemy import create_engine
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
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    EstimateCertificate,
    PricingComponent,
    Quantity,
)
from classifire.db import Base
from classifire.main import app
from classifire.models import Estimate, EstimateLine, LibraryRelease, Opening, Project, Service
from classifire.outputs.common import verify_snapshot
from classifire.services.validated_snapshot import SNAPSHOT_SCHEMA, lock_validated_snapshot
from classifire.services.validation import (
    IndependentValidationError,
    latest_passing_gate,
    run_independent_validation,
)
from classifire.services.workflow import WorkflowStage
from classifire.services.workflow_db import assess_estimate_workflow


@dataclass(frozen=True)
class _RouteView:
    path: str
    methods: frozenset[str]
    endpoint: Callable[..., Any] | None


def _iter_effective_routes() -> Iterator[_RouteView]:
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


def _manifest_hash(manifest: dict[str, Any]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _release(db: Session, kind: str, version: str) -> LibraryRelease:
    manifest: dict[str, Any] = {
        "release_type": kind,
        "version": version,
        "records": [{"id": f"{kind}-fixture-record"}],
    }
    release = LibraryRelease(
        library_type=kind,
        version=version,
        status="active",
        release_hash=_manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.flush()
    return release


def _fixture(
    db: Session,
    *,
    method: str = "Exact Library Match",
    validator_outcome: str = "PASS",
    pricing_status: str = "validated",
    recovery_status: str = "Recovered — Exact Library Match",
    reconciliation_result: str = "PASS",
    amount: Decimal = Decimal("100.00"),
) -> tuple[Estimate, SystemRequiredComponent, PricingComponent]:
    project = Project(reference="VAL-001", name="Validation Release Test")
    db.add(project)
    db.flush()
    pricing_release = _release(db, "pricing", "pricing-test")
    technical_release = _release(db, "technical", "technical-test")
    labour_release = _release(db, "labour", "labour-test")

    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="VAL-001-R1",
        title="Validation Release Test",
        status="draft",
        pricing_release_id=pricing_release.id,
        technical_release_id=technical_release.id,
        labour_release_id=labour_release.id,
        tax_rate=Decimal("0.10"),
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

    physical_lock = PhysicalModelLock(
        project_id=project.id,
        estimate_id=estimate.id,
        service_ids=[service.id],
        opening_ids=[opening.id],
        validator_result="PASS",
        content_hash="1" * 64,
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
        service_id=service.id,
        candidate_id="VAR-001",
        category="COLLAR",
        description="Required collar",
        technical_requirement_id="REQ-001",
        quantity_formula_id="QF-EACH",
        required_labour_activity_ids=[],
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
            candidate_status="APPROVED",
            required_component_ids=[component.id],
            validator_result="PASS",
            content_hash="2" * 64,
        )
    )

    quantity = Quantity(
        project_id=project.id,
        estimate_id=estimate.id,
        required_component_id=component.id,
        quantity_type="Calculated Quantity",
        subject_type="system_required_component",
        subject_id=component.id,
        numeric_value=Decimal("1"),
        unit_basis="each",
        source_method="QF-EACH",
        formula_id="QF-EACH",
        status="validated",
        provenance={"record_hash": "3" * 64},
    )
    db.add(quantity)
    db.flush()
    pricing = PricingComponent(
        project_id=project.id,
        estimate_id=estimate.id,
        opening_id=opening.id,
        service_id=service.id,
        required_component_id=component.id,
        quantity_id=quantity.id,
        component_type="library_rate_anchor",
        scope_description="Canonical collar recovery",
        unit_basis="each",
        rate_source="pricing_release:PKB-001:v1",
        unit_rate=amount,
        extended_cost=amount,
        confidence="HIGH",
        risk_status="CONTROLLED",
        status=pricing_status,
        provenance={"record_hash": "4" * 64},
    )
    db.add(pricing)
    db.flush()
    db.add(
        CommercialMethodLock(
            component_id=pricing.id,
            library_search_completed=True,
            exact_library_match_found=(method == "Exact Library Match"),
            parameterised_rate_found=False,
            component_build_completed=False,
            expert_estimate_required=(method in {"Expert Estimate", "Not Priced"}),
            selected_pricing_method=method,
            package15_basis="VAR-001:REQ-001",
            rate_applicability_result="PASS_EXACT",
            quantity_formula_result="PASS:QF-EACH",
            labour_build_result="NOT_REQUIRED",
            recovery_status=recovery_status,
            validator_outcome=validator_outcome,
            content_hash="5" * 64,
        )
    )
    db.add(
        CommercialRecoveryRecord(
            component_id=pricing.id,
            recovery_status=recovery_status,
            economic_activity_key=f"required_component:{component.id}",
            recovery_location=f"required_component:{component.id}",
            allocated_amount_aud_ex_gst=amount,
            active=True,
        )
    )
    db.add(
        ComponentRequirementReconciliation(
            opening_id=opening.id,
            required_component_id=component.id,
            generated_component_id=pricing.id,
            quantity_record_id=quantity.id,
            labour_activity_ids=[],
            recovery_status=recovery_status,
            result=reconciliation_result,
        )
    )

    # Deliberately incorrect legacy line proves the validated snapshot ignores it.
    db.add(
        EstimateLine(
            estimate_id=estimate.id,
            opening_id=opening.id,
            service_id=service.id,
            line_number=1,
            component_type="material",
            description="Legacy line must not control validated totals",
            quantity=1,
            unit="each",
            base_unit_cost=Decimal("9999"),
            unit_sell=Decimal("9999"),
            subtotal_ex_tax=Decimal("9999"),
            tax=Decimal("999.90"),
            total_incl_tax=Decimal("10998.90"),
        )
    )
    db.flush()
    return estimate, component, pricing


def test_final_validator_passes_only_final_commercial_records() -> None:
    with _session() as db:
        estimate, _, _ = _fixture(db)
        result = run_independent_validation(db, estimate)
        assert result.passed
        assert result.gate_evidence.result == "PASS"
        assert result.gate_evidence.exception_count == 0
        assert estimate.status == "validated_pending_snapshot"
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.independent_validation_passed
        assert assessment.stage == WorkflowStage.VALIDATED_SNAPSHOT.value


def test_expert_estimate_is_retained_but_fails_final_independent_validation() -> None:
    with _session() as db:
        estimate, _, _ = _fixture(
            db,
            method="Expert Estimate",
            validator_outcome="PROVISIONAL",
            pricing_status="provisional",
            recovery_status="Recovered — Expert Estimate",
            reconciliation_result="PROVISIONAL",
        )
        result = run_independent_validation(db, estimate)
        assert not result.passed
        assert result.gate_evidence.result == "FAIL"
        codes = {item.code for item in result.issues}
        assert "COMMERCIAL_METHOD_NOT_FINAL_PASS" in codes
        assert "NON_FINAL_COMMERCIAL_METHOD" in codes
        assert "COMPONENT_RECONCILIATION_NOT_PASS" in codes


def test_passing_gate_becomes_stale_after_governed_commercial_change() -> None:
    with _session() as db:
        estimate, _, pricing = _fixture(db)
        result = run_independent_validation(db, estimate)
        assert result.passed
        latest_passing_gate(db, estimate)

        pricing.extended_cost = Decimal("101.00")
        db.flush()
        with pytest.raises(IndependentValidationError, match="stale"):
            latest_passing_gate(db, estimate)


def test_validated_snapshot_uses_canonical_pricing_and_creates_certificate() -> None:
    with _session() as db:
        estimate, component, _ = _fixture(db, amount=Decimal("100.00"))
        result = run_independent_validation(db, estimate)
        assert result.passed

        snapshot, created = lock_validated_snapshot(db, estimate)
        assert created
        assert snapshot["schema"] == SNAPSHOT_SCHEMA
        verify_snapshot(snapshot)
        assert snapshot["estimate"]["subtotal_ex_tax"] == "100.00"
        assert snapshot["estimate"]["tax_total"] == "10.00"
        assert snapshot["estimate"]["total_incl_tax"] == "110.00"
        assert snapshot["lines"][0]["required_component_id"] == component.id
        assert snapshot["lines"][0]["subtotal_ex_tax"] == "100.00"
        assert snapshot["estimate_certificate"]["final_certificate_hash"]
        assert db.query(EstimateCertificate).count() == 1
        assert estimate.subtotal_ex_tax == Decimal("100.0000")
        assert estimate.status == "locked"

        second, created_again = lock_validated_snapshot(db, estimate)
        assert not created_again
        assert second["snapshot_hash"] == snapshot["snapshot_hash"]


def test_release_control_routes_precede_legacy_lock_and_export_routes() -> None:
    routes = list(_iter_effective_routes())
    lock_path = "/api/v1/estimates/{estimate_id}/lock"
    export_path = "/api/v1/estimates/{estimate_id}/export/{artifact_type}"
    lock_routes = [
        route for route in routes if route.path == lock_path and "POST" in route.methods
    ]
    export_routes = [
        route for route in routes if route.path == export_path and "GET" in route.methods
    ]
    assert lock_routes and lock_routes[0].endpoint is not None
    assert export_routes and export_routes[0].endpoint is not None
    assert lock_routes[0].endpoint.__module__ == "classifire.api.release_control"
    assert export_routes[0].endpoint.__module__ == "classifire.api.release_control"
    assert any(
        route.path == "/api/v1/estimates/{estimate_id}/independent-validation"
        and "POST" in route.methods
        for route in routes
    )
