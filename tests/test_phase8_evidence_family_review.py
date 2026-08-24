from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from classifire.services.phase8_evidence_family_review import (
    EVIDENCE_FAMILY_REVIEW_OVERLAY_SCHEMA,
    EVIDENCE_FAMILY_REVIEW_SCHEMA,
    EVIDENCE_FAMILY_REVIEW_VALIDATION_SCHEMA,
    Phase8EvidenceFamilyReviewError,
    build_phase8_evidence_family_review_overlay,
    validate_phase8_evidence_family_review,
    validate_phase8_evidence_family_review_overlay,
)
from classifire.services.phase8_visual_evidence import EVIDENCE_FAMILY_INVENTORY_SCHEMA
from classifire.services.phase8_visual_proposal import canonical_json_sha256


def _inventory() -> dict[str, Any]:
    return {
        "schema": EVIDENCE_FAMILY_INVENTORY_SCHEMA,
        "source_manifest_sha256": "A" * 64,
        "families": [
            {
                "family_id": "FAMILY-001",
                "member_evidence_ids": ["E-001"],
                "relationship_types": ["UNRESOLVED_VIEW_RELATION"],
                "preferred_detail_evidence_id": "E-001",
                "context_evidence_ids": [],
            },
            {
                "family_id": "FAMILY-002",
                "member_evidence_ids": ["E-002"],
                "relationship_types": ["UNRESOLVED_VIEW_RELATION"],
                "preferred_detail_evidence_id": "E-002",
                "context_evidence_ids": [],
            },
            {
                "family_id": "FAMILY-003",
                "member_evidence_ids": ["E-003"],
                "relationship_types": ["UNRESOLVED_VIEW_RELATION"],
                "preferred_detail_evidence_id": "E-003",
                "context_evidence_ids": [],
            },
        ],
    }


def _declaration(
    declaration_id: str,
    relationship_type: str,
    subject_evidence_id: str,
    related_evidence_id: str,
) -> dict[str, str]:
    return {
        "declaration_id": declaration_id,
        "relationship_type": relationship_type,
        "subject_evidence_id": subject_evidence_id,
        "related_evidence_id": related_evidence_id,
        "outcome": "CONFIRMED",
        "evidence_basis": "Synthetic fixture visual review.",
    }


def _review(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": EVIDENCE_FAMILY_REVIEW_SCHEMA,
        "status": "HUMAN_DECLARATIONS_RECORDED",
        "scope": "DECLARATIONS_ONLY_NO_AUTOMATIC_MERGE",
        "source_inventory": {
            "schema": EVIDENCE_FAMILY_INVENTORY_SCHEMA,
            "inventory_sha256": canonical_json_sha256(inventory),
        },
        "reviewer": {
            "name": "Synthetic competent reviewer",
            "competency_reference": "SYNTHETIC-REVIEWER-001",
            "reviewed_at": "2026-08-24",
            "review_method": "Synthetic visual evidence review",
            "site_visit_performed": False,
        },
        "relationship_declarations": [
            _declaration("EFR-001", "REENCODE_OF", "E-002", "E-001"),
            _declaration("EFR-002", "ALTERNATE_ANGLE_OF", "E-003", "E-001"),
        ],
        "unreviewed_relationships_may_remain": True,
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "database_write_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
        "automatic_family_merge_performed": False,
        "release_performed": False,
    }


def test_validates_human_relationship_declarations_without_merging_families() -> None:
    inventory = _inventory()
    result = validate_phase8_evidence_family_review(
        evidence_family_inventory=inventory,
        review=_review(inventory),
    )

    assert result == {
        "schema": EVIDENCE_FAMILY_REVIEW_VALIDATION_SCHEMA,
        "status": "PASS",
        "source_inventory_sha256": canonical_json_sha256(inventory),
        "declaration_count": 2,
        "relationship_type_counts": {
            "ALTERNATE_ANGLE_OF": 1,
            "REENCODE_OF": 1,
        },
        "reviewed_evidence_ids": ["E-001", "E-002", "E-003"],
        "scope": "DECLARATIONS_ONLY_NO_AUTOMATIC_MERGE",
        "unreviewed_relationships_may_remain": True,
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "database_write_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
        "automatic_family_merge_performed": False,
        "release_performed": False,
    }
    assert inventory == _inventory()


def test_builds_hash_bound_proposal_context_overlay_without_mutating_inventory() -> None:
    inventory = _inventory()
    review = _review(inventory)
    overlay = build_phase8_evidence_family_review_overlay(
        evidence_family_inventory=inventory,
        review=review,
    )

    assert overlay == {
        "schema": EVIDENCE_FAMILY_REVIEW_OVERLAY_SCHEMA,
        "status": "HUMAN_DECLARATIONS_AVAILABLE_FOR_PROPOSAL_CONTEXT",
        "scope": "REVIEWED_RELATIONSHIPS_ONLY_NO_AUTOMATIC_MERGE_OR_INFERENCE",
        "source_inventory_sha256": canonical_json_sha256(inventory),
        "source_manifest_sha256": "A" * 64,
        "review_sha256": canonical_json_sha256(review),
        "relationship_declaration_count": 2,
        "relationship_declarations": [
            {
                "declaration_id": "EFR-001",
                "relationship_type": "REENCODE_OF",
                "subject_evidence_id": "E-002",
                "related_evidence_id": "E-001",
            },
            {
                "declaration_id": "EFR-002",
                "relationship_type": "ALTERNATE_ANGLE_OF",
                "subject_evidence_id": "E-003",
                "related_evidence_id": "E-001",
            },
        ],
        "unreviewed_relationships_may_remain": True,
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "database_write_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
        "automatic_family_merge_performed": False,
        "release_performed": False,
    }
    assert "reviewer" not in overlay
    assert "evidence_basis" not in json.dumps(overlay)
    assert inventory == _inventory()
    assert review == _review(inventory)
    assert (
        validate_phase8_evidence_family_review_overlay(
            evidence_family_inventory=inventory,
            review=review,
            overlay=deepcopy(overlay),
        )
        == overlay
    )


def test_rejects_tampered_or_stale_proposal_context_overlay() -> None:
    inventory = _inventory()
    review = _review(inventory)
    source_overlay = build_phase8_evidence_family_review_overlay(
        evidence_family_inventory=inventory,
        review=review,
    )
    tampered_overlay = deepcopy(source_overlay)
    tampered_overlay["relationship_declarations"][0]["related_evidence_id"] = "E-003"

    with pytest.raises(Phase8EvidenceFamilyReviewError) as caught:
        validate_phase8_evidence_family_review_overlay(
            evidence_family_inventory=inventory,
            review=review,
            overlay=tampered_overlay,
        )

    assert caught.value.code == "EVIDENCE_FAMILY_REVIEW_OVERLAY_HASH_MISMATCH"

    review["reviewer"]["reviewed_at"] = "2026-08-25"
    with pytest.raises(Phase8EvidenceFamilyReviewError) as stale:
        validate_phase8_evidence_family_review_overlay(
            evidence_family_inventory=inventory,
            review=review,
            overlay=source_overlay,
        )

    assert stale.value.code == "EVIDENCE_FAMILY_REVIEW_OVERLAY_HASH_MISMATCH"


def test_rejects_review_not_bound_to_exact_inventory() -> None:
    inventory = _inventory()
    review = _review(inventory)
    review["source_inventory"]["inventory_sha256"] = "0" * 64

    with pytest.raises(Phase8EvidenceFamilyReviewError) as caught:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=review,
        )

    assert caught.value.code == "EVIDENCE_FAMILY_REVIEW_SOURCE_HASH_MISMATCH"


def test_rejects_unknown_or_automatic_relationship_type() -> None:
    inventory = _inventory()
    review = _review(inventory)
    review["relationship_declarations"][0]["subject_evidence_id"] = "E-MISSING"

    with pytest.raises(Phase8EvidenceFamilyReviewError) as unknown:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=review,
        )

    assert unknown.value.code == "EVIDENCE_FAMILY_DECLARATION_EVIDENCE_INVALID"

    automatic = _review(inventory)
    automatic["relationship_declarations"][0]["relationship_type"] = "EXACT_BYTE_DUPLICATE"
    with pytest.raises(Phase8EvidenceFamilyReviewError) as caught:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=automatic,
        )

    assert caught.value.code == "EVIDENCE_FAMILY_RELATIONSHIP_TYPE_INVALID"


def test_rejects_conflicting_or_duplicate_pair_declarations() -> None:
    inventory = _inventory()
    conflicting = _review(inventory)
    conflicting["relationship_declarations"].append(
        _declaration("EFR-003", "DISTINCT_IMAGE", "E-001", "E-002")
    )

    with pytest.raises(Phase8EvidenceFamilyReviewError) as conflict:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=conflicting,
        )

    assert conflict.value.code == "EVIDENCE_FAMILY_RELATIONSHIP_CONFLICT"

    duplicate = deepcopy(_review(inventory))
    duplicate["relationship_declarations"].append(
        _declaration("EFR-003", "REENCODE_OF", "E-001", "E-002")
    )
    with pytest.raises(Phase8EvidenceFamilyReviewError) as caught:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=duplicate,
        )

    assert caught.value.code == "EVIDENCE_FAMILY_RELATIONSHIP_DUPLICATE"


def test_rejects_any_claim_of_automatic_or_canonical_action() -> None:
    inventory = _inventory()
    review = _review(inventory)
    review["automatic_family_merge_performed"] = True

    with pytest.raises(Phase8EvidenceFamilyReviewError) as caught:
        validate_phase8_evidence_family_review(
            evidence_family_inventory=inventory,
            review=review,
        )

    assert caught.value.code == "EVIDENCE_FAMILY_REVIEW_NOOP_VIOLATION"
    assert caught.value.detail == "automatic_family_merge_performed"


def test_cli_validates_a_review_record_without_writing_state(tmp_path: Path) -> None:
    inventory = _inventory()
    inventory_path = tmp_path / "inventory.json"
    review_path = tmp_path / "review.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    review_path.write_text(json.dumps(_review(inventory)), encoding="utf-8")
    repository_root = Path(__file__).parents[1]
    result = subprocess.run(  # noqa: S603 -- fixed local validator command in a test fixture
        [
            sys.executable,
            str(repository_root / "scripts" / "validate_phase8_evidence_family_review.py"),
            "--inventory",
            str(inventory_path),
            "--review",
            str(review_path),
        ],
        capture_output=True,
        check=False,
        cwd=repository_root,
        env={**os.environ, "PYTHONPATH": str(repository_root / "src")},
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "PASS"
