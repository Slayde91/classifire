param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$python = Get-Command python -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
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
        "classifire_lock_physical_model",
        "classifire_derive_quantity_labour"
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
    $script:managedApiProcess = Start-Process \
        -FilePath $python.Source \
        -ArgumentList @("-m", "uvicorn", "classifire.main:app", "--host", "127.0.0.1", "--port", "8787") \
        -WorkingDirectory $repoRoot \
        -RedirectStandardOutput $stdout \
        -RedirectStandardError $stderr \
        -PassThru

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
            throw "CLASSIFIRE API transport failure for $AgentId -> $Method $Path: $($_.Exception.Message)"
        }
        $status = [int]$response.StatusCode
        if ($status -ne 403) {
            throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received HTTP $status."
        }
        return
    }

    try {
        $response = Invoke-WebRequest @params
        $status = [int]$response.StatusCode
    }
    catch {
        $status = Get-HttpStatusFromError -ErrorRecord $_
        if ($null -eq $status) {
            throw "CLASSIFIRE API transport failure for $AgentId -> $Method $Path: $($_.Exception.Message)"
        }
    }
    if ($status -ne 403) {
        throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received HTTP $status."
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
        }
        elseif ($agentId -eq "cf-technical-system") {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-real/commercial/derive" -Body @{}
        }
        elseif ($agentId -eq "cf-commercial-engine") {
            Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/openings/not-real/repair-strategy" -Body @{ variant_id = "VAR-001" }
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

        $paramsJson = @{ sessionKey = $canonicalSessionKey } | ConvertTo-Json -Compress
        $paramsNative = Convert-ToOpenClawNativeJsonArgument -Json $paramsJson
        $effectiveRaw = (& $openclaw.Source gateway call tools.effective --params $paramsNative --json 2>&1 | Out-String)
        if ($LASTEXITCODE -ne 0) {
            throw "tools.effective failed for $agentId. Output: $effectiveRaw"
        }
        $effective = Convert-OpenClawJson $effectiveRaw
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
