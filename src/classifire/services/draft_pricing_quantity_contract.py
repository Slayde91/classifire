"""Strict contract for a project quantity tied to saved Scope and a frozen recipe."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .draft_system_match_contract import canonical, digest

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-QUANTITY-BASIS-v1"
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


def quantity_basis_definition(
    *,
    draft_scope_id: str,
    scope: dict[str, Any],
    technical_release: dict[str, Any],
    technical_target: dict[str, Any],
    recipe_link: dict[str, Any],
    requirement: dict[str, Any],
    quantity: str,
    unit: str,
    evidence_state: str,
    review_reason: str,
) -> dict[str, Any]:
    value = {
        "schema_version": SCHEMA,
        "draft_scope_id": draft_scope_id,
        "scope": scope,
        "technical_release": technical_release,
        "technical_target": technical_target,
        "recipe_link": recipe_link,
        "requirement": requirement,
        "quantity_basis": {
            "source": "scope_service",
            "quantity": quantity,
            "unit": unit,
            "evidence_state": evidence_state,
            "review_reason": review_reason.strip(),
        },
        "effects": dict(EFFECTS),
    }
    validate_quantity_basis_definition(value)
    return value


def quantity_basis_envelope(
    definition: dict[str, Any], *, basis_id: str, reviewed_by_id: str, reviewed_at: datetime
) -> dict[str, Any]:
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ValueError("reviewed_at must include a timezone")
    value = {
        "schema_version": SCHEMA,
        "basis_id": basis_id,
        "reviewed_at": reviewed_at.astimezone(UTC).isoformat(),
        "reviewed_by_id": reviewed_by_id,
        "definition": definition,
        "definition_sha256": digest(definition),
    }
    validate_quantity_basis_envelope(value)
    return value


def validate_quantity_basis_definition(value: Any) -> None:
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema_version",
            "draft_scope_id",
            "scope",
            "technical_release",
            "technical_target",
            "recipe_link",
            "requirement",
            "quantity_basis",
            "effects",
        }
        or value["schema_version"] != SCHEMA
    ):
        raise ValueError("quantity basis definition")
    _identifier(value["draft_scope_id"])
    scope = value["scope"]
    if type(scope) is not dict or set(scope) != {"revision", "sha256", "service"}:
        raise ValueError("quantity scope")
    if type(scope["revision"]) is not int or scope["revision"] < 1:
        raise ValueError("quantity scope revision")
    _hash(scope["sha256"])
    service = scope["service"]
    if type(service) is not dict or set(service) != {"id", "label", "quantity", "unit", "state"}:
        raise ValueError("quantity service")
    _identifier(service["id"])
    _bounded(service["label"], 200)
    _decimal(service["quantity"], service["unit"])
    if service["state"] not in ("Confirmed", "Inferred", "Provisional", "Unresolved"):
        raise ValueError("quantity service state")
    release = value["technical_release"]
    if type(release) is not dict or set(release) != {"id", "version", "sha256"}:
        raise ValueError("quantity release")
    _identifier(release["id"])
    _bounded(release["version"], 50)
    _hash(release["sha256"])
    target = value["technical_target"]
    if type(target) is not dict or set(target) != {
        "id",
        "snapshot_sha256",
        "recipe_snapshot_sha256",
    }:
        raise ValueError("quantity target")
    _identifier(target["id"])
    _hash(target["snapshot_sha256"])
    _hash(target["recipe_snapshot_sha256"])
    link = value["recipe_link"]
    if type(link) is not dict or set(link) != {"id", "sha256"}:
        raise ValueError("quantity recipe link")
    _identifier(link["id"])
    _hash(link["sha256"])
    requirement = value["requirement"]
    if type(requirement) is not dict or set(requirement) != {
        "id",
        "kind",
        "path",
        "label",
        "source_value",
        "source_value_sha256",
    }:
        raise ValueError("quantity requirement")
    _hash(requirement["id"])
    if requirement["kind"] not in ("component", "activity"):
        raise ValueError("quantity requirement kind")
    _bounded(requirement["path"], 500)
    _bounded(requirement["label"], 1000)
    _hash(requirement["source_value_sha256"])
    if digest(requirement["source_value"]) != requirement["source_value_sha256"]:
        raise ValueError("quantity requirement source")
    basis = value["quantity_basis"]
    if type(basis) is not dict or set(basis) != {
        "source",
        "quantity",
        "unit",
        "evidence_state",
        "review_reason",
    }:
        raise ValueError("quantity basis")
    if basis["source"] != "scope_service" or basis["evidence_state"] != service["state"]:
        raise ValueError("quantity source")
    _decimal(basis["quantity"], basis["unit"])
    if (basis["quantity"], basis["unit"]) != (service["quantity"], service["unit"]):
        raise ValueError("quantity mismatch")
    _bounded(basis["review_reason"], 4000)
    if value["effects"] != EFFECTS or len(canonical(value)) > 524288:
        raise ValueError("quantity effects or size")


def validate_quantity_basis_envelope(value: Any) -> None:
    if (
        type(value) is not dict
        or set(value)
        != {
            "schema_version",
            "basis_id",
            "reviewed_at",
            "reviewed_by_id",
            "definition",
            "definition_sha256",
        }
        or value["schema_version"] != SCHEMA
    ):
        raise ValueError("quantity basis envelope")
    _identifier(value["basis_id"])
    _identifier(value["reviewed_by_id"])
    try:
        timestamp = datetime.fromisoformat(value["reviewed_at"])
    except (TypeError, ValueError) as exc:
        raise ValueError("quantity basis timestamp") from exc
    if timestamp.tzinfo is None or timestamp.utcoffset() != UTC.utcoffset(timestamp):
        raise ValueError("quantity basis timestamp")
    validate_quantity_basis_definition(value["definition"])
    _hash(value["definition_sha256"])
    if value["definition_sha256"] != digest(value["definition"]):
        raise ValueError("quantity definition hash")


def _decimal(value: Any, unit: Any) -> None:
    if type(value) is not str or type(unit) is not str or unit not in ("each", "m", "mm"):
        raise ValueError("quantity value")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("quantity value") from exc
    if (
        not number.is_finite()
        or number <= 0
        or number > Decimal("1000000000")
        or format(number.normalize(), "f") != value
    ):
        raise ValueError("quantity value")
    if unit == "each" and number != number.to_integral_value():
        raise ValueError("quantity each")


def _identifier(value: Any) -> None:
    _bounded(value, 64)


def _bounded(value: Any, maximum: int) -> None:
    if type(value) is not str or value != value.strip() or not 1 <= len(value) <= maximum:
        raise ValueError("quantity text")


def _hash(value: Any) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value)
    ):
        raise ValueError("quantity hash")


__all__ = [
    "EFFECTS",
    "SCHEMA",
    "quantity_basis_definition",
    "quantity_basis_envelope",
    "validate_quantity_basis_definition",
    "validate_quantity_basis_envelope",
]
