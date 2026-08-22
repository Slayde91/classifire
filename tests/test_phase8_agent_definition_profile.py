from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "agent-definitions" / "CLASSIFIRE_Agent_Fleet_v1.0"
CONTROLLED_WRITE_TOOLS = {
    "classifire_register_evidence_observations",
    "classifire_submit_initial_physical_model",
    "classifire_select_repair_strategy",
    "classifire_lock_repair_strategy",
    "classifire_derive_quantity_labour",
    "classifire_required_components",
    "classifire_derive_commercial",
}


def _section(source: str, start: str, end: str | None = None) -> str:
    start_index = source.index(start)
    if end is None:
        return source[start_index:]
    return source[start_index : source.index(end, start_index)]


def _mentioned_tools(source: str) -> set[str]:
    return {tool for tool in CONTROLLED_WRITE_TOOLS if tool in source}


def test_phase8_matrix_activates_only_the_physical_admission_tool() -> None:
    source = (FLEET / "TOOL_GRANT_MATRIX.md").read_text(encoding="utf-8")
    active = _section(
        source,
        "## Active Phase 8 admission-only profile",
        "## Retained inactive controlled-write source inventory",
    )
    inactive = _section(
        source,
        "## Retained inactive controlled-write source inventory",
        "## Required delta",
    )

    assert _mentioned_tools(active) == {
        "classifire_submit_initial_physical_model"
    }
    assert _mentioned_tools(inactive) == CONTROLLED_WRITE_TOOLS - {
        "classifire_submit_initial_physical_model"
    }
    assert "classifire_lock_physical_model" in inactive
    assert "retired" in inactive.lower()


def test_role_tool_docs_keep_broader_tools_in_inactive_sections() -> None:
    expectations = {
        "cf-intake-evidence": {"classifire_register_evidence_observations"},
        "cf-physical-model": {
            "classifire_lock_physical_model",
            "classifire_derive_quantity_labour",
        },
        "cf-technical-system": {
            "classifire_select_repair_strategy",
            "classifire_lock_repair_strategy",
        },
        "cf-commercial-engine": {
            "classifire_required_components",
            "classifire_derive_commercial",
        },
    }

    for agent_id, inactive_tools in expectations.items():
        source = (
            FLEET / "agents" / agent_id / "TOOLS.md"
        ).read_text(encoding="utf-8")
        active = _section(
            source,
            "## Currently authorised tools — Phase 8 admission-only profile",
            "## Retained inactive",
        )
        inactive = _section(source, "## Retained inactive")
        assert _mentioned_tools(active) == (
            {"classifire_submit_initial_physical_model"}
            if agent_id == "cf-physical-model"
            else set()
        )
        assert inactive_tools <= set(inactive.split("`"))


def test_physical_workflow_stops_before_lock_in_phase8() -> None:
    for relative_path in (
        "agents/cf-physical-model/AGENTS.md",
        "agents/cf-physical-model/WORKFLOWS.md",
    ):
        source = (FLEET / relative_path).read_text(encoding="utf-8")
        normalized = " ".join(source.split())
        assert "admission-bound initial-submission tool" in normalized
        assert "Do not request a Physical Model Lock" in normalized

    mission_control = (FLEET / "MISSION_CONTROL_UPDATE.md").read_text(
        encoding="utf-8"
    )
    assert "Task D — Admission-bound initial canonical submission" in mission_control
    assert "Task E — Physical Model Lock (inactive and deferred)" in mission_control
    assert "The Phase 8 admission-only profile stops here" in mission_control


def test_agent_definition_profile_matches_plugin_and_installer() -> None:
    plugin = (
        ROOT / "openclaw-plugin-classifire-controlled-write" / "src" / "index.ts"
    ).read_text(encoding="utf-8")
    installer = (
        ROOT / "scripts" / "install_classifire_controlled_write_plugin.ps1"
    ).read_text(encoding="utf-8")

    assert '"phase8-admission-only": new Set([' in plugin
    assert '"classifire_submit_initial_physical_model"' in plugin
    assert "value = 'phase8-admission-only'" in installer
    assert '"cf-physical-model" = @(' in installer
