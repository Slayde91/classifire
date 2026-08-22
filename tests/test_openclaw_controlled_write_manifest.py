from __future__ import annotations

import json
from pathlib import Path

EXPECTED_TOOLS = {
    "classifire_register_evidence_observations",
    "classifire_submit_initial_physical_model",
    "classifire_select_repair_strategy",
    "classifire_lock_repair_strategy",
    "classifire_derive_quantity_labour",
    "classifire_required_components",
    "classifire_derive_commercial",
}


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1] / "openclaw-plugin-classifire-controlled-write"


def test_controlled_write_manifest_declares_every_governed_tool() -> None:
    root = _plugin_root()
    manifest = json.loads((root / "openclaw.plugin.json").read_text(encoding="utf-8"))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    declared = set((manifest.get("contracts") or {}).get("tools") or [])
    metadata = manifest.get("toolMetadata") or {}

    assert declared == EXPECTED_TOOLS
    assert set(metadata) == EXPECTED_TOOLS
    assert all(metadata[name].get("optional") is True for name in EXPECTED_TOOLS)
    assert manifest.get("version") == package.get("version")
    assert package_lock.get("version") == package.get("version")
    assert package_lock["packages"][""]["version"] == package.get("version")
    profile_schema = manifest["configSchema"]["properties"]["deploymentProfile"]
    assert profile_schema["enum"] == [
        "phase8-admission-only",
        "full-controlled-write",
    ]
    assert profile_schema["default"] == "phase8-admission-only"
    assert package["scripts"]["verify:phase8-profile"] == (
        "node scripts/verify-phase8-profile.mjs"
    )
    assert (root / "scripts" / "verify-phase8-profile.mjs").is_file()


def test_phase8_profile_is_fail_closed_while_broader_source_is_preserved() -> None:
    root = _plugin_root()
    source = (root / "src" / "index.ts").read_text(encoding="utf-8")

    assert (
        'const DEFAULT_DEPLOYMENT_PROFILE: DeploymentProfile = '
        '"phase8-admission-only";'
    ) in source
    assert (
        '"phase8-admission-only": new Set([\n'
        '    "classifire_submit_initial_physical_model",\n'
        "  ]),"
    ) in source
    assert '"full-controlled-write": new Set(Object.keys(TOOL_AGENTS))' in source
    assert "if (!activeTools.has(event.toolName))" in source
    assert "if (!activeTools.has(name))" in source
    assert "Object.prototype.hasOwnProperty.call" in source
    assert "Unsupported CLASSIFIRE deploymentProfile" in source

    for tool_name in EXPECTED_TOOLS:
        assert f'    register(\n      "{tool_name}"' in source


def test_initial_physical_submission_is_admission_bound_and_lock_free() -> None:
    root = _plugin_root()
    source = (root / "src" / "index.ts").read_text(encoding="utf-8")

    assert (
        'classifire_submit_initial_physical_model: new Set(["cf-physical-model"])'
        in source
    )
    assert "cf-adjudicated-physical-writer" not in source
    assert "classifire_lock_physical_model" not in source
    assert "/physical-model/lock" not in source
    assert (
        "/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}"
        "/physical-model/initial"
    ) in source
    assert "admission_id: Type.String({ minLength: 36, maxLength: 100 })" in source
    assert "idempotency_key: Type.String({ minLength: 16, maxLength: 200 })" in source
    assert "}, { additionalProperties: false })" in source
    assert "params.openings" not in source
    assert "params.services" not in source
    assert (
        "body: JSON.stringify({\n"
        "            admission_id: params.admission_id,\n"
        "            idempotency_key: params.idempotency_key,\n"
        "          }),"
    ) in source
