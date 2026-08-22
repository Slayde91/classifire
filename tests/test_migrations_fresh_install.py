from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def _alembic_upgrade(
    repo_root: Path,
    database_path: Path,
    target: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["CLASSIFIRE_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    return subprocess.run(  # noqa: S603 - fixed local test command and revision target
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_fresh_sqlite_database_migrates_to_head(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "fresh-classifire.db"
    result = _alembic_upgrade(repo_root, database_path, "head")
    assert result.returncode == 0, result.stdout + "\n" + result.stderr

    with sqlite3.connect(database_path) as connection:
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        admission_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(physical_model_admissions)").fetchall()
        }
        receipt_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(physical_model_submission_receipts)"
            ).fetchall()
        }

    assert revision == ("0007_reconcile_adjudicated_admission_lineages",)
    assert {
        "users",
        "projects",
        "estimates",
        "openings",
        "services",
        "agent_service_principals",
        "physical_model_admissions",
        "physical_model_submission_receipts",
        "physical_model_locks",
        "repair_strategy_locks",
        "pricing_components",
        "gate_evidence",
        "audit_trails",
    } <= tables
    assert "physical_model_initial_submissions" not in tables
    assert {
        "normalised_submission_payload_json",
        "artifact_digests",
        "policy_versions",
        "admission_envelope_json",
    } <= admission_columns
    assert not {
        "preflight_receipt_json",
        "artifact_manifest_sha256",
        "implementation_manifest_sha256",
        "claim_idempotency_key_hash",
    } & admission_columns
    assert {
        "admission_record_id",
        "admission_id",
        "canonical_write_performed",
        "physical_model_lock_created",
        "receipt_json",
        "receipt_sha256",
    } <= receipt_columns


def test_reconciliation_refuses_nonempty_legacy_admission_journal(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "legacy-admission.db"

    legacy = _alembic_upgrade(
        repo_root,
        database_path,
        "0006_adjudicated_canonical_admissions",
    )
    assert legacy.returncode == 0, legacy.stdout + "\n" + legacy.stderr

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO physical_model_admissions (
                id, created_at, updated_at, record_version, admission_id,
                project_id, estimate_id, purpose, preflight_receipt_sha256,
                normalised_submission_payload_sha256, protected_state_fingerprint,
                protected_state_fingerprint_version, source_run_id, adjudicated_run_id,
                artifact_manifest_sha256, implementation_manifest_sha256,
                admission_envelope_json, admission_envelope_sha256,
                preflight_receipt_json, normalised_submission_payload_json, issuer_id,
                signing_key_id, signature_algorithm, signature, issued_at, expires_at,
                state
            ) VALUES (
                :id, :created_at, :updated_at, :record_version, :admission_id,
                :project_id, :estimate_id, :purpose, :preflight_receipt_sha256,
                :normalised_submission_payload_sha256, :protected_state_fingerprint,
                :protected_state_fingerprint_version, :source_run_id, :adjudicated_run_id,
                :artifact_manifest_sha256, :implementation_manifest_sha256,
                :admission_envelope_json, :admission_envelope_sha256,
                :preflight_receipt_json, :normalised_submission_payload_json, :issuer_id,
                :signing_key_id, :signature_algorithm, :signature, :issued_at, :expires_at,
                :state
            )
            """,
            {
                "id": "legacy-admission-record",
                "created_at": "2026-08-22T00:00:00+00:00",
                "updated_at": "2026-08-22T00:00:00+00:00",
                "record_version": 1,
                "admission_id": "legacy-admission",
                "project_id": "legacy-project",
                "estimate_id": "legacy-estimate",
                "purpose": "initial_adjudicated_canonicalisation",
                "preflight_receipt_sha256": "A" * 64,
                "normalised_submission_payload_sha256": "B" * 64,
                "protected_state_fingerprint": "C" * 64,
                "protected_state_fingerprint_version": "legacy-fingerprint",
                "source_run_id": "legacy-source-run",
                "adjudicated_run_id": "legacy-adjudicated-run",
                "artifact_manifest_sha256": "D" * 64,
                "implementation_manifest_sha256": "E" * 64,
                "admission_envelope_json": "{}",
                "admission_envelope_sha256": "F" * 64,
                "preflight_receipt_json": "{}",
                "normalised_submission_payload_json": "{}",
                "issuer_id": "legacy-issuer",
                "signing_key_id": "legacy-key",
                "signature_algorithm": "legacy-signature",
                "signature": "legacy-signature-bytes",
                "issued_at": "2026-08-22T00:00:00+00:00",
                "expires_at": "2026-08-22T01:00:00+00:00",
                "state": "issued",
            },
        )

    reconciliation = _alembic_upgrade(repo_root, database_path, "head")
    assert reconciliation.returncode != 0
    assert "retained journal records in physical_model_admissions" in (
        reconciliation.stdout + reconciliation.stderr
    )

    with sqlite3.connect(database_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM physical_model_admissions"
        ).fetchone()
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(physical_model_admissions)"
            ).fetchall()
        }

    assert count == (1,)
    assert "preflight_receipt_json" in columns
    assert "artifact_manifest_sha256" in columns
