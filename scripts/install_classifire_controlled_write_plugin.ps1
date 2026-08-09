param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$npm = Get-Command npm -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pluginRoot = Join-Path $repoRoot "openclaw-plugin-classifire-controlled-write"
$TokenFile = [System.IO.Path]::GetFullPath($TokenFile)

if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw "CLASSIFIRE agent token file is missing: $TokenFile. Run 'classifire provision-agent-tokens --rotate' first."
}
if (-not (Test-Path -LiteralPath (Join-Path $pluginRoot "package.json"))) {
    throw "CLASSIFIRE controlled-write plugin source is missing at $pluginRoot"
}

$tokenDoc = Get-Content -LiteralPath $TokenFile -Raw | ConvertFrom-Json
if ($tokenDoc.schema -ne "CLASSIFIRE-AGENT-TOKENS-v1") {
    throw "Unexpected CLASSIFIRE agent token-file schema."
}

$requiredScopes = @{
    "cf-technical-system" = @("technical:select", "technical:lock")
    "cf-physical-model" = @("quantity:derive")
    "cf-commercial-engine" = @("commercial:components", "commercial:derive")
}
foreach ($agentId in $requiredScopes.Keys) {
    $scopeProperty = $tokenDoc.scopes.PSObject.Properties[$agentId]
    $currentScopes = if ($null -ne $scopeProperty) { @($scopeProperty.Value) } else { @() }
    foreach ($scope in $requiredScopes[$agentId]) {
        if ($currentScopes -notcontains $scope) {
            throw "CLASSIFIRE agent token scopes are stale for $agentId (missing $scope). Run 'classifire provision-agent-tokens --rotate', then rerun this installer."
        }
    }
}

function Convert-ToAgentItems {
    param([object]$Value)
    if ($Value -is [System.Array]) { return @($Value) }
    if ($null -ne $Value.list) { return @($Value.list) }
    if ($null -ne $Value.agents) { return @($Value.agents) }
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

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

$addByAgent = @{
    "cf-technical-system" = @(
        "classifire_select_repair_strategy",
        "classifire_lock_repair_strategy"
    )
    "cf-physical-model" = @(
        "classifire_derive_quantity_labour"
    )
    "cf-commercial-engine" = @(
        "classifire_required_components",
        "classifire_derive_commercial"
    )
}

Write-Host "Building CLASSIFIRE controlled-write OpenClaw plugin..." -ForegroundColor Cyan
Push-Location $pluginRoot
try {
    & $npm.Source install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed for CLASSIFIRE controlled-write plugin." }
    & $npm.Source run build
    if ($LASTEXITCODE -ne 0) { throw "TypeScript build failed for CLASSIFIRE controlled-write plugin." }
}
finally {
    Pop-Location
}

Write-Host "Link-installing CLASSIFIRE controlled-write plugin..." -ForegroundColor Cyan
# Official OpenClaw local-development form: openclaw plugins install --link <path>.
# This installed OpenClaw build rejects combining --force with --link, so do not add --force here.
$installOutput = (& $openclaw.Source plugins install --link $pluginRoot 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -and $installOutput -notmatch "already (installed|linked|registered)" -and $installOutput -notmatch "already exists") {
    throw "OpenClaw controlled-write plugin install failed: $($installOutput.Trim())"
}
if ($installOutput.Trim()) { Write-Host $installOutput.Trim() -ForegroundColor DarkGray }

Write-Host "Resolving existing cf-* agent tool grants..." -ForegroundColor Cyan
$agentsRaw = (& $openclaw.Source config get agents.list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read OpenClaw agents.list: $agentsRaw" }
$agentsValue = $agentsRaw | ConvertFrom-Json
$agents = @(Convert-ToAgentItems $agentsValue)
$indexById = @{}
for ($i = 0; $i -lt $agents.Count; $i++) {
    $id = [string]$agents[$i].id
    if ($id) { $indexById[$id] = $i }
}
foreach ($id in $addByAgent.Keys) {
    if (-not $indexById.ContainsKey($id)) {
        throw "Required CLASSIFIRE agent '$id' is missing from OpenClaw agents.list."
    }
}

$operations = @(
    [pscustomobject]@{ path = 'plugins.entries["classifire-controlled-write"].config.baseUrl'; value = $BaseUrl },
    [pscustomobject]@{ path = 'plugins.entries["classifire-controlled-write"].config.tokenFile'; value = $TokenFile }
)

foreach ($id in ($addByAgent.Keys | Sort-Object)) {
    $index = $indexById[$id]
    $existing = @()
    $toolsNode = $agents[$index].tools
    if ($null -ne $toolsNode -and $null -ne $toolsNode.alsoAllow) {
        $existing = @($toolsNode.alsoAllow)
    }
    $merged = @($existing + @($addByAgent[$id]) | ForEach-Object { [string]$_ } | Sort-Object -Unique)
    $operations += [pscustomobject]@{
        path = "agents.list[$index].tools.alsoAllow"
        value = $merged
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$batchFile = Join-Path $env:TEMP "classifire-controlled-write-$stamp.batch.json"
Write-Utf8NoBom -Path $batchFile -Content (@($operations) | ConvertTo-Json -Depth 8)

try {
    Write-Host "Dry-running controlled-write plugin config and merged agent grants..." -ForegroundColor Cyan
    $dry = (& $openclaw.Source config set --batch-file $batchFile --dry-run 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw controlled-write config dry-run failed: $($dry.Trim())"
    }

    Write-Host "Applying controlled-write plugin config and merged agent grants..." -ForegroundColor Cyan
    $apply = (& $openclaw.Source config set --batch-file $batchFile 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw controlled-write config apply failed: $($apply.Trim())"
    }
}
finally {
    Remove-Item -LiteralPath $batchFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Enabling CLASSIFIRE controlled-write plugin..." -ForegroundColor Cyan
& $openclaw.Source plugins enable classifire-controlled-write | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Unable to enable classifire-controlled-write plugin." }

& $openclaw.Source config validate | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw config validation failed after controlled-write installation." }

Write-Host "Restarting OpenClaw Gateway..." -ForegroundColor Cyan
& $openclaw.Source gateway restart | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw Gateway restart failed." }

Write-Host "Inspecting live controlled-write plugin runtime..." -ForegroundColor Cyan
& $openclaw.Source plugins inspect classifire-controlled-write --runtime --json | Out-Host
if ($LASTEXITCODE -ne 0) { throw "CLASSIFIRE controlled-write plugin runtime inspection failed." }

Write-Host "CLASSIFIRE controlled-write plugin installed." -ForegroundColor Green
Write-Host "Only cf-technical-system, cf-physical-model and cf-commercial-engine received new tools." -ForegroundColor Green
Write-Host "Human Release, library approval and generic estimate:write remain unavailable to agents." -ForegroundColor Green
