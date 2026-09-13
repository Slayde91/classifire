"""Explicit retention of native AI proposals, independent of Scope confirmation."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import DraftScope, DraftWorkspaceProposal, User, new_id
from . import draft_workspace_chat as chat
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft

MAX_BYTES = 1048576
SCHEMA = "CLASSIFIRE-NATIVE-PROPOSAL-v1"
ACTIONS = {"propose_word_scope", "propose_pdf_scope", "propose_xlsx_scope", "propose_scope_edits"}


def _raw(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _signer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        settings.secret_key,
        salt="native-proposal-retention-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def offer(
    actor: User,
    request: chat.WorkspaceChatRequest,
    context: dict[str, Any],
    response: dict[str, Any],
    model_response: dict[str, Any],
    *,
    settings: Settings,
    injected: bool,
) -> dict[str, Any] | None:
    """Issue a bounded save authorization; no persistence and no source-file body."""
    if request.action not in ACTIONS or not (
        response.get("proposal") or response.get("edit_proposal")
    ):
        return None
    document = {
        "schema": SCHEMA,
        "id": new_id(),
        "actor_id": actor.id,
        "draft_id": request.draft_id,
        "base_revision": request.revision,
        "generated_at": datetime.now(UTC).isoformat(),
        "provider": "injected" if injected else "openai",
        "model": "application-supplied-port" if injected else settings.workspace_chat_model,
        "request": request.model_dump(mode="json"),
        "context": context,
        "model_response": model_response,
        "response": response,
    }
    raw = _raw(document)
    if len(raw.encode()) > MAX_BYTES:
        return None
    return {
        "document": document,
        "authorization": _signer(settings).dumps(
            {"sha256": _hash(raw), "actor_id": actor.id, "draft_id": request.draft_id}
        ),
    }


def _document(value: Any) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "id",
        "actor_id",
        "draft_id",
        "base_revision",
        "generated_at",
        "provider",
        "model",
        "request",
        "context",
        "model_response",
        "response",
    }:
        raise DraftScopeError("CHAT_PROPOSAL_INVALID", 422)
    try:
        raw = _raw(value)
        if (
            value["schema"] != SCHEMA
            or len(raw.encode()) > MAX_BYTES
            or any(str(UUID(value[k])) != value[k] for k in ("id", "actor_id", "draft_id"))
        ):
            raise ValueError("binding")
        request = chat.parse_workspace(value["request"])
        if (
            request.action not in ACTIONS
            or request.draft_id != value["draft_id"]
            or request.revision != value["base_revision"]
            or request.context_sha256 != value["context"]["context_sha256"]
        ):
            raise ValueError("request")
        if not (value["response"].get("proposal") or value["response"].get("edit_proposal")):
            raise ValueError("proposal")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise DraftScopeError("CHAT_PROPOSAL_INVALID", 422) from exc
    return value, raw


def _owner(db: Session, actor: User, draft_id: str, *, write: bool = False) -> DraftScope:
    _actor(db, actor, "project:write" if write else "project:read")
    draft = get_draft(db, actor, draft_id)
    if draft.owner_user_id != actor.id:
        raise DraftScopeError("DRAFT_NOT_FOUND", 404)
    return draft


def retain(
    db: Session, actor: User, draft_id: str, value: Any, authorization: str, *, settings: Settings
) -> DraftWorkspaceProposal:
    document, raw = _document(value)
    _owner(db, actor, draft_id, write=True)
    if document["actor_id"] != actor.id or document["draft_id"] != draft_id:
        raise DraftScopeError("CHAT_PROPOSAL_INVALID", 422)
    try:
        signed = _signer(settings).loads(authorization, max_age=900)
        if signed != {"sha256": _hash(raw), "actor_id": actor.id, "draft_id": draft_id}:
            raise BadData("binding")
    except BadData as exc:
        raise DraftScopeError("CHAT_PROPOSAL_AUTHORIZATION_EXPIRED_OR_CHANGED", 409) from exc
    request = chat.parse_workspace(document["request"])
    if chat.workspace_context(db, actor, request, settings=settings) != document["context"]:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    with _atomic(db):
        # Serializes duplicate clicks and the bounded per-Draft retention quota.
        db.scalar(select(DraftScope).where(DraftScope.id == draft_id).with_for_update())
        if chat.workspace_context(db, actor, request, settings=settings) != document["context"]:
            raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
        existing = db.get(DraftWorkspaceProposal, document["id"])
        if existing is not None:
            if (
                existing.created_by_id != actor.id
                or existing.draft_scope_id != draft_id
                or existing.proposal_sha256 != _hash(raw)
                or existing.proposal_json != raw
            ):
                raise DraftScopeError("CHAT_PROPOSAL_CORRUPT", 409)
            return existing
        count = (
            db.scalar(
                select(func.count())
                .select_from(DraftWorkspaceProposal)
                .where(DraftWorkspaceProposal.draft_scope_id == draft_id)
            )
            or 0
        )
        if count >= 100:
            raise DraftScopeError("CHAT_PROPOSAL_LIMIT", 429)
        row = DraftWorkspaceProposal(
            id=document["id"],
            draft_scope_id=draft_id,
            created_by_id=actor.id,
            base_revision=document["base_revision"],
            proposal_json=raw,
            proposal_sha256=_hash(raw),
        )
        db.add(row)
        db.flush()
        record_audit(
            db,
            actor=actor,
            action="workspace_proposal.retain",
            entity_type="draft_workspace_proposal",
            entity_id=row.id,
            new_value={"proposal_sha256": row.proposal_sha256, "base_revision": row.base_revision},
        )
        return row


def list_saved(db: Session, actor: User, draft_id: str) -> list[dict[str, Any]]:
    _owner(db, actor, draft_id)
    rows = db.scalars(
        select(DraftWorkspaceProposal)
        .where(
            DraftWorkspaceProposal.draft_scope_id == draft_id,
            DraftWorkspaceProposal.created_by_id == actor.id,
        )
        .order_by(DraftWorkspaceProposal.created_at.desc(), DraftWorkspaceProposal.id)
        .limit(100)
    )
    return [
        {"id": row.id, "base_revision": row.base_revision, "saved_at": row.created_at.isoformat()}
        for row in rows
    ]


def reopen(
    db: Session, actor: User, draft_id: str, identity: str, *, settings: Settings
) -> dict[str, Any]:
    draft = _owner(db, actor, draft_id)
    row = db.get(DraftWorkspaceProposal, identity, populate_existing=True)
    if row is None or row.created_by_id != actor.id or row.draft_scope_id != draft_id:
        raise DraftScopeError("CHAT_PROPOSAL_NOT_FOUND", 404)
    if (
        len(row.proposal_json.encode()) > MAX_BYTES
        or _hash(row.proposal_json) != row.proposal_sha256
    ):
        raise DraftScopeError("CHAT_PROPOSAL_CORRUPT", 409)
    try:
        document, raw = _document(json.loads(row.proposal_json))
        if raw != row.proposal_json or (
            document["id"],
            document["actor_id"],
            document["draft_id"],
            document["base_revision"],
        ) != (row.id, actor.id, draft_id, row.base_revision):
            raise ValueError("binding")
    except (ValueError, DraftScopeError) as exc:
        raise DraftScopeError("CHAT_PROPOSAL_CORRUPT", 409) from exc
    request = chat.parse_workspace(document["request"])
    # Historical context still needs fresh rights, retained-source integrity and a clean scan.
    chat.workspace_context(
        db, actor, request.model_copy(update={"action": "advice"}), settings=settings
    )
    can_review = False
    if draft.latest_revision == row.base_revision:
        try:
            can_review = (
                chat.workspace_context(db, actor, request, settings=settings) == document["context"]
            )
        except DraftScopeError:
            pass
    return {
        "document": document,
        "sha256": row.proposal_sha256,
        "can_review": can_review,
        "notice": (
            "Saved AI proposal, not a saved Scope change. Review and confirmation remain separate."
        )
        if can_review
        else (
            "Historical proposal only. Inputs or permissions changed; "
            "its save controls are unavailable."
        ),
    }
