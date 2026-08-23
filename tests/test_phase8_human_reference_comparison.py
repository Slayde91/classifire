from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from classifire.services.canonical_submission_state import InitialSubmissionState
from classifire.services.phase8_human_reference_comparison import (
    HUMAN_COMPARISON_SCHEMA,
    HUMAN_REFERENCE_PURPOSE,
    HUMAN_REFERENCE_SCHEMA,
    Phase8HumanReferenceComparisonError,
    compare_phase8_human_reference,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_EVIDENCE_MANIFEST_SCHEMA,
    VISUAL_INFERENCE_PROFILE_SCHEMA,
    VISUAL_INFERENCE_RESPONSE_SCHEMA,
    VISUAL_PROPOSAL_APPROVED,
    ProposalOnlyVisualController,
    canonical_json_sha256,
)
from classifire.services.physical_scope import is_blank_opening_type

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import compare_phase8_human_reference as comparison_cli  # noqa: E402


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
                    "source_reference": "synthetic.pdf#page=1-image=1",
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
        "blind_prompt_sha256": "2" * 64,
        "physical_prompt_sha256": "3" * 64,
        "validator_prompt_sha256": "4" * 64,
        "correction_prompt_sha256": "5" * 64,
        "runtime_policy_sha256": "6" * 64,
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


def _proposal(
    *,
    openings: list[dict[str, Any]] | None = None,
    services: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
        "openings": openings
        or [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            }
        ],
        "services": services
        or [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
                "source_reference": "E-001",
                "confidence": "0.95",
            }
        ],
    }


def _blind_inventory(proposal: dict[str, Any]) -> dict[str, Any]:
    openings = proposal["openings"]
    services = proposal["services"]
    return {
        "status": "COMPLETE",
        "observed_opening_count": len(openings),
        "observed_service_group_count": len(services),
        "candidate_openings": [
            {
                "candidate_id": f"V-{opening['opening_code']}",
                "blank": is_blank_opening_type(opening["opening_type"]),
                "detail": "synthetic opening observation",
                "evidence_refs": ["E-001"],
            }
            for opening in openings
        ],
        "candidate_services": [
            {
                "candidate_id": f"V-{service['service_code']}",
                "service_type": service["service_type"],
                "material": service.get("material"),
                "quantity": service["quantity"],
                "candidate_opening_ids": [
                    f"V-{opening_code}" for opening_code in service["opening_codes"]
                ],
                "detail": "synthetic service observation",
                "evidence_refs": ["E-001"],
            }
            for service in services
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _validator(
    proposal: dict[str, Any],
    blind_inventory: dict[str, Any],
) -> dict[str, Any]:
    reconciliation = [
        {
            "blind_candidate_id": candidate["candidate_id"],
            "disposition": "ACCOUNTED_FOR",
            "proposal_refs": [candidate["candidate_id"].removeprefix("V-")],
            "detail": "synthetic candidate accounted for",
            "evidence_refs": ["E-001"],
        }
        for candidate in [
            *blind_inventory["candidate_openings"],
            *blind_inventory["candidate_services"],
        ]
    ]
    return {
        "verdict": "APPROVED",
        "issues": [],
        "limitations": [],
        "observed_opening_count": len(proposal["openings"]),
        "observed_service_group_count": len(proposal["services"]),
        "blind_reconciliation": reconciliation,
    }


class _ScriptedPort:
    def __init__(self, proposal: dict[str, Any]) -> None:
        blind_inventory = _blind_inventory(proposal)
        self.responses = {
            "blind_inventory": blind_inventory,
            "physical_proposal": proposal,
            "conditioned_validator_0": _validator(proposal, blind_inventory),
        }
        self.calls: list[dict[str, Any]] = []

    def invoke(
        self,
        *,
        role: str,
        stage: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"role": role, "stage": stage, "request": deepcopy(request)})
        return {
            "schema": VISUAL_INFERENCE_RESPONSE_SCHEMA,
            "agent_id": role,
            "provider": "test-provider",
            "model": "validator-test-model" if role == "cf-validator" else "physical-test-model",
            "session_id_sha256": "7" * 64,
            "transport_receipt_sha256": "8" * 64,
            "tool_calls": [],
            "payload": deepcopy(self.responses[stage]),
        }


def _completed_controller(
    proposal: dict[str, Any],
) -> tuple[dict[str, Any], _ScriptedPort]:
    port = _ScriptedPort(proposal)
    result = ProposalOnlyVisualController(
        run_id="RUN-001",
        estimate_id="EST-001",
        evidence_manifest=_manifest(),
        inference_profile=_profile(),
        inference_port=port,
        protected_state_reader=_state,
    ).run()
    assert result.status == VISUAL_PROPOSAL_APPROVED
    assert result.proposal == proposal
    return result.receipt, port


def _reference(openings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": HUMAN_REFERENCE_SCHEMA,
        "run_id": "REFERENCE-RUN-001",
        "purpose": HUMAN_REFERENCE_PURPOSE,
        "defects": [
            {
                "external_defect_id": "D-001",
                "opening_count": len(openings),
                "openings": openings,
            }
        ],
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _artifact_paths(
    tmp_path: Path,
    proposal: dict[str, Any],
    receipt: dict[str, Any],
    reference: dict[str, Any],
) -> tuple[Path, Path, Path]:
    proposal_path = tmp_path / "proposal.json"
    receipt_path = tmp_path / "controller-receipt.json"
    reference_path = tmp_path / "human-reference.json"
    _write_json(proposal_path, proposal)
    _write_json(receipt_path, receipt)
    _write_json(reference_path, reference)
    return proposal_path, receipt_path, reference_path


def test_comparison_runs_after_inference_and_binds_all_input_bytes(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    receipt, port = _completed_controller(proposal)
    reference = _reference(
        [
            {
                "substrate": "concrete wall",
                "blank": False,
                "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
            }
        ]
    )
    proposal_path, receipt_path, reference_path = _artifact_paths(
        tmp_path,
        proposal,
        receipt,
        reference,
    )

    result = compare_phase8_human_reference(
        proposal_path=proposal_path,
        controller_receipt_path=receipt_path,
        reference_path=reference_path,
    )

    assert result["schema"] == HUMAN_COMPARISON_SCHEMA
    assert result["status"] == "PASS"
    assert result["passed_defect_count"] == 1
    assert result["mismatch_defect_count"] == 0
    assert result["human_reference_visible_to_inference"] is False
    assert result["canonical_database_read_performed"] is False
    assert result["canonical_write_performed"] is False
    assert result["physical_model_lock_created"] is False
    assert result["input_bindings"]["proposal"] == {
        "path": str(proposal_path.resolve()),
        "sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest().upper(),
        "canonical_json_sha256": canonical_json_sha256(proposal),
    }
    assert (
        result["input_bindings"]["controller_receipt"]["proposal_canonical_json_binding"]
        == "VERIFIED"
    )
    assert (
        result["input_bindings"]["human_reference"]["sha256"]
        == hashlib.sha256(reference_path.read_bytes()).hexdigest().upper()
    )
    assert all(call["request"]["human_reference_visible"] is False for call in port.calls)
    assert all(
        call["request"]["evidence_manifest"]["human_reference_included"] is False
        for call in port.calls
    )


def test_comparison_detects_substrate_swap_within_service_topology(
    tmp_path: Path,
) -> None:
    proposal = _proposal(
        openings=[
            {
                "external_defect_id": "D-001",
                "opening_code": "O-PIPE",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            },
            {
                "external_defect_id": "D-001",
                "opening_code": "O-CABLE",
                "substrate_type": "concrete",
                "substrate_plane": "slab",
                "orientation": "horizontal",
                "opening_type": "service_penetration",
            },
        ],
        services=[
            {
                "service_code": "S-PIPE",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "primary_opening_code": "O-PIPE",
                "opening_codes": ["O-PIPE"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
                "source_reference": "E-001",
                "confidence": "0.95",
            },
            {
                "service_code": "S-CABLE",
                "service_type": "cable_bundle",
                "material": None,
                "quantity": 1,
                "primary_opening_code": "O-CABLE",
                "opening_codes": ["O-CABLE"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
                "source_reference": "E-001",
                "confidence": "0.95",
            },
        ],
    )
    receipt, _ = _completed_controller(proposal)
    reference = _reference(
        [
            {
                "substrate": "concrete slab",
                "blank": False,
                "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
            },
            {
                "substrate": "concrete wall",
                "blank": False,
                "service_groups": [{"type": "cable_bundle", "material": None, "quantity": 1}],
            },
        ]
    )
    paths = _artifact_paths(tmp_path, proposal, receipt, reference)

    result = compare_phase8_human_reference(
        proposal_path=paths[0],
        controller_receipt_path=paths[1],
        reference_path=paths[2],
    )

    assert result["status"] == "MISMATCH"
    assert result["defects"][0]["actual_opening_count"] == 2
    substrate_issues = [
        issue
        for issue in result["defects"][0]["issues"]
        if "within matching service topology" in issue
    ]
    assert len(substrate_issues) == 2
    assert not any("topology differs" in issue for issue in result["defects"][0]["issues"])


def test_comparison_maps_one_service_group_to_each_linked_opening(
    tmp_path: Path,
) -> None:
    proposal = _proposal(
        openings=[
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            },
            {
                "external_defect_id": "D-001",
                "opening_code": "O-002",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            },
        ],
        services=[
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": 1,
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001", "O-002"],
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "passes_through",
                "source_reference": "E-001",
                "confidence": "0.95",
            }
        ],
    )
    receipt, _ = _completed_controller(proposal)
    expected_opening = {
        "substrate": "concrete wall",
        "blank": False,
        "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
    }
    paths = _artifact_paths(
        tmp_path,
        proposal,
        receipt,
        _reference([expected_opening, expected_opening]),
    )

    result = compare_phase8_human_reference(
        proposal_path=paths[0],
        controller_receipt_path=paths[1],
        reference_path=paths[2],
    )

    assert result["status"] == "PASS"
    assert result["defects"][0]["actual_opening_count"] == 2


def test_comparison_rejects_proposal_bytes_not_bound_to_controller_receipt(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    receipt, _ = _completed_controller(proposal)
    tampered = deepcopy(proposal)
    tampered["services"][0]["material"] = "copper"
    paths = _artifact_paths(
        tmp_path,
        tampered,
        receipt,
        _reference(
            [
                {
                    "substrate": None,
                    "blank": False,
                    "service_groups": [{"type": "pipe", "material": "copper", "quantity": 1}],
                }
            ]
        ),
    )

    with pytest.raises(Phase8HumanReferenceComparisonError) as caught:
        compare_phase8_human_reference(
            proposal_path=paths[0],
            controller_receipt_path=paths[1],
            reference_path=paths[2],
        )

    assert caught.value.code == "PROPOSAL_RECEIPT_HASH_MISMATCH"


def test_comparison_rejects_receipt_that_exposed_human_reference(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    receipt, _ = _completed_controller(proposal)
    receipt["human_reference_visible_to_inference"] = True
    paths = _artifact_paths(
        tmp_path,
        proposal,
        receipt,
        _reference(
            [
                {
                    "substrate": None,
                    "blank": False,
                    "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
                }
            ]
        ),
    )

    with pytest.raises(Phase8HumanReferenceComparisonError) as caught:
        compare_phase8_human_reference(
            proposal_path=paths[0],
            controller_receipt_path=paths[1],
            reference_path=paths[2],
        )

    assert caught.value.code == "CONTROLLER_RECEIPT_INVALID"


def test_comparison_fails_closed_for_non_validation_reference_purpose(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    receipt, _ = _completed_controller(proposal)
    reference = _reference(
        [
            {
                "substrate": None,
                "blank": False,
                "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
            }
        ]
    )
    reference["purpose"] = "Use this during inference."
    paths = _artifact_paths(tmp_path, proposal, receipt, reference)

    with pytest.raises(Phase8HumanReferenceComparisonError) as caught:
        compare_phase8_human_reference(
            proposal_path=paths[0],
            controller_receipt_path=paths[1],
            reference_path=paths[2],
        )

    assert caught.value.code == "HUMAN_REFERENCE_PURPOSE_INVALID"


def test_comparison_reports_missing_reference_defect_as_mismatch(
    tmp_path: Path,
) -> None:
    proposal = _proposal()
    receipt, _ = _completed_controller(proposal)
    reference = {
        "schema": HUMAN_REFERENCE_SCHEMA,
        "run_id": "REFERENCE-RUN-001",
        "purpose": HUMAN_REFERENCE_PURPOSE,
        "defects": [],
    }
    paths = _artifact_paths(tmp_path, proposal, receipt, reference)

    result = compare_phase8_human_reference(
        proposal_path=paths[0],
        controller_receipt_path=paths[1],
        reference_path=paths[2],
    )

    assert result["status"] == "MISMATCH"
    assert result["defects"][0]["expected_opening_count"] is None
    assert result["defects"][0]["issues"] == [
        "controller defect_reference is absent from the human reference"
    ]


def test_cli_writes_mismatch_receipt_and_returns_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    proposal = _proposal()
    receipt, _ = _completed_controller(proposal)
    paths = _artifact_paths(
        tmp_path,
        proposal,
        receipt,
        _reference(
            [
                {
                    "substrate": "concrete slab",
                    "blank": False,
                    "service_groups": [{"type": "pipe", "material": "PVC", "quantity": 1}],
                }
            ]
        ),
    )
    output_path = tmp_path / "comparison.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "compare_phase8_human_reference.py",
            "--proposal",
            str(paths[0]),
            "--controller-receipt",
            str(paths[1]),
            "--reference",
            str(paths[2]),
            "--output",
            str(output_path),
        ],
    )

    exit_code = comparison_cli.main()
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert saved == printed
    assert saved["status"] == "MISMATCH"
    assert saved["canonical_write_performed"] is False
