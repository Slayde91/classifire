from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AgentServicePrincipal

TOKEN_PREFIX = "cfa_"

AGENT_SCOPE_MAP: dict[str, set[str]] = {
    "cf-orchestrator": {"health:read", "workflow:read"},
    "cf-intake-evidence": {
        "health:read",
        "workflow:read",
        "evidence:read",
        "evidence:write",
    },
    "cf-physical-model": {
        "health:read",
        "workflow:read",
        "evidence:read",
        "physical:read",
        # This scope can execute only a pre-existing signed admission. It
        # cannot submit arbitrary topology or create a physical-model lock.
        "physical:adjudicated:submit",
    },
    "cf-technical-system": {
        "health:read",
        "workflow:read",
        "technical:search",
        "technical:select",
        "technical:lock",
    },
    "cf-commercial-engine": {
        "health:read",
        "workflow:read",
        "commercial:recommend",
        "commercial:components",
        "commercial:derive",
    },
    "cf-validator": {
        "health:read",
        "workflow:read",
        "evidence:read",
        "physical:read",
        "validation:run",
    },
    "cf-output": {"health:read", "workflow:read", "snapshot:lock", "output:render"},
    "cf-library-governance": {"health:read", "workflow:read", "library:read"},
    "cf-platform-governance": {"health:read", "workflow:read"},
}

# Human Release is intentionally not a machine scope and must never be added here.
FORBIDDEN_AGENT_SCOPES = {"human_release", "estimate:approve", "release:approve"}


def hash_agent_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_agent_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def scopes_for_agent(agent_id: str) -> list[str]:
    scopes = AGENT_SCOPE_MAP.get(agent_id)
    if scopes is None:
        raise ValueError(f"Unknown controlled CLASSIFIRE agent id: {agent_id}")
    if scopes & FORBIDDEN_AGENT_SCOPES:
        raise ValueError(f"Forbidden human-release scope configured for {agent_id}")
    return sorted(scopes)


def provision_agent_principal(
    db: Session,
    *,
    agent_id: str,
    display_name: str | None = None,
) -> tuple[AgentServicePrincipal, str]:
    """Create or rotate one controlled agent credential and return plaintext once."""

    token = generate_agent_token()
    token_hash = hash_agent_token(token)
    now = datetime.now(timezone.utc)
    principal = db.scalar(
        select(AgentServicePrincipal).where(AgentServicePrincipal.agent_id == agent_id)
    )
    if principal is None:
        principal = AgentServicePrincipal(
            agent_id=agent_id,
            display_name=display_name or agent_id,
            token_hash=token_hash,
            token_hint=token[-8:],
            scopes=scopes_for_agent(agent_id),
            is_active=True,
            rotated_at=now,
        )
        db.add(principal)
    else:
        principal.display_name = display_name or principal.display_name or agent_id
        principal.token_hash = token_hash
        principal.token_hint = token[-8:]
        principal.scopes = scopes_for_agent(agent_id)
        principal.is_active = True
        principal.rotated_at = now
        principal.record_version += 1
    db.flush()
    return principal, token


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Agent bearer token required",
        )
    return token.strip()


def authenticate_agent(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
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

    token = _bearer_token(request)
    supplied_hash = hash_agent_token(token)
    if not hmac.compare_digest(supplied_hash, principal.token_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid agent token")

    principal.last_used_at = datetime.now(timezone.utc)
    return principal


def require_agent_scope(scope: str) -> Callable[..., AgentServicePrincipal]:
    if scope in FORBIDDEN_AGENT_SCOPES:
        raise ValueError(f"Forbidden agent scope cannot be exposed: {scope}")

    def dependency(
        principal: Annotated[AgentServicePrincipal, Depends(authenticate_agent)],
    ) -> AgentServicePrincipal:
        configured_scopes = AGENT_SCOPE_MAP.get(principal.agent_id)

        if configured_scopes is None or scope not in configured_scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Agent scope required: {scope}",
            )

        scopes = set(principal.scopes or [])

        if scope not in scopes:
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
