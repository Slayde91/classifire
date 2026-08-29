from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

import pytest
from test_phase8_visual_proposal import _blind_inventory, _proposal, _validator

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_proposal_review import (
    PHASE8_PROPOSAL_REVIEW_SCHEMA,
    Phase8ProposalReviewError,
    build_phase8_proposal_review,
    render_phase8_proposal_review_markdown,
    validate_phase8_proposal_review,
)
from classifire.services.phase8_visual_prompts import current_visual_prompt_profile_hashes
from classifire.services.phase8_visual_proposal import (
    LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_PROFILE_SCHEMA,
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    ProposalOnlyVisualController,
)


def _manifest() -> dict[str, Any]:
    return {
        "schema": VISUAL_EVIDENCE_MANIFEST_SCHEMA,
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "human_reference_included": False,
        "artifacts": [
            {
                "evidence_id": "E-001",
                "sha256": "1" * 64,
                "size_bytes": 1024,
                "media_type": "image/jpeg",
                "inference_allowed": True,
                "validation_only": False,
                "provenance": {
                    "source_reference": "report.pdf#page=1-image=1",
                    "page_number": 1,
                    "region_reference": "image-1",
                    "evidence_class": "observed",
                    "evidence_role": "primary_detail",
                    "relationship": "embedded_image",
                    "parent_evidence_id": None,
                    "pixel_width": 1600,
                    "pixel_height": 1200,
                },
            }
        ],
    }


class _Port:
    def __init__(self, proposal: dict[str, Any], *, validator: dict[str, Any] | None = None):
        self._responses = {
            "blind_inventory": _blind_inventory(),
            "physical_proposal": proposal,
            "conditioned_validator_0": validator or _validator(),
        }

    def invoke(self, *, role: str, stage: str, request: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
            "agent_id": role,
            "provider": "test-provider",
            "model": "validator-test-model" if role == "cf-validator" else "physical-test-model",
            "session_id_sha256": "7" * 64,
            "transport_receipt_sha256": "8" * 64,
            "tool_calls": [],
            "payload": deepcopy(self._responses[stage]),
        }


def _state() -> InitialSubmissionState:
    return InitialSubmissionState(
        estimate_id="EST-001",
        fingerprint="A" * 64,
        counts={
            "defect_count": 1,
            "evidence_count": 1,
            "opening_count": 0,
            "service_count": 0,
            "service_opening_link_count": 0,
            "active_physical_model_lock_count": 0,
        },
        snapshot={"schema": "CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1"},
    )


def _profile() -> dict[str, Any]:
    return {
        "schema": VISUAL_INFERENCE_PROFILE_SCHEMA,
        "implementation_revision": "a" * 40,
        "provider": "test-provider",
        "physical_model": "physical-test-model",
        "validator_model": "validator-test-model",
        **current_visual_prompt_profile_hashes(),
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def _review_inputs(proposal: dict[str, Any]) -> dict[str, Any]:
    manifest = _manifest()
    result = ProposalOnlyVisualController(
        run_id="RUN-001",
        estimate_id="EST-001",
        evidence_manifest=manifest,
        inference_profile=_profile(),
        inference_port=_Port(proposal),
        protected_state_reader=_state,
        max_correction_passes=0,
    ).run()
    assert result.proposal is not None
    proposal_bytes = _json_bytes(result.proposal)
    receipt_bytes = _json_bytes(result.receipt)
    return {
        "package_id": "PACKAGE-001",
        "package_sha256": "9" * 64,
        "approval_reference": "proposal-only approval",
        "proposal_file_bytes": proposal_bytes,
        "proposal_file_sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        "controller_receipt_file_bytes": receipt_bytes,
        "controller_receipt_file_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "evidence_manifest": manifest,
    }


def test_review_is_hash_bound_noncanonical_and_renders_every_assessment() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    markdown = render_phase8_proposal_review_markdown(review)

    assert review["schema"] == PHASE8_PROPOSAL_REVIEW_SCHEMA
    assert review["review_status"] == "ASSESSMENT_AVAILABLE"
    assert validate_phase8_proposal_review(review) == []
    assert review["proposal_only"] is True
    assert all(review[field] is False for field in (
        "canonical_submission_performed",
        "technical_selection_performed",
        "commercial_pricing_performed",
        "physical_model_lock_created",
        "human_release_performed",
    ))
    size = next(
        item for item in review["openings"][0]["properties"] if item["field"] == "size"
    )
    assert size["unit"] == "mm"
    assert "# CLASSIFIRE proposal-only evidence review" in markdown
    assert "100 mm" in markdown


@pytest.mark.parametrize("target", ["proposal", "receipt", "manifest"])
def test_review_detects_tampered_bound_inputs(target: str) -> None:
    inputs = _review_inputs(_proposal())
    if target == "proposal":
        inputs["proposal_file_bytes"] += b" "
        expected = "PROPOSAL_REVIEW_PROPOSAL_TAMPERED"
    elif target == "receipt":
        inputs["controller_receipt_file_bytes"] += b" "
        expected = "PROPOSAL_REVIEW_CONTROLLER_RECEIPT_TAMPERED"
    else:
        inputs["evidence_manifest"] = deepcopy(inputs["evidence_manifest"])
        inputs["evidence_manifest"]["defect_reference"] = "D-OTHER"
        expected = "PROPOSAL_REVIEW_MANIFEST_TAMPERED"

    with pytest.raises(Phase8ProposalReviewError, match=expected):
        build_phase8_proposal_review(**inputs)


def test_blocked_invalid_assessment_produces_safe_review_status() -> None:
    proposal = _proposal()
    proposal["services"][0]["property_assessments"]["material"]["evidence_refs"] = [
        "E-OUTSIDE"
    ]

    review = build_phase8_proposal_review(**_review_inputs(proposal))

    assert review["review_status"] == "INVALID_BLOCKED_PROPOSAL"
    assert review["proposal_outcome"] == "INVALID"
    assert any("outside the approved manifest" in item for item in review["validation_errors"])
    assert review["openings"] == []
    assert review["services"] == []


def test_review_rejects_rows_hidden_under_no_proposal_status() -> None:
    valid = build_phase8_proposal_review(**_review_inputs(_proposal()))
    forged = deepcopy(valid)
    forged["review_status"] = "NO_PROPOSAL"
    forged["input_bindings"]["proposal_file_sha256"] = None
    forged["input_bindings"]["proposal_canonical_sha256"] = None

    errors = validate_phase8_proposal_review(forged)

    assert any("must not contain openings" in error for error in errors)
    with pytest.raises(Phase8ProposalReviewError, match="PROPOSAL_REVIEW_RENDER_INVALID"):
        render_phase8_proposal_review_markdown(forged)


def test_review_rejects_status_value_contradiction() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    size = next(
        item for item in review["openings"][0]["properties"] if item["field"] == "size"
    )
    size["status"] = "UNKNOWN"

    errors = validate_phase8_proposal_review(review)

    assert any("UNKNOWN property must have null value" in error for error in errors)


def test_review_rejects_forged_negative_measurement() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    size = next(
        item for item in review["openings"][0]["properties"] if item["field"] == "size"
    )
    size["value"] = {"value": -100, "unit": "mm"}

    errors = validate_phase8_proposal_review(review)

    assert any("measurement values are invalid" in error for error in errors)


def test_review_rejects_forged_fields_labels_shapes_and_semantics() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    opening_properties = review["openings"][0]["properties"]
    size = next(item for item in opening_properties if item["field"] == "size")
    size["value"] = 100
    material = next(
        item
        for item in review["services"][0]["properties"]
        if item["field"] == "material"
    )
    material["label"] = "Technical system"
    opening_properties.append(
        {
            **size,
            "field": "technical_system",
            "label": "Technical system",
            "value": "unsupported selection",
        }
    )
    review["services"][0]["properties"] = [
        item
        for item in review["services"][0]["properties"]
        if item["field"] != "arrangement"
    ]
    review["services"][0]["service_semantics"] = "cable_bundle"

    errors = validate_phase8_proposal_review(review)

    assert any("field is unsupported: technical_system" in error for error in errors)
    assert any("property size" in error and "structured measurement" in error for error in errors)
    assert any("label does not match field" in error for error in errors)
    assert any("missing required properties: arrangement" in error for error in errors)
    assert any("semantics do not match service type" in error for error in errors)


def test_review_status_cannot_be_relabelled_across_policy_generations() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    review["review_status"] = "LEGACY_POLICY_UNASSESSED"
    review["openings"] = []
    review["services"] = []
    review["additional_evidence_required"] = []

    errors = validate_phase8_proposal_review(review)

    assert any("legacy-unassessed review requires legacy policy" in error for error in errors)


def test_review_status_cannot_contradict_bound_proposal_outcome() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    review["review_status"] = "INSUFFICIENT_EVIDENCE"
    review["openings"] = []
    review["services"] = []
    review["additional_evidence_required"] = []
    review["evidence_limitations"] = ["Forged limitation."]

    errors = validate_phase8_proposal_review(review)

    assert any(
        "requires an INSUFFICIENT_EVIDENCE proposal outcome" in error
        for error in errors
    )

    review["review_status"] = "NO_PROPOSAL"
    review["input_bindings"]["proposal_file_sha256"] = None
    review["input_bindings"]["proposal_canonical_sha256"] = None
    review["evidence_limitations"] = []
    errors = validate_phase8_proposal_review(review)
    assert any("requires a NONE proposal outcome" in error for error in errors)


def test_valid_blocked_review_cannot_be_relabelled_as_invalid() -> None:
    inputs = _review_inputs(_proposal())
    receipt = json.loads(inputs["controller_receipt_file_bytes"])
    receipt["status"] = "VISUAL_PROPOSAL_BLOCKED"
    receipt["errors"] = ["Human review is required."]
    receipt_bytes = _json_bytes(receipt)
    inputs["controller_receipt_file_bytes"] = receipt_bytes
    inputs["controller_receipt_file_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    review = build_phase8_proposal_review(**inputs)
    assert review["proposal_outcome"] == "MODEL_SUPPORTED"
    review["review_status"] = "INVALID_BLOCKED_PROPOSAL"
    review["openings"] = []
    review["services"] = []
    review["additional_evidence_required"] = []
    review["validation_errors"] = ["Forged invalidity claim."]

    errors = validate_phase8_proposal_review(review)

    assert any("requires an INVALID proposal outcome" in error for error in errors)


def test_review_rejects_unbounded_nested_values_and_unrelated_units() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    opening_links = next(
        item
        for item in review["services"][0]["properties"]
        if item["field"] == "opening_codes"
    )
    opening_links["value"] = ["O-" + ("x" * 5_000)]
    material = next(
        item
        for item in review["services"][0]["properties"]
        if item["field"] == "material"
    )
    material["unit"] = "mm"

    errors = validate_phase8_proposal_review(review)

    assert any("property list is invalid" in error for error in errors)
    assert any("unit does not match field semantics" in error for error in errors)


def test_review_malformed_unhashable_field_fails_closed_without_raising() -> None:
    review = build_phase8_proposal_review(**_review_inputs(_proposal()))
    review["services"][0]["properties"][0]["field"] = []

    errors = validate_phase8_proposal_review(review)

    assert any("property field is invalid" in error for error in errors)


def test_relabelled_v2_proposal_cannot_be_reviewed_as_legacy_v1() -> None:
    inputs = _review_inputs(_proposal())
    receipt = json.loads(inputs["controller_receipt_file_bytes"])
    receipt["policy_version"] = LEGACY_VISUAL_PROPOSAL_POLICY_VERSION
    receipt_bytes = _json_bytes(receipt)
    inputs["controller_receipt_file_bytes"] = receipt_bytes
    inputs["controller_receipt_file_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()

    with pytest.raises(
        Phase8ProposalReviewError,
        match="PROPOSAL_REVIEW_CONTROLLER_RECEIPT_INVALID",
    ):
        build_phase8_proposal_review(**inputs)


def test_insufficient_evidence_is_not_labelled_as_assessment_available() -> None:
    proposal = {
        "status": "INSUFFICIENT_EVIDENCE",
        "assessment_schema": "CLASSIFIRE-PHASE8-PROPERTY-ASSESSMENTS-v2",
        "limitations": ["The opening boundary cannot be resolved from the supplied view."],
        "openings": [],
        "services": [],
    }

    review = build_phase8_proposal_review(**_review_inputs(proposal))

    assert review["review_status"] == "INSUFFICIENT_EVIDENCE"
    assert review["openings"] == []
    assert review["services"] == []
    assert review["evidence_limitations"] == proposal["limitations"]
    assert validate_phase8_proposal_review(review) == []


def test_failed_controller_without_proposal_builds_safe_no_proposal_review() -> None:
    inputs = _review_inputs(_proposal())
    receipt = json.loads(inputs["controller_receipt_file_bytes"])
    receipt["status"] = "VISUAL_PROPOSAL_FAILED"
    receipt["errors"] = ["The model response was unavailable. " + ("x" * 3_000)]
    receipt["result_hashes"] = {
        "blind_inventory_sha256": None,
        "proposal_sha256": None,
        "validator_sha256": None,
    }
    receipt_bytes = _json_bytes(receipt)
    inputs["controller_receipt_file_bytes"] = receipt_bytes
    inputs["controller_receipt_file_sha256"] = hashlib.sha256(receipt_bytes).hexdigest()
    inputs["proposal_file_bytes"] = None
    inputs["proposal_file_sha256"] = None

    review = build_phase8_proposal_review(**inputs)

    assert review["review_status"] == "NO_PROPOSAL"
    assert review["openings"] == []
    assert review["services"] == []
    assert len(review["controller_blockers"][0]) <= 2_000
    assert "truncated; see hash-bound source artifact" in review["controller_blockers"][0]
    assert validate_phase8_proposal_review(review) == []


def test_long_proposal_limitation_is_safely_bounded_in_review_copy() -> None:
    proposal = _proposal()
    proposal["limitations"] = ["limited view " + ("x" * 3_000)]

    review = build_phase8_proposal_review(**_review_inputs(proposal))

    assert len(review["evidence_limitations"][0]) <= 2_000
    assert "truncated; see hash-bound source artifact" in review["evidence_limitations"][0]
    assert validate_phase8_proposal_review(review) == []


def test_additional_evidence_is_explicit_not_automatic_for_unknowns() -> None:
    proposal = _proposal()
    unknown = proposal["openings"][0]["property_assessments"]["opposite_face_continuity"]
    assert unknown["status"] == "UNKNOWN"
    review = build_phase8_proposal_review(**_review_inputs(proposal))
    assert review["additional_evidence_required"] == []

    unknown["additional_evidence_required"] = (
        "A report drawing that confirms whether the wall continues on the opposite face."
    )
    review = build_phase8_proposal_review(**_review_inputs(proposal))
    assert len(review["additional_evidence_required"]) == 1
    assert review["additional_evidence_required"][0]["property"] == (
        "opposite_face_continuity"
    )
    assert validate_phase8_proposal_review(review) == []
    assert "Opposite-face continuity" in render_phase8_proposal_review_markdown(review)

    changed = deepcopy(review)
    changed["additional_evidence_required"][0]["reason"] = "Forged reason."
    assert any(
        "do not match property assessments" in error
        for error in validate_phase8_proposal_review(changed)
    )
    omitted = deepcopy(review)
    omitted["additional_evidence_required"] = []
    assert any(
        "do not match property assessments" in error
        for error in validate_phase8_proposal_review(omitted)
    )


def test_known_count_bundle_with_optional_unknown_size_class_round_trips() -> None:
    proposal = _proposal()
    service = proposal["services"][0]
    service["service_type"] = "cable_bundle"
    service["cable_count"] = 8
    service["bundle_size_class"] = None
    service["property_assessments"]["service_type"]["reasoning"] = (
        "The supplied evidence supports a cable bundle."
    )
    service["property_assessments"]["cable_count"] = {
        "status": "INFERRED",
        "confidence": "MEDIUM",
        "reasoning": "Eight cables can reasonably be distinguished in the supplied view.",
        "evidence_refs": ["E-001"],
        "credible_alternative": None,
        "additional_evidence_required": None,
    }
    service["property_assessments"]["bundle_size_class"] = {
        "status": "UNKNOWN",
        "confidence": None,
        "reasoning": "A bundle class is not needed because cable count is available.",
        "evidence_refs": ["E-001"],
        "credible_alternative": None,
        "additional_evidence_required": None,
    }

    review = build_phase8_proposal_review(**_review_inputs(proposal))

    assert review["services"][0]["service_semantics"] == "cable_bundle"
    assert validate_phase8_proposal_review(review) == []


def test_markdown_neutralises_links_images_html_and_model_markup() -> None:
    proposal = _proposal()
    assessment = proposal["services"][0]["property_assessments"]["material"]
    assessment["reasoning"] = "[click](https://unsafe.example) ![x](bad) <img src=x>"
    review = build_phase8_proposal_review(**_review_inputs(proposal))

    markdown = render_phase8_proposal_review_markdown(review)

    assert "https://" not in markdown
    assert "<img" not in markdown
    assert "![x]" not in markdown
