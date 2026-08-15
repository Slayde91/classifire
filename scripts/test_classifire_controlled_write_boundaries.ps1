param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "CLASSIFIRE virtual-environment Python is missing: $venvPython"
}
$python = Get-Command -Name $venvPython -ErrorAction Stop
$TokenFile = [System.IO.Path]::GetFullPath($TokenFile)
$managedApiProcess = $null

if (-not (Test-Path -LiteralPath $TokenFile)) {
    throw "CLASSIFIRE agent token file is missing: $TokenFile"
}

$tokenDoc = Get-Content -LiteralPath $TokenFile -Raw | ConvertFrom-Json
if ($tokenDoc.schema -ne "CLASSIFIRE-AGENT-TOKENS-v1") {
    throw "Unexpected CLASSIFIRE token-file schema."
}

$expectedByAgent = @{
    "cf-orchestrator" = @()
    "cf-intake-evidence" = @("classifire_register_evidence_observations")
    "cf-physical-model" = @(
        "classifire_submit_initial_physical_model",
        "classifire_lock_physical_model"
    )
    "cf-technical-system" = @("classifire_select_repair_strategy", "classifire_lock_repair_strategy")
    "cf-commercial-engine" = @("classifire_required_components", "classifire_derive_commercial")
    "cf-validator" = @()
    "cf-output" = @()
    "cf-library-governance" = @()
    "cf-platform-governance" = @()
}

$allWriteTools = @(
    "classifire_register_evidence_observations",
    "classifire_submit_initial_physical_model",
    "classifire_lock_physical_model",
    "classifire_select_repair_strategy",
    "classifire_lock_repair_strategy",
    "classifire_derive_quantity_labour",
    "classifire_required_components",
    "classifire_derive_commercial"
)

function Convert-OpenClawJson {
    param([string]$Raw)
    $start = $Raw.IndexOf('{')
    $end = $Raw.LastIndexOf('}')
    if ($start -lt 0 -or $end -lt $start) {
        throw "OpenClaw did not return a JSON object. Output: $Raw"
    }
    return $Raw.Substring($start, $end - $start + 1) | ConvertFrom-Json
}

function Convert-ToOpenClawNativeJsonArgument {
    param([string]$Json)
    if ($env:OS -eq "Windows_NT" -and $PSVersionTable.PSVersion.Major -lt 6) {
        return $Json.Replace('"', '\"')
    }
    return $Json
}

function Get-ClassifireToolNames {
    param([object]$Value)
    $serialized = $Value | ConvertTo-Json -Depth 30 -Compress
    return @(
        [regex]::Matches($serialized, 'classifire_[A-Za-z0-9_]+') |
            ForEach-Object { $_.Value } |
            Sort-Object -Unique
    )
}

function Get-AgentToken {
    param([string]$AgentId)
    $property = $tokenDoc.tokens.PSObject.Properties[$AgentId]
    if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        throw "No token found for $AgentId."
    }
    return [string]$property.Value
}

function Test-ClassifireApiHealth {
    try {
        $health = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/healthz") -Method GET -ErrorAction Stop
        return ($health.status -eq "ok" -and $health.product -eq "CLASSIFIRE")
    }
    catch {
        return $false
    }
}

function Start-ManagedClassifireApiIfNeeded {
    if (Test-ClassifireApiHealth) {
        Write-Host "PASS CLASSIFIRE API health (existing process)" -ForegroundColor Green
        return
    }

    $logRoot = Join-Path $repoRoot "data\uat\boundary-api"
    New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $stdout = Join-Path $logRoot "$stamp.stdout.log"
    $stderr = Join-Path $logRoot "$stamp.stderr.log"

    Write-Host "CLASSIFIRE API is offline; starting a temporary local boundary-test API..." -ForegroundColor DarkYellow
    $startParams = @{
        FilePath = $python.Source
        ArgumentList = @("-m", "uvicorn", "classifire.main:app", "--host", "127.0.0.1", "--port", "8787")
        WorkingDirectory = $repoRoot
        RedirectStandardOutput = $stdout
        RedirectStandardError = $stderr
        PassThru = $true
    }
    $script:managedApiProcess = Start-Process @startParams

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (Test-ClassifireApiHealth) {
            Write-Host "PASS CLASSIFIRE API health (temporary managed process)" -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 250
    }

    $detail = ""
    if (Test-Path -LiteralPath $stderr) {
        $detail = (Get-Content -LiteralPath $stderr -Raw -ErrorAction SilentlyContinue).Trim()
    }
    throw "CLASSIFIRE API could not be started for boundary testing. $detail"
}

function Get-HttpStatusFromError {
    param([System.Management.Automation.ErrorRecord]$ErrorRecord)
    $response = $ErrorRecord.Exception.Response
    if ($null -ne $response -and $null -ne $response.StatusCode) {
        try { return [int]$response.StatusCode } catch { }
    }
    if ($null -ne $ErrorRecord.Exception.StatusCode) {
        try { return [int]$ErrorRecord.Exception.StatusCode } catch { }
    }
    return $null
}

function Assert-ForbiddenApi {
    param(
        [string]$AgentId,
        [string]$Path,
        [string]$Method = "POST",
        [object]$Body = $null
    )

    $headers = @{
        Authorization = "Bearer $(Get-AgentToken $AgentId)"
        "X-Classifire-Agent-ID" = $AgentId
    }
    $params = @{
        Uri = ($BaseUrl.TrimEnd('/') + $Path)
        Method = $Method
        Headers = $headers
        UseBasicParsing = $true
        ErrorAction = "Stop"
    }
    if ($null -ne $Body) {
        $params.ContentType = "application/json"
        $params.Body = ($Body | ConvertTo-Json -Depth 8 -Compress)
    }

    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $params.SkipHttpErrorCheck = $true
        try {
            $response = Invoke-WebRequest @params
        }
        catch {
            throw "CLASSIFIRE API transport failure for $AgentId -> $Method ${Path}: $($_.Exception.Message)"
        }
        $status = [int]$response.StatusCode
    }
    else {
        try {
            $response = Invoke-WebRequest @params
            $status = [int]$response.StatusCode
        }
        catch {
            $status = Get-HttpStatusFromError -ErrorRecord $_
            if ($null -eq $status) {
                throw "CLASSIFIRE API transport failure for $AgentId -> $Method ${Path}: $($_.Exception.Message)"
            }
        }
    }

    if ($status -ne 403) {
        throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received HTTP $status."
    }
}

function Test-OpenClawGatewayRpc {
    $raw = (& $openclaw.Source gateway status --require-rpc --timeout 30000 2>&1 | Out-String)
    return ($LASTEXITCODE -eq 0)
}

function Restart-OpenClawGatewayAndWait {
    Write-Host "Restarting OpenClaw Gateway and waiting for RPC..." -ForegroundColor DarkYellow
    $restart = (& $openclaw.Source gateway restart 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw Gateway restart failed: $($restart.Trim())"
    }
    for ($attempt = 0; $attempt -lt 12; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-OpenClawGatewayRpc) {
            Write-Host "PASS OpenClaw Gateway RPC" -ForegroundColor Green
            return
        }
    }
    throw "OpenClaw Gateway RPC did not become healthy after restart."
}

function Ensure-OpenClawGatewayRpc {
    if (Test-OpenClawGatewayRpc) {
        Write-Host "PASS OpenClaw Gateway RPC" -ForegroundColor Green
        return
    }
    Restart-OpenClawGatewayAndWait
}

function Invoke-GatewayJson {
    param(
        [string]$Method,
        [hashtable]$Params,
        [string]$Context
    )

    $paramsJson = $Params | ConvertTo-Json -Depth 12 -Compress
    $paramsNative = Convert-ToOpenClawNativeJsonArgument -Json $paramsJson

    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $raw = (& $openclaw.Source gateway call $Method --params $paramsNative --timeout 60000 --json 2>&1 | Out-String).Trim()
        $exitCode = $LASTEXITCODE
        $parsed = $null
        try { $parsed = Convert-OpenClawJson $raw } catch { }

        $transportFailure = $false
        if ($null -ne $parsed -and $parsed.ok -eq $false -and $null -ne $parsed.error) {
            $errorType = [string]$parsed.error.type
            $errorKind = [string]$parsed.error.kind
            $transportFailure = ($errorType -eq "gateway_transport_error" -or $errorKind -eq "timeout")
        }
        elseif ($exitCode -ne 0 -and $raw -match "(?i)gateway.*(timeout|transport|closed|unavailable)") {
            $transportFailure = $true
        }

        if ($exitCode -eq 0 -and $null -ne $parsed -and -not $transportFailure) {
            return $parsed
        }

        if ($attempt -eq 0 -and $transportFailure) {
            Write-Host "Gateway RPC transient failure during $Context; restarting once and retrying..." -ForegroundColor DarkYellow
            Restart-OpenClawGatewayAndWait
            continue
        }

        throw "Gateway call $Method failed for ${Context}: $raw"
    }
}

try {
    Start-ManagedClassifireApiIfNeeded

    Write-Host "Checking CLASSIFIRE agent intake/physical routes are loaded..." -ForegroundColor Cyan
    $openApi = Invoke-RestMethod -Uri ($BaseUrl.TrimEnd('/') + "/openapi.json") -Method GET -ErrorAction Stop
    $requiredAgentPaths = @(
        "/api/v1/agent/estimates/{estimate_id}/evidence/register",
        "/api/v1/agent/estimates/{estimate_id}/physical-model/initial",
        "/api/v1/agent/estimates/{estimate_id}/physical-model/lock"
    )
    $availablePaths = @($openApi.paths.PSObject.Properties.Name)
    $missingPaths = @($requiredAgentPaths | Where-Object { $availablePaths -notcontains $_ })
    if ($missingPaths.Count -gt 0) {
        throw (
            "The running CLASSIFIRE API is stale and does not expose the new controlled intake/physical routes: " +
            ($missingPaths -join ", ") +
            ". Restart the existing CLASSIFIRE API from the current C:\CLASSIFIRE checkout, then rerun this test."
        )
    }
    Write-Host "PASS controlled intake/physical API routes loaded" -ForegroundColor Green

    Write-Host "Checking controlled-write API cross-role denial..." -ForegroundColor Cyan
    foreach ($agentId in ($expectedByAgent.Keys | Sort-Object)) {
        if ($agentId -eq "cf-intake-evidence") {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-real/physical-model/initial" -Body @{ openings = @(); services = @() }
        }
        elseif ($agentId -eq "cf-physical-model") {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-real/evidence/register" -Body @{ observations = @(@{ stored_file_id = "x"; evidence_type = "page" }) }
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-real/quantity-labour/derive" -Body @{}
        }
        elseif ($agentId -eq "cf-technical-system") {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-real/commercial/derive" -Body @{}
        }
        else {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/openings/not-real/repair-strategy" -Body @{ variant_id = "VAR-001" }
        }
        Write-Host "PASS controlled-write API denial $agentId" -ForegroundColor Green
    }

    $forbiddenAgentAuthoritySegment = '/(human[-_]?release|release|approve|approval)(/|$)'
    $badPaths = @($openApi.paths.PSObject.Properties.Name | Where-Object {
        $path = ([string]$_).ToLowerInvariant()
        $path -like "/api/v1/agent/*" -and $path -match $forbiddenAgentAuthoritySegment
    })
    if ($badPaths.Count -gt 0) {
        throw "Human Release/approval-like route exists under the agent API: $($badPaths -join ', ')"
    }
    Write-Host "PASS controlled-write API exposes no Human Release/approval route" -ForegroundColor Green

    Write-Host ""
    Write-Host "Checking OpenClaw Gateway RPC..." -ForegroundColor Cyan
    Ensure-OpenClawGatewayRpc

    Write-Host "Checking OpenClaw controlled-write effective tool boundaries..." -ForegroundColor Cyan
    $stamp = Get-Date -Format "yyyyMMddHHmmss"
    foreach ($agentId in ($expectedByAgent.Keys | Sort-Object)) {
        $sessionAlias = "classifire-write-boundary-$stamp-$agentId"
        $raw = (& $openclaw.Source agent --agent $agentId --session-key $sessionAlias --message "Reply exactly READY. Do not call any tools." --timeout 180 --json 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "OpenClaw agent probe failed for $agentId. Output: $raw"
        }
        $json = Convert-OpenClawJson $raw
        $canonicalSessionKey = [string]$json.result.meta.systemPromptReport.sessionKey
        if ([string]::IsNullOrWhiteSpace($canonicalSessionKey)) {
            $canonicalSessionKey = ("agent:{0}:{1}" -f $agentId, $sessionAlias)
        }

        $effective = Invoke-GatewayJson -Method "tools.effective" -Params @{ sessionKey = $canonicalSessionKey } -Context $agentId
        $visibleAll = @(Get-ClassifireToolNames -Value $effective)
        $visible = @($visibleAll | Where-Object { $allWriteTools -contains $_ })
        $expected = @($expectedByAgent[$agentId])

        foreach ($tool in $expected) {
            if ($visible -notcontains $tool) {
                throw "$agentId is missing authorised controlled-write tool $tool. Visible write tools: $($visible -join ', ')"
            }
        }
        foreach ($tool in $allWriteTools) {
            if ($expected -notcontains $tool -and $visible -contains $tool) {
                throw "$agentId can see forbidden controlled-write tool $tool."
            }
        }

        Write-Host "PASS controlled-write tools $agentId -> $($visible -join ', ')" -ForegroundColor Green
    }

    Write-Host ""
    Write-Host "CLASSIFIRE controlled-write role-boundary test PASSED for all 9 agents." -ForegroundColor Green
}
finally {
    if ($null -ne $managedApiProcess) {
        try {
            if (-not $managedApiProcess.HasExited) {
                Stop-Process -Id $managedApiProcess.Id -Force -ErrorAction SilentlyContinue
            }
        }
        catch { }
        Write-Host "Stopped temporary CLASSIFIRE boundary-test API." -ForegroundColor DarkGray
    }
}
