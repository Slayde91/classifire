param(
    [string]$WorkspaceRoot = "C:\CLASSIFIRE-OpenClaw",
    [int]$TimeoutSeconds = 180
)

$ErrorActionPreference = "Stop"
$openclaw = Get-Command openclaw -ErrorAction Stop

$agentIds = @(
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

Write-Host "Checking CLASSIFIRE OpenClaw agent roster..." -ForegroundColor Cyan
$roster = (& $openclaw.Source agents list --json 2>&1 | Out-String)

$failures = @()
foreach ($id in $agentIds) {
    if ($roster -notmatch [regex]::Escape($id)) {
        $failures += "$id is missing from OpenClaw roster"
        continue
    }

    $workspace = Join-Path $WorkspaceRoot $id
    foreach ($requiredFile in @("AGENTS.md", "SOUL.md", "IDENTITY.md")) {
        if (-not (Test-Path (Join-Path $workspace $requiredFile))) {
            $failures += "$id is missing $requiredFile"
        }
    }

    $prompt = @"
CLASSIFIRE fleet smoke test. Do not call tools, do not modify files, do not browse, and do not perform any canonical CLASSIFIRE action.
Read your controlled workspace identity/boundaries and reply with exactly two lines:
READY $id
BOUNDARY <one short sentence stating the most important thing your role must not do>
"@

    Write-Host "Testing $id..." -ForegroundColor Cyan
    $response = (& $openclaw.Source agent --agent $id --message $prompt --timeout $TimeoutSeconds --json 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        $failures += "$id agent turn failed: $response"
        continue
    }
    if ($response -notmatch [regex]::Escape("READY $id")) {
        $failures += "$id did not return the required READY receipt"
        Write-Host $response -ForegroundColor DarkYellow
        continue
    }
    Write-Host "PASS $id" -ForegroundColor Green
}

if ($failures.Count -gt 0) {
    Write-Host "" 
    Write-Host "CLASSIFIRE OpenClaw smoke test FAILED:" -ForegroundColor Red
    foreach ($failure in $failures) {
        Write-Host " - $failure" -ForegroundColor Red
    }
    exit 1
}

Write-Host "" 
Write-Host "CLASSIFIRE OpenClaw smoke test PASSED for all $($agentIds.Count) agents." -ForegroundColor Green
exit 0
