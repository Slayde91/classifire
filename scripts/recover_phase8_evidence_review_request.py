"""Recover one hash-bound Phase 8 evidence-review request without inference.

This offline command reads an existing blocked representative-run output and
the exact local OpenClaw sessions bound by its controller receipt. It never
opens the retained source report or linked-original files, retrieves evidence,
calls a model, writes canonical state, or creates a Physical Model Lock. It does
read the local session transcripts, which can contain prior prompt content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from classifire.blind_visual_inventory import (
    validate_blind_reconciliation_payload,
    validate_blind_visual_inventory_payload,
)
from classifire.services.phase8_evidence_review import (
    build_blocked_visual_evidence_review_request,
)
from classifire.services.phase8_representative_run import (
    REPRESENTATIVE_RUN_APPROVAL_SCOPE,
    REPRESENTATIVE_RUN_PACKAGE_SCHEMA,
    REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
    phase8_representative_source_tree_sha256,
)
from classifire.services.phase8_visual_proposal import (
    VISUAL_PROPOSAL_BLOCKED,
    canonical_json_sha256,
    validate_phase8_visual_proposal_receipt,
    validate_visual_physical_proposal,
)
from classifire.visual_validation import validate_visual_validator_payload

RECOVERY_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-REVIEW-RECOVERY-v1"
_MAX_JSON_BYTES = 32 * 1024 * 1024
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_ALLOWED_AGENT_IDS = frozenset(
    {
        "cf-phase8-visual-physical",
        "cf-phase8-visual-validator",
    }
)


class Phase8EvidenceReviewRecoveryError(RuntimeError):
    """Stable, content-safe failure for offline review recovery."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(f"Phase 8 evidence-review recovery failed: {code}.")


@dataclass(frozen=True, slots=True)
class RecoveredStage:
    payload: dict[str, Any]
    receipt: dict[str, object]


@dataclass(frozen=True, slots=True)
class RecoveredEvidenceReview:
    request: dict[str, object]
    receipt: dict[str, object]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in _HEX_DIGITS for character in value)
    )


def _nonblank(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _reject_json_constant(_: str) -> None:
    raise ValueError("non-standard JSON constant")


def _loads_json_object(raw: bytes, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise Phase8EvidenceReviewRecoveryError(code) from None
    if not isinstance(value, dict):
        raise Phase8EvidenceReviewRecoveryError(code)
    return value


def _read_bytes(path: Path, *, code: str) -> tuple[Path, bytes]:
    try:
        resolved = path.resolve(strict=True)
        if not resolved.is_file():
            raise OSError
        raw = resolved.read_bytes()
    except OSError:
        raise Phase8EvidenceReviewRecoveryError(code) from None
    if not raw or len(raw) > _MAX_JSON_BYTES:
        raise Phase8EvidenceReviewRecoveryError(code)
    return resolved, raw


def _read_json_object(path: Path, *, code: str) -> tuple[Path, dict[str, Any], bytes]:
    resolved, raw = _read_bytes(path, code=code)
    return resolved, _loads_json_object(raw, code=code), raw


def _render_json(value: object) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise Phase8EvidenceReviewRecoveryError("OUTPUT_NOT_JSON") from None


def _artifact_binding(
    *,
    value: dict[str, Any],
    raw: bytes,
    recorded_sha256: object,
    code: str,
) -> dict[str, str]:
    recorded = _nonblank(recorded_sha256).upper()
    actual = _sha256_bytes(raw)
    lf_rendered = _sha256_bytes(_render_json(value))
    if not _is_sha256(recorded):
        raise Phase8EvidenceReviewRecoveryError(code)
    if actual == recorded:
        mode = "BYTE_SHA256"
    elif lf_rendered == recorded:
        mode = "LF_RENDERED_JSON_SHA256"
    else:
        raise Phase8EvidenceReviewRecoveryError(code)
    return {
        "recorded_sha256": recorded,
        "actual_file_sha256": actual,
        "canonical_json_sha256": canonical_json_sha256(value),
        "binding_mode": mode,
    }


def _strict_metadata_package(package: dict[str, Any]) -> tuple[str, str, dict[str, str]]:
    if (
        set(package) != {"schema", "package_id", "approval", "execution", "inputs", "runtime"}
        or package.get("schema") != REPRESENTATIVE_RUN_PACKAGE_SCHEMA
    ):
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    package_id = _nonblank(package.get("package_id"))
    approval = package.get("approval")
    execution = package.get("execution")
    runtime = package.get("runtime")
    if not package_id or not isinstance(approval, dict) or not isinstance(execution, dict):
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    if not isinstance(runtime, dict):
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    if set(approval) != {
        "reference",
        "authorised_by",
        "authorised_at_utc",
        "scope",
        "report_sha256",
        "retrieval_hosts",
    }:
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    approval_reference = _nonblank(approval.get("reference"))
    if (
        not approval_reference
        or not _nonblank(approval.get("authorised_by"))
        or not _nonblank(approval.get("authorised_at_utc"))
        or approval.get("scope") != REPRESENTATIVE_RUN_APPROVAL_SCOPE
        or not _is_sha256(_nonblank(approval.get("report_sha256")))
        or not isinstance(approval.get("retrieval_hosts"), list)
    ):
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    if set(execution) != {
        "expected_git_revision",
        "source_tree_sha256",
        "estimate_id",
        "defect_reference",
        "operator_reference",
        "rollback_only",
        "canonical_submission_allowed",
        "physical_model_lock_allowed",
        "human_reference_visible_to_inference",
    }:
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    if (
        not _nonblank(execution.get("estimate_id"))
        or not _nonblank(execution.get("defect_reference"))
        or execution.get("rollback_only") is not True
        or execution.get("canonical_submission_allowed") is not False
        or execution.get("physical_model_lock_allowed") is not False
        or execution.get("human_reference_visible_to_inference") is not False
    ):
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    expected_runtime_keys = {
        "gateway_command",
        "gateway_base_url",
        "provider",
        "physical_model",
        "validator_model",
        "physical_agent_id",
        "validator_agent_id",
    }
    if set(runtime) != expected_runtime_keys:
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    agent_ids = {
        "cf-physical-model": _nonblank(runtime.get("physical_agent_id")),
        "cf-validator": _nonblank(runtime.get("validator_agent_id")),
    }
    if set(agent_ids.values()) != _ALLOWED_AGENT_IDS:
        raise Phase8EvidenceReviewRecoveryError("PACKAGE_INVALID")
    return package_id, approval_reference, agent_ids


def _validate_no_write_receipt(value: dict[str, Any], *, code: str) -> None:
    if (
        value.get("schema") != REPRESENTATIVE_RUN_RECEIPT_SCHEMA
        or value.get("rollback_only") is not True
        or value.get("canonical_submission_performed") is not False
        or value.get("physical_model_lock_created") is not False
        or value.get("human_reference_visible_to_inference") is not False
        or not _nonblank(value.get("package_id"))
        or not _nonblank(value.get("approval_reference"))
        or not _is_sha256(_nonblank(value.get("package_sha256")))
    ):
        raise Phase8EvidenceReviewRecoveryError(code)
    protected = value.get("protected_state")
    if (
        not isinstance(protected, dict)
        or protected.get("unchanged_after_rollback") is not True
        or protected.get("before") != protected.get("after_rollback")
    ):
        raise Phase8EvidenceReviewRecoveryError(code)


def _final_stage(
    stages: list[dict[str, Any]],
    *,
    predicate: Callable[[str], bool],
    code: str,
) -> dict[str, Any]:
    matched = [stage for stage in stages if predicate(_nonblank(stage.get("stage")))]
    if not matched:
        raise Phase8EvidenceReviewRecoveryError(code)
    return matched[-1]


def _expected_session_key(
    *,
    agent_id: str,
    controller: dict[str, Any],
    stage: dict[str, Any],
) -> str:
    identity = canonical_json_sha256(
        {
            "run_id": controller["run_id"],
            "stage": stage["stage"],
            "request_sha256": stage["request_sha256"],
        }
    )
    return f"agent:{agent_id}:classifire-phase8-{identity[:32].lower()}"


def _recover_stage(
    *,
    openclaw_root: Path,
    controller: dict[str, Any],
    stage: dict[str, Any],
    agent_ids: dict[str, str],
    seen_transcripts: set[Path],
) -> RecoveredStage:
    role = _nonblank(stage.get("role"))
    agent_id = agent_ids.get(role)
    if not agent_id or stage.get("failed") is True:
        raise Phase8EvidenceReviewRecoveryError("STAGE_NOT_RECOVERABLE")
    session_key = _expected_session_key(
        agent_id=agent_id,
        controller=controller,
        stage=stage,
    )
    expected_session_hash = _nonblank(stage.get("session_id_sha256")).upper()
    if _sha256_text(session_key) != expected_session_hash:
        raise Phase8EvidenceReviewRecoveryError("SESSION_KEY_HASH_MISMATCH")
    try:
        sessions_root = (openclaw_root / "agents" / agent_id / "sessions").resolve(strict=True)
        sessions_root.relative_to(openclaw_root)
    except (OSError, ValueError):
        raise Phase8EvidenceReviewRecoveryError("SESSIONS_ROOT_INVALID") from None
    _, sessions, sessions_raw = _read_json_object(
        sessions_root / "sessions.json",
        code="SESSIONS_INDEX_INVALID",
    )
    entry = sessions.get(session_key)
    session_id = _nonblank(entry.get("sessionId")) if isinstance(entry, dict) else ""
    if not session_id:
        raise Phase8EvidenceReviewRecoveryError("SESSION_INDEX_BINDING_MISMATCH")
    try:
        transcript_path = (sessions_root / f"{session_id}.jsonl").resolve(strict=True)
        transcript_path.relative_to(sessions_root)
    except (OSError, ValueError):
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_CONTAINMENT_INVALID") from None
    if transcript_path in seen_transcripts:
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_REUSED")
    seen_transcripts.add(transcript_path)
    _, transcript_raw = _read_bytes(transcript_path, code="TRANSCRIPT_INVALID")

    records: list[dict[str, Any]] = []
    for line in transcript_raw.splitlines():
        if line.strip():
            records.append(_loads_json_object(line, code="TRANSCRIPT_INVALID"))
    transcript_sessions = [record for record in records if record.get("type") == "session"]
    if len(transcript_sessions) != 1 or transcript_sessions[0].get("id") != session_id:
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_SESSION_MISMATCH")
    for record in records:
        record_type = _nonblank(record.get("type")).casefold()
        if "tool" in record_type or "function" in record_type:
            raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_TOOL_RECORD_FORBIDDEN")
    assistant_messages: list[dict[str, Any]] = []
    for record in records:
        message = record.get("message")
        if (
            record.get("type") == "message"
            and isinstance(message, dict)
            and message.get("role") == "assistant"
        ):
            assistant_messages.append(message)
    if len(assistant_messages) != 1:
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_OUTPUT_INVALID")
    content = assistant_messages[0].get("content")
    if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_OUTPUT_INVALID")
    if any(item.get("type") not in {"thinking", "text"} for item in content):
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_TOOL_RECORD_FORBIDDEN")
    texts = [
        item.get("text").strip()
        for item in content
        if item.get("type") == "text"
        and isinstance(item.get("text"), str)
        and item.get("text").strip()
    ]
    if len(texts) != 1:
        raise Phase8EvidenceReviewRecoveryError("TRANSCRIPT_OUTPUT_INVALID")
    payload = _loads_json_object(texts[0].encode("utf-8"), code="STAGE_PAYLOAD_INVALID")
    payload_sha256 = canonical_json_sha256(payload)
    if payload_sha256 != _nonblank(stage.get("payload_sha256")).upper():
        raise Phase8EvidenceReviewRecoveryError("STAGE_PAYLOAD_HASH_MISMATCH")
    return RecoveredStage(
        payload=payload,
        receipt={
            "sequence": stage["sequence"],
            "stage": stage["stage"],
            "role": role,
            "controller_session_id_sha256": expected_session_hash,
            "transcript_file_sha256": _sha256_bytes(transcript_raw),
            "sessions_index_file_sha256": _sha256_bytes(sessions_raw),
            "payload_canonical_json_sha256": payload_sha256,
        },
    )


def recover_phase8_evidence_review(
    *,
    package_path: Path,
    completion_path: Path,
    representative_receipt_path: Path,
    controller_path: Path,
    proposal_path: Path,
    openclaw_root: Path,
    repository_root: Path,
    recovery_script_path: Path | None = None,
) -> RecoveredEvidenceReview:
    """Recover a safe review request from exact, receipt-bound local sessions."""

    _, package, package_raw = _read_json_object(package_path, code="PACKAGE_INVALID")
    _, completion, completion_raw = _read_json_object(
        completion_path, code="COMPLETION_RECEIPT_INVALID"
    )
    _, representative, representative_raw = _read_json_object(
        representative_receipt_path,
        code="REPRESENTATIVE_RECEIPT_INVALID",
    )
    _, controller, controller_raw = _read_json_object(
        controller_path, code="CONTROLLER_RECEIPT_INVALID"
    )
    _, proposal, proposal_raw = _read_json_object(proposal_path, code="PROPOSAL_INVALID")
    try:
        resolved_openclaw_root = openclaw_root.resolve(strict=True)
        if not resolved_openclaw_root.is_dir():
            raise OSError
    except OSError:
        raise Phase8EvidenceReviewRecoveryError("OPENCLAW_ROOT_INVALID") from None

    package_id, approval_reference, agent_ids = _strict_metadata_package(package)
    package_sha256 = _sha256_bytes(package_raw)
    _validate_no_write_receipt(completion, code="COMPLETION_RECEIPT_INVALID")
    _validate_no_write_receipt(representative, code="REPRESENTATIVE_RECEIPT_INVALID")
    if (
        completion.get("human_reference_comparison_status") != f"SKIPPED_{VISUAL_PROPOSAL_BLOCKED}"
        or completion.get("package_id") != package_id
        or representative.get("package_id") != package_id
        or completion.get("approval_reference") != approval_reference
        or representative.get("approval_reference") != approval_reference
        or completion.get("package_sha256") != package_sha256
        or representative.get("package_sha256") != package_sha256
        or any(completion.get(key) != value for key, value in representative.items())
    ):
        raise Phase8EvidenceReviewRecoveryError("RUN_LINEAGE_MISMATCH")
    artifacts = completion.get("artifacts")
    if not isinstance(artifacts, dict):
        raise Phase8EvidenceReviewRecoveryError("COMPLETION_RECEIPT_INVALID")
    representative_binding = _artifact_binding(
        value=representative,
        raw=representative_raw,
        recorded_sha256=artifacts.get("representative_run_receipt_sha256"),
        code="REPRESENTATIVE_ARTIFACT_HASH_MISMATCH",
    )
    controller_binding = _artifact_binding(
        value=controller,
        raw=controller_raw,
        recorded_sha256=artifacts.get("controller_receipt_sha256"),
        code="CONTROLLER_ARTIFACT_HASH_MISMATCH",
    )
    proposal_binding = _artifact_binding(
        value=proposal,
        raw=proposal_raw,
        recorded_sha256=artifacts.get("proposal_sha256"),
        code="PROPOSAL_ARTIFACT_HASH_MISMATCH",
    )
    controller_canonical_sha256 = canonical_json_sha256(controller)
    if (
        controller_canonical_sha256
        != _nonblank(completion.get("controller_receipt_sha256")).upper()
        or controller_canonical_sha256
        != _nonblank(representative.get("controller_receipt_sha256")).upper()
    ):
        raise Phase8EvidenceReviewRecoveryError("CONTROLLER_CANONICAL_HASH_MISMATCH")

    controller_errors = validate_phase8_visual_proposal_receipt(controller)
    if controller_errors or controller.get("status") != VISUAL_PROPOSAL_BLOCKED:
        raise Phase8EvidenceReviewRecoveryError("CONTROLLER_RECEIPT_INVALID")
    raw_stages = controller.get("stages")
    if not isinstance(raw_stages, list) or any(not isinstance(stage, dict) for stage in raw_stages):
        raise Phase8EvidenceReviewRecoveryError("CONTROLLER_RECEIPT_INVALID")
    stages = list(raw_stages)
    seen_transcripts: set[Path] = set()
    recovered_stages = [
        _recover_stage(
            openclaw_root=resolved_openclaw_root,
            controller=controller,
            stage=stage,
            agent_ids=agent_ids,
            seen_transcripts=seen_transcripts,
        )
        for stage in stages
    ]
    recovered_by_sequence = {
        int(stage["sequence"]): recovered
        for stage, recovered in zip(stages, recovered_stages, strict=True)
    }
    blind_stage = _final_stage(
        stages,
        predicate=lambda name: name in {"blind_inventory", "blind_inventory_retry"},
        code="BLIND_STAGE_MISSING",
    )
    proposal_stage = _final_stage(
        stages,
        predicate=lambda name: (
            name == "physical_proposal"
            or name.startswith(("physical_structural_retry_", "physical_correction_"))
        ),
        code="PROPOSAL_STAGE_MISSING",
    )
    validator_stage = _final_stage(
        stages,
        predicate=lambda name: name.startswith("conditioned_validator_"),
        code="VALIDATOR_STAGE_MISSING",
    )
    blind = recovered_by_sequence[int(blind_stage["sequence"])].payload
    recovered_proposal = recovered_by_sequence[int(proposal_stage["sequence"])].payload
    validator = recovered_by_sequence[int(validator_stage["sequence"])].payload
    if recovered_proposal != proposal:
        raise Phase8EvidenceReviewRecoveryError("PROPOSAL_TRANSCRIPT_MISMATCH")
    result_hashes = controller.get("result_hashes")
    if not isinstance(result_hashes, dict):
        raise Phase8EvidenceReviewRecoveryError("CONTROLLER_RECEIPT_INVALID")
    if (
        canonical_json_sha256(blind)
        != _nonblank(result_hashes.get("blind_inventory_sha256")).upper()
        or canonical_json_sha256(proposal)
        != _nonblank(result_hashes.get("proposal_sha256")).upper()
        or canonical_json_sha256(validator)
        != _nonblank(result_hashes.get("validator_sha256")).upper()
    ):
        raise Phase8EvidenceReviewRecoveryError("RESULT_HASH_MISMATCH")
    if (
        validate_blind_visual_inventory_payload(blind)
        or validate_visual_physical_proposal(
            proposal,
            defect_reference=_nonblank(controller.get("defect_reference")),
        )
        or validate_visual_validator_payload(validator, proposal)
        or validate_blind_reconciliation_payload(blind, proposal, validator)
        or _nonblank(validator.get("verdict")).upper() != "BLOCKED"
    ):
        raise Phase8EvidenceReviewRecoveryError("BLOCKED_PAYLOAD_INVALID")

    review_request = build_blocked_visual_evidence_review_request(
        package_id=package_id,
        approval_reference=approval_reference,
        visual_result=SimpleNamespace(
            status=VISUAL_PROPOSAL_BLOCKED,
            blind_inventory=blind,
            validator=validator,
        ),
        controller_receipt_file_sha256=_sha256_bytes(controller_raw),
        proposal_file_sha256=_sha256_bytes(proposal_raw),
    )
    if review_request is None:
        raise Phase8EvidenceReviewRecoveryError("REVIEW_REQUEST_UNAVAILABLE")

    try:
        resolved_repository_root = repository_root.resolve(strict=True)
        recovery_source_tree_sha256 = phase8_representative_source_tree_sha256(
            resolved_repository_root
        )
    except (OSError, RuntimeError):
        raise Phase8EvidenceReviewRecoveryError("RECOVERY_SOURCE_INVALID") from None
    selected_script = recovery_script_path or Path(__file__)
    _, recovery_script_raw = _read_bytes(selected_script, code="RECOVERY_SOURCE_INVALID")
    review_file = _render_json(review_request)
    recovery_receipt: dict[str, object] = {
        "schema": RECOVERY_RECEIPT_SCHEMA,
        "status": "RECOVERED_HASH_VERIFIED_LOCAL_TRANSCRIPTS",
        "package_id": package_id,
        "approval_reference": approval_reference,
        "source_files": {
            "package": {
                "actual_file_sha256": package_sha256,
            },
            "completion_receipt": {
                "actual_file_sha256": _sha256_bytes(completion_raw),
                "canonical_json_sha256": canonical_json_sha256(completion),
            },
            "representative_run_receipt": representative_binding,
            "controller_receipt": controller_binding,
            "proposal": proposal_binding,
        },
        "source_run_implementation_revision": controller["implementation_revision"],
        "stages": [recovered.receipt for recovered in recovered_stages],
        "evidence_review_request_file_sha256": _sha256_bytes(review_file),
        "evidence_review_request_canonical_json_sha256": canonical_json_sha256(review_request),
        "recovery_source_tree_sha256": recovery_source_tree_sha256,
        "recovery_script_sha256": _sha256_bytes(recovery_script_raw),
        "integrity_scope": {
            "proved": [
                "package and no-write run-receipt lineage",
                "controller and proposal content bindings",
                "deterministic session-key bindings for every successful stage",
                "local transcript payload hashes for every successful stage",
                "final blind, proposal, and Validator domain validity",
            ],
            "not_replayed": [
                "Gateway authentication",
                "runtime tool attestation or audit",
                "OpenResponses response identity",
                "external inference transport",
            ],
            "local_session_history_immutable": False,
        },
        "source_report_or_linked_original_file_read_performed": False,
        "inference_request_performed": False,
        "retrieval_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    return RecoveredEvidenceReview(request=review_request, receipt=recovery_receipt)


def _write_recovered_output(output: Path, recovered: RecoveredEvidenceReview) -> str:
    if output.exists():
        raise Phase8EvidenceReviewRecoveryError("OUTPUT_ALREADY_EXISTS")
    try:
        parent = output.parent.resolve(strict=True)
        temporary = parent / f".{output.name}.tmp-{uuid.uuid4().hex}"
        temporary.mkdir()
        request_bytes = _render_json(recovered.request)
        receipt_bytes = _render_json(recovered.receipt)
        (temporary / "evidence-review-request.json").write_bytes(request_bytes)
        (temporary / "recovery-receipt.json").write_bytes(receipt_bytes)
        if (
            _sha256_bytes((temporary / "evidence-review-request.json").read_bytes())
            != recovered.receipt["evidence_review_request_file_sha256"]
            or len(list(temporary.iterdir())) != 2
        ):
            raise Phase8EvidenceReviewRecoveryError("OUTPUT_VERIFICATION_FAILED")
        temporary.replace(output)
        return _sha256_bytes((output / "recovery-receipt.json").read_bytes())
    except Phase8EvidenceReviewRecoveryError:
        raise
    except OSError:
        raise Phase8EvidenceReviewRecoveryError("OUTPUT_WRITE_FAILED") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--completion", required=True, type=Path)
    parser.add_argument("--representative-receipt", required=True, type=Path)
    parser.add_argument("--controller", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--openclaw-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise Phase8EvidenceReviewRecoveryError("OUTPUT_ALREADY_EXISTS")
        recovered = recover_phase8_evidence_review(
            package_path=args.package,
            completion_path=args.completion,
            representative_receipt_path=args.representative_receipt,
            controller_path=args.controller,
            proposal_path=args.proposal,
            openclaw_root=args.openclaw_root,
            repository_root=args.repository_root,
        )
        recovery_receipt_file_sha256 = _write_recovered_output(
            args.output,
            recovered,
        )
    except Phase8EvidenceReviewRecoveryError as exc:
        print(json.dumps({"status": "RECOVERY_FAILED", "failure_code": exc.code}))
        return 2
    except Exception:
        print(
            json.dumps(
                {
                    "status": "RECOVERY_FAILED",
                    "failure_code": "UNEXPECTED_RECOVERY_ERROR",
                }
            )
        )
        return 2
    print(
        json.dumps(
            {
                "status": recovered.receipt["status"],
                "evidence_review_request_file_sha256": recovered.receipt[
                    "evidence_review_request_file_sha256"
                ],
                "recovery_receipt_file_sha256": recovery_receipt_file_sha256,
                "source_report_or_linked_original_file_read_performed": False,
                "inference_request_performed": False,
                "retrieval_performed": False,
                "canonical_submission_performed": False,
                "physical_model_lock_created": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
