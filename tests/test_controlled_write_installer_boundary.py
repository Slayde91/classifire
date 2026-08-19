from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install_classifire_controlled_write_plugin.ps1"
BOUNDARY_TEST = ROOT / "scripts" / "test_classifire_controlled_write_boundaries.ps1"


def _section(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end, source.index(start))]


def test_installer_assigns_adjudicated_writer_only_the_bound_submit_tool() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    required_scopes = _section(
        source,
        "$requiredScopes = @{",
        "foreach ($agentId in $requiredScopes.Keys)",
    )
    add_by_agent = _section(source, "$addByAgent = @{", "$allControlledWriteTools = @(")
    current_tools = _section(
        source,
        "$allControlledWriteTools = @(",
        "$retiredControlledWriteTools",
    )

    assert '"cf-adjudicated-physical-writer" = @("physical:adjudicated:submit")' in required_scopes
    assert '"cf-physical-model" = @("physical:write", "physical:lock")' not in required_scopes
    assert '"cf-adjudicated-physical-writer" = @(' in add_by_agent
    assert '"classifire_submit_initial_physical_model"' in add_by_agent
    assert '"cf-physical-model" = @(' not in add_by_agent
    assert '"classifire_lock_physical_model"' not in current_tools


def test_installer_fails_closed_for_missing_or_legacy_writer_token_scope() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "$tokenDoc.tokens.PSObject.Properties[$agentId]" in source
    assert "(missing token)" in source
    assert '"cf-adjudicated-physical-writer" = @("physical:write", "physical:lock")' in source
    assert (
        '"cf-physical-model" = @("physical:write", "physical:lock", "physical:adjudicated:submit")'
    ) in source
    assert "forbidden $scope" in source


def test_installer_and_boundary_script_strip_legacy_physical_grants() -> None:
    installer = INSTALLER.read_text(encoding="utf-8")
    boundary_test = BOUNDARY_TEST.read_text(encoding="utf-8")

    assert "agents.list[$physicalIndex].tools.alsoAllow" in installer
    assert "agents.list[$physicalIndex].tools.sandbox.tools.alsoAllow" in installer
    assert '"classifire_lock_physical_model"' in installer
    assert '"cf-physical-model" = @()' in boundary_test
    assert (
        '"cf-adjudicated-physical-writer" = @("classifire_submit_initial_physical_model")'
    ) in boundary_test
    assert '$writerScopes -notcontains "physical:adjudicated:submit"' in boundary_test
    assert "$legacyPhysicalScopes -contains $forbiddenScope" in boundary_test
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
