from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_property_assessments import PROPERTY_ASSESSMENT_SCHEMA
from classifire.services.phase8_visual_prompts import current_visual_prompt_profile_hashes
from classifire.services.phase8_visual_proposal import (
    LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
    LEGACY_VISUAL_PROPOSAL_RECEIPT_SCHEMA,
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_PROFILE_SCHEMA,
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    VISUAL_PROPOSAL_APPROVED,
    VISUAL_PROPOSAL_BLOCKED,
    VISUAL_PROPOSAL_FAILED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED,
    VISUAL_PROPOSAL_RECEIPT_SCHEMA,
    Phase8VisualProposalError,
    ProposalOnlyVisualController,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_visual_evidence_manifest,
    validate_visual_inference_profile,
    validate_visual_inference_response,
    validate_visual_physical_proposal,
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


def _profile() -> dict[str, Any]:
    return {
        "schema": VISUAL_INFERENCE_PROFILE_SCHEMA,
        "implementation_revision": "a" * 40,
        "provider": "test-provider",
        "physical_model": "physical-test-model",
        "validator_model": "validator-test-model",
        **current_visual_prompt_profile_hashes(),
    }


def _state(*, fingerprint: str = "A" * 64, opening_count: int = 0) -> InitialSubmissionState:
    return InitialSubmissionState(
        estimate_id="EST-001",
        fingerprint=fingerprint,
        counts={
            "defect_count": 1,
            "evidence_count": 1,
            "opening_count": opening_count,
            "service_count": 0,
            "service_opening_link_count": 0,
            "active_physical_model_lock_count": 0,
        },
        snapshot={"schema": "CLASSIFIRE-INITIAL-SUBMISSION-STATE-v1"},
    )


def _blind_inventory() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "one opening",
                "evidence_refs": ["E-001"],
            }
        ],
        "candidate_services": [
            {
                "candidate_id": "V-S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "candidate_opening_ids": ["V-O-001"],
                "detail": "one pipe group",
                "evidence_refs": ["E-001"],
            }
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _assessment(value: object) -> dict[str, Any]:
    return {
        "status": "UNKNOWN" if value is None else "CONFIRMED",
        "confidence": None,
        "reasoning": (
            "The supplied view cannot support this value."
            if value is None
            else "The supplied synthetic evidence directly supports this value."
        ),
        "evidence_refs": ["E-001"],
        "credible_alternative": None,
        "additional_evidence_required": None,
    }


def _proposal(*, quantity: int = 1) -> dict[str, Any]:
    opening = {
        "external_defect_id": "D-001",
        "opening_code": "O-001",
        "shape": "circular",
        "size": {"value": 100, "unit": "mm"},
        "opening_type": "service_penetration",
        "substrate_plane": "wall",
        "substrate_type": "concrete",
        "substrate_specific_type": "solid concrete wall",
        "substrate_thickness": {"value": 100, "unit": "mm"},
        "orientation": "vertical",
        "opening_boundary": "visible circular boundary",
        "opposite_face_continuity": None,
    }
    service = {
        "service_code": "S-001",
        "quantity": quantity,
        "service_type": "pipe",
        "material": "PVC",
        "size": {"value": 50, "unit": "mm"},
        "insulation_or_covering": "uninsulated",
        "arrangement": "single service",
        "primary_opening_code": "O-001",
        "opening_codes": ["O-001"],
        "link_type": "penetrates",
        "relationship_status": "confirmed",
        "concealed_continuity": None,
        "evidence_status": "confirmed",
        "source_reference": "E-001",
        "confidence": "0.95",
    }
    opening["property_assessments"] = {
        field: _assessment(opening[field])
        for field in (
            "shape",
            "size",
            "opening_type",
            "substrate_plane",
            "substrate_type",
            "substrate_specific_type",
            "substrate_thickness",
            "orientation",
            "opening_boundary",
            "opposite_face_continuity",
        )
    }
    service["property_assessments"] = {
        field: _assessment(service[field])
        for field in (
            "quantity",
            "service_type",
            "material",
            "size",
            "insulation_or_covering",
            "arrangement",
            "primary_opening_code",
            "opening_codes",
            "link_type",
            "relationship_status",
            "concealed_continuity",
        )
    }
    return {
        "status": "MODEL_SUPPORTED",
        "assessment_schema": PROPERTY_ASSESSMENT_SCHEMA,
        "limitations": [],
        "openings": [opening],
        "services": [service],
    }


def _validator(
    *,
    verdict: str = "APPROVED",
    issue_code: str | None = None,
) -> dict[str, Any]:
    issue = (
        {
            "code": issue_code,
            "detail": "structured correction required",
            "evidence_refs": ["E-001"],
        }
        if issue_code
        else None
    )
    if issue is not None and issue_code == "WRONG_SERVICE_QUANTITY":
        issue.update(
            {
                "subject": "Service",
                "subject_code": "S-001",
                "property": "quantity",
            }
        )
    issues = [issue] if issue is not None else []
    return {
        "verdict": verdict,
        "issues": issues,
        "limitations": [],
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "blind_reconciliation": [
            {
                "blind_candidate_id": "V-O-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["O-001"],
                "detail": "Opening accounted for",
                "evidence_refs": ["E-001"],
            },
            {
                "blind_candidate_id": "V-S-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["S-001"],
                "detail": "Service accounted for",
                "evidence_refs": ["E-001"],
            },
        ],
    }


class ScriptedInferencePort:
    def __init__(self, responses: dict[str, list[Any]]) -> None:
        self.responses = {name: list(values) for name, values in responses.items()}
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> Any:
        self.calls.append({"role": role, "stage": stage, "request": deepcopy(request)})
        values = self.responses.get(stage)
        if not values:
            raise AssertionError(f"unexpected inference stage: {stage}")
        value = values.pop(0)
        if isinstance(value, Exception):
            raise value
        return {
            "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
            "agent_id": role,
            "provider": "test-provider",
            "model": ("validator-test-model" if role == "cf-validator" else "physical-test-model"),
            "session_id_sha256": "7" * 64,
            "transport_receipt_sha256": "8" * 64,
            "tool_calls": [],
            "payload": deepcopy(value),
        }


def _controller(
    port: ScriptedInferencePort,
    *,
    state_reader=lambda: _state(),  # noqa: B008
    manifest: dict[str, Any] | None = None,
    max_correction_passes: int = 2,
) -> ProposalOnlyVisualController:
    return ProposalOnlyVisualController(
        run_id="RUN-001",
        estimate_id="EST-001",
        evidence_manifest=manifest or _manifest(),
        inference_profile=_profile(),
        inference_port=port,
        protected_state_reader=state_reader,
        max_correction_passes=max_correction_passes,
    )


def test_evidence_manifest_forbids_human_reference_and_validation_only_artifacts() -> None:
    manifest = _manifest()
    manifest["human_reference_included"] = True
    manifest["artifacts"][0]["validation_only"] = True
    manifest["artifacts"][0]["inference_allowed"] = False
    manifest["artifacts"][0]["provenance"]["evidence_role"] = "human_reference"

    errors = validate_visual_evidence_manifest(manifest, estimate_id="EST-001")

    assert any("human-reference" in error for error in errors)
    assert any("validation-only" in error for error in errors)
    assert any("not approved for inference" in error for error in errors)
    assert any("provenance is forbidden" in error for error in errors)


def test_evidence_manifest_binds_linked_original_to_retained_context() -> None:
    manifest = _manifest()
    linked = deepcopy(manifest["artifacts"][0])
    linked["evidence_id"] = "E-002"
    linked["sha256"] = "9" * 64
    linked["size_bytes"] = 4096
    linked["provenance"]["source_reference"] = "approved-host/original.jpg"
    linked["provenance"]["evidence_role"] = "primary_detail"
    linked["provenance"]["relationship"] = "linked_original"
    linked["provenance"]["parent_evidence_id"] = "E-001"
    linked["provenance"]["pixel_width"] = 3200
    linked["provenance"]["pixel_height"] = 2400
    manifest["artifacts"][0]["provenance"]["evidence_role"] = "page_context"
    manifest["artifacts"].append(linked)

    assert validate_visual_evidence_manifest(manifest, estimate_id="EST-001") == []


def test_evidence_manifest_allows_linked_original_to_retain_external_parent_lineage() -> None:
    manifest = _manifest()
    provenance = manifest["artifacts"][0]["provenance"]
    provenance["relationship"] = "linked_original"
    provenance["parent_evidence_id"] = "retained-report-evidence"

    assert validate_visual_evidence_manifest(manifest, estimate_id="EST-001") == []


def test_evidence_manifest_rejects_unknown_parent_and_missing_image_dimensions() -> None:
    manifest = _manifest()
    provenance = manifest["artifacts"][0]["provenance"]
    provenance["parent_evidence_id"] = "E-MISSING"
    provenance["pixel_width"] = None

    errors = validate_visual_evidence_manifest(manifest, estimate_id="EST-001")

    assert any("unknown parent evidence" in error for error in errors)
    assert any("requires pixel dimensions" in error for error in errors)


def test_evidence_manifest_rejects_parent_cycles() -> None:
    manifest = _manifest()
    second = deepcopy(manifest["artifacts"][0])
    second["evidence_id"] = "E-002"
    second["sha256"] = "9" * 64
    second["provenance"]["source_reference"] = "report.pdf#page=1-image=2"
    second["provenance"]["parent_evidence_id"] = "E-001"
    manifest["artifacts"][0]["provenance"]["parent_evidence_id"] = "E-002"
    manifest["artifacts"].append(second)

    errors = validate_visual_evidence_manifest(manifest, estimate_id="EST-001")

    assert any("parent relationships contain a cycle" in error for error in errors)


def test_inference_profile_requires_prompt_runtime_and_implementation_bindings() -> None:
    profile = _profile()
    profile["implementation_revision"] = "short"
    profile["validator_prompt_sha256"] = "bad"

    errors = validate_visual_inference_profile(profile)

    assert any("implementation revision" in error for error in errors)
    assert any("validator_prompt_sha256" in error for error in errors)


def test_controller_rejects_noncurrent_policy_hashes_before_any_port_call() -> None:
    profile = _profile()
    profile["runtime_policy_sha256"] = "F" * 64
    port = ScriptedInferencePort({})

    with pytest.raises(Phase8VisualProposalError) as caught:
        ProposalOnlyVisualController(
            run_id="RUN-001",
            estimate_id="EST-001",
            evidence_manifest=_manifest(),
            inference_profile=profile,
            inference_port=port,
            protected_state_reader=_state,
        )

    assert caught.value.code == "INFERENCE_PROFILE_POLICY_MISMATCH"
    assert port.calls == []


def test_inference_response_rejects_wrong_model_and_tool_calls() -> None:
    response = {
        "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
        "agent_id": "cf-validator",
        "provider": "test-provider",
        "model": "wrong-model",
        "session_id_sha256": "7" * 64,
        "transport_receipt_sha256": "8" * 64,
        "tool_calls": ["classifire_evidence_read"],
        "payload": _blind_inventory(),
    }

    errors = validate_visual_inference_response(
        response,
        role="cf-validator",
        profile=_profile(),
    )

    assert any("model does not match" in error for error in errors)
    assert any("forbidden tool call" in error for error in errors)


def test_physical_proposal_preserves_blank_and_service_relationship_semantics() -> None:
    proposal = _proposal()
    proposal["openings"][0]["opening_type"] = "blank_core_hole"

    errors = validate_visual_physical_proposal(proposal, defect_reference="D-001")

    assert any("blank but has linked Services" in error for error in errors)


def test_physical_proposal_rejects_wrong_defect_and_duplicate_service_codes() -> None:
    proposal = _proposal()
    proposal["openings"][0]["external_defect_id"] = "D-OTHER"
    proposal["services"].append(deepcopy(proposal["services"][0]))

    errors = validate_visual_physical_proposal(proposal, defect_reference="D-001")

    assert any("not bound to defect D-001" in error for error in errors)
    assert any("Service code is duplicated" in error for error in errors)


def test_physical_proposal_requires_explicit_service_uncertainty_and_provenance() -> None:
    proposal = _proposal()
    service = proposal["services"][0]
    del service["material"]
    del service["quantity"]
    service["evidence_status"] = ""
    service["confidence"] = "1.5"

    errors = validate_visual_physical_proposal(proposal, defect_reference="D-001")

    assert any("must state material or null" in error for error in errors)
    assert any("must state quantity or null" in error for error in errors)
    assert any("requires evidence_status" in error for error in errors)
    assert any("confidence must be 0..1" in error for error in errors)


def test_physical_proposal_rejects_infinite_quantity() -> None:
    proposal = _proposal()
    proposal["services"][0]["quantity"] = "Infinity"

    errors = validate_visual_physical_proposal(proposal, defect_reference="D-001")

    assert any("quantity must be positive or null" in error for error in errors)


def test_physical_proposal_rejects_nan_confidence_without_raising() -> None:
    proposal = _proposal()
    proposal["services"][0]["confidence"] = "NaN"

    errors = validate_visual_physical_proposal(proposal, defect_reference="D-001")

    assert any("confidence must be 0..1" in error for error in errors)


def test_physical_proposal_supports_mixed_blank_and_occupied_openings() -> None:
    proposal = _proposal()
    proposal["openings"].append(
        {
            "external_defect_id": "D-001",
            "opening_code": "O-002",
            "substrate_type": "concrete",
            "substrate_plane": "wall",
            "orientation": "vertical",
            "opening_type": "blank_core_hole",
        }
    )

    assert validate_visual_physical_proposal(proposal, defect_reference="D-001") == []


def test_physical_proposal_supports_one_service_across_multiple_openings() -> None:
    proposal = _proposal()
    proposal["openings"].append(
        {
            "external_defect_id": "D-001",
            "opening_code": "O-002",
            "substrate_type": "plasterboard",
            "substrate_plane": "wall",
            "orientation": "vertical",
            "opening_type": "service_penetration",
        }
    )
    proposal["services"][0]["opening_codes"] = ["O-001", "O-002"]

    assert validate_visual_physical_proposal(proposal, defect_reference="D-001") == []


def test_physical_proposal_supports_an_all_blank_defect_without_placeholder_service() -> None:
    proposal = _proposal()
    proposal["openings"][0]["opening_type"] = "blank_opening"
    proposal["services"] = []

    assert validate_visual_physical_proposal(proposal, defect_reference="D-001") == []


def test_controller_approves_only_after_independent_blind_and_conditioned_passes() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_APPROVED
    assert result.approved is True
    assert result.errors == ()
    assert validate_phase8_visual_proposal_receipt(result.receipt) == []
    assert result.receipt["result_hashes"] == {
        "blind_inventory_sha256": canonical_json_sha256(_blind_inventory()),
        "proposal_sha256": canonical_json_sha256(_proposal()),
        "validator_sha256": canonical_json_sha256(_validator()),
    }
    assert [call["stage"] for call in port.calls] == [
        "blind_inventory",
        "physical_proposal",
        "conditioned_validator_0",
    ]
    blind_input = port.calls[0]["request"]["stage_input"]
    physical_input = port.calls[1]["request"]["stage_input"]
    validator_input = port.calls[2]["request"]["stage_input"]
    assert blind_input == {
        "proposal_visible": False,
        "validator_receipt_visible": False,
    }
    assert physical_input == {
        "blind_inventory_visible": False,
        "validator_receipt_visible": False,
    }
    assert validator_input["blind_inventory"] == _blind_inventory()
    assert validator_input["proposal"] == _proposal()
    for call in port.calls:
        assert call["request"]["allowed_tools"] == []
        assert call["request"]["human_reference_visible"] is False
        assert call["request"]["policy_version"] == VISUAL_PROPOSAL_POLICY_VERSION
        assert call["request"]["inference_profile"] == _profile()
        assert call["request"]["inference_profile_sha256"] == canonical_json_sha256(_profile())
    assert result.receipt["policy_version"] == VISUAL_PROPOSAL_POLICY_VERSION


@pytest.mark.parametrize("failure", ["missing", "outside"])
def test_current_policy_blocks_missing_or_out_of_manifest_assessments(failure: str) -> None:
    proposal = _proposal()
    if failure == "missing":
        del proposal["services"][0]["property_assessments"]["arrangement"]
    else:
        proposal["services"][0]["property_assessments"]["arrangement"]["evidence_refs"] = [
            "E-OUTSIDE"
        ]
    result = _controller(
        ScriptedInferencePort(
            {
                "blind_inventory": [_blind_inventory()],
                "physical_proposal": [proposal],
            }
        ),
        max_correction_passes=0,
    ).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert result.approved is False


def test_receipt_validator_keeps_literal_v1_history_and_rejects_future_policy() -> None:
    result = _controller(
        ScriptedInferencePort(
            {
                "blind_inventory": [_blind_inventory()],
                "physical_proposal": [_proposal()],
                "conditioned_validator_0": [_validator()],
            }
        )
    ).run()
    historical = deepcopy(result.receipt)
    historical["schema"] = LEGACY_VISUAL_PROPOSAL_RECEIPT_SCHEMA
    historical["policy_version"] = LEGACY_VISUAL_PROPOSAL_POLICY_VERSION
    assert validate_phase8_visual_proposal_receipt(historical) == []
    relabelled = deepcopy(result.receipt)
    relabelled["policy_version"] = LEGACY_VISUAL_PROPOSAL_POLICY_VERSION
    assert any(
        "schema does not match policy version" in error
        for error in validate_phase8_visual_proposal_receipt(relabelled)
    )
    assert result.receipt["schema"] == VISUAL_PROPOSAL_RECEIPT_SCHEMA

    future = deepcopy(result.receipt)
    future["policy_version"] = "CLASSIFIRE-PHASE8-VISUAL-PROPOSAL-v999"
    assert "visual proposal receipt policy version is unsupported" in (
        validate_phase8_visual_proposal_receipt(future)
    )


def test_receipt_is_deterministic_for_identical_inputs_and_responses() -> None:
    responses = {
        "blind_inventory": [_blind_inventory()],
        "physical_proposal": [_proposal()],
        "conditioned_validator_0": [_validator()],
    }
    first = _controller(ScriptedInferencePort(responses)).run()
    second = _controller(ScriptedInferencePort(responses)).run()

    assert first.receipt == second.receipt
    assert first.receipt_sha256 == second.receipt_sha256


def test_invalid_blind_inventory_gets_one_blind_retry_then_blocks() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [{"status": "COMPLETE"}],
            "blind_inventory_retry": [{"status": "COMPLETE"}],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert result.approved is False
    assert any("blind inventory remained invalid" in error for error in result.errors)
    assert [call["stage"] for call in port.calls] == [
        "blind_inventory",
        "blind_inventory_retry",
    ]


def test_incomplete_physical_proposal_retries_without_seeing_blind_inventory() -> None:
    insufficient = {
        "status": "INSUFFICIENT_EVIDENCE",
        "limitations": ["first pass incomplete"],
        "openings": [],
        "services": [],
    }
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [insufficient],
            "physical_structural_retry_1": [_proposal()],
            "conditioned_validator_1": [_validator()],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_APPROVED
    retry_input = port.calls[2]["request"]["stage_input"]
    assert retry_input["blind_inventory_visible"] is False
    assert "blind_inventory" not in retry_input


def test_rejected_validator_allows_one_in_scope_quantity_correction() -> None:
    corrected = _proposal(quantity=2)
    corrected["services"][0]["property_assessments"]["quantity"]["reasoning"] = (
        "The corrected synthetic evidence supports two service groups."
    )
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [
                _validator(verdict="REJECTED", issue_code="WRONG_SERVICE_QUANTITY")
            ],
            "physical_correction_1": [corrected],
            "conditioned_validator_1": [_validator()],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_APPROVED
    assert result.proposal == corrected
    assert [call["stage"] for call in port.calls] == [
        "blind_inventory",
        "physical_proposal",
        "conditioned_validator_0",
        "physical_correction_1",
        "conditioned_validator_1",
    ]
    correction_input = port.calls[3]["request"]["stage_input"]
    assert correction_input["blind_inventory_visible"] is False
    assert "blind_inventory" not in correction_input


def test_ambiguous_size_or_quantity_authority_blocks_before_correction() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [
                _validator(
                    verdict="REJECTED",
                    issue_code="UNSUPPORTED_SIZE_OR_QUANTITY",
                )
            ],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert any("ambiguous" in error for error in result.errors)
    assert all(not call["stage"].startswith("physical_correction") for call in port.calls)


def test_out_of_scope_physical_correction_is_rejected() -> None:
    corrected = _proposal()
    corrected["services"][0]["material"] = "copper"
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [
                _validator(verdict="REJECTED", issue_code="WRONG_SERVICE_QUANTITY")
            ],
            "physical_correction_1": [corrected],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert any("exceeded Validator authority" in error for error in result.errors)
    assert any("material" in error for error in result.errors)


def test_incomplete_scoped_correction_is_terminal_without_structural_retry() -> None:
    corrected = _proposal(quantity=0)
    corrected["services"][0]["property_assessments"]["quantity"]["reasoning"] = (
        "This deliberately invalid correction must reach structural validation."
    )
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [
                _validator(verdict="REJECTED", issue_code="WRONG_SERVICE_QUANTITY")
            ],
            "physical_correction_1": [corrected],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert any("remained incomplete" in error for error in result.errors)
    assert all("structural_retry" not in call["stage"] for call in port.calls)


def test_malformed_validator_gets_one_format_retry() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [{"verdict": "APPROVED"}],
            "conditioned_validator_retry_0": [_validator()],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_APPROVED
    assert [call["stage"] for call in port.calls][-1] == "conditioned_validator_retry_0"


def test_blocked_validator_returns_actionable_limitations_without_correction() -> None:
    validator = _validator(verdict="BLOCKED")
    validator["limitations"] = ["photo relationship is unresolved"]
    validator["blind_reconciliation"][0]["disposition"] = "UNRESOLVED"
    validator["blind_reconciliation"][0]["proposal_refs"] = []
    validator["blind_reconciliation"][1]["disposition"] = "UNRESOLVED"
    validator["blind_reconciliation"][1]["proposal_refs"] = []
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [validator],
        }
    )

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_BLOCKED
    assert any("photo relationship is unresolved" in error for error in result.errors)
    assert all(not call["stage"].startswith("physical_correction") for call in port.calls)


def test_nonempty_protected_state_stops_before_inference() -> None:
    port = ScriptedInferencePort({})

    with pytest.raises(Phase8VisualProposalError) as rejected:
        _controller(port, state_reader=lambda: _state(opening_count=1)).run()

    assert rejected.value.code == "PROTECTED_STATE_NOT_EMPTY"
    assert port.calls == []


def test_protected_state_change_overrides_inference_result_and_fails_closed() -> None:
    current = {"state": _state()}

    class MutatingPort(ScriptedInferencePort):
        def invoke(
            self,
            *,
            role: str,
            stage: str,
            request: dict[str, Any],
        ) -> Any:
            result = super().invoke(role=role, stage=stage, request=request)
            current["state"] = _state(fingerprint="B" * 64)
            return result

    port = MutatingPort({"blind_inventory": [_blind_inventory()]})

    result = _controller(port, state_reader=lambda: current["state"]).run()

    assert result.status == VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED
    assert result.approved is False
    assert result.receipt["protected_state"]["unchanged"] is False
    assert any("protected state changed" in error for error in result.errors)
    assert validate_phase8_visual_proposal_receipt(result.receipt) == []


def test_protected_state_count_change_still_produces_a_valid_failure_receipt() -> None:
    current = {"state": _state()}

    class MutatingPort(ScriptedInferencePort):
        def invoke(
            self,
            *,
            role: str,
            stage: str,
            request: dict[str, Any],
        ) -> Any:
            result = super().invoke(role=role, stage=stage, request=request)
            current["state"] = _state(fingerprint="B" * 64, opening_count=1)
            return result

    result = _controller(
        MutatingPort({"blind_inventory": [_blind_inventory()]}),
        state_reader=lambda: current["state"],
    ).run()

    assert result.status == VISUAL_PROPOSAL_PROTECTED_STATE_CHANGED
    assert validate_phase8_visual_proposal_receipt(result.receipt) == []


def test_inference_port_failure_is_audited_and_returns_failed_receipt() -> None:
    port = ScriptedInferencePort({"blind_inventory": [RuntimeError("transport failed")]})

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_FAILED
    assert result.approved is False
    assert result.receipt["stages"][0]["failed"] is True
    assert any("INFERENCE_PORT_FAILED" in error for error in result.errors)
    assert validate_phase8_visual_proposal_receipt(result.receipt) == []
    relabelled = deepcopy(result.receipt)
    relabelled["policy_version"] = LEGACY_VISUAL_PROPOSAL_POLICY_VERSION
    assert any(
        "schema does not match policy version" in error
        for error in validate_phase8_visual_proposal_receipt(relabelled)
    )


def test_controller_stops_when_transport_reports_any_tool_call() -> None:
    class ToolUsingPort(ScriptedInferencePort):
        def invoke(
            self,
            *,
            role: str,
            stage: str,
            request: dict[str, Any],
        ) -> Any:
            response = super().invoke(role=role, stage=stage, request=request)
            response["tool_calls"] = ["classifire_evidence_read"]
            return response

    port = ToolUsingPort({"blind_inventory": [_blind_inventory()]})

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_FAILED
    assert result.receipt["stages"][0]["failed"] is True
    assert any("forbidden tool call" in error for error in result.errors)
    assert validate_phase8_visual_proposal_receipt(result.receipt) == []


def test_non_json_inference_response_is_audited_and_fails_closed() -> None:
    port = ScriptedInferencePort({"blind_inventory": [object()]})

    result = _controller(port).run()

    assert result.status == VISUAL_PROPOSAL_FAILED
    assert result.receipt["stages"][0]["failed"] is True
    assert any("INFERENCE_RESPONSE_NOT_JSON" in error for error in result.errors)


def test_receipt_validator_rejects_write_claim_and_changed_approved_state() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    result = _controller(port).run()
    receipt = deepcopy(result.receipt)
    receipt["controller_canonical_write_performed"] = True
    receipt["protected_state"]["unchanged"] = False

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("controller_canonical_write_performed must be false" in error for error in errors)
    assert any("requires unchanged protected state" in error for error in errors)


def test_controller_rejects_human_reference_manifest_before_inference() -> None:
    manifest = _manifest()
    manifest["human_reference_included"] = True
    port = ScriptedInferencePort({})

    with pytest.raises(Phase8VisualProposalError) as rejected:
        _controller(port, manifest=manifest)

    assert rejected.value.code == "EVIDENCE_MANIFEST_INVALID"
    assert port.calls == []


def test_controller_is_single_use() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    controller = _controller(port)
    assert controller.run().approved is True

    with pytest.raises(Phase8VisualProposalError) as rejected:
        controller.run()

    assert rejected.value.code == "CONTROLLER_ALREADY_RUN"


def test_canonical_hash_rejects_nonfinite_json_numbers() -> None:
    with pytest.raises(Phase8VisualProposalError) as rejected:
        canonical_json_sha256({"quantity": float("nan")})

    assert rejected.value.code == "NON_JSON_VALUE"


def test_receipt_validator_rejects_unknown_stage_and_role_mismatch() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    receipt = deepcopy(_controller(port).run().receipt)
    receipt["stages"][0]["stage"] = "uncontrolled_operation"
    receipt["stages"][1]["role"] = "cf-validator"

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("stage 1 name is unsupported" in error for error in errors)
    assert any("stage 2 role does not match stage" in error for error in errors)


def test_receipt_validator_rejects_unapproved_extension_fields() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    receipt = deepcopy(_controller(port).run().receipt)
    receipt["unapproved_extension"] = True
    receipt["stages"][0]["database_write"] = False
    receipt["protected_state"]["snapshot"] = {}
    receipt["result_hashes"]["other_sha256"] = "9" * 64

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("receipt fields do not match" in error for error in errors)
    assert any("stage 1 fields do not match" in error for error in errors)
    assert any("protected_state fields do not match" in error for error in errors)
    assert any("result_hashes fields do not match" in error for error in errors)


def test_receipt_validator_rejects_reordered_and_nonterminal_failed_stages() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    receipt = deepcopy(_controller(port).run().receipt)
    receipt["stages"][0]["stage"], receipt["stages"][1]["stage"] = (
        receipt["stages"][1]["stage"],
        receipt["stages"][0]["stage"],
    )
    receipt["stages"][0]["failed"] = True

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("must begin with blind_inventory" in error for error in errors)
    assert any("failed inference stage must terminate" in error for error in errors)


def test_receipt_validator_rejects_repeated_validator_without_physical_correction() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    receipt = deepcopy(_controller(port).run().receipt)
    repeated = deepcopy(receipt["stages"][-1])
    repeated["sequence"] = 4
    repeated["stage"] = "conditioned_validator_1"
    receipt["stages"].append(repeated)
    receipt["result_hashes"]["validator_sha256"] = repeated["payload_sha256"]

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any(
        "conditioned Validator pass requires a preceding Physical proposal" in error
        for error in errors
    )


def test_receipt_validator_rejects_cross_role_result_hash_substitution() -> None:
    port = ScriptedInferencePort(
        {
            "blind_inventory": [_blind_inventory()],
            "physical_proposal": [_proposal()],
            "conditioned_validator_0": [_validator()],
        }
    )
    receipt = deepcopy(_controller(port).run().receipt)
    receipt["result_hashes"]["blind_inventory_sha256"] = receipt["result_hashes"]["proposal_sha256"]

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("blind_inventory_sha256" in error for error in errors)


def test_blocked_receipt_rejects_result_hash_substitution() -> None:
    validator = _validator(verdict="BLOCKED", issue_code="MISSED_OPENING")
    validator["blind_reconciliation"][0]["disposition"] = "UNRESOLVED"
    validator["blind_reconciliation"][0]["proposal_refs"] = []
    result = _controller(
        ScriptedInferencePort(
            {
                "blind_inventory": [_blind_inventory()],
                "physical_proposal": [_proposal()],
                "conditioned_validator_0": [validator],
            }
        )
    ).run()
    assert result.status == VISUAL_PROPOSAL_BLOCKED
    receipt = deepcopy(result.receipt)
    receipt["result_hashes"]["validator_sha256"] = receipt["result_hashes"]["proposal_sha256"]

    errors = validate_phase8_visual_proposal_receipt(receipt)

    assert any("validator_sha256" in error for error in errors)
