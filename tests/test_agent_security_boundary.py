from __future__ import annotations

import pytest
from fastapi import HTTPException
from physical_foundation_support import physical_session
from starlette.requests import Request

from classifire.agent_security import (
    AGENT_SCOPE_MAP,
    authenticate_agent,
    provision_agent_principal,
    require_agent_scope,
    scopes_for_agent,
)
from classifire.api.agent_api import agent_health
from classifire.models import AgentServicePrincipal


def _request(agent_id: str, token: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "headers": [
                (b"x-classifire-agent-id", agent_id.encode("ascii")),
                (b"authorization", f"Bearer {token}".encode("ascii")),
            ],
        }
    )


def test_layer_three_scope_map_is_read_only_for_physical_agents() -> None:
    assert AGENT_SCOPE_MAP["cf-physical-model"] == frozenset(
        {"health:read", "workflow:read", "evidence:read", "physical:read"}
    )
    all_scopes = set().union(*AGENT_SCOPE_MAP.values())
    assert {"physical:write", "physical:lock", "estimate:approve"}.isdisjoint(all_scopes)
    assert AGENT_SCOPE_MAP["cf-adjudicated-physical-writer"] == frozenset(
        {"health:read", "workflow:read", "physical:adjudicated:submit"}
    )
    assert scopes_for_agent("cf-adjudicated-physical-writer") == [
        "health:read",
        "physical:adjudicated:submit",
        "workflow:read",
    ]


def test_agent_token_is_hashed_and_requires_server_and_persisted_scope() -> None:
    with physical_session() as db:
        principal, token = provision_agent_principal(
            db, agent_id="cf-physical-model", display_name="Physical review"
        )
        assert token not in principal.token_hash
        assert principal.token_hint == token[-8:]
        assert db.get(AgentServicePrincipal, principal.id) is not None

        authenticated = authenticate_agent(_request(principal.agent_id, token), db)
        assert authenticated.id == principal.id
        assert agent_health(principal)["physical_mutation_exposed"] is False

        dependency = require_agent_scope("physical:read")
        assert dependency(principal).id == principal.id
        principal.scopes = ["health:read"]
        with pytest.raises(HTTPException) as denied:
            dependency(principal)
        assert denied.value.status_code == 403


def test_unknown_or_invalid_agent_credentials_fail_closed() -> None:
    with physical_session() as db:
        principal, token = provision_agent_principal(db, agent_id="cf-orchestrator")
        with pytest.raises(HTTPException) as wrong_token:
            authenticate_agent(_request(principal.agent_id, token + "x"), db)
        assert wrong_token.value.status_code == 401

        with pytest.raises(HTTPException) as unknown_agent:
            authenticate_agent(_request("cf-unknown", token), db)
        assert unknown_agent.value.status_code == 401
