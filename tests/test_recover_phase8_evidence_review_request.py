from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from classifire.services.phase8_openresponses_transport import (
    OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA,
    build_phase8_openresponses_transport_receipt_bundle,
)
from classifire.services.phase8_representative_run import (
    LEGACY_REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
    REPRESENTATIVE_RUN_APPROVAL_SCOPE,
    REPRESENTATIVE_RUN_PACKAGE_SCHEMA,
    REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_PROPOSAL_BLOCKED,
    VISUAL_PROPOSAL_POLICY_VERSION,
    VISUAL_PROPOSAL_RECEIPT_SCHEMA,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import recover_phase8_evidence_review_request as recovery_cli  # noqa: E402

_STORED_FILE_ID = "00000000-0000-4000-8000-000000000001"
_SCAN_ATTESTATION_ID = "00000000-0000-4000-8000-000000000002"
_OTHER_SCAN_ATTESTATION_ID = "00000000-0000-4000-8000-000000000003"


def _render(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _write_json(path: Path, value: object) -> bytes:
    raw = _render(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _blind_inventory() -> dict[str, Any]:
    return {
        "status": "COMPLETE",
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "candidate_openings": [
            {
                "candidate_id": "V-O-001",
                "blank": False,
                "detail": "Possible opening relationship in the wide view.",
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
                "detail": "One visible pipe group.",
                "evidence_refs": ["E-001"],
            }
        ],
        "unresolved_candidates": [],
        "limitations": [],
    }


def _proposal() -> dict[str, Any]:
    return {
        "status": "MODEL_SUPPORTED",
        "limitations": [],
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


def _blocked_validator() -> dict[str, Any]:
    return {
        "verdict": "BLOCKED",
        "issues": [
            {
                "code": "MISSED_OPENING",
                "detail": "Confirm whether the supplied views show the same opening.",
                "evidence_refs": ["E-001"],
            }
        ],
        "limitations": ["HTTPS://example.invalid/signed"],
        "observed_opening_count": 1,
        "observed_service_group_count": 1,
        "blind_reconciliation": [
            {
                "blind_candidate_id": "V-O-001",
                "disposition": "UNRESOLVED",
                "proposal_refs": [],
                "detail": "The opening relationship remains unresolved.",
                "evidence_refs": ["E-001"],
            },
            {
                "blind_candidate_id": "V-S-001",
                "disposition": "ACCOUNTED_FOR",
                "proposal_refs": ["S-001"],
                "detail": "The visible service is represented.",
                "evidence_refs": ["E-001"],
            },
        ],
    }


def _stage(
    *,
    sequence: int,
    name: str,
    role: str,
    payload: dict[str, Any],
    run_id: str,
    agent_id: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    request_sha256 = f"{sequence:X}" * 64
    identity = canonical_json_sha256(
        {
            "run_id": run_id,
            "stage": name,
            "request_sha256": request_sha256,
        }
    )
    session_key = f"agent:{agent_id}:classifire-phase8-{identity[:32].lower()}"
    session_id_sha256 = hashlib.sha256(session_key.encode("utf-8")).hexdigest().upper()
    payload_sha256 = canonical_json_sha256(payload)
    transport_receipt = {
        "schema": OPENRESPONSES_TRANSPORT_RECEIPT_SCHEMA,
        "request_sha256": request_sha256,
        "prompt_template_sha256": "7" * 64,
        "session_id_sha256": session_id_sha256,
        "attestation_receipt_sha256": "8" * 64,
        "audit_receipt_sha256": "9" * 64,
        "evidence": [
            {
                "evidence_id": "E-001",
                "stored_file_id": _STORED_FILE_ID,
                "malware_scan_attestation_id": _SCAN_ATTESTATION_ID,
                "malware_scan_attestation_receipt_sha256": "D" * 64,
                "malware_scan_sequence": 1,
                "sha256": "E" * 64,
                "size_bytes": 123,
                "media_type": "image/jpeg",
            }
        ],
        "openresponses_response_id_sha256": "6" * 64,
        "payload_sha256": payload_sha256,
    }
    stage = {
            "sequence": sequence,
            "stage": name,
            "role": role,
            "request_sha256": request_sha256,
            "response_sha256": "A" * 64,
            "payload_sha256": payload_sha256,
            "provider": "test-provider",
            "model": "test-model",
            "session_id_sha256": session_id_sha256,
            "transport_receipt_sha256": canonical_json_sha256(transport_receipt),
            "protected_state_fingerprint_after": "C" * 64,
            "allowed_tools": [],
    }
    return stage, session_key, {"stage": name, "role": role, "receipt": transport_receipt}


def _write_transcript(
    sessions_root: Path,
    *,
    session_id: str,
    payload: dict[str, Any],
) -> Path:
    transcript = sessions_root / f"{session_id}.jsonl"
    records = [
        {"type": "session", "id": session_id},
        {
            "type": "message",
            "message": {
                "role": "user",
                "content": [
                    {"type": "text", "text": "PROMPT_SENTINEL"},
                    {"type": "image", "data": "BASE64_IMAGE_SENTINEL"},
                ],
            },
        },
        {
            "type": "message",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "thinking", "thinking": "THINKING_SENTINEL"},
                    {
                        "type": "text",
                        "text": json.dumps(
                            payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                ],
            },
        },
    ]
    transcript.write_bytes(
        b"".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            for record in records
        )
    )
    return transcript


def _fixture(tmp_path: Path, *, transport_bound: bool = False) -> dict[str, Path]:
    run_id = "run-001"
    package_id = "package-001"
    approval_reference = "approval-001"
    blind = _blind_inventory()
    proposal = _proposal()
    malformed_validator = {"verdict": "BLOCKED"}
    validator = _blocked_validator()
    stage_specs = [
        (
            "blind_inventory",
            "cf-validator",
            "cf-phase8-visual-validator",
            blind,
        ),
        (
            "physical_proposal",
            "cf-physical-model",
            "cf-phase8-visual-physical",
            proposal,
        ),
        (
            "conditioned_validator_0",
            "cf-validator",
            "cf-phase8-visual-validator",
            malformed_validator,
        ),
        (
            "conditioned_validator_retry_0",
            "cf-validator",
            "cf-phase8-visual-validator",
            validator,
        ),
    ]
    stages: list[dict[str, Any]] = []
    transport_receipt_records: list[dict[str, Any]] = []
    session_entries: dict[str, dict[str, dict[str, str]]] = {
        "cf-phase8-visual-physical": {},
        "cf-phase8-visual-validator": {},
    }
    paths: dict[str, Path] = {}
    openclaw_root = tmp_path / "openclaw"
    for sequence, (name, role, agent_id, payload) in enumerate(stage_specs, start=1):
        stage, session_key, transport_record = _stage(
            sequence=sequence,
            name=name,
            role=role,
            payload=payload,
            run_id=run_id,
            agent_id=agent_id,
        )
        stages.append(stage)
        transport_receipt_records.append(transport_record)
        sessions_root = openclaw_root / "agents" / agent_id / "sessions"
        sessions_root.mkdir(parents=True, exist_ok=True)
        session_id = f"session-{sequence}"
        session_entries[agent_id][session_key] = {"sessionId": session_id}
        paths[f"transcript_{sequence}"] = _write_transcript(
            sessions_root,
            session_id=session_id,
            payload=payload,
        )
    for agent_id, entries in session_entries.items():
        _write_json(
            openclaw_root / "agents" / agent_id / "sessions" / "sessions.json",
            entries,
        )

    protected_summary = {"fingerprint": "D" * 64, "counts": {}}
    controller = {
        "schema": VISUAL_PROPOSAL_RECEIPT_SCHEMA,
        "policy_version": VISUAL_PROPOSAL_POLICY_VERSION,
        "status": VISUAL_PROPOSAL_BLOCKED,
        "run_id": run_id,
        "estimate_id": "EST-001",
        "defect_reference": "D-001",
        "evidence_manifest_sha256": "E" * 64,
        "inference_profile_sha256": "F" * 64,
        "implementation_revision": "a" * 40,
        "stages": stages,
        "result_hashes": {
            "blind_inventory_sha256": canonical_json_sha256(blind),
            "proposal_sha256": canonical_json_sha256(proposal),
            "validator_sha256": canonical_json_sha256(validator),
        },
        "protected_state": {
            "before_fingerprint": "C" * 64,
            "after_fingerprint": "C" * 64,
            "before_counts": {},
            "after_counts": {},
            "unchanged": True,
        },
        "errors": ["Validator blocked the proposal: review required"],
        "runtime_inference_performed": True,
        "controller_database_write_performed": False,
        "controller_canonical_write_performed": False,
        "write_or_lock_capability_exposed": False,
        "human_reference_visible_to_inference": False,
    }
    assert validate_phase8_visual_proposal_receipt(controller) == []
    transport_bundle = (
        build_phase8_openresponses_transport_receipt_bundle(
            transport_receipt_records,
            controller_receipt=controller,
        )
        if transport_bound
        else None
    )

    package = {
        "schema": REPRESENTATIVE_RUN_PACKAGE_SCHEMA,
        "package_id": package_id,
        "approval": {
            "reference": approval_reference,
            "authorised_by": "test-user",
            "authorised_at_utc": "2026-08-23T00:00:00Z",
            "scope": REPRESENTATIVE_RUN_APPROVAL_SCOPE,
            "report_sha256": "1" * 64,
            "retrieval_hosts": ["twiddle.onuptick.com"],
        },
        "execution": {
            "expected_git_revision": "a" * 40,
            "source_tree_sha256": "2" * 64,
            "estimate_id": "EST-001",
            "defect_reference": "D-001",
            "operator_reference": "test-operator",
            "rollback_only": True,
            "canonical_submission_allowed": False,
            "physical_model_lock_allowed": False,
            "human_reference_visible_to_inference": False,
        },
        "inputs": {},
        "runtime": {
            "gateway_command": ["unused"],
            "gateway_base_url": "http://127.0.0.1:18789",
            "provider": "test-provider",
            "physical_model": "test-model",
            "validator_model": "test-model",
            "physical_agent_id": "cf-phase8-visual-physical",
            "validator_agent_id": "cf-phase8-visual-validator",
        },
    }
    package_path = tmp_path / "package.json"
    package_raw = _write_json(package_path, package)
    controller_path = tmp_path / "proposal-controller-receipt.json"
    controller_raw = _write_json(controller_path, controller)
    proposal_path = tmp_path / "proposal.json"
    proposal_raw = _write_json(proposal_path, proposal)
    representative: dict[str, Any] = {
        "schema": (
            REPRESENTATIVE_RUN_RECEIPT_SCHEMA
            if transport_bundle is not None
            else LEGACY_REPRESENTATIVE_RUN_RECEIPT_SCHEMA
        ),
        "package_id": package_id,
        "package_sha256": _sha256_bytes(package_raw),
        "approval_reference": approval_reference,
        "authorised_by": "test-user",
        "authorised_at_utc": "2026-08-23T00:00:00Z",
        "source_revision": "a" * 40,
        "source_tree_sha256": "2" * 64,
        "report_sha256": "1" * 64,
        "retrieval_hosts": ["twiddle.onuptick.com"],
        "preflight_receipt_sha256": "3" * 64,
        "runner_receipt_sha256": "4" * 64,
        "controller_receipt_sha256": canonical_json_sha256(controller),
        "protected_state": {
            "before": protected_summary,
            "after_rollback": protected_summary,
            "unchanged_after_rollback": True,
        },
        "rollback_only": True,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    if transport_bundle is not None:
        representative["transport_receipt_bundle_sha256"] = canonical_json_sha256(
            transport_bundle
        )
    representative_path = tmp_path / "representative-run-receipt.json"
    representative_raw = _write_json(representative_path, representative)
    completion = {
        **representative,
        "artifacts": {
            "representative_run_receipt_sha256": _sha256_bytes(representative_raw),
            "controller_receipt_sha256": _sha256_bytes(controller_raw),
            "proposal_sha256": _sha256_bytes(proposal_raw),
        },
        "human_reference_comparison_status": f"SKIPPED_{VISUAL_PROPOSAL_BLOCKED}",
    }
    if transport_bundle is not None:
        transport_path = tmp_path / "openresponses-transport-receipts.json"
        transport_raw = _write_json(transport_path, transport_bundle)
        completion["artifacts"]["openresponses_transport_receipts_sha256"] = (
            _sha256_bytes(transport_raw)
        )
        paths["transport_receipts"] = transport_path
    completion_path = tmp_path / "completion-receipt.json"
    _write_json(completion_path, completion)
    return {
        "package": package_path,
        "completion": completion_path,
        "representative": representative_path,
        "controller": controller_path,
        "proposal": proposal_path,
        "openclaw_root": openclaw_root,
        **paths,
    }


def _recover(paths: dict[str, Path]) -> recovery_cli.RecoveredEvidenceReview:
    return recovery_cli.recover_phase8_evidence_review(
        package_path=paths["package"],
        completion_path=paths["completion"],
        representative_receipt_path=paths["representative"],
        controller_path=paths["controller"],
        proposal_path=paths["proposal"],
        transport_receipts_path=paths.get("transport_receipts"),
        openclaw_root=paths["openclaw_root"],
        repository_root=REPOSITORY_ROOT,
        recovery_script_path=SCRIPTS / "recover_phase8_evidence_review_request.py",
    )


def test_hash_bound_all_stage_recovery_writes_only_safe_review_files(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)

    recovered = _recover(paths)

    assert recovered.receipt["status"] == "RECOVERED_HASH_VERIFIED_LOCAL_TRANSCRIPTS"
    assert recovered.receipt["schema"] == recovery_cli.RECOVERY_RECEIPT_SCHEMA
    assert recovered.receipt["transport_security_binding"] == {
        "status": "LEGACY_TRANSPORT_BINDING_UNAVAILABLE",
        "receipt_count": None,
        "bundle_actual_file_sha256": None,
        "bundle_canonical_json_sha256": None,
    }
    assert len(recovered.receipt["stages"]) == 4
    assert recovered.request["unresolved_blind_observations"][0]["blind_candidate_id"] == "V-O-001"
    output = tmp_path / "recovered"
    receipt_file_sha256 = recovery_cli._write_recovered_output(output, recovered)
    assert receipt_file_sha256 == _sha256_bytes((output / "recovery-receipt.json").read_bytes())
    assert sorted(path.name for path in output.iterdir()) == [
        "evidence-review-request.json",
        "recovery-receipt.json",
    ]
    rendered = b"".join(path.read_bytes() for path in output.iterdir()).decode("utf-8")
    for forbidden in (
        "PROMPT_SENTINEL",
        "BASE64_IMAGE_SENTINEL",
        "THINKING_SENTINEL",
        "https://",
    ):
        assert forbidden.casefold() not in rendered.casefold()
    assert recovered.receipt["source_report_or_linked_original_file_read_performed"] is False
    assert recovered.receipt["inference_request_performed"] is False
    assert recovered.receipt["canonical_submission_performed"] is False
    assert recovered.receipt["physical_model_lock_created"] is False


def test_recovery_verifies_advertised_transport_receipt_sidecar(tmp_path: Path) -> None:
    paths = _fixture(tmp_path, transport_bound=True)

    recovered = _recover(paths)

    binding = recovered.receipt["transport_security_binding"]
    assert binding["status"] == "VERIFIED_LOCAL_TRANSPORT_PREIMAGE_BINDING"
    assert binding["receipt_count"] == 4
    assert binding["bundle_actual_file_sha256"] == _sha256_bytes(
        paths["transport_receipts"].read_bytes()
    )
    assert _SCAN_ATTESTATION_ID not in json.dumps(recovered.receipt)
    assert _SCAN_ATTESTATION_ID not in json.dumps(recovered.request)
    assert any(
        "local hash correspondence" in item
        for item in recovered.receipt["integrity_scope"]["proved"]
    )


def test_recovery_requires_and_rejects_tampered_advertised_transport_sidecar(
    tmp_path: Path,
) -> None:
    missing_paths = _fixture(tmp_path / "missing", transport_bound=True)
    missing_paths.pop("transport_receipts")
    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as missing:
        _recover(missing_paths)
    assert missing.value.code == "TRANSPORT_RECEIPTS_REQUIRED"

    tampered_paths = _fixture(tmp_path / "tampered", transport_bound=True)
    transport_path = tampered_paths["transport_receipts"]
    bundle = json.loads(transport_path.read_text(encoding="utf-8"))
    bundle["records"][0]["receipt"]["evidence"][0][
        "malware_scan_attestation_id"
    ] = _OTHER_SCAN_ATTESTATION_ID
    _write_json(transport_path, bundle)
    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as tampered:
        _recover(tampered_paths)
    assert tampered.value.code == "TRANSPORT_RECEIPTS_INVALID"


def test_recovery_rejects_v2_downgrade_and_canonical_bundle_hash_drift(
    tmp_path: Path,
) -> None:
    missing_artifact_paths = _fixture(tmp_path / "missing-artifact", transport_bound=True)
    completion_path = missing_artifact_paths["completion"]
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    del completion["artifacts"]["openresponses_transport_receipts_sha256"]
    _write_json(completion_path, completion)
    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as missing:
        _recover(missing_artifact_paths)
    assert missing.value.code == "TRANSPORT_RECEIPTS_REQUIRED"

    legacy_paths = _fixture(tmp_path / "legacy")
    unexpected_sidecar = tmp_path / "legacy" / "unexpected-sidecar.json"
    _write_json(unexpected_sidecar, {})
    legacy_paths["transport_receipts"] = unexpected_sidecar
    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as unexpected:
        _recover(legacy_paths)
    assert unexpected.value.code == "TRANSPORT_RECEIPTS_UNEXPECTED"

    hash_drift_paths = _fixture(tmp_path / "hash-drift", transport_bound=True)
    representative_path = hash_drift_paths["representative"]
    representative = json.loads(representative_path.read_text(encoding="utf-8"))
    representative["transport_receipt_bundle_sha256"] = "0" * 64
    representative_raw = _write_json(representative_path, representative)
    completion_path = hash_drift_paths["completion"]
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["transport_receipt_bundle_sha256"] = "0" * 64
    completion["artifacts"]["representative_run_receipt_sha256"] = _sha256_bytes(
        representative_raw
    )
    _write_json(completion_path, completion)
    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as hash_drift:
        _recover(hash_drift_paths)
    assert hash_drift.value.code == "TRANSPORT_RECEIPTS_INVALID"


def test_recovery_rejects_tampered_stage_payload(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    transcript = paths["transcript_4"]
    raw = transcript.read_text(encoding="utf-8")
    transcript.write_text(
        raw.replace("The opening relationship remains unresolved.", "Changed detail."),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as rejected:
        _recover(paths)

    assert rejected.value.code == "STAGE_PAYLOAD_HASH_MISMATCH"


def test_recovery_rejects_non_object_assistant_message(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    transcript = paths["transcript_1"]
    records = [
        json.loads(line)
        for line in transcript.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in records:
        message = record.get("message")
        if isinstance(message, dict) and message.get("role") == "assistant":
            record["message"] = None
    transcript.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
        newline="\n",
    )

    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as rejected:
        _recover(paths)

    assert rejected.value.code == "TRANSCRIPT_OUTPUT_INVALID"


def test_recovery_rejects_existing_output_directory(tmp_path: Path) -> None:
    recovered = _recover(_fixture(tmp_path))
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(recovery_cli.Phase8EvidenceReviewRecoveryError) as rejected:
        recovery_cli._write_recovered_output(output, recovered)

    assert rejected.value.code == "OUTPUT_ALREADY_EXISTS"


def test_recovery_accepts_and_records_legacy_windows_json_rendering(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    for name in ("representative", "controller", "proposal"):
        path = paths[name]
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))

    recovered = _recover(paths)

    source_files = recovered.receipt["source_files"]
    for name in ("representative_run_receipt", "controller_receipt", "proposal"):
        assert source_files[name]["binding_mode"] == "LF_RENDERED_JSON_SHA256"
        assert source_files[name]["actual_file_sha256"] != source_files[name]["recorded_sha256"]
