from __future__ import annotations

from pathlib import Path

import pytest

from classifire.agent_security import scopes_for_agent

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = ROOT / "openclaw-plugin-classifire-controlled-write" / "src" / "index.ts"


def test_only_physical_model_receives_the_adjudicated_submit_scope() -> None:
    physical_scopes = scopes_for_agent("cf-physical-model")

    assert "physical:adjudicated:submit" in physical_scopes
    assert "physical:write" not in physical_scopes
    assert "physical:lock" not in physical_scopes

    with pytest.raises(ValueError, match="Unknown controlled CLASSIFIRE agent id"):
        scopes_for_agent("cf-adjudicated-physical-writer")


def test_plugin_defaults_to_the_admission_only_physical_profile() -> None:
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")

    assert 'DEFAULT_DEPLOYMENT_PROFILE: DeploymentProfile = "phase8-admission-only"' in source
    assert 'classifire_submit_initial_physical_model: new Set(["cf-physical-model"])' in source
    assert '"phase8-admission-only": new Set([' in source
    assert '"classifire_submit_initial_physical_model",' in source
    assert '"full-controlled-write": new Set(Object.keys(TOOL_AGENTS))' in source
