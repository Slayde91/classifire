param(
    [string]$WorkspaceRoot = "C:\CLASSIFIRE-OpenClaw",
    [string]$FleetRoot
)

$ErrorActionPreference = "Stop"

$openclaw = Get-Command openclaw -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logo = Join-Path $repoRoot "assets\brand\generated\classifire-logo-small.png"

if (-not $FleetRoot) {
    $FleetRoot = Join-Path $repoRoot "openclaw\agent-definitions\CLASSIFIRE_Agent_Fleet_v1.0"
}
$FleetRoot = [System.IO.Path]::GetFullPath($FleetRoot)
$manifestPath = Join-Path $FleetRoot "FLEET_MANIFEST.json"

if (-not (Test-Path -LiteralPath $logo)) {
    throw "CLASSIFIRE logo not found at $logo. Run the CLASSIFIRE logo installer first."
}
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "Canonical CLASSIFIRE agent fleet manifest not found: $manifestPath"
}

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.schema -ne "CLASSIFIRE-AGENT-FLEET-MANIFEST-v1") {
    throw "Unexpected CLASSIFIRE agent fleet schema: $($manifest.schema)"
}
if ($manifest.version -ne "1.0") {
    throw "Unsupported CLASSIFIRE agent fleet version: $($manifest.version)"
}
if (@($manifest.agents).Count -ne 9) {
    throw "CLASSIFIRE Agent Fleet v1.0 must contain exactly 9 agents; found $(@($manifest.agents).Count)."
}

$requiredFiles = @(
    "IDENTITY.md",
    "SOUL.md",
    "AGENTS.md",
    "TOOLS.md",
    "TASK_BOUNDARIES.md",
    "WORKFLOWS.md",
    "PROMPTS.md"
)

foreach ($spec in $manifest.agents) {
    $source = Join-Path (Join-Path $FleetRoot "agents") $spec.id
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Canonical agent source folder missing: $source"
    }
    foreach ($file in $requiredFiles) {
        $sourceFile = Join-Path $source $file
        if (-not (Test-Path -LiteralPath $sourceFile)) {
            throw "Canonical agent definition missing for $($spec.id): $sourceFile"
        }
    }
}

New-Item -ItemType Directory -Force -Path $WorkspaceRoot | Out-Null

Write-Host "Reading existing OpenClaw agents..." -ForegroundColor Cyan
$listText = (& $openclaw.Source agents list --json 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read the existing OpenClaw agent roster."
}

foreach ($spec in $manifest.agents) {
    $id = [string]$spec.id
    $name = [string]$spec.name
    $theme = [string]$spec.theme
    $workspace = Join-Path $WorkspaceRoot $id
    $source = Join-Path (Join-Path $FleetRoot "agents") $id

    New-Item -ItemType Directory -Force -Path $workspace | Out-Null

    if ($listText -notmatch [regex]::Escape($id)) {
        Write-Host "Creating OpenClaw agent $id..." -ForegroundColor Cyan
        & $openclaw.Source agents add $id --workspace $workspace --non-interactive --json
        if ($LASTEXITCODE -ne 0) {
            throw "OpenClaw failed while creating $id."
        }
    }
    else {
        Write-Host "Agent $id already exists; refreshing canonical Agent Fleet v1.0 files." -ForegroundColor DarkYellow
    }

    foreach ($file in $requiredFiles) {
        Copy-Item -LiteralPath (Join-Path $source $file) -Destination (Join-Path $workspace $file) -Force
    }

    $avatarDir = Join-Path $workspace "avatars"
    New-Item -ItemType Directory -Force -Path $avatarDir | Out-Null
    Copy-Item -LiteralPath $logo -Destination (Join-Path $avatarDir "classifire.png") -Force

    $bootstrap = Join-Path $workspace "BOOTSTRAP.md"
    if (Test-Path -LiteralPath $bootstrap) {
        Remove-Item -LiteralPath $bootstrap -Force
    }

    Write-Host "Synchronising identity for $id..." -ForegroundColor Cyan
    & $openclaw.Source agents set-identity --agent $id --name $name --theme $theme --avatar "avatars/classifire.png" --json
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw failed while setting identity for $id."
    }

    $installedCount = @(Get-ChildItem -LiteralPath $workspace -File -Filter "*.md" | Where-Object { $_.Name -in $requiredFiles }).Count
    if ($installedCount -ne 7) {
        throw "Canonical Agent Fleet installation incomplete for $id: expected 7 Markdown files, found $installedCount."
    }
    Write-Host "Installed canonical Agent Fleet v1.0 definition for $id (7 Markdown files)." -ForegroundColor Green
}

Write-Host ""
Write-Host "CLASSIFIRE OpenClaw Agent Fleet v1.0 installed or refreshed from repository-controlled definitions." -ForegroundColor Green
Write-Host "Canonical fleet source: $FleetRoot" -ForegroundColor Green
Write-Host "Workspace root: $WorkspaceRoot" -ForegroundColor Green
Write-Host "Old qf-* agents were intentionally NOT deleted." -ForegroundColor Yellow
Write-Host "No CLASSIFIRE estimate, technical, commercial, validation, snapshot, or Human Release record was changed." -ForegroundColor Green
Write-Host ""
& $openclaw.Source agents list --bindings
