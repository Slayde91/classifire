from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "tests" / "fixtures" / "real_uat_20260809_human_physical_reference.json"
RUNTIME = ROOT / "scripts" / "run_classifire_real_uat_fireseals_topologyaware.py"


def test_human_reference_has_all_ten_reviewed_defects() -> None:
    payload = json.loads(REFERENCE.read_text(encoding="utf-8"))
    defects = payload["defects"]
    assert len(defects) == 10
    assert {row["external_defect_id"] for row in defects} == {
        "147038", "147039", "147046", "147031", "147037",
        "147042", "147044", "147045", "147047", "147192",
    }
    assert sum(int(row["opening_count"]) for row in defects) == 17


def test_human_reference_is_validation_only_not_runtime_input() -> None:
    source = RUNTIME.read_text(encoding="utf-8")
    assert REFERENCE.name not in source
    assert "tests/fixtures" not in source
    assert "human_physical_reference" not in source
