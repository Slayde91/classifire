param()

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$docker = Get-Command docker -ErrorAction Stop

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

$denyTools = @(
    "exec",
    "process",
    "write",
    "edit",
    "apply_patch",
    "browser",
    "gateway",
    "cron",
    "sessions_spawn",
    "subagents",
    "image_generate",
    "video_generate",
    "music_generate"
)

# Windows PowerShell strips embedded double quotes when arguments pass through
# the openclaw.ps1 -> node.exe wrapper. OpenClaw config values parse as JSON5 by
# default, so use single-quoted JSON5 string values here and deliberately omit
# --strict-json for the tools.deny array.
$denyJson5Items = $denyTools | ForEach-Object {
    "'" + $_.Replace("'", "\\'") + "'"
}
$denyJson5 = "[" + ($denyJson5Items -join ",") + "]"

function Resolve-OpenClawConfigPath {
    $raw = (& $openclaw.Source config file 2>&1 | Out-String).Trim()
    if (-not $raw) {
        throw "Unable to resolve the active OpenClaw configuration file."
    }
    if ($raw -match '^~[\\/](.+)$') {
        return Join-Path $HOME $Matches[1]
    }
    return [System.IO.Path]::GetFullPath($raw)
}

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

function Invoke-ConfigSet {
    param(
        [string]$Path,
        [string]$Value,
        [switch]$StrictJson,
        [switch]$DryRun
    )

    $args = @("config", "set", $Path, $Value)
    if ($StrictJson) { $args += "--strict-json" }
    if ($DryRun) { $args += "--dry-run" }

    $output = (& $openclaw.Source @args 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw config set failed for $Path. Output: $($output.Trim())"
    }
    return $output
}

Write-Host "Checking Docker daemon readiness..." -ForegroundColor Cyan
$dockerStatus = (& $docker.Source info 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw (
        "Docker is installed but the Docker daemon is not reachable. " +
        "Start Docker Desktop, wait until the Linux engine is running, then confirm 'docker info' succeeds before rerunning this script. " +
        "No OpenClaw hardening changes have been applied. Docker output: " +
        $dockerStatus.Trim()
    )
}
Write-Host "Docker daemon is reachable." -ForegroundColor Green

Write-Host "Validating current OpenClaw configuration..." -ForegroundColor Cyan
& $openclaw.Source config validate | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw "Current OpenClaw configuration is invalid before CLASSIFIRE hardening. Fix it before continuing."
}

Write-Host "Resolving CLASSIFIRE agent indexes from agents.list..." -ForegroundColor Cyan
$agentsRaw = (& $openclaw.Source config get agents.list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read agents.list from OpenClaw. Output: $agentsRaw"
}
try {
    $agentsValue = $agentsRaw | ConvertFrom-Json
    $agents = @(Convert-ToAgentItems $agentsValue)
}
catch {
    throw "OpenClaw agents.list was not valid JSON: $agentsRaw"
}

$indexById = @{}
for ($i = 0; $i -lt $agents.Count; $i++) {
    $agentId = [string]$agents[$i].id
    if ($agentId) {
        $indexById[$agentId] = $i
    }
}
foreach ($id in $agentIds) {
    if (-not $indexById.ContainsKey($id)) {
        $available = @($indexById.Keys | Sort-Object) -join ", "
        throw "Required CLASSIFIRE agent '$id' is missing from OpenClaw agents.list. Available ids: $available"
    }
}
Write-Host "Resolved all $($agentIds.Count) CLASSIFIRE agents." -ForegroundColor Green

$changes = @()
foreach ($id in $agentIds) {
    $index = $indexById[$id]
    $base = "agents.list[$index]"
    $changes += @(
        @{ Agent = $id; Path = "$base.tools.profile"; Value = "minimal"; Strict = $false },
        @{ Agent = $id; Path = "$base.tools.deny"; Value = $denyJson5; Strict = $false },
        @{ Agent = $id; Path = "$base.tools.elevated.enabled"; Value = "false"; Strict = $true },
        @{ Agent = $id; Path = "$base.sandbox.mode"; Value = "all"; Strict = $false },
        @{ Agent = $id; Path = "$base.sandbox.backend"; Value = "docker"; Strict = $false },
        @{ Agent = $id; Path = "$base.sandbox.scope"; Value = "agent"; Strict = $false },
        @{ Agent = $id; Path = "$base.sandbox.workspaceAccess"; Value = "none"; Strict = $false }
    )
}

Write-Host "Dry-running all CLASSIFIRE hardening changes against the active schema..." -ForegroundColor Cyan
foreach ($change in $changes) {
    if ($change.Strict) {
        Invoke-ConfigSet -Path $change.Path -Value $change.Value -StrictJson -DryRun | Out-Null
    }
    else {
        Invoke-ConfigSet -Path $change.Path -Value $change.Value -DryRun | Out-Null
    }
}
Write-Host "All hardening paths passed schema dry-run." -ForegroundColor Green

$configFile = Resolve-OpenClawConfigPath
if (-not (Test-Path -LiteralPath $configFile)) {
    throw "Resolved OpenClaw config file does not exist: $configFile"
}
$backupDir = Join-Path (Split-Path -Parent $configFile) "classifire-config-backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $backupDir "openclaw-before-classifire-hardening-$stamp.json"
Copy-Item -LiteralPath $configFile -Destination $backupFile -Force
Write-Host "Backed up OpenClaw config to $backupFile" -ForegroundColor DarkYellow

try {
    foreach ($id in $agentIds) {
        Write-Host "Hardening $id..." -ForegroundColor Cyan
        foreach ($change in $changes | Where-Object { $_.Agent -eq $id }) {
            if ($change.Strict) {
                Invoke-ConfigSet -Path $change.Path -Value $change.Value -StrictJson | Out-Null
            }
            else {
                Invoke-ConfigSet -Path $change.Path -Value $change.Value | Out-Null
            }
        }
    }

    Write-Host "Validating hardened OpenClaw configuration..." -ForegroundColor Cyan
    & $openclaw.Source config validate | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw configuration validation failed after CLASSIFIRE hardening."
    }
}
catch {
    Write-Host "Hardening failed. Restoring the pre-hardening OpenClaw config backup..." -ForegroundColor Red
    Copy-Item -LiteralPath $backupFile -Destination $configFile -Force
    & $openclaw.Source config validate | Out-Host
    throw
}

Write-Host ""
Write-Host "CLASSIFIRE OpenClaw hardening applied." -ForegroundColor Green
Write-Host "All cf-* agents now use:" -ForegroundColor Green
Write-Host " - tools.profile = minimal"
Write-Host " - explicit deny list for shell/file/browser/control tools"
Write-Host " - elevated execution disabled"
Write-Host " - sandbox.mode = all"
Write-Host " - sandbox.backend = docker"
Write-Host " - sandbox.scope = agent"
Write-Host " - sandbox.workspaceAccess = none"
Write-Host ""
Write-Host "This is intentionally restrictive. Controlled CLASSIFIRE API tools will be added later." -ForegroundColor Yellow
