param(
    [string]$RunId = (Get-Date -Format "yyyyMMdd-HHmmss"),
    [int]$TimeoutSeconds = 300,
    [string]$BaseUrl = "http://127.0.0.1:8787"
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

function Invoke-UatAgent {
    param(
        [string]$Stage,
        [string]$AgentId,
        [string]$Prompt
    )

    $promptFile = Join-Path $env:TEMP ("classifire-uat-" + $RunId + "-" + $Stage + ".txt")
    $stderrFile = Join-Path $env:TEMP ("classifire-uat-" + $RunId + "-" + $Stage + ".stderr.txt")
    Write-Utf8NoBom -Path $promptFile -Content $Prompt
    try {
        $sessionKey = "classifire-uat-$RunId-$Stage"
        Write-Host "Running $Stage with $AgentId..." -ForegroundColor Cyan
        $raw = (& $openclaw.Source agent `
            --agent $AgentId `
            --session-key $sessionKey `
            --message-file $promptFile `
            --timeout $TimeoutSeconds `
            --json 2>$stderrFile | Out-String).Trim()
        $exitCode = $LASTEXITCODE
        $stderr = if (Test-Path -LiteralPath $stderrFile) {
            Get-Content -LiteralPath $stderrFile -Raw
        }
        else { "" }

        Save-Receipt -Name ("$Stage.openclaw.json") -Content $raw | Out-Null
        if ($stderr) {
            Save-Receipt -Name ("$Stage.openclaw.stderr.txt") -Content $stderr | Out-Null
        }
        if ($exitCode -ne 0) {
            throw "OpenClaw agent turn failed for $Stage/$AgentId with exit code $exitCode. $stderr"
        }
        try {
            $null = $raw | ConvertFrom-Json
        }
        catch {
            throw "OpenClaw did not return the documented JSON envelope for $Stage/$AgentId. Raw response: $raw"
        }
        Write-Host "PASS OpenClaw turn $Stage / $AgentId" -ForegroundColor Green
    }
    finally {
        Remove-Item -LiteralPath $promptFile -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue
    }
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
& $openclaw.Source gateway status --deep --require-rpc | Out-Host
if ($LASTEXITCODE -ne 0) { throw "OpenClaw Gateway RPC preflight failed." }

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

$technicalPrompt = @"
Controlled CLASSIFIRE OpenClaw reference UAT. You are cf-technical-system.
Estimate ID: $estimateId
Opening ID: $openingId
Expected Package 15 variant: $variantId

Perform only this governed technical stage:
1. Call classifire_workflow_status for the estimate and require stage opening_specific_technical_search.
2. Call classifire_technical_search for the opening.
3. Locate variant $variantId for the service. Proceed only if it is returned, every critical comparison is MATCH, and blockers is empty. If not, stop and report ERROR without selecting or locking anything.
4. Call classifire_select_repair_strategy with this opening and variant, match_classification opening_specific_candidate, and treatment_description 'Controlled reference UAT exact Package 15 collar treatment'.
5. Call classifire_lock_repair_strategy for the opening. Require validator_result PASS and exactly one required component.
6. Call classifire_workflow_status again.
Do not perform commercial work, validation, output rendering, library approval, Human Release, shell, browser, filesystem or generic HTTP work. Reply with a concise result only.
"@
Invoke-UatAgent -Stage "10-technical" -AgentId "cf-technical-system" -Prompt $technicalPrompt
Verify-UatStage -EstimateId $estimateId -ExpectedStage "quantity_and_labour" -ReceiptName "11-after-technical.json" | Out-Null

$quantityPrompt = @"
Controlled CLASSIFIRE OpenClaw reference UAT. You are cf-physical-model.
Estimate ID: $estimateId

Perform only this governed quantity/labour stage:
1. Call classifire_workflow_status and require stage quantity_and_labour.
2. Call classifire_derive_quantity_labour for the estimate with empty component_inputs and empty labour_adjustments.
3. Require exactly one validated quantity, value 1, unit each, formula QF-EACH, with no required labour activities.
4. Call classifire_workflow_status again.
Do not change technical strategy, do commercial work, validate, render outputs or perform Human Release. Reply with a concise result only.
"@
Invoke-UatAgent -Stage "20-quantity" -AgentId "cf-physical-model" -Prompt $quantityPrompt
Verify-UatStage -EstimateId $estimateId -ExpectedStage "commercial_pricing_and_recovery" -ReceiptName "21-after-quantity.json" | Out-Null

$commercialPrompt = @"
Controlled CLASSIFIRE OpenClaw reference UAT. You are cf-commercial-engine.
Estimate ID: $estimateId
Expected exact Package 14 entry: $pricingEntryId

Perform only this governed commercial stage:
1. Call classifire_workflow_status and require stage commercial_pricing_and_recovery.
2. Call classifire_required_components and require exactly one mandatory COLLAR component with candidate_status CONFIRMED_TECHNICAL_MATCH.
3. For that required component, call classifire_package14_recommendation. Proceed only if $pricingEntryId is the exact eligible Package 14 basis. Never promote a near/proxy match.
4. Call classifire_derive_commercial with empty library_selections, parameterised_selections, component_builds and expert_estimates. The deterministic engine may auto-select only the single eligible exact match.
5. Require Exact Library Match, validator_outcome PASS, and no unresolved anomaly.
6. Call classifire_workflow_status again.
Do not perform validation, output rendering, library approval or Human Release. Reply with a concise result only.
"@
Invoke-UatAgent -Stage "30-commercial" -AgentId "cf-commercial-engine" -Prompt $commercialPrompt
Verify-UatStage -EstimateId $estimateId -ExpectedStage "independent_validation" -ReceiptName "31-after-commercial.json" | Out-Null

$validatorPrompt = @"
Controlled CLASSIFIRE OpenClaw reference UAT. You are cf-validator.
Estimate ID: $estimateId

Perform only final independent validation:
1. Call classifire_workflow_status and require stage independent_validation.
2. Call classifire_run_validation for the estimate.
3. Require passed true, result PASS, exception_count 0.
4. Call classifire_workflow_status again and require validated_snapshot.
Do not lock the snapshot, render outputs or perform Human Release. Reply with a concise result only.
"@
Invoke-UatAgent -Stage "40-validation" -AgentId "cf-validator" -Prompt $validatorPrompt
Verify-UatStage -EstimateId $estimateId -ExpectedStage "validated_snapshot" -ReceiptName "41-after-validation.json" | Out-Null

$outputPrompt = @"
Controlled CLASSIFIRE OpenClaw reference UAT. You are cf-output.
Estimate ID: $estimateId

Perform only controlled validated output creation:
1. Call classifire_workflow_status and require stage validated_snapshot.
2. Call classifire_lock_snapshot with reason 'Controlled OpenClaw reference UAT after passing deterministic validation'.
3. Call classifire_render_output for artifact_type technical-xlsx.
4. Call classifire_render_output for artifact_type proposal-xlsx.
5. Call classifire_workflow_status again and require stage human_release.
Never perform or request Human Release. Human Release must remain a separate human-controlled action. Reply with a concise result only.
"@
Invoke-UatAgent -Stage "50-output" -AgentId "cf-output" -Prompt $outputPrompt
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
