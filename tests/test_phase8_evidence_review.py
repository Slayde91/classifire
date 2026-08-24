from __future__ import annotations

import json
from types import SimpleNamespace

from classifire.services.phase8_evidence_review import (
    EVIDENCE_REVIEW_REQUEST_SCHEMA,
    build_blocked_visual_evidence_review_request,
)
from classifire.services.phase8_visual_proposal import VISUAL_PROPOSAL_BLOCKED


def test_unresolved_observation_alone_creates_content_safe_review_request() -> None:
    visual_result = SimpleNamespace(
        status=VISUAL_PROPOSAL_BLOCKED,
        blind_inventory={
            "candidate_openings": [
                {
                    "candidate_id": "V-O-001",
                    "detail": "Possible opening relationship in the wide view.",
                    "evidence_refs": ["E-001", "TOKEN=do-not-copy"],
                }
            ],
            "candidate_services": [],
            "unresolved_candidates": [],
            "limitations": [],
        },
        validator={
            "verdict": "BLOCKED",
            "issues": [
                {
                    "code": "MISSED_OPENING",
                    "detail": "HTTPS://example.invalid/signed",
                    "evidence_refs": ["E-001"],
                }
            ],
            "limitations": ["Authorization: Bearer secret"],
            "blind_reconciliation": [
                {
                    "blind_candidate_id": "V-O-001",
                    "disposition": "UNRESOLVED",
                    "proposal_refs": [],
                    "detail": "Confirm whether the views show the same opening.",
                    "evidence_refs": ["E-001", "x-amz-signature=secret"],
                }
            ],
        },
    )

    request = build_blocked_visual_evidence_review_request(
        package_id="package-001",
        approval_reference="approval-001",
        visual_result=visual_result,
        controller_receipt_file_sha256="A" * 64,
        proposal_file_sha256="B" * 64,
    )

    assert request is not None
    assert request["schema"] == EVIDENCE_REVIEW_REQUEST_SCHEMA
    assert request["review_items"] == []
    assert request["unresolved_blind_observations"] == [
        {
            "blind_candidate_id": "V-O-001",
            "kind": "opening",
            "detail": "Possible opening relationship in the wide view.",
            "evidence_refs": ["E-001"],
            "validator_detail": "Confirm whether the views show the same opening.",
            "validator_evidence_refs": ["E-001"],
        }
    ]
    assert request["controller_receipt_file_sha256"] == "A" * 64
    assert request["proposal_file_sha256"] == "B" * 64
    rendered = json.dumps(request).casefold()
    for marker in ("https://", "authorization:", "bearer ", "token=", "x-amz-"):
        assert marker not in rendered


def test_review_request_rejects_unsafe_identity_or_unbound_artifact_hash() -> None:
    visual_result = SimpleNamespace(
        status=VISUAL_PROPOSAL_BLOCKED,
        blind_inventory={
            "candidate_openings": [],
            "candidate_services": [],
            "unresolved_candidates": [],
            "limitations": [],
        },
        validator={
            "verdict": "BLOCKED",
            "issues": [
                {
                    "code": "MISSED_OPENING",
                    "detail": "Review required.",
                    "evidence_refs": ["E-001"],
                }
            ],
            "limitations": [],
            "blind_reconciliation": [],
        },
    )

    assert (
        build_blocked_visual_evidence_review_request(
            package_id="package-001",
            approval_reference="https://example.invalid/approval",
            visual_result=visual_result,
            controller_receipt_file_sha256="A" * 64,
            proposal_file_sha256="B" * 64,
        )
        is None
    )
    assert (
        build_blocked_visual_evidence_review_request(
            package_id="package-001",
            approval_reference="approval-001",
            visual_result=visual_result,
            controller_receipt_file_sha256="not-a-hash",
            proposal_file_sha256="B" * 64,
        )
        is None
    )


def test_review_request_fails_closed_for_malformed_validator_lists() -> None:
    visual_result = SimpleNamespace(
        status=VISUAL_PROPOSAL_BLOCKED,
        blind_inventory={},
        validator={
            "verdict": "BLOCKED",
            "issues": object(),
            "limitations": object(),
            "blind_reconciliation": object(),
        },
    )

    assert (
        build_blocked_visual_evidence_review_request(
            package_id="package-001",
            approval_reference="approval-001",
            visual_result=visual_result,
            controller_receipt_file_sha256="A" * 64,
            proposal_file_sha256="B" * 64,
        )
        is None
    )
