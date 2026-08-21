from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import record_audit
from .canonical_models import (
    EvidenceSource,
    RepairStrategyLock,
    ServiceOpeningLink,
    SystemRequiredComponent,
)
from .commercial_models import (
    CommercialMethodLock,
    EstimateCertificate,
    GateEvidence,
    PricingComponent,
    Quantity,
)
from .config import Settings
from .models import (
    Approval,
    AuditEvent,
    Estimate,
    LabourComponent,
    LibraryRelease,
    Opening,
    PricingLibraryRecord,
    Project,
    Service,
    TechnicalVariant,
)
from .services.physical_model import create_physical_model_lock
from .services.workflow_db import assess_estimate_workflow

UAT_PREFIX = "UAT-OC"
UAT_RATE = Decimal("275.00")
EXPECTED_FINAL_STAGE = "human_release"


@dataclass(frozen=True)
class ReferenceUatFixture:
    run_id: str
    project_id: str
    project_reference: str
    estimate_id: str
    estimate_reference: str
    opening_id: str
    opening_code: str
    service_id: str
    service_code: str
    variant_id: str
    pricing_entry_id: str
    expected_rate_ex_tax: str
    initial_stage: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "project_id": self.project_id,
            "project_reference": self.project_reference,
            "estimate_id": self.estimate_id,
            "estimate_reference": self.estimate_reference,
            "opening_id": self.opening_id,
            "opening_code": self.opening_code,
            "service_id": self.service_id,
            "service_code": self.service_code,
            "variant_id": self.variant_id,
            "pricing_entry_id": self.pricing_entry_id,
            "expected_rate_ex_tax": self.expected_rate_ex_tax,
            "initial_stage": self.initial_stage,
        }


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _clean_run_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", value.strip()).strip("-")
    if not cleaned:
        raise ValueError("UAT run_id cannot be blank")
    if len(cleaned) > 24:
        raise ValueError("UAT run_id must be 24 characters or fewer")
    return cleaned


def _release(
    db: Session,
    *,
    library_type: str,
    version: str,
    record_ids: list[str],
    run_id: str,
) -> LibraryRelease:
    manifest = {
        "schema": "CLASSIFIRE-UAT-RELEASE-v1",
        "library_type": library_type,
        "version": version,
        "run_id": run_id,
        "records": [{"id": item} for item in record_ids],
    }
    release = LibraryRelease(
        library_type=library_type,
        version=version,
        status="uat_fixture",
        release_hash=_sha(manifest),
        source_manifest=manifest,
        notes="Synthetic CLASSIFIRE OpenClaw reference UAT release. Never select as a production current release.",
    )
    db.add(release)
    db.flush()
    return release


def prepare_reference_uat(db: Session, *, run_id: str) -> ReferenceUatFixture:
    """Create one deterministic, synthetic-but-governed OpenClaw UAT estimate.

    The fixture deliberately stops after Physical Model Lock. All downstream
    technical, quantity/labour, commercial, validation and output changes must be
    performed through the controlled agent APIs during the live UAT.
    """
    run_id = _clean_run_id(run_id)
    project_reference = f"{UAT_PREFIX}-{run_id}"
    estimate_reference = f"{project_reference}-R1"
    variant_id = f"UAT-VAR-{run_id}"
    system_id = f"UAT-SYS-{run_id}"
    pricing_entry_id = f"UAT-PKB-{run_id}"
    release_version = f"uat-{run_id}"

    if db.scalar(select(Project.id).where(Project.reference == project_reference)):
        raise ValueError(f"Reference UAT run already exists: {project_reference}")
    if db.scalar(select(TechnicalVariant.id).where(TechnicalVariant.variant_id == variant_id)):
        raise ValueError(f"Reference UAT technical variant already exists: {variant_id}")

    project = Project(
        reference=project_reference,
        name="CLASSIFIRE OpenClaw Reference UAT",
        jurisdiction="NSW/ACT, Australia",
        notes=(
            "Synthetic controlled UAT project only. It exists to validate the live "
            "CLASSIFIRE/OpenClaw agent chain and must not be treated as customer work."
        ),
    )
    db.add(project)
    db.flush()

    estimate = Estimate(
        project_id=project.id,
        revision=1,
        reference=estimate_reference,
        title="Controlled Multi-Agent Reference Estimate",
        status="draft",
        currency="AUD",
        tax_name="GST",
        tax_rate=Decimal("0.10"),
        assumptions=["Synthetic reference UAT; no customer or production scope."],
        exclusions=["Human Release is intentionally excluded from the agent chain."],
    )
    db.add(estimate)
    db.flush()

    evidence_payload = {
        "schema": "CLASSIFIRE-UAT-EVIDENCE-v1",
        "run_id": run_id,
        "project_reference": project_reference,
        "physical_scope": {
            "substrate_type": "concrete",
            "substrate_plane": "wall",
            "orientation": "vertical",
            "opening_type": "rectangular",
            "width_mm": 160,
            "height_mm": 160,
            "frl": "-/120/120",
            "service_type": "pipe",
            "service_material": "copper",
            "service_size_mm": 50,
            "service_quantity": 1,
        },
    }
    evidence = EvidenceSource(
        estimate_id=estimate.id,
        evidence_type="synthetic_reference_uat",
        source_reference=f"uat://classifire/openclaw/{run_id}",
        sha256=_sha(evidence_payload),
        evidence_class="CONTROLLED_UAT_FIXTURE",
        confidence=Decimal("1.0"),
        status="active",
        source_json=evidence_payload,
    )
    db.add(evidence)

    opening = Opening(
        estimate_id=estimate.id,
        opening_code="O-001",
        location="Synthetic UAT wall opening",
        substrate_type="concrete",
        substrate_plane="wall",
        substrate_thickness_mm=Decimal("150"),
        orientation="vertical",
        opening_type="rectangular",
        width_mm=Decimal("160"),
        height_mm=Decimal("160"),
        frl="-/120/120",
        physical_model_status="confirmed",
        technical_status="not_assessed",
    )
    db.add(opening)
    db.flush()

    service = Service(
        opening_id=opening.id,
        service_code="S-001",
        service_type="pipe",
        material="copper",
        nominal_size_mm=Decimal("50"),
        outside_diameter_mm=Decimal("50"),
        quantity=Decimal("1"),
        evidence_status="confirmed",
        confidence=Decimal("1.0"),
    )
    db.add(service)
    db.flush()
    db.add(
        ServiceOpeningLink(
            service_id=service.id,
            opening_id=opening.id,
            link_type="penetrates",
            relationship_status="confirmed",
            evidence_status="confirmed",
            confidence=Decimal("1.0"),
            source_reference=evidence.source_reference,
        )
    )
    db.flush()

    parsed_requirements = {
        "variant_id": variant_id,
        "system_id": system_id,
        "requirements": [
            {
                "requirement_id": "REQ-COLLAR-001",
                "category": "COLLAR",
                "description": "Install one controlled tested collar treatment to the copper service.",
                "source_field": "UAT_Requirement",
                "source_document_id": "UAT-DOC-001",
                "source_page": "UAT-1",
                "source_row": "UAT-R1",
                "mandatory": True,
                "exclusion": False,
            }
        ],
        "required_component_categories": ["COLLAR"],
        "required_labour_activities": [],
        "dependencies": [],
        "exclusions": ["Any non-matching service, substrate, orientation or FRL"],
        "parser_version": "CLASSIFIRE-UAT-P15-PARSER-v1",
    }
    parsed_requirements["requirements_hash"] = _sha(parsed_requirements)

    variant = TechnicalVariant(
        variant_id=variant_id,
        system_id=system_id,
        source_document_reference="UAT-DOC-001",
        source_page="UAT-1",
        manufacturer="CLASSIFIRE UAT",
        product_family="Controlled Collar Reference",
        service_type="pipe",
        service_material="copper",
        minimum_service_size_mm=Decimal("50"),
        maximum_service_size_mm=Decimal("50"),
        permitted_service_quantity="1",
        substrate_type="concrete",
        minimum_substrate_thickness_mm=Decimal("100"),
        orientation="vertical",
        opening_type="rectangular",
        component_requirements=parsed_requirements,
        labour_requirements=[],
        frl="-/120/120",
        jurisdiction="NSW/ACT, Australia",
        quality_score=Decimal("100"),
        confidence_cap=Decimal("100"),
        search_eligibility="ACTIVE",
        expert_review_required=False,
        status="active",
        source_hash=_sha({"variant": parsed_requirements, "run_id": run_id}),
        source_json={
            "uat_reference": True,
            "run_id": run_id,
            "parsed_requirements": parsed_requirements,
        },
    )
    db.add(variant)
    db.flush()
    technical_release = _release(
        db,
        library_type="technical",
        version=release_version,
        record_ids=[variant.id],
        run_id=run_id,
    )
    variant.release_id = technical_release.id

    applicability = {
        "Exact_Match_Eligible_YN": "YES",
        "Proxy_Eligible_YN": "NO",
        "Critical_Fields_Complete_YN": "YES",
        "Opening_Level_Reconciliation_Required_YN": "NO",
        "Duplicate_Recovery_Risk_Class": "LOW",
        "Package15_Variant_ID_Parsed": variant_id,
    }
    pricing = PricingLibraryRecord(
        pkb_entry_id=pricing_entry_id,
        entry_version="1",
        description="Synthetic UAT exact collar rate",
        system_description=f"Exact commercial analogue for {variant_id}",
        unit="each",
        rate_ex_tax=UAT_RATE,
        currency="AUD",
        tax_basis="GST Exclusive",
        service_type="pipe",
        service_class="pipe",
        service_material="copper",
        substrate="concrete",
        substrate_plane="wall",
        orientation="vertical",
        frl="-/120/120",
        manufacturer="CLASSIFIRE UAT",
        repair_family="controlled tested collar treatment",
        rate_inclusions={"Rate_Includes_Collar": "YES"},
        rate_exclusions={},
        applicability=applicability,
        commercial_confidence="HIGH",
        technical_status="MATCHED",
        status="active",
        source_hash=_sha({"pricing_entry_id": pricing_entry_id, "run_id": run_id}),
        source_json={
            **applicability,
            "PKB_Entry_ID": pricing_entry_id,
            "uat_reference": True,
            "run_id": run_id,
        },
    )
    db.add(pricing)
    db.flush()
    pricing_release = _release(
        db,
        library_type="pricing",
        version=release_version,
        record_ids=[pricing.id],
        run_id=run_id,
    )
    pricing.release_id = pricing_release.id

    labour = LabourComponent(
        code=f"UAT-LAB-{run_id}",
        revision=1,
        name="Unused UAT labour release anchor",
        category="uat",
        unit="person_hour",
        base_rate=Decimal("130"),
        default_hours=Decimal("0"),
        crew_size=Decimal("1"),
        status="active",
        notes="Release anchor only; the first live reference UAT has no required labour activities.",
    )
    db.add(labour)
    db.flush()
    labour_release = _release(
        db,
        library_type="labour",
        version=release_version,
        record_ids=[labour.id],
        run_id=run_id,
    )
    labour.release_id = labour_release.id

    estimate.technical_release_id = technical_release.id
    estimate.pricing_release_id = pricing_release.id
    estimate.labour_release_id = labour_release.id
    db.flush()

    physical_lock, _created = create_physical_model_lock(db, estimate)
    opening.physical_model_status = "locked"

    record_audit(
        db,
        actor=None,
        actor_type="system",
        actor_name="CLASSIFIRE reference UAT fixture generator",
        action="prepare_openclaw_reference_uat",
        entity_type="estimate",
        entity_id=estimate.id,
        project_id=project.id,
        new_value={
            "run_id": run_id,
            "project_reference": project_reference,
            "estimate_reference": estimate_reference,
            "opening_id": opening.id,
            "service_id": service.id,
            "variant_id": variant_id,
            "pricing_entry_id": pricing_entry_id,
            "physical_model_lock_id": physical_lock.id,
            "technical_release_id": technical_release.id,
            "pricing_release_id": pricing_release.id,
            "labour_release_id": labour_release.id,
        },
        reason="Prepare a synthetic governed estimate for controlled live OpenClaw multi-agent UAT",
        correlation_id=f"classifire-uat:{run_id}",
    )
    db.flush()

    assessment = assess_estimate_workflow(db, estimate)
    if assessment.stage != "opening_specific_technical_search":
        raise RuntimeError(
            "Reference UAT fixture did not stop at opening_specific_technical_search: "
            + assessment.stage
        )

    return ReferenceUatFixture(
        run_id=run_id,
        project_id=project.id,
        project_reference=project_reference,
        estimate_id=estimate.id,
        estimate_reference=estimate_reference,
        opening_id=opening.id,
        opening_code=opening.opening_code,
        service_id=service.id,
        service_code=service.service_code,
        variant_id=variant_id,
        pricing_entry_id=pricing_entry_id,
        expected_rate_ex_tax=str(UAT_RATE),
        initial_stage=assessment.stage,
    )


def inspect_reference_uat(
    db: Session,
    *,
    estimate_id: str,
    settings: Settings | None = None,
    expected_stage: str | None = None,
) -> dict[str, Any]:
    estimate = db.get(Estimate, estimate_id)
    if estimate is None:
        return {"ok": False, "errors": ["Estimate not found"], "estimate_id": estimate_id}
    project = db.get(Project, estimate.project_id)
    assessment = assess_estimate_workflow(db, estimate)
    errors: list[str] = []

    if not project or not project.reference.startswith(UAT_PREFIX + "-"):
        errors.append("Estimate is not a CLASSIFIRE OpenClaw reference UAT fixture")
    if expected_stage and assessment.stage != expected_stage:
        errors.append(f"Expected workflow stage {expected_stage!r}; found {assessment.stage!r}")

    openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)).all())
    opening_ids = [row.id for row in openings]
    components = list(
        db.scalars(
            select(SystemRequiredComponent).where(SystemRequiredComponent.opening_id.in_(opening_ids))
        ).all()
    ) if opening_ids else []
    component_ids = [row.id for row in components]
    repair_locks = list(
        db.scalars(
            select(RepairStrategyLock).where(
                RepairStrategyLock.opening_id.in_(opening_ids),
                RepairStrategyLock.invalidated_at.is_(None),
            )
        ).all()
    ) if opening_ids else []
    quantities = list(
        db.scalars(
            select(Quantity).where(
                Quantity.required_component_id.in_(component_ids),
                Quantity.status != "superseded",
            )
        ).all()
    ) if component_ids else []
    pricing_rows = list(
        db.scalars(
            select(PricingComponent).where(
                PricingComponent.estimate_id == estimate.id,
                PricingComponent.status != "superseded",
            )
        ).all()
    )
    pricing_ids = [row.id for row in pricing_rows]
    method_locks = list(
        db.scalars(select(CommercialMethodLock).where(CommercialMethodLock.component_id.in_(pricing_ids))).all()
    ) if pricing_ids else []
    gates = list(
        db.scalars(
            select(GateEvidence).where(
                GateEvidence.estimate_id == estimate.id,
                GateEvidence.gate_type == "FINAL_INDEPENDENT_VALIDATION",
            )
        ).all()
    )
    certificates = list(
        db.scalars(select(EstimateCertificate).where(EstimateCertificate.estimate_id == estimate.id)).all()
    )
    render_events = list(
        db.scalars(
            select(AuditEvent).where(
                AuditEvent.entity_type == "estimate",
                AuditEvent.entity_id == estimate.id,
                AuditEvent.action == "render_output",
            )
        ).all()
    )
    approvals = list(
        db.scalars(
            select(Approval).where(
                Approval.entity_type == "estimate",
                Approval.entity_id == estimate.id,
                Approval.approval_type.in_(["human_release", "release"]),
                Approval.status == "approved",
            )
        ).all()
    )

    stage = assessment.stage
    stages_at_or_after_technical = {
        "quantity_and_labour",
        "commercial_pricing_and_recovery",
        "independent_validation",
        "validated_snapshot",
        "output_rendering",
        "human_release",
        "complete",
    }
    stages_at_or_after_quantity = {
        "commercial_pricing_and_recovery",
        "independent_validation",
        "validated_snapshot",
        "output_rendering",
        "human_release",
        "complete",
    }
    stages_at_or_after_commercial = {
        "independent_validation",
        "validated_snapshot",
        "output_rendering",
        "human_release",
        "complete",
    }
    stages_at_or_after_validation = {
        "validated_snapshot",
        "output_rendering",
        "human_release",
        "complete",
    }

    if stage in stages_at_or_after_technical:
        if len(repair_locks) != 1 or repair_locks[0].validator_result != "PASS":
            errors.append("Expected one active PASS RepairStrategyLock")
        if len(components) != 1 or components[0].category != "COLLAR":
            errors.append("Expected exactly one Package 15-derived COLLAR component")
        elif components[0].candidate_status != "CONFIRMED_TECHNICAL_MATCH":
            errors.append("UAT COLLAR component is not a confirmed technical match")

    if stage in stages_at_or_after_quantity:
        valid_quantities = [
            row for row in quantities
            if row.status == "validated"
            and row.numeric_value == Decimal("1.000000")
            and row.unit_basis.lower() == "each"
        ]
        if len(valid_quantities) != 1:
            errors.append("Expected one validated QF-EACH quantity of 1 each")

    if stage in stages_at_or_after_commercial:
        if len(pricing_rows) != 1:
            errors.append("Expected exactly one active PricingComponent")
        else:
            row = pricing_rows[0]
            if row.status != "validated" or row.extended_cost != UAT_RATE:
                errors.append(
                    f"Expected one validated PricingComponent at {UAT_RATE}; found {row.status}/{row.extended_cost}"
                )
        if len(method_locks) != 1:
            errors.append("Expected exactly one CommercialMethodLock")
        else:
            lock = method_locks[0]
            if lock.selected_pricing_method != "Exact Library Match" or lock.validator_outcome != "PASS":
                errors.append(
                    "Commercial method must be Exact Library Match with validator outcome PASS"
                )

    if stage in stages_at_or_after_validation:
        passing = [row for row in gates if row.result == "PASS" and int(row.exception_count or 0) == 0]
        if len(passing) != 1:
            errors.append("Expected exactly one passing final independent-validation gate")

    artifact_rows: list[dict[str, Any]] = []
    if stage in {"human_release", "complete"}:
        if not estimate.snapshot_json or not estimate.snapshot_hash:
            errors.append("Validated immutable snapshot is missing")
        if len(certificates) != 1 or not certificates[0].final_certificate_hash:
            errors.append("EstimateCertificate is missing or invalid")
        current_render_events = [
            row for row in render_events
            if (row.new_value or {}).get("snapshot_hash") == estimate.snapshot_hash
        ]
        if not current_render_events:
            errors.append("No controlled render_output receipt references the current snapshot")
        if approvals:
            errors.append("Human Release must remain unapproved at the end of the agent UAT")

        if settings and estimate.snapshot_hash:
            safe_ref = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in estimate.reference)
            export_dir = settings.storage_root / "exports" / estimate.id / estimate.snapshot_hash
            expected_files = [
                export_dir / f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Technical_Estimate.xlsx",
                export_dir / f"CLASSIFIRE_{safe_ref}_R{estimate.revision}_Proposal.xlsx",
            ]
            for path in expected_files:
                exists = path.exists()
                digest = None
                if exists:
                    h = hashlib.sha256()
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            h.update(chunk)
                    digest = h.hexdigest()
                artifact_rows.append(
                    {"path": str(path), "exists": exists, "sha256": digest}
                )
                if not exists:
                    errors.append(f"Expected controlled output is missing: {path.name}")

    return {
        "ok": not errors,
        "errors": errors,
        "estimate_id": estimate.id,
        "estimate_reference": estimate.reference,
        "estimate_status": estimate.status,
        "workflow": assessment.as_dict(),
        "repair_strategy_lock_count": len(repair_locks),
        "required_components": [
            {
                "id": row.id,
                "category": row.category,
                "candidate_id": row.candidate_id,
                "candidate_status": row.candidate_status,
                "quantity_formula_id": row.quantity_formula_id,
            }
            for row in components
        ],
        "quantities": [
            {
                "id": row.id,
                "required_component_id": row.required_component_id,
                "formula_id": row.formula_id,
                "numeric_value": str(row.numeric_value) if row.numeric_value is not None else None,
                "unit_basis": row.unit_basis,
                "status": row.status,
            }
            for row in quantities
        ],
        "pricing": [
            {
                "id": row.id,
                "required_component_id": row.required_component_id,
                "rate_source": row.rate_source,
                "unit_rate": str(row.unit_rate) if row.unit_rate is not None else None,
                "extended_cost": str(row.extended_cost) if row.extended_cost is not None else None,
                "status": row.status,
            }
            for row in pricing_rows
        ],
        "commercial_methods": [
            {
                "id": row.id,
                "selected_pricing_method": row.selected_pricing_method,
                "validator_outcome": row.validator_outcome,
                "rate_applicability_result": row.rate_applicability_result,
            }
            for row in method_locks
        ],
        "validation_gates": [
            {
                "id": row.id,
                "result": row.result,
                "exception_count": row.exception_count,
                "run_id": row.run_id,
            }
            for row in gates
        ],
        "snapshot_hash": estimate.snapshot_hash,
        "certificate_hash": certificates[0].final_certificate_hash if certificates else None,
        "render_event_count": len(render_events),
        "human_release_approval_count": len(approvals),
        "artifacts": artifact_rows,
    }


__all__ = [
    "EXPECTED_FINAL_STAGE",
    "ReferenceUatFixture",
    "UAT_PREFIX",
    "UAT_RATE",
    "inspect_reference_uat",
    "prepare_reference_uat",
]
