"""Governed review of Dataset A evidence against frozen technical recipes."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    DraftPricingRecipeLink,
    DraftPricingRowObservation,
    DraftScope,
    User,
    new_id,
)
from .draft_pricing_intake import (
    _active_technical_release,
    _row_observation_context,
    _row_observation_value,
    _technical_variant_snapshot,
)
from .draft_pricing_recipe_contract import (
    recipe_link_definition,
    recipe_link_envelope,
    validate_recipe_link_envelope,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft
from .draft_system_match_contract import canonical, digest


def _access(db: Session, actor: User, draft_id: str) -> User:
    get_draft(db, actor, draft_id)
    actor = _actor(db, actor, "pricing:approve")
    return _actor(db, actor, "technical:read")


def _observation_dependency(
    db: Session,
    actor: User,
    row: DraftPricingRowObservation,
    *,
    settings: Settings,
    lock: bool,
) -> dict[str, Any]:
    value = _row_observation_value(row)
    _, source, profile, decision, _, source_row = _row_observation_context(
        db,
        actor,
        row.draft_scope_id,
        row.source_id,
        row.profile_id,
        row.row_number,
        settings=settings,
        lock=lock,
    )
    definition = value["definition"]
    if (
        source.dataset_id != row.dataset_id
        or source.dataset_version != row.dataset_version
        or source.source_sha256 != row.source_sha256
        or profile.profile_sha256 != row.profile_sha256
        or decision.decision_sha256 != row.decision_sha256
        or source_row["sha256"] != row.row_sha256
    ):
        raise DraftScopeError("PRICING_RECIPE_OBSERVATION_STALE", 409)
    return {
        "id": row.id,
        "sha256": row.observation_sha256,
        "dataset_id": row.dataset_id,
        "dataset_version": row.dataset_version,
        "source_sha256": row.source_sha256,
        "profile_sha256": row.profile_sha256,
        "decision_sha256": row.decision_sha256,
        "row_sha256": row.row_sha256,
        "item_kind": row.item_kind,
        "normalized_reference": row.normalized_reference,
        "evidence_state": row.evidence_state,
        "unit": definition["row"]["values"]["unit"],
    }


def _context(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    variant_id: str,
    requirement_id: str,
    observation_ids: list[str],
    *,
    settings: Settings,
    lock: bool,
) -> tuple[User, Any, dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    actor = _access(db, actor, draft_id)
    if len(observation_ids) != len(set(observation_ids)) or len(observation_ids) > 20:
        raise DraftScopeError("PRICING_RECIPE_OBSERVATIONS_INVALID", 422)
    if lock:
        draft = db.scalar(
            select(DraftScope)
            .where(DraftScope.id == draft_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if draft is None:
            raise DraftScopeError("DRAFT_NOT_FOUND", 404)
    actor, release, records, active_ids = _active_technical_release(
        db, actor, release_id, lock=lock
    )
    snapshot = _technical_variant_snapshot(
        db, variant_id, records, active_ids, settings=settings, lock=lock
    )
    recipe = snapshot["release_record"].get("recipe_snapshot")
    if type(recipe) is not dict:
        raise DraftScopeError("PRICING_RECIPE_SNAPSHOT_REQUIRED", 409)
    requirement = next(
        (item for item in recipe["requirements"] if item["id"] == requirement_id),
        None,
    )
    if requirement is None:
        raise DraftScopeError("PRICING_RECIPE_REQUIREMENT_NOT_FOUND", 404)
    statement = (
        select(DraftPricingRowObservation)
        .where(
            DraftPricingRowObservation.draft_scope_id == draft_id,
            DraftPricingRowObservation.id.in_(observation_ids),
        )
        .order_by(DraftPricingRowObservation.id)
    )
    if lock:
        statement = statement.with_for_update()
    rows = list(db.scalars(statement.execution_options(populate_existing=True)).all())
    if len(rows) != len(observation_ids):
        raise DraftScopeError("PRICING_RECIPE_OBSERVATION_NOT_FOUND", 404)
    observations = [
        _observation_dependency(db, actor, row, settings=settings, lock=lock) for row in rows
    ]
    return actor, release, snapshot, requirement, observations


def preview_recipe_link(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    variant_id: str,
    requirement_id: str,
    observation_ids: list[str],
    *,
    status: str,
    unit: str | None,
    quantity_basis: str | None,
    yield_basis: str | None,
    productivity_basis: str | None,
    recovery_boundary: str | None,
    evidence_state: str,
    review_reason: str,
    unresolved_fields: list[str],
    settings: Settings,
) -> dict[str, Any]:
    actor, release, snapshot, requirement, observations = _context(
        db,
        actor,
        draft_id,
        release_id,
        variant_id,
        requirement_id,
        observation_ids,
        settings=settings,
        lock=False,
    )
    recipe = snapshot["release_record"]["recipe_snapshot"]
    try:
        definition = recipe_link_definition(
            draft_scope_id=draft_id,
            technical_release={
                "id": release.id,
                "version": release.version,
                "sha256": release.release_hash,
            },
            technical_target={
                "id": snapshot["id"],
                "snapshot_sha256": snapshot["sha256"],
                "recipe_snapshot_sha256": recipe["sha256"],
            },
            requirement=requirement,
            observations=observations,
            status=status,
            unit=unit,
            quantity_basis=quantity_basis,
            yield_basis=yield_basis,
            productivity_basis=productivity_basis,
            recovery_boundary=recovery_boundary,
            evidence_state=evidence_state,
            review_reason=review_reason,
            unresolved_fields=unresolved_fields,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_RECIPE_LINK_INVALID", 422) from exc
    return {
        "definition": definition,
        "preview_hash": digest(definition),
        "technical_release_sha256": release.release_hash,
        "technical_variant_snapshot_sha256": snapshot["sha256"],
        "recipe_snapshot_sha256": recipe["sha256"],
        "database_write_performed": False,
    }


def save_recipe_link(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    variant_id: str,
    requirement_id: str,
    observation_ids: list[str],
    *,
    status: str,
    unit: str | None,
    quantity_basis: str | None,
    yield_basis: str | None,
    productivity_basis: str | None,
    recovery_boundary: str | None,
    evidence_state: str,
    review_reason: str,
    unresolved_fields: list[str],
    expected_release_sha256: str,
    expected_variant_snapshot_sha256: str,
    expected_recipe_snapshot_sha256: str,
    expected_preview_hash: str,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, release, snapshot, requirement, _ = _context(
            db,
            actor,
            draft_id,
            release_id,
            variant_id,
            requirement_id,
            observation_ids,
            settings=settings,
            lock=True,
        )
        recipe = snapshot["release_record"]["recipe_snapshot"]
        if (
            release.release_hash != expected_release_sha256
            or snapshot["sha256"] != expected_variant_snapshot_sha256
            or recipe["sha256"] != expected_recipe_snapshot_sha256
        ):
            raise DraftScopeError("PRICING_RECIPE_BASIS_CHANGED", 409)
        preview = preview_recipe_link(
            db,
            actor,
            draft_id,
            release_id,
            variant_id,
            requirement_id,
            observation_ids,
            status=status,
            unit=unit,
            quantity_basis=quantity_basis,
            yield_basis=yield_basis,
            productivity_basis=productivity_basis,
            recovery_boundary=recovery_boundary,
            evidence_state=evidence_state,
            review_reason=review_reason,
            unresolved_fields=unresolved_fields,
            settings=settings,
        )
        if preview["preview_hash"] != expected_preview_hash:
            raise DraftScopeError("PRICING_RECIPE_BASIS_CHANGED", 409)
        if (
            db.scalar(
                select(DraftPricingRecipeLink).where(
                    DraftPricingRecipeLink.definition_sha256 == expected_preview_hash
                )
            )
            is not None
        ):
            raise DraftScopeError("PRICING_RECIPE_LINK_REPLAYED", 409)
        reviewed = datetime.now(UTC)
        link_id = new_id()
        envelope = recipe_link_envelope(
            preview["definition"],
            link_id=link_id,
            reviewed_by_id=actor.id,
            reviewed_at=reviewed,
        )
        raw = canonical(envelope)
        interpretation = envelope["definition"]["interpretation"]
        stored = DraftPricingRecipeLink(
            id=link_id,
            draft_scope_id=draft_id,
            technical_release_id=release_id,
            technical_release_sha256=cast(str, release.release_hash),
            technical_variant_id=variant_id,
            technical_variant_snapshot_sha256=snapshot["sha256"],
            recipe_snapshot_sha256=recipe["sha256"],
            requirement_id=requirement["id"],
            requirement_kind=requirement["kind"],
            requirement_path=requirement["path"],
            mapping_status=interpretation["status"],
            evidence_state=interpretation["evidence_state"],
            definition_sha256=expected_preview_hash,
            link_json=raw.decode(),
            link_sha256=hashlib.sha256(raw).hexdigest(),
            reviewed_by_id=actor.id,
            created_at=reviewed,
            updated_at=reviewed,
        )
        db.add(stored)
        draft = get_draft(db, actor, draft_id)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.recipe_link.save",
            entity_type="draft_pricing_recipe_link",
            entity_id=link_id,
            project_id=draft.project_id,
            new_value={
                "technical_release_id": release_id,
                "technical_variant_id": variant_id,
                "requirement_id": requirement_id,
                "status": interpretation["status"],
                "evidence_state": interpretation["evidence_state"],
                "link_sha256": stored.link_sha256,
                "authority_granted": False,
            },
            reason=interpretation["review_reason"],
        )
        db.flush()
        return envelope


def _link_value(row: DraftPricingRecipeLink) -> dict[str, Any]:
    try:
        raw = row.link_json.encode()
        value = json.loads(raw)
        validate_recipe_link_envelope(value)
        definition = value["definition"]
        target = definition["technical_target"]
        requirement = definition["requirement"]
        interpretation = definition["interpretation"]
        created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            len(raw) > 1048576
            or hashlib.sha256(raw).hexdigest() != row.link_sha256
            or value["link_id"] != row.id
            or value["reviewed_by_id"] != row.reviewed_by_id
            or value["reviewed_at"] != created.astimezone(UTC).isoformat()
            or definition["draft_scope_id"] != row.draft_scope_id
            or definition["technical_release"]["id"] != row.technical_release_id
            or definition["technical_release"]["sha256"] != row.technical_release_sha256
            or target["id"] != row.technical_variant_id
            or target["snapshot_sha256"] != row.technical_variant_snapshot_sha256
            or target["recipe_snapshot_sha256"] != row.recipe_snapshot_sha256
            or requirement["id"] != row.requirement_id
            or requirement["kind"] != row.requirement_kind
            or requirement["path"] != row.requirement_path
            or interpretation["status"] != row.mapping_status
            or interpretation["evidence_state"] != row.evidence_state
            or value["definition_sha256"] != row.definition_sha256
        ):
            raise ValueError("recipe link binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_RECIPE_LINK_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def recipe_link_current(
    db: Session,
    actor: User,
    row: DraftPricingRecipeLink,
    *,
    settings: Settings,
    lock: bool = False,
) -> bool:
    try:
        value = _link_value(row)
        definition = value["definition"]
        _, release, snapshot, requirement, observations = _context(
            db,
            actor,
            row.draft_scope_id,
            row.technical_release_id,
            row.technical_variant_id,
            row.requirement_id,
            [item["id"] for item in definition["observations"]],
            settings=settings,
            lock=lock,
        )
        return bool(
            release.release_hash == row.technical_release_sha256
            and snapshot["sha256"] == row.technical_variant_snapshot_sha256
            and snapshot["release_record"]["recipe_snapshot"]["sha256"]
            == row.recipe_snapshot_sha256
            and requirement == definition["requirement"]
            and observations == definition["observations"]
        )
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        return False


def list_recipe_links(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
    release_id: str | None = None,
    variant_id: str | None = None,
) -> list[dict[str, Any]]:
    actor = _access(db, actor, draft_id)
    statement = select(DraftPricingRecipeLink).where(
        DraftPricingRecipeLink.draft_scope_id == draft_id
    )
    if release_id is not None:
        statement = statement.where(DraftPricingRecipeLink.technical_release_id == release_id)
    if variant_id is not None:
        statement = statement.where(DraftPricingRecipeLink.technical_variant_id == variant_id)
    rows = db.scalars(
        statement.order_by(DraftPricingRecipeLink.created_at, DraftPricingRecipeLink.id)
    ).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "current": recipe_link_current(db, actor, row, settings=settings),
            "value": _link_value(row),
        }
        for row in rows
    ]


def recipe_review_context(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    variant_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    actor = _access(db, actor, draft_id)
    actor, release, records, active_ids = _active_technical_release(db, actor, release_id)
    snapshot = _technical_variant_snapshot(
        db, variant_id, records, active_ids, settings=settings, lock=False
    )
    recipe = snapshot["release_record"].get("recipe_snapshot")
    if type(recipe) is not dict:
        raise DraftScopeError("PRICING_RECIPE_SNAPSHOT_REQUIRED", 409)
    rows = db.scalars(
        select(DraftPricingRowObservation)
        .where(DraftPricingRowObservation.draft_scope_id == draft_id)
        .order_by(DraftPricingRowObservation.normalized_reference, DraftPricingRowObservation.id)
    ).all()
    observations = []
    for row in rows:
        try:
            observations.append(
                _observation_dependency(db, actor, row, settings=settings, lock=False)
            )
        except DraftScopeError as exc:
            if exc.code != "PRICING_RECIPE_OBSERVATION_STALE":
                raise
    return {
        "technical_release": {
            "id": release.id,
            "version": release.version,
            "sha256": release.release_hash,
        },
        "technical_target": {
            "id": snapshot["id"],
            "variant_id": snapshot["variant_id"],
            "system_id": snapshot["system_id"],
            "snapshot_sha256": snapshot["sha256"],
        },
        "recipe": recipe,
        "requirements": recipe["requirements"],
        "observations": observations,
        "links": list_recipe_links(
            db,
            actor,
            draft_id,
            settings=settings,
            release_id=release_id,
            variant_id=variant_id,
        ),
    }


def recipe_link_bytes(db: Session, actor: User, draft_id: str, link_id: str) -> bytes:
    _access(db, actor, draft_id)
    row = db.scalar(
        select(DraftPricingRecipeLink).where(
            DraftPricingRecipeLink.id == link_id,
            DraftPricingRecipeLink.draft_scope_id == draft_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_RECIPE_LINK_NOT_FOUND", 404)
    _link_value(row)
    return row.link_json.encode()


__all__ = [
    "list_recipe_links",
    "preview_recipe_link",
    "recipe_link_bytes",
    "recipe_link_current",
    "recipe_review_context",
    "save_recipe_link",
]
