"""Deterministic read-only pricing coverage for governed technical targets."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import DraftPricingRowObservation, DraftPricingSystemMapping, User
from .draft_pricing_intake import (
    _active_technical_release,
    _row_observation_context,
    _row_observation_value,
    _system_mapping_dependencies_current,
    _system_mapping_value,
    _technical_variant_snapshot,
)
from .draft_scope import DraftScopeError, _actor, get_draft
from .draft_system_match_contract import digest

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-COVERAGE-v1"
STATUSES = (
    "direct_b_support",
    "bottom_up_a_support",
    "review_needed",
    "stale_input",
    "insufficient_evidence",
)
EFFECTS = {
    "price_calculated": False,
    "proposal_created": False,
    "pricing_library_activated": False,
    "technical_approval_granted": False,
    "technical_applicability_assessed": False,
    "system_match_changed": False,
    "estimate_changed": False,
    "evaluation_performed": False,
    "release_performed": False,
}


def _access(db: Session, actor: User, draft_id: str) -> User:
    get_draft(db, actor, draft_id)
    actor = _actor(db, actor, "pricing:approve")
    return _actor(db, actor, "technical:read")


def _observation_dependencies_current(
    db: Session,
    actor: User,
    row: DraftPricingRowObservation,
    *,
    settings: Settings,
) -> bool:
    try:
        _, source, profile, decision, _, source_row = _row_observation_context(
            db,
            actor,
            row.draft_scope_id,
            row.source_id,
            row.profile_id,
            row.row_number,
            settings=settings,
        )
        return (
            source.dataset_id == row.dataset_id
            and source.dataset_version == row.dataset_version
            and source.source_sha256 == row.source_sha256
            and source.document_sha256 == row.document_sha256
            and profile.revision == row.profile_revision
            and profile.profile_sha256 == row.profile_sha256
            and decision.id == row.profile_decision_id
            and decision.decision_sha256 == row.decision_sha256
            and source_row["sheet_index"] == row.sheet_index
            and source_row["row"] == row.row_number
            and source_row["sha256"] == row.row_sha256
        )
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        return False


def _observation_inventory(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(DraftPricingRowObservation)
        .where(DraftPricingRowObservation.draft_scope_id == draft_id)
        .order_by(DraftPricingRowObservation.id)
    ).all()
    inventory = []
    for row in rows:
        value = _row_observation_value(row)
        inventory.append(
            {
                "observation_id": row.id,
                "observation_sha256": row.observation_sha256,
                "dataset_id": row.dataset_id,
                "dataset_version": row.dataset_version,
                "source_id": row.source_id,
                "source_sha256": row.source_sha256,
                "profile_id": row.profile_id,
                "profile_sha256": row.profile_sha256,
                "row_sha256": row.row_sha256,
                "item_kind": row.item_kind,
                "evidence_state": row.evidence_state,
                "normalized_reference": row.normalized_reference,
                "current": _observation_dependencies_current(
                    db, actor, row, settings=settings
                ),
                "target_link": None,
                "reason": "no_governed_component_activity_recipe_link",
                "definition_sha256": value["definition_sha256"],
            }
        )
    return inventory


def _mapping_inventory(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(DraftPricingSystemMapping)
        .where(DraftPricingSystemMapping.draft_scope_id == draft_id)
        .order_by(DraftPricingSystemMapping.id)
    ).all()
    inventory = []
    for row in rows:
        value = _system_mapping_value(row)
        interpretation = value["definition"]["interpretation"]
        inventory.append(
            {
                "mapping_id": row.id,
                "mapping_sha256": row.mapping_sha256,
                "dataset_id": row.dataset_id,
                "dataset_version": row.dataset_version,
                "source_id": row.source_id,
                "source_sha256": row.source_sha256,
                "profile_id": row.profile_id,
                "profile_sha256": row.profile_sha256,
                "row_sha256": row.row_sha256,
                "status": row.mapping_status,
                "current": _system_mapping_dependencies_current(
                    db, actor, row, value, settings=settings
                ),
                "selected_variant_id": interpretation["selected_variant_id"],
                "candidate_variant_ids": interpretation["candidate_variant_ids"],
                "definition_sha256": value["definition_sha256"],
            }
        )
    return inventory


def _target_status(
    target_id: str, mappings: list[dict[str, Any]]
) -> tuple[str, str | None, str, list[str], list[dict[str, Any]]]:
    related = [
        item
        for item in mappings
        if item["selected_variant_id"] == target_id
        or target_id in item["candidate_variant_ids"]
    ]
    current_direct = [
        item
        for item in related
        if item["current"]
        and item["status"] == "mapped"
        and item["selected_variant_id"] == target_id
    ]
    stale = [item for item in related if not item["current"]]
    current_ambiguous = [
        item
        for item in related
        if item["current"]
        and item["status"] == "ambiguous"
        and target_id in item["candidate_variant_ids"]
    ]
    if current_direct:
        reasons = ["current_reviewed_dataset_b_mapping"]
        if stale:
            reasons.append("related_dataset_b_mapping_has_stale_dependencies")
        if current_ambiguous:
            reasons.append("additional_dataset_b_mapping_ambiguous_for_target")
        return (
            "direct_b_support",
            "direct_observed_b",
            "review_needed" if stale or current_ambiguous else "ready",
            reasons,
            related,
        )
    if stale:
        return (
            "stale_input",
            None,
            "blocked",
            ["related_dataset_b_mapping_has_stale_dependencies"],
            related,
        )
    if current_ambiguous:
        return (
            "review_needed",
            None,
            "review_needed",
            ["dataset_b_mapping_ambiguous_for_target"],
            related,
        )
    return (
        "insufficient_evidence",
        None,
        "blocked",
        [
            "no_current_reviewed_dataset_b_mapping",
            "no_governed_component_activity_recipe_link",
        ],
        related,
    )


def preview_coverage(
    db: Session,
    actor: User,
    draft_id: str,
    technical_release_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Return exact coverage status for every target in one active release.

    The result contains evidence identities and hashes, never price values. It
    performs no write and grants no downstream authority.
    """

    actor = _access(db, actor, draft_id)
    actor, release, records, active_ids = _active_technical_release(
        db, actor, technical_release_id
    )
    mappings = _mapping_inventory(db, actor, draft_id, settings=settings)
    observations = _observation_inventory(db, actor, draft_id, settings=settings)
    targets = []
    for target_id in sorted(active_ids, key=lambda item: (records[item]["variant_id"], item)):
        snapshot = _technical_variant_snapshot(
            db,
            target_id,
            records,
            active_ids,
            settings=settings,
            lock=False,
        )
        status, method, review_status, reasons, related = _target_status(
            target_id, mappings
        )
        targets.append(
            {
                "technical_target": {
                    "id": snapshot["id"],
                    "key": snapshot["key"],
                    "variant_id": snapshot["variant_id"],
                    "system_id": snapshot["system_id"],
                    "snapshot_sha256": snapshot["sha256"],
                    "technical_fields_sha256": snapshot["technical_fields_sha256"],
                    "release_record_sha256": snapshot["release_record_sha256"],
                    "source_sha256": snapshot["source_hash"],
                },
                "status": status,
                "primary_method": method,
                "review_status": review_status,
                "reasons": reasons,
                "dependencies": {
                    "dataset_b_mappings": related,
                    "dataset_a_observations": [],
                },
            }
        )
    status_counts = {status: 0 for status in STATUSES}
    for target in targets:
        status_counts[cast(str, target["status"])] += 1
    result = {
        "schema_version": SCHEMA,
        "draft_scope_id": draft_id,
        "technical_release": {
            "id": release.id,
            "version": release.version,
            "sha256": cast(str, release.release_hash),
            "effective_date": (
                release.effective_date.isoformat() if release.effective_date else None
            ),
        },
        "summary": {
            "target_count": len(targets),
            "status_counts": status_counts,
            "current_unlinked_dataset_a_observations": sum(
                1 for item in observations if item["current"]
            ),
            "stale_unlinked_dataset_a_observations": sum(
                1 for item in observations if not item["current"]
            ),
        },
        "targets": targets,
        "unlinked_dataset_a_observations": observations,
        "unassigned_dataset_b_mappings": [
            item
            for item in mappings
            if item["selected_variant_id"] is None
            and not item["candidate_variant_ids"]
        ],
        "limitations": [
            "dataset_a_rows_are_not_linked_to_versioned_component_activity_recipes",
            "bottom_up_a_support_cannot_be_confirmed_in_this_slice",
            "coverage_does_not_assess_project_specific_technical_applicability",
            "coverage_does_not_calculate_or_approve_a_price",
        ],
        "effects": EFFECTS,
    }
    result["coverage_sha256"] = digest(result)
    return result


__all__ = ["EFFECTS", "SCHEMA", "STATUSES", "preview_coverage"]
