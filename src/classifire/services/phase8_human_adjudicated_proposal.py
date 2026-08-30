"""Validate a local, human-adjudicated Phase 8 proposal revision.

This is a post-run artifact validator only.  It deliberately has no inference,
database, canonical-write, admission, signing, registration, or lock
interface.  A human review response may make an explicitly scoped proposal
revision more precise, but neither artifact can create canonical records.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .phase8_visual_proposal import (
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_BLOCKED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    canonical_json_sha256,
    receipt_bound_visual_evidence_refs,
    validate_phase8_visual_proposal_receipt,
    validate_policy_bound_visual_physical_proposal,
)
from .phase8_visual_provenance import assess_phase8_visual_provenance_completeness
from .physical_scope import is_blank_opening_type

HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA = "CLASSIFIRE-PHASE8-HUMAN-EVIDENCE-REVIEW-RESPONSE-v1"
HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2 = "CLASSIFIRE-PHASE8-HUMAN-EVIDENCE-REVIEW-RESPONSE-v2"
HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-REQUEST-v1"
HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2 = "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-REQUEST-v2"
HUMAN_ADJUDICATED_PROPOSAL_SCHEMA = "CLASSIFIRE-PHASE8-HUMAN-ADJUDICATED-PROPOSAL-v1"
HUMAN_ADJUDICATED_PROPOSAL_VALIDATION_SCHEMA = (
    "CLASSIFIRE-PHASE8-HUMAN-ADJUDICATED-PROPOSAL-VALIDATION-v1"
)
HUMAN_ADJUDICATED_PROPOSAL_VISUAL_PROVENANCE_VALIDATION_SCHEMA = (
    "CLASSIFIRE-PHASE8-HUMAN-ADJUDICATED-PROPOSAL-VISUAL-PROVENANCE-VALIDATION-v1"
)
HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS = "HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS"
ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS = "ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024

_REVIEW_NOOP_FLAGS = (
    "report_or_image_retrieval_performed",
    "runtime_inference_performed",
    "canonical_submission_performed",
    "physical_model_lock_created",
    "database_write_performed",
    "gateway_call_performed",
    "human_reference_visible_to_inference",
)
_REVISION_NOOP_FLAGS = (
    "runtime_inference_performed",
    "canonical_submission_performed",
    "physical_model_lock_created",
    "database_write_performed",
    "gateway_call_performed",
    "human_reference_visible_to_inference",
)


class Phase8HumanAdjudicatedProposalError(RuntimeError):
    """Fail-closed validation error for human-adjudicated proposal artifacts."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = f"Phase 8 human-adjudicated proposal validation failed: {code}."
        if detail:
            message += f" {detail}"
        super().__init__(message)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def _read_json_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    if not isinstance(path, Path) or not path.is_file():
        raise Phase8HumanAdjudicatedProposalError("ARTIFACT_MISSING", f"{label}: {path}")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise Phase8HumanAdjudicatedProposalError("ARTIFACT_UNREADABLE", label) from exc
    if not raw or len(raw) > MAX_ARTIFACT_BYTES:
        raise Phase8HumanAdjudicatedProposalError("ARTIFACT_SIZE_INVALID", label)
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Phase8HumanAdjudicatedProposalError("ARTIFACT_JSON_INVALID", label) from exc
    if not isinstance(value, dict):
        raise Phase8HumanAdjudicatedProposalError(
            "ARTIFACT_ROOT_INVALID", f"{label} must be a JSON object"
        )
    return value, _sha256(raw)


def _nonblank(value: object) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def _require_exact_fields(value: object, *, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise Phase8HumanAdjudicatedProposalError(code)
    return value


def _require_hash(binding: object, *, key: str, actual: str, code: str) -> None:
    if not isinstance(binding, dict) or binding.get(key) != actual:
        raise Phase8HumanAdjudicatedProposalError(code)


def _require_false_flags(value: dict[str, Any], *, fields: tuple[str, ...], code: str) -> None:
    for field_name in fields:
        if value.get(field_name) is not False:
            raise Phase8HumanAdjudicatedProposalError(code, field_name)


def _positive_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return False
    return number.is_finite() and number > 0


def _validated_review(
    review: dict[str, Any],
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
    _require_exact_fields(
        review,
        expected=expected_fields,
        code="HUMAN_REVIEW_FIELDS_INVALID",
    )
    if review.get("schema") != HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA:
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
    for index, decision in enumerate(decisions, start=1):
        if not isinstance(decision, dict):
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_DECISION_INVALID", str(index))
        defect_id = _nonblank(decision.get("external_defect_id"))
        review_item = _nonblank(decision.get("review_item"))
        outcome = _nonblank(decision.get("outcome"))
        if not defect_id or not review_item or outcome not in {"CONFIRMED", "UNRESOLVED"}:
            raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_DECISION_INVALID", str(index))
        reviewed_defects.add(defect_id)
        if outcome == "CONFIRMED":
            if review_item in confirmed_items:
                raise Phase8HumanAdjudicatedProposalError(
                    "HUMAN_REVIEW_ITEM_DUPLICATE", review_item
                )
            confirmed_items.add(review_item)
    return confirmed_items, reviewed_defects, len(decisions)


def _validated_review_request(
    request: dict[str, Any],
    *,
    request_sha256: str,
    review: dict[str, Any],
    source_proposal_sha256: str,
    controller_receipt_sha256: str,
    source_controller_status: str,
) -> None:
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
    if request.get("schema") != "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-REQUEST-v1":
        raise Phase8HumanAdjudicatedProposalError("HUMAN_REVIEW_REQUEST_SCHEMA_INVALID")
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


def _validated_revision_topology(
    revision: dict[str, Any],
    *,
    defect_reference: str,
    reviewed_defects: set[str],
    confirmed_review_items: set[str],
) -> dict[str, int]:
    counts = _require_exact_fields(
        revision.get("proposed_topology_counts"),
        expected={
            "defect_count",
            "opening_count",
            "service_count",
            "service_opening_link_count",
        },
        code="TOPOLOGY_COUNTS_INVALID",
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in counts.values()
    ):
        raise Phase8HumanAdjudicatedProposalError("TOPOLOGY_COUNTS_INVALID")
    openings = revision.get("openings")
    services = revision.get("services")
    if not isinstance(openings, list) or not isinstance(services, list):
        raise Phase8HumanAdjudicatedProposalError("TOPOLOGY_RECORDS_INVALID")

    opening_types: dict[str, object] = {}
    defect_ids: set[str] = set()
    for index, opening in enumerate(openings, start=1):
        if not isinstance(opening, dict):
            raise Phase8HumanAdjudicatedProposalError("OPENING_INVALID", str(index))
        opening_code = _nonblank(opening.get("opening_code"))
        external_defect_id = _nonblank(opening.get("external_defect_id"))
        if not opening_code or opening_code in opening_types:
            raise Phase8HumanAdjudicatedProposalError("OPENING_CODE_INVALID", opening_code)
        if external_defect_id != defect_reference or external_defect_id not in reviewed_defects:
            raise Phase8HumanAdjudicatedProposalError("OPENING_DEFECT_INVALID", opening_code)
        for field_name in (
            "opening_type",
            "orientation",
            "substrate_plane",
            "substrate_type",
            "evidence_status",
        ):
            if not _nonblank(opening.get(field_name)):
                raise Phase8HumanAdjudicatedProposalError("OPENING_FIELD_INVALID", field_name)
        if opening.get("evidence_status") != "HUMAN_ADJUDICATED_VISUAL_REVIEW":
            raise Phase8HumanAdjudicatedProposalError(
                "OPENING_EVIDENCE_STATUS_INVALID", opening_code
            )
        opening_types[opening_code] = opening.get("opening_type")
        defect_ids.add(external_defect_id)

    service_codes: set[str] = set()
    linked_openings: set[str] = set()
    link_count = 0
    for index, service in enumerate(services, start=1):
        if not isinstance(service, dict):
            raise Phase8HumanAdjudicatedProposalError("SERVICE_INVALID", str(index))
        service_code = _nonblank(service.get("service_code"))
        if not service_code or service_code in service_codes:
            raise Phase8HumanAdjudicatedProposalError("SERVICE_CODE_INVALID", service_code)
        service_codes.add(service_code)
        if not _nonblank(service.get("service_type")) or not _positive_number(
            service.get("quantity")
        ):
            raise Phase8HumanAdjudicatedProposalError("SERVICE_FIELD_INVALID", service_code)
        if "material" not in service:
            raise Phase8HumanAdjudicatedProposalError("SERVICE_FIELD_INVALID", service_code)
        if service.get("evidence_status") != "HUMAN_ADJUDICATED_VISUAL_REVIEW":
            raise Phase8HumanAdjudicatedProposalError(
                "SERVICE_EVIDENCE_STATUS_INVALID", service_code
            )
        source_reference = _nonblank(service.get("source_reference"))
        review_prefix = "human-review-response:"
        review_item = source_reference.removeprefix(review_prefix)
        if (
            not source_reference.startswith(review_prefix)
            or review_item not in confirmed_review_items
        ):
            raise Phase8HumanAdjudicatedProposalError("SERVICE_REVIEW_ITEM_INVALID", service_code)
        primary = _nonblank(service.get("primary_opening_code"))
        opening_codes = service.get("opening_codes")
        if not isinstance(opening_codes, list) or not primary:
            raise Phase8HumanAdjudicatedProposalError("SERVICE_OPENING_LINK_INVALID", service_code)
        normalised_links = [_nonblank(code) for code in opening_codes]
        if (
            not normalised_links
            or len(normalised_links) != len(set(normalised_links))
            or primary not in normalised_links
            or any(code not in opening_types for code in normalised_links)
        ):
            raise Phase8HumanAdjudicatedProposalError("SERVICE_OPENING_LINK_INVALID", service_code)
        linked_openings.update(normalised_links)
        link_count += len(normalised_links)

    for opening_code, opening_type in opening_types.items():
        is_blank = is_blank_opening_type(opening_type)
        if is_blank and opening_code in linked_openings:
            raise Phase8HumanAdjudicatedProposalError("BLANK_OPENING_HAS_SERVICE", opening_code)
        if not is_blank and opening_code not in linked_openings:
            raise Phase8HumanAdjudicatedProposalError(
                "OCCUPIED_OPENING_HAS_NO_SERVICE", opening_code
            )

    actual_counts = {
        "defect_count": len(defect_ids),
        "opening_count": len(opening_types),
        "service_count": len(service_codes),
        "service_opening_link_count": link_count,
    }
    if counts != actual_counts:
        raise Phase8HumanAdjudicatedProposalError("TOPOLOGY_COUNT_MISMATCH")
    return actual_counts


def validate_phase8_human_adjudicated_proposal(
    *,
    source_proposal_path: Path,
    source_controller_receipt_path: Path,
    human_review_request_path: Path,
    human_review_response_path: Path,
    revised_proposal_path: Path,
    source_evidence_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Validate hash-bound human adjudication without performing any write or inference."""

    source_proposal, source_proposal_sha256 = _read_json_object(
        source_proposal_path, label="source proposal"
    )
    controller_receipt, controller_receipt_sha256 = _read_json_object(
        source_controller_receipt_path, label="source controller receipt"
    )
    review_request, review_request_sha256 = _read_json_object(
        human_review_request_path, label="human review request"
    )
    review, review_sha256 = _read_json_object(
        human_review_response_path, label="human review response"
    )
    revision, revision_sha256 = _read_json_object(
        revised_proposal_path, label="human-adjudicated proposal"
    )

    receipt_errors = validate_phase8_visual_proposal_receipt(controller_receipt)
    if receipt_errors:
        raise Phase8HumanAdjudicatedProposalError(
            "SOURCE_CONTROLLER_RECEIPT_INVALID", "; ".join(receipt_errors)
        )
    if controller_receipt.get("status") not in {
        VISUAL_PROPOSAL_APPROVED,
        VISUAL_PROPOSAL_BLOCKED,
    }:
        raise Phase8HumanAdjudicatedProposalError("SOURCE_CONTROLLER_RECEIPT_STATUS_INVALID")
    source_controller_status = _nonblank(controller_receipt.get("status"))
    source_run_id = _nonblank(controller_receipt.get("run_id"))
    estimate_id = _nonblank(controller_receipt.get("estimate_id"))
    defect_reference = _nonblank(controller_receipt.get("defect_reference"))
    if not source_run_id or not estimate_id or not defect_reference:
        raise Phase8HumanAdjudicatedProposalError("SOURCE_CONTROLLER_RECEIPT_IDENTITY_INVALID")
    selected_manifest_path = source_evidence_manifest_path
    if (
        selected_manifest_path is None
        and controller_receipt.get("policy_version") == VISUAL_PROPOSAL_POLICY_VERSION
    ):
        selected_manifest_path = source_controller_receipt_path.with_name(
            "evidence-manifest.json"
        )
    allowed_evidence_refs: frozenset[str] | None = None
    evidence_manifest_binding: dict[str, Any] | None = None
    if selected_manifest_path is not None:
        evidence_manifest, evidence_manifest_file_sha256 = _read_json_object(
            selected_manifest_path,
            label="source evidence manifest",
        )
        allowed_evidence_refs, manifest_errors = receipt_bound_visual_evidence_refs(
            receipt=controller_receipt,
            evidence_manifest=evidence_manifest,
        )
        if manifest_errors:
            raise Phase8HumanAdjudicatedProposalError(
                "SOURCE_EVIDENCE_MANIFEST_INVALID",
                "; ".join(manifest_errors),
            )
        evidence_manifest_binding = {
            "path": str(selected_manifest_path.resolve()),
            "sha256": evidence_manifest_file_sha256,
            "canonical_json_sha256": canonical_json_sha256(evidence_manifest),
        }
    source_proposal_errors = validate_policy_bound_visual_physical_proposal(
        source_proposal,
        defect_reference=defect_reference,
        policy_version=str(controller_receipt["policy_version"]),
        allowed_evidence_refs=allowed_evidence_refs,
    )
    if source_proposal_errors:
        raise Phase8HumanAdjudicatedProposalError(
            "SOURCE_PROPOSAL_INVALID", "; ".join(source_proposal_errors)
        )
    source_proposal_canonical_sha256 = canonical_json_sha256(source_proposal)
    _require_hash(
        controller_receipt.get("result_hashes"),
        key="proposal_sha256",
        actual=source_proposal_canonical_sha256,
        code="SOURCE_PROPOSAL_RECEIPT_HASH_MISMATCH",
    )

    if (
        review.get("schema") == HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2
        or review_request.get("schema") == HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2
    ):
        from .phase8_human_review_v2 import validate_phase8_human_review_v2

        confirmed_review_items, reviewed_defects, decision_count = validate_phase8_human_review_v2(
            request=review_request,
            request_sha256=review_request_sha256,
            review=review,
            source_proposal_sha256=source_proposal_sha256,
            controller_receipt_sha256=controller_receipt_sha256,
            source_controller_status=source_controller_status,
        )
    else:
        confirmed_review_items, reviewed_defects, decision_count = _validated_review(review)
        _validated_review_request(
            review_request,
            request_sha256=review_request_sha256,
            review=review,
            source_proposal_sha256=source_proposal_sha256,
            controller_receipt_sha256=controller_receipt_sha256,
            source_controller_status=source_controller_status,
        )

    revision_expected_fields = {
        "schema",
        "status",
        "run_id",
        "source_run_id",
        "estimate_id",
        "source_proposal",
        "human_review_response",
        "proposed_topology_counts",
        "openings",
        "services",
        "limitations",
        *_REVISION_NOOP_FLAGS,
    }
    _require_exact_fields(
        revision,
        expected=revision_expected_fields,
        code="REVISION_FIELDS_INVALID",
    )
    if revision.get("schema") != HUMAN_ADJUDICATED_PROPOSAL_SCHEMA:
        raise Phase8HumanAdjudicatedProposalError("REVISION_SCHEMA_INVALID")
    if revision.get("status") != ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS:
        raise Phase8HumanAdjudicatedProposalError("REVISION_STATUS_INVALID")
    if (
        not _nonblank(revision.get("run_id"))
        or revision.get("source_run_id") != source_run_id
        or revision.get("estimate_id") != estimate_id
    ):
        raise Phase8HumanAdjudicatedProposalError("REVISION_IDENTITY_INVALID")
    source_binding = _require_exact_fields(
        revision.get("source_proposal"),
        expected={"path", "file_sha256", "canonical_json_sha256"},
        code="REVISION_SOURCE_BINDING_INVALID",
    )
    if not _nonblank(source_binding.get("path")):
        raise Phase8HumanAdjudicatedProposalError("REVISION_SOURCE_BINDING_INVALID")
    _require_hash(
        source_binding,
        key="file_sha256",
        actual=source_proposal_sha256,
        code="REVISION_SOURCE_FILE_HASH_MISMATCH",
    )
    _require_hash(
        source_binding,
        key="canonical_json_sha256",
        actual=source_proposal_canonical_sha256,
        code="REVISION_SOURCE_CANONICAL_HASH_MISMATCH",
    )
    review_binding = _require_exact_fields(
        revision.get("human_review_response"),
        expected={"path", "file_sha256"},
        code="REVISION_REVIEW_BINDING_INVALID",
    )
    if not _nonblank(review_binding.get("path")):
        raise Phase8HumanAdjudicatedProposalError("REVISION_REVIEW_BINDING_INVALID")
    _require_hash(
        review_binding,
        key="file_sha256",
        actual=review_sha256,
        code="REVISION_REVIEW_HASH_MISMATCH",
    )
    limitations = revision.get("limitations")
    if (
        not isinstance(limitations, list)
        or not limitations
        or any(not _nonblank(item) for item in limitations)
    ):
        raise Phase8HumanAdjudicatedProposalError("REVISION_LIMITATIONS_INVALID")
    _require_false_flags(revision, fields=_REVISION_NOOP_FLAGS, code="REVISION_NOOP_VIOLATION")
    actual_counts = _validated_revision_topology(
        revision,
        defect_reference=defect_reference,
        reviewed_defects=reviewed_defects,
        confirmed_review_items=confirmed_review_items,
    )

    return {
        "schema": HUMAN_ADJUDICATED_PROPOSAL_VALIDATION_SCHEMA,
        "status": "PASS",
        "source_run_id": source_run_id,
        "source_controller_status": source_controller_status,
        "estimate_id": estimate_id,
        "defect_reference": defect_reference,
        "human_review_decision_count": decision_count,
        "proposed_topology_counts": actual_counts,
        "input_bindings": {
            "source_proposal": {
                "path": str(source_proposal_path.resolve()),
                "sha256": source_proposal_sha256,
                "canonical_json_sha256": source_proposal_canonical_sha256,
            },
            "source_controller_receipt": {
                "path": str(source_controller_receipt_path.resolve()),
                "sha256": controller_receipt_sha256,
                "proposal_canonical_json_binding": "VERIFIED",
            },
            **(
                {"source_evidence_manifest": evidence_manifest_binding}
                if evidence_manifest_binding is not None
                else {}
            ),
            "human_review_request": {
                "path": str(human_review_request_path.resolve()),
                "sha256": review_request_sha256,
            },
            "human_review_response": {
                "path": str(human_review_response_path.resolve()),
                "sha256": review_sha256,
            },
            "human_adjudicated_proposal": {
                "path": str(revised_proposal_path.resolve()),
                "sha256": revision_sha256,
                "canonical_json_sha256": canonical_json_sha256(revision),
            },
        },
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "canonical_database_read_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "human_reference_visible_to_inference": False,
    }


def validate_phase8_human_adjudicated_proposal_with_visual_provenance(
    *,
    source_proposal_path: Path,
    source_controller_receipt_path: Path,
    human_review_request_path: Path,
    human_review_response_path: Path,
    revised_proposal_path: Path,
    linked_visual_run_receipt_path: Path,
    evidence_family_inventory_path: Path,
    source_evidence_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Require current visual provenance for a proposal-only human revision.

    Historic v1 validation remains available through
    :func:`validate_phase8_human_adjudicated_proposal`.  New consumers that
    need current visual provenance must use this strict, still no-write mode.
    It cannot make a limited proposal admission-eligible or create a lock.
    """

    proposal_validation = validate_phase8_human_adjudicated_proposal(
        source_proposal_path=source_proposal_path,
        source_controller_receipt_path=source_controller_receipt_path,
        human_review_request_path=human_review_request_path,
        human_review_response_path=human_review_response_path,
        revised_proposal_path=revised_proposal_path,
        source_evidence_manifest_path=source_evidence_manifest_path,
    )
    controller_receipt, _controller_receipt_file_sha256 = _read_json_object(
        source_controller_receipt_path,
        label="source controller receipt",
    )
    linked_receipt, linked_receipt_file_sha256 = _read_json_object(
        linked_visual_run_receipt_path,
        label="linked visual run receipt",
    )
    inventory, inventory_file_sha256 = _read_json_object(
        evidence_family_inventory_path,
        label="evidence family inventory",
    )
    provenance = assess_phase8_visual_provenance_completeness(
        estimate_id=proposal_validation["estimate_id"],
        defect_reference=proposal_validation["defect_reference"],
        linked_visual_run_receipt=linked_receipt,
        evidence_family_inventory=inventory,
    )
    if not provenance.complete:
        raise Phase8HumanAdjudicatedProposalError(
            "CURRENT_VISUAL_PROVENANCE_INCOMPLETE",
            ", ".join(provenance.errors),
        )
    if provenance.controller_receipt_sha256 != canonical_json_sha256(controller_receipt):
        raise Phase8HumanAdjudicatedProposalError("CURRENT_VISUAL_CONTROLLER_RECEIPT_HASH_MISMATCH")
    return {
        "schema": HUMAN_ADJUDICATED_PROPOSAL_VISUAL_PROVENANCE_VALIDATION_SCHEMA,
        "status": "PASS_PROPOSAL_ONLY_WITH_LIMITATIONS",
        "admission_eligible": False,
        "proposal_validation": proposal_validation,
        "visual_provenance": provenance.as_dict(),
        "input_bindings": {
            "linked_visual_run_receipt": {
                "path": str(linked_visual_run_receipt_path.resolve()),
                "sha256": linked_receipt_file_sha256,
            },
            "evidence_family_inventory": {
                "path": str(evidence_family_inventory_path.resolve()),
                "sha256": inventory_file_sha256,
            },
        },
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "human_reference_visible_to_inference": False,
    }


__all__ = [
    "ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS",
    "HUMAN_ADJUDICATED_PROPOSAL_SCHEMA",
    "HUMAN_ADJUDICATED_PROPOSAL_VALIDATION_SCHEMA",
    "HUMAN_ADJUDICATED_PROPOSAL_VISUAL_PROVENANCE_VALIDATION_SCHEMA",
    "HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA",
    "HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA",
    "HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2",
    "HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2",
    "HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS",
    "Phase8HumanAdjudicatedProposalError",
    "validate_phase8_human_adjudicated_proposal",
    "validate_phase8_human_adjudicated_proposal_with_visual_provenance",
]
