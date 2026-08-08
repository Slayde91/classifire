from __future__ import annotations

from datetime import datetime, timezone

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
from quantifire.commercial_models import (
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    GateEvidence,
    LabourActivity,
    PricingComponent,
    Quantity,
)
from quantifire.db import Base
from quantifire.models import AuditEvent, Estimate, Opening, Project, Service
from quantifire.services.workflow import WorkflowStage
from quantifire.services.workflow_db import assess_estimate_workflow


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _estimate(db: Session) -> Estimate:
    project = Project(reference="WF-DB-001", name="Workflow Adapter Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="WF-DB-001-R1",
        title="Workflow Adapter Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()
    return estimate


def _physical_model(db: Session, estimate: Estimate) -> tuple[Opening, Service]:
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
    return opening, service


def test_empty_estimate_is_fail_closed_at_evidence_intake() -> None:
    with _session() as db:
        estimate = _estimate(db)
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.stage == WorkflowStage.EVIDENCE_INTAKE.value
        assert not assessment.facts.evidence_intake_complete
        assert not assessment.facts.physical_model_complete


def test_physical_model_requires_retained_lock_before_technical_stage() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening, service = _physical_model(db, estimate)

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.evidence_intake_complete
        assert assessment.facts.physical_model_complete
        assert not assessment.facts.physical_model_locked
        assert assessment.stage == WorkflowStage.PHYSICAL_MODEL_LOCK.value

        db.add(
            PhysicalModelLock(
                project_id=estimate.project_id,
                estimate_id=estimate.id,
                service_ids=[service.id],
                opening_ids=[opening.id],
                validator_result="PASS",
                content_hash="a" * 64,
            )
        )
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.physical_model_locked
        assert assessment.stage == WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH.value


def test_stale_repair_strategy_does_not_survive_new_physical_model_lock() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening, service = _physical_model(db, estimate)
        old_lock = PhysicalModelLock(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            service_ids=[service.id],
            opening_ids=[opening.id],
            validator_result="PASS",
            content_hash="a" * 64,
        )
        db.add(old_lock)
        db.flush()
        db.add(
            RepairStrategy(
                opening_id=opening.id,
                physical_model_lock_id=old_lock.id,
                candidate_id="CAND-OLD",
                status="candidate_selected",
            )
        )
        db.flush()

        old_lock.invalidated_at = datetime.now(timezone.utc)
        old_lock.invalidation_reason = "Physical model changed"
        db.add(
            PhysicalModelLock(
                project_id=estimate.project_id,
                estimate_id=estimate.id,
                service_ids=[service.id],
                opening_ids=[opening.id],
                validator_result="PASS",
                content_hash="b" * 64,
            )
        )
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.physical_model_locked
        assert not assessment.facts.technical_search_complete
        assert assessment.stage == WorkflowStage.OPENING_SPECIFIC_TECHNICAL_SEARCH.value


def test_adapter_progresses_through_quantity_commercial_and_validation_records() -> None:
    with _session() as db:
        estimate = _estimate(db)
        opening, service = _physical_model(db, estimate)
        physical_lock = PhysicalModelLock(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            service_ids=[service.id],
            opening_ids=[opening.id],
            validator_result="PASS",
            content_hash="b" * 64,
        )
        db.add(physical_lock)
        db.flush()

        strategy = RepairStrategy(
            opening_id=opening.id,
            physical_model_lock_id=physical_lock.id,
            candidate_id="CAND-001",
            status="locked",
        )
        db.add(strategy)
        db.flush()

        component = SystemRequiredComponent(
            opening_id=opening.id,
            service_id=service.id,
            candidate_id="CAND-001",
            category="firestop_material",
            description="Required firestop material",
            required_labour_activity_ids=["LAB-001"],
        )
        db.add(component)
        db.flush()

        db.add(
            RepairStrategyLock(
                opening_id=opening.id,
                repair_strategy_id=strategy.id,
                candidate_id="CAND-001",
                candidate_status="reviewed",
                required_component_ids=[component.id],
                validator_result="PASS",
                content_hash="c" * 64,
            )
        )
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.technical_search_complete
        assert assessment.facts.repair_strategy_locked
        assert assessment.facts.components_derived
        assert not assessment.facts.quantity_and_labour_complete

        quantity = Quantity(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            required_component_id=component.id,
            quantity_type="Calculated Quantity",
            subject_type="system_required_component",
            subject_id=component.id,
            numeric_value=1,
            unit_basis="each",
            formula_id="QF-EACH",
            status="validated",
        )
        labour = LabourActivity(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            required_component_id=component.id,
            activity_type="Installation",
            activity_name="LAB-001",
            labour_quantity_hours=1,
            status="validated",
        )
        db.add_all([quantity, labour])
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.quantity_and_labour_complete
        assert assessment.stage == WorkflowStage.COMMERCIAL_PRICING_AND_RECOVERY.value

        pricing = PricingComponent(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            opening_id=opening.id,
            service_id=service.id,
            required_component_id=component.id,
            quantity_id=quantity.id,
            component_type="material",
            scope_description="Firestop material",
        )
        db.add(pricing)
        db.flush()
        db.add_all(
            [
                CommercialMethodLock(
                    component_id=pricing.id,
                    selected_pricing_method="Component-Built Price",
                    validator_outcome="PASS",
                    content_hash="d" * 64,
                ),
                CommercialRecoveryRecord(
                    component_id=pricing.id,
                    recovery_status="Recovered — Component-Built",
                    active=True,
                ),
                ComponentRequirementReconciliation(
                    opening_id=opening.id,
                    required_component_id=component.id,
                    generated_component_id=pricing.id,
                    quantity_record_id=quantity.id,
                    labour_activity_ids=[labour.id],
                    recovery_status="Recovered — Component-Built",
                    result="PASS",
                ),
            ]
        )
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.commercial_pricing_and_recovery_complete
        assert assessment.stage == WorkflowStage.INDEPENDENT_VALIDATION.value

        db.add(
            GateEvidence(
                estimate_id=estimate.id,
                gate_type="INDEPENDENT_VALIDATION",
                validator_id="validator-test",
                exception_count=0,
                result="PASS",
            )
        )
        db.flush()

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.independent_validation_passed
        assert assessment.stage == WorkflowStage.VALIDATED_SNAPSHOT.value

        estimate.snapshot_json = {"test": True}
        estimate.snapshot_hash = "e" * 64
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.validated_snapshot_created
        assert assessment.stage == WorkflowStage.OUTPUT_RENDERING.value

        db.add(
            AuditEvent(
                actor_type="system",
                actor_name="test",
                action="render_output",
                entity_type="estimate",
                entity_id=estimate.id,
                project_id=estimate.project_id,
                event_hash="f" * 64,
            )
        )
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.output_rendered
        assert assessment.stage == WorkflowStage.HUMAN_RELEASE.value


def test_non_final_gate_pass_does_not_fake_independent_validation() -> None:
    with _session() as db:
        estimate = _estimate(db)
        db.add(
            GateEvidence(
                estimate_id=estimate.id,
                gate_type="COMPONENT_COMPLETENESS",
                validator_id="validator-test",
                exception_count=0,
                result="PASS",
            )
        )
        db.flush()
        assessment = assess_estimate_workflow(db, estimate)
        assert not assessment.facts.independent_validation_passed
