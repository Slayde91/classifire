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
