"""Read-only register projections from explicit saved Draft artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ..models import User
from ..security import has_permission
from . import draft_estimates as estimates
from . import draft_system_matches as matches
from .draft_scope import DraftScopeError, get_draft, read_revision
from .draft_scope_evidence import reference_status


def hierarchy_review(content: dict[str, Any]) -> dict[str, list[str]]:
    """Classify intake without rewriting identities, links or historical evidence."""
    defects = {item["id"] for item in content["defects"]}
    openings = {item["id"]: item for item in content["openings"]}
    result: dict[str, list[str]] = {}
    used: set[str] = set()
    for service in content["services"]:
        links = service["opening_ids"]
        reasons = []
        if len(links) != 1:
            reasons.append("Select one parent Opening; existing links are preserved for review.")
        for identity in links:
            opening = openings.get(identity)
            if opening is None:
                reasons.append("The linked Opening is unavailable.")
                continue
            used.add(identity)
            if opening["defect_id"] not in defects:
                reasons.append("The parent Opening needs a Defect.")
            if opening["blank"]:
                reasons.append("A blank Opening cannot contain a Service.")
        result[service["id"]] = list(dict.fromkeys(reasons))
    for identity, opening in openings.items():
        reasons = []
        if opening["defect_id"] not in defects:
            reasons.append("Select a parent Defect.")
        if not opening["blank"] and identity not in used:
            reasons.append("Confirm whether this Opening is blank or identify its Services.")
        result[identity] = reasons
    return result


def _selection(value: str) -> tuple[str, int]:
    try:
        identity, number = value.rsplit(":", 1)
        UUID(identity)
        revision = int(number)
        if str(revision) != number or not 1 <= revision <= 2_147_483_647:
            raise ValueError
        return identity, revision
    except (ValueError, AttributeError) as exc:
        raise DraftScopeError("REGISTER_SELECTION_INVALID", 422) from exc


def register_context(
    db: Session,
    actor: User,
    draft_id: str,
    scope_revision: int,
    *,
    storage_root: Path,
    match_selection: str = "",
    estimate_selection: str = "",
) -> dict[str, Any]:
    """No matching, rate calculation, history writes or implicit artifact selection."""
    get_draft(db, actor, draft_id)
    scope = read_revision(db, actor, draft_id, scope_revision)
    result: dict[str, Any] = {
        "targets": {},
        "match_choices": [],
        "estimate_choices": [],
        "match_selection": match_selection,
        "estimate_selection": estimate_selection,
        "warnings": [],
        "evidence_refs": [
            dict(ref, status=reference_status(ref, scope["content"]))
            for ref in scope.get("evidence_refs", [])
        ],
        "readiness": hierarchy_review(scope["content"]),
    }
    if has_permission(actor, "technical:read"):
        result["match_choices"] = [
            {
                "value": f"{item.id}:{item.latest_revision}",
                "label": (
                    f"Review {item.id[:8]} / revision {item.latest_revision}"
                    f" / Scope {item.scope_revision}"
                ),
            }
            for item in matches.list_matches(db, actor, draft_id)
        ]
    if has_permission(actor, "estimate:read"):
        result["estimate_choices"] = [
            {
                "value": f"{item.id}:{item.latest_revision}",
                "label": (
                    f"Estimate {item.id[:8]} / revision {item.latest_revision}"
                    f" / Scope {item.scope_revision}"
                ),
            }
            for item in estimates.list_estimates(db, actor, draft_id)
        ]
    selected_match = None
    if match_selection:
        identity, revision = _selection(match_selection)
        selected_match = matches.read_match_revision(db, actor, draft_id, identity, revision)
        if not any(item["value"] == match_selection for item in result["match_choices"]):
            result["match_choices"].append(
                {
                    "value": match_selection,
                    "label": f"Selected historical review {identity[:8]} / revision {revision}",
                }
            )
        stale = matches.match_staleness(
            db, actor, draft_id, identity, revision, storage_root=storage_root
        )
        if selected_match["scope"]["sha256"] != scope["sha256"]:
            stale.append("Selected review uses a different Scope revision.")
        target = selected_match["target"]
        key = (
            ("service:" + target["service_id"])
            if target["service_id"]
            else ("blank_opening:" + target["opening_id"] if target["blank_opening"] else "")
        )
        decisions = {item["candidate_id"]: item["decision"] for item in selected_match["decisions"]}
        labels = {"keep": "kept for review", "reject": "rejected", "unreviewed": "awaiting review"}
        candidates = [
            f"{item['system_id']} / {item['variant_id']} "
            f"({labels[decisions[item['candidate_id']]]})"
            for item in selected_match["candidates"]
        ]
        blockers = sorted(
            {code for item in selected_match["candidates"] for code in item["blockers"]}
        )
        if key:
            result["targets"].setdefault(key, {}).update(
                system_opening_id=target["opening_id"],
                system_text="; ".join(candidates) or "No candidates retained",
                system_status="Stale" if stale else "Unapproved candidate review",
                system_warnings=stale + blockers,
                system_url=f"/scopes/{draft_id}/system-matches/{identity}?revision={revision}",
                status="Stale" if stale else "Unapproved",
            )
        result["warnings"].extend(stale)
    if estimate_selection:
        identity, revision = _selection(estimate_selection)
        estimate = estimates.read_estimate_revision(db, actor, draft_id, identity, revision)
        if not any(item["value"] == estimate_selection for item in result["estimate_choices"]):
            result["estimate_choices"].append(
                {
                    "value": estimate_selection,
                    "label": f"Selected historical estimate {identity[:8]} / revision {revision}",
                }
            )
        stale = estimates.estimate_staleness(
            db, actor, draft_id, identity, revision, storage_root=storage_root
        )
        if estimate["scope"]["sha256"] != scope["sha256"]:
            stale.append("Selected estimate uses a different Scope revision.")
        if selected_match and (
            estimate["system_match"] is None
            or estimate["system_match"]["sha256"] != selected_match["sha256"]
        ):
            stale.append("The selected estimate is not bound to the displayed system review.")
        for line in estimate["lines"]:
            amount = line["subtotal_ex_tax"]
            price = (
                "Omitted"
                if line["status"] == "omitted"
                else "Not priced"
                if amount is None
                else f"{estimate['currency']} {amount} ex tax"
            )
            result["targets"].setdefault(line["recovery_key"], {}).update(
                price_text=price,
                price_status="Stale" if stale else "Saved Draft amount",
                price_warnings=stale,
                rate_method=estimate["provenance"],
                price_url=f"/scopes/{draft_id}/estimates/{identity}?revision={revision}",
            )
        result["warnings"].extend(stale)
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result
