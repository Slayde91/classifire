"""Execute one approved Phase 8 representative package, then roll it back.

The package must be self-contained and explicitly authorised. This command cannot
create an admission, submit a canonical model, or create a Physical Model Lock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess  # nosec B404
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from shutil import which
from typing import cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from classifire.services.phase8_evidence_review import (
    build_blocked_visual_evidence_review_request,
)
from classifire.services.phase8_human_reference_comparison import (
    compare_phase8_human_reference,
)
from classifire.services.phase8_linked_visual_run import Phase8VisualInferencePortFactory
from classifire.services.phase8_proposal_review import (
    build_phase8_proposal_review,
    render_phase8_proposal_review_markdown,
)
from classifire.services.phase8_representative_run import (
    Phase8RepresentativeRunError,
    Phase8RepresentativeRunPackage,
    Phase8RepresentativeRunResult,
    execute_phase8_representative_run,
    load_phase8_representative_run_package,
    verify_phase8_representative_run_package,
)
from classifire.services.phase8_visual_evidence import RetainedVisualEvidencePacket
from classifire.services.phase8_visual_proposal import Phase8VisualInferencePort
from classifire.services.phase8_visual_runtime import (
    ManagedPhase8VisualRuntime,
    verify_phase8_no_write_gateway_readiness,
)

RUNTIME_READINESS_RECEIPT_SCHEMA = "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUNTIME-READINESS-v1"


def _git_revision(repository_root: Path) -> str:
    git_executable = which("git")
    if git_executable is None:
        raise Phase8RepresentativeRunError("SOURCE_REVISION_UNAVAILABLE")
    # Security: the executable is resolved and argv is fixed; no shell is used.
    completed = subprocess.run(  # noqa: S603  # nosec B603
        [git_executable, "-C", str(repository_root), "rev-parse", "HEAD"],
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise Phase8RepresentativeRunError("SOURCE_REVISION_UNAVAILABLE")
    revision = completed.stdout.strip().lower()
    if len(revision) != 40 or any(character not in "0123456789abcdef" for character in revision):
        raise Phase8RepresentativeRunError("SOURCE_REVISION_UNAVAILABLE")
    return revision


def _write_json(path: Path, value: object) -> str:
    rendered = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(rendered)
    return hashlib.sha256(rendered).hexdigest().upper()


def _write_text(path: Path, value: str) -> str:
    rendered = value.encode("utf-8")
    path.write_bytes(rendered)
    return hashlib.sha256(rendered).hexdigest().upper()


def _failure_code(error: Exception) -> str:
    candidate = getattr(error, "code", None)
    if (
        isinstance(candidate, str)
        and candidate
        and len(candidate) <= 120
        and all(
            character.isupper() or character.isdigit() or character == "_"
            for character in candidate
        )
    ):
        return candidate
    return "UNEXPECTED_EXECUTION_ERROR"


def _failure_type(error: Exception) -> str:
    """Expose only a stable exception class name in a failure receipt."""

    candidate = type(error).__name__
    if (
        isinstance(candidate, str)
        and candidate
        and len(candidate) <= 120
        and all(character.isalnum() or character == "_" for character in candidate)
    ):
        return candidate
    return "UNCLASSIFIED_EXCEPTION"


def _verify_runtime_readiness(
    package: Phase8RepresentativeRunPackage,
) -> dict[str, object]:
    verify_phase8_no_write_gateway_readiness(
        command_prefix=package.gateway_command,
        gateway_base_url=package.gateway_base_url,
    )
    return {
        "schema": RUNTIME_READINESS_RECEIPT_SCHEMA,
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "approval_reference": package.approval_reference,
        "gateway_readiness_probed": True,
        # This is a boolean readiness result, never token material.
        "gateway_token_available": True,  # nosec B105
        "gateway_rpc_available": True,
        "probe_method": "sessions.describe",
        "runtime_started": False,
        "retrieval_performed": False,
        "inference_request_performed": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }


def _emit_failure(
    *,
    output: Path,
    package: Phase8RepresentativeRunPackage,
    failure: Exception,
) -> int:
    failure_receipt = {
        "schema": "CLASSIFIRE-PHASE8-REPRESENTATIVE-RUN-FAILURE-v1",
        "package_id": package.package_id,
        "package_sha256": package.package_sha256,
        "approval_reference": package.approval_reference,
        "failure_code": _failure_code(failure),
        "failure_type": _failure_type(failure),
        "rollback_only": True,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
        "human_reference_visible_to_inference": False,
    }
    failure_receipt_sha256 = _write_json(output / "failure-receipt.json", failure_receipt)
    print(
        json.dumps(
            {
                "status": "EXECUTION_FAILED",
                "failure_code": failure_receipt["failure_code"],
                "failure_receipt_sha256": failure_receipt_sha256,
                "rollback_only": True,
                "canonical_submission_performed": False,
                "physical_model_lock_created": False,
            },
            sort_keys=True,
        )
    )
    return 2


def _finalize_result(
    *,
    output: Path,
    package: Phase8RepresentativeRunPackage,
    result: Phase8RepresentativeRunResult,
    preflight_receipt_sha256: str,
    readiness_receipt_sha256: str,
) -> int:
    artifacts: dict[str, str] = {
        "preflight_receipt_sha256": preflight_receipt_sha256,
        "runtime_readiness_receipt_sha256": readiness_receipt_sha256,
        "runner_receipt_sha256": _write_json(
            output / "linked-visual-run-receipt.json",
            result.runner_result.receipt,
        ),
        "representative_run_receipt_sha256": _write_json(
            output / "representative-run-receipt.json",
            result.receipt,
        ),
    }
    evidence_packet = result.runner_result.evidence_packet
    if evidence_packet is not None:
        artifacts["evidence_manifest_file_sha256"] = _write_json(
            output / "evidence-manifest.json",
            evidence_packet.manifest,
        )
        artifacts["evidence_manifest_canonical_sha256"] = evidence_packet.manifest_sha256

    visual_result = result.runner_result.visual_result
    comparison_status = (
        f"SKIPPED_{visual_result.status}"
        if visual_result is not None and not visual_result.approved
        else "SKIPPED_RETRIEVAL_BLOCKED"
        if visual_result is None
        else "NOT_RUN"
    )
    if visual_result is not None:
        if evidence_packet is None:
            raise Phase8RepresentativeRunError("REVIEW_EVIDENCE_MANIFEST_MISSING")
        controller_receipt_path = output / "proposal-controller-receipt.json"
        artifacts["controller_receipt_sha256"] = _write_json(
            controller_receipt_path,
            visual_result.receipt,
        )
        proposal_path: Path | None = None
        if visual_result.proposal is not None:
            proposal_path = output / "proposal.json"
            artifacts["proposal_sha256"] = _write_json(
                proposal_path,
                visual_result.proposal,
            )
        proposal_review = build_phase8_proposal_review(
            package_id=package.package_id,
            package_sha256=package.package_sha256,
            approval_reference=package.approval_reference,
            proposal_file_bytes=(
                proposal_path.read_bytes() if proposal_path is not None else None
            ),
            proposal_file_sha256=artifacts.get("proposal_sha256"),
            controller_receipt_file_bytes=controller_receipt_path.read_bytes(),
            controller_receipt_file_sha256=artifacts["controller_receipt_sha256"],
            evidence_manifest=evidence_packet.manifest,
        )
        artifacts["proposal_review_sha256"] = _write_json(
            output / "proposal-review.json",
            proposal_review,
        )
        artifacts["proposal_review_markdown_sha256"] = _write_text(
            output / "proposal-review.md",
            render_phase8_proposal_review_markdown(proposal_review),
        )
        if visual_result.proposal is not None and visual_result.approved:
            comparison = compare_phase8_human_reference(
                proposal_path=output / "proposal.json",
                controller_receipt_path=controller_receipt_path,
                reference_path=package.human_reference_path,
                evidence_manifest_path=output / "evidence-manifest.json",
            )
            comparison_status = str(comparison["status"])
            artifacts["human_reference_comparison_sha256"] = _write_json(
                output / "human-reference-comparison.json",
                comparison,
            )

        evidence_review_request = build_blocked_visual_evidence_review_request(
            package_id=package.package_id,
            approval_reference=package.approval_reference,
            visual_result=visual_result,
            controller_receipt_file_sha256=artifacts["controller_receipt_sha256"],
            proposal_file_sha256=artifacts.get("proposal_sha256"),
        )
        if evidence_review_request is not None:
            artifacts["evidence_review_request_sha256"] = _write_json(
                output / "evidence-review-request.json",
                evidence_review_request,
            )

    completion_receipt = {
        **result.receipt,
        "artifacts": artifacts,
        "human_reference_comparison_status": comparison_status,
        "human_reference_visible_to_inference": False,
        "canonical_submission_performed": False,
        "physical_model_lock_created": False,
    }
    completion_receipt_sha256 = _write_json(
        output / "completion-receipt.json",
        completion_receipt,
    )
    print(
        json.dumps(
            {
                "status": visual_result.status
                if visual_result is not None
                else "RETRIEVAL_BLOCKED",
                "comparison_status": comparison_status,
                "completion_receipt_sha256": completion_receipt_sha256,
                "rollback_only": True,
                "canonical_submission_performed": False,
                "physical_model_lock_created": False,
            },
            sort_keys=True,
        )
    )
    return (
        0
        if visual_result is not None and visual_result.approved and comparison_status == "PASS"
        else 2
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help=(
            "Verify package and snapshot bindings plus no-write gateway readiness "
            "without retrieval or inference."
        ),
    )
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Exact checked-out source root that the package must bind.",
    )
    args = parser.parse_args()

    package = load_phase8_representative_run_package(args.package)
    output = args.output.resolve()
    if output.exists():
        raise Phase8RepresentativeRunError("OUTPUT_ALREADY_EXISTS")
    output.mkdir(parents=True)
    repository_root = args.repository_root.resolve(strict=True)
    revision = _git_revision(repository_root)
    engine = create_engine(
        f"sqlite+pysqlite:///{package.database_copy_path.as_posix()}",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @contextmanager
    def inference_port_factory(
        packet: RetainedVisualEvidencePacket,
    ) -> Iterator[Phase8VisualInferencePort]:
        with ManagedPhase8VisualRuntime(
            command_prefix=package.gateway_command,
            base_url=package.gateway_base_url,
            provider=package.provider,
            physical_model=package.physical_model,
            validator_model=package.validator_model,
            physical_agent_id=package.physical_agent_id,
            validator_agent_id=package.validator_agent_id,
            implementation_revision=revision,
            evidence_packet=packet,
        ) as runtime:
            yield runtime.transport

    result = None
    preflight = None
    preflight_receipt_sha256 = None
    readiness_receipt_sha256 = None
    failure: Exception | None = None
    try:
        with Session(engine, autoflush=False, expire_on_commit=False) as db:
            preflight = verify_phase8_representative_run_package(
                db,
                package,
                actual_git_revision=revision,
                repository_root=repository_root,
            )
            preflight_receipt_sha256 = _write_json(
                output / "preflight-receipt.json",
                preflight.receipt,
            )
            readiness_receipt_sha256 = _write_json(
                output / "runtime-readiness-receipt.json",
                _verify_runtime_readiness(package),
            )
            if not args.verify_only:
                result = execute_phase8_representative_run(
                    db,
                    package,
                    actual_git_revision=revision,
                    repository_root=repository_root,
                    inference_port_factory=cast(
                        Phase8VisualInferencePortFactory,
                        inference_port_factory,
                    ),
                )
    except Exception as exc:
        failure = exc
    finally:
        engine.dispose()

    if failure is not None:
        return _emit_failure(output=output, package=package, failure=failure)

    if args.verify_only:
        if (
            preflight is None
            or preflight_receipt_sha256 is None
            or readiness_receipt_sha256 is None
        ):
            return _emit_failure(
                output=output,
                package=package,
                failure=Phase8RepresentativeRunError("RUNNER_STATE_INVALID"),
            )
        print(
            json.dumps(
                {
                    "status": "PRECHECK_PASSED",
                    "preflight_receipt_sha256": preflight_receipt_sha256,
                    "runtime_readiness_receipt_sha256": readiness_receipt_sha256,
                    "preflight_only": True,
                    "runtime_started": False,
                    "retrieval_performed": False,
                    "canonical_submission_performed": False,
                    "physical_model_lock_created": False,
                },
                sort_keys=True,
            )
        )
        return 0

    if (
        result is None
        or preflight_receipt_sha256 is None
        or readiness_receipt_sha256 is None
    ):
        return _emit_failure(
            output=output,
            package=package,
            failure=Phase8RepresentativeRunError("RUNNER_STATE_INVALID"),
        )
    try:
        return _finalize_result(
            output=output,
            package=package,
            result=result,
            preflight_receipt_sha256=preflight_receipt_sha256,
            readiness_receipt_sha256=readiness_receipt_sha256,
        )
    except Exception as exc:
        return _emit_failure(output=output, package=package, failure=exc)


if __name__ == "__main__":
    raise SystemExit(main())
