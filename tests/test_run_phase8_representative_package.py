from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import run_phase8_representative_package as representative_cli  # noqa: E402
from test_phase8_proposal_review import _manifest, _review_inputs  # noqa: E402
from test_phase8_visual_proposal import _proposal  # noqa: E402

from classifire.services.phase8_evidence_review import (  # noqa: E402
    EVIDENCE_REVIEW_REQUEST_SCHEMA,
)
from classifire.services.phase8_proposal_review import Phase8ProposalReviewError  # noqa: E402
from classifire.services.phase8_visual_proposal import canonical_json_sha256  # noqa: E402


class _Session:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, *_exc_info: object) -> None:
        return None


class _Engine:
    def dispose(self) -> None:
        return None


def test_blocked_visual_proposal_writes_completion_without_human_comparison(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    output = tmp_path / "output"
    package = SimpleNamespace(
        package_id="package-001",
        package_sha256="9" * 64,
        approval_reference="TEST-APPROVAL-001",
        database_copy_path=tmp_path / "snapshot.db",
        human_reference_path=tmp_path / "human-reference.json",
        gateway_command=("gateway",),
        gateway_base_url="http://127.0.0.1:18789",
        provider="openai",
        physical_model="physical-model",
        validator_model="validator-model",
        physical_agent_id="cf-phase8-visual-physical",
        validator_agent_id="cf-phase8-visual-validator",
    )
    proposal = _proposal()
    review_inputs = _review_inputs(proposal)
    controller_receipt = json.loads(review_inputs["controller_receipt_file_bytes"])
    controller_receipt["status"] = "VISUAL_PROPOSAL_BLOCKED"
    controller_receipt["errors"] = ["Validator blocked the proposal."]
    manifest = _manifest()
    visual_result = SimpleNamespace(
        status="VISUAL_PROPOSAL_BLOCKED",
        approved=False,
        proposal=proposal,
        validator={
            "verdict": "BLOCKED",
            "issues": [
                {
                    "code": "MISSED_OPENING",
                    "detail": "Confirm whether the two views show one or two openings.",
                    "evidence_refs": ["E-001"],
                }
            ],
            "limitations": [
                "The supplied views do not establish face continuity.",
                "https://example.invalid/path?Signature=redacted",
            ],
            "blind_reconciliation": [
                {
                    "blind_candidate_id": "V-O-001",
                    "disposition": "UNRESOLVED",
                    "detail": "The candidate opening cannot be related across the supplied views.",
                    "evidence_refs": ["E-001"],
                },
                {
                    "blind_candidate_id": "V-S-001",
                    "disposition": "ACCOUNTED_FOR",
                    "detail": "The visible service group is represented in the proposal.",
                    "evidence_refs": ["E-002"],
                },
            ],
        },
        blind_inventory={
            "candidate_openings": [
                {
                    "candidate_id": "V-O-001",
                    "detail": "Possible opening in the wide view.",
                    "evidence_refs": ["E-001"],
                }
            ],
            "candidate_services": [
                {
                    "candidate_id": "V-S-001",
                    "detail": "Visible service group in the close view.",
                    "evidence_refs": ["E-002"],
                }
            ],
            "unresolved_candidates": [],
            "limitations": [],
        },
        receipt=controller_receipt,
    )
    result = SimpleNamespace(
        runner_result=SimpleNamespace(
            receipt={"schema": "runner-receipt"},
            visual_result=visual_result,
            evidence_packet=SimpleNamespace(
                manifest=manifest,
                manifest_sha256=canonical_json_sha256(manifest),
            ),
        ),
        receipt={"schema": "representative-receipt"},
    )
    comparison_called = False

    def comparison_must_not_run(**_kwargs: object) -> dict[str, object]:
        nonlocal comparison_called
        comparison_called = True
        raise AssertionError("human comparison must not run for a blocked proposal")

    monkeypatch.setattr(
        representative_cli,
        "load_phase8_representative_run_package",
        lambda _path: package,
    )
    monkeypatch.setattr(representative_cli, "_git_revision", lambda _root: "a" * 40)
    monkeypatch.setattr(representative_cli, "create_engine", lambda *_args, **_kwargs: _Engine())
    monkeypatch.setattr(representative_cli, "Session", lambda *_args, **_kwargs: _Session())
    monkeypatch.setattr(
        representative_cli,
        "verify_phase8_representative_run_package",
        lambda *_args, **_kwargs: SimpleNamespace(receipt={"schema": "preflight"}),
    )
    monkeypatch.setattr(
        representative_cli,
        "_verify_runtime_readiness",
        lambda _package: {"schema": "runtime-readiness"},
    )
    monkeypatch.setattr(
        representative_cli,
        "execute_phase8_representative_run",
        lambda *_args, **_kwargs: result,
    )
    monkeypatch.setattr(
        representative_cli,
        "compare_phase8_human_reference",
        comparison_must_not_run,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_representative_package.py",
            "--package",
            str(tmp_path / "package.json"),
            "--output",
            str(output),
            "--repository-root",
            str(tmp_path),
        ],
    )

    assert representative_cli.main() == 2
    assert comparison_called is False

    completion = json.loads((output / "completion-receipt.json").read_text(encoding="utf-8"))
    assert completion["human_reference_comparison_status"] == "SKIPPED_VISUAL_PROPOSAL_BLOCKED"
    assert "human_reference_comparison_sha256" not in completion["artifacts"]
    assert (output / "proposal.json").is_file()
    assert (output / "evidence-manifest.json").is_file()
    assert (output / "proposal-review.json").is_file()
    assert (output / "proposal-review.md").is_file()
    review_request = json.loads(
        (output / "evidence-review-request.json").read_text(encoding="utf-8")
    )
    assert review_request["schema"] == EVIDENCE_REVIEW_REQUEST_SCHEMA
    assert review_request["status"] == "HUMAN_EVIDENCE_REVIEW_REQUIRED"
    assert review_request["review_items"] == [
        {
            "source": "validator_issue",
            "code": "MISSED_OPENING",
            "detail": "Confirm whether the two views show one or two openings.",
            "evidence_refs": ["E-001"],
        },
        {
            "source": "validator_limitation",
            "code": None,
            "detail": "The supplied views do not establish face continuity.",
            "evidence_refs": [],
        },
    ]
    assert review_request["unresolved_blind_observations"] == [
        {
            "blind_candidate_id": "V-O-001",
            "kind": "opening",
            "detail": "Possible opening in the wide view.",
            "evidence_refs": ["E-001"],
            "validator_detail": (
                "The candidate opening cannot be related across the supplied views."
            ),
            "validator_evidence_refs": ["E-001"],
        }
    ]
    assert review_request["canonical_submission_performed"] is False
    assert review_request["physical_model_lock_created"] is False
    assert review_request["human_reference_visible_to_inference"] is False
    assert "https://" not in json.dumps(review_request)
    assert "evidence_review_request_sha256" in completion["artifacts"]
    for artifact_name, filename in {
        "controller_receipt_sha256": "proposal-controller-receipt.json",
        "proposal_sha256": "proposal.json",
        "evidence_manifest_file_sha256": "evidence-manifest.json",
        "proposal_review_sha256": "proposal-review.json",
        "proposal_review_markdown_sha256": "proposal-review.md",
        "evidence_review_request_sha256": "evidence-review-request.json",
    }.items():
        assert (
            completion["artifacts"][artifact_name]
            == hashlib.sha256((output / filename).read_bytes()).hexdigest().upper()
        )
    assert completion["artifacts"]["evidence_manifest_canonical_sha256"] == (
        canonical_json_sha256(
            json.loads((output / "evidence-manifest.json").read_text(encoding="utf-8"))
        )
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "VISUAL_PROPOSAL_BLOCKED"
    assert summary["comparison_status"] == "SKIPPED_VISUAL_PROPOSAL_BLOCKED"
    assert (
        summary["completion_receipt_sha256"]
        == hashlib.sha256((output / "completion-receipt.json").read_bytes()).hexdigest().upper()
    )

    failure_output = tmp_path / "review-failure-output"

    def fail_review(**_kwargs: object) -> dict[str, object]:
        raise Phase8ProposalReviewError("SYNTHETIC_REVIEW_FAILURE")

    monkeypatch.setattr(representative_cli, "build_phase8_proposal_review", fail_review)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_phase8_representative_package.py",
            "--package",
            str(tmp_path / "package.json"),
            "--output",
            str(failure_output),
            "--repository-root",
            str(tmp_path),
        ],
    )

    assert representative_cli.main() == 2
    failure_summary = json.loads(capsys.readouterr().out)
    failure_receipt = json.loads(
        (failure_output / "failure-receipt.json").read_text(encoding="utf-8")
    )
    assert failure_summary["status"] == "EXECUTION_FAILED"
    assert failure_summary["failure_code"] == "SYNTHETIC_REVIEW_FAILURE"
    assert failure_receipt["failure_code"] == "SYNTHETIC_REVIEW_FAILURE"
    assert not (failure_output / "completion-receipt.json").exists()
