from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from sqlalchemy import create_engine, select
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
    PricingComponent,
    Quantity,
)
from classifire.db import Base
from classifire.models import (
    Estimate,
    LabourComponent,
    LibraryRelease,
    MarkupProfile,
    Opening,
    PricingLibraryRecord,
    Product,
    Project,
    Service,
    TechnicalVariant,
)
from classifire.services.commercial import derive_commercial_pricing
from classifire.services.workflow import WorkflowStage
from classifire.services.workflow_db import assess_estimate_workflow


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return Session(engine)


def _manifest_hash(manifest: dict[str, object]) -> str:
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _release(db: Session, library_type: str, version: str, record_ids: list[str]) -> LibraryRelease:
    manifest: dict[str, object] = {"records": [{"id": item} for item in record_ids]}
    release = LibraryRelease(
        library_type=library_type,
        version=version,
        status="active",
        release_hash=_manifest_hash(manifest),
        source_manifest=manifest,
    )
    db.add(release)
    db.flush()
    return release


def _pricing_record(
    db: Session,
    *,
    entry_id: str = "PKB-001",
    rate: str = "500",
    service_material: str = "copper",
    exact: str = "YES",
    proxy: str = "NO",
    inclusions: dict[str, str] | None = None,
) -> PricingLibraryRecord:
    applicability = {
        "Exact_Match_Eligible_YN": exact,
        "Proxy_Eligible_YN": proxy,
        "Critical_Fields_Complete_YN": "YES",
        "Opening_Level_Reconciliation_Required_YN": "NO",
        "Duplicate_Recovery_Risk_Class": "LOW",
        "Package15_Variant_ID_Parsed": "VAR-001",
    }
    record = PricingLibraryRecord(
        pkb_entry_id=entry_id,
        entry_version="1",
        description=f"Rate {entry_id}",
        unit="each",
        rate_ex_tax=Decimal(rate),
        currency="AUD",
        tax_basis="GST Exclusive",
        service_type="pipe",
        service_class="pipe",
        service_material=service_material,
        substrate="concrete",
        substrate_plane="wall",
        orientation="vertical",
        frl="-/120/120",
        manufacturer="FIREFLY",
        repair_family="tested service treatment",
        rate_inclusions=inclusions or {"Rate_Includes_Collar": "YES"},
        rate_exclusions={},
        applicability=applicability,
        commercial_confidence="HIGH",
        technical_status="MATCHED",
        status="active",
        source_hash=entry_id.lower().replace("-", "")[:1] * 64 or "a" * 64,
        source_json={**applicability, "PKB_Entry_ID": entry_id},
    )
    db.add(record)
    db.flush()
    return record


def _base_estimate(
    db: Session,
    *,
    service_count: int = 1,
    shared_batt: bool = True,
    required_labour: bool = False,
) -> tuple[Estimate, Opening, list[Service], list[SystemRequiredComponent]]:
    project = Project(reference="COMM-001", name="Commercial Engine Test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference="COMM-001-R1",
        title="Commercial Engine Test",
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
        width_mm=500,
        height_mm=300,
        frl="-/120/120",
    )
    db.add(opening)
    db.flush()

    services: list[Service] = []
    components: list[SystemRequiredComponent] = []
    for index in range(service_count):
        service = Service(
            opening_id=opening.id,
            service_code=f"S-{index + 1:03d}",
            service_type="pipe",
            material="copper",
            nominal_size_mm=50,
            outside_diameter_mm=50,
            quantity=1,
        )
        db.add(service)
        db.flush()
        db.add(ServiceOpeningLink(service_id=service.id, opening_id=opening.id))
        component = SystemRequiredComponent(
            opening_id=opening.id,
            service_id=service.id,
            candidate_id="VAR-001",
            category="COLLAR",
            description=f"Collar treatment for {service.service_code}",
            technical_requirement_id=f"REQ-COLLAR-{index + 1}",
            quantity_formula_id="QF-EACH",
            required_labour_activity_ids=([] if not required_labour else ["INSTALL_COLLAR"]),
            candidate_status="CONFIRMED_TECHNICAL_MATCH",
            mandatory=True,
        )
        db.add(component)
        db.flush()
        services.append(service)
        components.append(component)

    if shared_batt:
        batt = SystemRequiredComponent(
            opening_id=opening.id,
            service_id=None,
            candidate_id="VAR-001",
            category="BATT",
            description="Shared batt closure",
            technical_requirement_id="REQ-BATT-SHARED",
            quantity_formula_id="QF-BATT-BOARD-AREA",
            required_labour_activity_ids=[],
            candidate_status="CONFIRMED_TECHNICAL_MATCH",
            mandatory=True,
        )
        db.add(batt)
        db.flush()
        components.append(batt)

    variant = TechnicalVariant(
        variant_id="VAR-001",
        system_id="SYS-001",
        service_type="pipe",
        service_material="copper",
        substrate_type="concrete",
        orientation="vertical",
        frl="-/120/120",
        component_requirements={"required_component_categories": [item.category for item in components]},
        status="active",
        expert_review_required=False,
        source_hash="1" * 64,
        source_json={},
    )
    db.add(variant)
    db.flush()

    physical_lock = PhysicalModelLock(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        service_ids=[item.id for item in services],
        opening_ids=[opening.id],
        validator_result="PASS",
        content_hash="2" * 64,
    )
    db.add(physical_lock)
    db.flush()
    strategy = RepairStrategy(
        opening_id=opening.id,
        physical_model_lock_id=physical_lock.id,
        candidate_id="VAR-001",
        selected_technical_variant_id=variant.id,
        match_classification="opening_specific_candidate",
        status="locked",
    )
    db.add(strategy)
    db.flush()
    db.add(
        RepairStrategyLock(
            opening_id=opening.id,
            repair_strategy_id=strategy.id,
            candidate_id="VAR-001",
            candidate_status="APPROVED",
            required_component_ids=[item.id for item in components],
            validator_result="PASS",
            content_hash="3" * 64,
        )
    )
    db.flush()

    for component in components:
        value = Decimal("0.50") if component.category == "BATT" else Decimal("1")
        unit = "m2" if component.category == "BATT" else "each"
        quantity = Quantity(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            required_component_id=component.id,
            quantity_type="Calculated Quantity",
            subject_type="system_required_component",
            subject_id=component.id,
            numeric_value=value,
            unit_basis=unit,
            source_method=component.quantity_formula_id,
            formula_id=component.quantity_formula_id,
            status="validated",
            provenance={"fixture": True},
        )
        db.add(quantity)
        db.flush()
        if required_labour:
            db.add(
                LabourActivity(
                    project_id=estimate.project_id,
                    estimate_id=estimate.id,
                    required_component_id=component.id,
                    activity_type="Installation",
                    activity_name="INSTALL_COLLAR",
                    labour_quantity_hours=Decimal("0.2"),
                    status="validated",
                    provenance={"fixture": True},
                )
            )
    db.flush()
    return estimate, opening, services, components


def test_exact_package14_rate_recovers_shared_batt_without_double_pricing() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(db, service_count=1, shared_batt=True)
        rate = _pricing_record(
            db,
            inclusions={
                "Rate_Includes_Collar": "YES",
                "Rate_Includes_Board_Batt": "YES",
                "Rate_Includes_Direct_Labour": "YES",
            },
        )
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [rate.id]).id
        db.flush()

        result = derive_commercial_pricing(db, estimate)
        assert len(result.pricing_components) == 2
        by_required = {item.required_component_id: item for item in result.pricing_components}
        collar = next(item for item in components if item.category == "COLLAR")
        batt = next(item for item in components if item.category == "BATT")
        assert by_required[collar.id].extended_cost == Decimal("500.0000")
        assert by_required[batt.id].extended_cost == Decimal("0.0000")
        assert by_required[batt.id].component_type == "covered_by_library_rate"
        assert {item.selected_pricing_method for item in result.method_locks} == {"Exact Library Match"}

        assessment = assess_estimate_workflow(db, estimate)
        assert assessment.facts.commercial_pricing_and_recovery_complete
        assert assessment.stage == WorkflowStage.INDEPENDENT_VALIDATION.value


def test_two_service_rates_cannot_both_recover_same_shared_batt() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(db, service_count=2, shared_batt=True)
        rate = _pricing_record(
            db,
            inclusions={
                "Rate_Includes_Collar": "YES",
                "Rate_Includes_Board_Batt": "YES",
            },
        )
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [rate.id]).id
        db.flush()

        result = derive_commercial_pricing(db, estimate)
        positive = [item for item in result.pricing_components if item.extended_cost and item.extended_cost > 0]
        assert len(positive) == 1
        assert positive[0].extended_cost == Decimal("500.0000")
        batt = next(item for item in components if item.category == "BATT")
        batt_row = next(item for item in result.pricing_components if item.required_component_id == batt.id)
        assert batt_row.extended_cost == Decimal("0.0000")
        methods = [item.selected_pricing_method for item in result.method_locks]
        assert methods.count("Exact Library Match") == 2  # anchor + covered shared batt
        assert methods.count("Not Priced") == 1


def test_component_built_price_uses_pinned_product_labour_and_markup_releases() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(
            db, service_count=1, shared_batt=False, required_labour=True
        )
        component = components[0]
        component.category = "COLLAR"
        quantity = db.scalar(select(Quantity).where(Quantity.required_component_id == component.id))
        assert quantity is not None
        quantity.unit_basis = "each"
        quantity.numeric_value = Decimal("1")

        # Mismatched Package 14 record proves the hierarchy falls through to component build.
        mismatched = _pricing_record(db, service_material="steel")
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [mismatched.id]).id

        product = Product(
            sku="COLLAR-PROD",
            revision=1,
            name="Controlled collar",
            item_type="product",
            category="collar",
            unit="each",
            base_cost=Decimal("10"),
            currency="AUD",
            tax_treatment="exclusive",
            status="active",
        )
        labour = LabourComponent(
            code="INSTALLER",
            revision=1,
            name="Installer",
            category="installation",
            unit="person_hour",
            base_rate=Decimal("100"),
            default_hours=Decimal("0"),
            crew_size=Decimal("1"),
            status="active",
        )
        markup = MarkupProfile(
            name="Global commercial markup",
            scope_type="global",
            scope_id=None,
            product_markup=Decimal("0.30"),
            material_markup=Decimal("0.30"),
            labour_markup=Decimal("0"),
            status="active",
        )
        db.add_all([product, labour, markup])
        db.flush()
        estimate.products_release_id = _release(db, "products", "PROD-1", [product.id]).id
        estimate.labour_release_id = _release(db, "labour", "LAB-1", [labour.id]).id
        estimate.markups_release_id = _release(db, "markups", "MARK-1", [markup.id]).id
        db.flush()

        result = derive_commercial_pricing(
            db,
            estimate,
            component_builds={
                component.id: {
                    "product_sku": product.sku,
                    "labour_codes": {"INSTALL_COLLAR": labour.code},
                    "validator_status": "PASS",
                    "proof_reference": "TEST-COMP-BUILD",
                }
            },
        )
        pricing = result.pricing_components[0]
        assert pricing.extended_cost == Decimal("33.0000")
        lock = result.method_locks[0]
        assert lock.selected_pricing_method == "Component-Built Price"
        assert lock.validator_outcome == "PASS"


def test_expert_estimate_is_used_only_after_higher_methods_are_unavailable() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(db, service_count=1, shared_batt=False)
        component = components[0]
        mismatched = _pricing_record(db, service_material="steel")
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [mismatched.id]).id
        db.flush()

        result = derive_commercial_pricing(
            db,
            estimate,
            expert_estimates={
                component.id: {
                    "unit_rate": "123.45",
                    "rationale": "Controlled expert estimate because no valid higher commercial method exists.",
                    "evidence_reference": "EXPERT-TEST-001",
                    "validator_status": "PASS",
                }
            },
        )
        pricing = result.pricing_components[0]
        assert pricing.extended_cost == Decimal("123.4500")
        lock = result.method_locks[0]
        assert lock.selected_pricing_method == "Expert Estimate"
        assert lock.validator_outcome == "PROVISIONAL"


def test_missing_all_commercial_methods_creates_not_priced_recovery_instead_of_zero_price() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(db, service_count=1, shared_batt=False)
        component = components[0]
        mismatched = _pricing_record(db, service_material="steel")
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [mismatched.id]).id
        db.flush()

        result = derive_commercial_pricing(db, estimate)
        pricing = result.pricing_components[0]
        assert pricing.extended_cost is None
        assert pricing.status == "not_priced"
        lock = result.method_locks[0]
        assert lock.selected_pricing_method == "Not Priced"
        assert lock.validator_outcome == "NOT PRICED"
        reconciliation = result.reconciliations[0]
        assert reconciliation.result == "PROVISIONAL"
        assert reconciliation.missing_status == "Not Priced — Missing Valid Method"


def test_equal_prices_across_distinct_scope_generate_anomaly_review() -> None:
    with _session() as db:
        estimate, _, _, components = _base_estimate(db, service_count=2, shared_batt=False)
        mismatched = _pricing_record(db, service_material="steel")
        estimate.pricing_release_id = _release(db, "pricing", "P14-1", [mismatched.id]).id
        db.flush()
        expert = {
            component.id: {
                "unit_rate": "100",
                "rationale": "Regression equal-price test",
                "evidence_reference": f"EXPERT-{index}",
                "validator_status": "PASS",
            }
            for index, component in enumerate(components, 1)
        }
        result = derive_commercial_pricing(db, estimate, expert_estimates=expert)
        assert len(result.anomaly_reviews) == 1
        assert result.anomaly_reviews[0].result == "REVIEW REQUIRED"
        assert len(result.anomaly_reviews[0].subject_ids or []) == 2
        assert all(item.anomaly_result == "REVIEW_REQUIRED" for item in result.method_locks)
