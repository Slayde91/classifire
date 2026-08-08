param(
    [switch]$ProbeRuntimeRoster
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop

function Show-AgentItems {
    param([object]$Value)

    $items = @()

    if ($Value -is [System.Array]) {
        $items = @($Value)
    }
    elseif ($null -ne $Value.list) {
        $items = @($Value.list)
    }
    elseif ($null -ne $Value.agents) {
        $items = @($Value.agents)
    }
    elseif ($null -ne $Value.entries) {
        foreach ($property in $Value.entries.PSObject.Properties) {
            $item = $property.Value
            if (-not $item.id) {
                $item | Add-Member -NotePropertyName id -NotePropertyValue $property.Name -Force
            }
            $items += $item
        }
    }
    else {
        $items = @($Value)
    }

    foreach ($item in $items) {
        $id = if ($item.id) { $item.id } elseif ($item.agentId) { $item.agentId } elseif ($item.name) { $item.name } else { "<unknown>" }
        $workspace = if ($item.workspace) { $item.workspace } else { "<not reported>" }
        Write-Host "   id=$id workspace=$workspace"
    }
}

Write-Host "CLASSIFIRE OpenClaw configuration diagnostic" -ForegroundColor Cyan
Write-Host "This script is read-only and does not print secret values." -ForegroundColor DarkGray
Write-Host ""

Write-Host "1. OpenClaw executable" -ForegroundColor Cyan
Write-Host "   $($openclaw.Source)"
Write-Host ""

Write-Host "2. Process path/profile overrides" -ForegroundColor Cyan
foreach ($name in @("OPENCLAW_HOME", "OPENCLAW_STATE_DIR", "OPENCLAW_CONFIG_PATH", "OPENCLAW_PROFILE")) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = "<not set>"
    }
    Write-Host "   $name = $value"
}
Write-Host ""

Write-Host "3. CLI active config file" -ForegroundColor Cyan
& $openclaw.Source config file | Out-Host
Write-Host ""

Write-Host "4. Gateway/service status (deep)" -ForegroundColor Cyan
& $openclaw.Source gateway status --deep | Out-Host
Write-Host ""

Write-Host "5. Runtime agent roster" -ForegroundColor Cyan
if (-not $ProbeRuntimeRoster) {
    Write-Host "   SKIPPED by default because this command can block on some OpenClaw builds." -ForegroundColor Yellow
    Write-Host "   The earlier CLASSIFIRE smoke test already proved the cf-* runtime agents are callable."
    Write-Host "   Use -ProbeRuntimeRoster only when explicitly troubleshooting the roster command."
}
else {
    Write-Host "   Probing runtime roster..." -ForegroundColor Yellow
    $rosterRaw = (& $openclaw.Source agents list --json 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        Write-Host $rosterRaw -ForegroundColor Red
    }
    else {
        try {
            $roster = $rosterRaw | ConvertFrom-Json
            Show-AgentItems $roster
        }
        catch {
            Write-Host "   Unable to parse agent roster JSON; raw non-secret output follows:" -ForegroundColor Yellow
            Write-Host $rosterRaw
        }
    }
}
Write-Host ""

Write-Host "6. CLI config agents.list summary" -ForegroundColor Cyan
$configRaw = (& $openclaw.Source config get agents.list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Write-Host "   agents.list unavailable: $configRaw" -ForegroundColor Yellow
}
else {
    try {
        $cfg = $configRaw | ConvertFrom-Json
        Write-Host "   JSON type: $($cfg.GetType().FullName)" -ForegroundColor DarkGray
        if ($cfg -isnot [System.Array]) {
            $propertyNames = @($cfg.PSObject.Properties.Name)
            if ($propertyNames.Count -gt 0) {
                Write-Host "   Top-level properties: $($propertyNames -join ', ')" -ForegroundColor DarkGray
            }
        }
        Show-AgentItems $cfg
    }
    catch {
        Write-Host "   Unable to parse agents.list JSON; raw output follows:" -ForegroundColor Yellow
        Write-Host $configRaw
    }
}
Write-Host ""

Write-Host "7. Gateway read-scope RPC check" -ForegroundColor Cyan
& $openclaw.Source gateway status --require-rpc | Out-Host
Write-Host ""

Write-Host "Diagnostic complete. No configuration was changed." -ForegroundColor Green
