from __future__ import annotations

import itertools
import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import Estimate, EstimatingRule, Opening, RuleEvaluation, Service
from .release_scope import pinned_rules
from .technical import mixed_service_candidate_available


@dataclass(frozen=True)
class Evaluation:
    result: str
    severity: str
    explanation: str
    inputs: dict[str, Any]
    output: dict[str, Any]


def _numeric(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))


def _service_radius(service: Service) -> Decimal | None:
    diameter = _numeric(service.outside_diameter_mm or service.nominal_size_mm)
    if diameter is not None:
        return diameter / Decimal("2")
    width = _numeric(service.width_mm)
    height = _numeric(service.height_mm)
    if width is not None and height is not None:
        return max(width, height) / Decimal("2")
    return None


def edge_gap_mm(a: Service, b: Service) -> Decimal | None:
    ax, ay = _numeric(a.centre_x_mm), _numeric(a.centre_y_mm)
    bx, by = _numeric(b.centre_x_mm), _numeric(b.centre_y_mm)
    ar, br = _service_radius(a), _service_radius(b)
    if ax is None or ay is None or bx is None or by is None or ar is None or br is None:
        return None
    centre_distance = Decimal(str(math.hypot(float(ax - bx), float(ay - by))))
    return centre_distance - ar - br


def _lookup_path(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _condition(condition: dict[str, Any], context: dict[str, Any]) -> bool:
    if "all" in condition:
        return all(_condition(item, context) for item in condition["all"])
    if "any" in condition:
        return any(_condition(item, context) for item in condition["any"])
    if "not" in condition:
        return not _condition(condition["not"], context)
    left = _lookup_path(context, condition.get("field", ""))
    right = condition.get("value")
    op = condition.get("operator", "eq")
    if not isinstance(op, str):
        raise ValueError("Rule operator must be text")
    if op in {"lt", "lte", "gt", "gte"}:
        if left is None:
            return False
        left_number, right_number = Decimal(str(left)), Decimal(str(right))
        return bool(
            {
                "lt": left_number < right_number,
                "lte": left_number <= right_number,
                "gt": left_number > right_number,
                "gte": left_number >= right_number,
            }[op]
        )
    if op == "eq":
        return bool(left == right)
    if op == "neq":
        return bool(left != right)
    if op == "in":
        return left in (right or [])
    if op == "contains":
        return str(right).lower() in str(left or "").lower()
    if op == "exists":
        return left is not None
    raise ValueError(f"Unsupported rule operator: {op}")


def evaluate_generic_rule(rule: EstimatingRule, context: dict[str, Any]) -> Evaluation:
    triggered = _condition(rule.conditions, context)
    actions = rule.actions if triggered else {}
    return Evaluation(
        result="TRIGGERED" if triggered else "PASS",
        severity=rule.severity if triggered else "information",
        explanation=(
            actions.get("message") or rule.description
            if triggered
            else f"Rule {rule.rule_code} did not trigger."
        ),
        inputs=context,
        output=actions,
    )


def evaluate_proximity_rule(db: Session, rule: EstimatingRule, opening: Opening) -> Evaluation:
    threshold = Decimal(str(rule.conditions.get("minimum_separation_mm", 40)))
    pairs: list[dict[str, Any]] = []
    missing_geometry = False
    below: list[dict[str, Any]] = []
    exact: list[dict[str, Any]] = []
    above: list[dict[str, Any]] = []
    for a, b in itertools.combinations(opening.services, 2):
        gap = edge_gap_mm(a, b)
        item = {
            "service_a": a.service_code,
            "service_b": b.service_code,
            "gap_mm": str(gap) if gap is not None else None,
        }
        pairs.append(item)
        if gap is None:
            missing_geometry = True
        elif gap < threshold:
            below.append(item)
        elif gap == threshold:
            exact.append(item)
        else:
            above.append(item)

    inputs = {
        "opening_id": opening.id,
        "opening_code": opening.opening_code,
        "threshold_mm": str(threshold),
        "service_count": len(opening.services),
        "pairs": pairs,
        "jurisdiction": opening.estimate.project.jurisdiction,
    }
    if len(opening.services) < 2:
        return Evaluation(
            result="NOT_APPLICABLE",
            severity="information",
            explanation="The opening contains fewer than two Services.",
            inputs=inputs,
            output={"required_action": "none"},
        )
    if missing_geometry:
        return Evaluation(
            result="BLOCKED",
            severity="hold",
            explanation=(
                "Service separation cannot be evaluated because coordinates or service "
                "dimensions are missing. This is a technical-evidence gap, not a pass."
            ),
            inputs=inputs,
            output={
                "required_action": "capture_service_geometry",
                "automatic_solution_approved": False,
            },
        )
    if below:
        mixed = mixed_service_candidate_available(db, opening)
        if mixed["available"]:
            message = (
                f"One or more service pairs are closer than the configured {threshold} mm "
                "assumption. An Active mixed-service candidate exists, but exact "
                "applicability and human technical approval are required."
            )
            action = "review_mixed_service_candidate"
        else:
            message = (
                f"One or more service pairs are closer than the configured {threshold} mm "
                "assumption and no Active mixed-service candidate was found. Create a "
                "provisional bulkhead/construction allowance only if authorised, including "
                "separate service treatments where required, and obtain a technically "
                "approved solution."
            )
            action = "technical_hold_and_bulkhead_allowance_review"
        return Evaluation(
            result="TRIGGERED",
            severity=rule.severity,
            explanation=message,
            inputs=inputs,
            output={
                "below_threshold_pairs": below,
                "mixed_service_search": mixed,
                "required_action": action,
                "cost_allowance_is_not_technical_approval": True,
                "automatic_solution_approved": False,
            },
        )
    return Evaluation(
        result="PASS",
        severity="information",
        explanation=(
            f"All measurable service pairs meet or exceed the configured {threshold} mm "
            "assumption. This does not independently prove compliance with a selected "
            "technical system."
        ),
        inputs=inputs,
        output={"exact_threshold_pairs": exact, "above_threshold_pairs": above},
    )


def active_rules(db: Session, jurisdiction: str | None = None) -> list[EstimatingRule]:
    today = date.today()
    stmt = select(EstimatingRule).where(
        EstimatingRule.status == "active",
        or_(EstimatingRule.effective_date.is_(None), EstimatingRule.effective_date <= today),
        or_(EstimatingRule.expiry_date.is_(None), EstimatingRule.expiry_date >= today),
    )
    if jurisdiction:
        stmt = stmt.where(
            or_(EstimatingRule.jurisdiction.is_(None), EstimatingRule.jurisdiction == jurisdiction)
        )
    return list(
        db.scalars(
            stmt.order_by(EstimatingRule.priority.asc(), EstimatingRule.rule_code.asc())
        ).all()
    )


def evaluate_estimate_rules(db: Session, estimate: Estimate) -> list[RuleEvaluation]:
    existing = db.scalars(
        select(RuleEvaluation).where(RuleEvaluation.estimate_id == estimate.id)
    ).all()
    for item in existing:
        db.delete(item)
    results: list[RuleEvaluation] = []
    for rule in pinned_rules(db, estimate):
        if rule.category == "service_proximity":
            for opening in estimate.openings:
                evaluation = evaluate_proximity_rule(db, rule, opening)
                record = RuleEvaluation(
                    estimate_id=estimate.id,
                    opening_id=opening.id,
                    rule_id=rule.id,
                    result=evaluation.result,
                    severity=evaluation.severity,
                    explanation=evaluation.explanation,
                    inputs=evaluation.inputs,
                    output=evaluation.output,
                    rule_version=rule.version,
                    source_reference=rule.source_reference,
                )
                db.add(record)
                results.append(record)
        else:
            context = {
                "estimate": {
                    "status": estimate.status,
                    "currency": estimate.currency,
                    "tax_rate": str(estimate.tax_rate),
                },
                "project": {"jurisdiction": estimate.project.jurisdiction},
            }
            evaluation = evaluate_generic_rule(rule, context)
            record = RuleEvaluation(
                estimate_id=estimate.id,
                rule_id=rule.id,
                result=evaluation.result,
                severity=evaluation.severity,
                explanation=evaluation.explanation,
                inputs=evaluation.inputs,
                output=evaluation.output,
                rule_version=rule.version,
                source_reference=rule.source_reference,
            )
            db.add(record)
            results.append(record)
    return results
