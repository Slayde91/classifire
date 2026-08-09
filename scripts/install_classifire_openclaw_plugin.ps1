param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$npm = Get-Command npm -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pluginRoot = Join-Path $repoRoot "openclaw-plugin-classifire"
$TokenFile = [System.IO.Path]::GetFullPath($TokenFile)

if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw "CLASSIFIRE agent token file is missing: $TokenFile. Run 'classifire provision-agent-tokens' first."
}
if (-not (Test-Path -LiteralPath (Join-Path $pluginRoot "package.json"))) {
    throw "CLASSIFIRE OpenClaw plugin source is missing at $pluginRoot"
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

# Keep the CLASSIFIRE fleet on OpenClaw's minimal base profile and add only the
# narrow role-specific tools each agent needs. The real-report agents also need
# read-only media inspection so report photos are reviewed rather than inferred
# from extracted text.
$allowByAgent = @{
    "cf-orchestrator" = @("classifire_health", "classifire_workflow_status")
    "cf-intake-evidence" = @(
        "classifire_health",
        "classifire_workflow_status",
        "classifire_evidence_read",
        "pdf",
        "image"
    )
    "cf-physical-model" = @(
        "classifire_health",
        "classifire_workflow_status",
        "classifire_evidence_read",
        "classifire_physical_model_read",
        "pdf",
        "image"
    )
    "cf-technical-system" = @("classifire_health", "classifire_workflow_status", "classifire_technical_search")
    "cf-commercial-engine" = @("classifire_health", "classifire_workflow_status", "classifire_package14_recommendation")
    "cf-validator" = @("classifire_health", "classifire_workflow_status", "classifire_run_validation")
    "cf-output" = @("classifire_health", "classifire_workflow_status", "classifire_lock_snapshot", "classifire_render_output")
    "cf-library-governance" = @("classifire_health", "classifire_workflow_status", "classifire_library_releases")
    "cf-platform-governance" = @("classifire_health", "classifire_workflow_status")
}

Write-Host "Building CLASSIFIRE OpenClaw plugin..." -ForegroundColor Cyan
Push-Location $pluginRoot
try {
    & $npm.Source install
    if ($LASTEXITCODE -ne 0) { throw "npm install failed for CLASSIFIRE OpenClaw plugin." }
    & $npm.Source run build
    if ($LASTEXITCODE -ne 0) { throw "TypeScript build failed for CLASSIFIRE OpenClaw plugin." }
}
finally {
    Pop-Location
}

Write-Host "Link-installing CLASSIFIRE OpenClaw plugin..." -ForegroundColor Cyan
$installOutput = (& $openclaw.Source plugins install $pluginRoot --link 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -and $installOutput -notmatch "already (installed|linked|registered)" -and $installOutput -notmatch "already exists") {
    throw "OpenClaw plugin install failed: $($installOutput.Trim())"
}
if ($installOutput.Trim()) { Write-Host $installOutput.Trim() -ForegroundColor DarkGray }

Write-Host "Resolving cf-* agent indexes..." -ForegroundColor Cyan
$agentsRaw = (& $openclaw.Source config get agents.list --json 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw "Unable to read OpenClaw agents.list: $agentsRaw" }
$agentsValue = $agentsRaw | ConvertFrom-Json
$agents = @(Convert-ToAgentItems $agentsValue)
$indexById = @{}
for ($i = 0; $i -lt $agents.Count; $i++) {
    $id = [string]$agents[$i].id
    if ($id) { $indexById[$id] = $i }
}
foreach ($id in $allowByAgent.Keys) {
    if (-not $indexById.ContainsKey($id)) {
        throw "Required CLASSIFIRE agent '$id' is missing from OpenClaw agents.list."
    }
}

$operations = @(
    [pscustomobject]@{ path = 'plugins.entries["classifire-tools"].config.baseUrl'; value = $BaseUrl },
    [pscustomobject]@{ path = 'plugins.entries["classifire-tools"].config.tokenFile'; value = $TokenFile }
)
foreach ($id in ($allowByAgent.Keys | Sort-Object)) {
    $index = $indexById[$id]
    $existing = @()
    $toolsNode = $agents[$index].tools
    if ($null -ne $toolsNode -and $null -ne $toolsNode.alsoAllow) {
        $existing = @($toolsNode.alsoAllow)
    }
    $merged = @(
        $existing + @($allowByAgent[$id]) |
            ForEach-Object { [string]$_ } |
            Sort-Object -Unique
    )
    $operations += [pscustomobject]@{
        path = "agents.list[$index].tools.alsoAllow"
        value = $merged
    }
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$batchFile = Join-Path $env:TEMP "classifire-openclaw-plugin-$stamp.batch.json"
Write-Utf8NoBom -Path $batchFile -Content (@($operations) | ConvertTo-Json -Depth 8)

try {
    Write-Host "Dry-running CLASSIFIRE plugin configuration and merged per-agent tool grants..." -ForegroundColor Cyan
    $dry = (& $openclaw.Source config set --batch-file $batchFile --dry-run 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw plugin config dry-run failed: $($dry.Trim())"
    }

    Write-Host "Applying CLASSIFIRE plugin configuration and merged per-agent tool grants..." -ForegroundColor Cyan
    $apply = (& $openclaw.Source config set --batch-file $batchFile 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw plugin config apply failed: $($apply.Trim())"
    }
}
finally {
    Remove-Item -LiteralPath $batchFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Enabling CLASSIFIRE plugin..." -ForegroundColor Cyan
& $openclaw.Source plugins enable classifire-tools | Out-Host
if ($LASTEXITCODE -ne 0) { throw "Unable to enable classifire-tools plugin." }

& $openclaw.Source config validate | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw config validation failed after plugin installation." }

Write-Host "Restarting OpenClaw Gateway so plugin runtime is live..." -ForegroundColor Cyan
& $openclaw.Source gateway restart | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw Gateway restart failed." }

Write-Host "Inspecting live CLASSIFIRE plugin runtime..." -ForegroundColor Cyan
& $openclaw.Source plugins inspect classifire-tools --runtime --json | Out-Host
if ($LASTEXITCODE -ne 0) { throw "CLASSIFIRE plugin runtime inspection failed." }

Write-Host "CLASSIFIRE OpenClaw plugin installed and role-limited additive tools applied." -ForegroundColor Green
Write-Host "Existing controlled-write grants were preserved rather than replaced." -ForegroundColor Green
Write-Host "cf-intake-evidence and cf-physical-model received read-only pdf/image inspection tools." -ForegroundColor Green
Write-Host "cf-physical-model also received canonical evidence read access for evidence-backed modelling." -ForegroundColor Green
Write-Host "Human Release remains unavailable to every agent." -ForegroundColor Green
