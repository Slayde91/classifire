from __future__ import annotations

import json
from pathlib import Path

TOOL = "classifire_submit_initial_physical_model"


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1] / "openclaw-plugin-classifire-controlled-write"


def test_manifest_exposes_only_the_admission_writer_tool() -> None:
    root = _plugin_root()
    manifest = json.loads((root / "openclaw.plugin.json").read_text(encoding="utf-8"))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    assert manifest["contracts"]["tools"] == [TOOL]
    assert set(manifest["toolMetadata"]) == {TOOL}
    assert manifest["toolMetadata"][TOOL]["optional"] is True
    assert manifest["version"] == package["version"]
    assert package_lock["version"] == package["version"]
    assert package_lock["packages"][""]["version"] == package["version"]


def test_plugin_accepts_no_physical_payload_and_exposes_no_lock_tool() -> None:
    source = (_plugin_root() / "src" / "index.ts").read_text(encoding="utf-8")

    assert 'const WRITER_AGENT_ID = "cf-adjudicated-physical-writer"' in source
    assert "admission_id: Type.String({ minLength: 36, maxLength: 100 })" in source
    assert "idempotency_key: Type.String({ minLength: 16, maxLength: 200 })" in source
    assert "additionalProperties: false" in source
    assert "/api/v1/agent/physical-model/initial" in source
    assert "params.openings" not in source
    assert "params.services" not in source
    assert "classifire_lock_physical_model" not in source
    assert "/physical-model/lock" not in source
