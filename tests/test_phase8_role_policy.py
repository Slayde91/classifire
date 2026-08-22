from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from classifire.agent_security import (
    AGENT_SCOPE_MAP,
    require_agent_scope,
)


def test_physical_role_has_only_the_admission_bound_mutation_scope() -> None:
    scopes = AGENT_SCOPE_MAP["cf-physical-model"]

    assert "physical:write" not in scopes
    assert "physical:lock" not in scopes
    assert "physical:adjudicated:submit" in scopes
    assert "quantity:derive" not in scopes
    assert "cf-adjudicated-physical-writer" not in AGENT_SCOPE_MAP

    for agent_id, agent_scopes in AGENT_SCOPE_MAP.items():
        assert "quantity:derive" not in agent_scopes, agent_id
        if agent_id != "cf-physical-model":
            assert "physical:adjudicated:submit" not in agent_scopes, agent_id


def test_stale_physical_quantity_scope_fails_closed() -> None:
    dependency = require_agent_scope("quantity:derive")

    principal = SimpleNamespace(
        agent_id="cf-physical-model",
        scopes=[
            "quantity:derive",
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        dependency(principal)

    assert exc_info.value.status_code == 403

    assert exc_info.value.detail == "Agent scope required: quantity:derive"
