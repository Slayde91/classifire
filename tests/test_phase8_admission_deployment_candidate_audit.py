from __future__ import annotations

import importlib.util
from pathlib import Path


def _audit_module():  # type: ignore[no-untyped-def]
    path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "audit_phase8_admission_deployment_candidate.py"
    )
    spec = importlib.util.spec_from_file_location("phase8_candidate_audit", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_audit_records_current_source_without_live_or_deployment_authority() -> None:
    module = _audit_module()
    receipt = module.build_candidate_receipt(Path(__file__).resolve().parents[1])

    assert receipt["schema"] == "CLASSIFIRE-PHASE8-ADMISSION-DEPLOYMENT-CANDIDATE-v2"
    assert receipt["deployment_authorised"] is False
    assert receipt["live_change_performed"] is False
    assert receipt["artifact_groups"]["admission_writer"]
    plugin_entries = receipt["artifact_groups"]["plugin"]
    plugin_paths = {entry["path"] for entry in plugin_entries}
    plugin_artifact = "openclaw-plugin-classifire-controlled-write/dist/index.js"
    assert plugin_artifact in receipt["missing_paths"] or plugin_artifact in plugin_paths
    assert receipt["status"] in {
        "LOCAL_CANDIDATE_REQUIRED_ARTIFACT_MISSING",
        "LOCAL_CANDIDATE_DIRTY_REVIEW_REQUIRED",
    }


def test_audit_hash_is_stable_when_only_generated_at_changes() -> None:
    module = _audit_module()
    root = Path(__file__).resolve().parents[1]

    first = module.build_candidate_receipt(root)
    second = module.build_candidate_receipt(root)

    assert first["candidate_sha256"] == second["candidate_sha256"]
    assert first["candidate_sha256"]
    assert first["generated_at"]
    assert second["generated_at"]
