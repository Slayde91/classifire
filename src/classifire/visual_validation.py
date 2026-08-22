from __future__ import annotations

from typing import Any

VISUAL_VALIDATOR_ISSUE_CODES = frozenset(
    {
        "MISSED_BARRIER",
        "WRONG_BARRIER",
        "WRONG_BARRIER_PLANE",
        "MISSED_OPENING",
        "DUPLICATED_OPENING",
        "OVER_SPLIT_OPENING",
        "OVER_MERGED_OPENING",
        "MISSED_SERVICE",
        "INVENTED_SERVICE",
        "WRONG_SERVICE_CLASS",
        "WRONG_SERVICE_GROUPING",
        "WRONG_SERVICE_QUANTITY",
        "WRONG_SERVICE_OPENING_LINK",
        "PHOTO_DUPLICATE_COUNTED",
        "OPPOSITE_FACE_DOUBLE_COUNTED",
        "UNSUPPORTED_MATERIAL",
        "UNSUPPORTED_DIMENSION",
        "UNSUPPORTED_SIZE_OR_QUANTITY",
    }
)

VISUAL_VALIDATOR_VERDICTS = frozenset({"APPROVED", "REJECTED", "BLOCKED"})

_OPENING_ADD_ISSUES = frozenset(
    {
        "MISSED_OPENING",
        "OVER_MERGED_OPENING",
    }
)
_OPENING_REMOVE_ISSUES = frozenset(
    {
        "DUPLICATED_OPENING",
        "OVER_SPLIT_OPENING",
    }
)
_SERVICE_ADD_ISSUES = frozenset(
    {
        "MISSED_SERVICE",
        "WRONG_SERVICE_GROUPING",
    }
)
_SERVICE_REMOVE_ISSUES = frozenset(
    {
        "INVENTED_SERVICE",
        "WRONG_SERVICE_GROUPING",
    }
)
_BARRIER_FIELD_ISSUES = frozenset(
    {
        "MISSED_BARRIER",
        "WRONG_BARRIER",
        "WRONG_BARRIER_PLANE",
    }
)
_OPENING_BARRIER_FIELDS = frozenset(
    {
        "substrate_type",
        "substrate_plane",
        "orientation",
    }
)
_SERVICE_LINK_FIELDS = frozenset(
    {
        "primary_opening_code",
        "opening_codes",
        "link_type",
    }
)
_SERVICE_CLASS_FIELDS = frozenset({"service_type"})
_SERVICE_MATERIAL_FIELDS = frozenset(
    {
        "material",
        "insulation_type",
    }
)


def proposal_topology_counts(proposal: Any) -> tuple[int, int]:
    if not isinstance(proposal, dict):
        return (-1, -1)

    openings = proposal.get("openings")
    services = proposal.get("services")
    return (
        len(openings) if isinstance(openings, list) else -1,
        len(services) if isinstance(services, list) else -1,
    )


def validate_visual_validator_payload(
    payload: Any,
    proposal: Any,
) -> list[str]:
    """Validate one independent visual-validator receipt.

    The gate is deliberately structural and fail-closed. It does not decide whether
    the validator's visual conclusion is correct; it ensures a malformed or internally
    contradictory validator response can never be treated as approval.
    """

    issues: list[str] = []
    if not isinstance(payload, dict):
        issues.append("validator receipt must be an object")
        payload = {}
    if not isinstance(proposal, dict):
        issues.append("proposal must be an object")
        proposal = {}

    verdict = str(payload.get("verdict") or "").strip().upper()
    if verdict not in VISUAL_VALIDATOR_VERDICTS:
        issues.append(f"validator verdict must be one of {sorted(VISUAL_VALIDATOR_VERDICTS)}")

    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        issues.append("validator issues must be an array")
        raw_issues = []

    for index, item in enumerate(raw_issues, start=1):
        if not isinstance(item, dict):
            issues.append(f"validator issue {index} is not an object")
            continue
        code = str(item.get("code") or "").strip().upper()
        detail = str(item.get("detail") or "").strip()
        if code not in VISUAL_VALIDATOR_ISSUE_CODES:
            issues.append(f"validator issue {index} has unsupported code {code!r}")
        if not detail:
            issues.append(f"validator issue {index} has no detail")
        refs = item.get("evidence_refs")
        if refs is not None and not isinstance(refs, list):
            issues.append(f"validator issue {index} evidence_refs must be an array when supplied")

    expected_openings, expected_services = proposal_topology_counts(proposal)
    for field_name, expected in (
        ("observed_opening_count", expected_openings),
        ("observed_service_group_count", expected_services),
    ):
        value = payload.get(field_name)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            issues.append(f"{field_name} must be a non-negative integer or null")
            continue
        if verdict == "APPROVED" and expected >= 0 and value != expected:
            issues.append(
                f"APPROVED validator count contradiction: {field_name}={value}, proposal={expected}"
            )

    limitations = payload.get("limitations")
    if limitations is not None and not isinstance(limitations, list):
        issues.append("validator limitations must be an array when supplied")

    if verdict == "APPROVED" and raw_issues:
        issues.append("APPROVED validator receipt cannot contain blocking issues")
    if verdict == "REJECTED" and not raw_issues:
        issues.append("REJECTED validator receipt must contain at least one issue")
    if verdict == "BLOCKED" and not raw_issues and not limitations:
        issues.append("BLOCKED validator receipt must state an issue or limitation")

    return list(dict.fromkeys(issues))


def visual_validator_approved(payload: Any, proposal: Any) -> bool:
    return (
        isinstance(payload, dict)
        and str(payload.get("verdict") or "").strip().upper() == "APPROVED"
        and not validate_visual_validator_payload(payload, proposal)
    )


def visual_validator_issue_codes(payload: Any) -> frozenset[str]:
    """Return the supported structured issue codes in one Validator receipt."""

    if not isinstance(payload, dict):
        return frozenset()

    raw_issues = payload.get("issues")
    if not isinstance(raw_issues, list):
        return frozenset()

    return frozenset(
        code
        for item in raw_issues
        if isinstance(item, dict)
        for code in [str(item.get("code") or "").strip().upper()]
        if code in VISUAL_VALIDATOR_ISSUE_CODES
    )


def _proposal_rows_by_code(
    proposal: dict[str, Any],
    *,
    collection: str,
    code_field: str,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    raw_rows = proposal.get(collection)
    if not isinstance(raw_rows, list):
        return {}, [f"corrected proposal {collection} must be an array"]

    rows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, item in enumerate(raw_rows, start=1):
        if not isinstance(item, dict):
            errors.append(f"corrected proposal {collection} item {index} is not an object")
            continue
        code = str(item.get(code_field) or "").strip()
        if not code:
            errors.append(f"corrected proposal {collection} item {index} has no {code_field}")
            continue
        if code in rows:
            errors.append(f"corrected proposal {collection} code {code!r} is duplicated")
            continue
        rows[code] = item
    return rows, errors


def _normalised_topology_value(field: str, value: Any) -> Any:
    if field == "opening_codes" and isinstance(value, list):
        return tuple(sorted(str(item).strip() for item in value))
    return value


def validate_visual_correction_scope(
    previous: Any,
    corrected: Any,
    validator: Any,
) -> list[str]:
    """Reject Physical corrections outside the Validator's structured issues.

    This guard deliberately evaluates semantic topology deltas rather than raw
    counts alone. Stable Opening and Service codes identify the entities that
    survived a correction pass; additions, removals, links, classes, material,
    dimensions and quantities then require their own explicit authority.
    """

    boundary_errors: list[str] = []
    if not isinstance(previous, dict):
        boundary_errors.append("previous proposal must be an object")
    if not isinstance(corrected, dict):
        boundary_errors.append("corrected proposal must be an object")
    if not isinstance(validator, dict):
        boundary_errors.append("validator receipt must be an object")
    if boundary_errors:
        return boundary_errors

    issue_codes = visual_validator_issue_codes(validator)
    if not issue_codes:
        return ["physical correction requires at least one supported structured validator issue"]
    if issue_codes == {"UNSUPPORTED_SIZE_OR_QUANTITY"}:
        return [
            "UNSUPPORTED_SIZE_OR_QUANTITY is ambiguous; Validator must use "
            "UNSUPPORTED_DIMENSION or WRONG_SERVICE_QUANTITY before Physical correction"
        ]

    previous_openings, previous_opening_errors = _proposal_rows_by_code(
        previous,
        collection="openings",
        code_field="opening_code",
    )
    corrected_openings, corrected_opening_errors = _proposal_rows_by_code(
        corrected,
        collection="openings",
        code_field="opening_code",
    )
    previous_services, previous_service_errors = _proposal_rows_by_code(
        previous,
        collection="services",
        code_field="service_code",
    )
    corrected_services, corrected_service_errors = _proposal_rows_by_code(
        corrected,
        collection="services",
        code_field="service_code",
    )

    errors = [
        *previous_opening_errors,
        *corrected_opening_errors,
        *previous_service_errors,
        *corrected_service_errors,
    ]
    if errors:
        return list(dict.fromkeys(errors))

    may_add_openings = bool(issue_codes & _OPENING_ADD_ISSUES)
    may_remove_openings = bool(issue_codes & _OPENING_REMOVE_ISSUES)
    may_add_services = bool(issue_codes & _SERVICE_ADD_ISSUES)
    may_remove_services = bool(issue_codes & _SERVICE_REMOVE_ISSUES)
    may_change_links = (
        "WRONG_SERVICE_OPENING_LINK" in issue_codes or may_add_openings or may_remove_openings
    )
    may_change_barrier_fields = bool(issue_codes & _BARRIER_FIELD_ISSUES)
    may_change_class = "WRONG_SERVICE_CLASS" in issue_codes
    may_change_material = "UNSUPPORTED_MATERIAL" in issue_codes
    may_change_dimensions = bool(
        issue_codes
        & {
            "UNSUPPORTED_DIMENSION",
        }
    )
    may_change_quantity = bool(
        issue_codes
        & {
            "WRONG_SERVICE_GROUPING",
            "WRONG_SERVICE_QUANTITY",
        }
    )
    may_change_opening_type = (
        may_add_services or may_remove_services or may_add_openings or may_remove_openings
    )

    added_openings = sorted(corrected_openings.keys() - previous_openings.keys())
    removed_openings = sorted(previous_openings.keys() - corrected_openings.keys())
    added_services = sorted(corrected_services.keys() - previous_services.keys())
    removed_services = sorted(previous_services.keys() - corrected_services.keys())

    if added_openings and not may_add_openings:
        errors.append(
            "validator issues do not authorize added Openings: " + ", ".join(added_openings)
        )
    if removed_openings and not may_remove_openings:
        errors.append(
            "validator issues do not authorize removed Openings: " + ", ".join(removed_openings)
        )
    if added_services and not may_add_services:
        errors.append(
            "validator issues do not authorize added Services: " + ", ".join(added_services)
        )
    if removed_services and not may_remove_services:
        errors.append(
            "validator issues do not authorize removed Services: " + ", ".join(removed_services)
        )

    for code in sorted(previous_openings.keys() & corrected_openings.keys()):
        before = previous_openings[code]
        after = corrected_openings[code]
        fields = set(before) | set(after)
        for field in sorted(fields - {"opening_code"}):
            if _normalised_topology_value(field, before.get(field)) == _normalised_topology_value(
                field, after.get(field)
            ):
                continue
            if field in _OPENING_BARRIER_FIELDS and may_change_barrier_fields:
                continue
            if field.endswith("_mm") and may_change_dimensions:
                continue
            if field == "opening_type" and may_change_opening_type:
                continue
            if field in {
                "confidence",
                "evidence_status",
                "external_defect_id",
                "frl",
                "location",
                "notes",
                "source_reference",
            }:
                continue
            errors.append(
                f"validator issues do not authorize Opening {code} field {field!r} to change"
            )

    for code in sorted(previous_services.keys() & corrected_services.keys()):
        before = previous_services[code]
        after = corrected_services[code]
        fields = set(before) | set(after)
        for field in sorted(fields - {"service_code"}):
            if _normalised_topology_value(field, before.get(field)) == _normalised_topology_value(
                field, after.get(field)
            ):
                continue
            if field in _SERVICE_LINK_FIELDS and may_change_links:
                continue
            if field in _SERVICE_CLASS_FIELDS and may_change_class:
                continue
            if field in _SERVICE_MATERIAL_FIELDS and may_change_material:
                continue
            if field.endswith("_mm") and may_change_dimensions:
                continue
            if field == "quantity" and may_change_quantity:
                continue
            if field in {
                "confidence",
                "evidence_status",
                "notes",
                "relationship_status",
                "source_reference",
            }:
                continue
            errors.append(
                f"validator issues do not authorize Service {code} field {field!r} to change"
            )

    return list(dict.fromkeys(errors))
