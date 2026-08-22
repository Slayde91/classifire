from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelAdmission,
    PhysicalModelLock,
    PhysicalModelSubmissionReceipt,
)
from classifire.db import Base
from classifire.models import Estimate, Opening, Project, Service
from classifire.physical_model_submission_schema import AgentInitialPhysicalModelInput
from classifire.services.adjudicated_admission import normalised_submission_payload_sha256
from classifire.services.adjudicated_physical_submission import (
    CONTROLLED_CANONICAL_WRITER_POLICY_VERSION,
    PREFLIGHT_SCHEMA,
    PREFLIGHT_STATUS,
    controlled_writer_implementation_hashes,
)
from classifire.services.protected_state_fingerprint import (
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)
from scripts.rehearse_adjudicated_canonicalisation import (
    REHEARSAL_RECEIPT_FILENAME,
    REHEARSAL_RECEIPT_SCHEMA,
    AdjudicatedCanonicalisationRehearsalError,
    run_rehearsal,
)


def _factory(path: Path) -> sessionmaker[Session]:
    engine = create_engine(f"sqlite+pysqlite:///{path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(255))"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES "
                 "('0007_reconcile_adjudicated_admission_lineages')")
        )
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


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


def _seed_source(factory: sessionmaker[Session]) -> Estimate:
    with factory() as db:
        project = Project(reference="REHEARSAL-PROJECT", name="Rehearsal project")
        db.add(project)
        db.flush()
        estimate = Estimate(
            project_id=project.id,
            reference="REHEARSAL-ESTIMATE",
            title="Rehearsal estimate",
            status="draft",
        )
        db.add(estimate)
        db.flush()
        defect = Defect(
            estimate_id=estimate.id,
            external_defect_id="D-001",
            defect_code="D-001",
            description="Synthetic defect",
            location="Synthetic location",
        )
        db.add(defect)
        db.flush()
        db.add(
            EvidenceSource(
                estimate_id=estimate.id,
                defect_id=defect.id,
                evidence_type="report",
                source_reference="synthetic-report",
                sha256="A" * 64,
            )
        )
        db.commit()
        return estimate


def _write_preflight(path: Path, factory: sessionmaker[Session], estimate: Estimate) -> None:
    with factory() as db:
        snapshot = protected_state_snapshot_from_session(db, estimate.id)
    payload = _payload()
    receipt = {
        "schema": PREFLIGHT_SCHEMA,
        "status": PREFLIGHT_STATUS,
        "project_id": estimate.project_id,
        "estimate_id": estimate.id,
        "source_run_id": "source-run-rehearsal",
        "adjudicated_receipt_run_id": "source-run-rehearsal-adjudicated-v1",
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
    path.write_text(json.dumps(receipt, sort_keys=True, separators=(",", ":")), encoding="utf-8")


def test_rehearsal_writes_only_safe_receipt_and_preserves_source(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    factory = _factory(source)
    estimate = _seed_source(factory)
    preflight = tmp_path / "preflight.json"
    _write_preflight(preflight, factory, estimate)
    output_dir = tmp_path / "rehearsal-output"

    output_path, summary = run_rehearsal(
        source_database=source,
        preflight_receipt=preflight,
        output_dir=output_dir,
    )

    assert output_path == output_dir / REHEARSAL_RECEIPT_FILENAME
    assert list(output_dir.iterdir()) == [output_path]
    assert summary["schema"] == REHEARSAL_RECEIPT_SCHEMA
    assert summary["status"] == "DISPOSABLE_REHEARSAL_PASSED_SOURCE_UNCHANGED"
    assert summary["source_database"]["write_performed"] is False
    assert summary["source_database"]["protected_state_before"] == summary[
        "source_database"
    ]["protected_state_after"]
    assert summary["disposable_copy"]["retained"] is False
    assert summary["controlled_submission"]["opening_count"] == 1
    assert summary["controlled_submission"]["service_count"] == 1
    assert summary["controlled_submission"]["service_opening_link_count"] == 1
    assert summary["controlled_submission"]["idempotent_replay_verified"] is True
    assert summary["controlled_submission"]["physical_model_lock_created"] is False
    assert summary["synthetic_admission"]["ephemeral_private_key_retained"] is False
    assert summary["synthetic_admission"]["manifest_retained"] is False

    receipt_text = output_path.read_text(encoding="utf-8")
    assert "signature" not in receipt_text.lower()
    assert "BEGIN PRIVATE KEY" not in receipt_text
    assert "BEGIN EC PRIVATE KEY" not in receipt_text
    assert "BEGIN PUBLIC KEY" not in receipt_text
    with factory() as db:
        assert db.scalar(select(Opening).where(Opening.estimate_id == estimate.id)) is None
        assert db.scalar(select(Service)) is None
        assert db.scalar(select(PhysicalModelAdmission)) is None
        assert db.scalar(select(PhysicalModelSubmissionReceipt)) is None
        assert (
            db.scalar(
                select(PhysicalModelLock).where(PhysicalModelLock.estimate_id == estimate.id)
            )
            is None
        )

    stale_receipt = json.loads(preflight.read_text(encoding="utf-8"))
    stale_receipt["implementation"]["controlled_writer_module_sha256"] = "C" * 64
    stale_path = tmp_path / "stale-preflight.json"
    stale_path.write_text(json.dumps(stale_receipt), encoding="utf-8")
    stale_output = tmp_path / "stale-output"
    with pytest.raises(AdjudicatedCanonicalisationRehearsalError) as raised:
        run_rehearsal(
            source_database=source,
            preflight_receipt=stale_path,
            output_dir=stale_output,
        )
    assert "PREFLIGHT_IMPLEMENTATION_MISMATCH" in str(raised.value)
    assert not stale_output.exists()
