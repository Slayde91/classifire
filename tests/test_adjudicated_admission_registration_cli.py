from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from typer.testing import CliRunner

import classifire.cli as cli
from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import (
    PhysicalModelAdmission,
    PhysicalModelInitialSubmission,
    PhysicalModelLock,
)
from classifire.db import Base
from classifire.models import AuditEvent, Estimate, Opening, Project, Service
from classifire.physical_model_submission_schema import AgentInitialPhysicalModelInput
from classifire.services.adjudicated_admission import (
    ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
    ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
    ADJUDICATED_ADMISSION_PURPOSE,
    admission_signing_bytes,
    normalised_submission_payload_sha256,
)
from classifire.services.adjudicated_physical_submission import (
    CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_STATUS,
    controlled_writer_implementation_hashes,
    preflight_admission_binding,
)
from classifire.services.protected_state_fingerprint import (
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)

ISSUER = "governance.classifire"
KEY_ID = "physical-admission-v1"


def _session_factory(
    *,
    schema: bool = True,
    revision: str | None = "0006_adjudicated_canonical_admissions",
) -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    if schema:
        Base.metadata.create_all(engine)
        if revision is not None:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255))"))
                connection.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
                    {"revision": revision},
                )
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _seed(db: Session) -> Estimate:
    project = Project(reference="OFFLINE-ADMISSION-PROJECT", name="Offline admission test")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="OFFLINE-ADMISSION-ESTIMATE",
        title="Offline admission test estimate",
        status="draft",
    )
    db.add(estimate)
    db.commit()
    return estimate


def _payload() -> dict[str, object]:
    return {
        "openings": [
            {
                "opening_code": "O-001",
                "external_defect_id": "D-001",
                "location": "Synthetic location",
                "substrate_type": "concrete",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "opening_type": "service_penetration",
                "diameter_mm": "100",
                "frl": "-/60/60",
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "service_type": "pipe",
                "material": "PVC",
                "outside_diameter_mm": "25",
                "quantity": "1",
                "evidence_status": "confirmed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
            }
        ],
    }


def _preflight_bytes(db: Session, estimate: Estimate) -> bytes:
    db.flush()
    snapshot = protected_state_snapshot_from_session(db, estimate.id)
    payload = _payload()
    receipt = {
        "schema": PREFLIGHT_SCHEMA,
        "status": PREFLIGHT_STATUS,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": "source-run-001",
        "adjudicated_receipt_run_id": "source-run-001-adjudicated-v1",
        "canonical_write_performed": False,
        "database_write_performed": False,
        "gateway_call_performed": False,
        "candidate_eligible": True,
        "submission_eligible": False,
        "lock_eligible": False,
        "controlled_writer_implemented": True,
        "controlled_writer_policy_version": CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
        "normalised_submission_payload": payload,
        "normalised_submission_payload_sha256": normalised_submission_payload_sha256(
            AgentInitialPhysicalModelInput.model_validate(payload).model_dump(mode="json")
        ),
        "protected_state": {
            "fingerprint_version": snapshot["fingerprint_version"],
            "fingerprint": protected_state_fingerprint(snapshot),
            "component_fingerprints": protected_component_fingerprints(snapshot),
            "counts": protected_state_counts(snapshot),
        },
        "artifact_references": {"adjudicated_proposal": {"sha256": "B" * 64}},
        "full_resolution_visual_evidence": {"verified_full_resolution_count": 1},
        "visual_adjudication_basis": {"status": "PASS"},
        "implementation": controlled_writer_implementation_hashes(),
    }
    return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _new_private_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def _public_key(private_key: ec.EllipticCurvePrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return _base64url(raw)


def _signed_manifest(
    *,
    private_key: ec.EllipticCurvePrivateKey,
    estimate: Estimate,
    preflight_bytes: bytes,
) -> dict[str, object]:
    binding = preflight_admission_binding(preflight_bytes)
    now = datetime.now(UTC).replace(microsecond=0)
    manifest: dict[str, object] = {
        "schema": ADJUDICATED_ADMISSION_P256_MANIFEST_SCHEMA,
        "admission_id": str(uuid4()),
        "purpose": ADJUDICATED_ADMISSION_PURPOSE,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "preflight_receipt_sha256": binding.raw_sha256,
        "normalised_submission_payload_sha256": binding.payload_sha256,
        "protected_state_fingerprint": binding.protected_state_fingerprint,
        "protected_state_fingerprint_version": binding.protected_state_fingerprint_version,
        "source_run_id": binding.source_run_id,
        "adjudicated_run_id": binding.adjudicated_run_id,
        "artifact_digests": dict(binding.artifact_digests),
        "policy_versions": dict(binding.policy_versions),
        "issuer": ISSUER,
        "key_id": KEY_ID,
        "issued_at": (now - timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
        "expires_at": (now + timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "signature_algorithm": ADJUDICATED_ADMISSION_P256_SIGNATURE_ALGORITHM,
        "signature": _base64url(b"\x30\x06\x02\x01\x01\x02\x01\x01"),
    }
    manifest["signature"] = _base64url(
        private_key.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    )
    return manifest


def _configure_cli(
    monkeypatch: object,
    *,
    factory: sessionmaker[Session],
    private_key: ec.EllipticCurvePrivateKey,
    enabled: bool = True,
) -> None:
    settings = SimpleNamespace(
        adjudicated_initial_submission_enabled=enabled,
        adjudicated_admission_public_keys={KEY_ID: _public_key(private_key)},
        adjudicated_admission_issuer_key_ids={ISSUER: [KEY_ID]},
        adjudicated_admission_max_ttl_seconds=900,
    )
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)


def _write_artifacts(
    tmp_path: Path,
    *,
    manifest: dict[str, object],
    preflight_bytes: bytes,
) -> tuple[Path, Path]:
    manifest_path = tmp_path / "signed-admission.json"
    preflight_path = tmp_path / "preflight.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    preflight_path.write_bytes(preflight_bytes)
    return manifest_path, preflight_path


def _invoke(
    *,
    manifest_path: Path,
    preflight_path: Path,
    confirm: bool = True,
) -> object:
    arguments = [
        "register-adjudicated-admission",
        "--manifest",
        str(manifest_path),
        "--preflight-receipt",
        str(preflight_path),
        "--operator-reference",
        "CHG-2026-0819",
    ]
    if confirm:
        arguments.append("--confirm")
    return CliRunner().invoke(cli.app, arguments)


def test_cli_registers_verified_admission_only(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 0, result.output
    assert "VERIFIED_ADMISSION_RECORDED_NO_MODEL_WRITE" in result.output
    assert str(manifest["signature"]) not in result.output
    with factory() as db:
        admission = db.scalar(select(PhysicalModelAdmission))
        audit = db.scalar(select(AuditEvent))
        assert admission is not None
        assert admission.admission_id == manifest["admission_id"]
        assert audit is not None
        assert audit.action == "register_adjudicated_physical_model_admission"
        assert audit.new_value is not None
        assert audit.new_value["canonical_write_performed"] is False
        assert db.scalar(select(PhysicalModelInitialSubmission)) is None
        assert db.scalar(select(Opening)) is None
        assert db.scalar(select(Service)) is None
        assert db.scalar(select(PhysicalModelLock)) is None


def test_cli_requires_explicit_confirmation(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path, confirm=False)

    assert result.exit_code == 2
    assert "ADMISSION_REGISTRATION_CONFIRMATION_REQUIRED" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_cli_rejects_invalid_signature_without_persisting(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    wrong_signer = _new_private_key()
    manifest["signature"] = _base64url(
        wrong_signer.sign(admission_signing_bytes(manifest), ec.ECDSA(hashes.SHA256()))
    )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_SIGNATURE_INVALID" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None
        assert db.scalar(select(Opening)) is None
        assert db.scalar(select(PhysicalModelLock)) is None


def test_cli_rejects_a_manifest_signed_by_a_different_pinned_key(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    signing_key = _new_private_key()
    wrong_pinned_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=signing_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=wrong_pinned_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_SIGNATURE_INVALID" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_cli_rejects_an_issuer_key_mapping_that_excludes_the_manifest_key(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    settings = SimpleNamespace(
        adjudicated_initial_submission_enabled=True,
        adjudicated_admission_public_keys={KEY_ID: _public_key(private_key)},
        adjudicated_admission_issuer_key_ids={ISSUER: ["different-key-id"]},
        adjudicated_admission_max_ttl_seconds=900,
    )
    monkeypatch.setattr(cli, "SessionLocal", factory)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_SIGNER_UNTRUSTED" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_cli_rejects_invalid_human_governance_reference_without_persisting(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "register-adjudicated-admission",
            "--manifest",
            str(manifest_path),
            "--preflight-receipt",
            str(preflight_path),
            "--operator-reference",
            "!",
            "--confirm",
        ],
    )

    assert result.exit_code == 2
    assert "OPERATOR_REFERENCE_INVALID" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_cli_registration_is_idempotent_without_creating_a_model(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    first = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)
    second = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    with factory() as db:
        assert len(list(db.scalars(select(PhysicalModelAdmission)))) == 1
        assert db.scalar(select(PhysicalModelInitialSubmission)) is None
        assert db.scalar(select(Opening)) is None
        assert db.scalar(select(Service)) is None
        assert db.scalar(select(PhysicalModelLock)) is None


def test_registered_admission_binding_fields_are_immutable(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )
    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)
    assert result.exit_code == 0, result.output

    with factory() as db:
        admission = db.scalar(select(PhysicalModelAdmission))
        assert admission is not None
        admission.normalised_submission_payload_json = "{}"
        with pytest.raises(ValueError, match="binding fields are immutable"):
            db.commit()
        db.rollback()


def test_cli_requires_alembic_revision_that_contains_the_admission_migration(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    ready_factory = _session_factory()
    private_key = _new_private_key()
    with ready_factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    outdated_factory = _session_factory(revision="0005_agent_service_principals")
    _configure_cli(monkeypatch, factory=outdated_factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_JOURNAL_MIGRATION_UNVERIFIED" in result.output


def test_cli_requires_feature_enablement(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    factory = _session_factory()
    private_key = _new_private_key()
    with factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    _configure_cli(monkeypatch, factory=factory, private_key=private_key, enabled=False)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_REGISTRATION_DISABLED" in result.output
    with factory() as db:
        assert db.scalar(select(PhysicalModelAdmission)) is None


def test_cli_requires_migrated_admission_journal(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    ready_factory = _session_factory()
    private_key = _new_private_key()
    with ready_factory() as db:
        estimate = _seed(db)
        preflight_bytes = _preflight_bytes(db, estimate)
        manifest = _signed_manifest(
            private_key=private_key,
            estimate=estimate,
            preflight_bytes=preflight_bytes,
        )
    unprepared_factory = _session_factory(schema=False)
    _configure_cli(monkeypatch, factory=unprepared_factory, private_key=private_key)
    manifest_path, preflight_path = _write_artifacts(
        tmp_path,
        manifest=manifest,
        preflight_bytes=preflight_bytes,
    )

    result = _invoke(manifest_path=manifest_path, preflight_path=preflight_path)

    assert result.exit_code == 2
    assert "ADMISSION_JOURNAL_SCHEMA_MISSING" in result.output
