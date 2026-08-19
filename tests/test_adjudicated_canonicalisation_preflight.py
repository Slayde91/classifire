from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from classifire import canonical_models, commercial_models  # noqa: F401
from classifire.canonical_models import (
    Defect,
    EvidenceSource,
    PhysicalModelLock,
    RepairStrategy,
)
from classifire.commercial_models import ComponentRequirementReconciliation
from classifire.db import Base
from classifire.models import Approval, Estimate, Project
from classifire.services.adjudicated_physical_submission import (
    controlled_writer_implementation_hashes,
)
from classifire.services.protected_state_fingerprint import (
    protected_component_fingerprints,
    protected_state_counts,
    protected_state_fingerprint,
    protected_state_snapshot_from_session,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import preflight_adjudicated_canonicalisation as preflight  # noqa: E402

_PRODUCTION_VISUAL_REVALIDATOR = preflight._validate_full_resolution_visual_evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)()


def _seed(db):
    project = Project(reference="PREFLIGHT-PROJECT", name="Preflight project")
    db.add(project)
    db.flush()
    estimate = Estimate(
        project_id=project.id,
        reference="PREFLIGHT-ESTIMATE",
        title="Preflight estimate",
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


def _protected_state(db, estimate_id: str) -> dict:
    snapshot = protected_state_snapshot_from_session(db, estimate_id)
    return {
        "fingerprint_version": snapshot["fingerprint_version"],
        "before_fingerprint": protected_state_fingerprint(snapshot),
        "after_fingerprint": protected_state_fingerprint(snapshot),
        "before_component_fingerprints": protected_component_fingerprints(snapshot),
        "after_component_fingerprints": protected_component_fingerprints(snapshot),
        "before_counts": protected_state_counts(snapshot),
        "after_counts": protected_state_counts(snapshot),
        "changed_components": [],
        "protected_state_unchanged": True,
    }


_SAME = object()


@pytest.fixture(autouse=True)
def _stub_full_resolution_revalidation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep artifact-chain tests isolated; the production default is never bypassed."""

    monkeypatch.setattr(
        preflight,
        "_validate_full_resolution_visual_evidence",
        lambda *_, **__: {
            "report_sha256": "B" * 64,
            "required_linked_photo_count": 1,
            "validated_primary_count": 1,
            "validated_mandatory_secondary_count": 1,
            "visual_defects": [],
        },
    )


def _artifacts(
    tmp_path: Path,
    db,
    estimate_id: str,
    *,
    material: str | None = "PVC",
    source_material: str | None | object = _SAME,
    include_human_decision: bool | object = _SAME,
    quantity_withheld: bool = False,
    unexpected_opening_field: bool = False,
    source_final_schema: str | None = preflight.SOURCE_VISUAL_FINAL_STATE_SCHEMA,
    source_final_withheld_tool: str | None = preflight.LEGACY_SOURCE_WITHHELD_TOOL,
    source_final_database_write: bool | None = False,
    source_final_canonical_write: bool = False,
    source_final_opening_count: int = 0,
    decision_material: object = _SAME,
) -> tuple[Path, Path]:
    source_dir = tmp_path / "source-run"
    adjudicated_dir = tmp_path / "adjudicated-revision"
    source_material = material if source_material is _SAME else source_material
    opening = {
        "opening_code": "O-001",
        "external_defect_id": "D-001",
        "location": "Synthetic location",
        "substrate_type": "concrete",
        "substrate_plane": "wall",
        "orientation": "vertical",
        "opening_type": "service_penetration",
        "frl": "- / 60 / 60",
    }
    source_proposal = {
        "defect_count": 1,
        "supported_defect_count": 1,
        "limited_defect_count": 0,
        "proposed_opening_count": 1,
        "proposed_service_count": 1,
        "openings": [opening],
        "services": [
            {
                "service_code": "S-001",
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "service_type": "pipe",
                "material": source_material,
                "quantity": 1,
                "evidence_status": "observed",
                "relationship_status": "confirmed",
                "link_type": "penetrates",
            }
        ],
        "limitations": [],
    }
    source_proposal_path = _write_json(
        source_dir / "20-fireseal-merged-proposal.json", source_proposal
    )
    historical_path = _write_json(source_dir / "22-human-reference.json", {"status": "MISMATCH"})
    changed = source_material != material
    include_human_decision = (
        changed or quantity_withheld if include_human_decision is _SAME else include_human_decision
    )
    decision_material = material if decision_material is _SAME else decision_material
    decisions = (
        [
            {
                "external_defect_id": "D-001",
                "decision": "MATERIAL_CORRECTION",
                "openings": [
                    {
                        "classification": "service_penetration",
                        "substrate_type": "concrete",
                        "substrate_plane": "wall",
                        "service_groups": [
                            {
                                "service_type": "pipe",
                                "material": decision_material,
                                "quantity": None if quantity_withheld else 1,
                            }
                        ],
                    }
                ],
            }
        ]
        if include_human_decision
        else []
    )
    human_adjudication = {
        "schema": preflight.HUMAN_ADJUDICATION_SCHEMA,
        "estimate_id": estimate_id,
        "run_id": "source-run-001",
        "canonical_write_performed": False,
        "decisions": decisions,
        "comparison_receipt": {
            "path": historical_path.name,
            "sha256": _sha256(historical_path),
        },
    }
    human_path = _write_json(source_dir / "23-human-adjudication-v1.json", human_adjudication)
    source_state = {
        "status": preflight.VISUAL_FINAL_STATE_STATUS,
        "estimate_id": estimate_id,
        "run_id": "source-run-001",
        "proposal_receipt": str(source_proposal_path),
        "withheld_tool": source_final_withheld_tool,
        "canonical_write_performed": source_final_canonical_write,
        "canonical_opening_count": source_final_opening_count,
        "canonical_service_count": 0,
        "canonical_active_lock_count": 0,
        "protected_state": _protected_state(db, estimate_id),
    }
    if source_final_schema is not None:
        source_state["schema"] = source_final_schema
        source_state["database_write_performed"] = source_final_database_write
        source_state["gateway_call_performed"] = True
        source_state["runtime_inference_performed"] = True
    source_state_path = _write_json(
        source_dir / "21-visual-proposal-only-final-state.json",
        source_state,
    )

    generator_inputs = {
        "proposal": source_proposal,
        "proposal_sha256": _sha256(source_proposal_path),
        "source_state": source_state,
        "source_state_sha256": _sha256(source_state_path),
        "adjudication": human_adjudication,
        "adjudication_sha256": _sha256(human_path),
        "adjudication_path": human_path.resolve(),
        "comparison_sha256": _sha256(historical_path),
        "estimate_id": estimate_id,
        "run_id": "source-run-001",
        "protected_state": source_state["protected_state"],
        "openings": source_proposal["openings"],
        "services": source_proposal["services"],
    }
    revision, generated_diff = preflight.build_revision(generator_inputs)
    if changed and not include_human_decision:
        revision["services"][0]["material"] = material
    if unexpected_opening_field:
        revision["openings"][0]["not_permitted"] = "must fail"
    proposal_path = _write_json(adjudicated_dir / preflight.PROPOSAL_FILENAME, revision)
    generated_diff["revision_proposal_sha256"] = _sha256(proposal_path)
    diff_path = _write_json(adjudicated_dir / preflight.DIFF_FILENAME, generated_diff)
    final_path = _write_json(
        adjudicated_dir / preflight.FINAL_STATE_FILENAME,
        {
            "schema": preflight.ADJUDICATED_FINAL_STATE_SCHEMA,
            "status": "ADJUDICATED_PROPOSAL_READY_FOR_HUMAN_REVIEW",
            "estimate_id": estimate_id,
            "run_id": "source-run-001-adjudicated-v1",
            "source_run_id": "source-run-001",
            "proposal_receipt": preflight.PROPOSAL_FILENAME,
            "proposal_sha256": _sha256(proposal_path),
            "source_final_state": {
                "path": str(source_state_path),
                "sha256": _sha256(source_state_path),
            },
            "source_proposal": {
                "path": str(source_proposal_path),
                "sha256": _sha256(source_proposal_path),
            },
            "human_adjudication": {"path": str(human_path), "sha256": _sha256(human_path)},
            "diff_receipt": {"path": preflight.DIFF_FILENAME, "sha256": _sha256(diff_path)},
            "canonical_write_performed": False,
            "database_write_performed": False,
            "gateway_call_performed": False,
            "runtime_inference_performed": False,
            "protected_state": _protected_state(db, estimate_id),
        },
    )
    comparison = preflight.validate_adjudicated_revision(
        proposal=revision,
        adjudication=human_adjudication,
    )
    comparison.update(
        {
            "estimate_id": estimate_id,
            "source_run_id": "source-run-001",
            "canonical_write_performed": False,
            "database_write_performed": False,
            "gateway_call_performed": False,
            "revision_proposal": {
                "path": preflight.PROPOSAL_FILENAME,
                "sha256": _sha256(proposal_path),
            },
            "final_state_receipt": {
                "path": preflight.FINAL_STATE_FILENAME,
                "sha256": _sha256(final_path),
            },
            "human_adjudication": {
                "path": str(human_path),
                "sha256": _sha256(human_path),
            },
        }
    )
    _write_json(adjudicated_dir / preflight.COMPARISON_FILENAME, comparison)
    return source_dir, adjudicated_dir


def _rebind_adjudicated_chain(adjudicated_dir: Path) -> None:
    proposal_path = adjudicated_dir / preflight.PROPOSAL_FILENAME
    diff_path = adjudicated_dir / preflight.DIFF_FILENAME
    final_path = adjudicated_dir / preflight.FINAL_STATE_FILENAME
    comparison_path = adjudicated_dir / preflight.COMPARISON_FILENAME
    diff = json.loads(diff_path.read_text(encoding="utf-8"))
    diff["revision_proposal_sha256"] = _sha256(proposal_path)
    _write_json(diff_path, diff)
    final_state = json.loads(final_path.read_text(encoding="utf-8"))
    final_state["proposal_sha256"] = _sha256(proposal_path)
    final_state["diff_receipt"]["sha256"] = _sha256(diff_path)
    _write_json(final_path, final_state)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["revision_proposal"]["sha256"] = _sha256(proposal_path)
    comparison["final_state_receipt"]["sha256"] = _sha256(final_path)
    _write_json(comparison_path, comparison)


def _visual_topology(*, material: str) -> dict:
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
            }
        ],
        "services": [
            {
                "service_code": "S-001",
                "primary_opening_code": "O-001",
                "opening_codes": ["O-001"],
                "service_type": "pipe",
                "material": material,
                "quantity": 1,
                "link_type": "penetrates",
            }
        ],
    }


def _manifest_entry(
    *,
    index: int,
    requested_photo_id: str,
    candidate_id: str,
    path: Path,
    candidate: dict,
    variant_group_id: str,
    variant_role: str,
    relationship: str,
) -> dict:
    return {
        "attachment_index": index,
        "role": "defect_photo",
        "requested_photo_id": requested_photo_id,
        "candidate_id": candidate_id,
        "photo_id": candidate["photo_id"],
        "page": candidate["page_number"],
        "path": str(path),
        "filename": path.name,
        "variant_group_id": variant_group_id,
        "variant_role": variant_role,
        "primary_secondary": "PRIMARY" if variant_role == "PRIMARY" else "SECONDARY",
        "relationship_to_primary": relationship,
        "provenance": candidate["provenance"],
        "source_resolution": "linked_original",
        "full_resolution_status": "VERIFIED",
        "pixel_width": candidate["width"],
        "pixel_height": candidate["height"],
        "expected_sha256": candidate["file_sha256"].lower(),
    }


def _write_contact_binding(
    *,
    source_dir: Path,
    manifest: list[dict],
    image_variant_sha256: str,
) -> dict:
    contact_path = source_dir / "photo-contact-sheets" / "defect-001.png"
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    contact_path.write_bytes(b"contact-sheet")
    detail_entries = [entry for entry in manifest if entry["role"] == "defect_photo"]
    binding_path = source_dir / "photo-contact-sheets" / "defect-001-binding.json"
    binding = {
        "binding": {
            "policy_version": "CLASSIFIRE-PHOTO-VISUAL-v2-HIGHEST-USABLE-DETAIL",
            "image_variant_receipt_sha256": image_variant_sha256,
            "contact_thumbnail": [900, 650],
            "inputs": [
                {
                    "label": f"{entry['photo_id']} [{entry['variant_role']}]",
                    "filename": entry["filename"],
                    "sha256": entry["expected_sha256"],
                }
                for entry in detail_entries
            ],
        },
        "output_sha256": _sha256(contact_path),
    }
    _write_json(binding_path, binding)
    return {
        "attachment_index": len(manifest) + 1,
        "role": "contact_sheet",
        "path": str(contact_path),
        "filename": contact_path.name,
        "expected_sha256": _sha256(contact_path).lower(),
        "candidate_id": None,
        "primary_secondary": "SECONDARY",
        "relationship_to_primary": "MULTI_IMAGE_CONTEXT",
    }


def test_preflight_binds_artifacts_and_withholds_lock_for_known_uncertainty(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path, db, estimate.id, material=None, quantity_withheld=True
    )

    receipt = preflight.build_preflight(
        db,
        source_run_dir=source_dir,
        adjudicated_dir=adjudicated_dir,
        estimate_id=estimate.id,
    )

    assert receipt["status"] == "PRECHECK_PASSED_SIGNED_ADMISSION_REQUIRED"
    assert receipt["candidate_eligible"] is True
    assert receipt["submission_eligible"] is False
    assert receipt["lock_eligible"] is False
    assert receipt["projected_lock_eligible"] is False
    assert receipt["canonical_counts"]["openings"] == 0
    assert receipt["projected_topology"]["unknown_material_service_codes"] == ["A-D-001-S-01-01"]
    assert receipt["projected_topology"]["quantity_withheld_opening_codes"] == ["A-D-001-O-01"]
    assert set(receipt["implementation"]) == {
        "preflight_script_sha256",
        *controlled_writer_implementation_hashes(),
    }
    assert db.query(Defect).filter(Defect.estimate_id == estimate.id).count() == 1


def test_preflight_rejects_protected_state_drift(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id)
    estimate.title = "Changed after adjudication"
    db.commit()

    with pytest.raises(preflight.CanonicalisationPreflightError, match="fingerprint"):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_unexpected_payload_field(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_material="STEEL",
        unexpected_opening_field=True,
    )

    proposal = json.loads(
        (adjudicated_dir / preflight.PROPOSAL_FILENAME).read_text(encoding="utf-8")
    )
    with pytest.raises(preflight.CanonicalisationPreflightError, match="unexpected fields"):
        preflight._normalised_payload(proposal, known_defect_ids={"D-001"})


def test_preflight_rejects_topology_change_without_human_decision(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_material="STEEL",
        include_human_decision=False,
    )

    with pytest.raises(
        preflight.CanonicalisationPreflightError, match="exactly one human decision"
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_marks_only_actual_human_topology_change_as_override(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id, source_material="STEEL")

    receipt = preflight.build_preflight(
        db,
        source_run_dir=source_dir,
        adjudicated_dir=adjudicated_dir,
        estimate_id=estimate.id,
    )

    assert receipt["visual_adjudication_basis"]["per_defect"] == [
        {
            "external_defect_id": "D-001",
            "evidence_basis": "VISUAL_EVIDENCE_PLUS_HUMAN_ADJUDICATED_OVERRIDE",
        }
    ]


def test_preflight_rejects_human_decision_with_wrong_semantic_topology(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_material="STEEL",
        decision_material="STEEL",
    )
    proposal_path = adjudicated_dir / preflight.PROPOSAL_FILENAME
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["services"][0]["material"] = "PVC"
    _write_json(proposal_path, proposal)
    _rebind_adjudicated_chain(adjudicated_dir)

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="not produced by the bound human-decision revision",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_stale_human_comparison_semantics(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_material="STEEL",
    )
    comparison_path = adjudicated_dir / preflight.COMPARISON_FILENAME
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
    comparison["defects"][0]["issues"] = ["Stale comparison detail."]
    _write_json(comparison_path, comparison)

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="regenerated human-decision semantics",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_extra_physical_mutation_in_human_changed_defect(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_material="STEEL",
    )
    proposal_path = adjudicated_dir / preflight.PROPOSAL_FILENAME
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["openings"][0]["width_mm"] = 999
    proposal["openings"][0]["opening_type"] = "unmeasured_rectangular_service_opening"
    _write_json(proposal_path, proposal)
    _rebind_adjudicated_chain(adjudicated_dir)

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="not produced by the bound human-decision revision",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_visual_model_source_match_rejects_same_count_material_change() -> None:
    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="does not semantically bind",
    ):
        preflight._require_visual_model_source_semantic_match(
            source_proposal=_visual_topology(material="PVC"),
            model=_visual_topology(material="STEEL"),
            external_defect_id="D-001",
            defect_index=1,
        )


def test_preflight_accepts_only_narrow_legacy_source_final_receipt(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_final_schema=None,
    )

    receipt = preflight.build_preflight(
        db,
        source_run_dir=source_dir,
        adjudicated_dir=adjudicated_dir,
        estimate_id=estimate.id,
    )

    assert (
        receipt["visual_adjudication_basis"]["source_final_receipt_contract"]
        == "LEGACY_SCHEMALESS_WITHHELD_TOOL_V0"
    )


def test_preflight_rejects_schema_less_source_final_without_withheld_tool(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_final_schema=None,
        source_final_withheld_tool=None,
    )

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="withheld canonical-write tool",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_source_visual_database_write_claim(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(
        tmp_path,
        db,
        estimate.id,
        source_final_database_write=True,
    )

    with pytest.raises(preflight.CanonicalisationPreflightError, match="database_write_performed"):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"source_final_canonical_write": True}, "canonical_write_performed"),
        ({"source_final_opening_count": 1}, "canonical_opening_count"),
    ],
)
def test_preflight_rejects_source_visual_write_or_nonempty_canonical_claim(
    tmp_path: Path,
    kwargs: dict,
    message: str,
) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id, **kwargs)

    with pytest.raises(preflight.CanonicalisationPreflightError, match=message):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_attachment_manifest_requires_exact_model_visible_detail_order(tmp_path: Path) -> None:
    source_dir = tmp_path / "source-run"
    source_dir.mkdir()
    image_variant_sha256 = "B" * 64
    paths = []
    candidates = []
    for index, photo_id in enumerate(("P-001", "P-002"), start=1):
        path = source_dir / f"{photo_id}.jpg"
        path.write_bytes(f"photo-{index}".encode("ascii"))
        paths.append(path.resolve())
        candidates.append(
            {
                "photo_id": photo_id,
                "page_number": 1,
                "provenance": "REPORT_LINKED_ORIGINAL",
                "file_sha256": _sha256(path),
                "width": 3024,
                "height": 4032,
            }
        )
    expected_sequence = [("P-001", "C-001"), ("P-002", "C-002")]
    permitted = {
        ("P-001", "C-001"): {
            "candidate": candidates[0],
            "path": paths[0],
            "variant_group_id": "G-001",
            "variant_role": "PRIMARY",
            "primary_secondary": "PRIMARY",
            "relationship_to_primary": "SELF",
        },
        ("P-002", "C-002"): {
            "candidate": candidates[1],
            "path": paths[1],
            "variant_group_id": "G-002",
            "variant_role": "MANDATORY_SECONDARY",
            "primary_secondary": "SECONDARY",
            "relationship_to_primary": "CROP_VARIANT",
        },
    }
    manifest = [
        _manifest_entry(
            index=1,
            requested_photo_id="P-001",
            candidate_id="C-001",
            path=paths[0],
            candidate=candidates[0],
            variant_group_id="G-001",
            variant_role="PRIMARY",
            relationship="SELF",
        ),
        _manifest_entry(
            index=2,
            requested_photo_id="P-002",
            candidate_id="C-002",
            path=paths[1],
            candidate=candidates[1],
            variant_group_id="G-002",
            variant_role="MANDATORY_SECONDARY",
            relationship="CROP_VARIANT",
        ),
    ]
    manifest.append(
        _write_contact_binding(
            source_dir=source_dir,
            manifest=manifest,
            image_variant_sha256=image_variant_sha256,
        )
    )
    inventory = {
        "P-001": {"full_resolution_status": "VERIFIED"},
        "P-002": {"full_resolution_status": "VERIFIED"},
    }

    preflight._validate_defect_attachment_manifest(
        source_run_dir=source_dir,
        defect_index=1,
        manifest=manifest,
        expected_detail_sequence=expected_sequence,
        permitted_candidates=permitted,
        requested_photo_ids=["P-001", "P-002"],
        expected_pages=set(),
        inventory_by_photo_id=inventory,
        image_variant_sha256=image_variant_sha256,
    )

    reversed_manifest = [
        {**manifest[1], "attachment_index": 1},
        {**manifest[0], "attachment_index": 2},
    ]
    reversed_manifest.append(
        _write_contact_binding(
            source_dir=source_dir,
            manifest=reversed_manifest,
            image_variant_sha256=image_variant_sha256,
        )
    )
    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="does not cover exactly the selected detail evidence",
    ):
        preflight._validate_defect_attachment_manifest(
            source_run_dir=source_dir,
            defect_index=1,
            manifest=reversed_manifest,
            expected_detail_sequence=expected_sequence,
            permitted_candidates=permitted,
            requested_photo_ids=["P-001", "P-002"],
            expected_pages=set(),
            inventory_by_photo_id=inventory,
            image_variant_sha256=image_variant_sha256,
        )


def test_linked_inventory_materialization_requires_exact_item_binding() -> None:
    inventory_row = {
        "photo_id": "P-001",
        "page_number": 1,
        "occurrence": 1,
        "full_resolution_required": True,
        "full_resolution_status": "VERIFIED",
        "full_resolution_path": "photo-linked/by-sha256/aa/photo.jpg",
        "full_resolution_sha256": "A" * 64,
        "full_resolution_width": 3024,
        "full_resolution_height": 4032,
        "full_resolution_binding_transform": "CENTER_CROP_COVER",
        "full_resolution_binding_crop_box": [0, 0, 1, 1],
        "full_resolution_embedded_pixel_sha256": "B" * 64,
        "full_resolution_usable_detail_gradient_gain_ratio": 2.0,
        "full_resolution_usable_detail_residual": 0.01,
        "full_resolution_usable_detail_matching_tiles": 16,
    }
    linked_inventory = {"photo_occurrence_count": 1, "photos": [inventory_row]}
    items = [
        {
            "photo_id": "P-001",
            "page_number": 1,
            "full_resolution_required": True,
            "status": "VERIFIED",
            "stored_path": "photo-linked/by-sha256/aa/photo.jpg",
            "content_sha256": "A" * 64,
            "decoded_width": 3024,
            "decoded_height": 4032,
            "thumbnail_transform": "CENTER_CROP_COVER",
            "thumbnail_crop_box_normalized": [0, 0, 1, 1],
            "embedded_pixel_sha256": "B" * 64,
            "usable_detail_gradient_gain_ratio": 2.0,
            "usable_detail_residual": 0.01,
            "usable_detail_matching_tiles": 16,
        }
    ]
    materialization = {"photo_occurrence_count": 1, "items": items}
    inventory_by_photo_id = preflight._linked_inventory_by_photo_id(linked_inventory)

    preflight._validate_linked_materialization_items(
        linked_inventory=linked_inventory,
        materialization=materialization,
        inventory_by_photo_id=inventory_by_photo_id,
    )

    items[0]["content_sha256"] = "C" * 64
    with pytest.raises(preflight.CanonicalisationPreflightError, match="full_resolution_sha256"):
        preflight._validate_linked_materialization_items(
            linked_inventory=linked_inventory,
            materialization=materialization,
            inventory_by_photo_id=inventory_by_photo_id,
        )


def test_preflight_rejects_historical_lock_descendant(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    historical_lock = PhysicalModelLock(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        defect_ids=[],
        evidence_hashes=[],
        service_ids=["historical-service"],
        opening_ids=["historical-opening"],
        validator_result="APPROVED",
        content_hash="C" * 64,
        invalidated_at=datetime.now(timezone.utc),
    )
    db.add(historical_lock)
    db.flush()
    db.add(
        RepairStrategy(
            opening_id="different-opening-bound-only-through-lock-id",
            physical_model_lock_id=historical_lock.id,
        )
    )
    db.commit()
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id)

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="historical_lock_repair_strategy_count",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_orphaned_historical_lock_reconciliation(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    historical_lock = PhysicalModelLock(
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        defect_ids=[],
        evidence_hashes=[],
        service_ids=["historical-service"],
        opening_ids=["historical-opening"],
        validator_result="APPROVED",
        content_hash="D" * 64,
        invalidated_at=datetime.now(timezone.utc),
    )
    db.add(historical_lock)
    db.flush()
    db.add(
        ComponentRequirementReconciliation(
            opening_id="historical-opening",
            required_component_id="orphaned-historical-component",
            result="unreconciled",
        )
    )
    db.commit()
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id)

    with pytest.raises(
        preflight.CanonicalisationPreflightError,
        match="historical_lock_component_reconciliation_count",
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_failure_receipt_explicitly_withholds_all_eligibility() -> None:
    receipt = preflight._failure_receipt(
        estimate_id="DRAFT-ESTIMATE",
        error=preflight.CanonicalisationPreflightError("Blocked for test."),
    )

    assert receipt["status"] == "BLOCKED"
    assert receipt["candidate_eligible"] is False
    assert receipt["submission_eligible"] is False
    assert receipt["lock_eligible"] is False
    assert receipt["projected_lock_eligible"] is False
    assert receipt["controlled_writer_implemented"] is True


def test_preflight_requires_production_full_resolution_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id)
    monkeypatch.setattr(
        preflight,
        "_validate_full_resolution_visual_evidence",
        _PRODUCTION_VISUAL_REVALIDATOR,
    )

    with pytest.raises(preflight.CanonicalisationPreflightError, match="Prepared source receipt"):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_rejects_downstream_approval(tmp_path: Path) -> None:
    db = _session()
    estimate = _seed(db)
    source_dir, adjudicated_dir = _artifacts(tmp_path, db, estimate.id)
    db.add(
        Approval(
            entity_type="estimate",
            entity_id=estimate.id,
            approval_type="technical",
            status="pending",
        )
    )
    db.commit()

    with pytest.raises(
        preflight.CanonicalisationPreflightError, match="Downstream estimate records"
    ):
        preflight.build_preflight(
            db,
            source_run_dir=source_dir,
            adjudicated_dir=adjudicated_dir,
            estimate_id=estimate.id,
        )


def test_preflight_receipt_write_refuses_to_overwrite(tmp_path: Path) -> None:
    payload = {"schema": preflight.PREFLIGHT_SCHEMA, "status": "BLOCKED"}
    output_dir = tmp_path / "fresh-receipt"
    destination = preflight._write_new_json(output_dir, payload)

    assert destination.read_text(encoding="utf-8")
    with pytest.raises(preflight.CanonicalisationPreflightError, match="fresh namespace"):
        preflight._write_new_json(output_dir, payload)


def test_preflight_fingerprint_matches_the_existing_uat_guard() -> None:
    import run_classifire_real_uat_fireseals_visualvalidated_proposal_only as legacy_guard

    db = _session()
    estimate = _seed(db)

    current_snapshot = protected_state_snapshot_from_session(db, estimate.id)
    legacy_snapshot = legacy_guard._protected_state_snapshot_from_session(db, estimate.id)

    assert current_snapshot == legacy_snapshot
    assert protected_state_fingerprint(
        current_snapshot
    ) == legacy_guard._protected_state_fingerprint(legacy_snapshot)
    assert protected_component_fingerprints(
        current_snapshot
    ) == legacy_guard._protected_component_fingerprints(legacy_snapshot)
    assert protected_state_counts(current_snapshot) == legacy_guard._protected_state_counts(
        legacy_snapshot
    )
