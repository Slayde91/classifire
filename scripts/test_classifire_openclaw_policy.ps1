param()

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop

$agentIds = @(
    "cf-orchestrator",
    "cf-intake-evidence",
    "cf-physical-model",
    "cf-technical-system",
    "cf-commercial-engine",
    "cf-validator",
    "cf-output",
    "cf-library-governance",
    "cf-platform-governance"
)

$requiredDenied = @(
    "exec",
    "process",
    "write",
    "edit",
    "apply_patch",
    "browser",
    "gateway",
    "cron",
    "sessions_spawn",
    "subagents"
)

$failures = @()

function Convert-ToAgentItems {
    param([object]$Value)

    if ($Value -is [System.Array]) {
        return @($Value)
    }
    if ($null -ne $Value.list) {
        return @($Value.list)
    }
    if ($null -ne $Value.agents) {
        return @($Value.agents)
    }
    if ($null -ne $Value.entries) {
        $items = @()
        foreach ($property in $Value.entries.PSObject.Properties) {
            $item = $property.Value
            if (-not $item.id) {
                $item | Add-Member -NotePropertyName id -NotePropertyValue $property.Name -Force
            }
            $items += $item
        }
        return $items
    }
    return @($Value)
}

Write-Host "Validating OpenClaw config syntax..." -ForegroundColor Cyan
& $openclaw.Source config validate | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "OpenClaw config validate failed."
}

Write-Host "Reading agents.list once..." -ForegroundColor Cyan
$agentsRaw = (& $openclaw.Source config get agents.list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read OpenClaw agents.list. Output: $agentsRaw"
}
try {
    $agentsValue = $agentsRaw | ConvertFrom-Json
    $agents = @(Convert-ToAgentItems $agentsValue)
}
catch {
    throw "OpenClaw agents.list was not valid JSON: $agentsRaw"
}

$byId = @{}
foreach ($item in $agents) {
    $id = [string]$item.id
    if ($id) {
        $byId[$id] = $item
    }
}

foreach ($id in $agentIds) {
    Write-Host "Checking $id..." -ForegroundColor Cyan
    if (-not $byId.ContainsKey($id)) {
        $failures += "$id is missing from agents.list"
        continue
    }

    $item = $byId[$id]

    if ([string]$item.tools.profile -ne "minimal") {
        $failures += "$id tools.profile expected minimal, got $($item.tools.profile)"
    }

    $deny = @($item.tools.deny)
    foreach ($tool in $requiredDenied) {
        if ($deny -notcontains $tool) {
            $failures += "$id is missing denied tool $tool"
        }
    }

    if ($null -eq $item.tools.elevated -or $item.tools.elevated.enabled -ne $false) {
        $failures += "$id elevated execution is not disabled"
    }

    if ([string]$item.sandbox.mode -ne "all") {
        $failures += "$id sandbox.mode expected all, got $($item.sandbox.mode)"
    }
    if ([string]$item.sandbox.backend -ne "docker") {
        $failures += "$id sandbox.backend expected docker, got $($item.sandbox.backend)"
    }
    if ([string]$item.sandbox.scope -ne "agent") {
        $failures += "$id sandbox.scope expected agent, got $($item.sandbox.scope)"
    }
    if ([string]$item.sandbox.workspaceAccess -ne "none") {
        $failures += "$id sandbox.workspaceAccess expected none, got $($item.sandbox.workspaceAccess)"
    }

    Write-Host "PASS config $id" -ForegroundColor Green
}

if ($failures.Count -eq 0) {
    Write-Host "Checking effective sandbox policy for each CLASSIFIRE agent..." -ForegroundColor Cyan
    foreach ($id in $agentIds) {
        $explain = (& $openclaw.Source sandbox explain --agent $id --json 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) {
            $failures += "$id sandbox explain failed: $explain"
        }
        else {
            Write-Host "PASS sandbox $id" -ForegroundColor Green
        }
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "CLASSIFIRE OpenClaw policy test FAILED:" -ForegroundColor Red
    foreach ($failure in $failures) {
        Write-Host " - $failure" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""
Write-Host "CLASSIFIRE OpenClaw policy test PASSED for all $($agentIds.Count) agents." -ForegroundColor Green
Write-Host "Dangerous host/file/control tools are denied and every cf-* agent is configured for an isolated Docker sandbox." -ForegroundColor Green
exit 0
