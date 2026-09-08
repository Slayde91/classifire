"""Governed project quantities bound to current Scope and frozen recipe evidence."""

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
    DraftPricingQuantityBasis,
    DraftPricingRecipeLink,
    DraftScope,
    User,
    new_id,
)
from .draft_pricing_quantity_contract import (
    quantity_basis_definition,
    quantity_basis_envelope,
    validate_quantity_basis_envelope,
)
from .draft_pricing_recipes import (
    _link_value,
    recipe_link_current,
    recipe_review_context,
)
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft, read_revision
from .draft_system_match_contract import canonical, digest


def _access(db: Session, actor: User, draft_id: str) -> User:
    get_draft(db, actor, draft_id)
    actor = _actor(db, actor, "pricing:approve")
    return _actor(db, actor, "technical:read")


def _latest_recipe_link(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    requirement_id: str,
    *,
    settings: Settings,
    lock: bool,
) -> tuple[DraftPricingRecipeLink, dict[str, Any]]:
    statement = (
        select(DraftPricingRecipeLink)
        .where(
            DraftPricingRecipeLink.draft_scope_id == draft_id,
            DraftPricingRecipeLink.technical_release_id == release_id,
            DraftPricingRecipeLink.technical_variant_id == target_id,
            DraftPricingRecipeLink.requirement_id == requirement_id,
        )
        .order_by(DraftPricingRecipeLink.created_at.desc(), DraftPricingRecipeLink.id.desc())
        .limit(1)
    )
    if lock:
        statement = statement.with_for_update()
    row = db.scalar(statement.execution_options(populate_existing=True))
    if row is None:
        raise DraftScopeError("PRICING_QUANTITY_RECIPE_LINK_REQUIRED", 409)
    value = _link_value(row)
    interpretation = value["definition"]["interpretation"]
    if (
        not recipe_link_current(db, actor, row, settings=settings, lock=lock)
        or interpretation["status"] != "linked"
        or interpretation["unit"] is None
    ):
        raise DraftScopeError("PRICING_QUANTITY_RECIPE_LINK_REQUIRED", 409)
    return row, value


def _context(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    requirement_id: str,
    scope_revision: int,
    scope_service_id: str,
    *,
    settings: Settings,
    lock: bool,
) -> tuple[
    User,
    DraftScope,
    dict[str, Any],
    dict[str, Any],
    DraftPricingRecipeLink,
    dict[str, Any],
]:
    actor = _access(db, actor, draft_id)
    draft_statement = select(DraftScope).where(DraftScope.id == draft_id)
    if lock:
        draft_statement = draft_statement.with_for_update()
    draft = db.scalar(draft_statement.execution_options(populate_existing=True))
    if draft is None:
        raise DraftScopeError("DRAFT_NOT_FOUND", 404)
    if type(scope_revision) is not int or scope_revision != draft.latest_revision:
        raise DraftScopeError("PRICING_QUANTITY_SCOPE_STALE", 409)
    scope = read_revision(db, actor, draft_id, scope_revision)
    service = next(
        (item for item in scope["content"]["services"] if str(item["id"]) == scope_service_id),
        None,
    )
    if service is None:
        raise DraftScopeError("PRICING_QUANTITY_SCOPE_SERVICE_NOT_FOUND", 404)
    if service["quantity"] is None:
        raise DraftScopeError("PRICING_QUANTITY_SCOPE_VALUE_REQUIRED", 422)
    link, link_value = _latest_recipe_link(
        db,
        actor,
        draft_id,
        release_id,
        target_id,
        requirement_id,
        settings=settings,
        lock=lock,
    )
    definition = link_value["definition"]
    if service["unit"] != definition["interpretation"]["unit"]:
        raise DraftScopeError("PRICING_QUANTITY_UNIT_MISMATCH", 422)
    return actor, draft, scope, service, link, link_value


def preview_quantity_basis(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    requirement_id: str,
    scope_revision: int,
    scope_service_id: str,
    review_reason: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    actor, _, scope, service, link, link_value = _context(
        db,
        actor,
        draft_id,
        release_id,
        target_id,
        requirement_id,
        scope_revision,
        scope_service_id,
        settings=settings,
        lock=False,
    )
    link_definition = link_value["definition"]
    try:
        definition = quantity_basis_definition(
            draft_scope_id=draft_id,
            scope={
                "revision": scope["revision"],
                "sha256": scope["sha256"],
                "service": {
                    key: service[key] for key in ("id", "label", "quantity", "unit", "state")
                },
            },
            technical_release=link_definition["technical_release"],
            technical_target=link_definition["technical_target"],
            recipe_link={"id": link.id, "sha256": link.link_sha256},
            requirement=link_definition["requirement"],
            quantity=service["quantity"],
            unit=service["unit"],
            evidence_state=service["state"],
            review_reason=review_reason,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise DraftScopeError("PRICING_QUANTITY_BASIS_INVALID", 422) from exc
    return {
        "definition": definition,
        "preview_hash": digest(definition),
        "scope_sha256": scope["sha256"],
        "recipe_link_sha256": link.link_sha256,
        "database_write_performed": False,
    }


def save_quantity_basis(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    requirement_id: str,
    scope_revision: int,
    scope_service_id: str,
    review_reason: str,
    *,
    expected_scope_sha256: str,
    expected_recipe_link_sha256: str,
    expected_preview_hash: str,
    settings: Settings,
) -> dict[str, Any]:
    with _atomic(db):
        actor, draft, scope, service, link, link_value = _context(
            db,
            actor,
            draft_id,
            release_id,
            target_id,
            requirement_id,
            scope_revision,
            scope_service_id,
            settings=settings,
            lock=True,
        )
        if (
            scope["sha256"] != expected_scope_sha256
            or link.link_sha256 != expected_recipe_link_sha256
        ):
            raise DraftScopeError("PRICING_QUANTITY_BASIS_CHANGED", 409)
        preview = preview_quantity_basis(
            db,
            actor,
            draft_id,
            release_id,
            target_id,
            requirement_id,
            scope_revision,
            scope_service_id,
            review_reason,
            settings=settings,
        )
        if preview["preview_hash"] != expected_preview_hash:
            raise DraftScopeError("PRICING_QUANTITY_BASIS_CHANGED", 409)
        if (
            db.scalar(
                select(DraftPricingQuantityBasis).where(
                    DraftPricingQuantityBasis.definition_sha256 == expected_preview_hash
                )
            )
            is not None
        ):
            raise DraftScopeError("PRICING_QUANTITY_BASIS_REPLAYED", 409)
        reviewed = datetime.now(UTC)
        basis_id = new_id()
        envelope = quantity_basis_envelope(
            preview["definition"],
            basis_id=basis_id,
            reviewed_by_id=actor.id,
            reviewed_at=reviewed,
        )
        raw = canonical(envelope)
        target = link_value["definition"]["technical_target"]
        requirement = link_value["definition"]["requirement"]
        stored = DraftPricingQuantityBasis(
            id=basis_id,
            draft_scope_id=draft_id,
            scope_revision=scope_revision,
            scope_sha256=scope["sha256"],
            scope_service_id=str(service["id"]),
            technical_release_id=release_id,
            technical_release_sha256=link.technical_release_sha256,
            technical_variant_id=target_id,
            technical_variant_snapshot_sha256=target["snapshot_sha256"],
            recipe_snapshot_sha256=target["recipe_snapshot_sha256"],
            recipe_link_id=link.id,
            recipe_link_sha256=link.link_sha256,
            requirement_id=requirement["id"],
            requirement_kind=requirement["kind"],
            requirement_path=requirement["path"],
            quantity=service["quantity"],
            unit=service["unit"],
            definition_sha256=expected_preview_hash,
            basis_json=raw.decode(),
            basis_sha256=hashlib.sha256(raw).hexdigest(),
            reviewed_by_id=actor.id,
            created_at=reviewed,
            updated_at=reviewed,
        )
        db.add(stored)
        record_audit(
            db,
            actor=actor,
            action="draft_pricing.quantity_basis.save",
            entity_type="draft_pricing_quantity_basis",
            entity_id=basis_id,
            project_id=draft.project_id,
            new_value={
                "scope_revision": scope_revision,
                "scope_sha256": scope["sha256"],
                "scope_service_id": str(service["id"]),
                "technical_release_id": release_id,
                "technical_variant_id": target_id,
                "requirement_id": requirement_id,
                "quantity": service["quantity"],
                "unit": service["unit"],
                "basis_sha256": stored.basis_sha256,
                "authority_granted": False,
            },
            reason=review_reason.strip(),
        )
        db.flush()
        return envelope


def _basis_value(row: DraftPricingQuantityBasis) -> dict[str, Any]:
    try:
        raw = row.basis_json.encode()
        value = json.loads(raw)
        validate_quantity_basis_envelope(value)
        definition = value["definition"]
        scope = definition["scope"]
        target = definition["technical_target"]
        requirement = definition["requirement"]
        basis = definition["quantity_basis"]
        created = (
            row.created_at.replace(tzinfo=UTC) if row.created_at.tzinfo is None else row.created_at
        )
        if (
            len(raw) > 1048576
            or hashlib.sha256(raw).hexdigest() != row.basis_sha256
            or value["basis_id"] != row.id
            or value["reviewed_by_id"] != row.reviewed_by_id
            or value["reviewed_at"] != created.astimezone(UTC).isoformat()
            or definition["draft_scope_id"] != row.draft_scope_id
            or scope["revision"] != row.scope_revision
            or scope["sha256"] != row.scope_sha256
            or str(scope["service"]["id"]) != row.scope_service_id
            or definition["technical_release"]["id"] != row.technical_release_id
            or definition["technical_release"]["sha256"] != row.technical_release_sha256
            or target["id"] != row.technical_variant_id
            or target["snapshot_sha256"] != row.technical_variant_snapshot_sha256
            or target["recipe_snapshot_sha256"] != row.recipe_snapshot_sha256
            or definition["recipe_link"]["id"] != row.recipe_link_id
            or definition["recipe_link"]["sha256"] != row.recipe_link_sha256
            or requirement["id"] != row.requirement_id
            or requirement["kind"] != row.requirement_kind
            or requirement["path"] != row.requirement_path
            or basis["quantity"] != row.quantity
            or basis["unit"] != row.unit
            or value["definition_sha256"] != row.definition_sha256
        ):
            raise ValueError("quantity basis binding")
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
        raise DraftScopeError("PRICING_QUANTITY_BASIS_INTEGRITY_FAILED", 409) from exc
    return cast(dict[str, Any], value)


def quantity_basis_current(
    db: Session,
    actor: User,
    row: DraftPricingQuantityBasis,
    *,
    settings: Settings,
) -> bool:
    try:
        value = _basis_value(row)
        latest_id = db.scalar(
            select(DraftPricingQuantityBasis.id)
            .where(
                DraftPricingQuantityBasis.draft_scope_id == row.draft_scope_id,
                DraftPricingQuantityBasis.technical_release_id == row.technical_release_id,
                DraftPricingQuantityBasis.technical_variant_id == row.technical_variant_id,
                DraftPricingQuantityBasis.requirement_id == row.requirement_id,
            )
            .order_by(
                DraftPricingQuantityBasis.created_at.desc(),
                DraftPricingQuantityBasis.id.desc(),
            )
            .limit(1)
        )
        if latest_id != row.id:
            return False
        definition = value["definition"]
        actor, _, scope, service, link, link_value = _context(
            db,
            actor,
            row.draft_scope_id,
            row.technical_release_id,
            row.technical_variant_id,
            row.requirement_id,
            row.scope_revision,
            row.scope_service_id,
            settings=settings,
            lock=False,
        )
        del actor
        return bool(
            scope["sha256"] == row.scope_sha256
            and {key: service[key] for key in ("id", "label", "quantity", "unit", "state")}
            == definition["scope"]["service"]
            and link.id == row.recipe_link_id
            and link.link_sha256 == row.recipe_link_sha256
            and link_value["definition"]["requirement"] == definition["requirement"]
        )
    except DraftScopeError as exc:
        if exc.status_code == 403:
            raise
        return False


def list_quantity_bases(
    db: Session,
    actor: User,
    draft_id: str,
    *,
    settings: Settings,
    release_id: str | None = None,
    target_id: str | None = None,
) -> list[dict[str, Any]]:
    actor = _access(db, actor, draft_id)
    statement = select(DraftPricingQuantityBasis).where(
        DraftPricingQuantityBasis.draft_scope_id == draft_id
    )
    if release_id is not None:
        statement = statement.where(DraftPricingQuantityBasis.technical_release_id == release_id)
    if target_id is not None:
        statement = statement.where(DraftPricingQuantityBasis.technical_variant_id == target_id)
    rows = db.scalars(
        statement.order_by(DraftPricingQuantityBasis.created_at, DraftPricingQuantityBasis.id)
    ).all()
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "current": quantity_basis_current(db, actor, row, settings=settings),
            "sha256": row.basis_sha256,
            "value": _basis_value(row),
        }
        for row in rows
    ]


def current_quantity_bases(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    *,
    settings: Settings,
) -> dict[str, dict[str, Any]]:
    history = list_quantity_bases(
        db,
        actor,
        draft_id,
        settings=settings,
        release_id=release_id,
        target_id=target_id,
    )
    return {
        item["value"]["definition"]["requirement"]["id"]: item
        for item in history
        if item["current"]
    }


def quantity_review_context(
    db: Session,
    actor: User,
    draft_id: str,
    release_id: str,
    target_id: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    actor = _access(db, actor, draft_id)
    scope = read_revision(db, actor, draft_id)
    recipe = recipe_review_context(db, actor, draft_id, release_id, target_id, settings=settings)
    history = list_quantity_bases(
        db,
        actor,
        draft_id,
        settings=settings,
        release_id=release_id,
        target_id=target_id,
    )
    links: dict[str, dict[str, Any]] = {}
    for item in recipe["links"]:
        links[item["value"]["definition"]["requirement"]["id"]] = item
    requirements = []
    for requirement in recipe["requirements"]:
        link = links.get(requirement["id"])
        unit = (
            link["value"]["definition"]["interpretation"]["unit"]
            if link is not None and link["current"]
            else None
        )
        bases = [
            item
            for item in history
            if item["value"]["definition"]["requirement"]["id"] == requirement["id"]
        ]
        requirements.append(
            {
                **requirement,
                "unit": unit,
                "services": [
                    item
                    for item in scope["content"]["services"]
                    if item["quantity"] is not None and item["unit"] == unit
                ],
                "bases": bases,
                "current_basis": next((item for item in reversed(bases) if item["current"]), None),
            }
        )
    return {
        "scope": {"revision": scope["revision"], "sha256": scope["sha256"]},
        "technical_release": recipe["technical_release"],
        "technical_target": recipe["technical_target"],
        "requirements": requirements,
    }


def quantity_basis_bytes(db: Session, actor: User, draft_id: str, basis_id: str) -> bytes:
    _access(db, actor, draft_id)
    row = db.scalar(
        select(DraftPricingQuantityBasis).where(
            DraftPricingQuantityBasis.id == basis_id,
            DraftPricingQuantityBasis.draft_scope_id == draft_id,
        )
    )
    if row is None:
        raise DraftScopeError("PRICING_QUANTITY_BASIS_NOT_FOUND", 404)
    _basis_value(row)
    return row.basis_json.encode()


__all__ = [
    "current_quantity_bases",
    "list_quantity_bases",
    "preview_quantity_basis",
    "quantity_basis_bytes",
    "quantity_basis_current",
    "quantity_review_context",
    "save_quantity_basis",
]
