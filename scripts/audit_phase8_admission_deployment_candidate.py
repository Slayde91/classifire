from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from classifire.services.adjudicated_physical_submission import (
    controlled_writer_implementation_hashes,
    preflight_admission_binding,
)

SCHEMA = "CLASSIFIRE-PHASE8-ADMISSION-DEPLOYMENT-CANDIDATE-v1"
PROFILE = "phase8-admission-only"
ADMISSION_TOOL = "classifire_submit_initial_physical_model"
EXPECTED_PLUGIN_VERSION = "0.5.0"

CANDIDATE_FILE_GROUPS: dict[str, tuple[str, ...]] = {
    "admission_boundary": (
        "scripts/preflight_adjudicated_canonicalisation.py",
        "scripts/rehearse_adjudicated_canonicalisation.py",
        "src/classifire/physical_model_submission_schema.py",
        "src/classifire/services/adjudicated_admission.py",
        "src/classifire/services/adjudicated_admission_registration.py",
        "src/classifire/services/adjudicated_physical_submission.py",
        "src/classifire/services/canonical_submission_state.py",
        "src/classifire/services/initial_canonicalisation_boundary.py",
        "src/classifire/services/protected_state_fingerprint.py",
        "src/classifire/api/agent_intake_physical.py",
        "src/classifire/api/physical_model.py",
        "src/classifire/api/router.py",
        "src/classifire/agent_security.py",
        "src/classifire/canonical_models.py",
        "src/classifire/models.py",
        "src/classifire/commercial_models.py",
        "src/classifire/services/physical_scope.py",
        "src/classifire/services/workflow.py",
        "src/classifire/services/workflow_db.py",
        "src/classifire/services/workflow_guard.py",
        "src/classifire/config.py",
        "src/classifire/cli.py",
    ),
    "migration_lineage": (
        "migrations/versions/0003_physical_model_foundation.py",
        "migrations/versions/0004_agent_service_principals.py",
        "migrations/versions/0005_adjudicated_admission_journal.py",
        "migrations/versions/0006_adjudicated_canonical_admissions.py",
        "migrations/versions/0006_physical_submission_receipts.py",
        "migrations/versions/0007_reconcile_adjudicated_admission_lineages.py",
    ),
    "deployment_profile": (
        "openclaw-plugin-classifire-controlled-write/src/index.ts",
        "openclaw-plugin-classifire-controlled-write/dist/index.js",
        "openclaw-plugin-classifire-controlled-write/openclaw.plugin.json",
        "openclaw-plugin-classifire-controlled-write/package.json",
        "openclaw-plugin-classifire-controlled-write/package-lock.json",
        "openclaw-plugin-classifire-controlled-write/scripts/verify-phase8-profile.mjs",
        "scripts/install_classifire_controlled_write_plugin.ps1",
        "scripts/test_classifire_controlled_write_boundaries.ps1",
        "scripts/sync_classifire_agent_scopes.py",
        "scripts/audit_phase8_admission_deployment_candidate.py",
    ),
    "agent_governance": (
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/TOOL_GRANT_MATRIX.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/MISSION_CONTROL_UPDATE.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-intake-evidence/TOOLS.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-physical-model/AGENTS.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-physical-model/TOOLS.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-physical-model/WORKFLOWS.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-technical-system/TOOLS.md",
        "agent-definitions/CLASSIFIRE_Agent_Fleet_v1.0/agents/cf-commercial-engine/TOOLS.md",
    ),
    "governance_docs": (
        "docs/PROJECT_STATE.md",
        "docs/CLASSIFIRE_ARCHITECTURE.md",
        "docs/CLASSIFIRE_ROADMAP.md",
        "docs/ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md",
        "docs/ADJUDICATED_ADMISSION_EXTERNAL_SIGNER_OPERATING_MODEL.md",
    ),
    "regression_evidence": (
        "tests/test_adjudicated_physical_submission.py",
        "tests/test_adjudicated_canonicalisation_rehearsal.py",
        "tests/test_initial_canonicalisation_boundary.py",
        "tests/test_migrations_fresh_install.py",
        "tests/test_openclaw_controlled_write_manifest.py",
        "tests/test_phase8_role_policy.py",
        "tests/test_agent_intake_physical_api.py",
        "tests/test_controlled_write_installer_boundary.py",
        "tests/test_legacy_physical_mutation_retirement.py",
        "tests/test_phase8_agent_definition_profile.py",
        "tests/test_phase8_admission_deployment_candidate_audit.py",
    ),
}

DEFAULT_PREFLIGHT = Path(
    "data/real-uat/20260822-phase8-admission-preflight-147042-v5/"
    "24-adjudicated-canonicalisation-preflight.json"
)
DEFAULT_REHEARSAL = Path(
    "data/real-uat/20260822-phase8-existing-physical-rehearsal-147042-v1/"
    "adjudicated-canonicalisation-rehearsal.json"
)


class CandidateAuditError(RuntimeError):
    pass


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(encoded)


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CandidateAuditError(f"Invalid candidate JSON: {path}") from exc
    if not isinstance(value, dict):
        raise CandidateAuditError(f"Candidate JSON must contain an object: {path}")
    return value


def _require_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateAuditError(f"Missing candidate mapping: {label}")
    return value


def _run_git(repository_root: Path, arguments: Sequence[str]) -> str:
    executable = shutil.which("git")
    if executable is None:
        raise CandidateAuditError("Git is unavailable")
    result = subprocess.run(  # noqa: S603 - fixed executable and internal arguments only
        [executable, *arguments],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise CandidateAuditError(
            f"Git command failed: {' '.join(arguments)}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _candidate_files(repository_root: Path) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for group, relative_paths in CANDIDATE_FILE_GROUPS.items():
        entries = []
        for relative_path in relative_paths:
            path = repository_root / relative_path
            if not path.is_file():
                raise CandidateAuditError(f"Candidate file is missing: {relative_path}")
            entries.append(
                {
                    "path": relative_path,
                    "sha256": _sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        result[group] = entries
    return result


def _validate_plugin_profile(repository_root: Path) -> dict[str, Any]:
    plugin_root = repository_root / "openclaw-plugin-classifire-controlled-write"
    manifest = _load_json_object(plugin_root / "openclaw.plugin.json")
    package = _load_json_object(plugin_root / "package.json")
    package_lock = _load_json_object(plugin_root / "package-lock.json")
    versions = {
        str(manifest.get("version")),
        str(package.get("version")),
        str(package_lock.get("version")),
        str(_require_mapping(package_lock.get("packages"), label="package-lock packages")
            .get("", {})
            .get("version")),
    }
    if versions != {EXPECTED_PLUGIN_VERSION}:
        raise CandidateAuditError(f"Plugin version mismatch: {sorted(versions)}")
    config_schema = _require_mapping(manifest.get("configSchema"), label="config schema")
    properties = _require_mapping(config_schema.get("properties"), label="config properties")
    profile = _require_mapping(properties.get("deploymentProfile"), label="deploymentProfile")
    if profile.get("default") != PROFILE:
        raise CandidateAuditError("Plugin does not default to the Phase 8 profile")
    tools = _require_mapping(manifest.get("contracts"), label="plugin contracts").get("tools")
    if not isinstance(tools, list) or ADMISSION_TOOL not in tools:
        raise CandidateAuditError("Admission tool is missing from the plugin contract")
    return {
        "version": EXPECTED_PLUGIN_VERSION,
        "active_profile": PROFILE,
        "active_tool": ADMISSION_TOOL,
        "source_tool_contract_count": len(tools),
        "dist_sha256": _sha256_file(plugin_root / "dist" / "index.js"),
    }


def _validate_preflight(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    receipt = _load_json_object(path)
    binding = preflight_admission_binding(raw)
    if receipt.get("candidate_eligible") is not True:
        raise CandidateAuditError("Preflight candidate is not eligible")
    for field in (
        "canonical_write_performed",
        "database_write_performed",
        "gateway_call_performed",
    ):
        if receipt.get(field) is not False:
            raise CandidateAuditError(f"Preflight is not no-write: {field}")
    current_hashes = controlled_writer_implementation_hashes()
    implementation = _require_mapping(
        receipt.get("implementation"), label="preflight implementation"
    )
    if any(implementation.get(key) != value for key, value in current_hashes.items()):
        raise CandidateAuditError("Preflight implementation hashes are stale")
    return {
        "path": path.as_posix(),
        "sha256": _sha256_bytes(raw),
        "schema": receipt.get("schema"),
        "status": receipt.get("status"),
        "candidate_eligible": True,
        "estimate_id": binding.estimate_id,
        "opening_count": len(binding.payload.get("openings", [])),
        "service_count": len(binding.payload.get("services", [])),
        "protected_state_fingerprint": binding.protected_state_fingerprint,
        "implementation_hashes": current_hashes,
    }


def _validate_rehearsal(path: Path) -> dict[str, Any]:
    receipt = _load_json_object(path)
    source = _require_mapping(receipt.get("source_database"), label="rehearsal source database")
    copy = _require_mapping(receipt.get("disposable_copy"), label="rehearsal disposable copy")
    submission = _require_mapping(
        receipt.get("controlled_submission"), label="rehearsal controlled submission"
    )
    synthetic = _require_mapping(
        receipt.get("synthetic_admission"), label="rehearsal synthetic admission"
    )
    if receipt.get("status") != "DISPOSABLE_REHEARSAL_PASSED_SOURCE_UNCHANGED":
        raise CandidateAuditError("Disposable rehearsal did not pass")
    required_false = {
        "source_database.write_performed": source.get("write_performed"),
        "disposable_copy.retained": copy.get("retained"),
        "controlled_submission.gateway_call_performed": submission.get(
            "gateway_call_performed"
        ),
        "controlled_submission.physical_model_lock_created": submission.get(
            "physical_model_lock_created"
        ),
        "synthetic_admission.ephemeral_private_key_retained": synthetic.get(
            "ephemeral_private_key_retained"
        ),
        "synthetic_admission.manifest_retained": synthetic.get("manifest_retained"),
    }
    invalid = [key for key, value in required_false.items() if value is not False]
    if invalid:
        raise CandidateAuditError(f"Unsafe rehearsal fields: {', '.join(invalid)}")
    before = _require_mapping(source.get("protected_state_before"), label="source state before")
    after = _require_mapping(source.get("protected_state_after"), label="source state after")
    if before.get("fingerprint") != after.get("fingerprint"):
        raise CandidateAuditError("Source protected-state fingerprint changed in rehearsal")
    if submission.get("writer_agent_id") != "cf-physical-model":
        raise CandidateAuditError("Rehearsal did not use cf-physical-model")
    return {
        "path": path.as_posix(),
        "sha256": _sha256_file(path),
        "schema": receipt.get("schema"),
        "status": receipt.get("status"),
        "writer_agent_id": submission.get("writer_agent_id"),
        "opening_count": submission.get("opening_count"),
        "service_count": submission.get("service_count"),
        "service_opening_link_count": submission.get("service_opening_link_count"),
        "source_protected_state_fingerprint": before.get("fingerprint"),
    }


def build_candidate_audit(
    repository_root: Path,
    *,
    preflight_path: Path = DEFAULT_PREFLIGHT,
    rehearsal_path: Path = DEFAULT_REHEARSAL,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    files = _candidate_files(repository_root)
    plugin = _validate_plugin_profile(repository_root)
    preflight = _validate_preflight(repository_root / preflight_path)
    rehearsal = _validate_rehearsal(repository_root / rehearsal_path)

    all_status_lines = _run_git(
        repository_root,
        ["status", "--porcelain=v1", "--untracked-files=all"],
    ).splitlines()
    candidate_paths = {
        entry["path"] for entries in files.values() for entry in entries
    }
    candidate_status_lines = [
        line for line in all_status_lines if line[3:] in candidate_paths
    ]
    candidate_basis = {
        "base_revision": _run_git(repository_root, ["rev-parse", "HEAD"]),
        "files": files,
        "plugin": plugin,
        "preflight_sha256": preflight["sha256"],
        "rehearsal_sha256": rehearsal["sha256"],
    }
    clean = not all_status_lines
    return {
        "schema": SCHEMA,
        "status": (
            "LOCAL_CANDIDATE_FROZEN_CLEAN"
            if clean
            else "LOCAL_CANDIDATE_FROZEN_REVIEW_REQUIRED"
        ),
        "generated_at": datetime.now(UTC).isoformat(),
        "deployment_authorised": False,
        "live_change_performed": False,
        "candidate_sha256": _canonical_sha256(candidate_basis),
        "git": {
            "base_revision": candidate_basis["base_revision"],
            "branch": _run_git(repository_root, ["branch", "--show-current"]),
            "worktree_clean": clean,
            "worktree_status_entry_count": len(all_status_lines),
            "worktree_status_sha256": _canonical_sha256(all_status_lines),
            "candidate_status_lines": candidate_status_lines,
        },
        "candidate_files": files,
        "plugin": plugin,
        "preflight": preflight,
        "rehearsal": rehearsal,
        "remaining_gate": (
            None
            if clean
            else "Review and freeze the complete dirty worktree before deployment approval."
        ),
    }


def _output_path(repository_root: Path, value: str) -> Path:
    path = (repository_root / value).resolve()
    try:
        path.relative_to(repository_root.resolve())
    except ValueError as exc:
        raise CandidateAuditError("Output path must remain inside the repository") from exc
    return path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Freeze and audit the local Phase 8 admission deployment candidate."
    )
    parser.add_argument("--repository-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--preflight", default=DEFAULT_PREFLIGHT.as_posix())
    parser.add_argument("--rehearsal", default=DEFAULT_REHEARSAL.as_posix())
    parser.add_argument("--output")
    parser.add_argument("--require-clean", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.repository_root)
    audit = build_candidate_audit(
        root,
        preflight_path=Path(args.preflight),
        rehearsal_path=Path(args.rehearsal),
    )
    rendered = json.dumps(audit, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output:
        output = _output_path(root, args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    if args.require_clean and not audit["git"]["worktree_clean"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
