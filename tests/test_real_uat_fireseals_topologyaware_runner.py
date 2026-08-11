from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals_topologyaware import (  # noqa: E402
    TOPOLOGY_POLICY_VERSION,
    TopologyAwareFireSealController,
)


def test_topology_policy_is_direct_image_and_newer_than_blankaware() -> None:
    assert "DIRECT-IMAGE-TOPOLOGY" in TOPOLOGY_POLICY_VERSION
    assert "_visual_files_for_defect" in TopologyAwareFireSealController.__dict__
    assert "_synthesise_defect" in TopologyAwareFireSealController.__dict__


def test_runner_forbids_one_opening_per_service_and_supports_mixed_services() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    assert "NEVER create one Opening per Service type" in source
    assert "Multiple unlike Services may share one Opening" in source
    assert "cable_bundle" in source
    assert "conduit" in source
    assert "flexible_duct" in source
    assert "aircon_bundle" in source
    assert "two similar PEX pipes" in source


def test_runtime_does_not_read_human_answer_fixture() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    forbidden = "real_uat_20260809_human_physical_reference"
    assert forbidden not in source
    assert "tests/fixtures" not in source
    assert "PRIMARY evidence" in source


def test_topology_stage_passes_actual_visual_files_to_model() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals_topologyaware.py").read_text(
        encoding="utf-8"
    )
    assert "files=files" in source
    assert "photo-zoom" in source
    assert "photo-layout-labelled" in source
    assert "photo-contact-sheets" in source
