param()

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$docker = Get-Command docker -ErrorAction Stop

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
$denyJson = $denyTools | ConvertTo-Json -Compress

$configFile = (& $openclaw.Source config file 2>&1 | Out-String).Trim()
if (-not $configFile) {
    throw "Unable to resolve the active OpenClaw configuration file."
}

$backupDir = Join-Path (Split-Path -Parent $configFile) "classifire-config-backups"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupFile = Join-Path $backupDir "openclaw-before-classifire-hardening-$stamp.json"
Copy-Item -LiteralPath $configFile -Destination $backupFile -Force
Write-Host "Backed up OpenClaw config to $backupFile" -ForegroundColor DarkYellow

foreach ($id in $agentIds) {
    Write-Host "Hardening $id..." -ForegroundColor Cyan
    $base = 'agents.entries["' + $id + '"]'

    & $openclaw.Source config set "$base.tools.profile" "minimal" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set minimal tool profile for $id." }

    & $openclaw.Source config set "$base.tools.deny" $denyJson --strict-json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set tool deny list for $id." }

    & $openclaw.Source config set "$base.tools.elevated.enabled" "false" --strict-json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to disable elevated execution for $id." }

    & $openclaw.Source config set "$base.tools.fs.workspaceOnly" "true" --strict-json | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to restrict filesystem scope for $id." }

    & $openclaw.Source config set "$base.sandbox.mode" "all" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to enable sandboxing for $id." }

    & $openclaw.Source config set "$base.sandbox.backend" "docker" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to select Docker sandbox backend for $id." }

    & $openclaw.Source config set "$base.sandbox.scope" "agent" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to set per-agent sandbox scope for $id." }

    & $openclaw.Source config set "$base.sandbox.workspaceAccess" "none" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Failed to remove host workspace access for $id." }
}

Write-Host "Validating OpenClaw configuration..." -ForegroundColor Cyan
& $openclaw.Source config validate
if ($LASTEXITCODE -ne 0) {
    throw "OpenClaw configuration validation failed. Restore $backupFile if required."
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
