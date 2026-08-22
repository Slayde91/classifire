"""Read-only Gate A audit for the current shared-main admission-writer candidate.

This script records exactly which source and compiled-plugin artefacts were
reviewed. It never reads configuration, contacts a runtime, opens a database,
creates a key, registers an admission, or performs a canonical write.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ARTIFACT_GROUPS: dict[str, tuple[str, ...]] = {
    "admission_writer": (
        "src/classifire/physical_model_submission_schema.py",
        "src/classifire/physical_models.py",
        "src/classifire/services/adjudicated_admission.py",
        "src/classifire/services/adjudicated_admission_registration.py",
        "src/classifire/services/adjudicated_key_policy.py",
        "src/classifire/services/adjudicated_physical_submission.py",
        "src/classifire/services/adjudicated_preflight.py",
        "src/classifire/services/canonical_submission_state.py",
        "src/classifire/services/initial_canonicalisation_boundary.py",
        "src/classifire/services/phase8_adjudicated_payload.py",
        "scripts/preflight_adjudicated_canonicalisation.py",
    ),
    "migration_lineage": (
        "migrations/versions/0003_physical_model_foundation.py",
        "migrations/versions/0005_adjudicated_admission_journal.py",
        "migrations/versions/0006_legacy_adjudicated_canonical_admissions.py",
        "migrations/versions/0007_reconcile_adjudicated_admission_lineages.py",
        "scripts/check_adjudicated_deployment_lineage.py",
    ),
    "plugin": (
        "openclaw-plugin-classifire-controlled-write/openclaw.plugin.json",
        "openclaw-plugin-classifire-controlled-write/src/index.ts",
        "openclaw-plugin-classifire-controlled-write/dist/index.js",
    ),
    "governance": (
        "docs/ADJUDICATED_CANONICAL_WRITER_DEPLOYMENT_RUNBOOK.md",
        "tests/test_adjudicated_admission.py",
        "tests/test_adjudicated_admission_registration.py",
        "tests/test_adjudicated_physical_submission.py",
        "tests/test_adjudicated_preflight.py",
        "tests/test_deployment_lineage.py",
        "tests/test_phase8_admission_only_profile.py",
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _git_output(repository_root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(  # noqa: S603 - fixed read-only Git command
            ["git", *args],  # noqa: S607 - fixed executable name
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def build_candidate_receipt(repository_root: Path) -> dict[str, Any]:
    """Return a deterministic source/artifact inventory without side effects."""

    repository_root = repository_root.resolve()
    artifact_groups: dict[str, list[dict[str, str | int]]] = {}
    missing_paths: list[str] = []
    for group, relative_paths in ARTIFACT_GROUPS.items():
        entries: list[dict[str, str | int]] = []
        for relative_path in relative_paths:
            path = repository_root / relative_path
            if not path.is_file():
                missing_paths.append(relative_path)
                continue
            entries.append(
                {
                    "path": relative_path,
                    "sha256": _sha256(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        artifact_groups[group] = entries

    revision = _git_output(repository_root, "rev-parse", "HEAD")
    branch = _git_output(repository_root, "branch", "--show-current")
    status = _git_output(repository_root, "status", "--porcelain")
    status_lines = [] if status is None else [line for line in status.splitlines() if line]
    stable_inventory = {
        "artifact_groups": artifact_groups,
        "missing_paths": sorted(missing_paths),
        "revision": revision,
    }
    candidate_sha256 = hashlib.sha256(
        json.dumps(stable_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest().upper()

    if missing_paths:
        status_code = "LOCAL_CANDIDATE_REQUIRED_ARTIFACT_MISSING"
    elif status is None:
        status_code = "LOCAL_CANDIDATE_GIT_STATUS_UNAVAILABLE"
    elif status_lines:
        status_code = "LOCAL_CANDIDATE_DIRTY_REVIEW_REQUIRED"
    else:
        status_code = "LOCAL_CANDIDATE_REVIEW_REQUIRED"

    return {
        "schema": "CLASSIFIRE-PHASE8-ADMISSION-DEPLOYMENT-CANDIDATE-v2",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status_code,
        "candidate_sha256": candidate_sha256,
        "artifact_groups": artifact_groups,
        "missing_paths": sorted(missing_paths),
        "git": {
            "revision": revision,
            "branch": branch,
            "worktree_clean": status == "",
            "worktree_status_lines": status_lines,
        },
        "deployment_authorised": False,
        "live_change_performed": False,
        "remaining_gate": "Human review of the exact current-main candidate is required.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="return exit code 2 unless all required artefacts exist and Git is clean",
    )
    args = parser.parse_args()
    receipt = build_candidate_receipt(args.repository_root)
    print(json.dumps(receipt, sort_keys=True))
    if args.require_clean and (
        receipt["missing_paths"] or not receipt["git"]["worktree_clean"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
