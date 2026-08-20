from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AgentServicePrincipal

TOKEN_PREFIX = "cfa_"  # noqa: S105 - identifier prefix, not a credential.

# Layer 3 identities remain read-only except for the dedicated Layer 5 writer,
# whose single scope can consume a pre-registered signed admission. It cannot
# accept raw physical facts or create a Physical Model Lock.
AGENT_SCOPE_MAP: dict[str, frozenset[str]] = {
    "cf-orchestrator": frozenset({"health:read", "workflow:read"}),
    "cf-intake-evidence": frozenset({"health:read", "workflow:read", "evidence:read"}),
    "cf-physical-model": frozenset(
        {"health:read", "workflow:read", "evidence:read", "physical:read"}
    ),
    "cf-validator": frozenset({"health:read", "workflow:read", "evidence:read", "physical:read"}),
    "cf-adjudicated-physical-writer": frozenset(
        {"health:read", "workflow:read", "physical:adjudicated:submit"}
    ),
    "cf-library-governance": frozenset({"health:read", "workflow:read"}),
    "cf-platform-governance": frozenset({"health:read", "workflow:read"}),
}

FORBIDDEN_AGENT_SCOPES = frozenset(
    {
        "estimate:approve",
        "human_release",
        "physical:lock",
        "physical:write",
        "release:approve",
    }
)


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_agent_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def scopes_for_agent(agent_id: str) -> list[str]:
    scopes = AGENT_SCOPE_MAP.get(agent_id)
    if scopes is None:
        raise ValueError(f"Unknown controlled CLASSIFIRE agent id: {agent_id}")
    if scopes & FORBIDDEN_AGENT_SCOPES:
        raise ValueError(f"Forbidden scope configured for agent {agent_id}")
    return sorted(scopes)


def provision_agent_principal(
    db: Session, *, agent_id: str, display_name: str | None = None
) -> tuple[AgentServicePrincipal, str]:
    """Create or rotate one credential and return its plaintext value once."""
    token = generate_agent_token()
    principal = db.scalar(
        select(AgentServicePrincipal).where(AgentServicePrincipal.agent_id == agent_id)
    )
    now = datetime.now(UTC)
    if principal is None:
        principal = AgentServicePrincipal(
            agent_id=agent_id,
            display_name=display_name or agent_id,
            token_hash=hash_agent_token(token),
            token_hint=token[-8:],
            scopes=scopes_for_agent(agent_id),
            is_active=True,
            rotated_at=now,
        )
        db.add(principal)
    else:
        principal.display_name = display_name or principal.display_name
        principal.token_hash = hash_agent_token(token)
        principal.token_hint = token[-8:]
        principal.scopes = scopes_for_agent(agent_id)
        principal.is_active = True
        principal.rotated_at = now
        principal.record_version += 1
    db.flush()
    return principal, token


def _bearer_token(request: Request) -> str:
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent bearer token required",
        )
    return token.strip()


def authenticate_agent(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> AgentServicePrincipal:
    agent_id = (request.headers.get("X-Classifire-Agent-ID") or "").strip()
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-Classifire-Agent-ID header required",
        )
    principal = db.scalar(
        select(AgentServicePrincipal).where(
            AgentServicePrincipal.agent_id == agent_id,
            AgentServicePrincipal.is_active.is_(True),
        )
    )
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown agent")
    if not hmac.compare_digest(hash_agent_token(_bearer_token(request)), principal.token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")
    principal.last_used_at = datetime.now(UTC)
    return principal


def require_agent_scope(scope: str) -> Callable[..., AgentServicePrincipal]:
    if scope in FORBIDDEN_AGENT_SCOPES:
        raise ValueError(f"Forbidden agent scope cannot be exposed: {scope}")

    def dependency(
        principal: Annotated[AgentServicePrincipal, Depends(authenticate_agent)],
    ) -> AgentServicePrincipal:
        configured = AGENT_SCOPE_MAP.get(principal.agent_id, frozenset())
        persisted = set(principal.scopes or [])
        if scope not in configured or scope not in persisted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent scope required: {scope}",
            )
        return principal

    return dependency


__all__ = [
    "AGENT_SCOPE_MAP",
    "FORBIDDEN_AGENT_SCOPES",
    "authenticate_agent",
    "generate_agent_token",
    "hash_agent_token",
    "provision_agent_principal",
    "require_agent_scope",
    "scopes_for_agent",
]
