"""Deterministic partial numeric checks, never a technical compatibility verdict."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

INPUT_FIELDS = ("substrate_thickness_mm", "annular_gap_min_mm", "annular_gap_max_mm")
UNASSESSED = (
    "service_type_material_size_and_instances",
    "substrate_type_and_condition",
    "opening_dimensions_and_configuration",
    "plane_orientation_and_installation_face",
    "insulation_and_seal_depth",
    "fire_rating_and_jurisdiction",
    "spacing_edges_supports_and_fixings",
    "components_exclusions_and_dependencies",
    "shared_openings_and_other_scope_items",
    "authorized_technical_review",
)


def measurement(value: Any) -> Decimal | None:
    if value is None:
        return None
    if (
        type(value) is not str
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,9})(?:\.[0-9]{1,4})?", value) is None
    ):
        raise ValueError("Use nonnegative millimetres with up to four decimal places")
    return Decimal(value)


def validate_inputs(inputs: Any) -> None:
    if type(inputs) is not dict or set(inputs) != {*INPUT_FIELDS, "measurement_note"}:
        raise ValueError("measurement inputs")
    values = {key: measurement(inputs[key]) for key in INPUT_FIELDS}
    thickness = values["substrate_thickness_mm"]
    if thickness is not None and thickness <= 0:
        raise ValueError("Substrate thickness must be positive")
    low, high = values["annular_gap_min_mm"], values["annular_gap_max_mm"]
    if low is not None and high is not None and low > high:
        raise ValueError("Minimum measured gap exceeds maximum measured gap")
    note = inputs["measurement_note"]
    if type(note) is not str or not 1 <= len(note.strip()) <= 2000 or len(note) > 2000:
        raise ValueError("Record where and how these measurements were obtained")


def _limit(value: Any) -> Decimal | None:
    # Source fields are Numeric(18,4), but malformed/ambiguous legacy content stays unknown.
    try:
        return measurement(value)
    except ValueError:
        return None


def _check(
    name: str, observed: tuple[Decimal | None, Decimal | None], limits: tuple[Any, Any], ready: bool
) -> dict[str, Any]:
    low, high = (_limit(value) for value in limits)
    start, end = observed
    result = {
        "criterion": name,
        "status": "unresolved",
        "reason": "measurement_missing",
        "lower_limit_mm": limits[0],
        "upper_limit_mm": limits[1],
    }
    if not ready:
        result["reason"] = "published_source_or_target_unresolved"
    elif low is not None and high is not None and low > high:
        result["reason"] = "source_limits_inconsistent"
    elif start is None or end is None:
        pass
    else:
        if (low is not None and start < low) or (high is not None and end > high):
            result.update(status="outside_limits", reason="measured_value_outside_published_limit")
        elif low is None or high is None:
            result["reason"] = "complete_source_range_missing"
        else:
            result.update(status="within_limits", reason="measured_range_within_inclusive_limits")
    return result


def results(
    candidate: dict[str, Any],
    target: dict[str, Any],
    inputs: dict[str, Any],
    published_fields_sha256: str | None,
) -> list[dict[str, Any]]:
    validate_inputs(inputs)
    fields = candidate["fields"]
    ready = (
        published_fields_sha256 == candidate["fields_sha256"]
        and candidate["source"]["state"] == "bound"
        and target["opening_id"] is not None
    )
    thickness = measurement(inputs["substrate_thickness_mm"])
    return [
        _check(
            "substrate_thickness",
            (thickness, thickness),
            (fields["minimum_substrate_thickness_mm"], fields["maximum_substrate_thickness_mm"]),
            ready,
        ),
        _check(
            "annular_gap_range",
            (measurement(inputs["annular_gap_min_mm"]), measurement(inputs["annular_gap_max_mm"])),
            (fields["annular_gap_min_mm"], fields["annular_gap_max_mm"]),
            ready and target["service_id"] is not None and not target["blank_opening"],
        ),
    ]


def validate_review(review: Any, candidates: list[dict[str, Any]], target: dict[str, Any]) -> None:
    if type(review) is not dict or set(review) != {
        "candidate_id",
        "inputs",
        "published_fields_sha256",
        "checks",
        "unassessed",
        "reviewed_by",
        "reviewed_at",
        "status",
    }:
        raise ValueError("constraint review")
    selected = next(
        (item for item in candidates if item["candidate_id"] == review["candidate_id"]), None
    )
    if selected is None or review["published_fields_sha256"] not in (
        None,
        selected["fields_sha256"],
    ):
        raise ValueError("constraint candidate")
    if review["status"] != "partial_unapproved" or review["unassessed"] != list(UNASSESSED):
        raise ValueError("constraint coverage")
    if review["checks"] != results(
        selected, target, review["inputs"], review["published_fields_sha256"]
    ):
        raise ValueError("constraint result")
    if type(review["reviewed_by"]) is not str or not 1 <= len(review["reviewed_by"]) <= 36:
        raise ValueError("constraint reviewer")
