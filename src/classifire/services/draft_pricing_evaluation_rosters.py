"""Persist target-blind pricing evaluation rosters from governed Dataset B mappings."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    DraftPricingEvaluationRoster,
    DraftPricingSystemMapping,
    DraftScope,
    User,
    new_id,
)
from .draft_pricing_evaluation_contract import (
    PricingEvaluationLineageError,
    assign_target_blind_splits,
    build_lineage_manifest,
    validate_lineage_manifest,
    validate_new_revision,
)
from .draft_pricing_intake import (
    _system_mapping_dependencies_current,
    _system_mapping_value,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft
from .draft_system_match_contract import canonical, digest

SCHEMA = "CLASSIFIRE-DRAFT-PRICING-EVALUATION-ROSTER-v1"
MAX_ROSTER_BYTES = 1024 * 1024
PREVIEW_MAX_AGE = timedelta(minutes=15)
PREVIEW_FUTURE_TOLERANCE = timedelta(minutes=1)
SELECTION_POLICY = {
    "eligible_source": "current_reviewed_mapped_dataset_b",
    "assignment": "target_blind_connected_lineage_v1",
    "target_commitment": "mapping_and_row_hash_without_target_value",
    "lineage_derivation": {
        "system_identity": "technical_system_id_hash",
        "alias_cluster": "resolved_technical_system_id_hash",
        "configuration_cluster": "technical_variant_key_hash",
        "source_derivation": "technical_source_hash",
        "version_lineage": "technical_variant_id_hash",
    },
}
EFFECTS = {
    "prediction_performed": False,
    "evaluation_performed": False,
    "target_revealed": False,
    "library_activated": False,
    "technical_approval_granted": False,
    "system_match_changed": False,
    "estimate_changed": False,
    "release_performed": False,
}


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _access(db: Session, actor: User, draft_id: str) -> tuple[User, DraftScope]:
    draft = get_draft(db, actor, draft_id)
    actor = _actor(db, actor, "pricing:approve")
    actor = _actor(db, actor, "technical:read")
    return actor, draft


def _token(prefix: str, value: object) -> str:
    return prefix + cast(str, digest({"value": value}))[:32]


def _inventory_hash(items: list[dict[str, Any]]) -> str:
    return cast(str, digest(items))


def _mapping_inventory(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
    lock: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    statement = (
        select(DraftPricingSystemMapping)
        .where(DraftPricingSystemMapping.draft_scope_id == draft_id)
        .order_by(DraftPricingSystemMapping.id)
    )
    rows = db.scalars(statement.with_for_update() if lock else statement).all()
    inventory: list[dict[str, Any]] = []
    members: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for row in rows:
        value = _system_mapping_value(row)
        current = _system_mapping_dependencies_current(
            db, actor, row, value, settings=settings, lock=lock
        )
        inventory.append(
            {
                "mapping_id": row.id,
                "mapping_sha256": row.mapping_sha256,
                "status": row.mapping_status,
                "current": current,
            }
        )
        if row.mapping_status != "mapped" or not current:
            exclusions.append(
                {
                    "mapping_id": row.id,
                    "mapping_sha256": row.mapping_sha256,
                    "reason": (
                        "stale_dependencies"
                        if not current
                        else f"status_{row.mapping_status}"
                    ),
                }
            )
            continue
        definition = value["definition"]
        variant = definition["variants"][0]
        members.append(
            {
                "observation_id": row.id,
                "dataset": {
                    "id": row.dataset_id,
                    "kind": "firefly_system_prices",
                    "version": row.dataset_version,
                },
                "source": {"id": row.source_id, "sha256": row.source_sha256},
                "profile": {
                    "id": row.profile_id,
                    "revision": row.profile_revision,
                    "sha256": row.profile_sha256,
                },
                "row": {
                    "sheet_index": row.sheet_index,
                    "sheet_name": definition["row"]["sheet"],
                    "number": row.row_number,
                    "sha256": row.row_sha256,
                },
                "target": {
                    "field": "rate",
                    "sha256": digest(
                        {
                            "field": "rate",
                            "mapping_sha256": row.mapping_sha256,
                            "row_sha256": row.row_sha256,
                        }
                    ),
                },
                "available_at": row.created_at.astimezone(UTC).isoformat(),
                "lineage_keys": {
                    "system_identity": _token("sys-", variant["system_id"]),
                    "alias_cluster": _token("alias-", variant["system_id"]),
                    "configuration_cluster": _token("cfg-", variant["key"]),
                    "source_derivation": _token("src-", variant["source_hash"]),
                    "version_lineage": _token("ver-", variant["id"]),
                },
            }
        )
    return inventory, members, exclusions


def validate_roster(value: Any) -> dict[str, Any]:
    keys = {
        "schema_version",
        "roster_id",
        "manifest_id",
        "draft_scope_id",
        "revision",
        "parent_manifest_sha256",
        "created_at",
        "created_by_id",
        "feature_cutoff_at",
        "selection_policy",
        "mapping_inventory",
        "mapping_inventory_sha256",
        "exclusions",
        "manifest",
        "effects",
        "roster_sha256",
    }
    try:
        if type(value) is not dict or set(value) != keys or value["schema_version"] != SCHEMA:
            raise ValueError("roster shape")
        for key in ("roster_id", "manifest_id", "draft_scope_id", "created_by_id"):
            if type(value[key]) is not str or not 1 <= len(value[key]) <= 128:
                raise ValueError("roster identity")
        revision = value["revision"]
        parent = value["parent_manifest_sha256"]
        if type(revision) is not int or revision < 1:
            raise ValueError("roster revision")
        if (revision == 1) != (parent is None):
            raise ValueError("roster parent")
        if parent is not None and (
            type(parent) is not str or len(parent) != 64
        ):
            raise ValueError("roster parent")
        created = datetime.fromisoformat(value["created_at"])
        cutoff = datetime.fromisoformat(value["feature_cutoff_at"])
        if (
            created.tzinfo is None
            or cutoff.tzinfo is None
            or created.utcoffset() != UTC.utcoffset(created)
            or cutoff.utcoffset() != UTC.utcoffset(cutoff)
            or cutoff > created
        ):
            raise ValueError("roster timestamp")
        if value["selection_policy"] != SELECTION_POLICY or value["effects"] != EFFECTS:
            raise ValueError("roster authority")
        inventory = value["mapping_inventory"]
        if type(inventory) is not list or inventory != sorted(
            inventory, key=lambda item: item.get("mapping_id", "")
        ):
            raise ValueError("mapping inventory")
        for item in inventory:
            if type(item) is not dict or set(item) != {
                "mapping_id",
                "mapping_sha256",
                "status",
                "current",
            }:
                raise ValueError("mapping inventory")
            if item["status"] not in {"mapped", "unmatched", "ambiguous"}:
                raise ValueError("mapping inventory")
            if type(item["current"]) is not bool:
                raise ValueError("mapping inventory")
            if (
                type(item["mapping_id"]) is not str
                or not 1 <= len(item["mapping_id"]) <= 128
                or type(item["mapping_sha256"]) is not str
                or len(item["mapping_sha256"]) != 64
            ):
                raise ValueError("mapping inventory")
        if len({item["mapping_id"] for item in inventory}) != len(inventory):
            raise ValueError("mapping inventory")
        if value["mapping_inventory_sha256"] != _inventory_hash(inventory):
            raise ValueError("mapping inventory hash")
        expected_exclusions = [
            {
                "mapping_id": item["mapping_id"],
                "mapping_sha256": item["mapping_sha256"],
                "reason": (
                    "stale_dependencies"
                    if not item["current"]
                    else f"status_{item['status']}"
                ),
            }
            for item in inventory
            if item["status"] != "mapped" or not item["current"]
        ]
        if value["exclusions"] != expected_exclusions:
            raise ValueError("mapping exclusions")
        manifest = validate_lineage_manifest(
            value["manifest"], expected_draft_scope_id=value["draft_scope_id"]
        )
        if (
            manifest["manifest_id"] != value["manifest_id"]
            or manifest["revision"] != revision
            or manifest["parent_manifest_sha256"] != parent
            or manifest["created_at"] != value["created_at"]
            or manifest["created_by_id"] != value["created_by_id"]
            or manifest["feature_cutoff_at"] != value["feature_cutoff_at"]
        ):
            raise ValueError("manifest binding")
        included = {
            member["observation_id"]
            for group in manifest["groups"]
            for member in group["members"]
        }
        expected_included = {
            item["mapping_id"]
            for item in inventory
            if item["status"] == "mapped" and item["current"]
        }
        if included != expected_included:
            raise ValueError("manifest inventory binding")
        if value["roster_sha256"] != digest(
            {key: item for key, item in value.items() if key != "roster_sha256"}
        ):
            raise ValueError("roster hash")
        if len(canonical(value)) > MAX_ROSTER_BYTES:
            raise ValueError("roster size")
        return cast(dict[str, Any], value)
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        PricingEvaluationLineageError,
    ) as exc:
        raise DraftScopeError("PRICING_EVALUATION_ROSTER_INVALID", 409) from exc


def _latest_roster(
    db: Session, draft_id: str, *, lock: bool = False
) -> DraftPricingEvaluationRoster | None:
    statement = (
        select(DraftPricingEvaluationRoster)
        .where(DraftPricingEvaluationRoster.draft_scope_id == draft_id)
        .order_by(DraftPricingEvaluationRoster.revision.desc())
        .limit(1)
    )
    return db.scalar(statement.with_for_update() if lock else statement)


def preview_roster(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
    roster_id: str | None = None,
    manifest_id: str | None = None,
    created_at: str | None = None,
    lock: bool = False,
) -> dict[str, Any]:
    actor, _ = _access(db, actor, draft_id)
    inventory, members, exclusions = _mapping_inventory(
        db, actor, draft_id, settings=settings, lock=lock
    )
    latest = _latest_roster(db, draft_id, lock=lock)
    previous = _roster_value(latest) if latest is not None else None
    revision = latest.revision + 1 if latest is not None else 1
    parent = latest.manifest_sha256 if latest is not None else None
    try:
        assignments = assign_target_blind_splits(
            [
                {
                    "observation_id": member["observation_id"],
                    "lineage_keys": member["lineage_keys"],
                }
                for member in members
            ]
        )
    except PricingEvaluationLineageError as exc:
        if "insufficient independent lineage groups" not in str(exc):
            raise DraftScopeError("PRICING_EVALUATION_ROSTER_INVALID", 409) from exc
        return {
            "can_save": False,
            "code": "PRICING_EVALUATION_INSUFFICIENT_GROUPS",
            "revision": revision,
            "mapping_inventory": inventory,
            "mapping_inventory_sha256": _inventory_hash(inventory),
            "eligible_count": len(members),
            "exclusions": exclusions,
        }
    sealed_at = created_at or datetime.now(UTC).isoformat()
    selected_roster_id = roster_id or new_id()
    selected_manifest_id = (
        previous["manifest_id"] if previous is not None else manifest_id or new_id()
    )
    observations = [
        {**member, "split": assignments[member["observation_id"]]} for member in members
    ]
    manifest = build_lineage_manifest(
        manifest_id=selected_manifest_id,
        draft_scope_id=draft_id,
        revision=revision,
        parent_manifest_sha256=parent,
        created_at=sealed_at,
        created_by_id=actor.id,
        feature_cutoff_at=sealed_at,
        observations=observations,
    )
    if previous is not None:
        validate_new_revision(manifest, previous=previous["manifest"])
    roster = {
        "schema_version": SCHEMA,
        "roster_id": selected_roster_id,
        "manifest_id": selected_manifest_id,
        "draft_scope_id": draft_id,
        "revision": revision,
        "parent_manifest_sha256": parent,
        "created_at": sealed_at,
        "created_by_id": actor.id,
        "feature_cutoff_at": sealed_at,
        "selection_policy": SELECTION_POLICY,
        "mapping_inventory": inventory,
        "mapping_inventory_sha256": _inventory_hash(inventory),
        "exclusions": exclusions,
        "manifest": manifest,
        "effects": EFFECTS,
    }
    roster["roster_sha256"] = digest(roster)
    validate_roster(roster)
    return {
        "can_save": True,
        "code": None,
        "revision": revision,
        "eligible_count": len(members),
        "exclusions": exclusions,
        "roster": roster,
        "preview_hash": roster["roster_sha256"],
    }


def _roster_value(row: DraftPricingEvaluationRoster) -> dict[str, Any]:
    try:
        raw = row.roster_json.encode("utf-8")
        value = json.loads(raw)
        validated = validate_roster(value)
        if (
            canonical(validated) != raw
            or hashlib.sha256(raw).hexdigest() != row.roster_sha256
            or validated["roster_id"] != row.id
            or validated["manifest_id"] != row.manifest_id
            or validated["draft_scope_id"] != row.draft_scope_id
            or validated["revision"] != row.revision
            or validated["parent_manifest_sha256"] != row.parent_manifest_sha256
            or validated["mapping_inventory_sha256"] != row.mapping_inventory_sha256
            or validated["manifest"]["manifest_sha256"] != row.manifest_sha256
            or validated["created_by_id"] != row.created_by_id
            or validated["created_at"] != _utc_iso(row.created_at)
            or validated["feature_cutoff_at"] != _utc_iso(row.feature_cutoff_at)
        ):
            raise ValueError("roster binding")
        return validated
    except (
        ValueError,
        TypeError,
        KeyError,
        UnicodeError,
        json.JSONDecodeError,
        DraftScopeError,
    ) as exc:
        raise DraftScopeError("PRICING_EVALUATION_ROSTER_INTEGRITY_FAILED", 409) from exc


def save_roster(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    roster_id: str,
    manifest_id: str,
    created_at: str,
    expected_revision: int,
    expected_parent_manifest_sha256: str | None,
    expected_mapping_inventory_sha256: str,
    expected_preview_hash: str,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, draft = _access(db, actor, draft_id)
        db.scalar(select(DraftScope.id).where(DraftScope.id == draft_id).with_for_update())
        preview = preview_roster(
            db,
            actor,
            draft_id,
            settings=settings,
            roster_id=roster_id,
            manifest_id=manifest_id,
            created_at=created_at,
            lock=True,
        )
        if not preview["can_save"]:
            raise DraftScopeError("PRICING_EVALUATION_INSUFFICIENT_GROUPS", 409)
        roster = preview["roster"]
        created = datetime.fromisoformat(roster["created_at"])
        now = datetime.now(UTC)
        if (
            roster["revision"] != expected_revision
            or roster["parent_manifest_sha256"] != expected_parent_manifest_sha256
            or roster["mapping_inventory_sha256"] != expected_mapping_inventory_sha256
            or roster["roster_sha256"] != expected_preview_hash
            or created < now - PREVIEW_MAX_AGE
            or created > now + PREVIEW_FUTURE_TOLERANCE
        ):
            raise DraftScopeError("PRICING_EVALUATION_ROSTER_CHANGED", 409)
        latest = _latest_roster(db, draft_id, lock=True)
        if (
            latest is not None
            and latest.mapping_inventory_sha256 == roster["mapping_inventory_sha256"]
        ):
            raise DraftScopeError("PRICING_EVALUATION_ROSTER_ALREADY_CURRENT", 409)
        raw = canonical(roster)
        stored = DraftPricingEvaluationRoster(
            id=roster["roster_id"],
            draft_scope_id=draft_id,
            revision=roster["revision"],
            manifest_id=roster["manifest_id"],
            parent_manifest_sha256=roster["parent_manifest_sha256"],
            mapping_inventory_sha256=roster["mapping_inventory_sha256"],
            manifest_sha256=roster["manifest"]["manifest_sha256"],
            feature_cutoff_at=datetime.fromisoformat(roster["feature_cutoff_at"]),
            roster_json=raw.decode("utf-8"),
            roster_sha256=hashlib.sha256(raw).hexdigest(),
            created_by_id=actor.id,
            created_at=created,
            updated_at=created,
        )
        db.add(stored)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.evaluation_roster.save",
            entity_type="draft_pricing_evaluation_roster",
            entity_id=stored.id,
            project_id=draft.project_id,
            new_value={
                "revision": stored.revision,
                "parent_manifest_sha256": stored.parent_manifest_sha256,
                "mapping_inventory_sha256": stored.mapping_inventory_sha256,
                "manifest_sha256": stored.manifest_sha256,
                "roster_sha256": stored.roster_sha256,
                "eligible_count": preview["eligible_count"],
                "excluded_count": len(preview["exclusions"]),
            },
        )
        db.flush()
        return cast(dict[str, Any], roster)


def list_rosters(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
    before_revision: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    actor, _ = _access(db, actor, draft_id)
    if before_revision is not None and (
        type(before_revision) is not int or before_revision < 1
    ):
        raise DraftScopeError("PRICING_EVALUATION_ROSTER_LIST_INVALID", 422)
    if limit is not None and (type(limit) is not int or not 1 <= limit <= 100):
        raise DraftScopeError("PRICING_EVALUATION_ROSTER_LIST_INVALID", 422)
    inventory, _, _ = _mapping_inventory(db, actor, draft_id, settings=settings)
    current_inventory_sha256 = _inventory_hash(inventory)
    latest = _latest_roster(db, draft_id)
    statement = select(DraftPricingEvaluationRoster).where(
        DraftPricingEvaluationRoster.draft_scope_id == draft_id
    )
    if before_revision is not None:
        statement = statement.where(
            DraftPricingEvaluationRoster.revision < before_revision
        )
    statement = statement.order_by(DraftPricingEvaluationRoster.revision.desc())
    if limit is not None:
        statement = statement.limit(limit)
    rows = db.scalars(statement).all()
    result: list[dict[str, Any]] = []
    for row in rows:
        value = _roster_value(row)
        result.append(
            {
                "id": row.id,
                "revision": row.revision,
                "created_at": row.created_at,
                "roster_sha256": row.roster_sha256,
                "manifest_sha256": row.manifest_sha256,
                "mapping_inventory_sha256": row.mapping_inventory_sha256,
                "is_current": latest is not None
                and row.id == latest.id
                and row.mapping_inventory_sha256 == current_inventory_sha256,
                "value": value,
            }
        )
    return result


def roster_bytes(
    db: Session,
    actor: User,
    draft_id: str,
    roster_id: str,
) -> bytes:
    _access(db, actor, draft_id)
    row = db.scalar(
        select(DraftPricingEvaluationRoster).where(
            DraftPricingEvaluationRoster.id == roster_id,
            DraftPricingEvaluationRoster.draft_scope_id == draft_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_EVALUATION_ROSTER_NOT_FOUND", 404)
    value = _roster_value(row)
    return cast(bytes, canonical(value))
