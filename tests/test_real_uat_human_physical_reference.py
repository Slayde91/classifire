from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "fixtures" / "real_uat_20260809_human_physical_reference.json"
RUNTIME = ROOT / "scripts" / "run_classifire_real_uat_fireseals_topologyaware.py"
SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import validate_real_uat_human_physical_reference as validator  # noqa: E402


def test_human_reference_has_all_ten_reviewed_defects() -> None:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    defects = payload["defects"]
    assert len(defects) == 10
    assert {row["external_defect_id"] for row in defects} == {
        "147038",
        "147039",
        "147046",
        "147031",
        "147037",
        "147042",
        "147044",
        "147045",
        "147047",
        "147192",
    }
    assert sum(int(row["opening_count"]) for row in defects) == 17


def test_human_reference_is_validation_only_not_runtime_input() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert REFERENCE.name not in source
    assert "tests/fixtures" not in source
    assert "human_physical_reference" not in source


def test_proposal_mode_compares_without_reading_canonical_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    reference_path.write_text(
        json.dumps(
            {
                "defects": [
                    {
                        "external_defect_id": "D-001",
                        "opening_count": 1,
                        "openings": [
                            {
                                "substrate": "concrete slab",
                                "blank": False,
                                "service_groups": [
                                    {
                                        "type": "pipe",
                                        "material": "PVC",
                                        "quantity": 1,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {
                "openings": [
                    {
                        "external_defect_id": "D-001",
                        "opening_code": "O-001",
                        "opening_type": "service_penetration",
                        "substrate_type": "concrete",
                        "substrate_plane": "slab",
                        "orientation": "horizontal",
                    }
                ],
                "services": [
                    {
                        "service_code": "S-001",
                        "service_type": "pipe",
                        "material": "PVC",
                        "quantity": 1,
                        "primary_opening_code": "O-001",
                        "opening_codes": ["O-001"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "SessionLocal",
        lambda: pytest.fail("proposal mode must not read canonical database rows"),
    )

    result = validator.validate(
        estimate_id="estimate-test",
        reference_path=reference_path,
        proposal_path=proposal_path,
    )

    assert result["status"] == "PASS"
    assert result["schema"] == "CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-VALIDATION-v3"
    assert result["passed_defect_count"] == 1
    assert result["comparison_source"] == {
        "kind": "proposal",
        "path": str(proposal_path.resolve()),
        "sha256": hashlib.sha256(proposal_path.read_bytes()).hexdigest().upper(),
        "final_state_receipt": None,
    }
    assert result["estimate_id_source"] == "caller_supplied"
    assert (
        result["reference_sha256"]
        == hashlib.sha256(reference_path.read_bytes()).hexdigest().upper()
    )
    assert len(result["validator_sha256"]) == 64

    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal["openings"][0].update(
        {
            "substrate_type": "wall",
            "substrate_plane": "wall",
            "orientation": "vertical",
        }
    )
    proposal["services"][0].update(
        {
            "service_type": "other",
            "material": None,
        }
    )
    proposal_path.write_text(
        json.dumps(proposal),
        encoding="utf-8",
    )

    mismatch = validator.validate(
        estimate_id="estimate-test",
        reference_path=reference_path,
        proposal_path=proposal_path,
    )
    issues = mismatch["defects"][0]["issues"]

    assert mismatch["status"] == "MISMATCH"
    assert any("topology differs" in issue for issue in issues)
    assert any("no current opening supports expected substrate" in issue for issue in issues)


def test_proposal_mode_fails_closed_for_unknown_opening_reference(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    reference_path.write_text(
        json.dumps({"defects": []}),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {
                "openings": [],
                "services": [
                    {
                        "service_code": "S-001",
                        "service_type": "pipe",
                        "quantity": 1,
                        "primary_opening_code": "O-MISSING",
                        "opening_codes": ["O-MISSING"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        RuntimeError,
        match="unknown opening O-MISSING",
    ):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
        )


def test_substrate_must_match_the_same_opening_service_topology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_path = tmp_path / "reference.json"
    reference_path.write_text(
        json.dumps(
            {
                "defects": [
                    {
                        "external_defect_id": "D-001",
                        "opening_count": 2,
                        "openings": [
                            {
                                "substrate": "concrete slab",
                                "blank": False,
                                "service_groups": [
                                    {"type": "pipe", "material": "PVC", "quantity": 1}
                                ],
                            },
                            {
                                "substrate": "block wall",
                                "blank": False,
                                "service_groups": [
                                    {"type": "cable", "material": None, "quantity": 1}
                                ],
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        validator,
        "_canonical_openings_by_external",
        lambda _estimate_id: {
            "D-001": [
                {
                    "opening_code": "O-PIPE",
                    "blank": False,
                    "substrate_type": "block",
                    "substrate_plane": "wall",
                    "orientation": "vertical",
                    "service_groups": [{"service_type": "pipe", "material": "PVC", "quantity": 1}],
                },
                {
                    "opening_code": "O-CABLE",
                    "blank": False,
                    "substrate_type": "concrete",
                    "substrate_plane": "slab",
                    "orientation": "horizontal",
                    "service_groups": [{"service_type": "cable", "material": None, "quantity": 1}],
                },
            ]
        },
    )

    result = validator.validate(
        estimate_id="estimate-test",
        reference_path=reference_path,
    )

    assert result["status"] == "MISMATCH"
    assert result["comparison_source"] == {"kind": "canonical_database"}
    issues = result["defects"][0]["issues"]
    assert not any("topology differs" in issue for issue in issues)
    assert sum("within matching service topology" in issue for issue in issues) == 2


@pytest.mark.parametrize(
    ("proposal", "message"),
    [
        ({"openings": {}, "services": []}, "openings must be a list"),
        ({"openings": [], "services": {}}, "services must be a list"),
        (
            {
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
                        "quantity": 1,
                        "opening_codes": "O-001",
                    }
                ],
            },
            "opening_codes must be a list",
        ),
    ],
)
def test_proposal_mode_rejects_malformed_collection_types(
    tmp_path: Path,
    proposal: dict[str, object],
    message: str,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    reference_path.write_text(json.dumps({"defects": []}), encoding="utf-8")
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")

    with pytest.raises(RuntimeError, match=message):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
        )


def test_proposal_mode_reports_external_defect_absent_from_reference(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    reference_path.write_text(json.dumps({"defects": []}), encoding="utf-8")
    proposal_path.write_text(
        json.dumps(
            {
                "openings": [
                    {
                        "external_defect_id": "D-EXTRA",
                        "opening_code": "O-EXTRA",
                        "opening_type": "blank_opening",
                    }
                ],
                "services": [],
            }
        ),
        encoding="utf-8",
    )

    result = validator.validate(
        estimate_id="estimate-test",
        reference_path=reference_path,
        proposal_path=proposal_path,
    )

    assert result["status"] == "MISMATCH"
    assert result["defect_count"] == 1
    assert result["mismatch_defect_count"] == 1
    assert result["defects"][0]["external_defect_id"] == "D-EXTRA"
    assert "absent from the human reference" in result["defects"][0]["issues"][0]


def test_proposal_mode_maps_one_service_to_multiple_openings(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    reference_path.write_text(
        json.dumps(
            {
                "defects": [
                    {
                        "external_defect_id": "D-001",
                        "opening_count": 2,
                        "openings": [
                            {
                                "substrate": None,
                                "blank": False,
                                "service_groups": [
                                    {"type": "pipe", "material": "PVC", "quantity": 1}
                                ],
                            },
                            {
                                "substrate": None,
                                "blank": False,
                                "service_groups": [
                                    {"type": "pipe", "material": "PVC", "quantity": 1}
                                ],
                            },
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps(
            {
                "openings": [
                    {
                        "external_defect_id": "D-001",
                        "opening_code": "O-001",
                        "opening_type": "service_penetration",
                    },
                    {
                        "external_defect_id": "D-001",
                        "opening_code": "O-002",
                        "opening_type": "service_penetration",
                    },
                ],
                "services": [
                    {
                        "service_code": "S-001",
                        "service_type": "pipe",
                        "material": "PVC",
                        "quantity": 1,
                        "primary_opening_code": "O-001",
                        "opening_codes": ["O-001", "O-002"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validator.validate(
        estimate_id="estimate-test",
        reference_path=reference_path,
        proposal_path=proposal_path,
    )

    assert result["status"] == "PASS"
    assert result["passed_defect_count"] == 1


def test_cli_writes_bound_mismatch_receipt_and_returns_two(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    proposal_state_path = tmp_path / "final-state.json"
    output_path = tmp_path / "comparison.json"
    reference_path.write_text(
        json.dumps(
            {
                "run_id": "run-test",
                "defects": [
                    {
                        "external_defect_id": "D-001",
                        "opening_count": 1,
                        "openings": [{"substrate": None, "blank": True, "service_groups": []}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps({"openings": [], "services": []}),
        encoding="utf-8",
    )
    proposal_state_path.write_text(
        json.dumps(
            {
                "run_id": "run-test",
                "estimate_id": "estimate-test",
                "proposal_receipt": str(proposal_path.resolve()),
                "canonical_write_performed": False,
                "protected_state": {
                    "before_fingerprint": "A" * 64,
                    "after_fingerprint": "A" * 64,
                    "protected_state_unchanged": True,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "validate_real_uat_human_physical_reference.py",
            "--estimate-id",
            "estimate-test",
            "--reference",
            str(reference_path),
            "--proposal",
            str(proposal_path),
            "--proposal-state",
            str(proposal_state_path),
            "--output",
            str(output_path),
        ],
    )

    exit_code = validator.main()
    printed = json.loads(capsys.readouterr().out)
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert exit_code == 2
    assert saved == printed
    assert saved["status"] == "MISMATCH"
    assert saved["schema"] == "CLASSIFIRE-HUMAN-PHYSICAL-REFERENCE-VALIDATION-v3"
    assert saved["reference_run_id"] == "run-test"
    assert saved["estimate_id_source"] == "proposal_final_state_receipt"
    assert saved["comparison_source"]["final_state_receipt"] == {
        "path": str(proposal_state_path.resolve()),
        "sha256": hashlib.sha256(proposal_state_path.read_bytes()).hexdigest().upper(),
        "run_id": "run-test",
        "estimate_id": "estimate-test",
        "proposal_path_binding": "VERIFIED",
        "proposal_content_binding": "PATH_ONLY",
    }
    assert (
        saved["comparison_source"]["sha256"]
        == hashlib.sha256(proposal_path.read_bytes()).hexdigest().upper()
    )


def test_proposal_state_receipt_must_match_estimate_run_and_path(
    tmp_path: Path,
) -> None:
    reference_path = tmp_path / "reference.json"
    proposal_path = tmp_path / "proposal.json"
    state_path = tmp_path / "final-state.json"
    reference_path.write_text(
        json.dumps({"run_id": "run-test", "defects": []}),
        encoding="utf-8",
    )
    proposal_path.write_text(
        json.dumps({"openings": [], "services": []}),
        encoding="utf-8",
    )
    state = {
        "run_id": "run-test",
        "estimate_id": "wrong-estimate",
        "proposal_receipt": str(proposal_path.resolve()),
        "canonical_write_performed": False,
        "protected_state": {
            "before_fingerprint": "A" * 64,
            "after_fingerprint": "A" * 64,
            "protected_state_unchanged": True,
        },
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")

    with pytest.raises(RuntimeError, match="estimate_id does not match"):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
            proposal_state_path=state_path,
        )

    state["estimate_id"] = "estimate-test"
    state["run_id"] = "different-run"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="run_id does not match"):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
            proposal_state_path=state_path,
        )

    state["run_id"] = "run-test"
    state["proposal_receipt"] = str((tmp_path / "different-proposal.json").resolve())
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="proposal_receipt does not match"):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
            proposal_state_path=state_path,
        )

    state["proposal_receipt"] = str(proposal_path.resolve())
    state["protected_state"].pop("before_fingerprint")
    state["protected_state"].pop("after_fingerprint")
    state_path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="before_fingerprint must be a 64-character"):
        validator.validate(
            estimate_id="estimate-test",
            reference_path=reference_path,
            proposal_path=proposal_path,
            proposal_state_path=state_path,
        )
