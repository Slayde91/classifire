"""Explicit retention of native AI proposals, independent of Scope confirmation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from itsdangerous import BadData, URLSafeTimedSerializer
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..config import Settings
from ..models import (
    DraftScope,
    DraftScopeRevision,
    DraftWorkspaceProposal,
    DraftWorkspaceProposalDecision,
    User,
    new_id,
)
from . import draft_workspace_chat as chat
from .draft_scope import DraftScopeError, _actor, _atomic, get_draft, read_revision

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


def read_generation(
    db: Session, actor: User, draft_id: str, identity: str, *, settings: Settings
) -> tuple[DraftScope, DraftWorkspaceProposal, dict[str, Any]]:
    """Read only the verified generation; a later decision is an independent record."""
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
    return draft, row, document


def reopen(
    db: Session, actor: User, draft_id: str, identity: str, *, settings: Settings
) -> dict[str, Any]:
    draft, row, document = read_generation(db, actor, draft_id, identity, settings=settings)
    request = chat.parse_workspace(document["request"])
    decision = read_decision(db, actor, draft_id, row)
    can_review = False
    if decision is None and draft.latest_revision == row.base_revision:
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
        "decision": decision,
        "can_reject": decision is None and _can_write(db, actor, draft_id),
        "notice": (
            (
                "You rejected this saved proposal. Rejection did not change Scope."
                if decision["outcome"] == "rejected"
                else f"You confirmed reviewed Scope revision {decision['scope_revision']}. "
                "The original generated proposal remains separate from your reviewed result."
            )
            if decision
            else (
                (
                    "Saved AI proposal, not a saved Scope change. "
                    "Review and confirmation remain separate."
                )
                if can_review
                else (
                    "Historical proposal only. Inputs or permissions changed; "
                    "its save controls are unavailable."
                )
            )
        ),
    }


DECISION_SCHEMA = "CLASSIFIRE-NATIVE-PROPOSAL-DECISION-v1"


def _can_write(db: Session, actor: User, draft_id: str) -> bool:
    try:
        _owner(db, actor, draft_id, write=True)
    except DraftScopeError:
        return False
    return True


def read_decision(
    db: Session, actor: User, draft_id: str, proposal: DraftWorkspaceProposal
) -> dict[str, Any] | None:
    """Verify an explicitly linked decision; never infer one from later revisions."""
    _owner(db, actor, draft_id)
    if proposal.draft_scope_id != draft_id or proposal.created_by_id != actor.id:
        raise DraftScopeError("CHAT_PROPOSAL_NOT_FOUND", 404)
    row = db.scalar(
        select(DraftWorkspaceProposalDecision)
        .where(DraftWorkspaceProposalDecision.proposal_id == proposal.id)
        .execution_options(populate_existing=True)
    )
    if row is None:
        return None
    try:
        document: dict[str, Any] = json.loads(row.decision_json)
        expected = {
            "schema",
            "id",
            "proposal_id",
            "proposal_sha256",
            "actor_id",
            "draft_id",
            "outcome",
            "decided_at",
            "base_revision",
            "scope_revision",
            "scope_sha256",
            "reviewed_payload_sha256",
            "proposal_payload_changed",
        }
        if (
            set(document) != expected
            or type(document["base_revision"]) is not int
            or _raw(document) != row.decision_json
            or _hash(row.decision_json) != row.decision_sha256
            or document["schema"] != DECISION_SCHEMA
            or (
                document["id"],
                document["proposal_id"],
                document["proposal_sha256"],
                document["actor_id"],
                document["draft_id"],
                document["outcome"],
                document["base_revision"],
            )
            != (
                row.id,
                proposal.id,
                proposal.proposal_sha256,
                actor.id,
                draft_id,
                row.outcome,
                proposal.base_revision,
            )
            or row.created_by_id != actor.id
            or datetime.fromisoformat(document["decided_at"]) != row.created_at.replace(tzinfo=UTC)
        ):
            raise ValueError("binding")
        if row.outcome == "confirmed":
            # Reopening has verified the immutable generation. Check the derived claim,
            # not just the decision's own checksum and the type of its changed flag.
            original = json.loads(proposal.proposal_json)
            prepared = original["response"][
                "edit_proposal"
                if original["request"]["action"] == "propose_scope_edits"
                else "proposal"
            ]
            reviewed_hash = document["reviewed_payload_sha256"]
            revision = db.get(DraftScopeRevision, row.scope_revision_id, populate_existing=True)
            if revision is None or (
                revision.draft_scope_id != draft_id
                or revision.created_by_id != actor.id
                or revision.revision != proposal.base_revision + 1
                or type(document["scope_revision"]) is not int
                or document["scope_revision"] != revision.revision
                or document["scope_sha256"] != _hash(revision.envelope_json)
                or type(document["proposal_payload_changed"]) is not bool
                or not isinstance(reviewed_hash, str)
                or re.fullmatch(r"[0-9a-f]{64}", reviewed_hash) is None
                or document["proposal_payload_changed"]
                != (reviewed_hash != _hash(_raw(prepared["payload"])))
            ):
                raise ValueError("revision")
            read_revision(db, actor, draft_id, revision.revision)
        elif (
            row.outcome != "rejected"
            or row.scope_revision_id is not None
            or any(
                document[k] is not None
                for k in (
                    "scope_revision",
                    "scope_sha256",
                    "reviewed_payload_sha256",
                    "proposal_payload_changed",
                )
            )
        ):
            raise ValueError("outcome")
        return document
    except (ValueError, TypeError, KeyError, AttributeError, DraftScopeError) as exc:
        raise DraftScopeError("CHAT_PROPOSAL_DECISION_CORRUPT", 409) from exc


@dataclass(frozen=True)
class ReviewLink:
    proposal_id: str
    draft_id: str
    actor_id: str
    base_revision: int
    proposal_sha256: str
    reviewed_payload_sha256: str
    proposal_payload_changed: bool


def prepare_review_link(
    db: Session,
    actor: User,
    draft_id: str,
    identity: str | None,
    expected_revision: int,
    payload: dict[str, Any],
    *,
    action: str,
    source_id: str | None = None,
    settings: Settings,
) -> ReviewLink | None:
    """Lock and verify an optional saved proposal before the existing Scope writer."""
    if identity is None:
        return None
    try:
        if str(UUID(identity)) != identity:
            raise ValueError("identity")
    except (ValueError, TypeError, AttributeError) as exc:
        raise DraftScopeError("CHAT_PROPOSAL_INVALID", 422) from exc
    _owner(db, actor, draft_id, write=True)
    # Shared source review and retention lock source bytes before the Draft.
    # Preserve that order, then recheck the proposal after taking its write locks.
    read_generation(db, actor, draft_id, identity, settings=settings)
    db.scalar(select(DraftScope).where(DraftScope.id == draft_id).with_for_update())
    row = db.scalar(
        select(DraftWorkspaceProposal)
        .where(
            DraftWorkspaceProposal.id == identity,
            DraftWorkspaceProposal.draft_scope_id == draft_id,
            DraftWorkspaceProposal.created_by_id == actor.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise DraftScopeError("CHAT_PROPOSAL_NOT_FOUND", 404)
    value = reopen(db, actor, draft_id, identity, settings=settings)
    if value["decision"] is not None:
        raise DraftScopeError("CHAT_PROPOSAL_ALREADY_DECIDED", 409)
    if not value["can_review"] or row.base_revision != expected_revision:
        raise DraftScopeError("CHAT_CONTEXT_CHANGED", 409)
    document = value["document"]
    if document["request"]["action"] != action:
        raise DraftScopeError("CHAT_PROPOSAL_REVIEW_MISMATCH", 409)
    prepared = document["response"].get(
        "edit_proposal" if action == "propose_scope_edits" else "proposal"
    )
    if not prepared or prepared.get("source_id") != source_id:
        raise DraftScopeError("CHAT_PROPOSAL_REVIEW_MISMATCH", 409)
    reviewed = _hash(_raw(payload))
    return ReviewLink(
        row.id,
        draft_id,
        actor.id,
        expected_revision,
        row.proposal_sha256,
        reviewed,
        reviewed != _hash(_raw(prepared["payload"])),
    )


def _record_decision(
    db: Session,
    actor: User,
    proposal: DraftWorkspaceProposal,
    *,
    revision: DraftScopeRevision | None = None,
    link: ReviewLink | None = None,
) -> DraftWorkspaceProposalDecision:
    outcome = "confirmed" if revision is not None else "rejected"
    now = datetime.now(UTC)
    identity = new_id()
    document = {
        "schema": DECISION_SCHEMA,
        "id": identity,
        "proposal_id": proposal.id,
        "proposal_sha256": proposal.proposal_sha256,
        "actor_id": actor.id,
        "draft_id": proposal.draft_scope_id,
        "outcome": outcome,
        "decided_at": now.isoformat(),
        "base_revision": proposal.base_revision,
        "scope_revision": revision.revision if revision else None,
        "scope_sha256": _hash(revision.envelope_json) if revision else None,
        "reviewed_payload_sha256": link.reviewed_payload_sha256 if link else None,
        "proposal_payload_changed": link.proposal_payload_changed if link else None,
    }
    raw = _raw(document)
    row = DraftWorkspaceProposalDecision(
        id=identity,
        created_at=now,
        updated_at=now,
        proposal_id=proposal.id,
        created_by_id=actor.id,
        outcome=outcome,
        scope_revision_id=revision.id if revision else None,
        decision_json=raw,
        decision_sha256=_hash(raw),
    )
    db.add(row)
    record_audit(
        db,
        actor=actor,
        action="workspace_proposal." + outcome,
        entity_type="draft_workspace_proposal",
        entity_id=proposal.id,
        new_value={
            "decision_id": row.id,
            "decision_sha256": row.decision_sha256,
            "scope_revision": document["scope_revision"],
        },
    )
    db.flush()
    return row


def record_confirmation(db: Session, actor: User, link: ReviewLink | None) -> None:
    """Join the caller's Scope-save transaction; never execute a Scope writer."""
    if link is None:
        return
    _owner(db, actor, link.draft_id, write=True)
    proposal = db.get(DraftWorkspaceProposal, link.proposal_id, populate_existing=True)
    revision = db.scalar(
        select(DraftScopeRevision)
        .where(
            DraftScopeRevision.draft_scope_id == link.draft_id,
            DraftScopeRevision.revision == link.base_revision + 1,
        )
        .execution_options(populate_existing=True)
    )
    if (
        proposal is None
        or revision is None
        or actor.id != link.actor_id
        or proposal.created_by_id != actor.id
        or proposal.draft_scope_id != link.draft_id
        or proposal.base_revision != link.base_revision
        or revision.created_by_id != actor.id
        or proposal.proposal_sha256 != link.proposal_sha256
    ):
        raise DraftScopeError("CHAT_PROPOSAL_REVIEW_MISMATCH", 409)
    if (
        db.scalar(
            select(DraftWorkspaceProposalDecision.id).where(
                DraftWorkspaceProposalDecision.proposal_id == proposal.id
            )
        )
        is not None
    ):
        raise DraftScopeError("CHAT_PROPOSAL_ALREADY_DECIDED", 409)
    _record_decision(db, actor, proposal, revision=revision, link=link)


def reject(db: Session, actor: User, draft_id: str, identity: str, *, settings: Settings) -> None:
    """Explicit human rejection closes a proposal without writing any Scope revision."""
    _owner(db, actor, draft_id, write=True)
    with _atomic(db):
        # Match retention and Scope review: source bytes, then Draft decision locks.
        read_generation(db, actor, draft_id, identity, settings=settings)
        db.scalar(select(DraftScope).where(DraftScope.id == draft_id).with_for_update())
        opened = reopen(db, actor, draft_id, identity, settings=settings)
        if opened["decision"] is not None:
            raise DraftScopeError("CHAT_PROPOSAL_ALREADY_DECIDED", 409)
        proposal = db.get(DraftWorkspaceProposal, identity)
        if proposal is None:
            raise DraftScopeError("CHAT_PROPOSAL_NOT_FOUND", 404)
        _record_decision(db, actor, proposal)
