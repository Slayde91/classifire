from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_phase8_admission_deployment_candidate.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("phase8_candidate_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_candidate_audit_binds_current_source_profile_and_safe_evidence() -> None:
    module = _load_script()

    audit = module.build_candidate_audit(ROOT)

    assert audit["schema"] == module.SCHEMA
    assert audit["status"] == "LOCAL_CANDIDATE_FROZEN_REVIEW_REQUIRED"
    assert audit["deployment_authorised"] is False
    assert audit["live_change_performed"] is False
    assert len(audit["candidate_sha256"]) == 64
    assert audit["plugin"] == {
        "version": "0.5.0",
        "active_profile": "phase8-admission-only",
        "active_tool": "classifire_submit_initial_physical_model",
        "source_tool_contract_count": 7,
        "dist_sha256": audit["plugin"]["dist_sha256"],
    }
    assert audit["preflight"]["candidate_eligible"] is True
    assert audit["preflight"]["opening_count"] == 17
    assert audit["preflight"]["service_count"] == 24
    assert audit["rehearsal"]["writer_agent_id"] == "cf-physical-model"
    assert audit["rehearsal"]["opening_count"] == 17
    assert audit["rehearsal"]["service_count"] == 24
    assert audit["rehearsal"]["service_opening_link_count"] == 24
    assert audit["git"]["worktree_clean"] is False
    assert audit["remaining_gate"] is not None


def test_candidate_audit_rejects_unsafe_rehearsal(tmp_path: Path) -> None:
    module = _load_script()
    source = ROOT / module.DEFAULT_REHEARSAL
    receipt = json.loads(source.read_text(encoding="utf-8"))
    receipt["controlled_submission"]["physical_model_lock_created"] = True
    tampered = tmp_path / "rehearsal.json"
    tampered.write_text(json.dumps(receipt), encoding="utf-8")

    with pytest.raises(module.CandidateAuditError, match="Unsafe rehearsal fields"):
        module._validate_rehearsal(tampered)


def test_candidate_audit_rejects_output_outside_repository() -> None:
    module = _load_script()

    with pytest.raises(module.CandidateAuditError, match="inside the repository"):
        module._output_path(ROOT, "../outside.json")
