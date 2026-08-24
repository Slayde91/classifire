from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_classifire_real_uat_integrated import (  # noqa: E402
    TEXT_FACT_EVIDENCE_TYPE,
    IntegratedEvidenceController,
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


def test_linked_original_hash_supersedes_embedded_digest_for_visual_deduplication() -> None:
    first = {
        "photo_id": "P001-I01",
        "digest": "embedded-a",
        "full_resolution_sha256": "A" * 64,
    }
    second = {
        "photo_id": "P004-I03",
        "digest": "embedded-b",
        "full_resolution_sha256": "a" * 64,
    }

    assert IntegratedEvidenceController._visual_key(first) == (
        IntegratedEvidenceController._visual_key(second)
    )


def test_variant_group_supersedes_page_order_but_ambiguous_occurrences_do_not_collapse() -> None:
    earlier = {
        "photo_id": "P001-I01",
        "image_variant_group_id": "group-1",
        "image_variant_group_status": "RESOLVED",
        "image_variant_relationships": ["FULL_FRAME_EQUIVALENT"],
    }
    later = {
        "photo_id": "P010-I03",
        "image_variant_group_id": "group-1",
        "image_variant_group_status": "RESOLVED",
        "image_variant_relationships": ["SELF"],
    }
    assert IntegratedEvidenceController._visual_key(earlier) == (
        IntegratedEvidenceController._visual_key(later)
    )
    earlier["image_variant_group_status"] = "AMBIGUOUS"
    later["image_variant_group_status"] = "AMBIGUOUS"
    assert IntegratedEvidenceController._visual_key(earlier) != (
        IntegratedEvidenceController._visual_key(later)
    )


def test_variant_primary_on_later_page_becomes_canonical_visual() -> None:
    controller = object.__new__(IntegratedEvidenceController)
    controller.receipt = {"report_sha256": "a" * 64}
    controller._image_variant_receipt_sha256 = lambda: "b" * 64
    controller._image_variant_resolution_cache = SimpleNamespace(
        groups=(
            {
                "group_id": "g1",
                "primary_candidate_id": "later:linked",
                "equivalent_candidate_ids": [],
            },
        ),
        rows=(),
    )
    saved: dict[str, dict] = {}
    controller.save_json = lambda name, payload: saved.setdefault(name, payload)
    by_id = {
        "P001-I01": {
            "photo_id": "P001-I01",
            "page_number": 1,
            "occurrence": 1,
            "image_variant_group_id": "g1",
            "image_variant_primary_photo_id": "P010-I03",
            "image_variant_group_status": "RESOLVED",
            "image_variant_relationships": ["FULL_FRAME_EQUIVALENT"],
            "image_variant_policy_version": "v1",
        },
        "P010-I03": {
            "photo_id": "P010-I03",
            "page_number": 10,
            "occurrence": 3,
            "image_variant_group_id": "g1",
            "image_variant_primary_photo_id": "P010-I03",
            "image_variant_group_status": "RESOLVED",
            "image_variant_relationships": ["SELF"],
            "image_variant_policy_version": "v1",
        },
    }

    controller._on_image_variant_inventory_ready(by_id)

    assert by_id["P001-I01"]["canonical_photo_id"] == "P010-I03"
    assert saved["16a-photo-dedup-map.json"]["image_variant_receipt_sha256"] == "b" * 64


def test_duplicate_and_multi_angle_counting_safeguards_are_explicit() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_integrated.py").read_text(encoding="utf-8")
    photo_source = (SCRIPTS / "run_classifire_real_uat_photoaware.py").read_text(encoding="utf-8")
    assert "EXACT_DUPLICATE_OF:" in source
    assert "image-variant grouping" in source
    assert "greatest-usable-detail PRIMARY" in source
    assert "same_service_opposite_barrier_side" in photo_source
    assert "same_opening_opposite_barrier_side" in photo_source
    assert "Photograph count NEVER equals service count or opening count" in photo_source


def test_gateway_timeout_is_recoverable_once() -> None:
    source = (SCRIPTS / "run_classifire_real_uat_integrated.py").read_text(encoding="utf-8")
    assert "except subprocess.TimeoutExpired" in source
    assert 'self.openclaw("gateway", "restart"' in source
    assert "failed after one managed restart and retry" in source
