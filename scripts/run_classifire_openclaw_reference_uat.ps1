param(
    [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [int]$TimeoutSeconds = 300,
    [string]$BaseUrl = "http://127.0.0.1:8787",
    [string]$GatewayHttpBaseUrl = "http://127.0.0.1:18789"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$openclaw = Get-Command openclaw -ErrorAction Stop
$python = Get-Command python -ErrorAction Stop
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$uatHelper = Join-Path $repoRoot "scripts\classifire_reference_uat.py"
$receiptDir = Join-Path $repoRoot ("data\uat\" + $RunId)
New-Item -ItemType Directory -Path $receiptDir -Force | Out-Null

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    [System.IO.File]::WriteAllText(
        $Path,
        $Content,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Save-Receipt {
    param([string]$Name, [string]$Content)
    $path = Join-Path $receiptDir $Name
    Write-Utf8NoBom -Path $path -Content $Content
    return $path
}

function Convert-OpenClawJson {
    param([string]$Raw)
    $trimmed = ($Raw | Out-String).Trim()
    try {
        return $trimmed | ConvertFrom-Json
    }
    catch {
        $start = $trimmed.IndexOf('{')
        $end = $trimmed.LastIndexOf('}')
        if ($start -lt 0 -or $end -lt $start) {
            throw "OpenClaw did not return a JSON object. Output: $trimmed"
        }
        return $trimmed.Substring($start, $end - $start + 1) | ConvertFrom-Json
    }
}

function Convert-ToOpenClawNativeJsonArgument {
    param([string]$Json)

    # tools.effective still uses Gateway WebSocket RPC. Its JSON contains only
    # the canonical session key, so the existing Windows PowerShell 5.1 quote
    # preservation is sufficient for that read-only RPC boundary.
    if ($env:OS -eq "Windows_NT" -and $PSVersionTable.PSVersion.Major -lt 6) {
        return $Json.Replace('"', '\"')
    }
    return $Json
}

function Get-OpenClawConfigScalar {
    param([string]$Path)

    $raw = (& $openclaw.Source config get $Path --json 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($raw)) {
        return $null
    }
    try {
        $value = $raw | ConvertFrom-Json
        if ($value -is [string]) { return [string]$value }
        if ($value -is [bool] -or $value -is [int] -or $value -is [long]) { return [string]$value }
        return $null
    }
    catch {
        return $raw.Trim('"')
    }
}

function Get-OpenClawGatewayHttpHeaders {
    $mode = Get-OpenClawConfigScalar -Path "gateway.auth.mode"
    if ([string]::IsNullOrWhiteSpace($mode)) {
        $mode = "token"
    }
    $mode = $mode.ToLowerInvariant()

    if ($mode -eq "none") {
        return @{}
    }

    $secret = $null
    if ($mode -eq "token") {
        $secret = [string]$env:OPENCLAW_GATEWAY_TOKEN
        if ([string]::IsNullOrWhiteSpace($secret)) {
            $secret = Get-OpenClawConfigScalar -Path "gateway.auth.token"
        }
    }
    elseif ($mode -eq "password") {
        $secret = [string]$env:OPENCLAW_GATEWAY_PASSWORD
        if ([string]::IsNullOrWhiteSpace($secret)) {
            $secret = Get-OpenClawConfigScalar -Path "gateway.auth.password"
        }
    }
    elseif ($mode -eq "trusted-proxy") {
        # OpenClaw permits a same-host direct password fallback for trusted-proxy
        # mode when no forwarded identity headers are supplied.
        $secret = [string]$env:OPENCLAW_GATEWAY_PASSWORD
        if ([string]::IsNullOrWhiteSpace($secret)) {
            $secret = Get-OpenClawConfigScalar -Path "gateway.auth.password"
        }
        if ([string]::IsNullOrWhiteSpace($secret)) {
            throw "OpenClaw gateway.auth.mode is trusted-proxy but no same-host gateway.auth.password/OPENCLAW_GATEWAY_PASSWORD fallback is available for the UAT HTTP caller."
        }
    }
    else {
        throw "Unsupported OpenClaw gateway.auth.mode '$mode' for the controlled UAT HTTP caller."
    }

    if ([string]::IsNullOrWhiteSpace($secret)) {
        throw "Unable to resolve the OpenClaw Gateway $mode credential. Configure gateway.auth.$mode or the corresponding OPENCLAW_GATEWAY_* environment variable."
    }

    return @{ Authorization = "Bearer $secret" }
}

function Initialize-UatAgentSession {
    param(
        [string]$Stage,
        [string]$AgentId
    )

    $alias = "classifire-uat-$RunId-$Stage"
    $promptFile = Join-Path $env:TEMP ("classifire-uat-" + $RunId + "-" + $Stage + "-ready.txt")
    $stderrFile = Join-Path $env:TEMP ("classifire-uat-" + $RunId + "-" + $Stage + "-ready.stderr.txt")
    Write-Utf8NoBom -Path $promptFile -Content (
        "Controlled CLASSIFIRE UAT session readiness check. Reply exactly READY. " +
        "Do not call any tools. Mandatory governed actions are invoked separately by the UAT controller."
    )
    try {
        Write-Host "Opening $Stage session for $AgentId..." -ForegroundColor Cyan
        $raw = (& $openclaw.Source agent `
            --agent $AgentId `
            --session-key $alias `
            --message-file $promptFile `
            --timeout $TimeoutSeconds `
            --verbose full `
            --json 2>$stderrFile | Out-String).Trim()
        $exitCode = $LASTEXITCODE
        $stderr = if (Test-Path -LiteralPath $stderrFile) {
            Get-Content -LiteralPath $stderrFile -Raw
        }
        else { "" }

        Save-Receipt -Name ("$Stage.session.json") -Content $raw | Out-Null
        if ($stderr) {
            Save-Receipt -Name ("$Stage.session.stderr.txt") -Content $stderr | Out-Null
        }
        if ($exitCode -ne 0) {
            throw "OpenClaw session readiness failed for $Stage/$AgentId with exit code $exitCode. $stderr"
        }

        $sessionEnvelope = Convert-OpenClawJson $raw
        $canonicalSessionKey = [string]$sessionEnvelope.result.meta.systemPromptReport.sessionKey
        if ([string]::IsNullOrWhiteSpace($canonicalSessionKey)) {
            $canonicalSessionKey = ("agent:{0}:{1}" -f $AgentId, $alias)
        }
        if (-not $canonicalSessionKey.StartsWith(("agent:{0}:" -f $AgentId), [System.StringComparison]::Ordinal)) {
            throw "OpenClaw returned session '$canonicalSessionKey' for $Stage, which does not belong to agent $AgentId."
        }

        Write-Host "PASS OpenClaw session $Stage / $AgentId" -ForegroundColor Green
        return $canonicalSessionKey
    }
    finally {
        Remove-Item -LiteralPath $promptFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Assert-EffectiveTool {
    param(
        [string]$Stage,
        [string]$AgentId,
        [string]$SessionKey,
        [string]$ToolName
    )

    $paramsJson = @{ sessionKey = $SessionKey } | ConvertTo-Json -Compress
    $paramsNative = Convert-ToOpenClawNativeJsonArgument -Json $paramsJson
    $raw = (& $openclaw.Source gateway call tools.effective --params $paramsNative --json 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "tools.effective failed for $Stage/$AgentId. $raw"
    }
    Save-Receipt -Name ("$Stage.effective.json") -Content $raw | Out-Null
    $effective = Convert-OpenClawJson $raw
    $serialized = $effective | ConvertTo-Json -Depth 40 -Compress
    if ($serialized -notmatch ('(?<![A-Za-z0-9_])' + [regex]::Escape($ToolName) + '(?![A-Za-z0-9_])')) {
        throw "$AgentId does not have effective OpenClaw tool $ToolName in session $SessionKey."
    }
}

function Invoke-ClassifireTool {
    param(
        [string]$Stage,
        [string]$AgentId,
        [string]$SessionKey,
        [string]$ToolName,
        [hashtable]$ToolArgs,
        [string]$ReceiptName
    )

    Assert-EffectiveTool -Stage $Stage -AgentId $AgentId -SessionKey $SessionKey -ToolName $ToolName

    # /tools/invoke uses Gateway auth plus the same effective tool policy. HTTP
    # request bodies avoid Windows PowerShell 5.1/npm shim argument splitting.
    $idempotencyKey = "classifire-uat-$RunId-$Stage-$ToolName-$ReceiptName"
    $paramsJson = @{
        name = $ToolName
        args = $ToolArgs
        sessionKey = $SessionKey
        agentId = $AgentId
        idempotencyKey = $idempotencyKey
    } | ConvertTo-Json -Depth 30 -Compress

    Write-Host "Invoking $ToolName as $AgentId..." -ForegroundColor Cyan
    $invokeUrl = $GatewayHttpBaseUrl.TrimEnd('/') + "/tools/invoke"
    $headers = Get-OpenClawGatewayHttpHeaders

    try {
        $response = Invoke-WebRequest `
            -Uri $invokeUrl `
            -Method POST `
            -Headers $headers `
            -ContentType "application/json" `
            -Body $paramsJson `
            -UseBasicParsing `
            -TimeoutSec 90
        $raw = [string]$response.Content
        Save-Receipt -Name $ReceiptName -Content $raw | Out-Null
    }
    catch [System.Net.WebException] {
        $status = $null
        $raw = ""
        if ($null -ne $_.Exception.Response) {
            try { $status = [int]$_.Exception.Response.StatusCode } catch { }
            try {
                $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
                try { $raw = $reader.ReadToEnd() } finally { $reader.Dispose() }
            }
            catch { }
        }
        if ($raw) { Save-Receipt -Name ($ReceiptName + ".error.json") -Content $raw | Out-Null }
        $statusSuffix = if ($null -ne $status) { " with HTTP $status" } else { "" }
        throw ("OpenClaw HTTP /tools/invoke failed for {0}/{1}{2}. {3}" -f $ToolName, $AgentId, $statusSuffix, $raw)
    }

    $payload = Convert-OpenClawJson $raw
    $invokeOk = $false
    if ($null -ne $payload.PSObject.Properties["ok"]) {
        $invokeOk = [bool]$payload.ok
    }
    elseif ($null -ne $payload.PSObject.Properties["result"] -and $null -ne $payload.result.PSObject.Properties["ok"]) {
        $invokeOk = [bool]$payload.result.ok
    }
    if (-not $invokeOk) {
        throw "OpenClaw policy/tool invocation returned ok=false for $ToolName/$AgentId. $raw"
    }
    Write-Host "PASS tool $ToolName / $AgentId" -ForegroundColor Green
    return $payload
}

function Verify-UatStage {
    param(
        [string]$EstimateId,
        [string]$ExpectedStage,
        [string]$ReceiptName
    )
    $raw = (& $python.Source $uatHelper verify `
        --estimate-id $EstimateId `
        --expect-stage $ExpectedStage | Out-String).Trim()
    $exitCode = $LASTEXITCODE
    Save-Receipt -Name $ReceiptName -Content $raw | Out-Null
    if ($exitCode -ne 0) {
        throw "CLASSIFIRE UAT verification failed for expected stage '$ExpectedStage'. $raw"
    }
    $payload = $raw | ConvertFrom-Json
    if (-not [bool]$payload.ok) {
        throw "CLASSIFIRE UAT verifier returned failure for '$ExpectedStage': $($payload.errors -join '; ')"
    }
    Write-Host "PASS CLASSIFIRE stage -> $ExpectedStage" -ForegroundColor Green
    return $payload
}

Write-Host "CLASSIFIRE controlled OpenClaw reference UAT" -ForegroundColor Cyan
Write-Host "Run ID: $RunId" -ForegroundColor DarkGray
Write-Host "Receipts: $receiptDir" -ForegroundColor DarkGray

Write-Host "Validating OpenClaw configuration..." -ForegroundColor Cyan
& $openclaw.Source config validate --json | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw configuration is invalid." }

Write-Host "Checking live OpenClaw Gateway RPC..." -ForegroundColor Cyan
& $openclaw.Source gateway status --require-rpc | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw Gateway RPC preflight failed." }

Write-Host "Checking OpenClaw Gateway HTTP auth..." -ForegroundColor Cyan
$null = Get-OpenClawGatewayHttpHeaders
Write-Host "PASS OpenClaw Gateway HTTP auth resolved" -ForegroundColor Green

Write-Host "Checking CLASSIFIRE API..." -ForegroundColor Cyan
$health = Invoke-RestMethod ($BaseUrl.TrimEnd('/') + "/healthz")
if ($health.status -ne "ok" -or $health.product -ne "CLASSIFIRE") {
    throw "CLASSIFIRE API health check failed."
}

Write-Host "Preparing governed synthetic reference estimate..." -ForegroundColor Cyan
$fixtureRaw = (& $python.Source $uatHelper prepare --run-id $RunId | Out-String).Trim()
$prepareExit = $LASTEXITCODE
Save-Receipt -Name "00-fixture.json" -Content $fixtureRaw | Out-Null
if ($prepareExit -ne 0) {
    throw "Reference UAT fixture creation failed. $fixtureRaw"
}
$fixture = $fixtureRaw | ConvertFrom-Json
if (-not [bool]$fixture.ok) {
    throw "Reference UAT fixture creation returned failure: $($fixture.error)"
}

$estimateId = [string]$fixture.estimate_id
$openingId = [string]$fixture.opening_id
$variantId = [string]$fixture.variant_id
$pricingEntryId = [string]$fixture.pricing_entry_id

Verify-UatStage -EstimateId $estimateId -ExpectedStage "opening_specific_technical_search" -ReceiptName "01-initial-state.json" | Out-Null

# Technical stage: exact candidate search, controlled selection and deterministic RepairStrategyLock.
$technicalAgent = "cf-technical-system"
$technicalSession = Initialize-UatAgentSession -Stage "10-technical" -AgentId $technicalAgent
Invoke-ClassifireTool -Stage "10-technical" -AgentId $technicalAgent -SessionKey $technicalSession `
    -ToolName "classifire_workflow_status" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "10a-technical-workflow.json" | Out-Null
Invoke-ClassifireTool -Stage "10-technical" -AgentId $technicalAgent -SessionKey $technicalSession `
    -ToolName "classifire_technical_search" -ToolArgs @{ opening_id = $openingId } `
    -ReceiptName "10b-technical-search.json" | Out-Null
Invoke-ClassifireTool -Stage "10-technical" -AgentId $technicalAgent -SessionKey $technicalSession `
    -ToolName "classifire_select_repair_strategy" -ToolArgs @{
        opening_id = $openingId
        variant_id = $variantId
        match_classification = "opening_specific_candidate"
        treatment_description = "Controlled reference UAT exact Package 15 collar treatment"
        assumptions = @()
        limitations = @()
    } -ReceiptName "10c-technical-select.json" | Out-Null
Invoke-ClassifireTool -Stage "10-technical" -AgentId $technicalAgent -SessionKey $technicalSession `
    -ToolName "classifire_lock_repair_strategy" -ToolArgs @{ opening_id = $openingId } `
    -ReceiptName "10d-technical-lock.json" | Out-Null
$afterTechnical = Verify-UatStage -EstimateId $estimateId -ExpectedStage "quantity_and_labour" -ReceiptName "11-after-technical.json"
if (@($afterTechnical.required_components).Count -ne 1) {
    throw "Reference UAT expected exactly one Package 15 required component after technical lock."
}
$requiredComponentId = [string]$afterTechnical.required_components[0].id

# Quantity/labour stage: QF-EACH resolves from the canonical one-service physical model.
$quantityAgent = "cf-physical-model"
$quantitySession = Initialize-UatAgentSession -Stage "20-quantity" -AgentId $quantityAgent
Invoke-ClassifireTool -Stage "20-quantity" -AgentId $quantityAgent -SessionKey $quantitySession `
    -ToolName "classifire_workflow_status" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "20a-quantity-workflow.json" | Out-Null
Invoke-ClassifireTool -Stage "20-quantity" -AgentId $quantityAgent -SessionKey $quantitySession `
    -ToolName "classifire_derive_quantity_labour" -ToolArgs @{
        estimate_id = $estimateId
        component_inputs = @{}
        labour_adjustments = @{}
    } -ReceiptName "20b-quantity-derive.json" | Out-Null
Verify-UatStage -EstimateId $estimateId -ExpectedStage "commercial_pricing_and_recovery" -ReceiptName "21-after-quantity.json" | Out-Null

# Commercial stage: recommendation is retained for audit; the deterministic engine may auto-apply only the single exact eligible rate.
$commercialAgent = "cf-commercial-engine"
$commercialSession = Initialize-UatAgentSession -Stage "30-commercial" -AgentId $commercialAgent
Invoke-ClassifireTool -Stage "30-commercial" -AgentId $commercialAgent -SessionKey $commercialSession `
    -ToolName "classifire_workflow_status" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "30a-commercial-workflow.json" | Out-Null
Invoke-ClassifireTool -Stage "30-commercial" -AgentId $commercialAgent -SessionKey $commercialSession `
    -ToolName "classifire_required_components" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "30b-required-components.json" | Out-Null
Invoke-ClassifireTool -Stage "30-commercial" -AgentId $commercialAgent -SessionKey $commercialSession `
    -ToolName "classifire_package14_recommendation" -ToolArgs @{ component_id = $requiredComponentId } `
    -ReceiptName "30c-package14-recommendation.json" | Out-Null
Invoke-ClassifireTool -Stage "30-commercial" -AgentId $commercialAgent -SessionKey $commercialSession `
    -ToolName "classifire_derive_commercial" -ToolArgs @{
        estimate_id = $estimateId
        library_selections = @{}
        parameterised_selections = @{}
        component_builds = @{}
        expert_estimates = @{}
    } -ReceiptName "30d-commercial-derive.json" | Out-Null
$afterCommercial = Verify-UatStage -EstimateId $estimateId -ExpectedStage "independent_validation" -ReceiptName "31-after-commercial.json"
if (@($afterCommercial.commercial_methods).Count -ne 1 -or [string]$afterCommercial.commercial_methods[0].selected_pricing_method -ne "Exact Library Match") {
    throw "Reference UAT did not retain exactly one Exact Library Match commercial method for $pricingEntryId."
}

# Independent validation stage.
$validatorAgent = "cf-validator"
$validatorSession = Initialize-UatAgentSession -Stage "40-validation" -AgentId $validatorAgent
Invoke-ClassifireTool -Stage "40-validation" -AgentId $validatorAgent -SessionKey $validatorSession `
    -ToolName "classifire_workflow_status" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "40a-validation-workflow.json" | Out-Null
Invoke-ClassifireTool -Stage "40-validation" -AgentId $validatorAgent -SessionKey $validatorSession `
    -ToolName "classifire_run_validation" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "40b-validation-run.json" | Out-Null
Verify-UatStage -EstimateId $estimateId -ExpectedStage "validated_snapshot" -ReceiptName "41-after-validation.json" | Out-Null

# Output stage: immutable validated snapshot and controlled workbooks only. Human Release stays outside all agent tools.
$outputAgent = "cf-output"
$outputSession = Initialize-UatAgentSession -Stage "50-output" -AgentId $outputAgent
Invoke-ClassifireTool -Stage "50-output" -AgentId $outputAgent -SessionKey $outputSession `
    -ToolName "classifire_workflow_status" -ToolArgs @{ estimate_id = $estimateId } `
    -ReceiptName "50a-output-workflow.json" | Out-Null
Invoke-ClassifireTool -Stage "50-output" -AgentId $outputAgent -SessionKey $outputSession `
    -ToolName "classifire_lock_snapshot" -ToolArgs @{
        estimate_id = $estimateId
        reason = "Controlled OpenClaw reference UAT after passing deterministic validation"
    } -ReceiptName "50b-snapshot-lock.json" | Out-Null
Invoke-ClassifireTool -Stage "50-output" -AgentId $outputAgent -SessionKey $outputSession `
    -ToolName "classifire_render_output" -ToolArgs @{
        estimate_id = $estimateId
        artifact_type = "technical-xlsx"
    } -ReceiptName "50c-technical-xlsx.json" | Out-Null
Invoke-ClassifireTool -Stage "50-output" -AgentId $outputAgent -SessionKey $outputSession `
    -ToolName "classifire_render_output" -ToolArgs @{
        estimate_id = $estimateId
        artifact_type = "proposal-xlsx"
    } -ReceiptName "50d-proposal-xlsx.json" | Out-Null
$final = Verify-UatStage -EstimateId $estimateId -ExpectedStage "human_release" -ReceiptName "51-final-state.json"

Write-Host "Recording CF-UAT-001 review receipt in Mission Control..." -ForegroundColor Cyan
$mcRaw = (& $python.Source $uatHelper receipt --run-id $RunId --estimate-id $estimateId | Out-String).Trim()
$mcExit = $LASTEXITCODE
Save-Receipt -Name "60-mission-control-review.json" -Content $mcRaw | Out-Null
if ($mcExit -ne 0) {
    throw "Mission Control UAT receipt failed. CLASSIFIRE state is retained for diagnosis. $mcRaw"
}
$mcReceipt = $mcRaw | ConvertFrom-Json
if (-not [bool]$mcReceipt.ok -or $mcReceipt.status -ne "review") {
    throw "Mission Control did not accept CF-UAT-001 into review. $mcRaw"
}
Write-Host "PASS Mission Control CF-UAT-001 -> review" -ForegroundColor Green

Write-Host ""
Write-Host "CLASSIFIRE controlled multi-agent reference UAT PASSED." -ForegroundColor Green
Write-Host "Estimate: $($final.estimate_reference)" -ForegroundColor Green
Write-Host "Final stage: $($final.workflow.stage)" -ForegroundColor Green
Write-Host "Snapshot: $($final.snapshot_hash)" -ForegroundColor Green
Write-Host "Certificate: $($final.certificate_hash)" -ForegroundColor Green
Write-Host "Human Release approvals: $($final.human_release_approval_count) (must be 0)" -ForegroundColor Green
Write-Host "Mission Control: CF-UAT-001 is in review" -ForegroundColor Green
Write-Host "Receipts retained at: $receiptDir" -ForegroundColor Green
