from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import (
    Package15CandidateRequirement,
    PhysicalModelLock,
    RepairStrategy,
    RepairStrategyLock,
    SystemRequiredComponent,
)
from ..models import Estimate, Opening, TechnicalVariant
from .release_scope import ReleaseScopeError, pinned_technical_ids
from .technical import mixed_service_candidate_available, search_for_opening
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


class RepairStrategyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ParsedPackage15Requirements:
    requirements: tuple[dict[str, Any], ...]
    component_categories: tuple[str, ...]
    labour_activities: tuple[str, ...]
    dependencies: tuple[str, ...]
    exclusions: tuple[str, ...]
    parser_version: str | None
    requirements_hash: str | None


_NON_COMPONENT_CATEGORIES = {"OTHER_SYSTEM_REQUIREMENT"}


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _stable_uuid(*parts: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "quantifire:v2.13:" + ":".join(parts)))


def _norm(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", "_").replace(" ", "_")


def parse_package15_requirements(variant: TechnicalVariant) -> ParsedPackage15Requirements:
    parsed: Any = variant.component_requirements
    if not isinstance(parsed, dict):
        parsed = (variant.source_json or {}).get("parsed_requirements")
    if not isinstance(parsed, dict):
        raise RepairStrategyError(
            f"Technical variant {variant.variant_id} has no structured Package 15 parsed_requirements payload."
        )

    requirements = parsed.get("requirements") or []
    categories = parsed.get("required_component_categories") or []
    labour = parsed.get("required_labour_activities") or variant.labour_requirements or []
    dependencies = parsed.get("dependencies") or []
    exclusions = parsed.get("exclusions") or []

    if not isinstance(requirements, list) or not isinstance(categories, list):
        raise RepairStrategyError(
            f"Technical variant {variant.variant_id} has malformed Package 15 requirement structures."
        )
    if not categories:
        raise RepairStrategyError(
            f"Technical variant {variant.variant_id} does not declare required component categories."
        )

    clean_requirements = tuple(item for item in requirements if isinstance(item, dict))
    return ParsedPackage15Requirements(
        requirements=clean_requirements,
        component_categories=tuple(sorted({_norm(str(item)) for item in categories if str(item).strip()})),
        labour_activities=tuple(sorted({str(item).strip() for item in labour if str(item).strip()})),
        dependencies=tuple(str(item).strip() for item in dependencies if str(item).strip()),
        exclusions=tuple(str(item).strip() for item in exclusions if str(item).strip()),
        parser_version=str(parsed.get("parser_version")) if parsed.get("parser_version") else None,
        requirements_hash=str(parsed.get("requirements_hash")) if parsed.get("requirements_hash") else None,
    )


def _active_physical_lock(db: Session, estimate_id: str, opening_id: str) -> PhysicalModelLock:
    locks = list(
        db.scalars(
            select(PhysicalModelLock).where(
                PhysicalModelLock.estimate_id == estimate_id,
                PhysicalModelLock.invalidated_at.is_(None),
            )
        ).all()
    )
    for item in locks:
        if opening_id in (item.opening_ids or []):
            return item
    raise RepairStrategyError("No active Physical Model Lock covers this opening.")


def _candidate_search_receipt(db: Session, opening: Opening, variant: TechnicalVariant) -> dict[str, Any]:
    result = search_for_opening(db, opening, limit=100)
    hits: list[dict[str, Any]] = []
    service_count = 0
    hit_services: set[str] = set()
    for service_result in result.get("services", []):
        service_count += 1
        for candidate in service_result.get("candidates", []):
            if candidate.get("variant_id") == variant.variant_id:
                hits.append(candidate)
                hit_services.add(str(service_result.get("service_id")))

    critical_blockers = sorted(
        {
            blocker
            for hit in hits
            for blocker in hit.get("blockers", [])
            if blocker in {"critical_field_mismatch", "search_excluded"}
        }
    )
    if critical_blockers:
        raise RepairStrategyError(
            f"Technical variant {variant.variant_id} failed opening-specific applicability: "
            + ", ".join(critical_blockers)
        )

    mixed_receipt: dict[str, Any] | None = None
    supported = service_count > 0 and len(hit_services) == service_count
    if not supported and service_count > 1:
        mixed_receipt = mixed_service_candidate_available(db, opening)
        supported = any(
            item.get("variant_id") == variant.variant_id
            for item in mixed_receipt.get("candidates", [])
        )

    if not supported:
        raise RepairStrategyError(
            f"Technical variant {variant.variant_id} was not returned as an opening-specific candidate."
        )

    return {
        "opening_search": result,
        "selected_candidate_hits": hits,
        "mixed_service_receipt": mixed_receipt,
        "critical_blockers": critical_blockers,
    }


def _materialize_candidate_requirements(
    db: Session,
    opening: Opening,
    variant: TechnicalVariant,
    parsed: ParsedPackage15Requirements,
) -> list[Package15CandidateRequirement]:
    records: list[Package15CandidateRequirement] = []
    for index, requirement in enumerate(parsed.requirements, 1):
        external_id = str(requirement.get("requirement_id") or f"REQ-{index:04d}")
        record_id = _stable_uuid("candidate-requirement", opening.id, variant.variant_id, external_id)
        record = db.get(Package15CandidateRequirement, record_id)
        values = {
            "opening_id": opening.id,
            "candidate_id": variant.variant_id,
            "category": _norm(str(requirement.get("category") or "OTHER_SYSTEM_REQUIREMENT")),
            "description": str(requirement.get("description") or "").strip() or "Unstated Package 15 requirement",
            "source_field": requirement.get("source_field"),
            "source_document_id": requirement.get("source_document_id") or variant.source_document_reference,
            "source_page": requirement.get("source_page") or variant.source_page,
            "source_row": requirement.get("source_row"),
            "mandatory": bool(requirement.get("mandatory", True)),
            "exclusion": bool(requirement.get("exclusion", False)),
        }
        if record is None:
            record = Package15CandidateRequirement(id=record_id, **values)
            db.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        records.append(record)
    db.flush()
    return records


def select_repair_strategy(
    db: Session,
    opening: Opening,
    *,
    variant_id: str,
    match_classification: str = "opening_specific_candidate",
    treatment_description: str | None = None,
    assumptions: list[str] | None = None,
    limitations: list[str] | None = None,
) -> RepairStrategy:
    estimate: Estimate = opening.estimate
    require_estimate_action(db, estimate, WorkflowAction.SEARCH_TECHNICAL)
    physical_lock = _active_physical_lock(db, estimate.id, opening.id)

    allowed_ids = pinned_technical_ids(db, estimate)
    variant = db.scalar(
        select(TechnicalVariant).where(
            TechnicalVariant.id.in_(allowed_ids),
            TechnicalVariant.variant_id == variant_id,
        )
    )
    if not variant:
        raise ReleaseScopeError(
            f"Technical variant {variant_id!r} is not present in the estimate's pinned Technical release."
        )

    search_receipt = _candidate_search_receipt(db, opening, variant)
    parsed = parse_package15_requirements(variant)
    requirement_records = _materialize_candidate_requirements(db, opening, variant, parsed)

    active_lock = db.scalar(
        select(RepairStrategyLock).where(
            RepairStrategyLock.opening_id == opening.id,
            RepairStrategyLock.invalidated_at.is_(None),
        ).limit(1)
    )
    if active_lock:
        raise RepairStrategyError("Repair Strategy is already locked and cannot be changed without controlled invalidation.")

    strategy = db.scalar(
        select(RepairStrategy).where(RepairStrategy.opening_id == opening.id).order_by(RepairStrategy.created_at.desc()).limit(1)
    )
    if strategy is None:
        strategy = RepairStrategy(opening_id=opening.id)
        db.add(strategy)

    strategy.physical_model_lock_id = physical_lock.id
    strategy.candidate_id = variant.variant_id
    strategy.selected_technical_variant_id = variant.id
    strategy.package15_release_id = estimate.technical_release_id
    strategy.match_classification = match_classification
    strategy.treatment_description = treatment_description or (
        f"Package 15 technical candidate {variant.variant_id} / system {variant.system_id}"
    )
    strategy.assumptions = assumptions or []
    strategy.limitations = limitations or []
    strategy.technical_basis = {
        "system_id": variant.system_id,
        "variant_id": variant.variant_id,
        "variant_content_hash": variant.source_hash,
        "source_document_id": variant.source_document_reference,
        "source_page": variant.source_page,
        "requirements_hash": parsed.requirements_hash,
        "parser_version": parsed.parser_version,
        "required_component_categories": list(parsed.component_categories),
        "required_labour_activities": list(parsed.labour_activities),
        "dependencies": list(parsed.dependencies),
        "exclusions": list(parsed.exclusions),
        "candidate_requirement_ids": sorted(item.id for item in requirement_records),
        "expert_review_required": bool(variant.expert_review_required),
        "search_receipt": search_receipt,
    }
    strategy.status = "candidate_selected"
    opening.selected_technical_variant_id = variant.id
    opening.technical_status = "candidate_selected"
    db.flush()
    return strategy


def _labour_codes_for_category(category: str, activities: tuple[str, ...]) -> list[str]:
    category = _norm(category)
    tokens: dict[str, tuple[str, ...]] = {
        "BATT": ("BATT",),
        "MASTIC_SEALANT": ("MASTIC", "SEAL_SURFACE", "SEAL_DEPTH"),
        "PIGTAIL_FIXING": ("PIGTAIL",),
        "MECHANICAL_FIXING": ("MECHANICAL_FIXING",),
        "SUPPORT": ("SERVICE_SUPPORT",),
        "QA_DOCUMENTATION": ("INSPECTION", "PHOTOGRAPHY", "REGISTER"),
        "PREPARATION_CLEANUP": ("PREPARE_", "CLEANUP"),
        "FRAMING": ("FRAMING",),
        "WRAP_MATERIAL": ("WRAP",),
        "MORTAR": ("MORTAR",),
        "CABLE_TIE": ("CABLE_TIE", "TIE_SPACING"),
        "COLLAR": ("COLLAR",),
        "BACKING": ("BACKING",),
        "BOARD": ("BOARD",),
    }
    wanted = tokens.get(category, ())
    return sorted(
        activity
        for activity in activities
        if any(token in _norm(activity) for token in wanted)
    )


def _materialize_system_components(
    db: Session,
    opening: Opening,
    variant: TechnicalVariant,
    parsed: ParsedPackage15Requirements,
) -> list[SystemRequiredComponent]:
    components: list[SystemRequiredComponent] = []
    for category in parsed.component_categories:
        if category in _NON_COMPONENT_CATEGORIES:
            continue
        component_id = _stable_uuid("system-component", opening.id, variant.variant_id, category)
        component = db.get(SystemRequiredComponent, component_id)
        values = {
            "opening_id": opening.id,
            "service_id": None,
            "candidate_id": variant.variant_id,
            "category": category,
            "description": f"Package 15 required component category: {category}",
            "technical_requirement_id": f"P15CAT:{variant.variant_id}:{category}"[:300],
            "quantity_formula_id": None,
            "required_labour_activity_ids": _labour_codes_for_category(category, parsed.labour_activities),
            "candidate_status": "RETAINED_TECHNICAL_REQUIREMENT",
            "mandatory": True,
        }
        if component is None:
            component = SystemRequiredComponent(id=component_id, **values)
            db.add(component)
        else:
            for key, value in values.items():
                setattr(component, key, value)
        components.append(component)
    if not components:
        raise RepairStrategyError("Package 15 candidate produced no controlled SystemRequiredComponent records.")
    db.flush()
    return components


def create_repair_strategy_lock(
    db: Session,
    opening: Opening,
) -> tuple[RepairStrategyLock, bool, list[SystemRequiredComponent]]:
    estimate: Estimate = opening.estimate
    require_estimate_action(db, estimate, WorkflowAction.LOCK_REPAIR_STRATEGY)

    strategy = db.scalar(
        select(RepairStrategy).where(
            RepairStrategy.opening_id == opening.id,
            RepairStrategy.status.in_(["candidate_selected", "locked"]),
        ).order_by(RepairStrategy.created_at.desc()).limit(1)
    )
    if not strategy or not strategy.selected_technical_variant_id or not strategy.candidate_id:
        raise RepairStrategyError("A selected Package 15 Repair Strategy is required before locking.")

    physical_lock = _active_physical_lock(db, estimate.id, opening.id)
    if strategy.physical_model_lock_id != physical_lock.id:
        raise RepairStrategyError(
            "Selected Repair Strategy was derived from a superseded Physical Model Lock; rerun opening-specific technical search."
        )

    variant = db.get(TechnicalVariant, strategy.selected_technical_variant_id)
    if not variant or variant.variant_id != strategy.candidate_id:
        raise RepairStrategyError("Selected Repair Strategy technical variant is missing or inconsistent.")

    parsed = parse_package15_requirements(variant)
    components = _materialize_system_components(db, opening, variant, parsed)
    component_ids = sorted(item.id for item in components)

    technical_basis = strategy.technical_basis or {}
    search_receipt = technical_basis.get("search_receipt") or {}
    mismatches = list(search_receipt.get("critical_blockers") or [])
    unmapped_labour = sorted(
        set(parsed.labour_activities)
        - {
            activity
            for component in components
            for activity in (component.required_labour_activity_ids or [])
        }
    )
    if unmapped_labour:
        mismatches.append("Unmapped Package 15 labour activities: " + ", ".join(unmapped_labour))

    payload = {
        "schema": "QUANTIFIRE-RepairStrategyLock-v2.13",
        "opening_id": opening.id,
        "repair_strategy_id": strategy.id,
        "physical_model_lock_id": strategy.physical_model_lock_id,
        "candidate_id": variant.variant_id,
        "variant_content_hash": variant.source_hash,
        "requirements_hash": parsed.requirements_hash,
        "required_component_ids": component_ids,
        "component_rows": [
            {
                "id": item.id,
                "category": item.category,
                "technical_requirement_id": item.technical_requirement_id,
                "required_labour_activity_ids": item.required_labour_activity_ids or [],
            }
            for item in sorted(components, key=lambda row: row.id)
        ],
        "dependencies": list(parsed.dependencies),
        "mismatches": mismatches,
        "assumptions": strategy.assumptions or [],
    }
    content_hash = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()

    existing = db.scalar(
        select(RepairStrategyLock).where(
            RepairStrategyLock.opening_id == opening.id,
            RepairStrategyLock.invalidated_at.is_(None),
        ).limit(1)
    )
    if existing:
        if existing.content_hash == content_hash:
            return existing, False, components
        raise RepairStrategyError(
            "An active Repair Strategy Lock already exists with different content; controlled invalidation is required."
        )

    validator_result = "CONDITIONED" if variant.expert_review_required or mismatches else "PASS"
    lock = RepairStrategyLock(
        opening_id=opening.id,
        repair_strategy_id=strategy.id,
        candidate_id=variant.variant_id,
        candidate_status="APPROVED_WITH_EXPERT_REVIEW" if variant.expert_review_required else "APPROVED",
        required_component_ids=component_ids,
        dependencies=list(parsed.dependencies),
        mismatches=mismatches,
        assumptions=strategy.assumptions or [],
        validator_result=validator_result,
        permitted_classes=["component_derivation", "quantity_and_labour"],
        content_hash=content_hash,
        signature=None,
    )
    db.add(lock)
    strategy.status = "locked"
    opening.technical_status = "repair_strategy_locked"
    db.flush()
    return lock, True, components


__all__ = [
    "ParsedPackage15Requirements",
    "RepairStrategyError",
    "create_repair_strategy_lock",
    "parse_package15_requirements",
    "select_repair_strategy",
]
