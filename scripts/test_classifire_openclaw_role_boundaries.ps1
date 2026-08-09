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
    "cf-orchestrator" = @("classifire_health", "classifire_workflow_status")
    "cf-intake-evidence" = @("classifire_health", "classifire_workflow_status", "classifire_evidence_read")
    "cf-physical-model" = @("classifire_health", "classifire_workflow_status", "classifire_physical_model_read")
    "cf-technical-system" = @("classifire_health", "classifire_workflow_status", "classifire_technical_search")
    "cf-commercial-engine" = @("classifire_health", "classifire_workflow_status", "classifire_package14_recommendation")
    "cf-validator" = @("classifire_health", "classifire_workflow_status", "classifire_run_validation")
    "cf-output" = @("classifire_health", "classifire_workflow_status", "classifire_lock_snapshot", "classifire_render_output")
    "cf-library-governance" = @("classifire_health", "classifire_workflow_status", "classifire_library_releases")
    "cf-platform-governance" = @("classifire_health", "classifire_workflow_status")
}

$allClassifireTools = @(
    "classifire_health",
    "classifire_workflow_status",
    "classifire_evidence_read",
    "classifire_physical_model_read",
    "classifire_technical_search",
    "classifire_package14_recommendation",
    "classifire_run_validation",
    "classifire_lock_snapshot",
    "classifire_render_output",
    "classifire_library_releases"
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

function Get-AgentToken {
    param([string]$AgentId)
    $property = $tokenDoc.tokens.PSObject.Properties[$AgentId]
    if ($null -eq $property -or [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        throw "No token found for $AgentId."
    }
    return [string]$property.Value
}

function Invoke-AgentApi {
    param(
        [string]$AgentId,
        [string]$Path,
        [string]$Method = "GET",
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
    return Invoke-WebRequest @params
}

function Assert-ForbiddenApi {
    param(
        [string]$AgentId,
        [string]$Path,
        [string]$Method = "GET",
        [object]$Body = $null
    )

    try {
        $response = Invoke-AgentApi -AgentId $AgentId -Path $Path -Method $Method -Body $Body
        throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received $($response.StatusCode)."
    }
    catch [System.Net.WebException] {
        $status = [int]$_.Exception.Response.StatusCode
        if ($status -ne 403) {
            throw "Expected HTTP 403 for $AgentId -> $Method $Path, but received HTTP $status."
        }
    }
}

Write-Host "Checking CLASSIFIRE API health with every agent credential..." -ForegroundColor Cyan
foreach ($agentId in ($expectedByAgent.Keys | Sort-Object)) {
    $response = Invoke-AgentApi -AgentId $agentId -Path "/api/v1/agent/health"
    if ($response.StatusCode -ne 200) {
        throw "Authenticated health failed for $agentId with HTTP $($response.StatusCode)."
    }
    $body = $response.Content | ConvertFrom-Json
    if ($body.agent_id -ne $agentId -or $body.human_release_exposed -ne $false) {
        throw "Authenticated health returned an unexpected identity or Human Release exposure for $agentId."
    }
    Write-Host "PASS API health $agentId" -ForegroundColor Green
}

Write-Host ""
Write-Host "Checking API cross-role denial..." -ForegroundColor Cyan
foreach ($agentId in ($expectedByAgent.Keys | Sort-Object)) {
    if ($agentId -eq "cf-library-governance") {
        Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/estimates/not-a-real-estimate/independent-validation" -Method "POST"
    }
    else {
        Assert-ForbiddenApi -AgentId $agentId -Path "/api/v1/agent/library/releases"
    }
    Write-Host "PASS API denial $agentId" -ForegroundColor Green
}

$openApi = Invoke-RestMethod ($BaseUrl.TrimEnd('/') + "/openapi.json")
$agentHumanReleasePaths = @($openApi.paths.PSObject.Properties.Name | Where-Object {
    $_ -like "/api/v1/agent/*" -and $_ -match "release"
})
if ($agentHumanReleasePaths.Count -gt 0) {
    throw "Human Release-like route exists under the agent API: $($agentHumanReleasePaths -join ', ')"
}
Write-Host "PASS no Human Release route exists under /api/v1/agent" -ForegroundColor Green

Write-Host ""
Write-Host "Checking OpenClaw direct tool visibility per agent..." -ForegroundColor Cyan
$stamp = Get-Date -Format "yyyyMMddHHmmss"
foreach ($agentId in ($expectedByAgent.Keys | Sort-Object)) {
    $sessionKey = "classifire-role-boundary-$stamp-$agentId"
    $raw = (& $openclaw.Source agent --agent $agentId --session-key $sessionKey --message "Reply exactly READY. Do not call any tools." --timeout 180 --json 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "OpenClaw agent probe failed for $agentId. Output: $raw"
    }
    $json = Convert-OpenClawJson $raw
    $entries = @($json.result.meta.systemPromptReport.tools.entries)
    $visible = @($entries | ForEach-Object { [string]$_.name } | Where-Object { $_ -like "classifire_*" })
    $expected = @($expectedByAgent[$agentId])

    foreach ($tool in $expected) {
        if ($visible -notcontains $tool) {
            throw "$agentId is missing authorised direct tool $tool. Visible CLASSIFIRE tools: $($visible -join ', ')"
        }
    }
    foreach ($tool in $allClassifireTools) {
        if ($expected -notcontains $tool -and $visible -contains $tool) {
            throw "$agentId can see forbidden CLASSIFIRE tool $tool."
        }
    }
    if ($visible -contains "classifire_human_release" -or $visible -contains "human_release") {
        throw "$agentId can see a Human Release tool."
    }

    Write-Host "PASS tool boundary $agentId -> $($visible -join ', ')" -ForegroundColor Green
}

Write-Host ""
Write-Host "CLASSIFIRE OpenClaw role-boundary test PASSED for all 9 agents." -ForegroundColor Green
