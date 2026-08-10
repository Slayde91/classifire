from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_integrated import (  # noqa: E402
    IntegratedEvidenceController,
    TEXT_FACT_EVIDENCE_TYPE,
)


def test_structured_text_evidence_type_and_fields_are_present() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_integrated.py").read_text(encoding="utf-8")
    assert TEXT_FACT_EVIDENCE_TYPE == "defect_text_fact_review"
    for required in (
        '"frl|substrate_type|substrate_plane|orientation|service_type|service_material|service_size|location|opening_type|other"',
        '"service_count|opening_count|item_count|treatment_count|other"',
        '"treatment_clues"',
        '"authority": "clue_only"',
        "Proposed-resolution wording is not proof",
    ):
        assert required in source


def test_text_merge_preserves_distinct_quantity_kinds() -> None:
    controller = object.__new__(IntegratedEvidenceController)
    result = controller._merge_text_analyses(
        [
            {
                "association_status": "SUPPORTED",
                "confidence": 0.9,
                "attributes": [
                    {
                        "name": "frl",
                        "value": "-/120/120",
                        "status": "stated",
                        "source_role": "defect_row",
                        "basis": "FRL -/120/120",
                    }
                ],
                "quantities": [
                    {
                        "kind": "opening_count",
                        "value": 2,
                        "unit": "core holes",
                        "status": "stated",
                        "source_role": "proposed_resolution",
                        "basis": "two core holes",
                    }
                ],
                "services": [],
                "treatment_clues": [],
                "technical_details": [],
                "physical_facts": [],
                "uncertainties": [],
            },
            {
                "association_status": "AMBIGUOUS",
                "confidence": 0.6,
                "attributes": [],
                "quantities": [
                    {
                        "kind": "service_count",
                        "value": 1,
                        "unit": "pipe",
                        "status": "inferred",
                        "source_role": "description",
                        "basis": "one described pipe",
                    }
                ],
                "services": [],
                "treatment_clues": [],
                "technical_details": [],
                "physical_facts": [],
                "uncertainties": [],
            },
        ],
        3,
    )
    assert result["association_status"] == "SUPPORTED"
    assert {row["kind"] for row in result["quantities"]} == {"opening_count", "service_count"}
    assert result["attributes"][0]["value"] == "-/120/120"


def test_exact_duplicate_visual_key_collapses_same_digest() -> None:
    first = {"photo_id": "P001-I01", "digest": "abc123"}
    second = {"photo_id": "P004-I03", "digest": "abc123"}
    third = {"photo_id": "P004-I04", "digest": "xyz999"}
    assert IntegratedEvidenceController._visual_key(first) == IntegratedEvidenceController._visual_key(second)
    assert IntegratedEvidenceController._visual_key(first) != IntegratedEvidenceController._visual_key(third)


def test_duplicate_and_multi_angle_counting_safeguards_are_explicit() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_integrated.py").read_text(encoding="utf-8")
    photo_source = (SCRIPTS / "run_classifire_real_uat_photoaware.py").read_text(encoding="utf-8")
    assert "EXACT_DUPLICATE_OF:" in source
    assert "exact-image de-duplication" in source
    assert "same_service_opposite_barrier_side" in photo_source
    assert "same_opening_opposite_barrier_side" in photo_source
    assert "Photograph count NEVER equals service count or opening count" in photo_source


def test_gateway_timeout_is_recoverable_once() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_integrated.py").read_text(encoding="utf-8")
    assert "except subprocess.TimeoutExpired" in source
    assert 'self.openclaw("gateway", "restart"' in source
    assert "failed after one managed restart and retry" in source
