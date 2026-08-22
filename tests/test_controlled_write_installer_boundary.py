from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_classifire_controlled_write_plugin.ps1"
BOUNDARY_TEST = ROOT / "scripts" / "test_classifire_controlled_write_boundaries.ps1"


def _section(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end, source.index(start))]


def test_installer_assigns_physical_agent_only_the_bound_submit_tool() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    required_scopes = _section(
        source,
        "$requiredScopes = @{",
        "foreach ($agentId in $requiredScopes.Keys)",
    )
    add_by_agent = _section(source, "$addByAgent = @{", "$managedAgentIds = @(")
    current_tools = _section(
        source,
        "$allControlledWriteTools = @(",
        "$retiredControlledWriteTools",
    )

    assert '"cf-physical-model" = @("physical:adjudicated:submit")' in required_scopes
    assert "cf-intake-evidence" not in required_scopes
    assert "cf-technical-system" not in required_scopes
    assert "cf-commercial-engine" not in required_scopes
    assert '"cf-physical-model" = @("physical:write", "physical:lock")' not in required_scopes
    assert '"cf-physical-model" = @(' in add_by_agent
    assert '"classifire_submit_initial_physical_model"' in add_by_agent
    assert "cf-intake-evidence" not in add_by_agent
    assert "cf-technical-system" not in add_by_agent
    assert "cf-commercial-engine" not in add_by_agent
    assert "cf-adjudicated-physical-writer" not in source
    assert '"classifire_lock_physical_model"' not in current_tools
    assert "config.deploymentProfile'" in source
    assert "value = 'phase8-admission-only'" in source


def test_installer_clears_stale_profile_grants_across_the_managed_fleet() -> None:
    source = INSTALLER.read_text(encoding="utf-8")
    managed_agents = _section(
        source,
        "$managedAgentIds = @(",
        "$allControlledWriteTools = @(",
    )

    for agent_id in (
        "cf-orchestrator",
        "cf-intake-evidence",
        "cf-physical-model",
        "cf-technical-system",
        "cf-commercial-engine",
        "cf-validator",
        "cf-output",
        "cf-library-governance",
        "cf-platform-governance",
    ):
        assert f'"{agent_id}"' in managed_agents

    assert "foreach ($id in ($managedAgentIds | Sort-Object))" in source
    assert "$_ -notin $allManagedControlledWriteTools" in source
    assert 'Where-Object { $_ -ne "classifire-controlled-write" }' in source
    assert 'if ($id -eq "cf-physical-model")' in source


def test_installer_fails_closed_for_missing_or_legacy_physical_token_scope() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "$tokenDoc.tokens.PSObject.Properties[$agentId]" in source
    assert "(missing token)" in source
    assert "scoped synchronizer for this agent without rotating its token" in source
    assert '"cf-physical-model" = @("physical:write", "physical:lock")' in source
    assert '"cf-physical-model" = @("physical:adjudicated:submit")' in source
    assert "forbidden $scope" in source


def test_installer_and_boundary_script_keep_only_admission_bound_physical_grant() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    boundary_test = BOUNDARY_TEST.read_text(encoding="utf-8")

    assert '"classifire_lock_physical_model"' in installer
    assert (
        '"cf-physical-model" = @("classifire_submit_initial_physical_model")'
    ) in boundary_test
    assert '"cf-intake-evidence" = @()' in boundary_test
    assert '"cf-technical-system" = @()' in boundary_test
    assert '"cf-commercial-engine" = @()' in boundary_test
    assert '$submissionScopes -notcontains "physical:adjudicated:submit"' in boundary_test
    assert "$submissionScopes -contains $forbiddenScope" in boundary_test
    assert 'Where-Object { $_ -ne "classifire_submit_initial_physical_model" }' in installer
    assert "$allManagedWriteTools" in boundary_test


def test_installer_preserves_the_approved_jpeg_response_allowlist() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    image_mimes = _section(
        source,
        "path = 'gateway.http.endpoints.responses.images.allowedMimes'",
        "path = 'gateway.http.endpoints.responses.images.maxBytes'",
    )

    assert "'image/png'" in image_mimes
    assert "'image/jpeg'" in image_mimes
