param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787",
    [switch]$PlanOnly
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
    "cf-physical-model" = @("physical:adjudicated:submit")
}
foreach ($agentId in $requiredScopes.Keys) {
    $tokenProperty = $tokenDoc.tokens.PSObject.Properties[$agentId]
    if ($null -eq $tokenProperty -or [string]::IsNullOrWhiteSpace([string]$tokenProperty.Value)) {
        throw "CLASSIFIRE agent token file is stale for $agentId (missing token). Provision that existing agent credential through the approved credential workflow, then rerun this installer."
    }

    $scopeProperty = $tokenDoc.scopes.PSObject.Properties[$agentId]
    $currentScopes = if ($null -ne $scopeProperty) { @($scopeProperty.Value) } else { @() }
    foreach ($scope in $requiredScopes[$agentId]) {
        if ($currentScopes -notcontains $scope) {
            throw "CLASSIFIRE agent token scopes are stale for $agentId (missing $scope). With separate live-change approval, run the scoped synchronizer for this agent without rotating its token, then rerun this installer."
        }
    }
}

$forbiddenMutationScopes = @{
    "cf-physical-model" = @("physical:write", "physical:lock")
}
foreach ($agentId in $forbiddenMutationScopes.Keys) {
    $scopeProperty = $tokenDoc.scopes.PSObject.Properties[$agentId]
    $currentScopes = if ($null -ne $scopeProperty) { @($scopeProperty.Value) } else { @() }
    foreach ($scope in $forbiddenMutationScopes[$agentId]) {
        if ($currentScopes -contains $scope) {
            throw "CLASSIFIRE agent token scopes are stale for $agentId (forbidden $scope). With separate live-change approval, run the scoped synchronizer for this agent without rotating its token, then rerun this installer."
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

function Invoke-OpenClawCaptured {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $previousErrorActionPreference = (
        $ErrorActionPreference
    )

    try {
        # OpenClaw can emit non-fatal config warnings on
        # stderr. Windows PowerShell must not promote those
        # warnings above the native process exit code.
        $ErrorActionPreference = "Continue"

        $output = (
            & $openclaw.Source @Arguments 2>&1 |
            Out-String
        )

        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = (
            $previousErrorActionPreference
        )
    }

    return [pscustomobject]@{
        Output = $output
        ExitCode = $exitCode
    }
}


function Invoke-OpenClawJsonRead {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    $stderrPath = (
        [System.IO.Path]::GetTempFileName()
    )

    $previousErrorActionPreference = (
        $ErrorActionPreference
    )

    $stdout = ""
    $stderr = ""
    $exitCode = $null

    try {
        # Keep stderr separate so OpenClaw warnings cannot
        # contaminate JSON stdout.
        $ErrorActionPreference = "Continue"

        $stdout = (
            & $openclaw.Source @Arguments `
                2> $stderrPath |
            Out-String
        ).Trim()

        $exitCode = $LASTEXITCODE

        if (Test-Path -LiteralPath $stderrPath) {
            $stderrValue = Get-Content `
                -LiteralPath $stderrPath `
                -Raw `
                -ErrorAction SilentlyContinue

            if ($null -ne $stderrValue) {
                $stderr = $stderrValue.Trim()
            }
        }
    }
    finally {
        $ErrorActionPreference = (
            $previousErrorActionPreference
        )

        Remove-Item `
            -LiteralPath $stderrPath `
            -Force `
            -ErrorAction SilentlyContinue
    }

    if ($exitCode -ne 0) {
        $diagnostic = @(
            $stderr,
            $stdout
        ) |
            Where-Object {
                -not [string]::IsNullOrWhiteSpace($_)
            }

        throw (
            "OpenClaw command failed (exit " +
            $exitCode +
            "): " +
            ($Arguments -join " ") +
            [Environment]::NewLine +
            ($diagnostic -join [Environment]::NewLine)
        )
    }

    try {
        return (
            $stdout |
            ConvertFrom-Json
        )
    }
    catch {
        throw (
            "OpenClaw returned invalid JSON for: " +
            ($Arguments -join " ") +
            [Environment]::NewLine +
            "stdout: " +
            $stdout +
            [Environment]::NewLine +
            "stderr: " +
            $stderr
        )
    }
}


$addByAgent = @{
    "cf-physical-model" = @(
        "classifire_submit_initial_physical_model"
    )
}

$managedAgentIds = @(
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

$allControlledWriteTools = @(
    "classifire_register_evidence_observations",
    "classifire_submit_initial_physical_model",
    "classifire_select_repair_strategy",
    "classifire_lock_repair_strategy",
    "classifire_derive_quantity_labour",
    "classifire_required_components",
    "classifire_derive_commercial"
)

$retiredControlledWriteTools = @(
    "classifire_lock_physical_model"
)

$allManagedControlledWriteTools = @(
    ($allControlledWriteTools + $retiredControlledWriteTools) |
    Sort-Object -Unique
)

Write-Host "Validating existing OpenClaw config before plugin install..." -ForegroundColor Cyan
$configValidationResult = Invoke-OpenClawCaptured -Arguments @(
    "config",
    "validate",
    "--json"
)

$configValidation = (
    $configValidationResult.Output.Trim()
)

if ($configValidationResult.ExitCode -ne 0) {
    throw (
        "OpenClaw config is invalid before CLASSIFIRE controlled-write installation. " +
        "Run 'openclaw config validate --json' and 'openclaw doctor --lint --json' and review the reported issue before repair. " +
        "Validation output: $configValidation"
    )
}

if (-not $PlanOnly) {
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
    # OpenClaw may emit non-fatal configuration warnings to stderr.
    # Windows PowerShell 5.1 can promote that stderr to NativeCommandError
    # when $ErrorActionPreference is "Stop". Capture both streams while
    # preserving the native process exit code as the authority.
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $installOutput = (
            & $openclaw.Source plugins install `
                --link $pluginRoot `
                2>&1 |
            Out-String
        )
        $installExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($installExitCode -ne 0 -and $installOutput -notmatch "already (installed|linked|registered)" -and $installOutput -notmatch "already exists") {
        throw "OpenClaw controlled-write plugin install failed: $($installOutput.Trim())"
    }
    if ($installOutput.Trim()) { Write-Host $installOutput.Trim() -ForegroundColor DarkGray }

}
else {
    Write-Host "Plan-only: skipping plugin build/link installation." -ForegroundColor DarkGray
}

Write-Host "Resolving existing cf-* agent tool grants..." -ForegroundColor Cyan
$agentsValue = Invoke-OpenClawJsonRead -Arguments @(
    "config",
    "get",
    "agents.list",
    "--json"
)
$agents = @(Convert-ToAgentItems $agentsValue)
$indexById = @{}
for ($i = 0; $i -lt $agents.Count; $i++) {
    $id = [string]$agents[$i].id
    if ($id) { $indexById[$id] = $i }
}
$requiredAgentIds = @($managedAgentIds | Sort-Object -Unique)
foreach ($id in $requiredAgentIds) {
    if (-not $indexById.ContainsKey($id)) {
        throw "Required CLASSIFIRE agent '$id' is missing from OpenClaw agents.list."
    }
}

$operations = @(
    [pscustomobject]@{
        path = 'plugins.entries["classifire-controlled-write"].config.baseUrl'
        value = $BaseUrl
    },
    [pscustomobject]@{
        path = 'plugins.entries["classifire-controlled-write"].config.tokenFile'
        value = $TokenFile
    },
    [pscustomobject]@{
        path = 'plugins.entries["classifire-controlled-write"].config.deploymentProfile'
        value = 'phase8-admission-only'
    },
    [pscustomobject]@{
        path = 'agents.defaults.pdfMaxPages'
        value = 200
    },
    [pscustomobject]@{
        path = 'agents.defaults.model.primary'
        value = 'openai/gpt-5.6'
    },
    [pscustomobject]@{
        path = 'gateway.http.endpoints.responses.enabled'
        value = $true
    },
    [pscustomobject]@{
        path = 'gateway.http.endpoints.responses.files.allowUrl'
        value = $false
    },
    [pscustomobject]@{
        path = 'gateway.http.endpoints.responses.images.allowUrl'
        value = $false
    },
    [pscustomobject]@{
        path = 'gateway.http.endpoints.responses.images.allowedMimes'
        # Linked report originals are verified JPEGs.  Keep the previously
        # approved JPEG allowance when installing the controlled-write plugin;
        # reducing this list to PNG would silently break high-detail visual
        # evidence handling after deployment.
        value = @('image/png', 'image/jpeg')
    },
    [pscustomobject]@{
        path = 'gateway.http.endpoints.responses.images.maxBytes'
        value = 10485760
    },
    [pscustomobject]@{
        path = 'tools.media.models'
        value = @(
            [ordered]@{
                provider = 'openai'
                model = 'gpt-5.6-sol'
                capabilities = @('image')
                maxChars = 20000
                maxBytes = 10485760
                timeoutSeconds = 180
            }
        )
    },
    [pscustomobject]@{
        path = 'tools.media.image.attachments.mode'
        value = 'all'
    },
    [pscustomobject]@{
        path = 'tools.media.image.attachments.maxAttachments'
        value = 20
    }
)

foreach ($id in ($managedAgentIds | Sort-Object)) {
    $index = $indexById[$id]
    $toolsNode = $agents[$index].tools

    $existing = @()
    if ($null -ne $toolsNode -and $null -ne $toolsNode.alsoAllow) {
        $existing = @($toolsNode.alsoAllow)
    }

    $retained = @(
        $existing |
        ForEach-Object { [string]$_ } |
        Where-Object {
            $_ -notin $allManagedControlledWriteTools
        }
    )

    $desiredTools = if ($addByAgent.ContainsKey($id)) {
        @($addByAgent[$id])
    }
    else {
        @()
    }

    $merged = @(
        $retained + $desiredTools |
        Sort-Object -Unique
    )

    $operations += [pscustomobject]@{
        path = "agents.list[$index].tools.alsoAllow"
        value = $merged
    }

    $sandboxAllow = @()

    if (
        $null -ne $toolsNode -and
        $null -ne $toolsNode.sandbox -and
        $null -ne $toolsNode.sandbox.tools -and
        $null -ne $toolsNode.sandbox.tools.alsoAllow
    ) {
        $sandboxAllow = @(
            $toolsNode.sandbox.tools.alsoAllow
        )
    }

    $sandboxAllow = @(
        $sandboxAllow |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -ne "classifire-controlled-write" } |
        Sort-Object -Unique
    )

    if ($id -eq "cf-physical-model") {
        $sandboxAllow = @(
            $sandboxAllow + "classifire-controlled-write" |
            Sort-Object -Unique
        )
    }

    $operations += [pscustomobject]@{
        path = "agents.list[$index].tools.sandbox.tools.alsoAllow"
        value = $sandboxAllow
    }
}

$physicalIndex = $indexById["cf-physical-model"]
$physicalTools = $agents[$physicalIndex].tools
$physicalDeny = @()

if ($null -ne $physicalTools -and $null -ne $physicalTools.deny) {
    $physicalDeny = @(
        $physicalTools.deny |
        ForEach-Object { [string]$_ } |
        Where-Object { $_ -ne "classifire_submit_initial_physical_model" }
    )
}

$physicalDeny = @(
    $physicalDeny +
    @(
        "classifire_lock_physical_model",
        "classifire_derive_quantity_labour"
    ) |
    Sort-Object -Unique
)

$operations += [pscustomobject]@{
    path = "agents.list[$physicalIndex].tools.deny"
    value = $physicalDeny
}

$validatorIndex = $indexById["cf-validator"]
$validatorTools = $agents[$validatorIndex].tools

$validatorDeny = @()
if ($null -ne $validatorTools -and $null -ne $validatorTools.deny) {
    $validatorDeny = @(
        $validatorTools.deny |
        ForEach-Object { [string]$_ }
    )
}

$validatorDeny = @(
    $validatorDeny +
    @(
        "classifire_submit_initial_physical_model",
        "classifire_derive_quantity_labour"
    ) |
    Sort-Object -Unique
)

$operations += [pscustomobject]@{
    path = "agents.list[$validatorIndex].tools.deny"
    value = $validatorDeny
}


$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$batchFile = Join-Path $env:TEMP "classifire-controlled-write-$stamp.batch.json"
Write-Utf8NoBom -Path $batchFile -Content (@($operations) | ConvertTo-Json -Depth 8)

try {
    Write-Host "Dry-running controlled-write plugin config and merged agent grants..." -ForegroundColor Cyan
    $dryResult = Invoke-OpenClawCaptured -Arguments @(
        "config",
        "set",
        "--batch-file",
        $batchFile,
        "--dry-run"
    )

    $dry = $dryResult.Output

    if ($dryResult.ExitCode -ne 0) {
        throw "OpenClaw controlled-write config dry-run failed: $($dry.Trim())"
    }

    if ($PlanOnly) {
        Write-Host $dry.Trim()
        Write-Host "CLASSIFIRE OpenClaw configuration PLAN-ONLY: PASS" -ForegroundColor Green
        Write-Host "No OpenClaw configuration was persisted." -ForegroundColor Green
        return
    }

    Write-Host "Applying controlled-write plugin config and merged agent grants..." -ForegroundColor Cyan
    $applyResult = Invoke-OpenClawCaptured -Arguments @(
        "config",
        "set",
        "--batch-file",
        $batchFile
    )

    $apply = $applyResult.Output

    if ($applyResult.ExitCode -ne 0) {
        throw "OpenClaw controlled-write config apply failed: $($apply.Trim())"
    }
}
finally {
    Remove-Item -LiteralPath $batchFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Enabling CLASSIFIRE controlled-write plugin..." -ForegroundColor Cyan
$enableResult = Invoke-OpenClawCaptured -Arguments @(
    "plugins",
    "enable",
    "classifire-controlled-write"
)

if ($enableResult.Output.Trim()) {
    Write-Host $enableResult.Output.Trim()
}

if ($enableResult.ExitCode -ne 0) {
    throw (
        "Unable to enable classifire-controlled-write plugin: " +
        $enableResult.Output.Trim()
    )
}

$validateResult = Invoke-OpenClawCaptured -Arguments @(
    "config",
    "validate",
    "--json"
)

if ($validateResult.Output.Trim()) {
    Write-Host $validateResult.Output.Trim()
}

if ($validateResult.ExitCode -ne 0) {
    throw (
        "OpenClaw config validation failed after " +
        "controlled-write installation: " +
        $validateResult.Output.Trim()
    )
}

Write-Host "Restarting OpenClaw Gateway..." -ForegroundColor Cyan
$restartResult = Invoke-OpenClawCaptured -Arguments @(
    "gateway",
    "restart"
)

if ($restartResult.Output.Trim()) {
    Write-Host $restartResult.Output.Trim()
}

if ($restartResult.ExitCode -ne 0) {
    throw "OpenClaw Gateway restart failed."
}

Write-Host "Inspecting live controlled-write plugin runtime..." -ForegroundColor Cyan
$inspectResult = Invoke-OpenClawCaptured -Arguments @(
    "plugins",
    "inspect",
    "classifire-controlled-write",
    "--runtime",
    "--json"
)

if ($inspectResult.Output.Trim()) {
    Write-Host $inspectResult.Output.Trim()
}

if ($inspectResult.ExitCode -ne 0) {
    throw "CLASSIFIRE controlled-write plugin runtime inspection failed."
}

Write-Host "CLASSIFIRE controlled-write plugin installed." -ForegroundColor Green
Write-Host "Phase 8 admission-only profile active: only cf-physical-model received classifire_submit_initial_physical_model." -ForegroundColor Green
Write-Host "OpenClaw PDF extraction allowance set to 200 pages for CLASSIFIRE report review." -ForegroundColor Green
Write-Host "Human Release, library approval and generic estimate:write remain unavailable to agents." -ForegroundColor Green
