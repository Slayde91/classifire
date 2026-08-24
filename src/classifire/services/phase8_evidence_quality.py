"""Content-free Phase 8 evidence-family quality metrics.

The service accepts retained evidence-family inventories only.  It does not
open evidence bytes, resolve paths, retrieve reports or images, call inference,
or access database or canonical-state interfaces.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

from .phase8_visual_evidence import EVIDENCE_FAMILY_INVENTORY_SCHEMA
from .phase8_visual_proposal import canonical_json_sha256

EVIDENCE_FAMILY_QUALITY_METRICS_SCHEMA = "CLASSIFIRE-PHASE8-EVIDENCE-FAMILY-QUALITY-METRICS-v1"

_HEX_DIGITS = frozenset("0123456789ABCDEF")
_INVENTORY_FIELDS = {"schema", "source_manifest_sha256", "families"}
_FAMILY_FIELDS = {
    "family_id",
    "member_evidence_ids",
    "relationship_types",
    "preferred_detail_evidence_id",
    "context_evidence_ids",
}
_AUTOMATIC_RELATIONSHIPS = frozenset(
    {
        "PARENT_LINKED_DETAIL",
        "EXACT_BYTE_DUPLICATE",
        "UNRESOLVED_VIEW_RELATION",
    }
)


class Phase8EvidenceQualityError(ValueError):
    """Stable failure for an invalid content-free evidence-quality input."""

    def __init__(self, code: str, detail: str | None = None) -> None:
        self.code = code
        self.detail = detail
        super().__init__(code if detail is None else f"{code}: {detail}")


def _exact_mapping(value: object, *, expected: set[str], code: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise Phase8EvidenceQualityError(code)
    return value


def _token(value: object, *, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Phase8EvidenceQualityError(code)
    return value.strip()


def _sha256(value: object, *, code: str) -> str:
    text = _token(value, code=code).upper()
    if len(text) != 64 or any(character not in _HEX_DIGITS for character in text):
        raise Phase8EvidenceQualityError(code)
    return text


def _validated_inventory(inventory: object) -> tuple[str, str, Counter[str], int, int]:
    value = _exact_mapping(
        inventory,
        expected=_INVENTORY_FIELDS,
        code="EVIDENCE_FAMILY_INVENTORY_FIELDS_INVALID",
    )
    if value.get("schema") != EVIDENCE_FAMILY_INVENTORY_SCHEMA:
        raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_INVENTORY_SCHEMA_INVALID")
    source_manifest_sha256 = _sha256(
        value.get("source_manifest_sha256"),
        code="EVIDENCE_FAMILY_MANIFEST_HASH_INVALID",
    )
    families = value.get("families")
    if not isinstance(families, list) or not families:
        raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_LIST_INVALID")

    family_ids: set[str] = set()
    evidence_ids: set[str] = set()
    relationship_counts: Counter[str] = Counter()
    context_member_count = 0
    for family in families:
        item = _exact_mapping(
            family,
            expected=_FAMILY_FIELDS,
            code="EVIDENCE_FAMILY_ENTRY_FIELDS_INVALID",
        )
        family_id = _token(item.get("family_id"), code="EVIDENCE_FAMILY_ID_INVALID")
        if family_id in family_ids:
            raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_ID_DUPLICATE", family_id)
        family_ids.add(family_id)
        members = item.get("member_evidence_ids")
        if (
            not isinstance(members, list)
            or not members
            or any(not isinstance(member, str) or not member.strip() for member in members)
            or len(set(members)) != len(members)
            or evidence_ids.intersection(members)
        ):
            raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_MEMBERS_INVALID", family_id)
        evidence_ids.update(members)
        relationships = item.get("relationship_types")
        if (
            not isinstance(relationships, list)
            or not relationships
            or any(relationship not in _AUTOMATIC_RELATIONSHIPS for relationship in relationships)
            or len(set(relationships)) != len(relationships)
        ):
            raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_RELATIONSHIPS_INVALID", family_id)
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
            raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_CONTEXT_INVALID", family_id)
        relationship_counts.update(relationships)
        context_member_count += len(context)
    return (
        source_manifest_sha256,
        canonical_json_sha256(value),
        relationship_counts,
        len(families),
        context_member_count,
    )


def summarise_phase8_evidence_family_quality(
    inventories: Sequence[object],
) -> dict[str, Any]:
    """Return deterministic, content-free metrics for distinct source packets."""

    if isinstance(inventories, (str, bytes)) or not isinstance(inventories, Sequence):
        raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_INVENTORIES_INVALID")
    if not inventories:
        raise Phase8EvidenceQualityError("EVIDENCE_FAMILY_INVENTORIES_EMPTY")

    source_manifest_hashes: set[str] = set()
    inventory_hashes: list[str] = []
    relationship_counts: Counter[str] = Counter()
    family_count = 0
    context_member_count = 0
    for inventory in inventories:
        (
            source_manifest_sha256,
            inventory_sha256,
            inventory_relationships,
            inventory_family_count,
            inventory_context_count,
        ) = _validated_inventory(inventory)
        if source_manifest_sha256 in source_manifest_hashes:
            raise Phase8EvidenceQualityError(
                "EVIDENCE_FAMILY_SOURCE_MANIFEST_DUPLICATE",
                source_manifest_sha256,
            )
        source_manifest_hashes.add(source_manifest_sha256)
        inventory_hashes.append(inventory_sha256)
        relationship_counts.update(inventory_relationships)
        family_count += inventory_family_count
        context_member_count += inventory_context_count

    unresolved = relationship_counts["UNRESOLVED_VIEW_RELATION"]
    return {
        "schema": EVIDENCE_FAMILY_QUALITY_METRICS_SCHEMA,
        "status": "PASS",
        "inventory_count": len(inventories),
        "inventory_sha256s": sorted(inventory_hashes),
        "source_manifest_sha256s": sorted(source_manifest_hashes),
        "family_count": family_count,
        "preserved_context_member_count": context_member_count,
        "relationship_family_counts": dict(sorted(relationship_counts.items())),
        "unresolved_view_family_count": unresolved,
        "families_requiring_human_relationship_review": unresolved,
        "report_or_image_retrieval_performed": False,
        "runtime_inference_performed": False,
        "database_write_performed": False,
        "canonical_write_performed": False,
        "physical_model_lock_created": False,
    }


__all__ = [
    "EVIDENCE_FAMILY_QUALITY_METRICS_SCHEMA",
    "Phase8EvidenceQualityError",
    "summarise_phase8_evidence_family_quality",
]
