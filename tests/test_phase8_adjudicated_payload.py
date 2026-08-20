from __future__ import annotations

import json

import pytest
from physical_foundation_support import add_estimate, physical_session

from classifire.services.adjudicated_admission import sha256_hex
from classifire.services.phase8_adjudicated_payload import (
    Phase8AdjudicatedPayloadError,
    derive_phase8_adjudicated_payload,
)
from classifire.services.physical_defects import bind_canonical_defect


def _write(path, value):  # type: ignore[no-untyped-def]
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    path.write_bytes(raw)
    return sha256_hex(raw)


def _artifacts(tmp_path, estimate_id):  # type: ignore[no-untyped-def]
    proposal = {
        "schema": "CLASSIFIRE-ADJUDICATED-PROPOSAL-v1",
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "runtime_inference_performed": False,
        "defect_count": 1,
        "supported_defect_count": 1,
        "limited_defect_count": 0,
        "limitations": [],
        "proposed_opening_count": 1,
        "proposed_service_count": 1,
        "openings": [
            {
                "external_defect_id": "D-001",
                "opening_code": "O-001",
                "opening_type": "service_penetration",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "service_type": "pipe",
                "material": "PVC",
                "quantity": "1",
                "opening_codes": ["O-001"],
                "primary_opening_code": "O-001",
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
            }
        ],
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_hash = _write(proposal_path, proposal)
    diff = {
        "schema": "CLASSIFIRE-ADJUDICATED-PROPOSAL-DIFF-v1",
        "scope": "OFFLINE_HUMAN_ADJUDICATION_ONLY",
        "estimate_id": estimate_id,
        "run_id": "source-run-001",
        "revision_proposal_sha256": proposal_hash,
        "human_comparison_sha256": "A" * 64,
        "database_write_performed": False,
        "gateway_call_performed": False,
    }
    diff_path = tmp_path / "diff.json"
    diff_hash = _write(diff_path, diff)
    protected = {
        "protected_state_unchanged": True,
        "changed_components": [],
        "before_fingerprint": "B" * 64,
        "after_fingerprint": "B" * 64,
        "before_counts": {"openings": 0},
        "after_counts": {"openings": 0},
        "before_component_fingerprints": {"openings": "C" * 64},
        "after_component_fingerprints": {"openings": "C" * 64},
    }
    final_state = {
        "schema": "CLASSIFIRE-ADJUDICATED-PROPOSAL-ONLY-FINAL-STATE-v1",
        "status": "ADJUDICATED_PROPOSAL_READY_FOR_HUMAN_REVIEW",
        "estimate_id": estimate_id,
        "source_run_id": "source-run-001",
        "run_id": "adjudicated-run-001",
        "proposal_sha256": proposal_hash,
        "diff_receipt": {"path": "diff.json", "sha256": diff_hash},
        "withheld_tool": "classifire_submit_initial_physical_model",
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "runtime_inference_performed": False,
        "protected_state": protected,
    }
    final_path = tmp_path / "final.json"
    final_hash = _write(final_path, final_state)
    comparison = {
        "schema": "CLASSIFIRE-HUMAN-ADJUDICATION-PROPOSAL-COMPARISON-v1",
        "status": "PASS",
        "estimate_id": estimate_id,
        "source_run_id": "source-run-001",
        "defect_count": 1,
        "passed_defect_count": 1,
        "mismatch_defect_count": 0,
        "defects": [{"external_defect_id": "D-001", "status": "PASS"}],
        "revision_proposal": {"path": "proposal.json", "sha256": proposal_hash},
        "final_state_receipt": {"path": "final.json", "sha256": final_hash},
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
    }
    comparison_path = tmp_path / "comparison.json"
    _write(comparison_path, comparison)
    return proposal_path, final_path, diff_path, comparison_path


def test_phase8_receipt_graph_derives_clean_stack_payload(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        defect = bind_canonical_defect(db, estimate, "D-001")
        proposal, final_state, diff, comparison = _artifacts(tmp_path, estimate.id)

        result = derive_phase8_adjudicated_payload(
            db,
            estimate_id=estimate.id,
            adjudicated_proposal_path=proposal,
            adjudicated_final_state_path=final_state,
            adjudicated_diff_path=diff,
            human_comparison_path=comparison,
        )

        assert result.source_run_id == "source-run-001"
        assert result.adjudicated_run_id == "adjudicated-run-001"
        assert result.payload["openings"][0]["canonical_defect_id"] == defect.id
        assert result.payload["service_opening_links"] == [
            {
                "service_code": "S-001",
                "opening_code": "O-001",
                "link_type": "penetrates",
                "relationship_status": "confirmed",
                "evidence_status": "confirmed",
                "confidence": None,
                "source_reference": None,
                "notes": None,
            }
        ]


def test_phase8_receipt_graph_rejects_changed_protected_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with physical_session() as db:
        estimate = add_estimate(db)
        bind_canonical_defect(db, estimate, "D-001")
        proposal, final_state, diff, comparison = _artifacts(tmp_path, estimate.id)
        final = json.loads(final_state.read_text(encoding="utf-8"))
        final["protected_state"]["protected_state_unchanged"] = False
        _write(final_state, final)

        with pytest.raises(Phase8AdjudicatedPayloadError) as rejected:
            derive_phase8_adjudicated_payload(
                db,
                estimate_id=estimate.id,
                adjudicated_proposal_path=proposal,
                adjudicated_final_state_path=final_state,
                adjudicated_diff_path=diff,
                human_comparison_path=comparison,
            )
        assert rejected.value.code == "ADJUDICATED_PROTECTED_STATE_INVALID"
