from __future__ import annotations

from pathlib import Path

from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES


def test_physical_model_agent_can_read_evidence_without_intake_write_authority() -> None:
    scopes = AGENT_SCOPE_MAP["cf-physical-model"]
    assert "evidence:read" in scopes
    assert "evidence:write" not in scopes
    assert not (scopes & FORBIDDEN_AGENT_SCOPES)


def test_openclaw_read_plugin_allows_evidence_for_intake_and_physical_only() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "openclaw-plugin-classifire"
        / "src"
        / "index.ts"
    ).read_text(encoding="utf-8")

    expected = (
        'classifire_evidence_read: new Set(["cf-intake-evidence", "cf-physical-model"])'
    )
    assert expected in source
    assert 'classifire_evidence_read: new Set(["cf-intake-evidence"])' not in source
