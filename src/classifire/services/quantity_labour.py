from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..canonical_models import RepairStrategyLock, SystemRequiredComponent
from ..commercial_models import LabourActivity, ProductivitySource, Quantity, QuantityFormulaInput
from ..models import Estimate, Opening, Service
from .workflow import WorkflowAction
from .workflow_guard import require_estimate_action


ENGINE_VERSION = "QUANTIFIRE-QUANTITY-ENGINE-v1.0"
LABOUR_ENGINE_VERSION = "QUANTIFIRE-LABOUR-ENGINE-v1.0"
TOL = Decimal("0.000001")
Q6 = Decimal("0.000001")
_VALID_INPUT_STATUSES = {"PASS", "FAIL", "UNVERIFIED"}
_APPROVED_PRODUCTIVITY_STATUSES = {"APPROVED", "ACTIVE", "CURRENT"}


class QuantityLabourError(RuntimeError):
    pass


@dataclass(frozen=True)
class InputEvidence:
    value: Any
    unit: str
    evidence_class: str | None
    evidence_ids: tuple[str, ...]
    assumption_id: str | None
    validator_status: str


@dataclass(frozen=True)
class FormulaResult:
    formula_id: str
    inputs: dict[str, InputEvidence]
    result: Decimal
    unit: str
    formula: str
    waste_factor: Decimal
    rounding_rule: str
    record_hash: str


@dataclass(frozen=True)
class QuantityLabourDerivation:
    quantities: tuple[Quantity, ...]
    labour_activities: tuple[LabourActivity, ...]


def _d(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _q6(value: Decimal) -> Decimal:
    return value.quantize(Q6, rounding=ROUND_HALF_UP)


def _norm(value: str | None) -> str:
    return (value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def _hash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def _engine_input(value: Any, unit: str, *, evidence_class: str) -> InputEvidence:
    return InputEvidence(
        value=value,
        unit=unit,
        evidence_class=evidence_class,
        evidence_ids=(),
        assumption_id=None,
        validator_status="PASS",
    )


def _provided_input(
    provided: dict[str, Any],
    name: str,
    unit: str,
    *,
    required: bool = True,
) -> InputEvidence | None:
    if name not in provided:
        if required:
            raise QuantityLabourError(f"Missing required quantity formula input: {name}")
        return None
    raw = provided[name]
    if isinstance(raw, dict) and "value" in raw:
        status = _norm(str(raw.get("validator_status") or "UNVERIFIED"))
        if status not in _VALID_INPUT_STATUSES:
            raise QuantityLabourError(
                f"Invalid validator_status {status!r} for quantity formula input {name}."
            )
        return InputEvidence(
            value=raw["value"],
            unit=str(raw.get("unit") or unit),
            evidence_class=(
                str(raw.get("evidence_class")) if raw.get("evidence_class") is not None else None
            ),
            evidence_ids=tuple(str(x) for x in (raw.get("evidence_ids") or [])),
            assumption_id=(
                str(raw.get("assumption_id")) if raw.get("assumption_id") is not None else None
            ),
            validator_status=status,
        )
    return InputEvidence(
        value=raw,
        unit=unit,
        evidence_class="CONTROLLED_INPUT",
        evidence_ids=(),
        assumption_id=None,
        validator_status="UNVERIFIED",
    )


def _input_payload(inputs: dict[str, InputEvidence]) -> dict[str, Any]:
    return {
        name: {
            "value": item.value,
            "unit": item.unit,
            "evidence_class": item.evidence_class,
            "evidence_ids": list(item.evidence_ids),
            "assumption_id": item.assumption_id,
            "validator_status": item.validator_status,
        }
        for name, item in sorted(inputs.items())
    }


def _formula_result(
    formula_id: str,
    inputs: dict[str, InputEvidence],
    result: Decimal,
    unit: str,
    formula: str,
    *,
    waste_factor: Decimal = Decimal("1"),
    rounding_rule: str = "none",
) -> FormulaResult:
    record = {
        "formula_id": formula_id,
        "formula_inputs": _input_payload(inputs),
        "formula": formula,
        "waste_factor": str(waste_factor),
        "rounding_rule": rounding_rule,
        "formula_result": str(_q6(result)),
        "unit": unit,
        "engine_version": ENGINE_VERSION,
    }
    return FormulaResult(
        formula_id=formula_id,
        inputs=inputs,
        result=_q6(result),
        unit=unit,
        formula=formula,
        waste_factor=waste_factor,
        rounding_rule=rounding_rule,
        record_hash=_hash(record),
    )


def _opening_and_service(
    db: Session, component: SystemRequiredComponent
) -> tuple[Opening, Service | None]:
    opening = db.get(Opening, component.opening_id)
    if not opening:
        raise QuantityLabourError(
            f"SystemRequiredComponent {component.id} refers to missing Opening {component.opening_id}."
        )
    service = db.get(Service, component.service_id) if component.service_id else None
    if component.service_id and not service:
        raise QuantityLabourError(
            f"SystemRequiredComponent {component.id} refers to missing Service {component.service_id}."
        )
    return opening, service


def _decimal_input(inputs: dict[str, InputEvidence], name: str) -> Decimal:
    try:
        return _d(inputs[name].value)
    except Exception as exc:
        raise QuantityLabourError(f"Quantity formula input {name} is not numeric.") from exc


def _ceil_decimal(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_CEILING)


def _resolve_formula(
    db: Session,
    component: SystemRequiredComponent,
    provided: dict[str, Any],
) -> FormulaResult:
    formula_id = component.quantity_formula_id
    if not formula_id:
        raise QuantityLabourError(
            f"SystemRequiredComponent {component.id} has no executable quantity_formula_id."
        )
    opening, service = _opening_and_service(db, component)
    inputs: dict[str, InputEvidence] = {}

    if formula_id == "QF-WRAP-LENGTH":
        inputs["service_quantity"] = _engine_input(
            service.quantity if service and service.quantity is not None else 1,
            "each",
            evidence_class="CANONICAL_PHYSICAL_MODEL",
        )
        inputs["prescribed_length_m"] = _provided_input(
            provided, "prescribed_length_m", "m"
        )  # type: ignore[assignment]
        inputs["layer_count"] = _provided_input(
            provided, "layer_count", "layer", required=False
        ) or _engine_input(1, "layer", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        inputs["waste_factor"] = _provided_input(
            provided, "waste_factor", "factor", required=False
        ) or _engine_input(Decimal("1.1"), "factor", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        procurement = _provided_input(
            provided, "procurement_length_m", "m", required=False
        )
        if procurement:
            inputs["procurement_length_m"] = procurement
        raw = (
            _decimal_input(inputs, "service_quantity")
            * _decimal_input(inputs, "prescribed_length_m")
            * _decimal_input(inputs, "layer_count")
            * _decimal_input(inputs, "waste_factor")
        )
        if procurement:
            procurement_length = _decimal_input(inputs, "procurement_length_m")
            if procurement_length <= 0:
                raise QuantityLabourError("procurement_length_m must be positive.")
            result = _ceil_decimal((raw / procurement_length) - TOL) * procurement_length
            rounding = "ceil procurement"
        else:
            result = raw
            rounding = "none"
        return _formula_result(
            formula_id,
            inputs,
            result,
            "m",
            "service_quantity * prescribed_length_m * layer_count * waste_factor",
            waste_factor=_decimal_input(inputs, "waste_factor"),
            rounding_rule=rounding,
        )

    if formula_id == "QF-MASTIC-ANNULAR-VOLUME":
        if opening.diameter_mm is not None:
            inputs["opening_diameter_mm"] = _engine_input(
                opening.diameter_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["opening_diameter_mm"] = _provided_input(
                provided, "opening_diameter_mm", "mm"
            )  # type: ignore[assignment]
        if service and (service.outside_diameter_mm is not None or service.nominal_size_mm is not None):
            inputs["service_diameter_mm"] = _engine_input(
                service.outside_diameter_mm
                if service.outside_diameter_mm is not None
                else service.nominal_size_mm,
                "mm",
                evidence_class="CANONICAL_PHYSICAL_MODEL",
            )
        else:
            inputs["service_diameter_mm"] = _provided_input(
                provided, "service_diameter_mm", "mm"
            )  # type: ignore[assignment]
        inputs["seal_depth_mm"] = _provided_input(
            provided, "seal_depth_mm", "mm"
        )  # type: ignore[assignment]
        inputs["faces"] = _provided_input(
            provided, "faces", "face", required=False
        ) or _engine_input(1, "face", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        inputs["waste_factor"] = _provided_input(
            provided, "waste_factor", "factor", required=False
        ) or _engine_input(Decimal("1.1"), "factor", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        opening_d = _decimal_input(inputs, "opening_diameter_mm")
        service_d = _decimal_input(inputs, "service_diameter_mm")
        if opening_d < service_d:
            raise QuantityLabourError("opening_diameter_mm is below service_diameter_mm.")
        annular_area = Decimal(str(math.pi)) / Decimal("4") * (
            opening_d**2 - service_d**2
        )
        raw_mm3 = annular_area * _decimal_input(inputs, "seal_depth_mm") * _decimal_input(
            inputs, "faces"
        )
        result = raw_mm3 / Decimal("1000000") * _decimal_input(inputs, "waste_factor")
        return _formula_result(
            formula_id,
            inputs,
            result,
            "L",
            "annular area * depth * faces / 1e6 * waste",
            waste_factor=_decimal_input(inputs, "waste_factor"),
        )

    if formula_id == "QF-BATT-BOARD-AREA":
        if opening.width_mm is not None:
            inputs["width_mm"] = _engine_input(
                opening.width_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["width_mm"] = _provided_input(provided, "width_mm", "mm")  # type: ignore[assignment]
        if opening.height_mm is not None:
            inputs["height_mm"] = _engine_input(
                opening.height_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["height_mm"] = _provided_input(provided, "height_mm", "mm")  # type: ignore[assignment]
        inputs["layers"] = _provided_input(
            provided, "layers", "layer", required=False
        ) or _engine_input(1, "layer", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        inputs["waste_factor"] = _provided_input(
            provided, "waste_factor", "factor", required=False
        ) or _engine_input(Decimal("1.15"), "factor", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        sheet = _provided_input(provided, "sheet_area_m2", "m2", required=False)
        if sheet:
            inputs["sheet_area_m2"] = sheet
        raw = (
            _decimal_input(inputs, "width_mm")
            / Decimal("1000")
            * _decimal_input(inputs, "height_mm")
            / Decimal("1000")
            * _decimal_input(inputs, "layers")
            * _decimal_input(inputs, "waste_factor")
        )
        if sheet:
            sheet_area = _decimal_input(inputs, "sheet_area_m2")
            if sheet_area <= 0:
                raise QuantityLabourError("sheet_area_m2 must be positive.")
            result = _ceil_decimal((raw / sheet_area) - TOL) * sheet_area
            rounding = "sheet upward"
        else:
            result = raw
            rounding = "none"
        return _formula_result(
            formula_id,
            inputs,
            result,
            "m2",
            "opening area * layers * waste",
            waste_factor=_decimal_input(inputs, "waste_factor"),
            rounding_rule=rounding,
        )

    if formula_id == "QF-FRAMING-PROCUREMENT":
        if opening.width_mm is not None:
            inputs["width_mm"] = _engine_input(
                opening.width_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["width_mm"] = _provided_input(provided, "width_mm", "mm")  # type: ignore[assignment]
        if opening.height_mm is not None:
            inputs["height_mm"] = _engine_input(
                opening.height_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["height_mm"] = _provided_input(provided, "height_mm", "mm")  # type: ignore[assignment]
        defaults = {
            "required_sides": (4, "side"),
            "layers": (1, "layer"),
            "procurement_length_m": (Decimal("1.22"), "m"),
            "corner_allowance_m": (0, "m"),
            "waste_factor": (1, "factor"),
        }
        for name, (default, unit) in defaults.items():
            inputs[name] = _provided_input(provided, name, unit, required=False) or _engine_input(
                default, unit, evidence_class="CONTROLLED_ENGINE_DEFAULT"
            )
        width = _decimal_input(inputs, "width_mm")
        height = _decimal_input(inputs, "height_mm")
        required_sides = int(_decimal_input(inputs, "required_sides"))
        layers = _decimal_input(inputs, "layers")
        if required_sides == 4:
            length = Decimal("2") * (width + height) / Decimal("1000")
        elif required_sides == 2:
            length = (width + height) / Decimal("1000")
        else:
            length = Decimal(required_sides) * max(width, height) / Decimal("1000")
        length = length * layers + _decimal_input(inputs, "corner_allowance_m")
        adjusted = length * _decimal_input(inputs, "waste_factor")
        procurement_length = _decimal_input(inputs, "procurement_length_m")
        if procurement_length <= 0:
            raise QuantityLabourError("procurement_length_m must be positive.")
        result = _ceil_decimal((adjusted / procurement_length) - TOL)
        return _formula_result(
            formula_id,
            inputs,
            result,
            "length",
            "ceil(required length * waste / procurement length)",
            waste_factor=_decimal_input(inputs, "waste_factor"),
            rounding_rule="whole lengths",
        )

    if formula_id == "QF-FIXING-COUNT":
        inputs["required_fixed_length_m"] = _provided_input(
            provided, "required_fixed_length_m", "m"
        )  # type: ignore[assignment]
        inputs["spacing_mm"] = _provided_input(provided, "spacing_mm", "mm")  # type: ignore[assignment]
        inputs["corner_fixings"] = _provided_input(
            provided, "corner_fixings", "each", required=False
        ) or _engine_input(0, "each", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        inputs["minimum_fixings"] = _provided_input(
            provided, "minimum_fixings", "each", required=False
        ) or _engine_input(0, "each", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        spacing = _decimal_input(inputs, "spacing_mm")
        if spacing <= 0:
            raise QuantityLabourError("spacing_mm must be positive.")
        calculated = _ceil_decimal(
            (_decimal_input(inputs, "required_fixed_length_m") / (spacing / Decimal("1000")))
            - TOL
        ) + _decimal_input(inputs, "corner_fixings")
        result = max(calculated, _decimal_input(inputs, "minimum_fixings"))
        return _formula_result(
            formula_id,
            inputs,
            result,
            "each",
            "max(ceil(length / spacing) + corners, minimum)",
            rounding_rule="whole fixings",
        )

    if formula_id == "QF-MORTAR-VOLUME":
        if opening.width_mm is not None:
            inputs["width_mm"] = _engine_input(
                opening.width_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["width_mm"] = _provided_input(provided, "width_mm", "mm")  # type: ignore[assignment]
        if opening.height_mm is not None:
            inputs["height_mm"] = _engine_input(
                opening.height_mm, "mm", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["height_mm"] = _provided_input(provided, "height_mm", "mm")  # type: ignore[assignment]
        inputs["depth_mm"] = _provided_input(provided, "depth_mm", "mm")  # type: ignore[assignment]
        inputs["service_displacement_m3"] = _provided_input(
            provided, "service_displacement_m3", "m3", required=False
        ) or _engine_input(0, "m3", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        inputs["waste_factor"] = _provided_input(
            provided, "waste_factor", "factor", required=False
        ) or _engine_input(Decimal("1.15"), "factor", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        density = _provided_input(provided, "density_kg_m3", "kg/m3", required=False)
        bag = _provided_input(provided, "bag_kg", "kg", required=False)
        if density:
            inputs["density_kg_m3"] = density
        if bag:
            inputs["bag_kg"] = bag
        opening_volume = (
            _decimal_input(inputs, "width_mm")
            / Decimal("1000")
            * _decimal_input(inputs, "height_mm")
            / Decimal("1000")
            * _decimal_input(inputs, "depth_mm")
            / Decimal("1000")
        )
        net = max(
            Decimal("0"), opening_volume - _decimal_input(inputs, "service_displacement_m3")
        ) * _decimal_input(inputs, "waste_factor")
        if density and bag:
            bag_kg = _decimal_input(inputs, "bag_kg")
            if bag_kg <= 0:
                raise QuantityLabourError("bag_kg must be positive.")
            result = _ceil_decimal(
                (net * _decimal_input(inputs, "density_kg_m3") / bag_kg) - TOL
            )
            return _formula_result(
                "QF-MORTAR-BAG-COUNT",
                inputs,
                result,
                "bag",
                "ceil(net volume * density / bag kg)",
                waste_factor=_decimal_input(inputs, "waste_factor"),
                rounding_rule="whole bags",
            )
        return _formula_result(
            formula_id,
            inputs,
            net,
            "m3",
            "(opening volume - displacement) * waste",
            waste_factor=_decimal_input(inputs, "waste_factor"),
        )

    if formula_id == "QF-EACH":
        auto_count: Decimal | None = None
        if component.category in {"QA_DOCUMENTATION", "LABEL"}:
            auto_count = Decimal("1")
        elif component.category in {"COLLAR", "SLEEVE"} and service is not None:
            auto_count = _d(service.quantity or 1)
        if auto_count is not None:
            inputs["count"] = _engine_input(
                auto_count, "each", evidence_class="CANONICAL_PHYSICAL_MODEL"
            )
        else:
            inputs["count"] = _provided_input(provided, "count", "each")  # type: ignore[assignment]
        return _formula_result(
            formula_id,
            inputs,
            _decimal_input(inputs, "count"),
            "each",
            "controlled count",
            rounding_rule="whole units",
        )

    if formula_id == "QF-ACTIVITY":
        inputs["activity_count"] = _provided_input(
            provided, "activity_count", "activity", required=False
        ) or _engine_input(1, "activity", evidence_class="CONTROLLED_ENGINE_DEFAULT")
        return _formula_result(
            formula_id,
            inputs,
            _decimal_input(inputs, "activity_count"),
            "activity",
            "controlled activity count",
        )

    if formula_id == "QF-LENGTH":
        inputs["length_m"] = _provided_input(provided, "length_m", "m")  # type: ignore[assignment]
        return _formula_result(
            formula_id,
            inputs,
            _decimal_input(inputs, "length_m"),
            "m",
            "controlled required length",
        )

    if formula_id == "QF-EXPERT-ESTIMATE":
        inputs["quantity"] = _provided_input(provided, "quantity", "unit")  # type: ignore[assignment]
        unit_input = _provided_input(provided, "unit", "unit")  # type: ignore[assignment]
        inputs["unit"] = unit_input
        return _formula_result(
            formula_id,
            inputs,
            _decimal_input(inputs, "quantity"),
            str(unit_input.value),
            "controlled expert-estimate quantity input",
        )

    raise QuantityLabourError(
        f"Unsupported executable quantity formula {formula_id!r} for component {component.id}."
    )


def _persist_quantity(
    db: Session,
    estimate: Estimate,
    component: SystemRequiredComponent,
    formula: FormulaResult,
) -> Quantity:
    all_pass = all(item.validator_status == "PASS" for item in formula.inputs.values())
    formula_record = {
        "formula_id": formula.formula_id,
        "formula_inputs": _input_payload(formula.inputs),
        "formula": formula.formula,
        "waste_factor": str(formula.waste_factor),
        "rounding_rule": formula.rounding_rule,
        "formula_result": str(formula.result),
        "unit": formula.unit,
        "engine_version": ENGINE_VERSION,
        "record_hash": formula.record_hash,
    }

    existing = list(
        db.scalars(
            select(Quantity)
            .where(
                Quantity.required_component_id == component.id,
                Quantity.status != "superseded",
            )
            .order_by(Quantity.record_version.desc(), Quantity.created_at.desc())
        ).all()
    )
    for item in existing:
        if (item.provenance or {}).get("record_hash") == formula.record_hash:
            return item
    for item in existing:
        item.status = "superseded"

    max_version = db.scalar(
        select(func.max(Quantity.record_version)).where(
            Quantity.required_component_id == component.id
        )
    ) or 0
    quantity = Quantity(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        required_component_id=component.id,
        quantity_type=(
            "Estimated Quantity"
            if formula.formula_id == "QF-EXPERT-ESTIMATE"
            else "Calculated Quantity"
        ),
        subject_type="system_required_component",
        subject_id=component.id,
        purpose=component.description,
        numeric_value=formula.result,
        unit_basis=formula.unit,
        source_method=formula.formula_id,
        formula_id=formula.formula_id,
        precision_digits=6,
        rounding_method=formula.rounding_rule,
        waste_factor=formula.waste_factor,
        conversion_factor=Decimal("1"),
        epistemic_type=(
            "EXPERT_ESTIMATE"
            if formula.formula_id == "QF-EXPERT-ESTIMATE"
            else "CALCULATED"
        ),
        confidence="CONTROLLED" if all_pass else "PROVISIONAL",
        risk_status="CONTROLLED" if all_pass else "REVIEW_REQUIRED",
        status="validated" if all_pass else "provisional",
        provenance={
            **formula_record,
            "opening_id": component.opening_id,
            "service_id": component.service_id,
            "candidate_id": component.candidate_id,
            "technical_requirement_id": component.technical_requirement_id,
        },
        record_version=int(max_version) + 1,
    )
    db.add(quantity)
    db.flush()

    for name, item in sorted(formula.inputs.items()):
        db.add(
            QuantityFormulaInput(
                quantity_record_id=quantity.id,
                input_name=name,
                input_value=item.value,
                unit=item.unit,
                evidence_class=item.evidence_class,
                evidence_ids=list(item.evidence_ids),
                assumption_id=item.assumption_id,
                validator_status=item.validator_status,
            )
        )
    db.flush()
    return quantity


def _approved_productivity(db: Session, activity: str) -> ProductivitySource:
    candidates = list(
        db.scalars(
            select(ProductivitySource)
            .where(ProductivitySource.activity == activity)
            .order_by(ProductivitySource.created_at.desc())
        ).all()
    )
    for candidate in candidates:
        if _norm(candidate.approval_status) in _APPROVED_PRODUCTIVITY_STATUSES:
            if not candidate.executable_formula_id:
                continue
            return candidate
    raise QuantityLabourError(
        f"No approved ProductivitySource with executable formula exists for labour activity {activity}."
    )


def _unit_key(value: str) -> str:
    text = value.strip().lower().replace("²", "2")
    aliases = {
        "sqm": "m2",
        "m^2": "m2",
        "litre": "l",
        "litres": "l",
        "liter": "l",
        "liters": "l",
        "ea": "each",
        "unit": "each",
        "units": "each",
    }
    return aliases.get(text, text)


def _activity_type(activity: str) -> str:
    norm = _norm(activity)
    if any(token in norm for token in ("INSPECTION", "PHOTOGRAPHY", "REGISTER")):
        return "QA"
    if "CLEANUP" in norm:
        return "Cleanup"
    if any(token in norm for token in ("PREPARE", "MEASURE", "SET_OUT")):
        return "Preparation"
    if any(token in norm for token in ("FINISH", "VERIFY")):
        return "Finishing"
    return "Installation"


def _factor_value(
    adjustment: dict[str, Any], name: str
) -> tuple[Decimal, str, list[str]]:
    raw = adjustment.get(name)
    if raw is None:
        return Decimal("1"), "PASS", []
    if isinstance(raw, dict) and "value" in raw:
        status = _norm(str(raw.get("validator_status") or "UNVERIFIED"))
        if status not in _VALID_INPUT_STATUSES:
            raise QuantityLabourError(
                f"Invalid validator_status {status!r} for labour adjustment {name}."
            )
        value = _d(raw["value"])
        evidence_ids = [str(x) for x in (raw.get("evidence_ids") or [])]
    else:
        status = "UNVERIFIED"
        value = _d(raw)
        evidence_ids = []
    if value <= 0:
        raise QuantityLabourError(f"Labour adjustment factor {name} must be positive.")
    return value, status, evidence_ids


def _persist_labour_activity(
    db: Session,
    estimate: Estimate,
    component: SystemRequiredComponent,
    quantity: Quantity,
    activity: str,
    productivity: ProductivitySource,
    adjustment: dict[str, Any],
) -> LabourActivity:
    if _unit_key(productivity.quantity_unit) != _unit_key(quantity.unit_basis):
        raise QuantityLabourError(
            f"ProductivitySource {productivity.id} for {activity} uses unit {productivity.quantity_unit!r}, "
            f"but component quantity uses {quantity.unit_basis!r}; no controlled conversion is defined."
        )
    if quantity.numeric_value is None:
        raise QuantityLabourError(f"Quantity {quantity.id} has no numeric value for labour derivation.")

    factor_names = (
        "difficulty_factor",
        "access_factor",
        "occupied_factor",
        "congestion_factor",
    )
    factors: dict[str, Decimal] = {}
    statuses: list[str] = []
    factor_evidence: dict[str, list[str]] = {}
    for name in factor_names:
        value, status, evidence_ids = _factor_value(adjustment, name)
        factors[name] = value
        statuses.append(status)
        factor_evidence[name] = evidence_ids

    hours = (
        _d(quantity.numeric_value)
        * _d(productivity.base_hours_per_unit)
        * factors["difficulty_factor"]
        * factors["access_factor"]
        * factors["occupied_factor"]
        * factors["congestion_factor"]
    )
    hours = _q6(hours)
    all_pass = quantity.status == "validated" and all(status == "PASS" for status in statuses)

    provenance = {
        "activity": activity,
        "component_id": component.id,
        "quantity_record_id": quantity.id,
        "quantity_driver": str(quantity.numeric_value),
        "quantity_unit": quantity.unit_basis,
        "productivity_id": productivity.id,
        "base_hours_per_unit": str(productivity.base_hours_per_unit),
        "difficulty_factor": str(factors["difficulty_factor"]),
        "access_factor": str(factors["access_factor"]),
        "occupied_factor": str(factors["occupied_factor"]),
        "congestion_factor": str(factors["congestion_factor"]),
        "factor_evidence_ids": factor_evidence,
        "person_hours": str(hours),
        "adjustment_formula": (
            "installed_quantity * base_hours * difficulty * access * occupied * congestion"
        ),
        "productivity_source_id": productivity.source_record_id,
        "source_version": productivity.source_version,
        "confidence": productivity.confidence,
        "evidence_class": productivity.evidence_class,
        "executable_formula_id": productivity.executable_formula_id,
        "engine_version": LABOUR_ENGINE_VERSION,
    }
    provenance["record_hash"] = _hash(provenance)

    existing = list(
        db.scalars(
            select(LabourActivity)
            .where(
                LabourActivity.required_component_id == component.id,
                LabourActivity.activity_name == activity,
                LabourActivity.status != "superseded",
            )
            .order_by(LabourActivity.record_version.desc(), LabourActivity.created_at.desc())
        ).all()
    )
    for item in existing:
        if (item.provenance or {}).get("record_hash") == provenance["record_hash"]:
            return item
    for item in existing:
        item.status = "superseded"

    max_version = db.scalar(
        select(func.max(LabourActivity.record_version)).where(
            LabourActivity.required_component_id == component.id,
            LabourActivity.activity_name == activity,
        )
    ) or 0
    labour = LabourActivity(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        required_component_id=component.id,
        productivity_source_id=productivity.id,
        activity_type=_activity_type(activity),
        activity_name=activity,
        scope_output=component.description,
        crew_size=None,
        labour_quantity_hours=hours,
        working_conditions={name: str(value) for name, value in factors.items()},
        rate_source=None,
        unit_rate=None,
        extended_cost=None,
        included_tools_and_incidentals=None,
        confidence=productivity.confidence or ("CONTROLLED" if all_pass else "PROVISIONAL"),
        risk_status="CONTROLLED" if all_pass else "REVIEW_REQUIRED",
        status="validated" if all_pass else "provisional",
        provenance=provenance,
        record_version=int(max_version) + 1,
    )
    db.add(labour)
    db.flush()
    return labour


def derive_quantity_and_labour(
    db: Session,
    estimate: Estimate,
    *,
    component_inputs: dict[str, dict[str, Any]] | None = None,
    labour_adjustments: dict[str, dict[str, Any]] | None = None,
) -> QuantityLabourDerivation:
    """Derive v2.13 quantities and person-hours without applying commercial rates.

    All required components must be covered by the current Repair Strategy Lock.
    Missing executable inputs or missing approved productivity sources fail closed
    before commercial pricing is permitted.
    """
    require_estimate_action(db, estimate, WorkflowAction.CALCULATE_QUANTITY_AND_LABOUR)
    component_inputs = component_inputs or {}
    labour_adjustments = labour_adjustments or {}

    opening_ids = list(
        db.scalars(select(Opening.id).where(Opening.estimate_id == estimate.id)).all()
    )
    if not opening_ids:
        raise QuantityLabourError("Estimate has no Openings for quantity derivation.")

    components = list(
        db.scalars(
            select(SystemRequiredComponent)
            .where(SystemRequiredComponent.opening_id.in_(opening_ids))
            .order_by(SystemRequiredComponent.opening_id, SystemRequiredComponent.id)
        ).all()
    )
    if not components:
        raise QuantityLabourError("Estimate has no SystemRequiredComponent records.")

    active_locks = list(
        db.scalars(
            select(RepairStrategyLock).where(
                RepairStrategyLock.opening_id.in_(opening_ids),
                RepairStrategyLock.invalidated_at.is_(None),
            )
        ).all()
    )
    locked_component_ids = {
        component_id
        for lock in active_locks
        for component_id in (lock.required_component_ids or [])
    }
    component_ids = {component.id for component in components}
    if not component_ids.issubset(locked_component_ids):
        missing = sorted(component_ids - locked_component_ids)
        raise QuantityLabourError(
            "SystemRequiredComponent records are not fully covered by active Repair Strategy Locks: "
            + ", ".join(missing)
        )

    # Resolve every quantity and every productivity source first so the operation
    # fails closed before partially writing the estimate stage.
    planned_formulas: dict[str, FormulaResult] = {}
    planned_productivity: dict[tuple[str, str], ProductivitySource] = {}
    errors: list[str] = []
    for component in components:
        try:
            planned_formulas[component.id] = _resolve_formula(
                db, component, component_inputs.get(component.id, {})
            )
        except QuantityLabourError as exc:
            errors.append(f"{component.id}: {exc}")
        for activity in component.required_labour_activity_ids or []:
            try:
                planned_productivity[(component.id, activity)] = _approved_productivity(
                    db, activity
                )
            except QuantityLabourError as exc:
                errors.append(f"{component.id}/{activity}: {exc}")
    if errors:
        raise QuantityLabourError("; ".join(sorted(set(errors))))

    quantities: list[Quantity] = []
    quantity_by_component: dict[str, Quantity] = {}
    for component in components:
        quantity = _persist_quantity(
            db, estimate, component, planned_formulas[component.id]
        )
        quantities.append(quantity)
        quantity_by_component[component.id] = quantity

    labour_rows: list[LabourActivity] = []
    for component in components:
        quantity = quantity_by_component[component.id]
        for activity in component.required_labour_activity_ids or []:
            adjustment = (
                labour_adjustments.get(f"{component.id}:{activity}")
                or labour_adjustments.get(activity)
                or {}
            )
            labour_rows.append(
                _persist_labour_activity(
                    db,
                    estimate,
                    component,
                    quantity,
                    activity,
                    planned_productivity[(component.id, activity)],
                    adjustment,
                )
            )

    db.flush()
    return QuantityLabourDerivation(
        quantities=tuple(quantities), labour_activities=tuple(labour_rows)
    )


__all__ = [
    "ENGINE_VERSION",
    "LABOUR_ENGINE_VERSION",
    "FormulaResult",
    "InputEvidence",
    "QuantityLabourDerivation",
    "QuantityLabourError",
    "derive_quantity_and_labour",
]
