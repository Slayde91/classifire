param(
    [string]$TokenFile = (Join-Path $HOME ".openclaw\classifire-agent-tokens.json"),
    [string]$BaseUrl = "http://127.0.0.1:8787"
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop
$TokenFile = [System.IO.Path]::GetFullPath($TokenFile)

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
    try {
        $response = Invoke-WebRequest @params
        throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received $($response.StatusCode)."
    }
    catch [System.Net.WebException] {
        $status = [int]$_.Exception.Response.StatusCode
        if ($status -ne 403) {
            throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received HTTP $status."
        }
    }
}

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

$openApi = Invoke-RestMethod ($BaseUrl.TrimEnd('/') + "/openapi.json")
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
