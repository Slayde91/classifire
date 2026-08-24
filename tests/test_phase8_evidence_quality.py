from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from classifire.services.phase8_evidence_quality import (
    EVIDENCE_FAMILY_QUALITY_METRICS_SCHEMA,
    Phase8EvidenceQualityError,
    summarise_phase8_evidence_family_quality,
)
from classifire.services.phase8_visual_evidence import EVIDENCE_FAMILY_INVENTORY_SCHEMA
from classifire.services.phase8_visual_proposal import canonical_json_sha256


def _inventory(
    source_manifest_sha256: str,
    families: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": EVIDENCE_FAMILY_INVENTORY_SCHEMA,
        "source_manifest_sha256": source_manifest_sha256,
        "families": families,
    }


def _family(
    family_id: str,
    members: list[str],
    relationships: list[str],
    preferred: str,
) -> dict[str, Any]:
    return {
        "family_id": family_id,
        "member_evidence_ids": members,
        "relationship_types": relationships,
        "preferred_detail_evidence_id": preferred,
        "context_evidence_ids": [member for member in members if member != preferred],
    }


def test_summarises_distinct_content_free_inventories() -> None:
    first = _inventory(
        "A" * 64,
        [
            _family(
                "FAMILY-001",
                ["E-001", "E-002"],
                ["PARENT_LINKED_DETAIL"],
                "E-002",
            ),
            _family(
                "FAMILY-002",
                ["E-003"],
                ["UNRESOLVED_VIEW_RELATION"],
                "E-003",
            ),
        ],
    )
    second = _inventory(
        "B" * 64,
        [
            _family(
                "FAMILY-003",
                ["E-101", "E-102"],
                ["EXACT_BYTE_DUPLICATE"],
                "E-101",
            )
        ],
    )

    result = summarise_phase8_evidence_family_quality([first, second])

    assert result == {
        "schema": EVIDENCE_FAMILY_QUALITY_METRICS_SCHEMA,
        "status": "PASS",
        "inventory_count": 2,
        "inventory_sha256s": sorted([canonical_json_sha256(first), canonical_json_sha256(second)]),
        "source_manifest_sha256s": ["A" * 64, "B" * 64],
        "family_count": 3,
        "preserved_context_member_count": 2,
        "relationship_family_counts": {
            "EXACT_BYTE_DUPLICATE": 1,
            "PARENT_LINKED_DETAIL": 1,
            "UNRESOLVED_VIEW_RELATION": 1,
        },
        "unresolved_view_family_count": 1,
        "families_requiring_human_relationship_review": 1,
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "database_write_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
    }


def test_rejects_duplicate_source_or_inventory_inputs() -> None:
    inventory = _inventory(
        "A" * 64,
        [_family("FAMILY-001", ["E-001"], ["UNRESOLVED_VIEW_RELATION"], "E-001")],
    )

    with pytest.raises(Phase8EvidenceQualityError) as duplicate_source:
        summarise_phase8_evidence_family_quality([inventory, deepcopy(inventory)])

    assert duplicate_source.value.code == "EVIDENCE_FAMILY_SOURCE_MANIFEST_DUPLICATE"

    distinct_inventory = deepcopy(inventory)
    distinct_inventory["source_manifest_sha256"] = "B" * 64
    result = summarise_phase8_evidence_family_quality([inventory, distinct_inventory])

    assert result["inventory_count"] == 2


def test_rejects_invalid_or_inconsistent_family_inventory() -> None:
    inventory = _inventory(
        "A" * 64,
        [_family("FAMILY-001", ["E-001", "E-002"], ["PARENT_LINKED_DETAIL"], "E-002")],
    )
    invalid_relationship = deepcopy(inventory)
    invalid_relationship["families"][0]["relationship_types"] = ["ALTERNATE_ANGLE_OF"]

    with pytest.raises(Phase8EvidenceQualityError) as relationship:
        summarise_phase8_evidence_family_quality([invalid_relationship])

    assert relationship.value.code == "EVIDENCE_FAMILY_RELATIONSHIPS_INVALID"

    invalid_context = deepcopy(inventory)
    invalid_context["families"][0]["context_evidence_ids"] = []
    with pytest.raises(Phase8EvidenceQualityError) as caught:
        summarise_phase8_evidence_family_quality([invalid_context])

    assert caught.value.code == "EVIDENCE_FAMILY_CONTEXT_INVALID"
