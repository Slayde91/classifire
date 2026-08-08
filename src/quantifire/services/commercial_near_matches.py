from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from ..models import Estimate, Opening, PricingLibraryRecord, Service
from .commercial import RateCandidateReceipt, search_package14_candidates

MIN_NEAR_MATCH_PERCENT = 55
DEFAULT_NEAR_MATCH_LIMIT = 5

_FIELD_WEIGHTS: dict[str, int] = {
    "service_type": 20,
    "service_material": 20,
    "substrate": 15,
    "substrate_plane": 10,
    "orientation": 10,
    "frl": 15,
    "package15": 10,
}


@dataclass(frozen=True)
class NearMatchSuggestion:
    pkb_entry_id: str
    record_id: str
    entry_version: str | None
    similarity_percent: int
    rate_ex_tax: str
    unit: str
    exact_match: bool
    exact_match_eligible: bool
    proxy_eligible: bool
    automatic_application_permitted: bool
    commercial_analogue: bool
    possible_use: str
    expert_review_required: bool
    blockers: tuple[str, ...]
    field_details: dict[str, dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return {
            "pkb_entry_id": self.pkb_entry_id,
            "record_id": self.record_id,
            "entry_version": self.entry_version,
            "similarity_percent": self.similarity_percent,
            "rate_ex_tax": self.rate_ex_tax,
            "unit": self.unit,
            "exact_match": self.exact_match,
            "exact_match_eligible": self.exact_match_eligible,
            "proxy_eligible": self.proxy_eligible,
            "automatic_application_permitted": self.automatic_application_permitted,
            "commercial_analogue": self.commercial_analogue,
            "possible_use": self.possible_use,
            "expert_review_required": self.expert_review_required,
            "blockers": list(self.blockers),
            "field_details": self.field_details,
        }


@dataclass(frozen=True)
class Package14Recommendation:
    exact_matches: tuple[NearMatchSuggestion, ...]
    suggested_near_matches: tuple[NearMatchSuggestion, ...]
    message: str
    next_action: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "exact_match_count": len(self.exact_matches),
            "near_match_count": len(self.suggested_near_matches),
            "exact_matches": [item.as_dict() for item in self.exact_matches],
            "suggested_near_matches": [item.as_dict() for item in self.suggested_near_matches],
            "message": self.message,
            "next_action": self.next_action,
            "control_rule": (
                "A reasonable near match may be proposed automatically, but it is never "
                "promoted automatically to an applicable technical system or pricing rate."
            ),
        }


def _field_score(result: str, weight: int) -> float:
    if result == "MATCH":
        return float(weight)
    if result == "UNKNOWN":
        return float(weight) * 0.35
    return 0.0


def _similarity(receipt: RateCandidateReceipt) -> int:
    score = 0.0
    for field, weight in _FIELD_WEIGHTS.items():
        if field == "package15":
            result = receipt.package15_result
        else:
            result = receipt.comparisons.get(field, "UNKNOWN")
        score += _field_score(result, weight)
    return max(0, min(100, round(score)))


def _details(
    receipt: RateCandidateReceipt,
    record: PricingLibraryRecord,
    opening: Opening,
    service: Service | None,
) -> dict[str, dict[str, Any]]:
    required = {
        "service_type": service.service_type if service else None,
        "service_material": service.material if service else None,
        "substrate": opening.substrate_type,
        "substrate_plane": opening.substrate_plane,
        "orientation": opening.orientation,
        "frl": opening.frl,
    }
    candidate = {
        "service_type": record.service_class or record.service_type,
        "service_material": record.service_material,
        "substrate": record.substrate,
        "substrate_plane": record.substrate_plane,
        "orientation": record.orientation,
        "frl": record.frl,
    }
    result: dict[str, dict[str, Any]] = {}
    for field in (
        "service_type",
        "service_material",
        "substrate",
        "substrate_plane",
        "orientation",
        "frl",
    ):
        result[field] = {
            "required": required[field],
            "candidate": candidate[field],
            "result": receipt.comparisons.get(field, "UNKNOWN"),
        }
    result["package15_mapping"] = {
        "required": "current locked Package 15 repair strategy",
        "candidate": "Package 14 retained Package 15 mapping",
        "result": receipt.package15_result,
    }
    return result


def _suggestion(
    db: Session,
    receipt: RateCandidateReceipt,
    opening: Opening,
    service: Service | None,
) -> NearMatchSuggestion:
    record = db.get(PricingLibraryRecord, receipt.record_id)
    if record is None:
        raise RuntimeError(f"Package 14 candidate record {receipt.record_id} is missing")
    exact = bool(receipt.exact_eligible and not receipt.blockers)
    possible_use = (
        "Exact Library Match"
        if exact
        else (
            "Approved Parameterised Match / Commercial Analogue"
            if receipt.proxy_eligible
            else "Commercial Analogue only"
        )
    )
    return NearMatchSuggestion(
        pkb_entry_id=receipt.pkb_entry_id,
        record_id=receipt.record_id,
        entry_version=receipt.entry_version,
        similarity_percent=_similarity(receipt),
        rate_ex_tax=str(receipt.rate_ex_tax),
        unit=receipt.unit,
        exact_match=exact,
        exact_match_eligible=receipt.exact_eligible,
        proxy_eligible=receipt.proxy_eligible,
        automatic_application_permitted=exact,
        commercial_analogue=not exact,
        possible_use=possible_use,
        expert_review_required=not exact,
        blockers=receipt.blockers,
        field_details=_details(receipt, record, opening, service),
    )


def recommend_package14_matches(
    db: Session,
    estimate: Estimate,
    *,
    opening: Opening,
    service: Service | None,
    near_match_limit: int = DEFAULT_NEAR_MATCH_LIMIT,
) -> Package14Recommendation:
    receipts = search_package14_candidates(
        db,
        estimate,
        opening=opening,
        service=service,
        limit=max(50, near_match_limit * 10),
    )
    suggestions = [_suggestion(db, item, opening, service) for item in receipts]
    exact = tuple(item for item in suggestions if item.exact_match)
    near = tuple(
        sorted(
            (
                item
                for item in suggestions
                if not item.exact_match and item.similarity_percent >= MIN_NEAR_MATCH_PERCENT
            ),
            key=lambda item: (item.similarity_percent, item.proxy_eligible, item.pkb_entry_id),
            reverse=True,
        )[:near_match_limit]
    )

    if exact:
        message = (
            f"{len(exact)} valid exact Package 14 match(es) were found. "
            "Use the existing Rate Applicability Gate before applying a selected exact rate."
        )
        next_action = "review_exact_matches"
    elif near:
        best = near[0]
        differences = [
            field
            for field, detail in best.field_details.items()
            if detail.get("result") != "MATCH"
        ]
        reason = ", ".join(differences) if differences else "non-exact applicability controls"
        message = (
            f"No exact Package 14 match was found. The closest commercial analogue is "
            f"{best.pkb_entry_id} at {best.similarity_percent}% similarity. It cannot be "
            f"automatically applied because of: {reason}. "
            + (
                "It may be considered for a formally approved parameterised match; otherwise "
                "proceed to component-built pricing."
                if best.proxy_eligible
                else "Treat it as a commercial analogue only and proceed to component-built pricing."
            )
        )
        next_action = (
            "review_parameterised_match_or_component_build"
            if best.proxy_eligible
            else "component_build_using_analogue_for_context_only"
        )
    else:
        message = (
            "No exact Package 14 match and no reasonable near match were found. "
            "Proceed to component-built pricing, then validated expert estimate if necessary."
        )
        next_action = "component_build"

    return Package14Recommendation(
        exact_matches=exact,
        suggested_near_matches=near,
        message=message,
        next_action=next_action,
    )


__all__ = [
    "DEFAULT_NEAR_MATCH_LIMIT",
    "MIN_NEAR_MATCH_PERCENT",
    "NearMatchSuggestion",
    "Package14Recommendation",
    "recommend_package14_matches",
]
