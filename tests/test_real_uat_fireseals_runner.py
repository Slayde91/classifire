from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_fireseals import (  # noqa: E402
    MAX_DEFECT_EVIDENCE_CHARS,
    build_bounded_defect_bundle,
)


def _large_text(seed: str, count: int = 80) -> list[str]:
    return [f"{seed}-{index}-" + ("x" * 180) for index in range(count)]


def test_bounded_bundle_does_not_require_ai_reduction() -> None:
    defect = {
        "canonical_defect_id": "defect-1",
        "external_defect_id": "147044",
        "description": "Multiple electrical and plumbing services through wall",
    }
    rows = [
        {
            "type": "defect_text_fact_review",
            "page": "4",
            "physical_facts": _large_text("fact"),
            "uncertainties": _large_text("uncertainty"),
            "services": [
                {"service_type": "electrical", "status": "stated"},
                {"service_type": "plumbing", "status": "stated"},
            ],
        },
        {
            "type": "defect_photo_reconciliation",
            "page": "4",
            "status": "insufficient_evidence",
            "physical_facts": _large_text("photo"),
        },
    ]

    bundle = build_bounded_defect_bundle(defect, rows)
    parsed = json.loads(bundle)

    assert len(bundle) <= MAX_DEFECT_EVIDENCE_CHARS
    assert parsed["defect"]["external_defect_id"] == "147044"
    assert parsed["direct_evidence"]
    assert parsed["rules"]["photo_count_is_not_quantity"] is True


def test_generic_page_and_image_context_is_excluded() -> None:
    defect = {"canonical_defect_id": "defect-1"}
    rows = [
        {"type": "report_page_review", "summary": "generic page"},
        {"type": "report_image_review", "summary": "generic image"},
        {
            "type": "defect_text_fact_review",
            "physical_facts": ["one defect-linked fact"],
        },
    ]

    parsed = json.loads(build_bounded_defect_bundle(defect, rows))
    types = [row["type"] for row in parsed["direct_evidence"]]

    assert types == ["defect_text_fact_review"]


def test_exact_duplicate_photo_details_are_collapsed() -> None:
    defect = {"canonical_defect_id": "defect-1"}
    rows = [
        {
            "type": "defect_photo_detail_review",
            "photo_id": "p1",
            "distinctive_features": ["EXACT_IMAGE_GROUP:digest:abc"],
            "physical_facts": ["view one"],
        },
        {
            "type": "defect_photo_detail_review",
            "photo_id": "p2",
            "distinctive_features": ["EXACT_IMAGE_GROUP:digest:abc"],
            "physical_facts": ["duplicate view"],
        },
    ]

    parsed = json.loads(build_bounded_defect_bundle(defect, rows))
    details = [
        row
        for row in parsed["direct_evidence"]
        if row["type"] == "defect_photo_detail_review"
    ]

    assert len(details) == 1


def test_fireseal_runner_supersedes_uncertain_photo_stop_rule() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals.py").read_text(
        encoding="utf-8"
    )
    assert "supersedes any earlier prompt sentence" in source
    assert "clearly labelled provisional AI best estimate" in source
    assert "Do not double-count uncertain photos" in source
    assert "limited to fire seals and service penetrations" in source


def test_fireseal_runner_has_no_lossy_reduction_call_in_bundle_path() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals.py").read_text(
        encoding="utf-8"
    )
    assert "build_bounded_defect_bundle" in source
    assert "self._reduce_physical_evidence" not in source
    assert "MAX_DEFECT_EVIDENCE_CHARS" in source


def test_fireseal_runner_retains_complete_text_and_photo_stages() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_fireseals.py").read_text(
        encoding="utf-8"
    )
    assert "structured text evidence already complete" in source
    assert "photo reconciliation evidence already complete" in source
    assert "20-fireseal-defect-" in source
    assert "bundle_sha256" in source
