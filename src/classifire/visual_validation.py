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


def proposal_topology_counts(proposal: dict[str, Any]) -> tuple[int, int]:
    openings = proposal.get("openings")
    services = proposal.get("services")
    return (
        len(openings) if isinstance(openings, list) else -1,
        len(services) if isinstance(services, list) else -1,
    )


def validate_visual_validator_payload(
    payload: dict[str, Any],
    proposal: dict[str, Any],
) -> list[str]:
    """Validate one independent visual-validator receipt.

    The gate is deliberately structural and fail-closed. It does not decide whether
    the validator's visual conclusion is correct; it ensures a malformed or internally
    contradictory validator response can never be treated as approval.
    """

    issues: list[str] = []
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


def visual_validator_approved(payload: dict[str, Any], proposal: dict[str, Any]) -> bool:
    return (
        str(payload.get("verdict") or "").strip().upper() == "APPROVED"
        and not validate_visual_validator_payload(payload, proposal)
    )
