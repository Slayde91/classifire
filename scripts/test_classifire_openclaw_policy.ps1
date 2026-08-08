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

function Get-ConfigValue {
    param(
        [string]$Path,
        [switch]$Json
    )

    if ($Json) {
        $raw = (& $openclaw.Source config get $Path --json 2>&1 | Out-String).Trim()
    }
    else {
        $raw = (& $openclaw.Source config get $Path 2>&1 | Out-String).Trim()
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Unable to read OpenClaw config path $Path. Output: $raw"
    }
    return $raw
}

Write-Host "Validating OpenClaw config syntax..." -ForegroundColor Cyan
& $openclaw.Source config validate | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "OpenClaw config validate failed."
}

foreach ($id in $agentIds) {
    Write-Host "Checking $id..." -ForegroundColor Cyan
    $base = 'agents.entries["' + $id + '"]'

    $profile = Get-ConfigValue "$base.tools.profile"
    if ($profile -ne "minimal") {
        $failures += "$id tools.profile expected minimal, got $profile"
    }

    $denyRaw = Get-ConfigValue "$base.tools.deny" -Json
    try {
        $deny = @($denyRaw | ConvertFrom-Json)
    }
    catch {
        $failures += "$id tools.deny was not valid JSON: $denyRaw"
        $deny = @()
    }
    foreach ($tool in $requiredDenied) {
        if ($deny -notcontains $tool) {
            $failures += "$id is missing denied tool $tool"
        }
    }

    $elevated = Get-ConfigValue "$base.tools.elevated.enabled"
    if ($elevated -ne "false") {
        $failures += "$id elevated execution is not disabled"
    }

    $workspaceOnly = Get-ConfigValue "$base.tools.fs.workspaceOnly"
    if ($workspaceOnly -ne "true") {
        $failures += "$id filesystem workspaceOnly is not true"
    }

    $sandboxMode = Get-ConfigValue "$base.sandbox.mode"
    $sandboxBackend = Get-ConfigValue "$base.sandbox.backend"
    $sandboxScope = Get-ConfigValue "$base.sandbox.scope"
    $workspaceAccess = Get-ConfigValue "$base.sandbox.workspaceAccess"

    if ($sandboxMode -ne "all") { $failures += "$id sandbox.mode expected all, got $sandboxMode" }
    if ($sandboxBackend -ne "docker") { $failures += "$id sandbox.backend expected docker, got $sandboxBackend" }
    if ($sandboxScope -ne "agent") { $failures += "$id sandbox.scope expected agent, got $sandboxScope" }
    if ($workspaceAccess -ne "none") { $failures += "$id sandbox.workspaceAccess expected none, got $workspaceAccess" }

    $explain = (& $openclaw.Source sandbox explain --agent $id --json 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        $failures += "$id sandbox explain failed: $explain"
    }
    else {
        Write-Host "PASS $id" -ForegroundColor Green
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
