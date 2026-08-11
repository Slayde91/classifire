from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from classifire.agent_security import AGENT_SCOPE_MAP, FORBIDDEN_AGENT_SCOPES


def test_physical_model_agent_can_read_evidence_without_intake_write_authority() -> None:
    scopes = AGENT_SCOPE_MAP["cf-physical-model"]
    assert "evidence:read" in scopes
    assert "evidence:write" not in scopes
    assert not (scopes & FORBIDDEN_AGENT_SCOPES)


def test_validator_can_read_evidence_and_physical_model_without_upstream_write_authority() -> None:
    scopes = AGENT_SCOPE_MAP["cf-validator"]
    assert {"evidence:read", "physical:read", "validation:run"} <= scopes
    assert "evidence:write" not in scopes
    assert "physical:write" not in scopes
    assert "physical:lock" not in scopes
    assert "technical:select" not in scopes
    assert "technical:lock" not in scopes
    assert "commercial:derive" not in scopes
    assert "snapshot:lock" not in scopes
    assert not (scopes & FORBIDDEN_AGENT_SCOPES)


def test_openclaw_read_plugin_allows_validator_read_only_visual_review() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "openclaw-plugin-classifire"
        / "src"
        / "index.ts"
    ).read_text(encoding="utf-8")

    evidence_expected = (
        'classifire_evidence_read: new Set(["cf-intake-evidence", "cf-physical-model", "cf-validator"])'
    )
    physical_expected = (
        'classifire_physical_model_read: new Set(["cf-physical-model", "cf-validator"])'
    )
    assert evidence_expected in source
    assert physical_expected in source
    assert 'classifire_evidence_read: new Set(["cf-intake-evidence", "cf-physical-model"])' not in source
    assert 'classifire_physical_model_read: new Set(["cf-physical-model"])' not in source


def test_openclaw_installer_grants_validator_only_required_visual_read_tools() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "install_classifire_openclaw_plugin.ps1"
    ).read_text(encoding="utf-8")
    start = source.index('"cf-validator" = @(')
    end = source.index("\n    )", start)
    block = source[start:end]

    for tool in (
        "classifire_health",
        "classifire_workflow_status",
        "classifire_evidence_read",
        "classifire_physical_model_read",
        "classifire_run_validation",
        "pdf",
        "image",
    ):
        assert f'"{tool}"' in block

    for forbidden in (
        "classifire_register_evidence_observations",
        "classifire_submit_initial_physical_model",
        "classifire_lock_physical_model",
        "classifire_select_repair_strategy",
        "classifire_lock_repair_strategy",
        "classifire_derive_commercial",
        "classifire_lock_snapshot",
    ):
        assert forbidden not in block


def test_scope_sync_standalone_import_loads_audit_trail_table() -> None:
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "sync_classifire_agent_scopes.py"
    probe = (
        "import importlib.util; "
        f"p={str(script)!r}; "
        "s=importlib.util.spec_from_file_location('scope_sync_probe', p); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "from classifire.db import Base; "
        "assert 'audit_trails' in Base.metadata.tables, sorted(Base.metadata.tables)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
