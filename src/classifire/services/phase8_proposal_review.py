"""Hash-bound, proposal-only review artifacts for Phase 8 assessments."""

from __future__ import annotations

import hashlib
import json
import math
import re
from copy import deepcopy
from typing import Any

from .phase8_property_assessments import (
    physical_property_fields_for_subject,
    required_physical_property_fields_for_subject,
    validate_physical_property_value,
)
from .phase8_report_assessment_controller import (
    validate_phase8_report_assessment_receipt,
)
from .phase8_visual_proposal import (
    LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_BLOCKED,
    VISUAL_PROPOSAL_FAILED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_policy_bound_visual_physical_proposal,
    validate_visual_evidence_manifest,
)
from .physical_scope import is_cable_bundle_service, is_cable_tray_service
from .report_evidence_adapter import (
    ReportDefectEvidencePacket,
    validate_report_defect_evidence_packet,
)

PHASE8_PROPOSAL_REVIEW_SCHEMA = "CLASSIFIRE-PHASE8-PROPOSAL-REVIEW-v2"
_HASH = re.compile(r"^[0-9a-fA-F]{64}$")
_MAX_TEXT = 2_000
_MAX_INPUT_BYTES = 32 * 1024 * 1024
_MAX_REVIEW_LIST_ITEMS = 200
_MAX_CODE = 200
_MAX_VALUE_TEXT = 500
_TRUNCATION_SUFFIX = " [truncated; see hash-bound source artifact]"
_NOOP_FLAGS = (
    "canonical_submission_performed",
    "technical_selection_performed",
    "commercial_pricing_performed",
    "physical_model_lock_created",
    "human_release_performed",
)
_REPORT_ASSESSMENT_BINDING_FIELDS = (
    'report_assessment_controller_receipt_file_sha256',
    'report_assessment_controller_receipt_canonical_sha256',
    'report_runtime_input_manifest_sha256',
    'report_packet_manifest_sha256',
    'report_documentary_context_manifest_sha256',
    'report_assessment_inference_profile_sha256',
)

_OPENING_LABELS = {
    "shape": "Shape",
    "size": "Size",
    "opening_type": "Opening type",
    "opening_boundary": "Opening boundary",
    "substrate_plane": "Element",
    "substrate_type": "General type",
    "substrate_specific_type": "Specific type",
    "substrate_thickness": "Approximate thickness",
    "orientation": "Orientation",
    "opposite_face_continuity": "Opposite-face continuity",
    "width_mm": "Width",
    "height_mm": "Height",
    "diameter_mm": "Diameter",
    "substrate_thickness_mm": "Substrate thickness",
    "frl": "Required FRL",
}
_SERVICE_LABELS = {
    "quantity": "Service-group quantity",
    "service_type": "Type",
    "material": "Material",
    "size": "Size",
    "insulation_or_covering": "Insulation or covering",
    "arrangement": "Arrangement",
    "primary_opening_code": "Primary opening",
    "opening_codes": "Opening links",
    "link_type": "Link type",
    "relationship_status": "Relationship status",
    "concealed_continuity": "Concealed continuity",
    "nominal_size_mm": "Nominal size",
    "outside_diameter_mm": "Outside diameter",
    "width_mm": "Width",
    "height_mm": "Height",
    "insulation_type": "Insulation type",
    "insulation_thickness_mm": "Insulation thickness",
    "cable_count": "Cables in bundle",
    "bundle_size_class": "Bundle size class",
    "tray_width_mm": "Tray width",
    "tray_height_mm": "Tray height",
}


class Phase8ProposalReviewError(RuntimeError):
    """Stable fail-closed error for malformed or unbound review inputs."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        message = f"Phase 8 proposal review failed: {code}."
        if detail:
            message += f" {detail}"
        super().__init__(message)


def _text(value: object, *, code: str, maximum: int = _MAX_TEXT) -> str:
    if not isinstance(value, str):
        raise Phase8ProposalReviewError(code)
    result = value.strip()
    if not result or len(result) > maximum:
        raise Phase8ProposalReviewError(code)
    return result


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _hash(value: object, *, code: str) -> str:
    result = _text(value, code=code, maximum=64)
    if not _HASH.fullmatch(result):
        raise Phase8ProposalReviewError(code)
    return result.upper()


def _bounded_review_text(value: object) -> str:
    text = str(value).strip()
    if len(text) <= _MAX_TEXT:
        return text
    return text[: _MAX_TEXT - len(_TRUNCATION_SUFFIX)].rstrip() + _TRUNCATION_SUFFIX


def _bounded_review_texts(values: object) -> list[str]:
    if not isinstance(values, list):
        return []
    rendered = [_bounded_review_text(value) for value in values[:_MAX_REVIEW_LIST_ITEMS]]
    if len(values) > _MAX_REVIEW_LIST_ITEMS:
        omitted = len(values) - (_MAX_REVIEW_LIST_ITEMS - 1)
        rendered = [
            *rendered[: _MAX_REVIEW_LIST_ITEMS - 1],
            f"{omitted} additional entries omitted; see hash-bound source artifact",
        ]
    return rendered


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise Phase8ProposalReviewError("PROPOSAL_REVIEW_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _reject_nonfinite_constant(_value: str) -> None:
    raise ValueError


def _json_object(raw: object, *, code: str) -> dict[str, Any]:
    if not isinstance(raw, bytes) or not raw or len(raw) > _MAX_INPUT_BYTES:
        raise Phase8ProposalReviewError(code)
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_object,
            parse_constant=_reject_nonfinite_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise Phase8ProposalReviewError(code) from exc
    if not isinstance(value, dict):
        raise Phase8ProposalReviewError(code)
    return value


def _unit(field: str, value: object) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("unit"), str):
        return str(value["unit"])
    return "mm" if field.endswith("_mm") else None


def _ordered_fields(assessments: dict[str, Any], *, subject: str) -> list[str]:
    labels = _OPENING_LABELS if subject == "Opening" else _SERVICE_LABELS
    known = [field for field in labels if field in assessments]
    return [*known, *sorted(set(assessments) - set(known))]


def _assessment_item(
    row: dict[str, Any],
    *,
    field: str,
    subject: str,
) -> dict[str, Any]:
    assessments = row.get("property_assessments")
    if not isinstance(assessments, dict) or not isinstance(assessments.get(field), dict):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_PROPERTY_MISSING")
    assessment = assessments[field]
    labels = _OPENING_LABELS if subject == "Opening" else _SERVICE_LABELS
    return {
        "label": labels.get(field, field.replace("_", " ").title()),
        "field": field,
        "value": deepcopy(row.get(field)),
        "unit": _unit(field, row.get(field)),
        "status": assessment.get("status"),
        "confidence": assessment.get("confidence"),
        "reasoning": assessment.get("reasoning"),
        "evidence_refs": deepcopy(assessment.get("evidence_refs")),
        "credible_alternative": assessment.get("credible_alternative"),
        "additional_evidence_required": assessment.get(
            "additional_evidence_required"
        ),
    }


def _review_base(
    *,
    package_id: str,
    package_sha256: str,
    approval_reference: str,
    receipt: dict[str, Any],
    receipt_file_sha256: str,
    manifest_sha256: str,
    proposal_file_sha256: str | None,
    proposal_canonical_sha256: str | None,
    documentary_packet_sha256: str | None,
    report_assessment_binding: dict[str, str] | None,
) -> dict[str, Any]:
    input_bindings: dict[str, str | None] = {
        "controller_receipt_file_sha256": receipt_file_sha256,
        "controller_receipt_canonical_sha256": canonical_json_sha256(receipt),
        "evidence_manifest_canonical_sha256": manifest_sha256,
        "inference_profile_sha256": receipt["inference_profile_sha256"],
        "proposal_file_sha256": proposal_file_sha256,
        "proposal_canonical_sha256": proposal_canonical_sha256,
    }
    if documentary_packet_sha256 is not None:
        input_bindings["documentary_packet_canonical_sha256"] = documentary_packet_sha256
    if report_assessment_binding is not None:
        input_bindings.update(report_assessment_binding)
    return {
        "schema": PHASE8_PROPOSAL_REVIEW_SCHEMA,
        "review_status": "UNAVAILABLE",
        "package_id": package_id,
        "package_sha256": package_sha256,
        "approval_reference": approval_reference,
        "run_id": receipt["run_id"],
        "estimate_id": receipt["estimate_id"],
        "defect_reference": receipt["defect_reference"],
        "visual_proposal_status": receipt["status"],
        "policy_version": receipt["policy_version"],
        "proposal_outcome": (
            "NONE" if proposal_file_sha256 is None else "INVALID"
        ),
        "implementation_revision": receipt["implementation_revision"],
        "input_bindings": input_bindings,
        "proposal_only": True,
        "canonical_submission_performed": False,
        "technical_selection_performed": False,
        "commercial_pricing_performed": False,
        "physical_model_lock_created": False,
        "human_release_performed": False,
        "controller_blockers": _bounded_review_texts(receipt["errors"]),
        "validation_errors": [],
        "openings": [],
        "services": [],
        "evidence_limitations": [],
        "additional_evidence_required": [],
    }


def _documentary_packet_binding(
    value: object,
    *,
    estimate_id: str,
    defect_reference: str,
) -> tuple[frozenset[str], str | None]:
    if value is None:
        return frozenset(), None
    if not isinstance(value, ReportDefectEvidencePacket):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_REPORT_PACKET_INVALID")
    if validate_report_defect_evidence_packet(value):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_REPORT_PACKET_INVALID")
    manifest = value.manifest
    if (
        manifest.get("estimate_id") != estimate_id
        or manifest.get("defect_reference") != defect_reference
    ):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_REPORT_PACKET_SCOPE_MISMATCH")
    refs = value.evidence_refs
    if not refs:
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_REPORT_PACKET_INVALID")
    return refs, canonical_json_sha256(manifest)


def _report_assessment_binding(
    *,
    receipt_file_bytes: object | None,
    receipt_file_sha256: object | None,
    visual_receipt: dict[str, Any],
    documentary_packet_sha256: str | None,
) -> dict[str, str] | None:
    if receipt_file_bytes is None and receipt_file_sha256 is None:
        return None
    if receipt_file_bytes is None or receipt_file_sha256 is None:
        raise Phase8ProposalReviewError('PROPOSAL_REVIEW_REPORT_RECEIPT_INPUT_CONFLICT')
    expected_hash = _hash(
        receipt_file_sha256,
        code='PROPOSAL_REVIEW_REPORT_RECEIPT_HASH_INVALID',
    )
    if (
        not isinstance(receipt_file_bytes, bytes)
        or _sha256_bytes(receipt_file_bytes) != expected_hash
    ):
        raise Phase8ProposalReviewError('PROPOSAL_REVIEW_REPORT_RECEIPT_TAMPERED')
    report_receipt = _json_object(
        receipt_file_bytes,
        code='PROPOSAL_REVIEW_REPORT_RECEIPT_INVALID',
    )
    if validate_phase8_report_assessment_receipt(report_receipt):
        raise Phase8ProposalReviewError('PROPOSAL_REVIEW_REPORT_RECEIPT_INVALID')
    if (
        report_receipt['visual_controller_receipt'] != visual_receipt
        or report_receipt['visual_controller_receipt_sha256']
        != canonical_json_sha256(visual_receipt)
    ):
        raise Phase8ProposalReviewError('PROPOSAL_REVIEW_REPORT_RECEIPT_VISUAL_MISMATCH')
    if documentary_packet_sha256 is None or (
        report_receipt['report_packet_manifest_sha256'] != documentary_packet_sha256
    ):
        raise Phase8ProposalReviewError('PROPOSAL_REVIEW_REPORT_RECEIPT_DOCUMENTARY_MISMATCH')
    return {
        'report_assessment_controller_receipt_file_sha256': expected_hash,
        'report_assessment_controller_receipt_canonical_sha256': canonical_json_sha256(
            report_receipt
        ),
        'report_runtime_input_manifest_sha256': report_receipt[
            'report_runtime_input_manifest_sha256'
        ],
        'report_packet_manifest_sha256': report_receipt['report_packet_manifest_sha256'],
        'report_documentary_context_manifest_sha256': report_receipt[
            'report_documentary_context_manifest_sha256'
        ],
        'report_assessment_inference_profile_sha256': report_receipt[
            'report_assessment_inference_profile_sha256'
        ],
    }


def build_phase8_proposal_review(
    *,
    package_id: object,
    package_sha256: object,
    approval_reference: object,
    proposal_file_bytes: bytes | None,
    proposal_file_sha256: object | None,
    controller_receipt_file_bytes: object,
    controller_receipt_file_sha256: object,
    evidence_manifest: object,
    documentary_evidence_packet: object | None = None,
    report_assessment_controller_receipt_file_bytes: object | None = None,
    report_assessment_controller_receipt_file_sha256: object | None = None,
) -> dict[str, Any]:
    """Build one review from the exact receipt, proposal bytes, and manifest."""

    package = _text(package_id, code="PROPOSAL_REVIEW_PACKAGE_INVALID", maximum=200)
    package_hash = _hash(package_sha256, code="PROPOSAL_REVIEW_PACKAGE_HASH_INVALID")
    approval = _text(
        approval_reference,
        code="PROPOSAL_REVIEW_APPROVAL_INVALID",
        maximum=500,
    )
    controller_expected_hash = _hash(
        controller_receipt_file_sha256,
        code="PROPOSAL_REVIEW_CONTROLLER_RECEIPT_HASH_INVALID",
    )
    if not isinstance(controller_receipt_file_bytes, bytes):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_CONTROLLER_RECEIPT_INVALID")
    if _sha256_bytes(controller_receipt_file_bytes) != controller_expected_hash:
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_CONTROLLER_RECEIPT_TAMPERED")
    receipt = _json_object(
        controller_receipt_file_bytes,
        code="PROPOSAL_REVIEW_CONTROLLER_RECEIPT_INVALID",
    )
    receipt_errors = validate_phase8_visual_proposal_receipt(receipt)
    if receipt_errors:
        raise Phase8ProposalReviewError(
            "PROPOSAL_REVIEW_CONTROLLER_RECEIPT_INVALID",
            "; ".join(receipt_errors),
        )

    if not isinstance(evidence_manifest, dict):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_MANIFEST_INVALID")
    manifest_errors = validate_visual_evidence_manifest(
        evidence_manifest,
        estimate_id=str(receipt["estimate_id"]),
    )
    if manifest_errors:
        raise Phase8ProposalReviewError(
            "PROPOSAL_REVIEW_MANIFEST_INVALID",
            "; ".join(manifest_errors),
        )
    manifest_sha256 = canonical_json_sha256(evidence_manifest)
    if manifest_sha256 != str(receipt["evidence_manifest_sha256"]).upper():
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_MANIFEST_TAMPERED")
    if evidence_manifest.get("defect_reference") != receipt.get("defect_reference"):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_DEFECT_MISMATCH")
    documentary_refs, documentary_packet_sha256 = _documentary_packet_binding(
        documentary_evidence_packet,
        estimate_id=str(receipt["estimate_id"]),
        defect_reference=str(receipt["defect_reference"]),
    )
    report_assessment_binding = _report_assessment_binding(
        receipt_file_bytes=report_assessment_controller_receipt_file_bytes,
        receipt_file_sha256=report_assessment_controller_receipt_file_sha256,
        visual_receipt=receipt,
        documentary_packet_sha256=documentary_packet_sha256,
    )

    result_hashes = receipt.get("result_hashes")
    if not isinstance(result_hashes, dict):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_RESULT_HASH_INVALID")
    expected_proposal_canonical = result_hashes.get("proposal_sha256")
    proposal_raw_hash: str | None = None
    proposal_canonical_hash: str | None = None
    proposal: dict[str, Any] | None = None
    if expected_proposal_canonical is None:
        if proposal_file_bytes is not None or proposal_file_sha256 is not None:
            raise Phase8ProposalReviewError("PROPOSAL_REVIEW_UNEXPECTED_PROPOSAL")
    else:
        expected_file_hash = _hash(
            proposal_file_sha256,
            code="PROPOSAL_REVIEW_PROPOSAL_HASH_INVALID",
        )
        if not isinstance(proposal_file_bytes, bytes):
            raise Phase8ProposalReviewError("PROPOSAL_REVIEW_PROPOSAL_INVALID")
        proposal_raw_hash = _sha256_bytes(proposal_file_bytes)
        if proposal_raw_hash != expected_file_hash:
            raise Phase8ProposalReviewError("PROPOSAL_REVIEW_PROPOSAL_TAMPERED")
        proposal = _json_object(
            proposal_file_bytes,
            code="PROPOSAL_REVIEW_PROPOSAL_INVALID",
        )
        proposal_canonical_hash = canonical_json_sha256(proposal)
        if proposal_canonical_hash != str(expected_proposal_canonical).upper():
            raise Phase8ProposalReviewError("PROPOSAL_REVIEW_PROPOSAL_RECEIPT_MISMATCH")

    review = _review_base(
        package_id=package,
        package_sha256=package_hash,
        approval_reference=approval,
        receipt=receipt,
        receipt_file_sha256=controller_expected_hash,
        manifest_sha256=manifest_sha256,
        proposal_file_sha256=proposal_raw_hash,
        proposal_canonical_sha256=proposal_canonical_hash,
        documentary_packet_sha256=documentary_packet_sha256,
        report_assessment_binding=report_assessment_binding,
    )
    if proposal is None:
        review["review_status"] = "NO_PROPOSAL"
        return review
    declared_outcome = str(proposal.get("status") or "").strip().upper()
    review["proposal_outcome"] = (
        declared_outcome
        if declared_outcome in {"MODEL_SUPPORTED", "INSUFFICIENT_EVIDENCE"}
        else "INVALID"
    )
    if receipt["policy_version"] == LEGACY_VISUAL_PROPOSAL_POLICY_VERSION:
        proposal_errors = validate_policy_bound_visual_physical_proposal(
            proposal,
            defect_reference=str(receipt["defect_reference"]),
            policy_version=str(receipt["policy_version"]),
        )
        if proposal_errors:
            if receipt["status"] == VISUAL_PROPOSAL_APPROVED:
                raise Phase8ProposalReviewError(
                    "PROPOSAL_REVIEW_APPROVED_PROPOSAL_INVALID",
                    "; ".join(proposal_errors),
                )
            review["proposal_outcome"] = "INVALID"
            review["review_status"] = "INVALID_BLOCKED_PROPOSAL"
            review["validation_errors"] = _bounded_review_texts(proposal_errors)
            return review
        review["review_status"] = "LEGACY_POLICY_UNASSESSED"
        return review
    if receipt["policy_version"] != VISUAL_PROPOSAL_POLICY_VERSION:
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_POLICY_UNSUPPORTED")

    allowed_refs = {
        str(item["evidence_id"]).strip()
        for item in evidence_manifest["artifacts"]
        if isinstance(item, dict)
    } | documentary_refs
    proposal_errors = validate_policy_bound_visual_physical_proposal(
        proposal,
        defect_reference=str(receipt["defect_reference"]),
        policy_version=str(receipt["policy_version"]),
        allowed_evidence_refs=allowed_refs,
    )
    if proposal_errors:
        if receipt["status"] == VISUAL_PROPOSAL_APPROVED:
            raise Phase8ProposalReviewError(
                "PROPOSAL_REVIEW_APPROVED_PROPOSAL_INVALID",
                "; ".join(proposal_errors),
            )
        review["proposal_outcome"] = "INVALID"
        review["review_status"] = "INVALID_BLOCKED_PROPOSAL"
        review["validation_errors"] = _bounded_review_texts(proposal_errors)
        return review
    if receipt["status"] not in {VISUAL_PROPOSAL_APPROVED, VISUAL_PROPOSAL_BLOCKED}:
        review["review_status"] = "NON_REVIEWABLE_CONTROLLER_OUTCOME"
        return review
    if str(proposal.get("status") or "").strip().upper() == "INSUFFICIENT_EVIDENCE":
        review["review_status"] = "INSUFFICIENT_EVIDENCE"
        review["evidence_limitations"] = _bounded_review_texts(
            proposal.get("limitations", [])
        )
        return review

    for subject, collection, code_field in (
        ("Opening", "openings", "opening_code"),
        ("Service", "services", "service_code"),
    ):
        output_key = "openings" if subject == "Opening" else "services"
        for row in proposal[collection]:
            assessments = row["property_assessments"]
            items = [
                _assessment_item(row, field=field, subject=subject)
                for field in _ordered_fields(assessments, subject=subject)
            ]
            record = {code_field: row[code_field], "properties": items}
            if subject == "Service":
                record["service_semantics"] = (
                    "cable_bundle"
                    if is_cable_bundle_service(row.get("service_type"))
                    else "cable_tray"
                    if is_cable_tray_service(row.get("service_type"))
                    else None
                )
            review[output_key].append(record)
            for item in items:
                if item["additional_evidence_required"] is not None:
                    review["additional_evidence_required"].append(
                        {
                            "subject": subject,
                            "code": row[code_field],
                            "property": item["field"],
                            "requested_evidence": item["additional_evidence_required"],
                            "reason": item["reasoning"],
                        }
                    )
    review["evidence_limitations"] = _bounded_review_texts(
        proposal.get("limitations", [])
    )
    review["review_status"] = "ASSESSMENT_AVAILABLE"
    return review


def validate_phase8_proposal_review(review: Any) -> list[str]:
    """Validate a review before rendering or downstream retention."""

    if not isinstance(review, dict):
        return ["proposal review must be an object"]
    expected = {
        "schema",
        "review_status",
        "package_id",
        "package_sha256",
        "approval_reference",
        "run_id",
        "estimate_id",
        "defect_reference",
        "visual_proposal_status",
        "policy_version",
        "proposal_outcome",
        "implementation_revision",
        "input_bindings",
        "proposal_only",
        *_NOOP_FLAGS,
        "controller_blockers",
        "validation_errors",
        "openings",
        "services",
        "evidence_limitations",
        "additional_evidence_required",
    }
    errors: list[str] = []
    if set(review) != expected:
        errors.append("proposal review fields do not match the approved schema")
    if review.get("schema") != PHASE8_PROPOSAL_REVIEW_SCHEMA:
        errors.append("proposal review schema is unsupported")
    if review.get("review_status") not in {
        "ASSESSMENT_AVAILABLE",
        "NO_PROPOSAL",
        "LEGACY_POLICY_UNASSESSED",
        "INVALID_BLOCKED_PROPOSAL",
        "NON_REVIEWABLE_CONTROLLER_OUTCOME",
        "INSUFFICIENT_EVIDENCE",
    }:
        errors.append("proposal review status is unsupported")
    if review.get("proposal_only") is not True:
        errors.append("proposal review must remain proposal-only")
    for flag in _NOOP_FLAGS:
        if review.get(flag) is not False:
            errors.append(f"proposal review {flag} must be false")
    for field in (
        "package_id",
        "approval_reference",
        "run_id",
        "estimate_id",
        "defect_reference",
        "visual_proposal_status",
        "policy_version",
        "implementation_revision",
    ):
        if not isinstance(review.get(field), str) or not str(review[field]).strip():
            errors.append(f"proposal review requires {field}")
    if not _HASH.fullmatch(str(review.get("package_sha256") or "")):
        errors.append("proposal review requires package_sha256")

    bindings = review.get("input_bindings")
    binding_fields = {
        "controller_receipt_file_sha256",
        "controller_receipt_canonical_sha256",
        "evidence_manifest_canonical_sha256",
        "inference_profile_sha256",
        "proposal_file_sha256",
        "proposal_canonical_sha256",
    }
    documentary_binding_field = "documentary_packet_canonical_sha256"
    report_assessment_binding_fields = set(_REPORT_ASSESSMENT_BINDING_FIELDS)
    supported_binding_fields = {
        frozenset(binding_fields),
        frozenset({*binding_fields, documentary_binding_field}),
        frozenset({*binding_fields, documentary_binding_field, *report_assessment_binding_fields}),
    }
    if not isinstance(bindings, dict) or frozenset(bindings) not in supported_binding_fields:
        errors.append("proposal review input bindings are invalid")
    else:
        for field, value in bindings.items():
            if field.startswith("proposal_") and value is None:
                continue
            if not _HASH.fullmatch(str(value or "")):
                errors.append(f"proposal review binding {field} is invalid")

    status = review.get("review_status")
    policy_version = review.get("policy_version")
    visual_status = review.get("visual_proposal_status")
    proposal_outcome = review.get("proposal_outcome")
    if proposal_outcome not in {
        "NONE",
        "MODEL_SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "INVALID",
    }:
        errors.append("proposal review outcome is unsupported")
    if policy_version not in {
        LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
        VISUAL_PROPOSAL_POLICY_VERSION,
    }:
        errors.append("proposal review policy version is unsupported")
    if visual_status not in {
        VISUAL_PROPOSAL_APPROVED,
        VISUAL_PROPOSAL_BLOCKED,
        VISUAL_PROPOSAL_FAILED,
        VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
    }:
        errors.append("proposal review visual status is unsupported")
    if status == "LEGACY_POLICY_UNASSESSED" and (
        policy_version != LEGACY_VISUAL_PROPOSAL_POLICY_VERSION
    ):
        errors.append("legacy-unassessed review requires legacy policy")
    if status in {
        "ASSESSMENT_AVAILABLE",
        "INSUFFICIENT_EVIDENCE",
        "NON_REVIEWABLE_CONTROLLER_OUTCOME",
    } and policy_version != VISUAL_PROPOSAL_POLICY_VERSION:
        errors.append(f"{status} review requires current assessment policy")
    if status in {"ASSESSMENT_AVAILABLE", "INSUFFICIENT_EVIDENCE"} and visual_status not in {
        VISUAL_PROPOSAL_APPROVED,
        VISUAL_PROPOSAL_BLOCKED,
    }:
        errors.append(f"{status} review requires an approved or blocked controller result")
    if status == "INVALID_BLOCKED_PROPOSAL" and visual_status != VISUAL_PROPOSAL_BLOCKED:
        errors.append("invalid-blocked review requires a blocked controller result")
    if status == "INVALID_BLOCKED_PROPOSAL" and proposal_outcome != "INVALID":
        errors.append("invalid-blocked review requires an INVALID proposal outcome")
    if status == "NON_REVIEWABLE_CONTROLLER_OUTCOME" and visual_status in {
        VISUAL_PROPOSAL_APPROVED,
        VISUAL_PROPOSAL_BLOCKED,
    }:
        errors.append("non-reviewable review requires a non-reviewable controller result")
    if status == "NO_PROPOSAL" and visual_status == VISUAL_PROPOSAL_APPROVED:
        errors.append("no-proposal review cannot claim an approved controller result")
    if status == "NO_PROPOSAL" and proposal_outcome != "NONE":
        errors.append("no-proposal review requires a NONE proposal outcome")
    if status != "NO_PROPOSAL" and proposal_outcome == "NONE":
        errors.append("proposal-backed review requires a proposal outcome")
    if status == "ASSESSMENT_AVAILABLE" and proposal_outcome != "MODEL_SUPPORTED":
        errors.append("assessment review requires a MODEL_SUPPORTED proposal outcome")
    if (
        status == "INSUFFICIENT_EVIDENCE"
        and proposal_outcome != "INSUFFICIENT_EVIDENCE"
    ):
        errors.append(
            "insufficient-evidence review requires an INSUFFICIENT_EVIDENCE "
            "proposal outcome"
        )
    if status in {"LEGACY_POLICY_UNASSESSED", "NON_REVIEWABLE_CONTROLLER_OUTCOME"} and (
        proposal_outcome not in {"MODEL_SUPPORTED", "INSUFFICIENT_EVIDENCE"}
    ):
        errors.append(f"{status} review requires a valid declared proposal outcome")
    if isinstance(bindings, dict):
        proposal_bindings = (
            bindings.get("proposal_file_sha256"),
            bindings.get("proposal_canonical_sha256"),
        )
        if status == "NO_PROPOSAL" and proposal_bindings != (None, None):
            errors.append("no-proposal review cannot retain proposal bindings")
        if status != "NO_PROPOSAL" and None in proposal_bindings:
            errors.append("proposal-backed review requires both proposal bindings")

    for field in (
        "controller_blockers",
        "validation_errors",
        "evidence_limitations",
        "additional_evidence_required",
        "openings",
        "services",
    ):
        if not isinstance(review.get(field), list):
            errors.append(f"proposal review {field} must be an array")

    for field in ("controller_blockers", "validation_errors", "evidence_limitations"):
        values = review.get(field)
        if isinstance(values, list) and any(
            not isinstance(item, str) or not item.strip() or len(item) > _MAX_TEXT
            for item in values
        ):
            errors.append(f"proposal review {field} must contain bounded text")

    if status != "ASSESSMENT_AVAILABLE":
        for field in ("openings", "services", "additional_evidence_required"):
            if review.get(field) != []:
                errors.append(f"{status} review must not contain {field}")
    if status == "INSUFFICIENT_EVIDENCE" and not review.get("evidence_limitations"):
        errors.append("insufficient-evidence review requires limitations")
    if status == "INVALID_BLOCKED_PROPOSAL" and not review.get("validation_errors"):
        errors.append("invalid blocked review requires validation errors")

    if status == "ASSESSMENT_AVAILABLE":
        if not review.get("openings"):
            errors.append("assessment review requires at least one Opening")
        review_property_fields: dict[tuple[str, str], set[str]] = {}
        expected_evidence_requests: list[tuple[str, str, str, str, str]] = []
        for subject, collection, code_field, record_fields, labels in (
            (
                "Opening",
                "openings",
                "opening_code",
                {"opening_code", "properties"},
                _OPENING_LABELS,
            ),
            (
                "Service",
                "services",
                "service_code",
                {"service_code", "service_semantics", "properties"},
                _SERVICE_LABELS,
            ),
        ):
            allowed_property_fields = physical_property_fields_for_subject(subject)
            required_property_fields = required_physical_property_fields_for_subject(subject)
            rows = review.get(collection)
            if not isinstance(rows, list):
                continue
            seen_codes: set[str] = set()
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict) or set(row) != record_fields:
                    errors.append(f"{subject} review record {index} is invalid")
                    continue
                if (
                    not isinstance(row.get(code_field), str)
                    or not row[code_field].strip()
                    or len(row[code_field].strip()) > _MAX_CODE
                ):
                    errors.append(f"{subject} review record {index} requires {code_field}")
                elif row[code_field].strip() in seen_codes:
                    errors.append(f"{subject} review code is duplicated")
                else:
                    seen_codes.add(row[code_field].strip())
                if subject == "Service" and row.get("service_semantics") not in {
                    None,
                    "cable_bundle",
                    "cable_tray",
                }:
                    errors.append("Service review semantics are invalid")
                properties = row.get("properties")
                if not isinstance(properties, list) or not properties:
                    errors.append(f"{subject} review record {index} requires properties")
                    continue
                seen_fields: set[str] = set()
                properties_by_field: dict[str, dict[str, Any]] = {}
                for item in properties:
                    expected_item = {
                        "label",
                        "field",
                        "value",
                        "unit",
                        "status",
                        "confidence",
                        "reasoning",
                        "evidence_refs",
                        "credible_alternative",
                        "additional_evidence_required",
                    }
                    if not isinstance(item, dict) or set(item) != expected_item:
                        errors.append(f"{subject} review property is invalid")
                        continue
                    property_field = item.get("field")
                    if not isinstance(property_field, str) or not property_field.strip():
                        errors.append(f"{subject} review property field is invalid")
                    elif property_field not in allowed_property_fields:
                        errors.append(
                            f"{subject} review property field is unsupported: {property_field}"
                        )
                    elif property_field in seen_fields:
                        errors.append(f"{subject} review property field is duplicated")
                    else:
                        seen_fields.add(property_field)
                        properties_by_field[property_field] = item
                    if (
                        isinstance(property_field, str)
                        and property_field in labels
                        and item.get("label") != labels[property_field]
                    ):
                        errors.append(f"{subject} review property label does not match field")
                    elif not isinstance(item.get("label"), str) or not item["label"].strip():
                        errors.append(f"{subject} review property label is invalid")
                    item_status = item.get("status")
                    if item_status not in {
                        "CONFIRMED",
                        "APPROXIMATE",
                        "INFERRED",
                        "UNKNOWN",
                    }:
                        errors.append(f"{subject} review property status is invalid")
                    confidence = item.get("confidence")
                    if item_status in {"APPROXIMATE", "INFERRED"}:
                        if confidence not in {"HIGH", "MEDIUM", "LOW"}:
                            errors.append(f"{subject} review property confidence is invalid")
                    elif confidence is not None:
                        errors.append(f"{subject} review property confidence must be null")
                    value = item.get("value")
                    if (
                        isinstance(property_field, str)
                        and property_field in allowed_property_fields
                    ):
                        errors.extend(
                            validate_physical_property_value(
                                value,
                                field=property_field,
                                label=f"{subject} review property {property_field}",
                            )
                        )
                    if item_status == "UNKNOWN" and value is not None:
                        errors.append(f"{subject} review UNKNOWN property must have null value")
                    if item_status in {"CONFIRMED", "APPROXIMATE", "INFERRED"} and value is None:
                        errors.append(f"{subject} review assessed property requires a value")
                    if isinstance(value, bool) or not (
                        value is None
                        or isinstance(value, (str, int, float, list, dict))
                    ):
                        errors.append(f"{subject} review property value is invalid")
                    if isinstance(value, float) and not math.isfinite(value):
                        errors.append(f"{subject} review property value is not finite")
                    if isinstance(value, str) and (
                        not value.strip() or len(value) > _MAX_VALUE_TEXT
                    ):
                        errors.append(f"{subject} review property text is invalid")
                    if isinstance(value, list) and (
                        not value
                        or any(not isinstance(entry, str) or not entry.strip() for entry in value)
                        or any(len(entry.strip()) > _MAX_VALUE_TEXT for entry in value)
                        or len(value) > _MAX_REVIEW_LIST_ITEMS
                        or len(value) != len(set(value))
                    ):
                        errors.append(f"{subject} review property list is invalid")
                    if isinstance(value, dict):
                        keys = set(value)
                        if keys not in ({"value", "unit"}, {"minimum", "maximum", "unit"}):
                            errors.append(f"{subject} review measurement fields are invalid")
                        elif value.get("unit") not in {"mm", "cm", "m"}:
                            errors.append(f"{subject} review measurement unit is invalid")
                        else:
                            number_fields = (
                                ("value",)
                                if keys == {"value", "unit"}
                                else ("minimum", "maximum")
                            )
                            numbers = [value.get(name) for name in number_fields]
                            numeric_values = [
                                float(number)
                                for number in numbers
                                if isinstance(number, (int, float))
                                and not isinstance(number, bool)
                            ]
                            if len(numeric_values) != len(numbers) or any(
                                not math.isfinite(number) or number <= 0
                                for number in numeric_values
                            ):
                                errors.append(
                                    f"{subject} review measurement values are invalid"
                                )
                            elif (
                                len(numeric_values) == 2
                                and numeric_values[0] > numeric_values[1]
                            ):
                                errors.append(
                                    f"{subject} review measurement range is invalid"
                                )
                    if (
                        isinstance(property_field, str)
                        and property_field.endswith("_mm")
                        and value is not None
                        and (
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            or value <= 0
                        )
                    ):
                        errors.append(f"{subject} review millimetre value is invalid")
                    if (
                        isinstance(property_field, str)
                        and property_field in {"quantity", "cable_count"}
                        and value is not None
                        and (
                            isinstance(value, bool)
                            or not isinstance(value, (int, float))
                            or not math.isfinite(value)
                            or value <= 0
                            or not float(value).is_integer()
                        )
                    ):
                        errors.append(f"{subject} review count is invalid")
                    unit = item.get("unit")
                    if unit not in {None, "mm", "cm", "m"}:
                        errors.append(f"{subject} review property unit is invalid")
                    if isinstance(value, dict) and unit != value.get("unit"):
                        errors.append(f"{subject} review property unit does not match value")
                    if (
                        isinstance(property_field, str)
                        and property_field.endswith("_mm")
                        and unit != "mm"
                    ):
                        errors.append(f"{subject} review millimetre unit is invalid")
                    if (
                        isinstance(property_field, str)
                        and property_field in allowed_property_fields
                        and unit != _unit(property_field, value)
                    ):
                        errors.append(
                            f"{subject} review property unit does not match field semantics"
                        )
                    reasoning = item.get("reasoning")
                    if (
                        not isinstance(reasoning, str)
                        or not reasoning.strip()
                        or len(reasoning) > _MAX_TEXT
                    ):
                        errors.append(f"{subject} review property reasoning is invalid")
                    refs = item.get("evidence_refs")
                    if (
                        not isinstance(refs, list)
                        or not refs
                        or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
                        or any(len(ref.strip()) > _MAX_VALUE_TEXT for ref in refs)
                        or len(refs) > _MAX_REVIEW_LIST_ITEMS
                        or len(refs) != len(set(refs))
                    ):
                        errors.append(f"{subject} review property evidence is invalid")
                    alternative = item.get("credible_alternative")
                    if alternative is not None and (
                        not isinstance(alternative, str)
                        or not alternative.strip()
                        or len(alternative) > _MAX_TEXT
                    ):
                        errors.append(f"{subject} review property alternative is invalid")
                    if item_status == "CONFIRMED" and alternative is not None:
                        errors.append(f"{subject} review confirmed property has an alternative")
                    requested = item.get("additional_evidence_required")
                    if requested is not None and (
                        not isinstance(requested, str)
                        or not requested.strip()
                        or len(requested) > _MAX_TEXT
                    ):
                        errors.append(f"{subject} review evidence request is invalid")
                    elif (
                        requested is not None
                        and isinstance(property_field, str)
                        and property_field in allowed_property_fields
                        and isinstance(row.get(code_field), str)
                        and row[code_field].strip()
                        and isinstance(reasoning, str)
                        and reasoning.strip()
                    ):
                        expected_evidence_requests.append(
                            (
                                subject,
                                row[code_field].strip(),
                                property_field,
                                requested.strip(),
                                reasoning.strip(),
                            )
                        )
                missing_required = sorted(required_property_fields - seen_fields)
                if missing_required:
                    errors.append(
                        f"{subject} review record {index} is missing required properties: "
                        + ", ".join(missing_required)
                    )
                code = row.get(code_field)
                if isinstance(code, str) and code.strip():
                    review_property_fields[(subject, code.strip())] = set(seen_fields)

                if subject == "Service":
                    service_type_item = properties_by_field.get("service_type")
                    service_type = (
                        service_type_item.get("value")
                        if isinstance(service_type_item, dict)
                        else None
                    )
                    expected_semantics = (
                        "cable_bundle"
                        if is_cable_bundle_service(service_type)
                        else "cable_tray"
                        if is_cable_tray_service(service_type)
                        else None
                    )
                    if row.get("service_semantics") != expected_semantics:
                        errors.append("Service review semantics do not match service type")
                    bundle_fields = {"cable_count", "bundle_size_class"}
                    tray_fields = {"tray_width_mm", "tray_height_mm"}
                    if expected_semantics == "cable_bundle":
                        if "cable_count" not in seen_fields:
                            errors.append("Cable-bundle review requires cable_count")
                        cable_count = properties_by_field.get("cable_count", {}).get("value")
                        if cable_count is None and "bundle_size_class" not in seen_fields:
                            errors.append(
                                "Cable-bundle review with unknown cable count requires "
                                "bundle_size_class"
                            )
                        bundle_class = properties_by_field.get(
                            "bundle_size_class", {}
                        ).get("value")
                        if (
                            "bundle_size_class" in seen_fields
                            and bundle_class is not None
                            and bundle_class not in {"small", "medium", "large"}
                        ):
                            errors.append("Cable-bundle review size class is invalid")
                        if tray_fields & seen_fields:
                            errors.append("Cable-bundle review cannot contain tray fields")
                    elif expected_semantics == "cable_tray":
                        if not tray_fields.issubset(seen_fields):
                            errors.append("Cable-tray review requires tray dimensions")
                        if bundle_fields & seen_fields:
                            errors.append("Cable-tray review cannot contain bundle fields")
                    elif (bundle_fields | tray_fields) & seen_fields:
                        errors.append(
                            "Non-cable review cannot contain bundle or tray fields"
                        )
        requests = review.get("additional_evidence_required")
        if isinstance(requests, list):
            expected_request = {"subject", "code", "property", "requested_evidence", "reason"}
            seen_requests: set[tuple[str, str, str]] = set()
            actual_evidence_requests: list[tuple[str, str, str, str, str]] = []
            for request in requests:
                if not isinstance(request, dict) or set(request) != expected_request:
                    errors.append("proposal review evidence request is invalid")
                    continue
                if any(
                    not isinstance(request.get(field), str)
                    or not request[field].strip()
                    or len(request[field]) > _MAX_TEXT
                    for field in expected_request
                ):
                    errors.append("proposal review evidence request text is invalid")
                    continue
                target = (
                    str(request["subject"]).strip(),
                    str(request["code"]).strip(),
                    str(request["property"]).strip(),
                )
                if target in seen_requests:
                    errors.append("proposal review evidence request is duplicated")
                else:
                    seen_requests.add(target)
                if (
                    target[0] not in {"Opening", "Service"}
                    or target[:2] not in review_property_fields
                    or target[2] not in review_property_fields.get(target[:2], set())
                ):
                    errors.append("proposal review evidence request target is invalid")
                actual_evidence_requests.append(
                    (
                        target[0],
                        target[1],
                        target[2],
                        str(request["requested_evidence"]).strip(),
                        str(request["reason"]).strip(),
                    )
                )
            if sorted(actual_evidence_requests) != sorted(expected_evidence_requests):
                errors.append(
                    "proposal review evidence requests do not match property assessments"
                )
    return list(dict.fromkeys(errors))


def _markdown_text(value: object) -> str:
    if value is None:
        return "Unknown"
    if isinstance(value, dict):
        if set(value) == {"value", "unit"}:
            value = f"{value['value']} {value['unit']}"
        elif set(value) == {"minimum", "maximum", "unit"}:
            value = f"{value['minimum']}-{value['maximum']} {value['unit']}"
        else:
            value = "Unknown"
    elif isinstance(value, list):
        value = ", ".join(_markdown_text(item) for item in value) or "Unknown"
    elif not isinstance(value, (str, int, float)):
        value = "Unknown"
    text = " ".join(str(value).split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = text.replace("://", ": //").replace("www.", "www .")
    for character in "\\`[]()!#*_|":
        text = text.replace(character, chr(92) + character)
    return text or "Unknown"


def _render_property(item: dict[str, Any]) -> str:
    value = _markdown_text(item["value"])
    if item.get("unit") and not isinstance(item.get("value"), dict):
        value += " " + _markdown_text(item["unit"])
    suffix = f" - {str(item['status']).title()}"
    if item.get("confidence") is not None:
        suffix += f", {str(item['confidence']).title()} confidence"
    refs = ", ".join(_markdown_text(value) for value in item["evidence_refs"])
    rendered = (
        f"- {_markdown_text(item['label'])}: {value}{suffix}. "
        f"Evidence: {refs}. Reasoning: {_markdown_text(item['reasoning'])}."
    )
    if item.get("credible_alternative") is not None:
        rendered += (
            " Credible alternative: "
            + _markdown_text(item["credible_alternative"])
            + "."
        )
    return rendered


def render_phase8_proposal_review_markdown(review: object) -> str:
    """Render a validated review without allowing active untrusted Markdown."""

    errors = validate_phase8_proposal_review(review)
    if errors:
        raise Phase8ProposalReviewError(
            "PROPOSAL_REVIEW_RENDER_INVALID",
            "; ".join(errors),
        )
    if not isinstance(review, dict):
        raise Phase8ProposalReviewError("PROPOSAL_REVIEW_RENDER_INVALID")
    lines = [
        "# CLASSIFIRE proposal-only evidence review",
        "",
        f"- Defect: {_markdown_text(review['defect_reference'])}",
        f"- Package: {_markdown_text(review['package_id'])}",
        f"- Review status: {_markdown_text(review['review_status'])}",
        f"- Controller status: {_markdown_text(review['visual_proposal_status'])}",
        f"- Policy: {_markdown_text(review['policy_version'])}",
        (
            "- This record does not approve a physical model, select a technical "
            "system, price work, lock state, or release an output."
        ),
    ]
    blockers = review["controller_blockers"]
    if blockers:
        lines.extend(["", "## Controller blockers", ""])
        lines.extend(f"- {_markdown_text(item)}" for item in blockers)
    validation_errors = review["validation_errors"]
    if validation_errors:
        lines.extend(["", "## Proposal validation limitations", ""])
        lines.extend(f"- {_markdown_text(item)}" for item in validation_errors)
    for opening in review["openings"]:
        lines.extend(
            [
                "",
                f"## Opening {_markdown_text(opening['opening_code'])}",
                "",
                "**Opening and substrate**",
            ]
        )
        lines.extend(_render_property(item) for item in opening["properties"])
    for service in review["services"]:
        lines.extend(
            ["", f"## Service {_markdown_text(service['service_code'])}", "", "**Services**"]
        )
        lines.extend(_render_property(item) for item in service["properties"])
    if review["evidence_limitations"]:
        lines.extend(["", "## Evidence limitations", ""])
        lines.extend(f"- {_markdown_text(item)}" for item in review["evidence_limitations"])
    if review["additional_evidence_required"]:
        lines.extend(["", "## Additional evidence required", ""])
        for item in review["additional_evidence_required"]:
            labels = (
                _OPENING_LABELS
                if item.get("subject") == "Opening"
                else _SERVICE_LABELS
            )
            property_label = labels.get(
                item.get("property"),
                str(item.get("property") or ""),
            )
            lines.append(
                f"- {_markdown_text(item.get('subject'))} "
                f"{_markdown_text(item.get('code'))}, "
                f"{_markdown_text(property_label)}: "
                f"{_markdown_text(item.get('requested_evidence'))}. "
                f"Reason: {_markdown_text(item.get('reason'))}."
            )
    return "\n".join(lines) + "\n"


__all__ = [
    "PHASE8_PROPOSAL_REVIEW_SCHEMA",
    "Phase8ProposalReviewError",
    "build_phase8_proposal_review",
    "render_phase8_proposal_review_markdown",
    "validate_phase8_proposal_review",
]
