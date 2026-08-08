from __future__ import annotations

import hashlib
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from quantifire import canonical_models, commercial_models  # noqa: F401
from quantifire.canonical_models import (
    EvidenceSource,
    Package15CandidateRequirement,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from quantifire.db import Base
from quantifire.models import Estimate, LibraryRelease, Opening, Project, Service, TechnicalVariant
from quantifire.services.physical_model import create_physical_model_lock
from quantifire.services.repair_strategy import (
    create_repair_strategy_lock,
    select_repair_strategy,
)
from quantifire.services.workflow import WorkflowStage, WorkflowTransitionError
from quantifire.services.workflow_db import assess_estimate_workflow


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _manifest_hash(manifest: dict[str, object]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _parsed_requirements() -> dict[str, object]:
    return {
        "variant_id": "VAR-001",
        "system_id": "SYS-001",
        "requirements": [
            {
                "requirement_id": "REQ-001",
                "category": "BATT",
                "description": "Install FIREFLYBatt closure",
                "source_field": "Closure_Requirements",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
            {
                "requirement_id": "REQ-002",
                "category": "MASTIC_SEALANT",
                "description": "Seal joints with approved mastic",
                "source_field": "Sealant_Requirements",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
            {
                "requirement_id": "REQ-003",
                "category": "OTHER_SYSTEM_REQUIREMENT",
                "description": "minimum 200 mm distance",
                "source_field": "Closure_Requirements",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
            {
                "requirement_id": "REQ-004",
                "category": "SUPPORT",
                "description": "Service support must remain stable",
                "source_field": "Support_Rules",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
            {
                "requirement_id": "REQ-005",
                "category": "QA_DOCUMENTATION",
                "description": "System-specific inspection and verification",
                "source_field": "QA_Requirements",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
            {
                "requirement_id": "REQ-006",
                "category": "PREPARATION_CLEANUP",
                "description": "Local preparation and cleanup",
                "source_field": "Preparation_Requirements",
                "source_document_id": "DOC-001",
                "source_page": "p.10",
                "source_row": "R1",
                "mandatory": True,
                "exclusion": False,
            },
        ],
        "required_component_categories": [
            "BATT",
            "MASTIC_SEALANT",
            "OTHER_SYSTEM_REQUIREMENT",
            "PREPARATION_CLEANUP",
            "QA_DOCUMENTATION",
            "SUPPORT",
        ],
        "required_labour_activities": [
            "MEASURE_BATT",
            "CUT_BATT",
            "FIT_BATT",
            "INSTALL_BATT_FIXINGS",
            "PREPARE_SEAL_SURFACE",
            "APPLY_ANNULAR_MASTIC",
            "FORM_MASTIC_FILLET",
            "VERIFY_SEAL_DEPTH",
            "INSTALL_SERVICE_SUPPORT",
            "SYSTEM_INSPECTION",
            "COMPLETION_PHOTOGRAPHY",
            "REGISTER_UPDATE",
            "LOCAL_CLEANUP",
        ],
        "dependencies": ["None beyond cited source evidence"],
        "exclusions": ["incompatible service/substrate/orientation/FRL"],
        "parser_version": "QUANTIFIRE-P15-REQUIREMENT-PARSER-v1.1",
        "requirements_hash": "a" * 64,
    }


def _fixture(db: Session) -> tuple[Estimate, Opening, TechnicalVariant]:
    project = Project(reference="RS-001", name="Repair Strategy Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="RS-001-R1",
        title="Repair Strategy Test",
        status="draft",
    )
    db.add(estimate)
    db.flush()

    db.add(
        EvidenceSource(
            estimate_id=estimate.id,
            evidence_type="test_fixture",
            source_reference="fixture://repair-strategy",
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

    parsed = _parsed_requirements()
    variant = TechnicalVariant(
        variant_id="VAR-001",
        system_id="SYS-001",
        source_document_reference="DOC-001",
        source_page="p.10",
        manufacturer="FIREFLY",
        product_family="FIREFLYBatt",
        service_type="pipe",
        service_material="copper",
        substrate_type="concrete",
        orientation="vertical",
        opening_type="rectangular",
        component_requirements=parsed,
        labour_requirements=list(parsed["required_labour_activities"]),
        frl="-/120/120",
        quality_score=90,
        confidence_cap=95,
        search_eligibility="ACTIVE",
        expert_review_required=True,
        status="active",
        source_hash="2" * 64,
        source_json={"parsed_requirements": parsed},
    )
    db.add(variant)
    db.flush()

    manifest: dict[str, object] = {"records": [{"id": variant.id}]}
    release = LibraryRelease(
        library_type="technical",
        version="2.13-test",
        status="active",
        release_hash=_manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.flush()
    variant.release_id = release.id
    estimate.technical_release_id = release.id
    db.flush()
    return estimate, opening, variant


def test_repair_strategy_selection_requires_physical_model_lock() -> None:
    with _session() as db:
        _, opening, variant = _fixture(db)
        with pytest.raises(WorkflowTransitionError, match="Physical Model Lock"):
            select_repair_strategy(db, opening, variant_id=variant.variant_id)


def test_candidate_selection_retains_detailed_package15_requirements() -> None:
    with _session() as db:
        estimate, opening, variant = _fixture(db)
        create_physical_model_lock(db, estimate)
        strategy = select_repair_strategy(db, opening, variant_id=variant.variant_id)

        requirements = list(
            db.scalars(
                select(Package15CandidateRequirement).where(
                    Package15CandidateRequirement.opening_id == opening.id,
                    Package15CandidateRequirement.candidate_id == variant.variant_id,
                )
            ).all()
        )
        assert strategy.status == "candidate_selected"
        assert strategy.physical_model_lock_id
        assert strategy.technical_basis["requirements_hash"] == "a" * 64
        assert strategy.technical_basis["candidate_status"] == "CONFIRMED_TECHNICAL_MATCH"
        assert len(requirements) == 6
        assert any(item.category == "OTHER_SYSTEM_REQUIREMENT" for item in requirements)


def test_repair_strategy_lock_generates_requirement_level_component_inventory() -> None:
    with _session() as db:
        estimate, opening, variant = _fixture(db)
        create_physical_model_lock(db, estimate)
        select_repair_strategy(db, opening, variant_id=variant.variant_id)

        lock, created, components = create_repair_strategy_lock(db, opening)
        categories = {item.category for item in components}

        assert created
        assert lock.validator_result == "CONDITIONED"
        assert set(lock.required_component_ids) == {item.id for item in components}
        assert len(components) == 6
        assert categories == {
            "BATT",
            "MASTIC_SEALANT",
            "OTHER_SYSTEM_REQUIREMENT",
            "PREPARATION_CLEANUP",
            "QA_DOCUMENTATION",
            "SUPPORT",
        }

        batt = next(item for item in components if item.category == "BATT")
        assert batt.quantity_formula_id == "QF-BATT-BOARD-AREA"
        assert batt.technical_requirement_id == "REQ-001"
        assert batt.description == "Install FIREFLYBatt closure"
        assert "MEASURE_BATT" in (batt.required_labour_activity_ids or [])

        mastic = next(item for item in components if item.category == "MASTIC_SEALANT")
        assert mastic.service_id is not None
        assert mastic.quantity_formula_id == "QF-MASTIC-ANNULAR-VOLUME"

        support = next(item for item in components if item.category == "SUPPORT")
        assert support.service_id is not None
        assert support.quantity_formula_id == "QF-EACH"

        qa = next(item for item in components if item.category == "QA_DOCUMENTATION")
        assert qa.quantity_formula_id == "QF-EACH"
        assert "SYSTEM_INSPECTION" in (qa.required_labour_activity_ids or [])

        other = next(item for item in components if item.category == "OTHER_SYSTEM_REQUIREMENT")
        assert other.quantity_formula_id == "QF-EXPERT-ESTIMATE"

        persisted = list(
            db.scalars(
                select(SystemRequiredComponent).where(SystemRequiredComponent.opening_id == opening.id)
            ).all()
        )
        assert {item.id for item in persisted} == set(lock.required_component_ids)

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.repair_strategy_locked
        assert assessment.facts.components_derived
        assert assessment.stage == WorkflowStage.QUANTITY_AND_LABOUR.value


def test_repair_strategy_lock_is_idempotent() -> None:
    with _session() as db:
        estimate, opening, variant = _fixture(db)
        create_physical_model_lock(db, estimate)
        select_repair_strategy(db, opening, variant_id=variant.variant_id)

        first, created, first_components = create_repair_strategy_lock(db, opening)
        second, created_again, second_components = create_repair_strategy_lock(db, opening)

        assert created
        assert not created_again
        assert second.id == first.id
        assert second.content_hash == first.content_hash
        assert {item.id for item in second_components} == {item.id for item in first_components}


def test_unpinned_candidate_cannot_be_selected() -> None:
    with _session() as db:
        estimate, opening, _ = _fixture(db)
        create_physical_model_lock(db, estimate)
        outside = TechnicalVariant(
            variant_id="VAR-OUTSIDE",
            system_id="SYS-OUTSIDE",
            service_type="pipe",
            service_material="copper",
            substrate_type="concrete",
            orientation="vertical",
            frl="-/120/120",
            component_requirements=_parsed_requirements(),
            status="active",
            expert_review_required=True,
            source_hash="3" * 64,
            source_json={"parsed_requirements": _parsed_requirements()},
        )
        db.add(outside)
        db.flush()

        with pytest.raises(ValueError, match="pinned Technical release"):
            select_repair_strategy(db, opening, variant_id=outside.variant_id)
