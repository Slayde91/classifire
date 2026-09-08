"""Strict contract for reviewed Dataset A links to frozen technical recipes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .draft_system_match_contract import canonical, digest

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-RECIPE-LINK-v1"
STATUSES = ("linked", "unresolved")
EVIDENCE_STATES = ("confirmed", "provisional", "unresolved")
UNRESOLVED_FIELDS = (
    "observation",
    "unit",
    "quantity_basis",
    "yield_basis",
    "productivity_basis",
    "recovery_boundary",
)
EFFECTS = {
    "price_calculated": False,
    "proposal_created": False,
    "pricing_library_activated": False,
    "technical_approval_granted": False,
    "technical_applicability_assessed": False,
    "system_match_changed": False,
    "estimate_changed": False,
    "evaluation_performed": False,
    "release_performed": False,
}


def recipe_link_definition(
    *,
    draft_scope_id: str,
    technical_release: dict[str, Any],
    technical_target: dict[str, Any],
    requirement: dict[str, Any],
    observations: list[dict[str, Any]],
    status: str,
    unit: str | None,
    quantity_basis: str | None,
    yield_basis: str | None,
    productivity_basis: str | None,
    recovery_boundary: str | None,
    evidence_state: str,
    review_reason: str,
    unresolved_fields: list[str],
) -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA,
        "draft_scope_id": draft_scope_id,
        "technical_release": technical_release,
        "technical_target": technical_target,
        "requirement": requirement,
        "observations": observations,
        "interpretation": {
            "status": status,
            "unit": _text(unit),
            "quantity_basis": _text(quantity_basis),
            "yield_basis": _text(yield_basis),
            "productivity_basis": _text(productivity_basis),
            "recovery_boundary": _text(recovery_boundary),
            "evidence_state": evidence_state,
            "review_reason": _text(review_reason),
            "unresolved_fields": unresolved_fields,
        },
        "effects": dict(EFFECTS),
    }
    validate_recipe_link_definition(value)
    return value


def recipe_link_envelope(
    definition: dict[str, Any], *, link_id: str, reviewed_by_id: str, reviewed_at: datetime
) -> dict[str, Any]:
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    value = {
        "schema_version": SCHEMA,
        "link_id": link_id,
        "reviewed_at": reviewed_at.astimezone(UTC).isoformat(),
        "reviewed_by_id": reviewed_by_id,
        "definition": definition,
        "definition_sha256": digest(definition),
    }
    validate_recipe_link_envelope(value)
    return value


def validate_recipe_link_definition(value: Any) -> None:
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema_version",
            "draft_scope_id",
            "technical_release",
            "technical_target",
            "requirement",
            "observations",
            "interpretation",
            "effects",
        }
        or value["schema_version"] != SCHEMA
    ):
        raise ValueError("recipe link definition")
    _identifier(value["draft_scope_id"])
    release = value["technical_release"]
    if type(release) is not dict or set(release) != {"id", "version", "sha256"}:
        raise ValueError("recipe release")
    _identifier(release["id"])
    _bounded(release["version"], 50)
    _hash(release["sha256"])
    target = value["technical_target"]
    if type(target) is not dict or set(target) != {
        "id",
        "snapshot_sha256",
        "recipe_snapshot_sha256",
    }:
        raise ValueError("recipe target")
    _identifier(target["id"])
    _hash(target["snapshot_sha256"])
    _hash(target["recipe_snapshot_sha256"])
    requirement = value["requirement"]
    if type(requirement) is not dict or set(requirement) != {
        "id",
        "kind",
        "path",
        "label",
        "source_value",
        "source_value_sha256",
    }:
        raise ValueError("recipe requirement")
    _hash(requirement["id"])
    if requirement["kind"] not in ("component", "activity"):
        raise ValueError("recipe requirement kind")
    _bounded(requirement["path"], 500)
    _bounded(requirement["label"], 1000)
    _hash(requirement["source_value_sha256"])
    if digest(requirement["source_value"]) != requirement["source_value_sha256"]:
        raise ValueError("recipe requirement source")
    observations = value["observations"]
    if type(observations) is not list or not 0 <= len(observations) <= 20:
        raise ValueError("recipe observations")
    if len({item.get("id") for item in observations if type(item) is dict}) != len(observations):
        raise ValueError("duplicate recipe observation")
    for item in observations:
        _observation(item, requirement["kind"])
    interpretation = value["interpretation"]
    if type(interpretation) is not dict or set(interpretation) != {
        "status",
        "unit",
        "quantity_basis",
        "yield_basis",
        "productivity_basis",
        "recovery_boundary",
        "evidence_state",
        "review_reason",
        "unresolved_fields",
    }:
        raise ValueError("recipe interpretation")
    if (
        interpretation["status"] not in STATUSES
        or interpretation["evidence_state"] not in EVIDENCE_STATES
    ):
        raise ValueError("recipe interpretation state")
    for key in ("unit", "quantity_basis", "yield_basis", "productivity_basis", "recovery_boundary"):
        item = interpretation[key]
        if item is not None:
            _bounded(item, 4000)
    _bounded(interpretation["review_reason"], 4000)
    unresolved = interpretation["unresolved_fields"]
    if (
        type(unresolved) is not list
        or unresolved != list(dict.fromkeys(unresolved))
        or any(item not in UNRESOLVED_FIELDS for item in unresolved)
    ):
        raise ValueError("recipe unresolved fields")
    _validate_state(requirement["kind"], observations, interpretation)
    if value["effects"] != EFFECTS or len(canonical(value)) > 524288:
        raise ValueError("recipe effects or size")


def _validate_state(kind: str, observations: list[dict[str, Any]], value: dict[str, Any]) -> None:
    if value["status"] == "unresolved":
        if (
            observations
            or value["evidence_state"] != "unresolved"
            or not value["unresolved_fields"]
        ):
            raise ValueError("unresolved recipe link")
        return
    if not observations or value["evidence_state"] == "unresolved":
        raise ValueError("linked recipe evidence")
    units = {item["unit"] for item in observations}
    if None in units or len(units) != 1 or value["unit"] not in units:
        raise ValueError("recipe unit")
    required = (
        {"quantity_basis", "recovery_boundary"}
        if kind == "component"
        else {"productivity_basis", "recovery_boundary"}
    )
    if any(value[key] is None for key in required):
        raise ValueError("recipe basis")
    if (
        kind == "component"
        and value["yield_basis"] is None
        and "yield_basis" not in value["unresolved_fields"]
    ):
        raise ValueError("recipe yield basis")
    if value["evidence_state"] == "confirmed" and (
        value["unresolved_fields"]
        or any(item["evidence_state"] != "confirmed" for item in observations)
    ):
        raise ValueError("confirmed recipe evidence")


def _observation(value: Any, kind: str) -> None:
    keys = {
        "id",
        "sha256",
        "dataset_id",
        "dataset_version",
        "source_sha256",
        "profile_sha256",
        "decision_sha256",
        "row_sha256",
        "item_kind",
        "normalized_reference",
        "evidence_state",
        "unit",
    }
    if type(value) is not dict or set(value) != keys:
        raise ValueError("recipe observation")
    _identifier(value["id"])
    for key in ("sha256", "source_sha256", "profile_sha256", "decision_sha256", "row_sha256"):
        _hash(value[key])
    _identifier(value["dataset_id"])
    if type(value["dataset_version"]) is not int or value["dataset_version"] < 1:
        raise ValueError("recipe observation version")
    allowed = ("product", "material", "service") if kind == "component" else ("labour", "service")
    if value["item_kind"] not in allowed or value["evidence_state"] not in (
        "confirmed",
        "provisional",
    ):
        raise ValueError("recipe observation kind")
    _bounded(value["normalized_reference"], 300)
    if value["unit"] is not None:
        _bounded(value["unit"], 50)


def validate_recipe_link_envelope(value: Any) -> None:
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema_version",
            "link_id",
            "reviewed_at",
            "reviewed_by_id",
            "definition",
            "definition_sha256",
        }
        or value["schema_version"] != SCHEMA
    ):
        raise ValueError("recipe link envelope")
    _identifier(value["link_id"])
    _identifier(value["reviewed_by_id"])
    try:
        timestamp = datetime.fromisoformat(value["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("recipe link timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("recipe link timestamp")
    validate_recipe_link_definition(value["definition"])
    _hash(value["definition_sha256"])
    if value["definition_sha256"] != digest(value["definition"]):
        raise ValueError("recipe link definition hash")


def _text(value: Any) -> Any:
    return value.strip() if type(value) is str else value


def _identifier(value: Any) -> None:
    _bounded(value, 64)


def _bounded(value: Any, maximum: int) -> None:
    if type(value) is not str or value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError("recipe text")


def _hash(value: Any) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("recipe hash")


__all__ = [
    "EFFECTS",
    "EVIDENCE_STATES",
    "SCHEMA",
    "STATUSES",
    "UNRESOLVED_FIELDS",
    "recipe_link_definition",
    "recipe_link_envelope",
    "validate_recipe_link_definition",
    "validate_recipe_link_envelope",
]
