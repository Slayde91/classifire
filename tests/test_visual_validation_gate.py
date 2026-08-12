from __future__ import annotations

from classifire.visual_validation import (
    validate_visual_validator_payload,
    visual_validator_approved,
)


def _proposal() -> dict:
    return {
        "openings": [
            {"opening_code": "O-A"},
            {"opening_code": "O-B"},
        ],
        "services": [
            {"service_code": "S-A"},
            {"service_code": "S-B"},
            {"service_code": "S-C"},
        ],
    }


def test_approved_visual_receipt_requires_matching_counts_and_no_issues() -> None:
    payload = {
        "verdict": "APPROVED",
        "observed_opening_count": 2,
        "observed_service_group_count": 3,
        "issues": [],
        "limitations": [],
    }
    assert validate_visual_validator_payload(payload, _proposal()) == []
    assert visual_validator_approved(payload, _proposal()) is True


def test_approved_visual_receipt_fails_closed_on_count_contradiction() -> None:
    payload = {
        "verdict": "APPROVED",
        "observed_opening_count": 1,
        "observed_service_group_count": 3,
        "issues": [],
        "limitations": [],
    }
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("count contradiction" in issue for issue in issues)
    assert visual_validator_approved(payload, _proposal()) is False


def test_rejected_visual_receipt_requires_structured_issue() -> None:
    payload = {
        "verdict": "REJECTED",
        "observed_opening_count": 3,
        "observed_service_group_count": 3,
        "issues": [
            {
                "code": "MISSED_OPENING",
                "detail": "A separate blank core hole is visible to the left of the service opening.",
                "evidence_refs": ["P001-I01"],
            }
        ],
        "limitations": [],
    }
    assert validate_visual_validator_payload(payload, _proposal()) == []
    assert visual_validator_approved(payload, _proposal()) is False


def test_unknown_issue_code_cannot_pass_the_gate() -> None:
    payload = {
        "verdict": "REJECTED",
        "issues": [{"code": "MODEL_FEELS_WRONG", "detail": "Unsupported free-form code."}],
    }
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("unsupported code" in issue for issue in issues)


def test_blocked_visual_receipt_must_explain_blocker() -> None:
    payload = {"verdict": "BLOCKED", "issues": [], "limitations": []}
    issues = validate_visual_validator_payload(payload, _proposal())
    assert any("must state an issue or limitation" in issue for issue in issues)
