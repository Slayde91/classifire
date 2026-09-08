"""Deterministic, bounded snapshots of technical component and activity recipes."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from ..models import TechnicalVariant

SCHEMA = "CLASSIFIRE-TECHNICAL-RECIPE-SNAPSHOT-v1"
MAX_REQUIREMENTS = 100
MAX_SERIALIZED_BYTES = 131072


class TechnicalRecipeSnapshotError(ValueError):
    """Raised when mutable recipe data cannot be frozen safely."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError) as exc:
        raise TechnicalRecipeSnapshotError("recipe fields must be canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def technical_recipe_snapshot(variant: TechnicalVariant) -> dict[str, Any]:
    """Freeze recipe fields and expose stable, individually reviewable requirements."""
    components = copy.deepcopy(variant.component_requirements)
    labour = copy.deepcopy(variant.labour_requirements)
    requirements: list[dict[str, Any]] = []
    if components is not None and not isinstance(components, (dict, list)):
        raise TechnicalRecipeSnapshotError("component_requirements must be an object or list")
    if labour is not None and not isinstance(labour, list):
        raise TechnicalRecipeSnapshotError("labour_requirements must be a list")
    if len(components or []) + len(labour or []) > MAX_REQUIREMENTS:
        raise TechnicalRecipeSnapshotError("too many recipe requirements")
    if isinstance(components, dict):
        for key in sorted(components):
            if not isinstance(key, str) or not key.strip() or len(key) > 200:
                raise TechnicalRecipeSnapshotError("component requirement key is invalid")
            requirements.append(
                _requirement(
                    "component", f"/component_requirements/{_pointer(key)}", key, components[key]
                )
            )
    elif isinstance(components, list):
        for index, value in enumerate(components):
            requirements.append(
                _requirement(
                    "component", f"/component_requirements/{index}", f"Component {index + 1}", value
                )
            )
    if isinstance(labour, list):
        for index, value in enumerate(labour):
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                raise TechnicalRecipeSnapshotError("labour requirement is invalid")
            requirements.append(
                _requirement("activity", f"/labour_requirements/{index}", value.strip(), value)
            )
    source_fields = {"component_requirements": components, "labour_requirements": labour}
    if len(_canonical(source_fields)) > MAX_SERIALIZED_BYTES:
        raise TechnicalRecipeSnapshotError("recipe fields are too large")
    body = {
        "schema": SCHEMA,
        "availability": "available" if requirements else "unavailable",
        "source_fields": source_fields,
        "source_fields_sha256": _digest(source_fields),
        "requirements": requirements,
    }
    body["sha256"] = _digest(body)
    return body


def _requirement(kind: str, path: str, label: str, value: Any) -> dict[str, Any]:
    if len(_canonical(value)) > 16384:
        raise TechnicalRecipeSnapshotError("recipe requirement is too large")
    identity = {"kind": kind, "path": path, "label": label, "source_value_sha256": _digest(value)}
    return {"id": _digest(identity), **identity, "source_value": value}


def validate_technical_recipe_snapshot(value: object) -> dict[str, Any]:
    """Validate exact schema and hashes, returning a defensive copy."""
    keys = {
        "schema",
        "availability",
        "source_fields",
        "source_fields_sha256",
        "requirements",
        "sha256",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise TechnicalRecipeSnapshotError("recipe snapshot shape is invalid")
    candidate = copy.deepcopy(value)
    supplied = candidate.pop("sha256")
    if candidate.get("schema") != SCHEMA or supplied != _digest(candidate):
        raise TechnicalRecipeSnapshotError("recipe snapshot hash is invalid")
    fields = candidate.get("source_fields")
    if not isinstance(fields, dict) or set(fields) != {
        "component_requirements",
        "labour_requirements",
    }:
        raise TechnicalRecipeSnapshotError("recipe source fields are invalid")
    if candidate.get("source_fields_sha256") != _digest(fields):
        raise TechnicalRecipeSnapshotError("recipe source fields hash is invalid")
    requirements = candidate.get("requirements")
    if not isinstance(requirements, list) or len(requirements) > MAX_REQUIREMENTS:
        raise TechnicalRecipeSnapshotError("recipe requirements are invalid")
    if candidate.get("availability") != ("available" if requirements else "unavailable"):
        raise TechnicalRecipeSnapshotError("recipe availability is invalid")
    if _snapshot_from_fields(fields) != value:
        raise TechnicalRecipeSnapshotError("recipe snapshot content is invalid")
    return copy.deepcopy(value)


def _snapshot_from_fields(fields: dict[str, Any]) -> dict[str, Any]:
    class _Variant:
        component_requirements = fields["component_requirements"]
        labour_requirements = fields["labour_requirements"]

    return technical_recipe_snapshot(_Variant())  # type: ignore[arg-type]


__all__ = [
    "SCHEMA",
    "TechnicalRecipeSnapshotError",
    "technical_recipe_snapshot",
    "validate_technical_recipe_snapshot",
]
