"""Strict v2 item coverage for hash-bound Phase 8 human reviews.

This module is deliberately a validation-only extension of the existing
proposal-only human review contract.  It has no report/image retrieval,
inference, database, canonical-write, admission, signing, lock, or release
interface.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .phase8_human_adjudicated_proposal import (
    _REVIEW_NOOP_FLAGS,
    HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA,
    HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2,
    HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2,
    HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS,
    Phase8HumanAdjudicatedProposalError,
    _nonblank,
    _require_exact_fields,
    _require_false_flags,
    _require_hash,
)
from .phase8_visual_proposal import canonical_json_sha256


def _validated_request_item_ids(
    review_items: list[dict[str, Any]],
    unresolved: list[dict[str, Any]],
) -> set[str]:
    issue_fields = {"review_item_id", "code", "detail", "evidence_refs", "source"}
    unresolved_fields = {
        "review_item_id",
        "blind_candidate_id",
        "detail",
        "evidence_refs",
        "kind",
        "validator_detail",
        "validator_evidence_refs",
    }
    request_item_ids: set[str] = set()
    for item in review_items:
        value = _require_exact_fields(
            item,
            expected=issue_fields,
            code="HUMAN_REVIEW_REQUEST_ITEM_FIELDS_INVALID",
        )
        item_id = _nonblank(value.get("review_item_id"))
        evidence_refs = value.get("evidence_refs")
        if (
            not item_id
            or (value.get("code") is not None and not _nonblank(value.get("code")))
            or not _nonblank(value.get("detail"))
            or not _nonblank(value.get("source"))
            or not isinstance(evidence_refs, list)
            or any(not _nonblank(reference) for reference in evidence_refs)
        ):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_ITEM_INVALID")
        if item_id in request_item_ids:
            raise Phase8HumanAdjudicatedProposalError(
                "HUMAN_REVIEW_REQUEST_ITEM_DUPLICATE", item_id
            )
        request_item_ids.add(item_id)
    for item in unresolved:
        value = _require_exact_fields(
            item,
            expected=unresolved_fields,
            code="HUMAN_REVIEW_REQUEST_ITEM_FIELDS_INVALID",
        )
        item_id = _nonblank(value.get("review_item_id"))
        list_fields = ("evidence_refs", "validator_evidence_refs")
        required_fields = ("blind_candidate_id", "detail", "kind", "validator_detail")
        if (
            not item_id
            or any(not _nonblank(value.get(field_name)) for field_name in required_fields)
            or any(
                not isinstance(value.get(field_name), list)
                or any(not _nonblank(reference) for reference in value[field_name])
                for field_name in list_fields
            )
        ):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_ITEM_INVALID")
        if item_id in request_item_ids:
            raise Phase8HumanAdjudicatedProposalError(
                "HUMAN_REVIEW_REQUEST_ITEM_DUPLICATE", item_id
            )
        request_item_ids.add(item_id)
    if not request_item_ids:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_CONTENT_INVALID")
    return request_item_ids


def _validated_request(
    request: dict[str, Any],
    *,
    request_sha256: str,
    review: dict[str, Any],
    source_proposal_sha256: str,
    controller_receipt_sha256: str,
    source_controller_status: str,
) -> set[str]:
    expected_fields = {
        "schema",
        "status",
        "package_id",
        "approval_reference",
        "proposal_file_sha256",
        "controller_receipt_file_sha256",
        "visual_proposal_status",
        "review_items",
        "unresolved_blind_observations",
        "reviewer_instructions",
        "canonical_submission_performed",
        "physical_model_lock_created",
        "human_reference_visible_to_inference",
    }
    _require_exact_fields(
        request,
        expected=expected_fields,
        code="HUMAN_REVIEW_REQUEST_FIELDS_INVALID",
    )
    if request.get("schema") != HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2:
        if request.get("schema") == HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA:
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_SCHEMA_REQUEST_MISMATCH")
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_SCHEMA_INVALID")
    if review.get("schema") != HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_SCHEMA_REQUEST_MISMATCH")
    if request.get("status") != "HUMAN_EVIDENCE_REVIEW_REQUIRED":
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_STATUS_INVALID")
    if request.get("package_id") != review.get("package_id") or request.get(
        "approval_reference"
    ) != review.get("approval_reference"):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_IDENTITY_INVALID")
    _require_hash(
        review.get("review_request"),
        key="file_sha256",
        actual=request_sha256,
        code="HUMAN_REVIEW_REQUEST_HASH_MISMATCH",
    )
    if request.get("proposal_file_sha256") != source_proposal_sha256:
        raise Phase8HumanAdjudicatedProposalError(
            "HUMAN_REVIEW_REQUEST_SOURCE_HASH_MISMATCH", "proposal"
        )
    if request.get("controller_receipt_file_sha256") != controller_receipt_sha256:
        raise Phase8HumanAdjudicatedProposalError(
            "HUMAN_REVIEW_REQUEST_SOURCE_HASH_MISMATCH", "controller receipt"
        )
    if request.get("visual_proposal_status") != source_controller_status:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_SOURCE_STATUS_INVALID")
    for field_name in (
        "canonical_submission_performed",
        "physical_model_lock_created",
        "human_reference_visible_to_inference",
    ):
        if request.get(field_name) is not False:
            raise Phase8HumanAdjudicatedProposalError(
                "HUMAN_REVIEW_REQUEST_NOOP_VIOLATION", field_name
            )
    review_items = request.get("review_items")
    unresolved = request.get("unresolved_blind_observations")
    instructions = request.get("reviewer_instructions")
    if (
        not isinstance(review_items, list)
        or not isinstance(unresolved, list)
        or any(not isinstance(item, dict) for item in [*review_items, *unresolved])
        or not review_items
        and not unresolved
        or not isinstance(instructions, list)
        or not instructions
        or any(not _nonblank(item) for item in instructions)
    ):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_CONTENT_INVALID")
    return _validated_request_item_ids(review_items, unresolved)


def _validated_response(
    review: dict[str, Any],
    *,
    expected_request_item_ids: set[str],
) -> tuple[set[str], set[str], int]:
    expected_fields = {
        "schema",
        "status",
        "package_id",
        "approval_reference",
        "review_request",
        "reviewer",
        "defect_decisions",
        "remaining_limitations",
        *_REVIEW_NOOP_FLAGS,
    }
    _require_exact_fields(review, expected=expected_fields, code="HUMAN_REVIEW_FIELDS_INVALID")
    if review.get("schema") != HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_SCHEMA_INVALID")
    if review.get("status") != HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_STATUS_INVALID")
    for field_name in ("package_id", "approval_reference"):
        if not _nonblank(review.get(field_name)):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_IDENTITY_INVALID", field_name)
    request = _require_exact_fields(
        review.get("review_request"),
        expected={"path", "file_sha256"},
        code="HUMAN_REVIEW_REQUEST_INVALID",
    )
    if not _nonblank(request.get("path")) or not _nonblank(request.get("file_sha256")):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_INVALID")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict) or not _nonblank(reviewer.get("name")):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEWER_INVALID")
    limitations = review.get("remaining_limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not _nonblank(item) for item in limitations)
    ):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_LIMITATIONS_INVALID")
    _require_false_flags(review, fields=_REVIEW_NOOP_FLAGS, code="HUMAN_REVIEW_NOOP_VIOLATION")

    decisions = review.get("defect_decisions")
    if not isinstance(decisions, list) or not decisions:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_DECISIONS_INVALID")
    confirmed_items: set[str] = set()
    reviewed_defects: set[str] = set()
    decision_codes: set[str] = set()
    accounted_request_item_ids: set[str] = set()
    for index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_DECISION_INVALID", str(index))
        defect_id = _nonblank(decision.get("external_defect_id"))
        review_item = _nonblank(decision.get("review_item"))
        outcome = _nonblank(decision.get("outcome"))
        request_item_ids = decision.get("request_item_ids")
        if (
            not defect_id
            or not review_item
            or outcome not in {"CONFIRMED", "UNRESOLVED"}
            or not isinstance(request_item_ids, list)
            or not request_item_ids
            or any(not _nonblank(item_id) for item_id in request_item_ids)
            or len(request_item_ids) != len(set(request_item_ids))
        ):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_DECISION_INVALID", str(index))
        if review_item in decision_codes:
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_ITEM_DUPLICATE", review_item)
        decision_codes.add(review_item)
        requested = {_nonblank(item_id) for item_id in request_item_ids}
        if not requested.issubset(expected_request_item_ids):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_ITEM_UNKNOWN")
        if accounted_request_item_ids.intersection(requested):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_ITEM_DUPLICATE")
        accounted_request_item_ids.update(requested)
        reviewed_defects.add(defect_id)
        if outcome == "CONFIRMED":
            confirmed_items.add(review_item)
    if accounted_request_item_ids != expected_request_item_ids:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_ITEMS_UNACCOUNTED_FOR")
    return confirmed_items, reviewed_defects, len(decisions)


def build_phase8_human_review_request_v2(request_v1: object) -> dict[str, Any]:
    """Return a deterministic, non-persisted v2 draft from one v1 request.

    This converter changes the request hash. It intentionally does not create
    a review response or infer which decisions cover which requested items.
    """

    expected_fields = {
        "schema",
        "status",
        "package_id",
        "approval_reference",
        "proposal_file_sha256",
        "controller_receipt_file_sha256",
        "visual_proposal_status",
        "review_items",
        "unresolved_blind_observations",
        "reviewer_instructions",
        "canonical_submission_performed",
        "physical_model_lock_created",
        "human_reference_visible_to_inference",
    }
    request = _require_exact_fields(
        request_v1,
        expected=expected_fields,
        code="HUMAN_REVIEW_REQUEST_FIELDS_INVALID",
    )
    if request.get("schema") != HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA:
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_SCHEMA_INVALID")
    review_items = request.get("review_items")
    unresolved = request.get("unresolved_blind_observations")
    if (
        not isinstance(review_items, list)
        or not isinstance(unresolved, list)
        or any(not isinstance(item, dict) for item in [*review_items, *unresolved])
    ):
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_CONTENT_INVALID")

    result = deepcopy(request)

    def with_ids(prefix: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        identified: list[dict[str, Any]] = []
        for item in items:
            if "review_item_id" in item:
                raise Phase8HumanAdjudicatedProposalError(
                    "HUMAN_REVIEW_REQUEST_ITEM_FIELDS_INVALID"
                )
            identified_item = deepcopy(item)
            identified_item["review_item_id"] = (
                f"{prefix}-{canonical_json_sha256({'prefix': prefix, 'item': item})[:24]}"
            )
            identified.append(identified_item)
        return identified

    result["schema"] = HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2
    result["review_items"] = with_ids("REVIEW", review_items)
    result["unresolved_blind_observations"] = with_ids("UNRESOLVED", unresolved)
    _validated_request_item_ids(
        result["review_items"],
        result["unresolved_blind_observations"],
    )
    return result


def validate_phase8_human_review_v2(
    *,
    request: dict[str, Any],
    request_sha256: str,
    review: dict[str, Any],
    source_proposal_sha256: str,
    controller_receipt_sha256: str,
    source_controller_status: str,
) -> tuple[set[str], set[str], int]:
    """Validate complete v2 request-item coverage without changing any state."""

    request_item_ids = _validated_request(
        request,
        request_sha256=request_sha256,
        review=review,
        source_proposal_sha256=source_proposal_sha256,
        controller_receipt_sha256=controller_receipt_sha256,
        source_controller_status=source_controller_status,
    )
    return _validated_response(review, expected_request_item_ids=request_item_ids)


__all__ = [
    "build_phase8_human_review_request_v2",
    "validate_phase8_human_review_v2",
]
