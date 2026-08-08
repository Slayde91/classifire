param()

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop

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
$rosterRaw = (& $openclaw.Source agents list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    Write-Host $rosterRaw -ForegroundColor Red
}
else {
    try {
        $roster = $rosterRaw | ConvertFrom-Json
        $items = @()
        if ($roster -is [System.Array]) {
            $items = @($roster)
        }
        elseif ($null -ne $roster.agents) {
            $items = @($roster.agents)
        }
        elseif ($null -ne $roster.list) {
            $items = @($roster.list)
        }
        else {
            $items = @($roster)
        }
        foreach ($item in $items) {
            $id = if ($item.id) { $item.id } elseif ($item.agentId) { $item.agentId } elseif ($item.name) { $item.name } else { "<unknown>" }
            $workspace = if ($item.workspace) { $item.workspace } else { "<not reported>" }
            Write-Host "   id=$id workspace=$workspace"
        }
    }
    catch {
        Write-Host "   Unable to parse agent roster JSON; raw non-secret output follows:" -ForegroundColor Yellow
        Write-Host $rosterRaw
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
        $items = @($cfg)
        if ($cfg -isnot [System.Array] -and $null -ne $cfg.list) {
            $items = @($cfg.list)
        }
        foreach ($item in $items) {
            $id = if ($item.id) { $item.id } elseif ($item.agentId) { $item.agentId } elseif ($item.name) { $item.name } else { "<unknown>" }
            $workspace = if ($item.workspace) { $item.workspace } else { "<not reported>" }
            Write-Host "   id=$id workspace=$workspace"
        }
    }
    catch {
        Write-Host "   Unable to parse agents.list JSON; raw redacted output follows:" -ForegroundColor Yellow
        Write-Host $configRaw
    }
}
Write-Host ""

Write-Host "7. Gateway read-scope RPC check" -ForegroundColor Cyan
& $openclaw.Source gateway status --require-rpc | Out-Host
Write-Host ""

Write-Host "Diagnostic complete. No configuration was changed." -ForegroundColor Green
