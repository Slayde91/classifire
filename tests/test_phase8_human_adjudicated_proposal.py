from __future__ import annotations

import hashlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from test_phase8_visual_proposal import (
    ScriptedInferencePort as _V2ScriptedInferencePort,
)
from test_phase8_visual_proposal import (
    _blind_inventory as _v2_blind_inventory,
)
from test_phase8_visual_proposal import (
    _controller as _v2_controller,
)
from test_phase8_visual_proposal import (
    _manifest as _v2_manifest,
)
from test_phase8_visual_proposal import (
    _proposal as _v2_proposal,
)
from test_phase8_visual_proposal import (
    _validator as _v2_validator,
)

from classifire.services import phase8_human_adjudicated_proposal as human_adjudication
from classifire.services.phase8_human_adjudicated_proposal import (
    ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS,
    HUMAN_ADJUDICATED_PROPOSAL_SCHEMA,
    HUMAN_ADJUDICATED_PROPOSAL_VALIDATION_SCHEMA,
    HUMAN_ADJUDICATED_PROPOSAL_VISUAL_PROVENANCE_VALIDATION_SCHEMA,
    HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2,
    HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA,
    HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2,
    HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS,
    Phase8HumanAdjudicatedProposalError,
    validate_phase8_human_adjudicated_proposal,
    validate_phase8_human_adjudicated_proposal_with_visual_provenance,
)
from classifire.services.phase8_human_review_v2 import build_phase8_human_review_request_v2
from classifire.services.phase8_visual_proposal import (
    LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
    LEGACY_VISUAL_PROPOSAL_RECEIPT_SCHEMA,
    VISUAL_PROPOSAL_BLOCKED,
    canonical_json_sha256,
)
from classifire.services.phase8_visual_provenance import Phase8VisualProvenanceCompleteness

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_phase8_human_adjudicated_proposal as validation_cli  # noqa: E402


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def _source_proposal() -> dict[str, Any]:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": ["Synthetic source is used only to test the local validator."],
        "openings": [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "metal",
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


def _source_receipt(proposal: dict[str, Any]) -> dict[str, Any]:
    protected_counts = {
        "defect_count": 1,
        "evidence_count": 1,
        "opening_count": 0,
        "service_count": 0,
        "service_opening_link_count": 0,
        "active_physical_model_lock_count": 0,
    }

    def stage(sequence: int, name: str, role: str, payload_sha256: str) -> dict[str, Any]:
        return {
            "sequence": sequence,
            "stage": name,
            "role": role,
            "request_sha256": str(sequence) * 64,
            "response_sha256": "A" * 64,
            "payload_sha256": payload_sha256,
            "provider": "synthetic-provider",
            "model": "synthetic-model",
            "session_id_sha256": "C" * 64,
            "transport_receipt_sha256": "D" * 64,
            "protected_state_fingerprint_after": "B" * 64,
            "allowed_tools": [],
        }

    proposal_sha256 = canonical_json_sha256(proposal)
    stages = [
        stage(1, "blind_inventory", "cf-validator", "3" * 64),
        stage(2, "physical_proposal", "cf-physical-model", proposal_sha256),
        stage(3, "conditioned_validator_0", "cf-validator", "4" * 64),
    ]

    return {
        "schema": LEGACY_VISUAL_PROPOSAL_RECEIPT_SCHEMA,
        "policy_version": LEGACY_VISUAL_PROPOSAL_POLICY_VERSION,
        "status": VISUAL_PROPOSAL_BLOCKED,
        "run_id": "RUN-001",
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "evidence_manifest_sha256": "1" * 64,
        "inference_profile_sha256": "2" * 64,
        "implementation_revision": "a" * 40,
        "stages": stages,
        "result_hashes": {
            "blind_inventory_sha256": "3" * 64,
            "proposal_sha256": proposal_sha256,
            "validator_sha256": "4" * 64,
        },
        "protected_state": {
            "before_fingerprint": "B" * 64,
            "after_fingerprint": "B" * 64,
            "before_counts": protected_counts,
            "after_counts": deepcopy(protected_counts),
            "unchanged": True,
        },
        "errors": ["Synthetic blocked receipt for artifact-validator testing."],
        "runtime_inference_performed": True,
        "controller_database_write_performed": False,
        "controller_canonical_write_performed": False,
        "write_or_lock_capability_exposed": False,
        "human_reference_visible_to_inference": False,
    }


def _review() -> dict[str, Any]:
    return {
        "schema": HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA,
        "status": HUMAN_REVIEW_COMPLETE_WITH_LIMITATIONS,
        "package_id": "PACKAGE-001",
        "approval_reference": "HUMAN-001",
        "review_request": {"path": "request.json", "file_sha256": "3" * 64},
        "reviewer": {
            "name": "Synthetic reviewer",
            "reviewed_at": "2026-08-24",
            "review_method": "Synthetic fixture",
            "site_visit_performed": False,
        },
        "defect_decisions": [
            {
                "external_defect_id": "D-001",
                "review_item": "O-001_SERVICE",
                "outcome": "CONFIRMED",
                "decision": "One metal pipe passes through the opening.",
                "evidence_status": "HUMAN_ADJUDICATED_VISUAL_REVIEW",
                "site_verified": False,
            }
        ],
        "remaining_limitations": ["No site visit was performed."],
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "human_reference_visible_to_inference": False,
    }


def _review_request(source_path: Path, receipt_path: Path) -> dict[str, Any]:
    return {
        "schema": "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-REQUEST-v1",
        "status": "HUMAN_EVIDENCE_REVIEW_REQUIRED",
        "package_id": "PACKAGE-001",
        "approval_reference": "HUMAN-001",
        "proposal_file_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest().upper(),
        "controller_receipt_file_sha256": hashlib.sha256(receipt_path.read_bytes())
        .hexdigest()
        .upper(),
        "visual_proposal_status": VISUAL_PROPOSAL_BLOCKED,
        "review_items": [
            {
                "code": "O-001_SERVICE",
                "detail": "Confirm the pipe.",
                "evidence_refs": ["E-001"],
                "source": "validator_issue",
            }
        ],
        "unresolved_blind_observations": [],
        "reviewer_instructions": ["Record a human review decision."],
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }


def _revision(source_path: Path, review_path: Path) -> dict[str, Any]:
    source = source_path.read_bytes()
    review = review_path.read_bytes()
    return {
        "schema": HUMAN_ADJUDICATED_PROPOSAL_SCHEMA,
        "status": ADJUDICATED_PROPOSAL_ONLY_WITH_LIMITATIONS,
        "run_id": "RUN-001-HUMAN-ADJUDICATED",
        "source_run_id": "RUN-001",
        "estimate_id": "EST-001",
        "source_proposal": {
            "path": "source-proposal.json",
            "file_sha256": hashlib.sha256(source).hexdigest().upper(),
            "canonical_json_sha256": canonical_json_sha256(json.loads(source)),
        },
        "human_review_response": {
            "path": "review.json",
            "file_sha256": hashlib.sha256(review).hexdigest().upper(),
        },
        "proposed_topology_counts": {
            "defect_count": 1,
            "opening_count": 1,
            "service_count": 1,
            "service_opening_link_count": 1,
        },
        "openings": [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "opening_type": "service_opening",
                "orientation": "vertical_wall_axis_unknown",
                "substrate_plane": "vertical_wall",
                "substrate_type": "concrete_or_masonry_unknown",
                "evidence_status": "HUMAN_ADJUDICATED_VISUAL_REVIEW",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "metal",
                "quantity": 1,
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "evidence_status": "HUMAN_ADJUDICATED_VISUAL_REVIEW",
                "source_reference": "human-review-response:O-001_SERVICE",
            }
        ],
        "limitations": ["This remains a proposal-only revision."],
        "runtime_inference_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "human_reference_visible_to_inference": False,
    }


def _artifact_paths(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    proposal_path = tmp_path / "source-proposal.json"
    receipt_path = tmp_path / "source-receipt.json"
    request_path = tmp_path / "request.json"
    review_path = tmp_path / "review.json"
    revision_path = tmp_path / "revision.json"
    source = _source_proposal()
    _write_json(proposal_path, source)
    _write_json(receipt_path, _source_receipt(source))
    _write_json(request_path, _review_request(proposal_path, receipt_path))
    review = _review()
    review["review_request"] = {
        "path": "request.json",
        "file_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest().upper(),
    }
    _write_json(review_path, review)
    _write_json(revision_path, _revision(proposal_path, review_path))
    return proposal_path, receipt_path, review_path, revision_path, request_path


def _current_artifact_paths(
    tmp_path: Path,
    *,
    out_of_manifest_assessment: bool = False,
) -> tuple[tuple[Path, Path, Path, Path, Path], Path]:
    visual_result = _v2_controller(
        _V2ScriptedInferencePort(
            {
                "blind_inventory": [_v2_blind_inventory()],
                "physical_proposal": [_v2_proposal()],
                "conditioned_validator_0": [
                    _v2_validator(
                        verdict="BLOCKED",
                        issue_code="WRONG_SERVICE_QUANTITY",
                    )
                ],
            }
        ),
        max_correction_passes=0,
    ).run()
    assert visual_result.status == VISUAL_PROPOSAL_BLOCKED
    assert visual_result.proposal is not None
    source = deepcopy(visual_result.proposal)
    receipt = deepcopy(visual_result.receipt)
    if out_of_manifest_assessment:
        source["services"][0]["property_assessments"]["material"]["evidence_refs"] = [
            "E-OUTSIDE"
        ]
        proposal_hash = canonical_json_sha256(source)
        receipt["result_hashes"]["proposal_sha256"] = proposal_hash
        for stage in receipt["stages"]:
            if stage["stage"] == "physical_proposal":
                stage["payload_sha256"] = proposal_hash

    proposal_path = tmp_path / "source-proposal.json"
    receipt_path = tmp_path / "source-receipt.json"
    manifest_path = tmp_path / "evidence-manifest.json"
    request_path = tmp_path / "request.json"
    review_path = tmp_path / "review.json"
    revision_path = tmp_path / "revision.json"
    _write_json(proposal_path, source)
    _write_json(receipt_path, receipt)
    _write_json(manifest_path, _v2_manifest())
    _write_json(request_path, _review_request(proposal_path, receipt_path))
    review = _review()
    review["review_request"] = {
        "path": "request.json",
        "file_sha256": hashlib.sha256(request_path.read_bytes()).hexdigest().upper(),
    }
    _write_json(review_path, review)
    _write_json(revision_path, _revision(proposal_path, review_path))
    return (
        proposal_path,
        receipt_path,
        review_path,
        revision_path,
        request_path,
    ), manifest_path


def _validate(paths: tuple[Path, Path, Path, Path, Path]) -> dict[str, Any]:
    return validate_phase8_human_adjudicated_proposal(
        source_proposal_path=paths[0],
        source_controller_receipt_path=paths[1],
        human_review_request_path=paths[4],
        human_review_response_path=paths[2],
        revised_proposal_path=paths[3],
    )


def test_validates_hash_bound_proposal_only_human_revision(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)

    result = _validate(paths)

    assert result["schema"] == HUMAN_ADJUDICATED_PROPOSAL_VALIDATION_SCHEMA
    assert result["status"] == "PASS"
    assert result["source_controller_status"] == VISUAL_PROPOSAL_BLOCKED
    assert result["human_review_decision_count"] == 1
    assert result["proposed_topology_counts"] == {
        "defect_count": 1,
        "opening_count": 1,
        "service_count": 1,
        "service_opening_link_count": 1,
    }
    assert (
        result["input_bindings"]["source_proposal"]["sha256"]
        == hashlib.sha256(paths[0].read_bytes()).hexdigest().upper()
    )
    assert (
        result["input_bindings"]["human_review_request"]["sha256"]
        == hashlib.sha256(paths[4].read_bytes()).hexdigest().upper()
    )
    for field_name in (
        "report_or_image_retrieval_performed",
        "runtime_inference_performed",
        "canonical_database_read_performed",
        "canonical_submission_performed",
        "physical_model_lock_created",
        "database_write_performed",
        "gateway_call_performed",
        "human_reference_visible_to_inference",
    ):
        assert result[field_name] is False


def test_current_policy_adjudication_accepts_receipt_bound_manifest(
    tmp_path: Path,
) -> None:
    paths, manifest_path = _current_artifact_paths(tmp_path)

    result = _validate(paths)

    assert result["status"] == "PASS"
    assert (
        result["input_bindings"]["source_evidence_manifest"]["sha256"]
        == hashlib.sha256(manifest_path.read_bytes()).hexdigest().upper()
    )


def test_current_policy_adjudication_rejects_missing_manifest(tmp_path: Path) -> None:
    paths, manifest_path = _current_artifact_paths(tmp_path)
    manifest_path.unlink()

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as rejected:
        _validate(paths)

    assert rejected.value.code == "ARTIFACT_MISSING"


def test_current_policy_adjudication_rejects_tampered_manifest(tmp_path: Path) -> None:
    paths, manifest_path = _current_artifact_paths(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = "F" * 64
    _write_json(manifest_path, manifest)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as rejected:
        _validate(paths)

    assert rejected.value.code == "SOURCE_EVIDENCE_MANIFEST_INVALID"


def test_current_policy_adjudication_rejects_out_of_manifest_assessment(
    tmp_path: Path,
) -> None:
    paths, _manifest_path = _current_artifact_paths(
        tmp_path,
        out_of_manifest_assessment=True,
    )

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as rejected:
        _validate(paths)

    assert rejected.value.code == "SOURCE_PROPOSAL_INVALID"


def test_strict_provenance_mode_binds_current_visual_receipt_and_stays_proposal_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_controller_receipt = {"controller": "synthetic"}
    base_validation = {
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "status": "PASS",
    }
    visual_provenance = Phase8VisualProvenanceCompleteness(
        estimate_id="EST-001",
        defect_reference="D-001",
        linked_visual_run_id="RUN-LINKED-001",
        linked_visual_receipt_status="VISUAL_PROPOSAL_APPROVED",
        evidence_manifest_sha256="A" * 64,
        evidence_family_inventory_sha256="B" * 64,
        controller_receipt_sha256=canonical_json_sha256(source_controller_receipt),
        family_count=1,
        preserved_context_member_count=1,
        errors=(),
    )
    artifacts = {
        "source controller receipt": (source_controller_receipt, "1" * 64),
        "linked visual run receipt": ({"linked": "synthetic"}, "2" * 64),
        "evidence family inventory": ({"inventory": "synthetic"}, "3" * 64),
    }
    monkeypatch.setattr(
        human_adjudication,
        "validate_phase8_human_adjudicated_proposal",
        lambda **_kwargs: base_validation,
    )
    monkeypatch.setattr(
        human_adjudication,
        "_read_json_object",
        lambda _path, *, label: artifacts[label],
    )
    monkeypatch.setattr(
        human_adjudication,
        "assess_phase8_visual_provenance_completeness",
        lambda **_kwargs: visual_provenance,
    )
    paths = {
        name: tmp_path / f"{name.replace(' ', '-')}.json"
        for name in (
            "source-proposal",
            "source-controller",
            "human-request",
            "human-response",
            "revision",
            "linked-receipt",
            "inventory",
        )
    }

    result = validate_phase8_human_adjudicated_proposal_with_visual_provenance(
        source_proposal_path=paths["source-proposal"],
        source_controller_receipt_path=paths["source-controller"],
        human_review_request_path=paths["human-request"],
        human_review_response_path=paths["human-response"],
        revised_proposal_path=paths["revision"],
        linked_visual_run_receipt_path=paths["linked-receipt"],
        evidence_family_inventory_path=paths["inventory"],
    )

    assert result["schema"] == HUMAN_ADJUDICATED_PROPOSAL_VISUAL_PROVENANCE_VALIDATION_SCHEMA
    assert result["status"] == "PASS_PROPOSAL_ONLY_WITH_LIMITATIONS"
    assert result["admission_eligible"] is False
    assert result["proposal_validation"] == base_validation
    assert result["visual_provenance"]["complete"] is True
    assert result["canonical_submission_performed"] is False
    assert result["physical_model_lock_created"] is False

    monkeypatch.setattr(
        human_adjudication,
        "assess_phase8_visual_provenance_completeness",
        lambda **_kwargs: replace(visual_provenance, controller_receipt_sha256="0" * 64),
    )
    with pytest.raises(Phase8HumanAdjudicatedProposalError) as mismatch:
        validate_phase8_human_adjudicated_proposal_with_visual_provenance(
            source_proposal_path=paths["source-proposal"],
            source_controller_receipt_path=paths["source-controller"],
            human_review_request_path=paths["human-request"],
            human_review_response_path=paths["human-response"],
            revised_proposal_path=paths["revision"],
            linked_visual_run_receipt_path=paths["linked-receipt"],
            evidence_family_inventory_path=paths["inventory"],
        )
    assert mismatch.value.code == "CURRENT_VISUAL_CONTROLLER_RECEIPT_HASH_MISMATCH"

    monkeypatch.setattr(
        human_adjudication,
        "assess_phase8_visual_provenance_completeness",
        lambda **_kwargs: replace(
            visual_provenance,
            errors=("CURRENT_VISUAL_RUN_SCOPE_MISMATCH",),
        ),
    )
    with pytest.raises(Phase8HumanAdjudicatedProposalError) as incomplete:
        validate_phase8_human_adjudicated_proposal_with_visual_provenance(
            source_proposal_path=paths["source-proposal"],
            source_controller_receipt_path=paths["source-controller"],
            human_review_request_path=paths["human-request"],
            human_review_response_path=paths["human-response"],
            revised_proposal_path=paths["revision"],
            linked_visual_run_receipt_path=paths["linked-receipt"],
            evidence_family_inventory_path=paths["inventory"],
        )
    assert incomplete.value.code == "CURRENT_VISUAL_PROVENANCE_INCOMPLETE"


def test_rejects_review_that_claims_a_database_write(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    review = json.loads(paths[2].read_text(encoding="utf-8"))
    review["database_write_performed"] = True
    _write_json(paths[2], review)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "HUMAN_REVIEW_NOOP_VIOLATION"


def test_rejects_request_with_changed_bytes(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    request = json.loads(paths[4].read_text(encoding="utf-8"))
    request["reviewer_instructions"].append("Changed after human review.")
    _write_json(paths[4], request)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "HUMAN_REVIEW_REQUEST_HASH_MISMATCH"


def test_rejects_review_request_with_wrong_source_hash(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    request = json.loads(paths[4].read_text(encoding="utf-8"))
    request["proposal_file_sha256"] = "0" * 64
    _write_json(paths[4], request)
    review = json.loads(paths[2].read_text(encoding="utf-8"))
    review["review_request"]["file_sha256"] = (
        hashlib.sha256(paths[4].read_bytes()).hexdigest().upper()
    )
    _write_json(paths[2], review)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "HUMAN_REVIEW_REQUEST_SOURCE_HASH_MISMATCH"


def test_rejects_service_without_a_confirmed_review_item(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    revision = json.loads(paths[3].read_text(encoding="utf-8"))
    revision["services"][0]["source_reference"] = "human-review-response:UNREVIEWED"
    _write_json(paths[3], revision)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "SERVICE_REVIEW_ITEM_INVALID"


def test_rejects_declared_topology_count_mismatch(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    revision = json.loads(paths[3].read_text(encoding="utf-8"))
    revision["proposed_topology_counts"]["opening_count"] = 2
    _write_json(paths[3], revision)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "TOPOLOGY_COUNT_MISMATCH"


def test_cli_prints_validation_without_writing_an_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _artifact_paths(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_phase8_human_adjudicated_proposal.py",
            "--source-proposal",
            str(paths[0]),
            "--source-controller-receipt",
            str(paths[1]),
            "--human-review-response",
            str(paths[2]),
            "--revised-proposal",
            str(paths[3]),
            "--human-review-request",
            str(paths[4]),
        ],
    )

    assert validation_cli.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"


def test_cli_uses_strict_visual_provenance_mode_only_with_both_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    captured: dict[str, Path] = {}

    def strict_validator(**kwargs: Path) -> dict[str, object]:
        captured.update(kwargs)
        return {"status": "PASS_PROPOSAL_ONLY_WITH_LIMITATIONS", "admission_eligible": False}

    monkeypatch.setattr(
        validation_cli,
        "validate_phase8_human_adjudicated_proposal_with_visual_provenance",
        strict_validator,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_phase8_human_adjudicated_proposal.py",
            "--source-proposal",
            "source-proposal.json",
            "--source-controller-receipt",
            "source-controller.json",
            "--human-review-response",
            "review.json",
            "--revised-proposal",
            "revision.json",
            "--human-review-request",
            "request.json",
            "--linked-visual-run-receipt",
            "linked-run.json",
            "--evidence-family-inventory",
            "family-inventory.json",
        ],
    )

    assert validation_cli.main() == 0
    assert captured["linked_visual_run_receipt_path"] == Path("linked-run.json")
    assert captured["evidence_family_inventory_path"] == Path("family-inventory.json")
    assert json.loads(capsys.readouterr().out) == {
        "status": "PASS_PROPOSAL_ONLY_WITH_LIMITATIONS",
        "admission_eligible": False,
    }


def _artifact_paths_v2(
    tmp_path: Path,
    *,
    additional_request_item: bool = False,
) -> tuple[Path, Path, Path, Path, Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = _artifact_paths(tmp_path)
    request = json.loads(paths[4].read_text(encoding="utf-8"))
    request["schema"] = HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2
    request["review_items"] = [
        {
            "review_item_id": "REQUEST-001",
            "code": "O-001_SERVICE",
            "detail": "Confirm the pipe.",
            "evidence_refs": ["E-001"],
            "source": "validator_issue",
        }
    ]
    if additional_request_item:
        request["review_items"].append(
            {
                "review_item_id": "REQUEST-002",
                "code": "O-001_MATERIAL",
                "detail": "Confirm the visible material.",
                "evidence_refs": ["E-001"],
                "source": "validator_issue",
            }
        )
    _write_json(paths[4], request)

    review = json.loads(paths[2].read_text(encoding="utf-8"))
    review["schema"] = HUMAN_EVIDENCE_REVIEW_RESPONSE_SCHEMA_V2
    review["review_request"] = {
        "path": "request.json",
        "file_sha256": hashlib.sha256(paths[4].read_bytes()).hexdigest().upper(),
    }
    review["defect_decisions"][0]["request_item_ids"] = ["REQUEST-001"]
    _write_json(paths[2], review)
    _write_json(paths[3], _revision(paths[0], paths[2]))
    return paths


def test_validates_complete_v2_request_item_coverage(tmp_path: Path) -> None:
    result = _validate(_artifact_paths_v2(tmp_path))

    assert result["status"] == "PASS"


def test_v2_rejects_unknown_or_repeated_request_item_ids(tmp_path: Path) -> None:
    paths = _artifact_paths_v2(tmp_path)
    review = json.loads(paths[2].read_text(encoding="utf-8"))
    review["defect_decisions"][0]["request_item_ids"] = ["REQUEST-UNKNOWN"]
    _write_json(paths[2], review)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as unknown:
        _validate(paths)

    assert unknown.value.code == "HUMAN_REVIEW_REQUEST_ITEM_UNKNOWN"

    paths = _artifact_paths_v2(tmp_path / "repeated")
    review = json.loads(paths[2].read_text(encoding="utf-8"))
    repeated = deepcopy(review["defect_decisions"][0])
    repeated["review_item"] = "O-001_SERVICE_REPEAT"
    repeated["outcome"] = "UNRESOLVED"
    review["defect_decisions"].append(repeated)
    _write_json(paths[2], review)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as repeated_item:
        _validate(paths)

    assert repeated_item.value.code == "HUMAN_REVIEW_REQUEST_ITEM_DUPLICATE"


def test_v2_rejects_request_items_without_a_human_decision(tmp_path: Path) -> None:
    paths = _artifact_paths_v2(tmp_path, additional_request_item=True)

    with pytest.raises(Phase8HumanAdjudicatedProposalError) as caught:
        _validate(paths)

    assert caught.value.code == "HUMAN_REVIEW_REQUEST_ITEMS_UNACCOUNTED_FOR"


def test_builds_deterministic_v2_request_draft_without_mutating_v1(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    request_v1 = json.loads(paths[4].read_text(encoding="utf-8"))
    first = build_phase8_human_review_request_v2(request_v1)
    second = build_phase8_human_review_request_v2(request_v1)

    assert first == second
    assert request_v1["schema"] != HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2
    assert first["schema"] == HUMAN_EVIDENCE_REVIEW_REQUEST_SCHEMA_V2
    assert first["review_items"][0]["review_item_id"].startswith("REVIEW-")
    assert "review_item_id" not in request_v1["review_items"][0]
