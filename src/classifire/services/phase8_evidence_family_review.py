"""Validate human-declared relationships between retained visual evidence.

This module validates a local, content-free review overlay. It deliberately has
no image or report retrieval, inference, database, canonical-write, admission,
lock, or release interface. Declarations do not alter the automatic
evidence-family inventory; they record only the reviewed relationships supplied
by a competent human reviewer.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .phase8_visual_evidence import EVIDENCE_FAMILY_INVENTORY_SCHEMA
from .phase8_visual_proposal import canonical_json_sha256

EVIDENCE_FAMILY_REVIEW_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-REVIEW-v1"
EVIDENCE_FAMILY_REVIEW_VALIDATION_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-REVIEW-VALIDATION-v1"
EVIDENCE_FAMILY_REVIEW_OVERLAY_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-REVIEW-OVERLAY-v1"
HUMAN_DECLARED_EVIDENCE_RELATIONSHIPS = frozenset(
    {
        "REENCODE_OF",
        "CROP_OF",
        "ANNOTATION_OF",
        "ALTERNATE_ANGLE_OF",
        "DISTINCT_IMAGE",
    }
)

_HEX_DIGITS = frozenset("0123456789ABCDEF")
_AUTOMATIC_RELATIONSHIPS = frozenset(
    {
        "PARENT_LINKED_DETAIL",
        "EXACT_BYTE_DUPLICATE",
        "UNRESOLVED_VIEW_RELATION",
    }
)
_NOOP_FLAGS = (
    "report_or_image_retrieval_performed",
    "runtime_inference_performed",
    "database_write_performed",
    "canonical_write_performed",
    "physical_model_lock_created",
    "automatic_family_merge_performed",
    "release_performed",
)
_INVENTORY_FIELDS = {"schema", "source_manifest_sha256", "families"}
_FAMILY_FIELDS = {
    "family_id",
    "member_evidence_ids",
    "relationship_types",
    "preferred_detail_evidence_id",
    "context_evidence_ids",
}
_REVIEW_FIELDS = {
    "schema",
    "status",
    "scope",
    "source_inventory",
    "reviewer",
    "relationship_declarations",
    "unreviewed_relationships_may_remain",
    *_NOOP_FLAGS,
}
_SOURCE_INVENTORY_FIELDS = {"schema", "inventory_sha256"}
_REVIEWER_FIELDS = {
    "name",
    "competency_reference",
    "reviewed_at",
    "review_method",
    "site_visit_performed",
}
_DECLARATION_FIELDS = {
    "declaration_id",
    "relationship_type",
    "subject_evidence_id",
    "related_evidence_id",
    "outcome",
    "evidence_basis",
}


class Phase8EvidenceFamilyReviewError(ValueError):
    """Stable failure for an invalid local evidence-family review record."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


def _require_exact_fields(value: object, *, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise Phase8EvidenceFamilyReviewError(code)
    return value


def _token(value: object, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase8EvidenceFamilyReviewError(code)
    return value.strip()


def _sha256(value: object, *, code: str) -> str:
    text = _token(value, code=code).upper()
    if len(text) != 64 or any(character not in _HEX_DIGITS for character in text):
        raise Phase8EvidenceFamilyReviewError(code)
    return text


def _validate_inventory(inventory: object) -> set[str]:
    value = _require_exact_fields(
        inventory,
        expected=_INVENTORY_FIELDS,
        code="EVIDENCE_FAMILY_INVENTORY_FIELDS_INVALID",
    )
    if value.get("schema") != EVIDENCE_FAMILY_INVENTORY_SCHEMA:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_INVENTORY_SCHEMA_INVALID")
    _sha256(value.get("source_manifest_sha256"), code="EVIDENCE_FAMILY_MANIFEST_HASH_INVALID")
    families = value.get("families")
    if not isinstance(families, list):
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_LIST_INVALID")

    family_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for family in families:
        item = _require_exact_fields(
            family,
            expected=_FAMILY_FIELDS,
            code="EVIDENCE_FAMILY_ENTRY_FIELDS_INVALID",
        )
        family_id = _token(item.get("family_id"), code="EVIDENCE_FAMILY_ID_INVALID")
        if family_id in family_ids:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_ID_DUPLICATE", family_id)
        family_ids.add(family_id)
        members = item.get("member_evidence_ids")
        if (
            not isinstance(members, list)
            or not members
            or any(not isinstance(member, str) or not member.strip() for member in members)
            or len(set(members)) != len(members)
        ):
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_MEMBERS_INVALID", family_id)
        if evidence_ids.intersection(members):
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_ID_IN_MULTIPLE_FAMILIES")
        evidence_ids.update(members)
        relationships = item.get("relationship_types")
        if (
            not isinstance(relationships, list)
            or not relationships
            or any(relationship not in _AUTOMATIC_RELATIONSHIPS for relationship in relationships)
            or len(set(relationships)) != len(relationships)
        ):
            raise Phase8EvidenceFamilyReviewError(
                "EVIDENCE_FAMILY_RELATIONSHIPS_INVALID", family_id
            )
        preferred = _token(
            item.get("preferred_detail_evidence_id"),
            code="EVIDENCE_FAMILY_PREFERRED_DETAIL_INVALID",
        )
        context = item.get("context_evidence_ids")
        if (
            preferred not in members
            or not isinstance(context, list)
            or any(not isinstance(member, str) or not member.strip() for member in context)
            or len(set(context)) != len(context)
            or set(context) != set(members) - {preferred}
        ):
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_CONTEXT_INVALID", family_id)
    return evidence_ids


def _validate_reviewer(value: object) -> None:
    reviewer = _require_exact_fields(
        value,
        expected=_REVIEWER_FIELDS,
        code="EVIDENCE_FAMILY_REVIEWER_FIELDS_INVALID",
    )
    for field in ("name", "competency_reference", "review_method"):
        _token(reviewer.get(field), code="EVIDENCE_FAMILY_REVIEWER_INVALID")
    reviewed_at = _token(reviewer.get("reviewed_at"), code="EVIDENCE_FAMILY_REVIEW_DATE_INVALID")
    try:
        date.fromisoformat(reviewed_at)
    except ValueError as exc:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_DATE_INVALID") from exc
    if not isinstance(reviewer.get("site_visit_performed"), bool):
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEWER_INVALID")


def _validate_declarations(
    value: object, *, evidence_ids: set[str]
) -> tuple[dict[str, int], set[str]]:
    if not isinstance(value, list) or not value:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_DECLARATIONS_INVALID")

    declaration_ids: set[str] = set()
    pair_relationships: dict[tuple[str, str], set[str]] = {}
    relationship_counts: dict[str, int] = {}
    reviewed_evidence_ids: set[str] = set()
    seen_relationships: set[tuple[str, tuple[str, str]]] = set()
    for declaration in value:
        item = _require_exact_fields(
            declaration,
            expected=_DECLARATION_FIELDS,
            code="EVIDENCE_FAMILY_DECLARATION_FIELDS_INVALID",
        )
        declaration_id = _token(
            item.get("declaration_id"), code="EVIDENCE_FAMILY_DECLARATION_ID_INVALID"
        )
        if declaration_id in declaration_ids:
            raise Phase8EvidenceFamilyReviewError(
                "EVIDENCE_FAMILY_DECLARATION_ID_DUPLICATE", declaration_id
            )
        declaration_ids.add(declaration_id)
        relationship = item.get("relationship_type")
        if relationship not in HUMAN_DECLARED_EVIDENCE_RELATIONSHIPS:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_RELATIONSHIP_TYPE_INVALID")
        subject = _token(
            item.get("subject_evidence_id"), code="EVIDENCE_FAMILY_DECLARATION_EVIDENCE_INVALID"
        )
        related = _token(
            item.get("related_evidence_id"), code="EVIDENCE_FAMILY_DECLARATION_EVIDENCE_INVALID"
        )
        if subject == related or subject not in evidence_ids or related not in evidence_ids:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_DECLARATION_EVIDENCE_INVALID")
        if item.get("outcome") != "CONFIRMED":
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_DECLARATION_OUTCOME_INVALID")
        _token(item.get("evidence_basis"), code="EVIDENCE_FAMILY_DECLARATION_BASIS_INVALID")
        pair = tuple(sorted((subject, related)))
        relationship_key = (relationship, pair)
        if relationship_key in seen_relationships:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_RELATIONSHIP_DUPLICATE")
        seen_relationships.add(relationship_key)
        pair_relationships.setdefault(pair, set()).add(relationship)
        if "DISTINCT_IMAGE" in pair_relationships[pair] and len(pair_relationships[pair]) > 1:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_RELATIONSHIP_CONFLICT")
        relationship_counts[relationship] = relationship_counts.get(relationship, 0) + 1
        reviewed_evidence_ids.update((subject, related))
    return dict(sorted(relationship_counts.items())), reviewed_evidence_ids


def validate_phase8_evidence_family_review(
    *,
    evidence_family_inventory: object,
    review: object,
) -> dict[str, Any]:
    """Validate a declaration-only review record against an immutable inventory.

    The result is a content-free summary. It does not merge families, select a
    preferred image, or authorize any downstream operation.
    """

    evidence_ids = _validate_inventory(evidence_family_inventory)
    review_record = _require_exact_fields(
        review,
        expected=_REVIEW_FIELDS,
        code="EVIDENCE_FAMILY_REVIEW_FIELDS_INVALID",
    )
    if review_record.get("schema") != EVIDENCE_FAMILY_REVIEW_SCHEMA:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_SCHEMA_INVALID")
    if review_record.get("status") != "HUMAN_DECLARATIONS_RECORDED":
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_STATUS_INVALID")
    if review_record.get("scope") != "DECLARATIONS_ONLY_NO_AUTOMATIC_MERGE":
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_SCOPE_INVALID")
    source = _require_exact_fields(
        review_record.get("source_inventory"),
        expected=_SOURCE_INVENTORY_FIELDS,
        code="EVIDENCE_FAMILY_REVIEW_SOURCE_FIELDS_INVALID",
    )
    if source.get("schema") != EVIDENCE_FAMILY_INVENTORY_SCHEMA:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_SOURCE_SCHEMA_INVALID")
    actual_inventory_sha256 = canonical_json_sha256(evidence_family_inventory)
    if (
        _sha256(source.get("inventory_sha256"), code="EVIDENCE_FAMILY_REVIEW_SOURCE_HASH_INVALID")
        != actual_inventory_sha256
    ):
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_SOURCE_HASH_MISMATCH")
    _validate_reviewer(review_record.get("reviewer"))
    if review_record.get("unreviewed_relationships_may_remain") is not True:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_LIMITATION_REQUIRED")
    for field in _NOOP_FLAGS:
        if review_record.get(field) is not False:
            raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_NOOP_VIOLATION", field)
    relationship_counts, reviewed_evidence_ids = _validate_declarations(
        review_record.get("relationship_declarations"), evidence_ids=evidence_ids
    )
    return {
        "schema": EVIDENCE_FAMILY_REVIEW_VALIDATION_SCHEMA,
        "status": "PASS",
        "source_inventory_sha256": actual_inventory_sha256,
        "declaration_count": sum(relationship_counts.values()),
        "relationship_type_counts": relationship_counts,
        "reviewed_evidence_ids": sorted(reviewed_evidence_ids),
        "scope": "DECLARATIONS_ONLY_NO_AUTOMATIC_MERGE",
        "unreviewed_relationships_may_remain": True,
        **{field: False for field in _NOOP_FLAGS},
    }


def build_phase8_evidence_family_review_overlay(
    *,
    evidence_family_inventory: object,
    review: object,
) -> dict[str, Any]:
    """Build a read-only proposal-context overlay for a validated human review.

    The overlay contains no automatic grouping instruction and cannot make a
    reviewed relationship eligible for inference, canonical state, locking, or
    release. A consumer must retain the bound inventory and review records and
    revalidate a reloaded overlay before using it.
    """

    validation = validate_phase8_evidence_family_review(
        evidence_family_inventory=evidence_family_inventory,
        review=review,
    )
    inventory_record = _require_exact_fields(
        evidence_family_inventory,
        expected=_INVENTORY_FIELDS,
        code="EVIDENCE_FAMILY_INVENTORY_FIELDS_INVALID",
    )
    review_record = _require_exact_fields(
        review,
        expected=_REVIEW_FIELDS,
        code="EVIDENCE_FAMILY_REVIEW_FIELDS_INVALID",
    )
    declarations = review_record["relationship_declarations"]
    assert isinstance(declarations, list)  # established by the validator above
    proposal_relationships: list[dict[str, str]] = []
    for declaration in sorted(declarations, key=lambda value: str(value["declaration_id"])):
        item = _require_exact_fields(
            declaration,
            expected=_DECLARATION_FIELDS,
            code="EVIDENCE_FAMILY_DECLARATION_FIELDS_INVALID",
        )
        proposal_relationships.append(
            {
                "declaration_id": str(item["declaration_id"]),
                "relationship_type": str(item["relationship_type"]),
                "subject_evidence_id": str(item["subject_evidence_id"]),
                "related_evidence_id": str(item["related_evidence_id"]),
            }
        )
    return {
        "schema": EVIDENCE_FAMILY_REVIEW_OVERLAY_SCHEMA,
        "status": "HUMAN_DECLARATIONS_AVAILABLE_FOR_PROPOSAL_CONTEXT",
        "scope": "REVIEWED_RELATIONSHIPS_ONLY_NO_AUTOMATIC_MERGE_OR_INFERENCE",
        "source_inventory_sha256": validation["source_inventory_sha256"],
        "source_manifest_sha256": _sha256(
            inventory_record.get("source_manifest_sha256"),
            code="EVIDENCE_FAMILY_MANIFEST_HASH_INVALID",
        ),
        "review_sha256": canonical_json_sha256(review_record),
        "relationship_declaration_count": validation["declaration_count"],
        "relationship_declarations": proposal_relationships,
        "unreviewed_relationships_may_remain": True,
        **{field: False for field in _NOOP_FLAGS},
    }


def validate_phase8_evidence_family_review_overlay(
    *,
    evidence_family_inventory: object,
    review: object,
    overlay: object,
) -> dict[str, Any]:
    """Verify that a reloaded overlay is exact for the supplied review inputs."""

    expected = build_phase8_evidence_family_review_overlay(
        evidence_family_inventory=evidence_family_inventory,
        review=review,
    )
    actual = _require_exact_fields(
        overlay,
        expected=set(expected),
        code="EVIDENCE_FAMILY_REVIEW_OVERLAY_FIELDS_INVALID",
    )
    try:
        actual_sha256 = canonical_json_sha256(actual)
    except (TypeError, ValueError) as exc:
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_OVERLAY_INVALID") from exc
    if actual_sha256 != canonical_json_sha256(expected):
        raise Phase8EvidenceFamilyReviewError("EVIDENCE_FAMILY_REVIEW_OVERLAY_HASH_MISMATCH")
    return expected


__all__ = [
    "EVIDENCE_FAMILY_REVIEW_SCHEMA",
    "EVIDENCE_FAMILY_REVIEW_VALIDATION_SCHEMA",
    "EVIDENCE_FAMILY_REVIEW_OVERLAY_SCHEMA",
    "HUMAN_DECLARED_EVIDENCE_RELATIONSHIPS",
    "Phase8EvidenceFamilyReviewError",
    "build_phase8_evidence_family_review_overlay",
    "validate_phase8_evidence_family_review_overlay",
    "validate_phase8_evidence_family_review",
]
