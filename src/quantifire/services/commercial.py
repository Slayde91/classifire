from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..canonical_models import RepairStrategy, SystemRequiredComponent
from ..commercial_models import (
    CommercialMethodLock,
    CommercialRecoveryRecord,
    ComponentRequirementReconciliation,
    LabourActivity,
    PriceAnomalyReview,
    PricingComponent,
    Quantity,
)
from ..models import Estimate, LabourComponent, Opening, PricingLibraryRecord, Product, Service, TechnicalVariant
from .calculation import D, money, resolve_markup
from .release_scope import (
    ReleaseScopeError,
    pinned_labour,
    pinned_pricing_record,
    pinned_product,
    release_record_ids,
)
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


ENGINE_VERSION = "QUANTIFIRE-COMMERCIAL-ENGINE-v1.0"
MONEY = Decimal("0.01")
_VALID_INPUT_STATUSES = {"PASS"}
_YES = {"YES", "Y", "TRUE", "1", "PASS", "ELIGIBLE", "INCLUDED", "ACTIVE"}
_LOW_RISK = {"", "NONE", "LOW", "MINOR", "N/A", "NA", "NOT_APPLICABLE"}
_MATERIAL_COMPONENT_CATEGORIES = {
    "BATT",
    "BOARD",
    "MASTIC_SEALANT",
    "COLLAR",
    "WRAP_MATERIAL",
    "FRAMING",
    "MORTAR",
    "MECHANICAL_FIXING",
    "PIGTAIL_FIXING",
    "CABLE_TIE",
    "BACKING",
    "SLEEVE",
    "LABEL",
    "SUPPORT",
}

_INCLUSION_CATEGORY_MAP: dict[str, set[str]] = {
    "BOARD_BATT": {"BATT", "BOARD"},
    "BATT": {"BATT", "BOARD"},
    "BOARD": {"BOARD", "BATT"},
    "MASTIC": {"MASTIC_SEALANT"},
    "SEALANT": {"MASTIC_SEALANT"},
    "COLLAR": {"COLLAR"},
    "FRAMING": {"FRAMING"},
    "WRAP": {"WRAP_MATERIAL"},
    "MECHANICAL_FIXING": {"MECHANICAL_FIXING"},
    "PIGTAIL": {"PIGTAIL_FIXING"},
    "CABLE_TIE": {"CABLE_TIE"},
    "MORTAR": {"MORTAR"},
    "BACKING": {"BACKING"},
    "SLEEVE": {"SLEEVE"},
    "LABEL": {"LABEL"},
    "SUPPORT": {"SUPPORT"},
    "PREPARATION": {"PREPARATION_CLEANUP"},
    "QA": {"QA_DOCUMENTATION"},
}


class CommercialPricingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RateCandidateReceipt:
    record_id: str
    pkb_entry_id: str
    entry_version: str | None
    rate_ex_tax: Decimal
    unit: str
    exact_eligible: bool
    proxy_eligible: bool
    comparisons: dict[str, str]
    package15_result: str
    blockers: tuple[str, ...]
    score: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "pkb_entry_id": self.pkb_entry_id,
            "entry_version": self.entry_version,
            "rate_ex_tax": str(self.rate_ex_tax),
            "unit": self.unit,
            "exact_eligible": self.exact_eligible,
            "proxy_eligible": self.proxy_eligible,
            "comparisons": self.comparisons,
            "package15_result": self.package15_result,
            "blockers": list(self.blockers),
            "score": self.score,
        }


@dataclass(frozen=True)
class RateSelectionPlan:
    scope_key: str
    opening_id: str
    service_id: str | None
    method: str
    record: PricingLibraryRecord
    rate_quantity: Decimal
    rate_unit: str
    unit_rate: Decimal
    included_component_ids: tuple[str, ...]
    anchor_component_id: str
    applicability_result: str
    reconciliation_proof: str | None
    parameterisation_formula_id: str | None
    approval_reference: str | None
    rejected_candidates: tuple[dict[str, Any], ...]
    explicit: bool


@dataclass(frozen=True)
class ComponentCommercialPlan:
    component_id: str
    opening_id: str
    service_id: str | None
    quantity_id: str
    labour_activity_ids: tuple[str, ...]
    method: str
    component_type: str
    unit_basis: str
    unit_rate: Decimal | None
    extended_cost: Decimal | None
    rate_source: str | None
    inclusions: dict[str, Any]
    exclusions: dict[str, Any]
    confidence: str
    risk_status: str
    status: str
    recovery_status: str
    validator_outcome: str
    rate_applicability_result: str
    quantity_formula_result: str
    labour_build_result: str
    package15_basis: str
    rejected_rate_candidates: tuple[dict[str, Any], ...]
    shared_component_key: str | None
    recovery_location: str | None
    proof_reference: str | None
    reconciliation_result: str
    reconciliation_missing_status: str | None
    commercial_consequence: str | None
    provenance: dict[str, Any]


@dataclass(frozen=True)
class CommercialDerivation:
    pricing_components: tuple[PricingComponent, ...]
    method_locks: tuple[CommercialMethodLock, ...]
    recovery_records: tuple[CommercialRecoveryRecord, ...]
    reconciliations: tuple[ComponentRequirementReconciliation, ...]
    anomaly_reviews: tuple[PriceAnomalyReview, ...]


def _norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").upper()).strip("_")


def _tokens(value: Any) -> set[str]:
    tokens = {token for token in _norm(value).split("_") if token}
    singular: set[str] = set()
    for token in tokens:
        singular.add(token)
        if token.endswith("IES") and len(token) > 3:
            singular.add(token[:-3] + "Y")
        elif token.endswith("S") and len(token) > 3:
            singular.add(token[:-1])
    return singular


def _compare(project_value: Any, candidate_value: Any) -> str:
    p = _norm(project_value)
    c = _norm(candidate_value)
    if not p or not c or "NOT_STATED" in c or "UNKNOWN" in c:
        return "UNKNOWN"
    if p == c or p in c or c in p:
        return "MATCH"
    pt = _tokens(project_value)
    ct = _tokens(candidate_value)
    if pt and ct and len(pt & ct) / max(1, len(pt)) >= 0.6:
        return "MATCH"
    return "MISMATCH"


def _flag(source: dict[str, Any] | None, key: str) -> bool:
    value = (source or {}).get(key)
    return _norm(value) in _YES


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _hash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _unit_key(value: str | None) -> str:
    text = (value or "").strip().lower().replace("²", "2")
    aliases = {
        "ea": "each",
        "unit": "each",
        "units": "each",
        "sqm": "m2",
        "m^2": "m2",
        "litre": "l",
        "litres": "l",
        "liter": "l",
        "liters": "l",
        "hr": "hour",
        "hrs": "hour",
        "hours": "hour",
    }
    return aliases.get(text, text)


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _current_strategy_basis(db: Session, opening_id: str) -> tuple[RepairStrategy, str | None]:
    strategy = db.scalar(
        select(RepairStrategy)
        .where(
            RepairStrategy.opening_id == opening_id,
            RepairStrategy.status == "locked",
        )
        .order_by(RepairStrategy.created_at.desc())
        .limit(1)
    )
    if not strategy or not strategy.candidate_id:
        raise CommercialPricingError(
            f"Opening {opening_id} has no current locked Repair Strategy for Package 14 applicability."
        )
    system_id: str | None = None
    if strategy.selected_technical_variant_id:
        variant = db.get(TechnicalVariant, strategy.selected_technical_variant_id)
        if variant:
            system_id = variant.system_id
    return strategy, system_id


def _package15_result(record: PricingLibraryRecord, candidate_id: str, system_id: str | None) -> str:
    values: list[str] = []
    for source in (record.applicability or {}, record.source_json or {}):
        for key, value in source.items():
            if _norm(key).startswith("PACKAGE15") and value not in (None, ""):
                values.append(str(value))
    if not values:
        return "UNVERIFIED"
    combined = _norm(" ".join(values))
    if _norm(candidate_id) and _norm(candidate_id) in combined:
        return "MATCH"
    if system_id and _norm(system_id) in combined:
        return "MATCH"
    return "MISMATCH"


def _reconciliation_required(record: PricingLibraryRecord) -> bool:
    app = record.applicability or {}
    if _flag(app, "Opening_Level_Reconciliation_Required_YN"):
        return True
    risk = _norm(app.get("Duplicate_Recovery_Risk_Class"))
    return risk not in _LOW_RISK


def search_package14_candidates(
    db: Session,
    estimate: Estimate,
    *,
    opening: Opening,
    service: Service | None,
    limit: int = 50,
) -> list[RateCandidateReceipt]:
    allowed_ids = release_record_ids(db, estimate, "pricing")
    records = list(
        db.scalars(
            select(PricingLibraryRecord).where(PricingLibraryRecord.id.in_(allowed_ids))
        ).all()
    )
    strategy, system_id = _current_strategy_basis(db, opening.id)
    receipts: list[RateCandidateReceipt] = []
    for record in records:
        applicability = record.applicability or {}
        service_type_candidate = record.service_class or record.service_type
        comparisons = {
            "service_type": _compare(service.service_type if service else None, service_type_candidate),
            "service_material": _compare(service.material if service else None, record.service_material),
            "substrate": _compare(opening.substrate_type, record.substrate),
            "substrate_plane": _compare(opening.substrate_plane, record.substrate_plane),
            "orientation": _compare(opening.orientation, record.orientation),
            "frl": _compare(opening.frl, record.frl),
        }
        p15_result = _package15_result(record, strategy.candidate_id, system_id)
        exact_flag = _flag(applicability, "Exact_Match_Eligible_YN")
        proxy_flag = _flag(applicability, "Proxy_Eligible_YN")
        critical_complete = _flag(applicability, "Critical_Fields_Complete_YN")
        blockers: list[str] = []
        if D(record.rate_ex_tax) <= 0:
            blockers.append("non_positive_rate")
        if service is not None and comparisons["service_type"] != "MATCH":
            blockers.append("service_type_not_exact")
        if service is not None and comparisons["service_material"] != "MATCH":
            blockers.append("service_material_not_exact")
        for field in ("substrate", "substrate_plane", "orientation", "frl"):
            if comparisons[field] != "MATCH":
                blockers.append(f"{field}_not_exact")
        if p15_result != "MATCH":
            blockers.append("package15_basis_not_exact")
        if not critical_complete:
            blockers.append("critical_fields_incomplete")
        if _reconciliation_required(record):
            blockers.append("opening_reconciliation_required")
        matches = sum(value == "MATCH" for value in comparisons.values())
        receipts.append(
            RateCandidateReceipt(
                record_id=record.id,
                pkb_entry_id=record.pkb_entry_id,
                entry_version=record.entry_version,
                rate_ex_tax=D(record.rate_ex_tax),
                unit=record.unit,
                exact_eligible=exact_flag,
                proxy_eligible=proxy_flag,
                comparisons=comparisons,
                package15_result=p15_result,
                blockers=tuple(blockers),
                score=matches * 10 + (10 if p15_result == "MATCH" else 0) + (5 if exact_flag else 0),
            )
        )
    receipts.sort(key=lambda item: (item.score, item.pkb_entry_id), reverse=True)
    return receipts[:limit]


def _included_categories(record: PricingLibraryRecord) -> set[str]:
    categories: set[str] = set()
    inclusions = record.rate_inclusions or {}
    for key, value in inclusions.items():
        norm_key = _norm(key)
        if not norm_key.startswith("RATE_INCLUDES") or _norm(value) not in _YES:
            continue
        suffix = norm_key.removeprefix("RATE_INCLUDES_")
        for token, mapped in _INCLUSION_CATEGORY_MAP.items():
            if token in suffix:
                categories.update(mapped)
    batt_status = _norm(inclusions.get("Separate_Batt_Combination_Status"))
    if any(token in batt_status for token in ("INCLUDED", "COMBINED", "RECOVERED")):
        categories.update({"BATT", "BOARD"})
    return categories


def _validated_quantity(db: Session, component_id: str) -> Quantity:
    quantity = db.scalar(
        select(Quantity)
        .where(
            Quantity.required_component_id == component_id,
            Quantity.status == "validated",
        )
        .order_by(Quantity.record_version.desc(), Quantity.created_at.desc())
        .limit(1)
    )
    if not quantity or quantity.numeric_value is None:
        raise CommercialPricingError(
            f"Required component {component_id} has no validated Quantity for commercial pricing."
        )
    return quantity


def _validated_labour(db: Session, component: SystemRequiredComponent) -> list[LabourActivity]:
    required = set(component.required_labour_activity_ids or [])
    if not required:
        return []
    rows = list(
        db.scalars(
            select(LabourActivity).where(
                LabourActivity.required_component_id == component.id,
                LabourActivity.status == "validated",
            )
        ).all()
    )
    latest: dict[str, LabourActivity] = {}
    for row in sorted(rows, key=lambda item: (item.record_version, item.created_at)):
        latest[row.activity_name] = row
    missing = sorted(required - set(latest))
    if missing:
        raise CommercialPricingError(
            f"Required component {component.id} is missing validated labour activities: {', '.join(missing)}"
        )
    return [latest[name] for name in sorted(required)]


def _rate_quantity(
    record: PricingLibraryRecord,
    *,
    service: Service | None,
    anchor_quantity: Quantity,
    selection: dict[str, Any] | None,
) -> Decimal:
    if selection and selection.get("rate_quantity") is not None:
        raw = selection["rate_quantity"]
        if not isinstance(raw, dict) or "value" not in raw:
            raise CommercialPricingError("rate_quantity must be an evidence object with value, unit and validator_status.")
        if _norm(raw.get("validator_status")) not in _VALID_INPUT_STATUSES:
            raise CommercialPricingError("rate_quantity must have validator_status PASS.")
        if _unit_key(str(raw.get("unit") or "")) != _unit_key(record.unit):
            raise CommercialPricingError(
                f"Controlled rate_quantity unit {raw.get('unit')!r} does not match Package 14 unit {record.unit!r}."
            )
        value = D(raw["value"])
        if value <= 0:
            raise CommercialPricingError("rate_quantity must be positive.")
        return value
    if _unit_key(record.unit) == _unit_key(anchor_quantity.unit_basis):
        return D(anchor_quantity.numeric_value)
    if _unit_key(record.unit) == "each":
        if service is not None and service.quantity is not None:
            return D(service.quantity)
        return Decimal("1")
    raise CommercialPricingError(
        f"Package 14 unit {record.unit!r} does not match validated component quantity unit "
        f"{anchor_quantity.unit_basis!r}; a controlled rate_quantity is required."
    )


def _scope_key(opening_id: str, service_id: str | None) -> str:
    return f"service:{service_id}" if service_id else f"opening:{opening_id}"


def _scope_components(
    components: list[SystemRequiredComponent], opening_id: str, service_id: str | None
) -> list[SystemRequiredComponent]:
    return [
        item
        for item in components
        if item.opening_id == opening_id and item.service_id == service_id
    ]


def _shared_components(components: list[SystemRequiredComponent], opening_id: str) -> list[SystemRequiredComponent]:
    return [item for item in components if item.opening_id == opening_id and item.service_id is None]


def _build_inclusion_ids(
    record: PricingLibraryRecord,
    *,
    anchor: SystemRequiredComponent,
    service_components: list[SystemRequiredComponent],
    shared_components: list[SystemRequiredComponent],
    selection: dict[str, Any] | None,
) -> tuple[str, ...]:
    allowed_categories = _included_categories(record)
    explicit = selection.get("included_required_component_ids") if selection else None
    available = {item.id: item for item in [*service_components, *shared_components]}
    if explicit is not None:
        ids = {str(item) for item in explicit}
        ids.add(anchor.id)
        unknown = ids - set(available)
        if unknown:
            raise CommercialPricingError(
                "Library-rate inclusion ledger references components outside the rate scope: "
                + ", ".join(sorted(unknown))
            )
        invalid = sorted(
            component_id
            for component_id in ids
            if component_id != anchor.id and available[component_id].category not in allowed_categories
        )
        if invalid:
            raise CommercialPricingError(
                "Package 14 inclusion flags do not support recovery of required component IDs: "
                + ", ".join(invalid)
            )
        return tuple(sorted(ids))

    ids = {anchor.id}
    for category in sorted(allowed_categories):
        matches = [
            item
            for item in [*service_components, *shared_components]
            if item.category == category and item.id != anchor.id
        ]
        if len(matches) > 1:
            raise CommercialPricingError(
                f"Package 14 rate {record.pkb_entry_id} includes category {category}, but multiple "
                "technical requirements exist. Supply an explicit included_required_component_ids ledger."
            )
        if len(matches) == 1:
            ids.add(matches[0].id)
    return tuple(sorted(ids))


def _select_rate_plan(
    db: Session,
    estimate: Estimate,
    *,
    opening: Opening,
    service: Service,
    service_components: list[SystemRequiredComponent],
    shared_components: list[SystemRequiredComponent],
    library_selection: dict[str, Any] | None,
    parameterised_selection: dict[str, Any] | None,
) -> RateSelectionPlan | None:
    scope = _scope_key(opening.id, service.id)
    receipts = search_package14_candidates(db, estimate, opening=opening, service=service, limit=200)
    by_pkb = {item.pkb_entry_id: item for item in receipts}
    rejected = tuple(item.as_dict() for item in receipts[:25])

    selected_receipt: RateCandidateReceipt | None = None
    explicit = False
    reconciliation_proof: str | None = None
    if library_selection:
        explicit = True
        pkb_entry_id = str(library_selection.get("pkb_entry_id") or "")
        selected_receipt = by_pkb.get(pkb_entry_id)
        if not selected_receipt:
            raise CommercialPricingError(
                f"Selected Package 14 rate {pkb_entry_id!r} is not present in the pinned Pricing release/search scope."
            )
        reconciliation_proof = str(library_selection.get("reconciliation_proof") or "") or None
        blockers = list(selected_receipt.blockers)
        if reconciliation_proof:
            blockers = [item for item in blockers if item != "opening_reconciliation_required"]
        if not selected_receipt.exact_eligible:
            blockers.append("exact_match_not_eligible")
        if blockers:
            raise CommercialPricingError(
                f"Selected Package 14 exact rate {pkb_entry_id} failed applicability: " + ", ".join(sorted(set(blockers)))
            )
    else:
        eligible = [item for item in receipts if item.exact_eligible and not item.blockers]
        if len(eligible) > 1:
            raise CommercialPricingError(
                f"Multiple exact Package 14 matches exist for {scope}; explicit selection is required: "
                + ", ".join(item.pkb_entry_id for item in eligible[:10])
            )
        if len(eligible) == 1:
            selected_receipt = eligible[0]

    method = "Exact Library Match"
    unit_rate: Decimal | None = None
    parameterisation_formula_id: str | None = None
    approval_reference: str | None = None
    selection = library_selection

    if selected_receipt is None and parameterised_selection:
        explicit = True
        pkb_entry_id = str(parameterised_selection.get("pkb_entry_id") or "")
        selected_receipt = by_pkb.get(pkb_entry_id)
        if not selected_receipt:
            raise CommercialPricingError(
                f"Parameterised Package 14 basis {pkb_entry_id!r} is not present in the pinned Pricing release/search scope."
            )
        hard_blockers = [
            item
            for item in selected_receipt.blockers
            if item not in {"critical_fields_incomplete", "opening_reconciliation_required"}
        ]
        reconciliation_proof = str(parameterised_selection.get("reconciliation_proof") or "") or None
        if reconciliation_proof:
            hard_blockers = [item for item in hard_blockers if item != "opening_reconciliation_required"]
        if not selected_receipt.proxy_eligible:
            hard_blockers.append("proxy_not_eligible")
        parameterisation_formula_id = str(parameterised_selection.get("parameterisation_formula_id") or "") or None
        approval_reference = str(parameterised_selection.get("approval_reference") or "") or None
        if not parameterisation_formula_id:
            hard_blockers.append("missing_parameterisation_formula_id")
        if not approval_reference:
            hard_blockers.append("missing_parameterisation_approval_reference")
        if _norm(parameterised_selection.get("validator_status")) != "PASS":
            hard_blockers.append("parameterised_rate_not_validated")
        unit_rate = D(parameterised_selection.get("unit_rate"))
        if unit_rate <= 0:
            hard_blockers.append("non_positive_parameterised_rate")
        if hard_blockers:
            raise CommercialPricingError(
                f"Approved Parameterised Match {pkb_entry_id} failed: " + ", ".join(sorted(set(hard_blockers)))
            )
        method = "Approved Parameterised Library Match"
        selection = parameterised_selection

    if selected_receipt is None:
        return None

    record = pinned_pricing_record(db, estimate, selected_receipt.pkb_entry_id)
    anchor_id = str((selection or {}).get("anchor_required_component_id") or "")
    service_ids = {item.id for item in service_components}
    if anchor_id:
        if anchor_id not in service_ids:
            raise CommercialPricingError(
                f"Library-rate anchor {anchor_id} must be a service-specific required component within {scope}."
            )
        anchor = next(item for item in service_components if item.id == anchor_id)
    else:
        if not service_components:
            raise CommercialPricingError(f"No service-specific required component exists to anchor {scope}.")
        anchor = sorted(service_components, key=lambda item: item.id)[0]

    anchor_quantity = _validated_quantity(db, anchor.id)
    rate_quantity = _rate_quantity(
        record,
        service=service,
        anchor_quantity=anchor_quantity,
        selection=selection,
    )
    included_ids = _build_inclusion_ids(
        record,
        anchor=anchor,
        service_components=service_components,
        shared_components=shared_components,
        selection=selection,
    )
    return RateSelectionPlan(
        scope_key=scope,
        opening_id=opening.id,
        service_id=service.id,
        method=method,
        record=record,
        rate_quantity=rate_quantity,
        rate_unit=record.unit,
        unit_rate=unit_rate if unit_rate is not None else D(record.rate_ex_tax),
        included_component_ids=included_ids,
        anchor_component_id=anchor.id,
        applicability_result=(
            "PASS_PARAMETERISED" if method.startswith("Approved Parameterised") else "PASS_EXACT"
        ),
        reconciliation_proof=reconciliation_proof,
        parameterisation_formula_id=parameterisation_formula_id,
        approval_reference=approval_reference,
        rejected_candidates=rejected,
        explicit=explicit,
    )


def _component_build_plan(
    db: Session,
    estimate: Estimate,
    component: SystemRequiredComponent,
    quantity: Quantity,
    labour_rows: list[LabourActivity],
    payload: dict[str, Any] | None,
    rejected: tuple[dict[str, Any], ...],
) -> ComponentCommercialPlan | None:
    if not payload:
        return None
    if _norm(payload.get("validator_status")) != "PASS":
        raise CommercialPricingError(
            f"Component-built pricing input for {component.id} must have validator_status PASS."
        )
    product: Product | None = None
    product_sku = str(payload.get("product_sku") or "") or None
    if component.category in _MATERIAL_COMPONENT_CATEGORIES and not product_sku:
        return None
    material_base = Decimal("0")
    material_sell = Decimal("0")
    material_markup = Decimal("0")
    material_markup_source: str | None = None
    product_rate_source: str | None = None
    if product_sku:
        product = pinned_product(db, estimate, product_sku)
        if _unit_key(product.unit) != _unit_key(quantity.unit_basis):
            raise CommercialPricingError(
                f"Pinned Product {product.sku} uses unit {product.unit!r}, but required component {component.id} "
                f"uses validated quantity unit {quantity.unit_basis!r}."
            )
        material_base = D(quantity.numeric_value) * D(product.base_cost)
        decision = resolve_markup(
            db,
            estimate=estimate,
            component_type=(product.item_type if product.item_type in {"product", "material"} else "material"),
            item=product,
            category=product.category,
        )
        material_markup = decision.value
        material_markup_source = decision.source
        material_sell = material_base * (Decimal("1") + material_markup)
        product_rate_source = f"product:{product.sku}:r{product.revision}"

    mappings = payload.get("labour_codes") or {}
    if not isinstance(mappings, dict):
        raise CommercialPricingError("labour_codes must map Package 15 labour activity IDs to LabourComponent codes.")
    labour_breakdown: list[dict[str, Any]] = []
    labour_sell = Decimal("0")
    for labour in labour_rows:
        code = str(mappings.get(labour.activity_name) or "")
        if not code:
            return None
        rate_record: LabourComponent = pinned_labour(db, estimate, code)
        decision = resolve_markup(
            db,
            estimate=estimate,
            component_type="labour",
            category=rate_record.category,
        )
        hours = D(labour.labour_quantity_hours)
        base = hours * D(rate_record.base_rate)
        sell = base * (Decimal("1") + decision.value)
        labour_sell += sell
        labour_breakdown.append(
            {
                "activity_name": labour.activity_name,
                "labour_activity_id": labour.id,
                "labour_code": rate_record.code,
                "labour_revision": rate_record.revision,
                "person_hours": str(hours),
                "base_rate": str(rate_record.base_rate),
                "base_cost": str(_money(base)),
                "markup": str(decision.value),
                "markup_source": decision.source,
                "sell_ex_tax": str(_money(sell)),
            }
        )

    if product is None and not labour_rows:
        return None
    extended = _money(material_sell + labour_sell)
    qty = D(quantity.numeric_value)
    unit_rate = _money(extended / qty) if qty > 0 else extended
    package15_basis = f"{component.candidate_id}:{component.technical_requirement_id or component.id}"
    provenance = {
        "engine_version": ENGINE_VERSION,
        "method": "Component-Built Price",
        "required_component_id": component.id,
        "quantity_id": quantity.id,
        "quantity": str(quantity.numeric_value),
        "quantity_unit": quantity.unit_basis,
        "product": (
            {
                "sku": product.sku,
                "revision": product.revision,
                "base_cost": str(product.base_cost),
                "base_extended_cost": str(_money(material_base)),
                "markup": str(material_markup),
                "markup_source": material_markup_source,
                "sell_ex_tax": str(_money(material_sell)),
            }
            if product
            else None
        ),
        "labour": labour_breakdown,
        "extended_sell_ex_tax": str(extended),
    }
    provenance["record_hash"] = _hash(provenance)
    return ComponentCommercialPlan(
        component_id=component.id,
        opening_id=component.opening_id,
        service_id=component.service_id,
        quantity_id=quantity.id,
        labour_activity_ids=tuple(item.id for item in labour_rows),
        method="Component-Built Price",
        component_type="component_built",
        unit_basis=quantity.unit_basis,
        unit_rate=unit_rate,
        extended_cost=extended,
        rate_source=product_rate_source or "pinned_labour_release",
        inclusions={"product_sku": product.sku if product else None, "labour": labour_breakdown},
        exclusions={},
        confidence="CONTROLLED",
        risk_status="CONTROLLED",
        status="validated",
        recovery_status="Recovered — Component-Built",
        validator_outcome="PASS",
        rate_applicability_result="NO_VALID_LIBRARY_MATCH_COMPONENT_BUILT",
        quantity_formula_result=f"PASS:{quantity.formula_id or quantity.source_method or 'validated_quantity'}",
        labour_build_result="PASS",
        package15_basis=package15_basis,
        rejected_rate_candidates=rejected,
        shared_component_key=None,
        recovery_location=f"required_component:{component.id}",
        proof_reference=str(payload.get("proof_reference") or "") or None,
        reconciliation_result="PASS",
        reconciliation_missing_status=None,
        commercial_consequence=None,
        provenance=provenance,
    )


def _expert_plan(
    component: SystemRequiredComponent,
    quantity: Quantity,
    labour_rows: list[LabourActivity],
    payload: dict[str, Any] | None,
    rejected: tuple[dict[str, Any], ...],
) -> ComponentCommercialPlan | None:
    if not payload:
        return None
    blockers: list[str] = []
    if _norm(payload.get("validator_status")) != "PASS":
        blockers.append("expert_estimate_not_validated")
    rationale = str(payload.get("rationale") or "").strip()
    if not rationale:
        blockers.append("missing_rationale")
    evidence_reference = str(payload.get("evidence_reference") or "").strip()
    if not evidence_reference:
        blockers.append("missing_evidence_reference")
    unit_rate = D(payload.get("unit_rate"))
    if unit_rate <= 0:
        blockers.append("non_positive_unit_rate")
    if blockers:
        raise CommercialPricingError(
            f"Expert estimate input for {component.id} failed: " + ", ".join(blockers)
        )
    qty = D(quantity.numeric_value)
    extended = _money(qty * unit_rate)
    provenance = {
        "engine_version": ENGINE_VERSION,
        "method": "Expert Estimate",
        "required_component_id": component.id,
        "quantity_id": quantity.id,
        "quantity": str(qty),
        "quantity_unit": quantity.unit_basis,
        "unit_rate": str(unit_rate),
        "extended_sell_ex_tax": str(extended),
        "rationale": rationale,
        "evidence_reference": evidence_reference,
    }
    provenance["record_hash"] = _hash(provenance)
    return ComponentCommercialPlan(
        component_id=component.id,
        opening_id=component.opening_id,
        service_id=component.service_id,
        quantity_id=quantity.id,
        labour_activity_ids=tuple(item.id for item in labour_rows),
        method="Expert Estimate",
        component_type="expert_estimate",
        unit_basis=quantity.unit_basis,
        unit_rate=unit_rate,
        extended_cost=extended,
        rate_source=f"expert_estimate:{evidence_reference}",
        inclusions={"rationale": rationale},
        exclusions={},
        confidence="PROVISIONAL",
        risk_status="REVIEW_REQUIRED",
        status="provisional",
        recovery_status="Recovered — Expert Estimate",
        validator_outcome="PROVISIONAL",
        rate_applicability_result="NO_VALID_HIGHER_METHOD_EXPERT_ESTIMATE",
        quantity_formula_result=f"PASS:{quantity.formula_id or quantity.source_method or 'validated_quantity'}",
        labour_build_result="PASS" if all(item.status == "validated" for item in labour_rows) else "PROVISIONAL",
        package15_basis=f"{component.candidate_id}:{component.technical_requirement_id or component.id}",
        rejected_rate_candidates=rejected,
        shared_component_key=None,
        recovery_location=f"required_component:{component.id}",
        proof_reference=evidence_reference,
        reconciliation_result="PROVISIONAL",
        reconciliation_missing_status=None,
        commercial_consequence="Expert estimate requires independent commercial review.",
        provenance=provenance,
    )


def _not_priced_plan(
    component: SystemRequiredComponent,
    quantity: Quantity,
    labour_rows: list[LabourActivity],
    rejected: tuple[dict[str, Any], ...],
    reason: str,
) -> ComponentCommercialPlan:
    provenance = {
        "engine_version": ENGINE_VERSION,
        "method": "Not Priced",
        "required_component_id": component.id,
        "reason": reason,
    }
    provenance["record_hash"] = _hash(provenance)
    return ComponentCommercialPlan(
        component_id=component.id,
        opening_id=component.opening_id,
        service_id=component.service_id,
        quantity_id=quantity.id,
        labour_activity_ids=tuple(item.id for item in labour_rows),
        method="Not Priced",
        component_type="not_priced",
        unit_basis=quantity.unit_basis,
        unit_rate=None,
        extended_cost=None,
        rate_source=None,
        inclusions={},
        exclusions={"reason": reason},
        confidence="UNPRICED",
        risk_status="BLOCKING_REVIEW",
        status="not_priced",
        recovery_status="Not Priced — Missing Valid Method",
        validator_outcome="NOT PRICED",
        rate_applicability_result="NO_VALID_METHOD",
        quantity_formula_result=f"PASS:{quantity.formula_id or quantity.source_method or 'validated_quantity'}",
        labour_build_result="PASS" if all(item.status == "validated" for item in labour_rows) else "PROVISIONAL",
        package15_basis=f"{component.candidate_id}:{component.technical_requirement_id or component.id}",
        rejected_rate_candidates=rejected,
        shared_component_key=None,
        recovery_location=f"required_component:{component.id}",
        proof_reference=None,
        reconciliation_result="PROVISIONAL",
        reconciliation_missing_status="Not Priced — Missing Valid Method",
        commercial_consequence="Component remains unpriced and must block uncontrolled release.",
        provenance=provenance,
    )


def _rate_component_plans(
    rate_plan: RateSelectionPlan,
    components_by_id: dict[str, SystemRequiredComponent],
    quantities: dict[str, Quantity],
    labour: dict[str, list[LabourActivity]],
) -> list[ComponentCommercialPlan]:
    result: list[ComponentCommercialPlan] = []
    total = _money(rate_plan.rate_quantity * rate_plan.unit_rate)
    anchor_key = f"rate_anchor:{rate_plan.scope_key}:{rate_plan.record.pkb_entry_id}"
    for component_id in rate_plan.included_component_ids:
        component = components_by_id[component_id]
        quantity = quantities[component_id]
        labour_rows = labour[component_id]
        anchor = component_id == rate_plan.anchor_component_id
        amount = total if anchor else Decimal("0")
        rate_source = (
            f"pricing_release:{rate_plan.record.pkb_entry_id}:{rate_plan.record.entry_version or 'unversioned'}"
        )
        provenance = {
            "engine_version": ENGINE_VERSION,
            "method": rate_plan.method,
            "scope_key": rate_plan.scope_key,
            "required_component_id": component.id,
            "package14_record_id": rate_plan.record.id,
            "pkb_entry_id": rate_plan.record.pkb_entry_id,
            "entry_version": rate_plan.record.entry_version,
            "rate_quantity": str(rate_plan.rate_quantity),
            "rate_unit": rate_plan.rate_unit,
            "unit_rate": str(rate_plan.unit_rate),
            "treatment_extended_sell_ex_tax": str(total),
            "anchor_required_component_id": rate_plan.anchor_component_id,
            "included_required_component_ids": list(rate_plan.included_component_ids),
            "covered_by_anchor": not anchor,
            "reconciliation_proof": rate_plan.reconciliation_proof,
            "parameterisation_formula_id": rate_plan.parameterisation_formula_id,
            "approval_reference": rate_plan.approval_reference,
            "raw_rate_inclusions": rate_plan.record.rate_inclusions or {},
        }
        provenance["record_hash"] = _hash(provenance)
        result.append(
            ComponentCommercialPlan(
                component_id=component.id,
                opening_id=component.opening_id,
                service_id=component.service_id,
                quantity_id=quantity.id,
                labour_activity_ids=tuple(item.id for item in labour_rows),
                method=rate_plan.method,
                component_type=("library_rate_anchor" if anchor else "covered_by_library_rate"),
                unit_basis=rate_plan.rate_unit if anchor else quantity.unit_basis,
                unit_rate=rate_plan.unit_rate if anchor else Decimal("0"),
                extended_cost=amount,
                rate_source=rate_source,
                inclusions={
                    "anchor_required_component_id": rate_plan.anchor_component_id,
                    "included_required_component_ids": list(rate_plan.included_component_ids),
                    "raw_rate_inclusions": rate_plan.record.rate_inclusions or {},
                },
                exclusions=rate_plan.record.rate_exclusions or {},
                confidence=rate_plan.record.commercial_confidence or "CONTROLLED",
                risk_status="CONTROLLED" if rate_plan.method == "Exact Library Match" else "REVIEWED_PARAMETERISED",
                status="validated",
                recovery_status=(
                    "Recovered — Exact Library Match"
                    if rate_plan.method == "Exact Library Match"
                    else "Recovered — Approved Parameterised Match"
                ),
                validator_outcome="PASS",
                rate_applicability_result=rate_plan.applicability_result,
                quantity_formula_result=f"PASS:{quantity.formula_id or quantity.source_method or 'validated_quantity'}",
                labour_build_result="INCLUDED_IN_LIBRARY_RATE" if labour_rows else "NOT_REQUIRED",
                package15_basis=f"{component.candidate_id}:{component.technical_requirement_id or component.id}",
                rejected_rate_candidates=rate_plan.rejected_candidates,
                shared_component_key=anchor_key,
                recovery_location=(
                    f"library_rate_anchor:{rate_plan.anchor_component_id}"
                    if anchor
                    else f"included_in_library_rate:{rate_plan.anchor_component_id}"
                ),
                proof_reference=rate_plan.reconciliation_proof or rate_plan.approval_reference,
                reconciliation_result="PASS",
                reconciliation_missing_status=None,
                commercial_consequence=None,
                provenance=provenance,
            )
        )
    return result


def _persist_component_plan(
    db: Session,
    estimate: Estimate,
    plan: ComponentCommercialPlan,
) -> tuple[PricingComponent, CommercialMethodLock, CommercialRecoveryRecord, ComponentRequirementReconciliation]:
    existing_rows = list(
        db.scalars(
            select(PricingComponent).where(
                PricingComponent.required_component_id == plan.component_id,
                PricingComponent.status != "superseded",
            )
        ).all()
    )
    record_hash = str(plan.provenance.get("record_hash") or _hash(plan.provenance))
    pricing: PricingComponent | None = None
    for row in existing_rows:
        if (row.provenance or {}).get("record_hash") == record_hash:
            pricing = row
            break
    if pricing is None:
        for row in existing_rows:
            row.status = "superseded"
            for recovery in db.scalars(
                select(CommercialRecoveryRecord).where(
                    CommercialRecoveryRecord.component_id == row.id,
                    CommercialRecoveryRecord.active.is_(True),
                )
            ).all():
                recovery.active = False
        pricing = PricingComponent(
            project_id=estimate.project_id,
            estimate_id=estimate.id,
            opening_id=plan.opening_id,
            service_id=plan.service_id,
            required_component_id=plan.component_id,
            quantity_id=plan.quantity_id,
            component_type=plan.component_type,
            scope_description=f"Commercial recovery for required component {plan.component_id}",
            unit_basis=plan.unit_basis,
            rate_source=plan.rate_source,
            unit_rate=plan.unit_rate,
            extended_cost=plan.extended_cost,
            inclusions=plan.inclusions,
            exclusions=plan.exclusions,
            confidence=plan.confidence,
            risk_status=plan.risk_status,
            status=plan.status,
            source_reference=plan.proof_reference,
            provenance=plan.provenance,
        )
        db.add(pricing)
        db.flush()

    lock_payload = {
        "pricing_component_id": pricing.id,
        "required_component_id": plan.component_id,
        "selected_pricing_method": plan.method,
        "rate_source": plan.rate_source,
        "unit_rate": str(plan.unit_rate) if plan.unit_rate is not None else None,
        "extended_cost": str(plan.extended_cost) if plan.extended_cost is not None else None,
        "recovery_status": plan.recovery_status,
        "rate_applicability_result": plan.rate_applicability_result,
        "quantity_formula_result": plan.quantity_formula_result,
        "labour_build_result": plan.labour_build_result,
        "package15_basis": plan.package15_basis,
        "record_hash": record_hash,
    }
    lock_hash = _hash(lock_payload)
    method_lock = db.scalar(
        select(CommercialMethodLock).where(CommercialMethodLock.content_hash == lock_hash)
    )
    if method_lock is None:
        method_lock = CommercialMethodLock(
            component_id=pricing.id,
            library_search_completed=True,
            exact_library_match_found=(plan.method == "Exact Library Match"),
            parameterised_rate_found=(plan.method == "Approved Parameterised Library Match"),
            component_build_completed=(plan.method == "Component-Built Price"),
            expert_estimate_required=(plan.method in {"Expert Estimate", "Not Priced"}),
            selected_pricing_method=plan.method,
            rejected_rate_candidates=list(plan.rejected_rate_candidates),
            package15_basis=plan.package15_basis,
            rate_applicability_result=plan.rate_applicability_result,
            quantity_formula_result=plan.quantity_formula_result,
            labour_build_result=plan.labour_build_result,
            recovery_status=plan.recovery_status,
            provisional_status=("PROVISIONAL" if plan.validator_outcome == "PROVISIONAL" else None),
            anomaly_result="PENDING",
            validator_outcome=plan.validator_outcome,
            content_hash=lock_hash,
        )
        db.add(method_lock)

    recovery = db.scalar(
        select(CommercialRecoveryRecord).where(
            CommercialRecoveryRecord.component_id == pricing.id,
            CommercialRecoveryRecord.active.is_(True),
        )
    )
    if recovery is None:
        recovery = CommercialRecoveryRecord(
            component_id=pricing.id,
            recovery_status=plan.recovery_status,
            economic_activity_key=f"required_component:{plan.component_id}",
            shared_component_key=plan.shared_component_key,
            recovery_location=plan.recovery_location,
            allocated_amount_aud_ex_gst=plan.extended_cost,
            active=True,
            provenance=_canonical(plan.provenance),
            proof_record_id=plan.proof_reference,
        )
        db.add(recovery)
    else:
        recovery.recovery_status = plan.recovery_status
        recovery.shared_component_key = plan.shared_component_key
        recovery.recovery_location = plan.recovery_location
        recovery.allocated_amount_aud_ex_gst = plan.extended_cost
        recovery.provenance = _canonical(plan.provenance)
        recovery.proof_record_id = plan.proof_reference

    reconciliation = db.scalar(
        select(ComponentRequirementReconciliation).where(
            ComponentRequirementReconciliation.required_component_id == plan.component_id
        )
    )
    if reconciliation is None:
        reconciliation = ComponentRequirementReconciliation(
            opening_id=plan.opening_id,
            required_component_id=plan.component_id,
            generated_component_id=pricing.id,
            quantity_record_id=plan.quantity_id,
            labour_activity_ids=list(plan.labour_activity_ids),
            recovery_status=plan.recovery_status,
            missing_status=plan.reconciliation_missing_status,
            technical_consequence=None,
            commercial_consequence=plan.commercial_consequence,
            result=plan.reconciliation_result,
        )
        db.add(reconciliation)
    else:
        reconciliation.opening_id = plan.opening_id
        reconciliation.generated_component_id = pricing.id
        reconciliation.quantity_record_id = plan.quantity_id
        reconciliation.labour_activity_ids = list(plan.labour_activity_ids)
        reconciliation.recovery_status = plan.recovery_status
        reconciliation.missing_status = plan.reconciliation_missing_status
        reconciliation.commercial_consequence = plan.commercial_consequence
        reconciliation.result = plan.reconciliation_result
    db.flush()
    return pricing, method_lock, recovery, reconciliation


def _price_anomaly_reviews(
    db: Session,
    estimate: Estimate,
    pricing_components: list[PricingComponent],
    method_locks: list[CommercialMethodLock],
) -> list[PriceAnomalyReview]:
    positive = [
        item
        for item in pricing_components
        if item.extended_cost is not None and D(item.extended_cost) > 0 and item.status != "superseded"
    ]
    groups: dict[str, list[PricingComponent]] = {}
    for item in positive:
        groups.setdefault(str(_money(D(item.extended_cost))), []).append(item)
    reviews: list[PriceAnomalyReview] = []
    lock_by_component = {item.component_id: item for item in method_locks}
    for price, rows in groups.items():
        if len(rows) < 2:
            continue
        signatures = [
            f"{item.opening_id}|{item.service_id}|{item.required_component_id}|{item.component_type}|{item.rate_source}|{item.unit_basis}"
            for item in rows
        ]
        distinct = len(set(signatures)) > 1
        result = "REVIEW REQUIRED" if distinct else "PASS — CANONICAL SCOPE MATCH"
        review = PriceAnomalyReview(
            estimate_id=estimate.id,
            comparison_type="equal_price_distinct_scope",
            subject_ids=[item.id for item in rows],
            canonical_signatures=signatures,
            prices=[price for _ in rows],
            physical_differences=signatures if distinct else [],
            documented_fixed_reason=None,
            result=result,
            required_action=(
                "Review equal prices across physically/commercially distinct scope before final validation."
                if distinct
                else None
            ),
        )
        db.add(review)
        reviews.append(review)
        if distinct:
            for item in rows:
                lock = lock_by_component.get(item.id)
                if lock and lock.validator_outcome == "PASS":
                    lock.validator_outcome = "PROVISIONAL"
                    lock.anomaly_result = "REVIEW_REQUIRED"
        else:
            for item in rows:
                lock = lock_by_component.get(item.id)
                if lock:
                    lock.anomaly_result = "PASS"
    db.flush()
    return reviews


def derive_commercial_pricing(
    db: Session,
    estimate: Estimate,
    *,
    library_selections: dict[str, dict[str, Any]] | None = None,
    parameterised_selections: dict[str, dict[str, Any]] | None = None,
    component_builds: dict[str, dict[str, Any]] | None = None,
    expert_estimates: dict[str, dict[str, Any]] | None = None,
) -> CommercialDerivation:
    """Execute the v2.13 commercial hierarchy on canonical component records.

    Hierarchy per recoverable scope/component:
    Exact Library Match -> Approved Parameterised Library Match -> Component-Built Price
    -> Expert Estimate -> Not Priced.

    Package 14 never creates technical scope. It may only value requirements already
    retained by the locked Package 15 repair strategy.
    """
    require_estimate_action(db, estimate, WorkflowAction.PRICE_AND_RECOVER)
    library_selections = library_selections or {}
    parameterised_selections = parameterised_selections or {}
    component_builds = component_builds or {}
    expert_estimates = expert_estimates or {}

    openings = list(db.scalars(select(Opening).where(Opening.estimate_id == estimate.id)).all())
    opening_by_id = {item.id: item for item in openings}
    services = list(
        db.scalars(
            select(Service).where(Service.opening_id.in_([item.id for item in openings]))
        ).all()
    ) if openings else []
    service_by_id = {item.id: item for item in services}
    components = list(
        db.scalars(
            select(SystemRequiredComponent).where(
                SystemRequiredComponent.opening_id.in_([item.id for item in openings])
            )
        ).all()
    ) if openings else []
    if not components:
        raise CommercialPricingError("Estimate has no SystemRequiredComponent records for commercial pricing.")
    components_by_id = {item.id: item for item in components}

    quantities: dict[str, Quantity] = {}
    labour: dict[str, list[LabourActivity]] = {}
    for component in components:
        quantities[component.id] = _validated_quantity(db, component.id)
        labour[component.id] = _validated_labour(db, component)

    # Select at most one treatment-level Package 14 rate per service scope.
    rate_plans: dict[str, RateSelectionPlan] = {}
    scope_rejections: dict[str, list[dict[str, Any]]] = {}
    for service in sorted(services, key=lambda item: item.id):
        opening = opening_by_id[service.opening_id]
        service_components = _scope_components(components, opening.id, service.id)
        if not service_components:
            continue
        shared = _shared_components(components, opening.id)
        scope = _scope_key(opening.id, service.id)
        try:
            selected = _select_rate_plan(
                db,
                estimate,
                opening=opening,
                service=service,
                service_components=service_components,
                shared_components=shared,
                library_selection=library_selections.get(scope),
                parameterised_selection=parameterised_selections.get(scope),
            )
        except (CommercialPricingError, ReleaseScopeError):
            raise
        if selected:
            rate_plans[scope] = selected
        else:
            receipts = search_package14_candidates(db, estimate, opening=opening, service=service, limit=25)
            scope_rejections[scope] = [item.as_dict() for item in receipts]

    # Prevent hidden duplicate recovery where multiple treatment-level rates claim
    # the same shared opening component. Deterministically keep the first automatic
    # exact rate and reject later automatic exact rates. Explicit selections conflict
    # hard so a reviewer must correct the ledger rather than receiving a silent credit.
    claims: dict[str, list[str]] = {}
    for scope, plan in rate_plans.items():
        for component_id in plan.included_component_ids:
            if components_by_id[component_id].service_id is None:
                claims.setdefault(component_id, []).append(scope)
    rejected_scopes: set[str] = set()
    for component_id, scopes in claims.items():
        if len(scopes) <= 1:
            continue
        ordered = sorted(scopes)
        explicit = [scope for scope in ordered if rate_plans[scope].explicit]
        if explicit:
            raise CommercialPricingError(
                f"Multiple explicitly selected treatment rates recover shared required component {component_id}: "
                + ", ".join(ordered)
                + ". Provide a non-overlapping inclusion ledger or approved parameterised recovery."
            )
        winner = ordered[0]
        for scope in ordered[1:]:
            rejected_scopes.add(scope)
            scope_rejections.setdefault(scope, []).append(
                {
                    "reason": "duplicate_shared_component_recovery",
                    "shared_required_component_id": component_id,
                    "winning_scope": winner,
                }
            )
    for scope in rejected_scopes:
        rate_plans.pop(scope, None)

    component_plans: dict[str, ComponentCommercialPlan] = {}
    for scope, rate_plan in rate_plans.items():
        for plan in _rate_component_plans(rate_plan, components_by_id, quantities, labour):
            if plan.component_id in component_plans:
                raise CommercialPricingError(
                    f"Required component {plan.component_id} is recovered by multiple Package 14 rate plans."
                )
            component_plans[plan.component_id] = plan

    # Apply the remaining hierarchy per uncovered technical requirement.
    for component in sorted(components, key=lambda item: item.id):
        if component.id in component_plans:
            continue
        quantity = quantities[component.id]
        labour_rows = labour[component.id]
        scope = _scope_key(component.opening_id, component.service_id)
        rejected = tuple(scope_rejections.get(scope, []))
        plan = _component_build_plan(
            db,
            estimate,
            component,
            quantity,
            labour_rows,
            component_builds.get(component.id),
            rejected,
        )
        if plan is None:
            plan = _expert_plan(
                component,
                quantity,
                labour_rows,
                expert_estimates.get(component.id),
                rejected,
            )
        if plan is None:
            reason = (
                "No applicable exact Package 14 rate, no approved parameterised rate, "
                "no complete component-build mapping, and no validated expert estimate."
            )
            plan = _not_priced_plan(component, quantity, labour_rows, rejected, reason)
        component_plans[component.id] = plan

    pricing_rows: list[PricingComponent] = []
    method_locks: list[CommercialMethodLock] = []
    recovery_rows: list[CommercialRecoveryRecord] = []
    reconciliations: list[ComponentRequirementReconciliation] = []
    for component_id in sorted(component_plans):
        pricing, method_lock, recovery, reconciliation = _persist_component_plan(
            db, estimate, component_plans[component_id]
        )
        pricing_rows.append(pricing)
        method_locks.append(method_lock)
        recovery_rows.append(recovery)
        reconciliations.append(reconciliation)

    anomaly_reviews = _price_anomaly_reviews(db, estimate, pricing_rows, method_locks)
    db.flush()
    return CommercialDerivation(
        pricing_components=tuple(pricing_rows),
        method_locks=tuple(method_locks),
        recovery_records=tuple(recovery_rows),
        reconciliations=tuple(reconciliations),
        anomaly_reviews=tuple(anomaly_reviews),
    )


__all__ = [
    "ENGINE_VERSION",
    "CommercialDerivation",
    "CommercialPricingError",
    "RateCandidateReceipt",
    "derive_commercial_pricing",
    "search_package14_candidates",
]
