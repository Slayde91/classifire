from __future__ import annotations

import json
from pathlib import Path

TOOL = "classifire_submit_initial_physical_model"
SOURCE_TOOLS = [
    "classifire_register_evidence_observations",
    TOOL,
    "classifire_select_repair_strategy",
    "classifire_lock_repair_strategy",
    "classifire_derive_quantity_labour",
    "classifire_required_components",
    "classifire_derive_commercial",
]


def _plugin_root() -> Path:
    return Path(__file__).resolve().parents[1] / "openclaw-plugin-classifire-controlled-write"


def test_manifest_preserves_source_contracts_but_defaults_to_admission_only() -> None:
    root = _plugin_root()
    manifest = json.loads((root / "openclaw.plugin.json").read_text(encoding="utf-8"))
    package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    package_lock = json.loads((root / "package-lock.json").read_text(encoding="utf-8"))

    assert manifest["contracts"]["tools"] == SOURCE_TOOLS
    assert set(manifest["toolMetadata"]) == set(SOURCE_TOOLS)
    assert manifest["toolMetadata"][TOOL]["optional"] is True
    profile = manifest["configSchema"]["properties"]["deploymentProfile"]
    assert profile["default"] == "phase8-admission-only"
    assert profile["enum"] == ["phase8-admission-only", "full-controlled-write"]
    assert manifest["version"] == package["version"]
    assert package_lock["version"] == package["version"]
    assert package_lock["packages"][""]["version"] == package["version"]


def test_plugin_admission_profile_accepts_no_physical_payload_or_lock_tool() -> None:
    source = (_plugin_root() / "src" / "index.ts").read_text(encoding="utf-8")

    assert 'classifire_submit_initial_physical_model: new Set(["cf-physical-model"])' in source
    assert '"phase8-admission-only": new Set([' in source
    assert "admission_id: Type.String({ minLength: 36, maxLength: 100 })" in source
    assert "idempotency_key: Type.String({ minLength: 16, maxLength: 200 })" in source
    assert "estimate_id: Type.String()" in source
    assert "additionalProperties: false" in source
    estimate_bound_route = (
        "/api/v1/agent/estimates/${encodeURIComponent(params.estimate_id)}"
        "/physical-model/initial"
    )
    assert estimate_bound_route in source
    assert "params.openings" not in source
    assert "params.services" not in source
    assert "classifire_lock_physical_model" not in source
    assert "/physical-model/lock" not in source
