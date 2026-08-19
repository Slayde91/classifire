from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import create_adjudicated_proposal_revision as revision  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _source_state(*, proposal_name: str) -> dict:
    fingerprint = "A" * 64
    return {
        "run_id": "run-source",
        "estimate_id": "estimate-source",
        "proposal_receipt": proposal_name,
        "canonical_write_performed": False,
        "protected_state": {
            "before_fingerprint": fingerprint,
            "after_fingerprint": fingerprint,
            "protected_state_unchanged": True,
        },
    }


def _proposal() -> dict:
    return {
        "defect_count": 2,
        "supported_defect_count": 2,
        "limited_defect_count": 0,
        "proposed_opening_count": 3,
        "proposed_service_count": 3,
        "limitations": [],
        "openings": [
            {
                "external_defect_id": "D-EMPTY",
                "opening_code": "O-EMPTY",
                "opening_type": "service_penetration",
                "substrate_type": "concrete slab",
                "substrate_plane": "floor",
                "orientation": "horizontal",
                "location": "L1",
                "frl": "-/120/120",
            },
            {
                "external_defect_id": "D-EMPTY",
                "opening_code": "O-PIPE",
                "opening_type": "service_penetration",
                "substrate_type": "concrete slab",
                "substrate_plane": "floor",
                "orientation": "horizontal",
                "location": "L1",
                "frl": "-/120/120",
            },
            {
                "external_defect_id": "D-FULL",
                "opening_code": "O-FULL",
                "opening_type": "service_penetration",
                "substrate_type": "wall",
                "substrate_plane": "wall",
                "orientation": "vertical",
                "location": "L2",
                "frl": "-/120/120",
            },
        ],
        "services": [
            {
                "service_code": "S-EMPTY",
                "service_type": "other",
                "quantity": 1,
                "primary_opening_code": "O-EMPTY",
                "opening_codes": ["O-EMPTY"],
            },
            {
                "service_code": "S-PIPE",
                "service_type": "pipe",
                "quantity": 1,
                "primary_opening_code": "O-PIPE",
                "opening_codes": ["O-PIPE"],
            },
            {
                "service_code": "S-FULL",
                "service_type": "other",
                "quantity": 1,
                "primary_opening_code": "O-FULL",
                "opening_codes": ["O-FULL"],
            },
        ],
    }


def _adjudication(*, comparison_sha256: str) -> dict:
    return {
        "schema": revision.ADJUDICATION_SCHEMA,
        "run_id": "run-source",
        "estimate_id": "estimate-source",
        "canonical_write_performed": False,
        "comparison_receipt": {"path": "comparison.json", "sha256": comparison_sha256},
        "decisions": [
            {
                "external_defect_id": "D-EMPTY",
                "status": "HUMAN_CLARIFIED",
                "decision": "EMPTY_CORE_IS_BLANK_OPENING_SEAL",
                "revision_source_opening_code": "O-EMPTY",
            },
            {
                "external_defect_id": "D-FULL",
                "status": "HUMAN_CONFIRMED",
                "decision": "TWO_OPENING_TOPOLOGY",
                "openings": [
                    {"classification": "blank_opening_seal", "service_groups": []},
                    {
                        "classification": "service_penetration",
                        "substrate_type": "block wall",
                        "substrate_plane": "wall",
                        "service_groups": [
                            {
                                "service_type": "air_duct",
                                "quantity": 1,
                            },
                            {
                                "service_type": "cable_group",
                                "quantity": None,
                                "quantity_status": "WITHHELD",
                            },
                        ],
                    },
                ],
            },
        ],
    }


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    proposal_path = tmp_path / "proposal.json"
    state_path = tmp_path / "state.json"
    comparison_path = tmp_path / "comparison.json"
    adjudication_path = tmp_path / "adjudication.json"
    _write_json(proposal_path, _proposal())
    _write_json(state_path, _source_state(proposal_name=proposal_path.name))
    _write_json(comparison_path, {"status": "MISMATCH"})
    _write_json(adjudication_path, _adjudication(comparison_sha256=_sha256(comparison_path)))
    return proposal_path, state_path, adjudication_path


def test_create_revision_is_offline_provenance_bound_and_preserves_source(tmp_path: Path) -> None:
    proposal_path, state_path, adjudication_path = _paths(tmp_path)
    original_proposal_bytes = proposal_path.read_bytes()
    output_dir = tmp_path / "adjudicated-v1"

    result = revision.create_revision(
        proposal_path=proposal_path,
        source_state_path=state_path,
        adjudication_path=adjudication_path,
        output_dir=output_dir,
    )

    assert result["status"] == "PASS"
    assert result["canonical_write_performed"] is False
    assert result["database_write_performed"] is False
    assert result["gateway_call_performed"] is False
    assert proposal_path.read_bytes() == original_proposal_bytes
    created = json.loads((output_dir / revision.PROPOSAL_FILENAME).read_text(encoding="utf-8"))
    assert created["schema"] == revision.REVISION_SCHEMA
    assert created["proposed_opening_count"] == 4
    assert created["proposed_service_count"] == 3
    empty = next(row for row in created["openings"] if row["opening_code"] == "O-EMPTY")
    assert empty["opening_type"] == "blank_core_hole"
    assert all("O-EMPTY" not in row["opening_codes"] for row in created["services"])
    full_services = [
        row for row in created["services"] if row["primary_opening_code"] == "A-D-FULL-O-02"
    ]
    assert {(row["service_type"], row["quantity"]) for row in full_services} == {
        ("flexible_duct", 1),
        ("cable_bundle", 1),
    }
    assert any(
        row["status"] == "QUANTITY_WITHHELD" for row in created["adjudication_withheld_details"]
    )
    final_state = json.loads(
        (output_dir / revision.FINAL_STATE_FILENAME).read_text(encoding="utf-8")
    )
    assert final_state["proposal_sha256"] == _sha256(output_dir / revision.PROPOSAL_FILENAME)
    assert final_state["protected_state"]["before_fingerprint"] == "A" * 64
    validation = json.loads((output_dir / revision.VALIDATION_FILENAME).read_text(encoding="utf-8"))
    assert validation["status"] == "PASS"


def test_refuses_tampered_comparison_binding_without_creating_output(tmp_path: Path) -> None:
    proposal_path, state_path, adjudication_path = _paths(tmp_path)
    payload = json.loads(adjudication_path.read_text(encoding="utf-8"))
    payload["comparison_receipt"]["sha256"] = "B" * 64
    _write_json(adjudication_path, payload)
    output_dir = tmp_path / "adjudicated-v1"

    with pytest.raises(revision.AdjudicatedProposalError, match="do not match"):
        revision.create_revision(
            proposal_path=proposal_path,
            source_state_path=state_path,
            adjudication_path=adjudication_path,
            output_dir=output_dir,
        )

    assert not output_dir.exists()


def test_refuses_source_directory_as_output_namespace(tmp_path: Path) -> None:
    proposal_path, state_path, adjudication_path = _paths(tmp_path)

    with pytest.raises(revision.AdjudicatedProposalError, match="fresh revision namespace"):
        revision.create_revision(
            proposal_path=proposal_path,
            source_state_path=state_path,
            adjudication_path=adjudication_path,
            output_dir=proposal_path.parent,
        )
