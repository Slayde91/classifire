"""Shared native-history metadata checks, with synthetic saved-generation reads."""

from __future__ import annotations

import copy
from uuid import UUID

import pytest
from test_draft_workspace_chat import case as _case
from test_draft_workspace_chat import scope_app as _scope_app
from test_draft_workspace_chat import scope_password_hash as _password_hash

from classifire.config import Settings
from classifire.models import User
from classifire.services import draft_scope as scopes
from classifire.services import draft_workspace_chat as chat
from classifire.services import draft_workspace_proposals as proposals

case = _case
scope_app = _scope_app
scope_password_hash = _password_hash


def _offer(actor, request, context, payload, settings):
    value = proposals.offer(
        actor,
        request,
        context,
        {"edit_proposal": {"payload": payload, "expected_revision": request.revision}},
        {"synthetic": True},
        settings=settings,
        injected=True,
    )
    assert value is not None
    return value


@pytest.fixture
def document():
    request = chat.WorkspaceChatRequest(
        screen={"name": "scopes"},
        action="propose_scope_edits",
        draft_id=str(UUID(int=1)),
        revision=1,
        ids=[str(UUID(int=2))],
        question="Synthetic metadata check",
        consent=True,
        context_sha256="a" * 64,
    )
    return _offer(
        User(id=str(UUID(int=3))),
        request,
        {"context_sha256": "a" * 64},
        {},
        Settings(_env_file=None),
    )["document"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "unknown-provider"),
        ("provider", None),
        ("provider", []),
        ("model", ""),
        ("model", None),
        ("model", 42),
        ("model", "m" * 201),
        ("generated_at", None),
        ("generated_at", "not-a-time"),
        ("generated_at", "2026-09-15T00:00:00"),
        ("generated_at", "2026-09-15T00:00:00+01:00"),
        ("generated_at", "2026-09-15T00:00:00.000000+00:00"),
    ],
)
def test_invalid_generation_metadata_is_refused(document, field, value):
    document[field] = value
    with pytest.raises(scopes.DraftScopeError, match="CHAT_PROPOSAL_INVALID"):
        proposals._document(document)


@pytest.mark.parametrize(
    "provider,model,stamp",
    [
        ("injected", "application-supplied-port", "2026-09-15T00:00:00+00:00"),
        ("openai", "m", "2026-09-15T00:00:00.123456+00:00"),
        ("openai", "m" * 200, "2026-09-15T00:00:00+00:00"),
    ],
)
def test_valid_metadata_keeps_original_bytes(document, provider, model, stamp):
    document.update(provider=provider, model=model, generated_at=stamp)
    original = copy.deepcopy(document)
    value, raw = proposals._document(document)
    assert value == original
    assert raw == proposals._raw(original)


@pytest.mark.parametrize(
    "field,value",
    [
        ("provider", "unknown-provider"),
        ("model", None),
        ("generated_at", "not-a-time"),
    ],
)
def test_saved_generation_with_matching_hash_still_requires_valid_metadata(case, field, value):
    x = case
    with x.factory() as db:
        actor = db.get(User, x.users["owner"])
        scope = scopes.read_revision(db, actor, x.draft_id)
        request = chat.WorkspaceChatRequest(
            screen={"name": "scopes"},
            action="propose_scope_edits",
            draft_id=x.draft_id,
            revision=scope["revision"],
            ids=[str(UUID(int=3))],
            question="Synthetic unchanged Scope proposal",
            consent=True,
        )
        context = chat.workspace_context(db, actor, request, settings=x.settings)
        request.context_sha256 = context["context_sha256"]
        offer = _offer(actor, request, context, scope["content"], x.settings)
        row = proposals.retain(
            db,
            actor,
            x.draft_id,
            offer["document"],
            offer["authorization"],
            settings=x.settings,
        )
        db.commit()
        identity = row.id
        original_scope = scopes.revision_bytes(db, actor, x.draft_id)
        assert (
            proposals.read_generation(db, actor, x.draft_id, identity, settings=x.settings)[2]
            == offer["document"]
        )
        invalid = copy.deepcopy(offer["document"])
        invalid[field] = value
        row.proposal_json = proposals._raw(invalid)
        row.proposal_sha256 = proposals._hash(row.proposal_json)
        db.commit()
        with pytest.raises(scopes.DraftScopeError, match="CHAT_PROPOSAL_CORRUPT"):
            proposals.read_generation(db, actor, x.draft_id, identity, settings=x.settings)
        assert scopes.revision_bytes(db, actor, x.draft_id) == original_scope
    assert x.port.calls == []
