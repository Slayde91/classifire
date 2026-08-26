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

from classifire.services.phase8_evidence_review import (  # noqa: E402
    EVIDENCE_REVIEW_REQUEST_SCHEMA,
)
from classifire.services.phase8_openresponses_transport import (  # noqa: E402
    OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA,
)
from classifire.services.phase8_representative_run import (  # noqa: E402
    REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
)
from classifire.services.phase8_visual_proposal import (  # noqa: E402
    canonical_json_sha256,
)


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
    visual_result = SimpleNamespace(
        status="VISUAL_PROPOSAL_BLOCKED",
        approved=False,
        proposal={"schema": "proposal"},
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
        receipt={"schema": "controller-receipt"},
    )
    transport_receipt_bundle = {
        "schema": OPENRESPONSES_TRANSPORT_RECEIPT_BUNDLE_SCHEMA,
        "run_id": "package-001",
        "evidence_manifest_sha256": "A" * 64,
        "controller_receipt_canonical_json_sha256": "B" * 64,
        "records": [{"retained": True}],
    }
    result = SimpleNamespace(
        runner_result=SimpleNamespace(
            receipt={"schema": "runner-receipt"},
            visual_result=visual_result,
            transport_receipt_records=({"retained": True},),
        ),
        transport_receipt_bundle=transport_receipt_bundle,
        receipt={
            "schema": REPRESENTATIVE_RUN_RECEIPT_SCHEMA,
            "transport_receipt_bundle_sha256": canonical_json_sha256(
                transport_receipt_bundle
            ),
        },
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
        "_configured_ready_malware_scanner",
        lambda: object(),
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
    assert completion["schema"] == REPRESENTATIVE_RUN_RECEIPT_SCHEMA
    assert completion["transport_receipt_bundle_sha256"] == canonical_json_sha256(
        transport_receipt_bundle
    )
    assert "human_reference_comparison_sha256" not in completion["artifacts"]
    assert json.loads(
        (output / "openresponses-transport-receipts.json").read_text(encoding="utf-8")
    ) == transport_receipt_bundle
    assert (output / "proposal.json").is_file()
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
        "openresponses_transport_receipts_sha256": (
            "openresponses-transport-receipts.json"
        ),
        "controller_receipt_sha256": "proposal-controller-receipt.json",
        "proposal_sha256": "proposal.json",
        "evidence_review_request_sha256": "evidence-review-request.json",
    }.items():
        assert (
            completion["artifacts"][artifact_name]
            == hashlib.sha256((output / filename).read_bytes()).hexdigest().upper()
        )
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "VISUAL_PROPOSAL_BLOCKED"
    assert summary["comparison_status"] == "SKIPPED_VISUAL_PROPOSAL_BLOCKED"
    assert (
        summary["completion_receipt_sha256"]
        == hashlib.sha256((output / "completion-receipt.json").read_bytes()).hexdigest().upper()
    )
