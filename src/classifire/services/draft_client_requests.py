"""Durable proposals from an authenticated client; human sessions execute commands."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..draft_client_auth import (
    EXPORT,
    WRITE,
    ClientAuthority,
    ClientIdentity,
    stored_identity,
)
from ..models import DraftClientRequest, User, new_id
from . import draft_project_packages as packages
from . import draft_scope as scopes


def _json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _payload(row: DraftClientRequest) -> dict[str, Any]:
    if hashlib.sha256(row.payload_json.encode()).hexdigest() != row.payload_hash:
        raise scopes.DraftScopeError("CLIENT_REQUEST_CORRUPT", 409)
    value = json.loads(row.payload_json)
    if not isinstance(value, dict):
        raise scopes.DraftScopeError("CLIENT_REQUEST_CORRUPT", 409)
    return value


def _owner(db: Session, actor: User, draft_id: str) -> None:
    # External clients are owner-only even when the mapped human is an administrator.
    if scopes.get_draft(db, actor, draft_id).owner_user_id != actor.id:
        raise scopes.DraftScopeError("DRAFT_NOT_FOUND", 404)


def authorize(
    db: Session,
    authority: ClientAuthority,
    identity: ClientIdentity,
    scope: str,
    draft_id: str | None = None,
) -> User:
    actor = authority.actor(db, identity, scope)
    scopes._actor(db, actor, "project:write" if scope == WRITE else "project:read")
    if draft_id is not None:
        _owner(db, actor, draft_id)
    return actor


def prepare(
    db: Session,
    authority: ClientAuthority,
    identity: ClientIdentity,
    command: str,
    payload: dict[str, Any],
) -> DraftClientRequest:
    actor = authorize(db, authority, identity, WRITE)
    if command == "create":
        if set(payload) != {"reference", "name"} or any(
            not isinstance(payload[k], str) or not 1 <= len(payload[k].strip()) <= limit
            for k, limit in (("reference", 100), ("name", 300))
        ):
            raise scopes.DraftScopeError("DRAFT_PROJECT_INVALID")
    elif command == "edit":
        if set(payload) != {"draft_id", "expected_revision", "content"}:
            raise scopes.DraftScopeError("CLIENT_REQUEST_INVALID")
        _owner(db, actor, payload["draft_id"])
        current = scopes.read_revision(db, actor, payload["draft_id"])
        if (
            type(payload["expected_revision"]) is not int
            or current["revision"] != payload["expected_revision"]
        ):
            raise scopes.DraftScopeError("DRAFT_REVISION_CONFLICT", 409)
        scopes.validate_payload(payload["content"])
    elif command == "package":
        if set(payload) != {"draft_id", "selection"}:
            raise scopes.DraftScopeError("CLIENT_REQUEST_INVALID")
        authorize(db, authority, identity, EXPORT, payload["draft_id"])
        preview = packages.preview(db, actor, payload["draft_id"], payload["selection"])
        payload = payload | {
            "preview_hash": preview["preview_hash"],
            "expected_revision": preview["latest_revision"],
        }
    else:
        raise scopes.DraftScopeError("CLIENT_REQUEST_INVALID")
    raw = _json(payload)
    if len(raw.encode()) > 1048576:
        raise scopes.DraftScopeError("CLIENT_REQUEST_TOO_LARGE", 413)
    pending = (
        db.scalar(
            select(func.count())
            .select_from(DraftClientRequest)
            .where(
                DraftClientRequest.owner_user_id == actor.id,
                DraftClientRequest.status == "pending",
                DraftClientRequest.expires_at > datetime.now(UTC),
            )
        )
        or 0
    )
    if pending >= 100:
        raise scopes.DraftScopeError("CLIENT_PENDING_LIMIT", 429)
    row = DraftClientRequest(
        id=new_id(),
        owner_user_id=actor.id,
        command=command,
        payload_json=raw,
        payload_hash=hashlib.sha256(raw.encode()).hexdigest(),
        identity_json=_json(identity.as_dict()),
        expires_at=datetime.fromtimestamp(identity.expires_at, UTC),
        status="pending",
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor=actor,
        action="draft_client.propose",
        entity_type="draft_client_request",
        entity_id=row.id,
        new_value={
            "command": command,
            "payload_hash": row.payload_hash,
            "client_id": identity.client_id,
        },
    )
    db.flush()
    return row


def read_request(db: Session, actor: User, request_id: str) -> DraftClientRequest:
    scopes._actor(db, actor, "project:read")
    row = db.get(DraftClientRequest, request_id, populate_existing=True)
    if row is None or row.owner_user_id != actor.id:
        raise scopes.DraftScopeError("CLIENT_REQUEST_NOT_FOUND", 404)
    _payload(row)
    return row


def review(db: Session, authority: ClientAuthority, actor: User, request_id: str) -> dict[str, Any]:
    row = read_request(db, actor, request_id)
    identity = stored_identity(row.identity_json)
    if identity.user_id != actor.id:
        raise scopes.DraftScopeError("CLIENT_REQUEST_CORRUPT", 409)
    if row.status == "pending":
        authorize(db, authority, identity, WRITE)
    payload = _payload(row)
    previous = None
    proposed = None
    findings: list[dict[str, str]] = []
    if row.command == "edit":
        _owner(db, actor, payload["draft_id"])
        previous = scopes.read_revision(db, actor, payload["draft_id"])
        content, findings = scopes.validate_payload(payload["content"])
        proposed = {"content": content.model_dump(mode="json")}
    elif row.command == "package":
        authorize(db, authority, identity, EXPORT, payload["draft_id"])
        packages.preview(db, actor, payload["draft_id"], payload["selection"])
    return {
        "row": row,
        "payload": payload,
        "previous": previous,
        "proposed": proposed,
        "findings": findings,
        "client_id": identity.client_id,
        "result": json.loads(row.result_json) if row.result_json else None,
    }


def decide(
    db: Session,
    authority: ClientAuthority,
    actor: User,
    request_id: str,
    payload_hash: str,
    confirm: bool,
) -> dict[str, Any]:
    info = review(db, authority, actor, request_id)
    row, payload = info["row"], info["payload"]
    if row.payload_hash != payload_hash:
        raise scopes.DraftScopeError("CLIENT_REVIEW_CHANGED", 409)
    if row.status != "pending":
        raise scopes.DraftScopeError("CLIENT_REQUEST_ALREADY_DECIDED", 409)
    with scopes._atomic(db):
        changed = db.execute(
            update(DraftClientRequest)
            .where(
                DraftClientRequest.id == row.id,
                DraftClientRequest.status == "pending",
                DraftClientRequest.payload_hash == payload_hash,
            )
            .values(status="confirmed" if confirm else "rejected")
            .execution_options(synchronize_session=False)
        )
        if changed.rowcount != 1:  # type: ignore[attr-defined]
            raise scopes.DraftScopeError("CLIENT_REQUEST_ALREADY_DECIDED", 409)
        result: dict[str, Any] = {"status": "rejected"}
        if confirm:
            if row.command == "create":
                draft = scopes.create_draft_project(
                    db, actor, payload["reference"], payload["name"]
                )
                result = {"draft_id": draft.id, "revision": draft.latest_revision}
            elif row.command == "edit":
                saved = scopes.save_revision(
                    db, actor, payload["draft_id"], payload["expected_revision"], payload["content"]
                )
                result = {
                    "draft_id": saved["artifact_id"],
                    "revision": saved["revision"],
                    "sha256": saved["sha256"],
                }
            elif row.command == "package":
                saved_package = packages.create_package(
                    db,
                    actor,
                    payload["draft_id"],
                    payload["selection"],
                    payload["expected_revision"],
                    payload["preview_hash"],
                )
                result = {
                    "draft_id": payload["draft_id"],
                    "package_id": saved_package.id,
                    "revision": saved_package.revision,
                    "sha256": saved_package.archive_hash,
                }
            result["status"] = "confirmed"
        db.execute(
            update(DraftClientRequest)
            .where(DraftClientRequest.id == row.id)
            .values(result_json=_json(result))
        )
        record_audit(
            db,
            actor=actor,
            action="draft_client.confirm" if confirm else "draft_client.reject",
            entity_type="draft_client_request",
            entity_id=row.id,
            new_value={"payload_hash": payload_hash, "result": result},
        )
        db.flush()
    return result
