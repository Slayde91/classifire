"""Shared presentation of saved candidate evidence; never computes applicability."""

from __future__ import annotations

from typing import Any

NOTICE = (
    "Unapproved candidate review for the selected target only. Keeping a candidate is "
    "a review preference, not technical approval. Text comparisons and partial numeric "
    "checks do not establish compatibility. Other Scope items remain unassessed. "
    "No Estimate, pricing or release is created by this report."
)


def _rows(value: Any, prefix: str = "") -> list[tuple[str, str]]:
    if isinstance(value, dict) and value:
        return [
            row
            for key, item in value.items()
            for row in _rows(item, (prefix + " / " if prefix else "") + key.replace("_", " "))
        ]
    if isinstance(value, list) and value:
        return [
            row
            for index, item in enumerate(value, 1)
            for row in _rows(item, prefix + " / " + str(index))
        ]
    if value is None or value == "":
        text = "Unknown / unavailable"
    elif isinstance(value, (dict, list)):
        text = "None recorded"
    elif isinstance(value, bool):
        text = "Yes" if value else "No"
    else:
        text = str(value)
    return [(prefix, text)]


def sections(match: dict[str, Any]) -> list[dict[str, Any]]:
    """Present only the already validated immutable match, with every saved field."""
    overview = {
        key: value
        for key, value in match.items()
        if key not in ("scope", "candidates", "decisions", "constraint_review")
    }
    result = [
        {"title": "Saved review and coverage", "rows": [("Authority", NOTICE), *_rows(overview)]}
    ]
    decisions = {item["candidate_id"]: item for item in match["decisions"]}
    labels = {
        "keep": "Kept for review - not approved",
        "reject": "Rejected by reviewer",
        "unreviewed": "Awaiting review",
    }
    for candidate in match["candidates"]:
        decision = decisions[candidate["candidate_id"]]
        detail = dict(candidate)
        detail["comparisons"] = {
            name: {
                "MATCH": "Text overlap only",
                "MISMATCH": "Text differs - review required",
                "UNKNOWN": "Missing or unrecognised text",
            }[value]
            for name, value in candidate["comparisons"].items()
        }
        result.append(
            {
                "title": "Candidate " + candidate["variant_id"],
                "rows": [
                    ("Saved decision", labels[decision["decision"]]),
                    ("Review notes", decision["notes"] or "No review notes supplied"),
                    (
                        "Interpretation",
                        "Captured library fields and source approvals describe the source; "
                        "they do not approve this candidate for the Scope.",
                    ),
                    *_rows(detail),
                ],
            }
        )
    if not match["candidates"]:
        result.append(
            {
                "title": "Candidates",
                "rows": [
                    (
                        "Result",
                        "No candidates retained. "
                        "This does not prove that no suitable system exists.",
                    )
                ],
            }
        )
    review = match.get("constraint_review")
    result.append(
        {
            "title": "Partial measured-limit review",
            "rows": [
                (
                    "Interpretation",
                    "Numeric checks only; complete technical applicability "
                    "and authorized approval remain unresolved.",
                ),
                *_rows(review),
            ]
            if review is not None
            else [("Result", "No measured-limit review saved")],
        }
    )
    return result


def summary(match: dict[str, Any]) -> list[tuple[str, str]]:
    """Human-readable saved findings before detailed provenance."""
    parts = sections(match)
    rows = [("Coverage", "Selected opening/service only; other Scope items are unassessed.")]
    for part in parts[1:-1]:
        for label, value in part["rows"][:2]:
            rows.append((part["title"] + " / " + label, value))
    review = match.get("constraint_review")
    if review is None:
        rows.append(("Measured limits", "No measured-limit review saved"))
    else:
        rows.append(("Measurement evidence", review["inputs"]["measurement_note"]))
        for check in review["checks"]:
            label = check["criterion"].replace("_", " ").title()
            status = check["status"].replace("_", " ")
            lower = check["lower_limit_mm"] or "unknown"
            upper = check["upper_limit_mm"] or "unknown"
            rows.append(
                (label, f"{status}; saved source limits {lower} to {upper} mm. Not approval.")
            )
    return rows
